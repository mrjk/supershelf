"""Shared kind-file read and write."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

from supershelf.kind_file.line import KindLine


class KindParsed(NamedTuple):
    """Columns, the first row of each path, and every row in file order."""

    columns: tuple[str, ...] | None
    rows: dict[str, dict[str, str]]
    raw_rows: list[KindLine]


class KindFormat:
    """Read and write a CSV kind file."""

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
