"""Plan and apply output drivers. The file driver is output_file."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from supershelf.constants import (
    KEY_OUTPUT_MODULES,
    KEY_OUTPUTS,
    STATUS_DUPLICATE,
    STATUS_REFRESH,
    STATUS_UNCHANGED,
)
from supershelf.database import EventRow, OutputPrevious, ShelfDatabase
from supershelf.errors import (
    OutputConfigError,
    OutputResolveError,
    VarCandidateError,
    VarConfigError,
    VarResolveError,
)
from supershelf.match import Matcher
from supershelf.profile import ShelfProfile
from supershelf.record import LinkedMatch, RecordSession
from supershelf.var_template import is_template
from supershelf.vars import VarPlan

STATUS_WRITE = "write"
STATUS_REPLACE = "replace"
STATUS_SKIP = "skip"
STATUS_CONFLICT = "conflict"
SHARED_KEYS = frozenset({"name", "driver", "kinds", "when"})
_PASSING = frozenset({STATUS_UNCHANGED, STATUS_REFRESH})
_APPLY = frozenset({STATUS_WRITE, STATUS_REPLACE})
_WHEN_TRUE = frozenset({"true", "yes", "1"})
_WHEN_FALSE = frozenset({"false", "no", "0"})


class WhenText:
    """Cast a when result to the boolean string `true` or `false`."""

    TRUE = "true"
    FALSE = "false"

    @staticmethod
    def cast(text: str) -> str | None:
        """`true`/`yes`/`1`, or `false`/`no`/`0`, or empty. Anything else is None."""
        token = text.strip().lower()
        if token == "" or token in _WHEN_FALSE:
            return WhenText.FALSE
        if token in _WHEN_TRUE:
            return WhenText.TRUE
        return None


@dataclass
class OutputAction:
    """One planned destination. The driver may store extra fields for apply."""

    profile: str
    input_index: int
    path: str
    output: str
    driver_name: str
    status: str
    operation: str
    when: str
    dest: str
    document_id: int | None = None
    source_hash: str = ""
    previous: OutputPrevious | None = None
    database: Path | None = None
    source: Path | None = None
    recorded_at: str = ""
    driver: OutputDriver | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def row(self) -> dict[str, object]:
        """One clak table row. Column order is the command contract."""
        return {
            "profile": self.profile,
            "input": self.input_index,
            "path": self.path,
            "output": self.output,
            "driver": self.driver_name,
            "status": self.status,
            "operation": self.operation,
            "when": self.when,
            "dest": self.dest,
        }


@dataclass
class OutputContext:
    """What a driver may read while planning one file. It does not write."""

    shelf: ShelfProfile
    match: LinkedMatch
    document_id: int
    events: list[EventRow]
    output_name: str
    driver_name: str
    driver: OutputDriver
    render: Callable[[str], str]

    def action(
        self,
        *,
        status: str,
        operation: str,
        dest: str,
        when: str = WhenText.TRUE,
        previous: OutputPrevious | None = None,
    ) -> OutputAction:
        """Fill the row columns the host owns. `dest` is blank when when is false."""
        return OutputAction(
            profile=self.shelf.name,
            input_index=self.match.row.file.input_index,
            path=self.match.found.path,
            output=self.output_name,
            driver_name=self.driver_name,
            status=status,
            operation=operation,
            when=when,
            dest=dest,
            document_id=self.document_id,
            source_hash=self.match.row.file.hash,
            previous=previous,
            database=self.shelf.database_file,
            source=self.match.found.absolute,
            driver=self.driver,
        )


class OutputDriver:
    """One kind of destination. Plugins subclass this."""

    name = ""

    def check(self, spec: Mapping[str, Any]) -> None:
        """Validate the item at load. A bad item raises OutputConfigError."""
        raise NotImplementedError

    def prepare(self, spec: Mapping[str, Any], profile: ShelfProfile) -> Any:
        """Render profile-scoped fields once. No file variables yet."""
        raise NotImplementedError

    def plan(self, prepared: Any, context: OutputContext) -> OutputAction | None:
        """Return one action, or None to add no row. Do not write or append."""
        raise NotImplementedError

    def apply(self, action: OutputAction, dry_run: bool = False) -> None:
        """Perform the action. `dry_run` true creates nothing and appends nothing."""
        raise NotImplementedError


@dataclass
class OutputItem:
    """One outputs entry after load. `prepared` belongs to the driver."""

    name: str
    driver_name: str
    kinds: list[str] | None
    when: str
    driver: OutputDriver
    prepared: Any


class OutputRegistry:
    """Driver instances for one profile. `file` is registered first."""

    def __init__(self) -> None:
        self._drivers: dict[str, OutputDriver] = {}

    def add(self, driver: OutputDriver, *, module: str | None = None) -> None:
        """Register a driver. A repeated name is a config error."""
        name = driver.name
        if not isinstance(name, str) or not name.strip():
            label = module or "output driver"
            raise OutputConfigError(
                f"{label} driver name is empty",
                advice="Set name on the OutputDriver subclass.",
            )
        if name in self._drivers:
            where = f" from {module}" if module else ""
            raise OutputConfigError(
                f"Output driver {name!r} is already registered{where}",
                advice="Use a different driver name. The built-in file driver cannot be replaced.",
            )
        self._drivers[name] = driver

    def get(self, name: str) -> OutputDriver:
        """The driver for this word, or a config error that names it."""
        found = self._drivers.get(name)
        if found is None:
            raise OutputConfigError(
                f"Output driver {name!r} is unknown",
                advice="Use file, or list the module in config.output_modules.",
            )
        return found


class OutputModules:
    """Load config.output_modules. This list is not var_modules."""

    @staticmethod
    def load(section: Mapping[str, Any], registry: OutputRegistry) -> None:
        """Register file, then each module's DRIVERS, in list order."""
        from supershelf.output_file import FileOutputDriver

        registry.add(FileOutputDriver())
        raw = section.get(KEY_OUTPUT_MODULES)
        if raw is None or raw == []:
            return
        if not isinstance(raw, list) or not all(
            isinstance(item, str) and item.strip() for item in raw
        ):
            raise OutputConfigError(
                "config.output_modules must be a list of module paths",
                advice="Use importable module names, such as my_package.supershelf_outputs.",
            )
        for module_name in raw:
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                raise OutputConfigError(
                    f"Cannot import output module {module_name!r}: {exc}",
                    advice="Install the package and check the module path.",
                ) from exc
            OutputModules._register(module, registry)

    @staticmethod
    def _register(module: object, registry: OutputRegistry) -> None:
        raw = getattr(module, "DRIVERS", None)
        label = getattr(module, "__name__", "output module")
        if not isinstance(raw, list) or not raw:
            raise OutputConfigError(
                f"Output module {label} has no DRIVERS",
                advice="Set DRIVERS to a list of OutputDriver subclasses.",
            )
        for item in raw:
            if not isinstance(item, type) or not issubclass(item, OutputDriver):
                raise OutputConfigError(
                    f"Output module {label} DRIVERS must be OutputDriver subclasses",
                    advice="Export the driver class, not an instance.",
                )
            registry.add(item(), module=str(label))


