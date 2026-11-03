"""Resolve variables for one matched file."""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from supershelf.common import config_section
from supershelf.constants import (
    DATE_TEXT,
    FIELD_CTIME,
    FIELD_DATE_FORMAT,
    FIELD_DIR,
    FIELD_EXT,
    FIELD_HASH,
    FIELD_KIND,
    FIELD_MTIME,
    FIELD_NAME,
    FIELD_PATH,
    FIELD_RULE,
    FIELD_STEM,
    FILE_FIELDS,
    KEY_CACHE_FILE,
    KEY_DEFAULT_VARS,
    KEY_METADATA_DRIVER,
    KEY_VAR_MODULES,
    MATCH_FIELDS,
    SOURCE_DEFAULT,
    SOURCE_FACT,
    SOURCE_KIND,
    SOURCE_RULE,
    TYPE_DATE,
    VAR_CONFIG,
    VAR_FILE,
    VAR_FILTERS,
    VAR_GLOBALS,
    VAR_MATCH,
    VAR_PROFILE,
)
from supershelf.errors import VarCandidateError, VarConfigError, VarResolveError
from supershelf.kind_file import KindDateFormat, KindFiles, KindOverrideMode, KindRow
from supershelf.metadata.driver import MetadataFile
from supershelf.metadata.process import ProcessRunner
from supershelf.metadata.registry import MetadataRegistry
from supershelf.metadata.session import MetadataSession
from supershelf.scan.match import FileMatch, Matcher
from supershelf.scan.walk import InputFile
from supershelf.template.environment import VarEnvironment, is_template
from supershelf.template.render import ScopeObject, scope_field
from supershelf.vars.catalog import VarCatalog
from supershelf.vars.spec import (
    CastMiss,
    CastValue,
    VarState,
    cast_date_display,
    cast_value,
    check_assignment_key,
    layer_source,
    reserved_var_name,
)


class DateScope:
    """A `type: date` value in a Jinja scope. `str()` uses the profile date format."""

    def __init__(self, text: str, display_format: str = DATE_TEXT) -> None:
        parsed = datetime.strptime(text, DATE_TEXT)
        self._parsed = parsed
        self.Y = parsed.strftime("%Y")
        self.m = parsed.strftime("%m")
        self.d = parsed.strftime("%d")
        self._iso = parsed.strftime(DATE_TEXT)
        self._format = display_format.strip() or DATE_TEXT

    def __str__(self) -> str:
        try:
            return self._parsed.strftime(self._format)
        except (TypeError, ValueError):
            return self._iso

    def strftime(self, fmt: str) -> str:
        """Format with a `strftime` pattern, such as `%Y-%m`."""
        if not isinstance(fmt, str) or not fmt.strip():
            raise VarCandidateError("A date format must be a non-empty string")
        try:
            return self._parsed.strftime(fmt)
        except (TypeError, ValueError) as exc:
            raise VarCandidateError(f"Date format {fmt!r} is invalid") from exc


def _file_namespace(file: InputFile) -> dict[str, str]:
    values = {
        FIELD_NAME: file.name,
        FIELD_STEM: file.stem,
        FIELD_EXT: file.extension,
        FIELD_PATH: file.path,
        FIELD_DIR: file.directory,
        FIELD_HASH: (file.sha256 or "").lower(),
        FIELD_CTIME: file.ctime or "",
        FIELD_MTIME: file.mtime or "",
    }
    return {field: values[field] for field in FILE_FIELDS}


def _match_namespace(kind: str, rule: str) -> dict[str, str]:
    return {FIELD_KIND: kind, FIELD_RULE: rule}


def _fact_lines(file_ns: Mapping[str, str], match_ns: Mapping[str, str]) -> dict[str, str]:
    facts = {f"{VAR_FILE}.{field}": file_ns[field] for field in FILE_FIELDS}
    facts.update({f"{VAR_MATCH}.{field}": match_ns[field] for field in MATCH_FIELDS})
    return facts


