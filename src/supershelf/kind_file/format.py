"""Shared kind-file read and write."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

from supershelf.constants import KIND_ROW_SHA
from supershelf.errors import VarConfigError
from supershelf.kind_file.line import KindLine
from supershelf.kind_file.names import KindNames
from supershelf.vars.spec import check_assignment_key


class KindParsed(NamedTuple):
    """Columns, the first row of each path, and every row in file order."""

    columns: tuple[str, ...] | None
    rows: dict[str, dict[str, str]]
    raw_rows: list[KindLine]


class KindFormat:
    """Read and write one kind-file suffix."""

    suffixes: tuple[str, ...] = ()

    def parse(
        self,
        path: Path,
        text: str,
        logger: logging.Logger,
        sep: str,
    ) -> KindParsed:
        """Rows from an existing file. `sep` is the CSV separator."""
        raise NotImplementedError

    def full_text(
        self,
        sep: str,
        columns: tuple[str, ...] | None,
        rows: list[KindLine],
    ) -> str:
        """Rewrite the whole file, including vars."""
        raise NotImplementedError

    def pending_text(
        self,
        sep: str,
        columns: tuple[str, ...],
        pending: list[tuple[str, str]],
        header: bool,
    ) -> str:
        """New rows for a create or an append. Other cells stay empty."""
        raise NotImplementedError


class KindMappingFormat(KindFormat):
    """TOML and YAML rows: path, sha, and a vars mapping."""

    def items(
        self,
        path: Path,
        items: list[object],
        logger: logging.Logger,
    ) -> KindParsed:
        """One mapping per row. The first path wins the lookup."""
        rows: dict[str, dict[str, str]] = {}
        raw_rows: list[KindLine] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise VarConfigError(
                    f"{path} item {index} must be a mapping",
                    advice="Set path, and vars when the row has values.",
                )
            relative = item.get("path")
            if not isinstance(relative, str) or relative.strip() == "":
                raise VarConfigError(
                    f"{path} item {index} needs a path",
                    advice="Path is the file relative to the input.",
                )
            digest = self._item_sha(path, relative, item.get(KIND_ROW_SHA))
            cells = self._vars(path, index, item.get("vars"))
            line = KindLine(relative, digest, cells if relative not in rows else dict(cells))
            raw_rows.append(line)
            if relative in rows:
                logger.warning(
                    "Kind file %s path %r is duplicated; keeping the first row",
                    path,
                    relative,
                )
                continue
            rows[relative] = line.cells
        return KindParsed(None, rows, raw_rows)

    def _vars(self, path: Path, index: int, raw: object) -> dict[str, str]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise VarConfigError(
                f"{path} item {index} vars must be a mapping",
                advice="Map variable names to text. Quote scalars such as dates.",
            )
        cells: dict[str, str] = {}
        label = f"{path} item {index} vars"
        for key, value in raw.items():
            if not KindNames.is_feed_column(str(key)):
                check_assignment_key(key, label)
            text = self._typed(value, label, str(key))
            if text is not None:
                cells[str(key)] = text
        return cells

    @staticmethod
    def _typed(value: object, label: str, key: str) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            if value.strip() == "":
                return None
            return value
        raise VarConfigError(
            f"{label} key {key} must be a string",
            advice="Quote scalars such as dates.",
        )

    @staticmethod
    def _item_sha(path: Path, relative: str, value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise VarConfigError(
                f"{path} path {relative} sha must be a string",
                advice="Quote the sha256.",
            )
        text = value.strip()
        if text == "":
            return ""
        return KindNames.check_sha(path, relative, text)
