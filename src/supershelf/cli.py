"""Supershelf command line."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as package_version

from clak import Argument, Command, ListViewMixin, LoggingOptMixin, Parser
from clak.comp.views import CompositeViewMixin
from clak.views import CompositeView, ListView

from supershelf.configs import ShelfConfigs
from supershelf.data import ShowTable, run_feed, run_prune, run_show
from supershelf.constants import APP_NAME, LOGGER_NAME
from supershelf.domain_schema import DomainSchema
from supershelf.match import (
    DETAIL_NO_PATTERNS,
    STATUS_HIT,
    STATUS_MISS,
    STATUS_NOT_TRIED,
    STATUS_SKIPPED,
    FileInspection,
    PatternTrial,
)
from supershelf.output import OutputSession
from supershelf.record import RecordReader, RecordSession
from supershelf.runs import ShelfRuns
from supershelf.scan import InputFile
from supershelf.kind_file import KindOverrideMode
from supershelf.var_template import VarEnvironment
from supershelf.vars import FileVars


def kept_path() -> Argument:
    """Optional path shared by every scan subcommand."""
    return Argument(
        "path",
        nargs="?",
        default=None,
        help=(
            "Path relative to the input, as shown in the path column. "
            "Omit for every kept file. An exact file path selects that file. "
            "Anything else selects paths that start with it."
        ),
    )


class PackageVersion:
    """Distribution version printed by --version."""

    UNKNOWN = "unknown"

    @staticmethod
    def line() -> str:
        """`supershelf` plus the installed version, or `unknown`."""
        try:
            number = package_version(APP_NAME)
        except PackageNotFoundError:
            number = PackageVersion.UNKNOWN
        return f"{APP_NAME} {number}"


class GlobalFlags:
    """Flags shared by every command."""

    config = Argument(
        "--config",
        help="Config file or directory. Overrides SUPERSHELF_CONFIG.",
    )
    profile = Argument(
        "--profile",
        help="Comma-separated profile names. Overrides SUPERSHELF_PROFILES.",
    )
    dry_run = Argument(
        "--dry-run",
        action="store_true",
        help="Report actions without changing anything.",
    )


class ProfilesCommand(ListViewMixin, Parser):
    """List profile names and config paths."""

    def cli_run(self, config=None, profile=None, **_):
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        return [
            {
                "profile": item.profile,
                "type": item.type,
                "path": str(item.path),
            }
            for item in loaded.config_list
        ]


class ScanFilesCommand(ListViewMixin, Parser):
    """List files kept by each input."""

    path = kept_path()
    quick = Argument(
        "--quick",
        action="store_true",
        help="Skip mtime, ctime, and sha256.",
    )

    def cli_run(self, config=None, profile=None, path=None, quick=False, **_):
        runs = ShelfRuns.load(config, profile)
        rows = []
        groups = runs.scans(quick=bool(quick), path=path)
        for shelf, scans in zip(runs.shelves, groups, strict=True):
            for result in scans:
                for found in result.results:
                    row = {
                        "profile": result.profile,
                        "input": result.index,
                        "path": found.path,
                    }
                    if not quick:
                        row["mtime"] = shelf.show_time(found.mtime or "")
                        row["ctime"] = shelf.show_time(found.ctime or "")
                        row["sha256"] = found.sha256
                    rows.append(row)
        return rows


class ScanKindsCommand(ListViewMixin, Parser):
    """List the kind matched for each kept file."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, **_):
        runs = ShelfRuns.load(config, profile)
        prepared = runs.matched()
        groups = runs.scans(quick=True, path=path)
        rows = []
        for (_shelf, matcher), scans in zip(prepared, groups, strict=True):
            for result in scans:
                for found in matcher.collect(result):
                    rows.append(
                        {
                            "profile": found.profile,
                            "input": found.index,
                            "path": found.path,
                            "kind": found.kind,
                            "rule": found.rule,
                        }
                    )
        return rows


_STRUCTURED_FORMATS = frozenset({"json", "yaml"})


def _table_pairs(resolved: FileVars, *, show_all: bool = False) -> tuple[tuple[str, str], ...]:
    """Printed variables in table order: alphabetical by name."""
    visible = list(resolved.items)
    if show_all:
        visible.extend(resolved.facts.items())
    return tuple(sorted(visible))