def _render_value(display: str, date_format: str, *, date: bool) -> str | DateScope:
    if date:
        return DateScope(display, date_format)
    return display


class FileVars:
    """Resolved variables for one matched file."""

    def __init__(
        self,
        kind: str,
        rule: str,
        states: tuple[tuple[str, VarState], ...],
        facts: Mapping[str, str] | None = None,
        rule_layer: Mapping[str, str] | None = None,
    ) -> None:
        self.kind = kind
        self.rule = rule
        self.states = states
        self.facts = dict(facts or {})
        self.rule_layer = dict(rule_layer or {})

    @property
    def items(self) -> tuple[tuple[str, str], ...]:
        """Set variables in first-seen order. The value is the display string."""
        return tuple((name, state.display) for name, state in self.states)

    @property
    def sources(self) -> dict[str, tuple[str, ...]]:
        """Source labels for each set variable, in the order layers wrote it."""
        return {name: tuple(state.value_sources) for name, state in self.states}

    def source_labels(self, name: str) -> tuple[str, ...]:
        """Labels for one printed name. Namespace fields are facts."""
        if name in self.facts:
            return (SOURCE_FACT,)
        return self.sources[name]

    def dump_vars(self, *, show_all: bool = False) -> dict[str, Any]:
        """JSON-ready values. Floats can differ from their display spelling."""
        dumped = {name: state.model_dump(mode="json") for name, state in self.states}
        if show_all:
            for name, value in self.facts.items():
                dumped[name] = {"value": value, "value_sources": [SOURCE_FACT]}
        return dumped


class VarTable:
    """Ordered variable definitions. Each value is one or more candidates."""

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
            cls._check_key(key, label)
            items = cls._candidates(value, label, str(key))
            for item in items:
                environment.compile_source(item)
            keys.append(str(key))
            candidates[str(key)] = items
        return cls(tuple(keys), candidates)

    @classmethod
    def _check_key(cls, key: object, label: str) -> None:
        check_assignment_key(key, label)

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


