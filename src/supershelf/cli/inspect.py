"""`supershelf inspect`."""

from __future__ import annotations

import json

from clak import Argument, Command, ListViewMixin, Parser

from supershelf.cli.common import kept_path
from supershelf.cli.scan import variable_rows
from supershelf.configs import ShelfConfigs
from supershelf.data import run_feed
from supershelf.domain_schema import DomainSchema
from supershelf.inspect_config import OUTPUT_FORMATS, InspectedConfig
from supershelf.scan.match import (
    DETAIL_NO_PATTERNS,
    STATUS_HIT,
    STATUS_MISS,
    STATUS_NOT_TRIED,
    STATUS_SKIPPED,
    FileInspection,
    PatternTrial,
)
from supershelf.scan.runs import ShelfRuns
from supershelf.scan.walk import InputFile
from supershelf.template.environment import VarEnvironment


class InspectConfigCommand(Parser):
    """Print the parsed config after profile init."""

    format = Argument(
        "--format",
        choices=OUTPUT_FORMATS,
        default=None,
        help="Output format. Default is the profile type, toml or yaml.",
    )

    def cli_run(self, config=None, profile=None, format=None, **_):
        inspected = InspectedConfig.load(
            config_option=config,
            profile_option=profile,
        )
        print(inspected.text(format), end="")


class InspectSchemaCommand(Parser):
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


class InspectScanFilesCommand(ListViewMixin, Parser):
    """Every kept file, including unchanged identity rows."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, **_):
        return ShelfRuns.load(config, profile).file_rows(path, changes_only=False)


class InspectScanKindsCommand(Parser):
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


class InspectScanVarsCommand(ListViewMixin, Parser):
    """Every matched file, including unchanged variables."""

    path = kept_path()
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
        show_all=False,
        ctx=None,
        **_,
    ):
        fmt = ctx.view_settings.get("format") if ctx is not None else None
        runs = ShelfRuns.load(config, profile)
        walk = runs.changed_resolves(path, dry_run=True, changes_only=False)
        return variable_rows(
            walk,
            fmt,
            show_all=bool(show_all),
            profiles=len(runs.shelves),
        )


class InspectScanFeedsCommand(ListViewMixin, Parser):
    """Every fed cell and every row a real feed would drop. Writes nothing."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, verbosity=0, **_):
        return run_feed(
            config,
            profile,
            path,
            dry_run=True,
            verbosity=int(verbosity or 0),
            changes_only=False,
        )


class InspectScanCommand(Parser):
    """Print the full plan for one scan step. Writes nothing."""

    files = Command(InspectScanFilesCommand, help="Every kept file, including unchanged")
    kinds = Command(InspectScanKindsCommand, help="Show how match rules test kept files")
    vars = Command(InspectScanVarsCommand, help="Every matched file, including unchanged vars")
    feeds = Command(
        InspectScanFeedsCommand,
        help="Every fed cell and every row a feed would drop",
    )


class InspectCommand(Parser):
    """Read config, schema, and scan plans. Writes nothing."""

    config = Command(
        InspectConfigCommand,
        help="Print the parsed config with early paths resolved",
    )
    schema = Command(
        InspectSchemaCommand,
        help="Print JSON Schema for declared variables and kinds",
    )
    scan = Command(InspectScanCommand, help="Print the full plan for one scan step")
