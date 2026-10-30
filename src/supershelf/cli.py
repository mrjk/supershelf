"""Supershelf command line."""

from clak import Argument, Command, ListViewMixin, LoggingOptMixin, Parser

from supershelf.configs import ShelfConfigs
from supershelf.constants import LOGGER_NAME
from supershelf.errors import SupershelfError
from supershelf.match import (
    DETAIL_NO_PATTERNS,
    STATUS_HIT,
    STATUS_MISS,
    STATUS_NOT_TRIED,
    STATUS_SKIPPED,
    FileInspection,
    Matcher,
    PatternTrial,
)
from supershelf.profile import ShelfProfile
from supershelf.scan import InputFile
from supershelf.vars import VarPlan


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

    quick = Argument(
        "--quick",
        action="store_true",
        help="Skip mtime, ctime, and sha256.",
    )

    def cli_run(self, config=None, profile=None, quick=False, **_):
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        rows = []
        for item in loaded.config_list:
            shelf = ShelfProfile.from_config(item)
            for result in shelf.scan(quick=bool(quick)):
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

    def cli_run(self, config=None, profile=None, **_):
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        prepared = []
        for item in loaded.config_list:
            shelf = ShelfProfile.from_config(item)
            prepared.append(
                (shelf, Matcher.from_document(shelf.document, shelf.name))
            )
        rows = []
        for shelf, matcher in prepared:
            for result in shelf.scan(quick=True):
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

    def cli_run(self, config=None, profile=None, **_):
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        prepared = []
        for item in loaded.config_list:
            shelf = ShelfProfile.from_config(item)
            matcher = Matcher.from_document(shelf.document, shelf.name)
            prepared.append(
                (
                    shelf,
                    matcher,
                    VarPlan.from_document(
                        shelf.document,
                        shelf.name,
                        matcher,
                        shelf.root_dir,
                        shelf.scope,
                    ),
                )
            )
        rows = []
        for shelf, matcher, plan in prepared:
            for result in shelf.scan(quick=False):
                files = {found.path: found for found in result.results}
                for matched in matcher.collect(result):
                    resolved = plan.resolve(
                        files[matched.path],
                        matched,
                        result.config.path,
                    )
                    for name, value in resolved.items:
                        rows.append(
                            {
                                "profile": matched.profile,
                                "input": matched.index,
                                "path": matched.path,
                                "kind": resolved.kind,
                                "rule": matched.rule,
                                "var": name,
                                "value": value,
                            }
                        )
        return rows


class ScanInspectCommand(Parser):
    """Show how match rules test kept files."""

    path = Argument(
        "path",
        nargs="?",
        default=None,
        help="Relative path of one kept file. Omit to list match or miss only.",
    )

    def cli_run(self, config=None, profile=None, path=None, verbosity=0, **_):
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        prepared = []
        for item in loaded.config_list:
            shelf = ShelfProfile.from_config(item)
            prepared.append((shelf, Matcher.from_document(shelf.document, shelf.name)))
        level = int(verbosity or 0)
        seen = 0
        for shelf, matcher in prepared:
            for result in shelf.scan(quick=True):
                for found in result.results:
                    if path is not None and found.path != path:
                        continue
                    seen += 1
                    self._show_inspection(
                        level,
                        result.profile,
                        result.index,
                        found,
                        matcher.explain(found),
                        named=path is not None,
                    )
        if path is not None and seen == 0:
            raise SupershelfError(f"No kept file {path!r}")
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
            self._print(
                f"{prefix} rule {trial.rule} {trial.field} {trial.pattern!r} "
                f"against {trial.candidate!r}: {trial.status}"
            )
            return
        if trial.status == STATUS_SKIPPED and verbosity >= 1:
            self._show_skipped(prefix, trial)
            return
        if trial.status == STATUS_NOT_TRIED and verbosity >= 2:
            self._print(
                f"{prefix} rule {trial.rule} {trial.field} {trial.pattern!r} "
                f"against {trial.candidate!r}: not tried"
            )

    def _show_skipped(self, prefix: str, trial: PatternTrial) -> None:
        if trial.detail == DETAIL_NO_PATTERNS:
            self._print(
                f"{prefix} rule {trial.rule} {trial.field}: skipped, {trial.detail}"
            )
            return
        self._print(
            f"{prefix} rule {trial.rule} {trial.field} {trial.pattern!r} "
            f"against {trial.candidate!r}: skipped, {trial.detail}"
        )

    @staticmethod
    def _print(line: str) -> None:
        print(line)


class ScanCommand(Parser):
    """Scan profile inputs."""

    files = Command(ScanFilesCommand, help="List files kept by each input")
    kinds = Command(ScanKindsCommand, help="List the kind matched for each kept file")
    vars = Command(ScanVarsCommand, help="List variables for each matched file")
    inspect = Command(ScanInspectCommand, help="Show how match rules test kept files")


class App(LoggingOptMixin, GlobalFlags, Parser):
    """Load supershelf profiles and scan their inputs."""

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
    scan = Command(ScanCommand, help="Scan profile inputs")


def main() -> None:
    App()
