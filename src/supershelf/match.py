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

from supershelf.constants import KEY_MATCH_RULES, LOGGER_NAME
from supershelf.errors import SupershelfError
from supershelf.scan import InputFile, InputScanResult

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


@dataclass(frozen=True)
class _RegexField:
    source: str
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class _GlobField:
    source: str
    patterns: tuple[str, ...]


_CompiledField = _RegexField | _GlobField


@dataclass(frozen=True)
class _Rule:
    name: str
    kind: str
    fields: tuple[_CompiledField, ...]


@dataclass(frozen=True)
class FileMatch:
    """One file claimed by a match rule."""

    profile: str
    index: int
    path: str
    kind: str
    rule: str
    groups: dict[str, str]


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
            spec = _parse_rule(profile_name, index, item)
            rule_name = _rule_labels(spec)[0]
            if rule_name in seen:
                raise SupershelfError(
                    f"Profile {profile_name} has duplicate match rule {rule_name!r}"
                )
            seen.add(rule_name)
            rules.append(_compile_rule(profile_name, spec))
        return cls(profile_name, tuple(rules))

    def claim(self, file: InputFile) -> FileMatch | None:
        """Return the first matching rule, or None."""
        for rule in self._rules:
            hit = _claim_rule(rule, file)
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


def _parse_rule(profile_name: str, index: int, item: object) -> MatchRuleSpec:
    if not isinstance(item, dict):
        raise SupershelfError(
            f"Profile {profile_name} match rule {index} must be a mapping"
        )
    try:
        spec = MatchRuleSpec.model_validate(item)
    except ValidationError as exc:
        raise SupershelfError(
            f"Invalid match rule {index} in profile {profile_name}: {exc}"
        ) from exc
    if not any(getattr(spec, name) for name in _PATTERN_FIELDS):
        raise SupershelfError(
            f"Profile {profile_name} match rule {_rule_labels(spec)[0]!r} has no patterns"
        )
    return spec


def _rule_labels(spec: MatchRuleSpec) -> tuple[str, str]:
    """Return the rule name and the kind. An explicit kind wins."""
    name = spec.name if spec.name is not None else spec.kind
    kind = spec.kind if spec.kind is not None else spec.name
    if name is None or kind is None:
        raise SupershelfError("match rule needs a name or a kind")
    return name, kind


def _compile_rule(profile_name: str, spec: MatchRuleSpec) -> _Rule:
    rule_name, rule_kind = _rule_labels(spec)
    fields: list[_CompiledField] = []
    for field_name, attr, source, is_regex in _FIELDS:
        raw_patterns = getattr(spec, attr)
        if is_regex:
            fields.append(
                _RegexField(
                    source,
                    tuple(
                        _compile_regex(profile_name, rule_name, field_name, pattern)
                        for pattern in raw_patterns
                    ),
                )
            )
        else:
            fields.append(_GlobField(source, tuple(raw_patterns)))
    return _Rule(rule_name, rule_kind, tuple(fields))


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


def _claim_rule(rule: _Rule, file: InputFile) -> tuple[str, dict[str, str]] | None:
    for field in rule.fields:
        if not field.patterns:
            continue
        if field.source == _DIRECTORY and file.directory == "":
            continue
        groups = _match_field(field, getattr(file, field.source))
        if groups is None:
            continue
        return rule.kind, groups
    return None


def _match_field(field: _CompiledField, candidate: str) -> dict[str, str] | None:
    if isinstance(field, _RegexField):
        for pattern in field.patterns:
            matched = pattern.fullmatch(candidate)
            if matched is None:
                continue
            return {
                name: value
                for name, value in matched.groupdict().items()
                if value is not None
            }
        return None
    for pattern in field.patterns:
        if PurePosixPath(candidate).full_match(pattern):
            return {}
    return None