def present_vars(resolved: FileVars, fmt: str | None, *, show_all: bool = False) -> object:
    """Table text, or the typed mapping for json and yaml."""
    if fmt in _STRUCTURED_FORMATS:
        return resolved.dump_vars(show_all=show_all)
    return "\n".join(
        f"{name}: {value}" for name, value in _table_pairs(resolved, show_all=show_all)
    )


def present_sources(resolved: FileVars, *, show_all: bool = False) -> str:
    """Source labels for the table, one line per name in present_vars order."""
    return "\n".join(
        ", ".join(resolved.source_labels(name))
        for name, _value in _table_pairs(resolved, show_all=show_all)
    )


class ScanVarsCommand(ListViewMixin, Parser):
    """List variables for each matched file."""

    path = kept_path()
    kind_overrides_mode = Argument(
        "--kind-overrides-mode",
        help="Kind file mode: auto, manual, always, or disabled.",
    )
    show_all = Argument(
        "--all",
        action="store_true",
        help="Include internal variables in the vars column.",
    )

    def cli_run(
        self,
        config=None,
        profile=None,
        path=None,
        dry_run=False,
        kind_overrides_mode=None,
        show_all=False,
        ctx=None,
        **_,
    ):
        fmt = ctx.view_settings.get("format") if ctx is not None else None
        if kind_overrides_mode is not None:
            KindOverrideMode.check(kind_overrides_mode, "--kind-overrides-mode")
        runs = ShelfRuns.load(config, profile)
        walk = runs.resolved(
            path,
            mode=kind_overrides_mode,
            dry_run=bool(dry_run),
        )
        rows = []
        for _shelf, _result, _found, matched, resolved, _plan in walk:
            presented = present_vars(resolved, fmt, show_all=bool(show_all))
            row = {
                "profile": matched.profile,
                "input": matched.index,
                "path": matched.path,
                "kind": resolved.kind,
                "rule": matched.rule,
                "vars": presented,
            }
            if isinstance(presented, str):
                row["sources"] = present_sources(resolved, show_all=bool(show_all))
            rows.append(row)
        for plan in walk.plans:
            plan.commit()
        return rows


class ScanInspectCommand(Parser):
    """Show how match rules test kept files."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, verbosity=0, **_):
        runs = ShelfRuns.load(config, profile)
        prepared = runs.matched()
        groups = runs.scans(quick=True, path=path)
        level = int(verbosity or 0)
        named = path is not None
        for (_shelf, matcher), scans in zip(prepared, groups, strict=True):
            for result in scans:
                for found in result.results:
                    self._show_inspection(
                        level,
                        result.profile,
                        result.index,
                        found,
                        matcher.explain(found),
                        named=named,
                    )
        return None

    def _show_inspection(
        self,
        verbosity: int,
        profile: str,
        index: int,
        file: InputFile,
        inspection: FileInspection,
        *,
        named: bool,
    ) -> None:
        prefix = f"profile {profile} input {index}"
        if not named:
            self._show_summary(prefix, file, inspection)
            return
        if verbosity >= 1:
            self._print(
                f"{prefix} path {file.path!r} directory {file.directory!r} "
                f"filename {file.name!r}"
            )
        for trial in inspection.trials:
            self._show_trial(verbosity, prefix, trial)
        if inspection.match is None:
            self._print(
                f"No match_rule for {file.path} in profile {profile} input {index}"
            )
            return
        self._print(
            f"Matched rule {inspection.match.rule} kind {inspection.match.kind} "
            f"for {file.path} in profile {profile} input {index}"
        )
        if verbosity < 1:
            return
        if inspection.match.groups:
            rendered = " ".join(
                f"{name}={value!r}" for name, value in inspection.match.groups.items()
            )
            self._print(f"{prefix} groups {rendered}")
        if any(trial.rule != inspection.match.rule for trial in inspection.trials):
            self._print(f"{prefix} stopped, later rules not tried")

    def _show_summary(
        self,
        prefix: str,
        file: InputFile,
        inspection: FileInspection,
    ) -> None:
        if inspection.match is None:
            self._print(f"miss {prefix} {file.path}")
            return
        self._print(
            f"match {prefix} {file.path} rule {inspection.match.rule} "
            f"kind {inspection.match.kind}"
        )

    def _show_trial(self, verbosity: int, prefix: str, trial: PatternTrial) -> None:
        if trial.status in (STATUS_HIT, STATUS_MISS):
            self._print(self._trial_line(prefix, trial))
            return
        if trial.status == STATUS_SKIPPED and verbosity >= 1:
            self._print(self._trial_line(prefix, trial))
            return
        if trial.status == STATUS_NOT_TRIED and verbosity >= 2:
            self._print(self._trial_line(prefix, trial))

    def _trial_line(self, prefix: str, trial: PatternTrial) -> str:
        if trial.detail == DETAIL_NO_PATTERNS:
            return f"{prefix} rule {trial.rule} {trial.field}: skipped, {trial.detail}"
        tail = trial.status
        if trial.status == STATUS_SKIPPED:
            tail = f"skipped, {trial.detail}"
        return (
            f"{prefix} rule {trial.rule} {trial.field} {trial.pattern!r} "
            f"against {trial.candidate!r}: {tail}"
        )

    @staticmethod
    def _print(line: str) -> None:
        print(line)


class SchemaCommand(Parser):
    """Print JSON Schema for declared variables and kinds."""

    def cli_run(self, config=None, profile=None, **_):
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        body = {}
        for item in loaded.config_list:
            environment = VarEnvironment()
            body[item.profile] = DomainSchema.load(
                item.config,
                compile_source=environment.compile_source,
            ).document()
        print(json.dumps(body, indent=2))


class ScanCommand(Parser):
    """Scan profile inputs."""

    files = Command(ScanFilesCommand, help="List files kept by each input")
    kinds = Command(ScanKindsCommand, help="List the kind matched for each kept file")
    vars = Command(ScanVarsCommand, help="List variables for each matched file")
    inspect = Command(ScanInspectCommand, help="Show how match rules test kept files")


class RecordIdentityFlag:
    """Link rule shared by the commands that compare a scan with the database."""

    record_identity = Argument(
        "--record-identity",
        help=(
            "Link rule for this run: a word or a comma-separated list. "
            "Does not override a match rule that set record_identity. "
            "Overrides SUPERSHELF_RECORD_IDENTITY and config.record_identity."
        ),
    )


class RecordStatusCommand(ListViewMixin, RecordIdentityFlag, Parser):
    """Compare matched files with the profile database."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, record_identity=None, **_):
        session = RecordSession.load(config, profile, record_identity)
        return session.status(path)


