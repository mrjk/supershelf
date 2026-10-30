"""Resolve variables for one matched file."""

from __future__ import annotations

import csv
import importlib
import io
import logging
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from supershelf.common import load_mapping_file, resolve_user_path
from supershelf.constants import (
    ALIAS_NAMES,
    CONFIG_SECTION,
    DATE_TEXT,
    INTERNAL_NAMES,
    KEY_DEFAULT_VARS,
    KEY_KIND_OVERRIDES,
    LOGGER_NAME,
    KEY_MATCH_RULES,
    KEY_OVERRIDE_PATH,
    KEY_OVERRIDES,
    KEY_RULE_VARS,
    KEY_VAR_MODULES,
    VAR_CTIME,
    VAR_DATE,
    VAR_FILE_CTIME,
    VAR_FILE_DIR,
    VAR_FILE_EXT,
    VAR_FILE_HASH,
    VAR_FILE_MTIME,
    VAR_FILE_NAME,
    VAR_FILE_PATH,
    VAR_FILE_STEM,
    VAR_FILTERS,
    VAR_GLOBALS,
    VAR_INPUT,
    VAR_KIND,
    VAR_MTIME,
    VAR_RULE_NAME,
)
from supershelf.errors import SupershelfError, VarCandidateError, VarConfigError, VarResolveError
from supershelf.match import FileMatch, MatchRuleSpec, Matcher
from supershelf.scan import InputFile
from supershelf.template import Template
from supershelf.var_commands import FileBinding
from supershelf.var_template import VarEnvironment


class FileVars:
    """Resolved variables for one matched file."""

    def __init__(self, kind: str, rule: str, items: tuple[tuple[str, str], ...]) -> None:
        self.kind = kind
        self.rule = rule
        self.items = items


class VarTable:
    """Ordered variable definitions. Each value is one or more candidates."""

    _IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
    _LOCKED = tuple(name for name in INTERNAL_NAMES if name != VAR_KIND) + ALIAS_NAMES

    def __init__(self, keys: tuple[str, ...], candidates: dict[str, tuple[str, ...]]) -> None:
        self.keys = keys
        self.candidates = candidates

    @classmethod
    def empty(cls) -> VarTable:
        """A table with no keys."""
        return cls((), {})

    @classmethod
    def parse(
        cls,
        raw: object,
        *,
        label: str,
        allows_kind: bool,
        environment: VarEnvironment,
    ) -> VarTable:
        """Parse a mapping of strings or string lists and compile every candidate."""
        if raw is None:
            return cls.empty()
        if not isinstance(raw, dict):
            raise VarConfigError(
                f"{label} must be a mapping",
                advice="Use a name, then a string or a list of strings.",
            )
        keys: list[str] = []
        candidates: dict[str, tuple[str, ...]] = {}
        for key, value in raw.items():
            cls._check_key(key, label, allows_kind)
            items = cls._candidates(value, label, str(key))
            for item in items:
                environment.compile_source(item)
            keys.append(str(key))
            candidates[str(key)] = items
        return cls(tuple(keys), candidates)

    @classmethod
    def _check_key(cls, key: object, label: str, allows_kind: bool) -> None:
        if not isinstance(key, str) or cls._IDENT.fullmatch(key) is None:
            raise VarConfigError(
                f"{label} key {key!r} is not a variable name",
                advice="Start with a letter or underscore, then use letters, digits, and underscores.",
            )
        if key in cls._LOCKED or (key == VAR_KIND and not allows_kind):
            raise VarConfigError(
                f"{label} cannot set {key}",
                advice="Only an override may set __kind__. Other internal names are fixed.",
            )

    @classmethod
    def _candidates(cls, value: object, label: str, key: str) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list):
            if not value:
                raise VarConfigError(
                    f"{label} key {key} has an empty list",
                    advice="Add at least one string, or remove the key.",
                )
            if all(isinstance(item, str) for item in value):
                return tuple(value)
        raise VarConfigError(
            f"{label} key {key} must be a string or a list of strings",
            advice="Quote scalars such as dates so they stay strings.",
        )


class OverrideRule:
    """One per-file override. The first matching path wins."""

    def __init__(self, pattern: str, table: VarTable) -> None:
        self.pattern = pattern
        self.table = table

    def matches(self, relative: str) -> bool:
        """Full-match the path relative to the input directory."""
        return PurePosixPath(relative).full_match(self.pattern)


