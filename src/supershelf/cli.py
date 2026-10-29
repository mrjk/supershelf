"""Supershelf command line."""

from clak import Argument, Command, ListViewMixin, LoggingOptMixin, Parser

from supershelf.configs import ShelfConfigs
from supershelf.constants import LOGGER_NAME
from supershelf.match import Matcher
from supershelf.profile import ShelfProfile


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


class ScanCommand(Parser):
    """Scan profile inputs."""

    files = Command(ScanFilesCommand, help="List files kept by each input")
    kinds = Command(ScanKindsCommand, help="List the kind matched for each kept file")


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
