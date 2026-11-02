"""`supershelf inspect`."""

from __future__ import annotations

from clak import Argument, Command, Parser

from supershelf.inspect_config import OUTPUT_FORMATS, InspectedConfig


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


class InspectCommand(Parser):
    """Show how profile init read the config."""

    config = Command(
        InspectConfigCommand,
        help="Print the parsed config with early paths resolved",
    )