class KindFiles:
    """Kind-wide var files. The first existing path wins, then the parse is cached."""

    def __init__(
        self,
        templates: tuple[str, ...],
        environment: VarEnvironment,
        root_dir: Path,
        profile_scope: Mapping[str, Any],
    ) -> None:
        self._templates = templates
        self._environment = environment
        self._root = root_dir
        self._profile_scope = profile_scope
        self._cache: dict[Path, VarTable] = {}
        self._logger = logging.getLogger(LOGGER_NAME)

    @classmethod
    def from_section(
        cls,
        section: Mapping[str, Any],
        environment: VarEnvironment,
        root_dir: Path,
        profile_scope: Mapping[str, Any],
    ) -> KindFiles:
        """Check the path list. Files are read later, when a kind is used."""
        raw = section.get(KEY_KIND_OVERRIDES)
        if raw is None or raw == []:
            return cls((), environment, root_dir, profile_scope)
        if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
            raise VarConfigError(
                "config.kind_overrides_config must be a list of path templates",
                advice="Omit it, or list strings such as {{ __root_dir__ }}/{{ __kind__ }}.csv.",
            )
        return cls(tuple(raw), environment, root_dir, profile_scope)

    def table_for(self, kind: str, input_dir: Path) -> VarTable:
        """Return the kind-wide table, or an empty table when no file exists."""
        scope = dict(self._profile_scope)
        scope[VAR_KIND] = kind
        scope[VAR_INPUT] = {"path": str(input_dir)}
        for template in self._templates:
            path = self._render_path(template, scope)
            if not path.exists():
                continue
            if not path.is_file():
                raise VarConfigError(
                    f"Kind file {path} is not a file",
                    advice="Point kind_overrides_config at a csv, toml, or yaml file.",
                )
            cached_path = path.resolve()
            cached = self._cache.get(cached_path)
            if cached is None:
                cached = self._load(cached_path)
                self._cache[cached_path] = cached
                self._logger.debug("Loaded kind file %s for kind %s", cached_path, kind)
            return cached
        return VarTable.empty()

    def _render_path(self, template: str, scope: Mapping[str, Any]) -> Path:
        try:
            rendered = Template(scope).render(template).strip()
        except SupershelfError as exc:
            raise VarConfigError(str(exc), advice=exc.advice) from exc
        if not rendered:
            raise VarConfigError(
                "A kind_overrides_config path rendered empty",
                advice="The path template must render to a file path.",
            )
        return resolve_user_path(rendered, self._root)

    def _load(self, path: Path) -> VarTable:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            raw: object = self._read_csv(path)
        elif suffix in (".toml", ".yaml", ".yml"):
            raw = self._read_mapping(path)
        else:
            raise VarConfigError(
                f"Kind file {path} has an unsupported suffix",
                advice="Use .csv, .toml, .yaml, or .yml.",
            )
        return VarTable.parse(
            raw,
            label=str(path),
            allows_kind=False,
            environment=self._environment,
        )

    def _read_mapping(self, path: Path) -> object:
        try:
            raw, _file_type = load_mapping_file(path)
        except SupershelfError as exc:
            raise VarConfigError(str(exc), advice=exc.advice) from exc
        except UnicodeDecodeError as exc:
            raise VarConfigError(
                f"{path} is not UTF-8",
                advice="Save the kind file as UTF-8.",
            ) from exc
        if raw is None:
            return {}
        return raw

    def _read_csv(self, path: Path) -> dict[str, str | list[str]]:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise VarConfigError(
                f"{path} is not UTF-8",
                advice="Save the kind file as UTF-8.",
            ) from exc
        try:
            rows = self._csv_rows(text)
        except csv.Error as exc:
            raise VarConfigError(
                f"Invalid CSV in {path}: {exc}",
                advice="Use a name,value table.",
            ) from exc
        if not rows:
            return {}
        if rows[0] != ["name", "value"]:
            raise VarConfigError(
                f"{path} header must be name,value",
                advice="Use two columns named name and value.",
            )
        found: dict[str, str | list[str]] = {}
        for row in rows[1:]:
            if len(row) != 2:
                raise VarConfigError(
                    f"{path} rows must have two columns",
                    advice="Each data row is a name and a value.",
                )
            name, value = row
            current = found.get(name)
            if current is None:
                found[name] = value
                continue
            if isinstance(current, list):
                current.append(value)
                continue
            found[name] = [current, value]
        return found

    def _csv_rows(self, text: str) -> list[list[str]]:
        rows: list[list[str]] = []
        for row in csv.reader(io.StringIO(text)):
            if not any(cell.strip() for cell in row):
                continue
            rows.append([cell.strip() for cell in row])
        return rows