class VarPlan:
    """Facts, then default, rule, and kind row assignments."""

    def __init__(
        self,
        environment: VarEnvironment,
        catalog: VarCatalog,
        rules: dict[str, VarTable],
        kinds: KindFiles,
        profile_scope: Mapping[str, Any],
        session: MetadataSession,
    ) -> None:
        self._environment = environment
        self._catalog = catalog
        self._rules = rules
        self._kinds = kinds
        self._profile_scope = dict(profile_scope)
        self._session = session

    @property
    def catalog(self) -> VarCatalog:
        """Schema and kind columns for this profile."""
        return self._catalog

    @property
    def kind_files(self) -> KindFiles:
        """Kind files for this profile. The feed writer commits them."""
        return self._kinds

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
        profile_name: str,
        matcher: Matcher,
        root_dir: Path,
        profile_scope: Mapping[str, Any],
        *,
        mode: str | None = None,
        dry_run: bool = False,
        environ: Mapping[str, str] | None = None,
        runner: ProcessRunner | None = None,
    ) -> VarPlan:
        """Load modules and var tables before any walk."""
        cls._reject_overrides(document)
        environment = VarEnvironment()
        section = cls._section(document)
        cls._reject_metadata_in_config(section)
        session = cls._metadata_session(
            document,
            profile_scope,
            environment,
            runner,
            dry_run,
        )
        chosen = KindOverrideMode.resolve(section, mode, os.environ if environ is None else environ)
        dates = KindDateFormat.from_section(section, profile_scope)
        cls._load_modules(environment, section)
        cls._reject_reserved_groups(matcher)
        defaults = VarTable.parse(
            document.get(KEY_DEFAULT_VARS),
            label="default_vars",
            environment=environment,
        )
        rules, rule_kinds = cls._rule_tables(matcher, environment)
        env = os.environ if environ is None else environ
        identity, default_identity = cls._kind_identity(document, profile_name, section, env)
        kinds = KindFiles.from_section(
            section,
            root_dir,
            profile_scope,
            chosen,
            dates,
            dry_run,
            identity,
            default_identity,
        )
        names: list[str] = list(defaults.keys)
        for table in rules.values():
            names.extend(table.keys)
        names.extend(matcher.named_groups())
        catalog = VarCatalog.load(
            document,
            compile_source=environment.compile_source,
            names=names,
        )
        kinds.bind_catalog(catalog)
        for rule_name, table in rules.items():
            cls._check_literals(
                catalog,
                table,
                f"match rule {rule_name} vars",
                rule_kinds[rule_name],
            )
        return cls(environment, catalog, rules, kinds, profile_scope, session)

    @staticmethod
    def _kind_identity(
        document: Mapping[str, Any],
        profile_name: str,
        section: Mapping[str, Any],
        environ: Mapping[str, str],
    ) -> tuple[dict[str, str], str]:
        """First record_identity step per rule. The record flag is not read."""
        from supershelf.record import RecordIdentity

        steps = RecordIdentity.resolve(section, None, environ)
        rules = RecordIdentity.rule_lists(document, profile_name, steps)
        return {name: item[0] for name, item in rules.items()}, steps[0]

    def resolve(self, file: InputFile, match: FileMatch, input_dir: Path) -> FileVars:
        """Resolve one matched file."""
        self._require_metadata(file, match)
        token = self._session.bind(MetadataFile.from_input(file))
        try:
            return self._resolve_bound(file, match, input_dir)
        finally:
            self._session.unbind(token)

    def _resolve_bound(self, file: InputFile, match: FileMatch, input_dir: Path) -> FileVars:
        file_ns = _file_namespace(file)
        match_ns = _match_namespace(match.kind, match.rule)
        scope: dict[str, str] = {}
        states: dict[str, VarState] = {}
        order: list[str] = []
        for name, value in match.groups.items():
            self._save_raw(name, value, SOURCE_FACT, scope, states, order, match, file.path)
        self._apply_defaults(scope, states, order, file_ns, match_ns, match.kind)
        self._apply(
            self._rules.get(match.rule, VarTable.empty()),
            layer_source(SOURCE_RULE, match.rule),
            scope,
            states,
            order,
            file_ns,
            match_ns,
            match.kind,
        )
        rule_layer = dict(scope)
        self._apply_cells(
            self._kinds.cells_for(match.kind, input_dir, file.path, match, file.sha256 or ""),
            scope,
            states,
            order,
            match,
            file.path,
        )
        self._require_mandatory(states, match, file.path)
        chosen = tuple(
            (key, states[key])
            for key in order
            if key in states and states[key].value is not None
        )
        return FileVars(
            match.kind,
            match.rule,
            chosen,
            _fact_lines(file_ns, match_ns),
            rule_layer,
        )

    @property
    def metadata(self) -> MetadataRegistry:
        """Drivers loaded for this profile."""
        return self._session.registry

    def snapshot(self, resolved: FileVars) -> str:
        """JSON object stored on a document. Identity columns are omitted."""
        body: dict[str, dict[str, object]] = {}
        for name, state in resolved.states:
            if reserved_var_name(name):
                continue
            if state.value is None:
                continue
            spec = self._catalog.effective(resolved.kind, name)
            body[name] = {
                "type": spec.type,
                "value": state.value,
                "display": state.display,
                "value_sources": list(state.value_sources),
            }
        return json.dumps(body, sort_keys=True, separators=(",", ":"))

    def compile(self, source: str) -> None:
        """Compile a template now so a syntax error fails before the walk."""
        self._environment.compile_source(source)

    def render_file(self, source: str, resolved: FileVars, file: InputFile) -> str:
        """Render one template with this file's display strings."""
        scope = {
            name: state.display
            for name, state in resolved.states
            if state.value is not None
        }
        return self._environment.render(
            source,
            self._render_scope(
                scope,
                _file_namespace(file),
                _match_namespace(resolved.kind, resolved.rule),
                resolved.kind,
            ),
        )

    def commit(self) -> None:
        """Create or append kind rows after every file in this plan has resolved."""
        self._kinds.commit()

    def _apply_cells(
        self,
        row: KindRow,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
        match: FileMatch,
        path: str,
    ) -> None:
        if row.path is None:
            return
        label = layer_source(SOURCE_KIND, row.path)
        for key, value in row.cells.items():
            self._save_raw(key, value, label, scope, states, order, match, path)

    def _apply_defaults(
        self,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
        file_ns: Mapping[str, str],
        match_ns: Mapping[str, str],
        kind: str,
    ) -> None:
        for key in self._catalog.names_for(kind):
            candidates = self._catalog.default_candidates(kind, key)
            if not candidates:
                continue
            cast = self._first(
                key,
                candidates,
                self._render_scope(scope, file_ns, match_ns, kind),
                kind,
            )
            if cast is None:
                continue
            self._save(key, cast, SOURCE_DEFAULT, scope, states, order)

    def _apply(
        self,
        table: VarTable,
        label: str,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
        file_ns: Mapping[str, str],
        match_ns: Mapping[str, str],
        kind: str,
    ) -> None:
        for key in table.keys:
            cast = self._first(
                key,
                table.candidates[key],
                self._render_scope(scope, file_ns, match_ns, kind),
                kind,
            )
            if cast is None:
                continue
            self._save(key, cast, label, scope, states, order)

    def _render_scope(
        self,
        scope: Mapping[str, str],
        file_ns: Mapping[str, str],
        match_ns: Mapping[str, str],
        kind: str,
    ) -> dict[str, Any]:
        """Profile names, file and match objects, then display strings written so far."""
        render_scope: dict[str, Any] = dict(self._profile_scope)
        render_scope[VAR_FILE] = ScopeObject(file_ns, FIELD_NAME)
        render_scope[VAR_MATCH] = ScopeObject(match_ns, FIELD_KIND)
        date_format = self._date_display_format()
        for name, value in scope.items():
            is_date = self._catalog.type_of(kind, name) == TYPE_DATE
            render_scope[name] = _render_value(value, date_format, date=is_date)
        return render_scope

    def _date_display_format(self) -> str:
        found = scope_field(self._profile_scope, VAR_CONFIG, FIELD_DATE_FORMAT)
        if isinstance(found, str) and found.strip():
            return found
        return DATE_TEXT

    def _first(
        self,
        key: str,
        candidates: tuple[object, ...],
        scope: Mapping[str, Any],
        kind: str,
    ) -> CastValue | None:
        spec = self._catalog.effective(kind, key)
        for source in candidates:
            try:
                if isinstance(source, str):
                    rendered = self._environment.render(source, scope)
                    cast = cast_value(spec, rendered, allow_typed=False)
                else:
                    cast = cast_value(spec, source, allow_typed=True)
            except VarCandidateError:
                continue
            except CastMiss:
                if spec.type != TYPE_DATE or not isinstance(source, str):
                    continue
                try:
                    cast = cast_date_display(rendered, self._date_display_format())
                except CastMiss:
                    continue
            return cast
        return None

    def _save(
        self,
        key: str,
        cast: CastValue,
        label: str,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
    ) -> None:
        state = states.get(key)
        if state is None:
            state = VarState()
            states[key] = state
        state.write(cast, label)
        scope[key] = cast.display
        if key not in order:
            order.append(key)

    def _save_raw(
        self,
        key: str,
        raw: str,
        label: str,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
        match: FileMatch,
        path: str,
    ) -> None:
        spec = self._catalog.effective(match.kind, key)
        try:
            cast = cast_value(spec, raw, allow_typed=False)
        except CastMiss as exc:
            raise self._failed(match, path, key, str(exc)) from exc
        self._save(key, cast, label, scope, states, order)

    def _require_mandatory(
        self,
        states: dict[str, VarState],
        match: FileMatch,
        path: str,
    ) -> None:
        for name in self._catalog.names_for(match.kind):
            spec = self._catalog.effective(match.kind, name)
            if not spec.mandatory:
                continue
            state = states.get(name)
            if state is None or state.value is None:
                reason = f"{name} is mandatory according the schema."
                raise VarResolveError(
                    f"Profile {match.profile} input {match.index} path {path} "
                    f"variable {name} failed: {reason}"
                )

    def _failed(self, match: FileMatch, path: str, key: str, advice: str) -> VarResolveError:
        return VarResolveError(
            f"Profile {match.profile} input {match.index} path {path} variable {key} failed",
            advice=advice,
        )

    def _require_metadata(self, file: InputFile, match: FileMatch) -> None:
        if file.ctime is None or file.mtime is None or file.sha256 is None:
            raise VarResolveError(
                f"Profile {match.profile} input {match.index} path {file.path} has no file metadata",
                advice="scan vars reads mtime, ctime, and sha256.",
            )

    @classmethod
    def _check_literals(
        cls,
        catalog: VarCatalog,
        table: VarTable,
        label: str,
        kind: str,
    ) -> None:
        """Cast non-template literals now. A miss is a config error, not a fallback."""
        for key in table.keys:
            spec = catalog.effective(kind, key)
            for item in table.candidates[key]:
                if is_template(item):
                    continue
                try:
                    cast_value(spec, item, allow_typed=False)
                except CastMiss as exc:
                    raise VarConfigError(
                        f"{label} key {key} cannot be cast",
                        advice=str(exc),
                    ) from exc

    @classmethod
    def _reject_metadata_in_config(cls, section: Mapping[str, Any]) -> None:
        if KEY_METADATA_DRIVER not in section:
            return
        raise VarConfigError(
            "config.metadata_driver is not a config key",
            advice="Move metadata_driver to the top level, next to default_vars.",
        )

    @classmethod
    def _metadata_session(
        cls,
        document: Mapping[str, Any],
        profile_scope: Mapping[str, Any],
        environment: VarEnvironment,
        runner: ProcessRunner | None,
        dry_run: bool,
    ) -> MetadataSession:
        tool = ProcessRunner() if runner is None else runner
        registry = MetadataRegistry.from_document(
            document.get(KEY_METADATA_DRIVER),
            cls._profile_dir(profile_scope),
            tool,
        )
        registry.require_available()
        session = MetadataSession(
            registry,
            tool,
            cache=cls._cache_file(profile_scope),
            dry_run=dry_run,
        )
        environment.bind_metadata(registry, session)
        return session

    @staticmethod
    def _profile_dir(profile_scope: Mapping[str, Any]) -> Path:
        raw = scope_field(profile_scope, VAR_PROFILE, FIELD_DIR)
        if not isinstance(raw, str) or not raw:
            return Path(".")
        return Path(raw)

    @staticmethod
    def _cache_file(profile_scope: Mapping[str, Any]) -> Path | None:
        raw = scope_field(profile_scope, VAR_CONFIG, KEY_CACHE_FILE)
        if not isinstance(raw, str) or not raw:
            return None
        return Path(raw)

    @classmethod
    def _section(cls, document: Mapping[str, Any]) -> Mapping[str, Any]:
        return config_section(
            document,
            error=VarConfigError,
            advice="Put profile settings under config:.",
        )

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
        matcher: Matcher,
        environment: VarEnvironment,
    ) -> tuple[dict[str, VarTable], dict[str, str]]:
        tables: dict[str, VarTable] = {}
        kinds: dict[str, str] = {}
        for name, kind, raw in matcher.rule_vars():
            tables[name] = VarTable.parse(
                raw,
                label=f"match rule {name} vars",
                environment=environment,
            )
            kinds[name] = kind
        return tables, kinds

    @classmethod
    def _reject_overrides(cls, document: Mapping[str, Any]) -> None:
        if "overrides" in document:
            raise VarConfigError(
                "overrides is not a profile key",
                advice="Per-file values belong in the kind file.",
            )