@dataclass
class OutputProfile:
    """The outputs list for one shelf, checked before the walk."""

    shelf: ShelfProfile
    items: list[OutputItem]

    @classmethod
    def load(cls, shelf: ShelfProfile) -> OutputProfile:
        """Read outputs and compile when and layout templates. Does not walk."""
        raw = shelf.document.get(KEY_OUTPUTS)
        if raw is None:
            raise OutputConfigError(
                f"Profile {shelf.name} outputs is not set",
                advice="Add an outputs list. scan, data, record, schema, and profiles ignore it.",
            )
        if raw == []:
            raise OutputConfigError(
                f"Profile {shelf.name} outputs is empty",
                advice="Add an output item, or remove the key.",
            )
        if not isinstance(raw, list):
            raise OutputConfigError(
                f"Profile {shelf.name} outputs must be a list",
                advice="Each item is a mapping with a name.",
            )
        section = ShelfProfile.config_section(shelf.document)
        registry = OutputRegistry()
        OutputModules.load(section, registry)
        items = [cls._item(shelf, spec, registry) for spec in raw]
        cls._unique(shelf.name, items)
        cls._compile(shelf, items)
        return cls(shelf, items)

    @staticmethod
    def _item(
        shelf: ShelfProfile,
        spec: object,
        registry: OutputRegistry,
    ) -> OutputItem:
        if not isinstance(spec, Mapping):
            raise OutputConfigError(
                f"Profile {shelf.name} output item must be a mapping",
                advice="Each outputs entry needs a name.",
            )
        name = OutputProfile._name(shelf.name, spec)
        driver_name = OutputProfile._driver_name(shelf.name, name, spec)
        try:
            driver = registry.get(driver_name)
        except OutputConfigError as exc:
            raise OutputConfigError(
                f"Profile {shelf.name} output {name!r} driver {driver_name!r} is unknown",
                advice=exc.advice,
            ) from exc
        kinds = OutputProfile._kinds(shelf.name, name, spec)
        when = OutputProfile._when(name, spec)
        driver.check(spec)
        prepared = driver.prepare(spec, shelf)
        return OutputItem(name, driver_name, kinds, when, driver, prepared)

    @staticmethod
    def _name(profile: str, spec: Mapping[str, Any]) -> str:
        name = spec.get("name")
        if not isinstance(name, str) or not name.strip():
            raise OutputConfigError(
                f"Profile {profile} output name is required",
                advice="Set name to a non-empty string. It must be unique in the profile.",
            )
        return name.strip()

    @staticmethod
    def _driver_name(profile: str, name: str, spec: Mapping[str, Any]) -> str:
        raw = spec.get("driver", "file")
        if raw is None:
            raw = "file"
        if not isinstance(raw, str) or not raw.strip():
            raise OutputConfigError(
                f"Profile {profile} output {name!r} driver must be a string",
                advice="Omit driver to use file.",
            )
        return raw.strip()

    @staticmethod
    def _kinds(profile: str, name: str, spec: Mapping[str, Any]) -> list[str] | None:
        raw = spec.get("kinds")
        if raw is None:
            return None
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise OutputConfigError(
                f"Profile {profile} output {name!r} kinds must be a list of strings",
                advice="Omit kinds to select every matched kind. An empty list selects nothing.",
            )
        return list(raw)

    @staticmethod
    def _when(name: str, spec: Mapping[str, Any]) -> str:
        raw = spec.get("when")
        if raw is None:
            return WhenText.TRUE
        if not isinstance(raw, str):
            raise OutputConfigError(
                f"Output {name!r} when must be a string",
                advice="Quote when. An unquoted YAML bool is not a string. Omit it to keep every file.",
            )
        if is_template(raw):
            return raw
        cast = WhenText.cast(raw)
        if cast is None:
            raise OutputConfigError(
                f"Output {name!r} when {raw!r} is not true or false",
                advice="Use true, false, yes, no, 1, 0, or a template.",
            )
        return cast

    @staticmethod
    def _unique(profile: str, items: list[OutputItem]) -> None:
        seen: set[str] = set()
        for item in items:
            if item.name in seen:
                raise OutputConfigError(
                    f"Profile {profile} output name {item.name!r} is repeated",
                    advice="Give each output its own name.",
                )
            seen.add(item.name)

    @staticmethod
    def _compile(shelf: ShelfProfile, items: list[OutputItem]) -> None:
        matcher = Matcher.from_document(shelf.document, shelf.name)
        plan = VarPlan.from_document(
            shelf.document,
            shelf.name,
            matcher,
            shelf.root_dir,
            shelf.scope,
            dry_run=True,
        )
        for item in items:
            OutputProfile._compile_one(plan, item.name, "when", item.when)
            layout = getattr(item.prepared, "layout", None)
            if isinstance(layout, str):
                OutputProfile._compile_one(plan, item.name, "layout", layout)

    @staticmethod
    def _compile_one(plan: VarPlan, name: str, label: str, source: str) -> None:
        if not is_template(source):
            return
        try:
            plan.compile(source)
        except VarConfigError as exc:
            raise OutputConfigError(
                f"Output {name!r} {label} {exc}",
                advice=exc.advice,
            ) from exc


