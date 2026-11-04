"""Fill documentation markers with CLI help and the version line.

The configuration tables stay hand-written. The profile models do not describe
the whole file, so this script does not emit a config schema or an API listing.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from supershelf.cli import App, PackageVersion
from supershelf.constants import APP_NAME

_MARKER = re.compile(
    r"<!-- extract: (?P<name>.+?) -->\n.*?<!-- /extract -->",
    re.DOTALL,
)


class DocExtract:
    """Replace `extract` markers in the content pages."""

    def __init__(self, content: Path) -> None:
        self.content = content
        self._blocks = self._texts()

    def run(self) -> None:
        """Rewrite every page that contains an extract marker."""
        pages = (
            self.content / "reference" / "cli.md",
            self.content / "quickstart" / "index.md",
            self.content / "about" / "index.md",
        )
        for path in pages:
            original = path.read_text(encoding="utf-8")
            updated = self._fill(path, original)
            if updated != original:
                path.write_text(updated, encoding="utf-8")

    def _fill(self, path: Path, text: str) -> str:
        seen: list[str] = []

        def replace(match: re.Match[str]) -> str:
            name = match.group("name").strip()
            seen.append(name)
            try:
                body = self._blocks[name]
            except KeyError as exc:
                raise SystemExit(f"{path} has an unknown extract marker {name!r}") from exc
            return (
                f"<!-- extract: {name} -->\n"
                f"```text\n{body.rstrip()}\n```\n"
                "<!-- /extract -->"
            )

        updated = _MARKER.sub(replace, text)
        missing = [name for name in self._expected(path) if name not in seen]
        if missing:
            raise SystemExit(f"{path} is missing extract markers: {', '.join(missing)}")
        return updated

    def _expected(self, path: Path) -> tuple[str, ...]:
        if path.name == "cli.md":
            return tuple(name for name in self._blocks if name.startswith("help"))
        return ("version",)

    @staticmethod
    def _texts() -> dict[str, str]:
        os.environ["COLUMNS"] = "80"
        commands = {
            "help": (),
            "help profiles": ("profiles",),
            "help schema": ("schema",),
            "help scan": ("scan",),
            "help scan files": ("scan", "files"),
            "help scan kinds": ("scan", "kinds"),
            "help scan vars": ("scan", "vars"),
            "help scan inspect": ("scan", "inspect"),
            "help output": ("output",),
            "help output preview": ("output", "preview"),
            "help output run": ("output", "run"),
        }
        blocks = {
            name: DocExtract._help(argv)
            for name, argv in commands.items()
        }
        blocks["version"] = PackageVersion.line() + "\n"
        return blocks

    @staticmethod
    def _help(argv: tuple[str, ...]) -> str:
        node = App(parse=False, proc_name=APP_NAME)
        for key in argv:
            node = node.children[key]
        return node.parser.format_help()


def main() -> None:
    content = Path(__file__).resolve().parent / "content"
    DocExtract(content).run()


if __name__ == "__main__":
    main()
