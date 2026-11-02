"""Supershelf command line."""

from clak import Argument, Command, LoggingOptMixin, Parser

from supershelf.cli.common import GlobalFlags, PackageVersion
from supershelf.cli.data import DataCommand
from supershelf.cli.output import OutputCommand
from supershelf.cli.profiles import ProfilesCommand
from supershelf.cli.record import RecordCommand
from supershelf.cli.scan import ScanCommand, present_sources, present_vars
from supershelf.cli.schema import SchemaCommand
from supershelf.constants import LOGGER_NAME

__all__ = [
    "App",
    "PackageVersion",
    "main",
    "present_sources",
    "present_vars",
]


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
