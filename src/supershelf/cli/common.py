"""Flags and helpers shared by every command."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version

from clak import Argument

from supershelf.constants import APP_NAME


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