class RecordRunCommand(ListViewMixin, RecordIdentityFlag, Parser):
    """Record matched files into the profile database."""

    path = kept_path()

    def cli_run(
        self,
        config=None,
        profile=None,
        path=None,
        dry_run=False,
        record_identity=None,
        **_,
    ):
        session = RecordSession.load(config, profile, record_identity)
        return session.run(path, dry_run=bool(dry_run))


class RecordHistoryCommand(ListViewMixin, Parser):
    """Show recorded events."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, **_):
        return RecordReader.load(config, profile).history(path)


class RecordDuplicatesCommand(ListViewMixin, Parser):
    """List documents that share a hash."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, **_):
        return RecordReader.load(config, profile).duplicates(path)


class DataFeedCommand(Parser):
    """Fill empty kind-file cells with resolved values."""

    names = Argument(
        "names",
        nargs="?",
        default=None,
        help=(
            "Comma-separated kinds or var names. Spaces around commas are ignored. "
            "A name that is both needs --kind or --var."
        ),
    )
    kind = Argument(
        "--kind",
        help="Comma-separated kinds. Each selected kind enables its schema vars.",
    )
    var = Argument(
        "--var",
        help="Comma-separated var names. With --kind, only these vars are written.",
    )
    force = Argument(
        "--force",
        action="store_true",
        help="Write kind files without asking. Required when stdin is not a terminal.",
    )

    def cli_run(
        self,
        config=None,
        profile=None,
        names=None,
        kind=None,
        var=None,
        force=False,
        dry_run=False,
        verbosity=0,
        **_,
    ):
        run_feed(
            config,
            profile,
            names,
            kind=kind,
            var=var,
            force=bool(force),
            dry_run=bool(dry_run),
            verbosity=int(verbosity or 0),
        )