class VarPlan:
    """Facts, then default, kind, rule, and override assignments."""

    def __init__(
        self,
        environment: VarEnvironment,
        defaults: VarTable,
        rules: dict[str, VarTable],
        overrides: tuple[OverrideRule, ...],
        kinds: KindFiles,
        profile_scope: Mapping[str, Any],
    ) -> None:
        self._environment = environment
        self._defaults = defaults
        self._rules = rules
        self._overrides = overrides
        self._kinds = kinds
        self._profile_scope = dict(profile_scope)
        self._pdf: dict[str, tuple[str | None, str | None]] = {}

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
        profile_name: str,
        matcher: Matcher,
        root_dir: Path,
        profile_scope: Mapping[str, Any],
    ) -> VarPlan:
        """Load modules and var tables before any walk."""
        environment = VarEnvironment()
        section = cls._section(document)
        cls._load_modules(environment, section)
        cls._reject_reserved_groups(matcher)
        defaults = VarTable.parse(
            document.get(KEY_DEFAULT_VARS),
            label="default_vars",
            allows_kind=False,
            environment=environment,
        )
        rules = cls._rule_tables(document, profile_name, environment)
        overrides = cls._override_tables(document, environment)
        kinds = KindFiles.from_section(section, environment, root_dir, profile_scope)
        return cls(environment, defaults, rules, overrides, kinds, profile_scope)

    def resolve(self, file: InputFile, match: FileMatch, input_dir: Path) -> FileVars:
        """Resolve one matched file. Kind files use the rule kind, not an override."""
        self._require_metadata(file, match)
        scope: dict[str, str] = {}
        order: list[str] = []
        for key, value in self._fact_rows(file, match):
            scope[key] = value
            order.append(key)
        binding = FileBinding(file.absolute, file.sha256 or "", file.ctime or "", file.mtime or "")
        self._apply(self._defaults, scope, order, binding, match, file.path)
        kind_table = self._kinds.table_for(match.kind, input_dir)
        self._apply(kind_table, scope, order, binding, match, file.path)
        self._apply(self._rules.get(match.rule, VarTable.empty()), scope, order, binding, match, file.path)
        self._apply(self._override_for(file.path), scope, order, binding, match, file.path)
        items = tuple((key, scope[key]) for key in order if key in scope)
        return FileVars(scope[VAR_KIND], match.rule, items)

    def _apply(
        self,
        table: VarTable,
        scope: dict[str, str],
        order: list[str],
        binding: FileBinding,
        match: FileMatch,
        path: str,
    ) -> None:
        for key in table.keys:
            render_scope = dict(self._profile_scope)
            render_scope.update(scope)
            value = self._first(key, table.candidates[key], render_scope, binding, match, path)
            if value is None:
                scope.pop(key, None)
                order[:] = [item for item in order if item != key]
                continue
            scope[key] = value
            if key not in order:
                order.append(key)

    def _first(
        self,
        key: str,
        candidates: tuple[str, ...],
        scope: Mapping[str, Any],
        binding: FileBinding,
        match: FileMatch,
        path: str,
    ) -> str | None:
        misses: list[str] = []
        for source in candidates:
            try:
                rendered = self._environment.render(source, scope, binding, self._pdf)
            except VarCandidateError as exc:
                misses.append(str(exc))
                continue
            if key == VAR_DATE and not self._is_date(rendered):
                misses.append(f"{rendered!r} is not a YYYY-MM-DD date")
                continue
            return rendered
        if key == VAR_DATE:
            return None
        advice = misses[-1] if misses else "Add a candidate that renders to a string."
        raise VarResolveError(
            f"Profile {match.profile} input {match.index} path {path} variable {key} failed",
            advice=advice,
        )

    def _override_for(self, relative: str) -> VarTable:
        for rule in self._overrides:
            if rule.matches(relative):
                return rule.table
        return VarTable.empty()

    def _fact_rows(self, file: InputFile, match: FileMatch) -> list[tuple[str, str]]:
        ext = file.suffix[1:] if file.suffix.startswith(".") else file.suffix
        values = {
            VAR_KIND: match.kind,
            VAR_RULE_NAME: match.rule,
            VAR_CTIME: file.ctime or "",
            VAR_MTIME: file.mtime or "",
            VAR_FILE_HASH: file.sha256 or "",
            VAR_FILE_NAME: file.name,
            VAR_FILE_STEM: file.stem,
            VAR_FILE_EXT: ext,
            VAR_FILE_PATH: file.path,
            VAR_FILE_DIR: file.directory,
        }
        rows = [(name, values[name]) for name in INTERNAL_NAMES]
        rows.append((VAR_FILE_CTIME, values[VAR_CTIME]))
        rows.append((VAR_FILE_MTIME, values[VAR_MTIME]))
        seen = {name for name, _value in rows}
        for name, value in match.groups.items():
            if name in seen:
                continue
            rows.append((name, value))
        return rows

    def _require_metadata(self, file: InputFile, match: FileMatch) -> None:
        if file.ctime is None or file.mtime is None or file.sha256 is None:
            raise VarResolveError(
                f"Profile {match.profile} input {match.index} path {file.path} has no file metadata",
                advice="scan vars reads mtime, ctime, and sha256.",
            )

    def _is_date(self, text: str) -> bool:
        try:
            parsed = datetime.strptime(text, DATE_TEXT)
        except ValueError:
            return False
        return parsed.strftime(DATE_TEXT) == text

    @classmethod
    def _section(cls, document: Mapping[str, Any]) -> Mapping[str, Any]:
        section = document.get(CONFIG_SECTION)
        if section is None:
            return {}
        if not isinstance(section, dict):
            raise VarConfigError(
                "config must be a mapping",
                advice="Put profile settings under config:.",
            )
        return section

    @classmethod
    def _load_modules(cls, environment: VarEnvironment, section: Mapping[str, Any]) -> None:
        raw = section.get(KEY_VAR_MODULES)
        if raw is None or raw == []:
            return
        if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
            raise VarConfigError(
                "config.var_modules must be a list of module paths",
                advice="Use importable module names, such as my_package.supershelf_vars.",
            )
        for module_name in raw:
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                raise VarConfigError(
                    f"Cannot import var module {module_name!r}: {exc}",
                    advice="Install the package and check the module path.",
                ) from exc
            cls._register_exports(environment, module, VAR_GLOBALS, environment.add_global)
            cls._register_exports(environment, module, VAR_FILTERS, environment.add_filter)

    @classmethod
    def _register_exports(cls, environment: VarEnvironment, module: object, attr: str, add: Any) -> None:
        raw = getattr(module, attr, None)
        if raw is None:
            return
        if not isinstance(raw, dict):
            raise VarConfigError(
                f"{getattr(module, '__name__', module)}.{attr} must be a mapping",
                advice="Map command names to functions.",
            )
        for name, func in raw.items():
            if not isinstance(name, str):
                raise VarConfigError(
                    f"{attr} keys must be strings",
                    advice="Use the command name as the key.",
                )
            add(name, func)

    @classmethod
    def _reject_reserved_groups(cls, matcher: Matcher) -> None:
        for name in matcher.named_groups():
            if name.startswith("__"):
                raise VarConfigError(
                    f"Regex group {name!r} is reserved",
                    advice="Name regex groups without a __ prefix. Those names are reserved.",
                )

    @classmethod
    def _rule_tables(
        cls,
        document: Mapping[str, Any],
        profile_name: str,
        environment: VarEnvironment,
    ) -> dict[str, VarTable]:
        raw = document.get(KEY_MATCH_RULES)
        if raw is None:
            return {}
        if not isinstance(raw, list):
            raise VarConfigError(
                f"Profile {profile_name} match_rules must be a list",
                advice="Write match_rules as a list of rules.",
            )
        tables: dict[str, VarTable] = {}
        for index, item in enumerate(raw, start=1):
            spec = MatchRuleSpec.from_item(profile_name, index, item)
            name = spec.labels()[0]
            raw_vars = item.get(KEY_RULE_VARS) if isinstance(item, dict) else None
            tables[name] = VarTable.parse(
                raw_vars,
                label=f"match rule {name} vars",
                allows_kind=False,
                environment=environment,
            )
        return tables

    @classmethod
    def _override_tables(
        cls,
        document: Mapping[str, Any],
        environment: VarEnvironment,
    ) -> tuple[OverrideRule, ...]:
        raw = document.get(KEY_OVERRIDES)
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise VarConfigError(
                "overrides must be a list",
                advice="Each item has a path and a vars mapping.",
            )
        rules: list[OverrideRule] = []
        for index, item in enumerate(raw, start=1):
            rules.append(cls._one_override(item, index, environment))
        return tuple(rules)

    @classmethod
    def _one_override(cls, item: object, index: int, environment: VarEnvironment) -> OverrideRule:
        if not isinstance(item, dict):
            raise VarConfigError(
                f"overrides item {index} must be a mapping",
                advice="Set path and vars.",
            )
        path = item.get(KEY_OVERRIDE_PATH)
        if not isinstance(path, str) or not path.strip():
            raise VarConfigError(
                f"overrides item {index} needs a path",
                advice="Path is a glob matched against the path relative to the input.",
            )
        if KEY_RULE_VARS not in item:
            raise VarConfigError(
                f"overrides item {index} needs vars",
                advice="Set vars to a mapping. An empty mapping changes nothing.",
            )
        table = VarTable.parse(
            item.get(KEY_RULE_VARS),
            label=f"overrides item {index} vars",
            allows_kind=True,
            environment=environment,
        )
        return OverrideRule(path, table)
