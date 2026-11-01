"""Supershelf command line."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as package_version

from clak import Argument, Command, ListViewMixin, LoggingOptMixin, Parser

from supershelf.configs import ShelfConfigs
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
from supershelf.record import RecordReader, RecordSession
from supershelf.runs import ShelfRuns
from supershelf.scan import InputFile
from supershelf.var_template import VarEnvironment
from supershelf.kind_file import KindOverrideMode


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
            presented = resolved.present(fmt, show_all=bool(show_all))
            row = {
                "profile": matched.profile,
                "input": matched.index,
                "path": matched.path,
                "kind": resolved.kind,
                "rule": matched.rule,
                "vars": presented,
            }
            if isinstance(presented, str):
                row["sources"] = resolved.present_sources(show_all=bool(show_all))
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
    """Load supershelf profiles, scan their inputs, and record matched files."""

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
    record = Command(RecordCommand, help="Record matched files and read that history")


def main() -> None:
    App()