class DataPruneCommand(Parser):
    """Drop empty columns, unmatched rows, or every row in existing kind files."""

    empty_fields = Argument(
        "--empty-fields",
        action="store_true",
        help="Drop empty columns that are not in the schema. This is the default.",
    )
    missing = Argument(
        "--missing",
        action="store_true",
        help="Drop rows whose path is not matched as that kind. Documents stay.",
    )
    clear = Argument(
        "--clear",
        action="store_true",
        help="Remove every row. The kind file and the database stay.",
    )
    every = Argument(
        "--all",
        action="store_true",
        help="Run every purge, including --clear. The database stays.",
    )
    force = Argument(
        "--force",
        action="store_true",
        help="Write kind files without asking. Required when stdin is not a terminal.",
    )

    def cli_run(
        self,
        config=None,
        profile=None,
        empty_fields=False,
        missing=False,
        clear=False,
        every=False,
        force=False,
        dry_run=False,
        verbosity=0,
        **_,
    ):
        run_prune(
            config,
            profile,
            empty_fields=bool(empty_fields),
            missing=bool(missing),
            clear=bool(clear),
            every=bool(every),
            force=bool(force),
            dry_run=bool(dry_run),
            verbosity=int(verbosity or 0),
        )


class DataShowCommand(CompositeViewMixin, Parser):
    """Print live variable values, one table per profile and kind."""

    class Meta:
        view_format_scope = "all"

    kind = Argument(
        "kind",
        nargs="?",
        default=None,
        help="Kind to print. Omit for every kind that has a matched file.",
    )

    def cli_run(self, config=None, profile=None, kind=None, dry_run=False, **_):
        tables = run_show(config, profile, kind, dry_run=bool(dry_run))
        return _show_view(tables)


def _show_view(tables: tuple[ShowTable, ...]) -> CompositeView:
    sections = []
    for index, table in enumerate(tables):
        title = f"profile {table.profile} kind {table.kind}"
        if table.kind_file:
            title = f"{title} {table.kind_file}"
        sections.append(
            (
                f"{table.profile}-{table.kind}-{index}",
                ListView(list(table.rows)),
                {"title": title},
            )
        )
    return CompositeView(sections)


class DataCommand(Parser):
    """Read and write kind files."""

    feed = Command(DataFeedCommand, help="Fill empty kind-file cells with resolved values")
    prune = Command(
        DataPruneCommand,
        help="Drop empty columns, unmatched rows, or every row",
    )
    show = Command(
        DataShowCommand,
        help="Print live variable values, one table per profile and kind",
    )


class OutputPreviewCommand(ListViewMixin, Parser):
    """Print destinations without writing them."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, **_):
        return OutputSession.load(config, profile).preview(path)


class OutputRunCommand(ListViewMixin, Parser):
    """Write destinations and record the apply."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, dry_run=False, format=None, **_):
        rows, failed = OutputSession.load(config, profile).run(path, dry_run=bool(dry_run))
        if failed:
            if format:
                ListView().render(rows, format=format)
            else:
                ListView().render(rows)
            raise SystemExit(1)
        return rows


class OutputCommand(Parser):
    """Write destinations for recorded files."""

    preview = Command(OutputPreviewCommand, help="Print destinations without writing them")
    run = Command(OutputRunCommand, help="Write destinations and record the apply")


class RecordCommand(Parser):
    """Record matched files and read that history."""

    status = Command(
        RecordStatusCommand,
        help="Compare matched files with the profile database",
    )
    run = Command(RecordRunCommand, help="Record matched files into the profile database")
    history = Command(RecordHistoryCommand, help="Show recorded events")
    duplicates = Command(
        RecordDuplicatesCommand,
        help="List documents that share a hash",
    )


class App(LoggingOptMixin, GlobalFlags, Parser):
    """Load profiles, scan inputs, record matched files, write outputs, and edit kind files."""

    version = Argument(
        "--version",
        action="version",
        version=PackageVersion.line(),
        help="Print the installed version and exit.",
    )

    class Meta:
        app_name = LOGGER_NAME
        log_prefix = LOGGER_NAME
        log_levels = [
            [f"WARNING|{LOGGER_NAME}"],
            [f"INFO|{LOGGER_NAME}"],
            [f"DEBUG|{LOGGER_NAME}"],
            ["DEBUG|"],
        ]

    profiles = Command(ProfilesCommand, help="List profile names and config paths")
    schema = Command(
        SchemaCommand,
        help="Print JSON Schema for declared variables and kinds",
    )
    scan = Command(ScanCommand, help="Scan profile inputs")
    data = Command(DataCommand, help="Read and write kind files")
    record = Command(RecordCommand, help="Record matched files and read that history")
    output = Command(OutputCommand, help="Write destinations for recorded files")


def main() -> None:
    App()
