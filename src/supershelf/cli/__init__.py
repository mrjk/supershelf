"""Supershelf command line."""

from clak import Argument, Command, LoggingOptMixin, Parser

from supershelf.cli.common import GlobalFlags, PackageVersion
from supershelf.cli.db import DbCommand
from supershelf.cli.inspect import InspectCommand
from supershelf.cli.output import OutputCommand
from supershelf.cli.profiles import ProfilesCommand
from supershelf.cli.scan import ScanCommand, present_sources, present_vars
from supershelf.constants import LOGGER_NAME

__all__ = [
    "App",
    "PackageVersion",
    "main",
    "present_sources",
    "present_vars",
]


class App(LoggingOptMixin, GlobalFlags, Parser):
    """Load profiles, inspect config, scan inputs, and write outputs."""

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
            [f"NOTICE|{LOGGER_NAME}"],
            [f"INFO|{LOGGER_NAME}"],
            [f"DEBUG|{LOGGER_NAME}"],
            ["DEBUG|"],
        ]

    profiles = Command(ProfilesCommand, help="List profile names and config paths")
    inspect = Command(InspectCommand, help="Read config, schema, and scan plans")
    scan = Command(ScanCommand, help="Scan profile inputs")
    db = Command(DbCommand, help="Read or import the profile database")
    output = Command(OutputCommand, help="Write destinations for recorded files")


def main() -> None:
    App()