class OutputSession:
    """preview and run for the selected profiles."""

    def __init__(self, session: RecordSession, profiles: list[OutputProfile]) -> None:
        self.session = session
        self.profiles = profiles

    @classmethod
    def load(
        cls,
        config: str | None,
        profile: str | None,
        identity_flag: str | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> OutputSession:
        """Check outputs before the walk. Identity uses the same rules as record."""
        session = RecordSession.load(config, profile, identity_flag, environ)
        profiles = [OutputProfile.load(run.shelf) for run in session.runs]
        return cls(session, profiles)

    def preview(self, path: str | None) -> list[dict[str, object]]:
        """Every selected row. Writes nothing. A conflict row is still exit 0."""
        actions = self._actions(path)
        return [action.row() for action in actions]

    def run(
        self,
        path: str | None,
        *,
        dry_run: bool,
    ) -> tuple[list[dict[str, object]], bool]:
        """Rows except unchanged. The bool is true when a conflict row stops the run."""
        actions = self._actions(path)
        failed = any(action.status == STATUS_CONFLICT for action in actions)
        if not dry_run and not failed:
            self._apply(actions)
        shown = [action for action in actions if action.status != STATUS_UNCHANGED]
        return [action.row() for action in shown], failed

    def _actions(self, path: str | None) -> list[OutputAction]:
        matches = self.session.sources(path)
        if path is not None and matches and all(
            match.row.status == STATUS_DUPLICATE for match in matches
        ):
            raise OutputResolveError(
                f"No output source for {path!r}",
                advice="The path matches a duplicate. Output writes the owning document.",
            )
        by_profile: dict[str, list[LinkedMatch]] = {}
        for match in matches:
            by_profile.setdefault(match.shelf.name, []).append(match)
        actions: list[OutputAction] = []
        for profile in self.profiles:
            actions.extend(self._profile(profile, by_profile.get(profile.shelf.name, [])))
        self._one_dest(actions)
        return actions

    def _profile(
        self,
        profile: OutputProfile,
        matches: list[LinkedMatch],
    ) -> list[OutputAction]:
        with ShelfDatabase.open_read(profile.shelf.database_file) as database:
            events = database.events()
        actions: list[OutputAction] = []
        for item in profile.items:
            for match in matches:
                planned = self._one(profile, item, match, events)
                if planned is not None:
                    actions.append(planned)
        return actions

    def _one(
        self,
        profile: OutputProfile,
        item: OutputItem,
        match: LinkedMatch,
        events: list[EventRow],
    ) -> OutputAction | None:
        if match.row.status == STATUS_DUPLICATE:
            return None
        if item.kinds is not None and match.resolved.kind not in item.kinds:
            return None
        when = self._when(item, match)
        operation = getattr(item.prepared, "operation", "")
        if not isinstance(operation, str):
            operation = ""
        if when == WhenText.FALSE:
            return OutputAction(
                profile=profile.shelf.name,
                input_index=match.row.file.input_index,
                path=match.found.path,
                output=item.name,
                driver_name=item.driver_name,
                status=STATUS_SKIP,
                operation=operation,
                when=WhenText.FALSE,
                dest="",
            )
        if match.row.status not in _PASSING:
            raise OutputResolveError(
                f"Profile {profile.shelf.name} input {match.row.file.input_index} "
                f"{match.found.path} is {match.row.status}",
                advice="Run record run.",
            )
        document_id = match.row.document_id
        if document_id is None:
            raise OutputResolveError(
                f"Profile {profile.shelf.name} input {match.row.file.input_index} "
                f"{match.found.path} is {match.row.status}",
                advice="Run record run.",
            )
        context = OutputContext(
            shelf=profile.shelf,
            match=match,
            document_id=document_id,
            events=events,
            output_name=item.name,
            driver_name=item.driver_name,
            driver=item.driver,
            render=lambda source, match=match: match.var_plan.render_file(
                source,
                match.resolved,
                match.found,
            ),
        )
        return item.driver.plan(item.prepared, context)

    def _when(self, item: OutputItem, match: LinkedMatch) -> str:
        if not is_template(item.when):
            return item.when
        try:
            rendered = match.var_plan.render_file(item.when, match.resolved, match.found)
        except VarCandidateError as exc:
            raise OutputResolveError(
                f"Output {item.name} {match.found.path} when failed: {exc}",
                advice="Set when to a template that renders true or false.",
            ) from exc
        except VarResolveError as exc:
            raise OutputResolveError(str(exc), advice=exc.advice) from exc
        cast = WhenText.cast(rendered)
        if cast is None:
            raise OutputResolveError(
                f"Output {item.name} {match.found.path} when rendered {rendered!r}",
                advice="Use true, false, yes, no, 1, or 0.",
            )
        return cast

    @staticmethod
    def _one_dest(actions: list[OutputAction]) -> None:
        seen: dict[str, OutputAction] = {}
        for action in actions:
            if not action.dest:
                continue
            other = seen.get(action.dest)
            if other is not None:
                raise OutputResolveError(
                    f"Destination {action.dest} is planned for {other.profile} {other.path} "
                    f"output {other.output} and {action.profile} {action.path} output {action.output}",
                    advice="Use a layout that gives each file its own destination.",
                )
            seen[action.dest] = action

    @staticmethod
    def _apply(actions: list[OutputAction]) -> None:
        stamp = datetime.now(timezone.utc).isoformat()
        for action in actions:
            if action.status not in _APPLY:
                continue
            if action.driver is None:
                raise OutputResolveError(
                    f"Output {action.output} has no driver",
                    advice="This is a bug. Report it.",
                )
            action.recorded_at = stamp
            action.driver.apply(action, False)
