"""TOML kind-file reader and writer."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from supershelf.errors import VarConfigError
from supershelf.kind_file.format import KindMappingFormat, KindParsed
from supershelf.kind_file.line import KindLine


class KindToml(KindMappingFormat):
    """[[rows]] tables. Each table has path, sha, and an optional vars table."""

    suffixes = (".toml",)

    def parse(
        self,
        path: Path,
        text: str,
        logger: logging.Logger,
        sep: str,
    ) -> KindParsed:
        """[[rows]] tables. `sep` is unused."""
        del sep
        try:
            raw = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise VarConfigError(
                f"Invalid TOML in {path}: {exc}",
                advice="Use [[rows]] tables with path and an optional vars table.",
            ) from exc
        if raw == {}:
            return KindParsed(None, {}, [])
        rows = raw.get("rows") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            raise VarConfigError(
                f"{path} must be [[rows]] tables",
                advice="Each table has path and an optional vars table.",
            )
        return self.items(path, rows, logger)

    def full_text(
        self,
        sep: str,
        columns: tuple[str, ...] | None,
        rows: list[KindLine],
    ) -> str:
        """One [[rows]] table per row, including vars."""
        del sep, columns
        return "".join(self._toml_row(line) for line in rows)

    def pending_text(
        self,
        sep: str,
        columns: tuple[str, ...],
        pending: list[tuple[str, str]],
        header: bool,
    ) -> str:
        """path and sha only. vars is omitted."""
        del sep, columns, header
        return "".join(self._pending_toml(relative, digest) for relative, digest in pending)

    def _toml_row(self, line: KindLine) -> str:
        lines = [f"[[rows]]\npath = {self._toml_string(line.path)}\n"]
        if line.sha:
            lines.append(f"sha = {self._toml_string(line.sha)}\n")
        if line.cells:
            lines.append("[rows.vars]\n")
            for key, value in line.cells.items():
                lines.append(f"{key} = {self._toml_string(value)}\n")
        return "".join(lines)

    def _pending_toml(self, relative: str, digest: str) -> str:
        lines = [f"[[rows]]\npath = {self._toml_string(relative)}\n"]
        if digest:
            lines.append(f"sha = {self._toml_string(digest)}\n")
        return "".join(lines)

    @staticmethod
    def _toml_string(value: str) -> str:
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'


TOML = KindToml()
