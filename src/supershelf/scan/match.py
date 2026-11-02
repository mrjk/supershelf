"""Classify scanned files with profile match_rules."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from supershelf.constants import KEY_MATCH_RULES, KEY_RULE_VARS, LOGGER_NAME
from supershelf.errors import SupershelfError
from supershelf.scan.walk import InputFile, InputScanResult

# Field name, model attribute, InputFile attribute, True when the pattern is a regex.
_FIELDS = (
    ("regex", "regex", "path", True),
    ("directory_regex", "directory_regex", "directory", True),
    ("filename_regex", "filename_regex", "name", True),
    ("glob", "glob", "path", False),
    ("directory_glob", "directory_glob", "directory", False),
    ("filename_glob", "filename_glob", "name", False),
)
_PATTERN_FIELDS = tuple(attr for _, attr, _, _ in _FIELDS)
_DIRECTORY = "directory"

STATUS_HIT = "hit"
STATUS_MISS = "miss"
STATUS_SKIPPED = "skipped"
STATUS_NOT_TRIED = "not tried"
DETAIL_NO_PATTERNS = "no patterns"
DETAIL_EMPTY_DIRECTORY = "empty directory"


class MatchRuleSpec(BaseModel):
    """One match rule. Unknown keys, including vars, are ignored."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    kind: str | None = None
    regex: list[str] = Field(default_factory=list)
    directory_regex: list[str] = Field(default_factory=list)
    filename_regex: list[str] = Field(default_factory=list)
    glob: list[str] = Field(default_factory=list)
    directory_glob: list[str] = Field(default_factory=list)
    filename_glob: list[str] = Field(default_factory=list)

    @field_validator("name", "kind", mode="before")
    @classmethod
    def blank_is_unset(cls, value: object) -> str | None:
        """A blank name or kind counts as omitted."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("must be a string")
        if not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def has_name_or_kind(self) -> MatchRuleSpec:
        if self.name is None and self.kind is None:
            raise ValueError("needs a name or a kind")
        return self

    @field_validator(*_PATTERN_FIELDS, mode="before")
    @classmethod
    def patterns(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        raise ValueError("must be a string or a list of strings")

    def labels(self) -> tuple[str, str]:
        """Return the rule name and the kind. An explicit kind wins."""
        name = self.name if self.name is not None else self.kind
        kind = self.kind if self.kind is not None else self.name
        if name is None or kind is None:
            raise SupershelfError("match rule needs a name or a kind")
        return name, kind

    @classmethod
    def from_item(cls, profile_name: str, index: int, item: object) -> MatchRuleSpec:
        """Parse one rule mapping. A bad shape or a rule with no patterns fails."""
        if not isinstance(item, dict):
            raise SupershelfError(
                f"Profile {profile_name} match rule {index} must be a mapping"
            )
        try:
            spec = cls.model_validate(item)
        except ValidationError as exc:
            raise SupershelfError(
                f"Invalid match rule {index} in profile {profile_name}: {exc}"
            ) from exc
        if not any(getattr(spec, name) for name in _PATTERN_FIELDS):
            raise SupershelfError(
                f"Profile {profile_name} match rule {spec.labels()[0]!r} has no patterns"
            )
        return spec


@dataclass(frozen=True)
class _CompiledField:
    """One compiled pattern field. Subclasses know how to match it."""

    name: str
    source: str
    patterns: tuple[re.Pattern[str] | str, ...]

    def candidate(self, file: InputFile) -> str:
        """The string this field compares against."""
        return getattr(file, self.source)

    def skip_reason(self, file: InputFile) -> str | None:
        """Why this field is not compared, or None when it is tried."""
        if not self.patterns:
            return DETAIL_NO_PATTERNS
        if self.source == _DIRECTORY and file.directory == "":
            return DETAIL_EMPTY_DIRECTORY
        return None

    def pattern_text(self, pattern: re.Pattern[str] | str) -> str:
        """The pattern as the user wrote it."""
        if isinstance(pattern, re.Pattern):
            return pattern.pattern
        return pattern

    def match_one(
        self,
        pattern: re.Pattern[str] | str,
        candidate: str,
    ) -> dict[str, str] | None:
        """Groups when this one pattern matches the whole candidate."""
        raise NotImplementedError


@dataclass(frozen=True)
class _RegexField(_CompiledField):
    patterns: tuple[re.Pattern[str], ...]

    def match_one(
        self,
        pattern: re.Pattern[str] | str,
        candidate: str,
    ) -> dict[str, str] | None:
        if not isinstance(pattern, re.Pattern):
            return None
        matched = pattern.fullmatch(candidate)
        if matched is None:
            return None
        return {
            name: value
            for name, value in matched.groupdict().items()
            if value is not None
        }


@dataclass(frozen=True)
class _GlobField(_CompiledField):
    patterns: tuple[str, ...]

    def match_one(
        self,
        pattern: re.Pattern[str] | str,
        candidate: str,
    ) -> dict[str, str] | None:
        if not isinstance(pattern, str):
            return None
        if PurePosixPath(candidate).full_match(pattern):
            return {}
        return None


@dataclass(frozen=True)
class _Rule:
    name: str
    kind: str
    fields: tuple[_CompiledField, ...]
    variables: object

    def claim(self, file: InputFile) -> tuple[str, dict[str, str]] | None:
        """Kind and groups when one field matches. Later fields are not tried."""
        for field in self.fields:
            if field.skip_reason(file) is not None:
                continue
            candidate = field.candidate(file)
            for pattern in field.patterns:
                groups = field.match_one(pattern, candidate)
                if groups is None:
                    continue
                return self.kind, groups
        return None

    def explain_reached(
        self,
        file: InputFile,
    ) -> tuple[list[PatternTrial], dict[str, str] | None]:
        """Trials for this rule, in field order. Groups when the rule wins."""
        trials: list[PatternTrial] = []
        won: dict[str, str] | None = None
        for field in self.fields:
            reason = field.skip_reason(file)
            if reason is not None:
                trials.extend(self._trials_for_skip(field, file, reason))
                continue
            if won is not None:
                trials.extend(self._trials_not_reached(field, file))
                continue
            candidate = field.candidate(file)
            for index, pattern in enumerate(field.patterns):
                text = field.pattern_text(pattern)
                groups = field.match_one(pattern, candidate)
                if groups is None:
                    trials.append(self._trial(field, text, candidate, STATUS_MISS))
                    continue
                trials.append(
                    self._trial(field, text, candidate, STATUS_HIT, groups=groups)
                )
                won = groups
                for later in field.patterns[index + 1 :]:
                    trials.append(
                        self._trial(
                            field,
                            field.pattern_text(later),
                            candidate,
                            STATUS_NOT_TRIED,
                        )
                    )
                break
        return trials, won

    def explain_unreached(self, file: InputFile) -> list[PatternTrial]:
        """Trials for a rule that matching never runs, because an earlier rule won."""
        trials: list[PatternTrial] = []
        for field in self.fields:
            trials.extend(self._trials_not_reached(field, file))
        return trials

    def _trial(
        self,
        field: _CompiledField,
        pattern: str,
        candidate: str,
        status: str,
        detail: str = "",
        groups: dict[str, str] | None = None,
    ) -> PatternTrial:
        return PatternTrial(
            rule=self.name,
            kind=self.kind,
            field=field.name,
            pattern=pattern,
            candidate=candidate,
            status=status,
            detail=detail,
            groups={} if groups is None else dict(groups),
        )

    def _trials_for_skip(
        self,
        field: _CompiledField,
        file: InputFile,
        reason: str,
    ) -> list[PatternTrial]:
        candidate = field.candidate(file)
        if reason == DETAIL_NO_PATTERNS:
            return [self._trial(field, "", candidate, STATUS_SKIPPED, reason)]
        return [
            self._trial(
                field,
                field.pattern_text(pattern),
                candidate,
                STATUS_SKIPPED,
                reason,
            )
            for pattern in field.patterns
        ]

    def _trials_not_reached(
        self,
        field: _CompiledField,
        file: InputFile,
    ) -> list[PatternTrial]:
        """A later field. Skips stay skips. Real patterns were not tried."""
        reason = field.skip_reason(file)
        if reason is not None:
            return self._trials_for_skip(field, file, reason)
        candidate = field.candidate(file)
        return [
            self._trial(
                field,
                field.pattern_text(pattern),
                candidate,
                STATUS_NOT_TRIED,
            )
            for pattern in field.patterns
        ]


@dataclass(frozen=True)
class FileMatch:
    """One file claimed by a match rule."""

    profile: str
    index: int
    path: str
    kind: str
    rule: str
    groups: dict[str, str]


@dataclass(frozen=True)
class PatternTrial:
    """One pattern comparison, or a field matching did not run."""

    rule: str
    kind: str
    field: str
    pattern: str
    candidate: str
    status: str
    detail: str
    groups: dict[str, str]


@dataclass(frozen=True)
class FileInspection:
    """Every trial for one file, plus the rule that claimed it."""

    match: FileMatch | None
    trials: tuple[PatternTrial, ...]


class Matcher:
    """Compiled match_rules for one profile."""

    def __init__(self, profile_name: str, rules: tuple[_Rule, ...]) -> None:
        self.profile_name = profile_name
        self._rules = rules
        self._logger = logging.getLogger(LOGGER_NAME)

    @classmethod
    def from_document(cls, document: dict[str, Any], profile_name: str) -> Matcher:
        raw = document.get(KEY_MATCH_RULES)
        if raw is None:
            return cls(profile_name, ())
        if not isinstance(raw, list):
            raise SupershelfError(
                f"Profile {profile_name} match_rules must be a list"
            )
        rules: list[_Rule] = []
        seen: set[str] = set()
        for index, item in enumerate(raw, start=1):
            spec = MatchRuleSpec.from_item(profile_name, index, item)
            rule_name = spec.labels()[0]
            if rule_name in seen:
                raise SupershelfError(
                    f"Profile {profile_name} has duplicate match rule {rule_name!r}"
                )
            seen.add(rule_name)
            variables = item.get(KEY_RULE_VARS) if isinstance(item, dict) else None
            rules.append(cls._compile_rule(profile_name, spec, variables))
        return cls(profile_name, tuple(rules))

    @classmethod
    def _compile_rule(
        cls,
        profile_name: str,
        spec: MatchRuleSpec,
        variables: object,
    ) -> _Rule:
        rule_name, rule_kind = spec.labels()
        fields: list[_CompiledField] = []
        for field_name, attr, source, is_regex in _FIELDS:
            raw_patterns = getattr(spec, attr)
            if is_regex:
                fields.append(
                    _RegexField(
                        field_name,
                        source,
                        tuple(
                            cls._compile_regex(
                                profile_name, rule_name, field_name, pattern
                            )
                            for pattern in raw_patterns
                        ),
                    )
                )
            else:
                fields.append(_GlobField(field_name, source, tuple(raw_patterns)))
        return _Rule(rule_name, rule_kind, tuple(fields), variables)

    @staticmethod
    def _compile_regex(
        profile_name: str,
        rule_name: str,
        field_name: str,
        pattern: str,
    ) -> re.Pattern[str]:
        try:
            return re.compile(pattern)
        except re.error as exc:
            raise SupershelfError(
                f"Invalid regex in profile {profile_name} rule {rule_name!r} "
                f"{field_name}: {pattern}: {exc}"
            ) from exc

    def named_groups(self) -> tuple[str, ...]:
        """Named groups from the compiled regexes, in first-seen order."""
        names: list[str] = []
        seen: set[str] = set()
        for rule in self._rules:
            for field in rule.fields:
                if not isinstance(field, _RegexField):
                    continue
                for pattern in field.patterns:
                    for name in pattern.groupindex:
                        if name in seen:
                            continue
                        seen.add(name)
                        names.append(name)
        return tuple(names)

    def rule_vars(self) -> tuple[tuple[str, str, object], ...]:
        """Raw vars for each compiled rule, in rule order, with that rule's kind."""
        return tuple((rule.name, rule.kind, rule.variables) for rule in self._rules)

    def claim(self, file: InputFile) -> FileMatch | None:
        """Return the first matching rule, or None."""
        for rule in self._rules:
            hit = rule.claim(file)
            if hit is None:
                continue
            kind, groups = hit
            return FileMatch(
                profile=self.profile_name,
                index=0,
                path=file.path,
                kind=kind,
                rule=rule.name,
                groups=groups,
            )
        return None

    def collect(self, scan: InputScanResult) -> list[FileMatch]:
        """Claim files in one scan. Unmatched files stay on the scan result."""
        found: list[FileMatch] = []
        for file in scan.results:
            hit = self.claim(file)
            if hit is None:
                self._logger.warning(
                    "No match_rule for %s in profile %s input %s",
                    file.path,
                    scan.profile,
                    scan.index,
                )
                continue
            found.append(replace(hit, profile=scan.profile, index=scan.index))
        return found

    def explain(self, file: InputFile) -> FileInspection:
        """Return every trial for one file. The first hit still wins."""
        trials: list[PatternTrial] = []
        found: FileMatch | None = None
        for rule in self._rules:
            if found is not None:
                trials.extend(rule.explain_unreached(file))
                continue
            rule_trials, won = rule.explain_reached(file)
            trials.extend(rule_trials)
            if won is None:
                continue
            found = FileMatch(
                profile=self.profile_name,
                index=0,
                path=file.path,
                kind=rule.kind,
                rule=rule.name,
                groups=dict(won),
            )
        return FileInspection(match=found, trials=tuple(trials))
