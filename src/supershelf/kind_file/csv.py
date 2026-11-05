"""CSV kind-file reader and writer."""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Mapping
from pathlib import Path

from supershelf.constants import KIND_CSV_PATH, KIND_CSV_SHA
from supershelf.errors import VarConfigError
from supershelf.kind_file.format import KindFormat, KindParsed
from supershelf.kind_file.line import KindLine
from supershelf.kind_file.names import KindNames
from supershelf.vars.spec import check_assignment_key


class KindCsv(KindFormat):
    """Header, rows, column extend, and the SHA insert. The separator is the caller's."""

    def parse(
        self,
        path: Path,
        text: str,
        logger: logging.Logger,
        sep: str,
    ) -> KindParsed:
        """One data row per file. The header is checked by name and case."""
        try:
            parsed = [
                row
                for row in csv.reader(io.StringIO(text), delimiter=sep)
                if any(cell.strip() for cell in row)
            ]
        except csv.Error as exc:
            raise VarConfigError(
                f"Invalid CSV in {path}: {exc}",
                advice=self._header_advice(sep, ()),
            ) from exc
        if not parsed:
            raise VarConfigError(
                f"{path} header is empty",
                advice=self._header_advice(sep, ()),
            )
        header = tuple(cell.strip() for cell in parsed[0])
        self._check_header(path, header, sep)
        rows: dict[str, dict[str, str]] = {}
        raw_rows: list[KindLine] = []
        for raw in parsed[1:]:
            if len(raw) > len(header):
                raise VarConfigError(
                    f"{path} row has too many columns",
                    advice=self._header_advice(sep, header),
                )
            padded = list(raw) + [""] * (len(header) - len(raw))
            relative = ""
            sha_cell: str | None = None
            cells: dict[str, str] = {}
            for name, cell in zip(header, padded, strict=True):
                if name == KIND_CSV_PATH:
                    relative = cell
                    continue
                if name == KIND_CSV_SHA:
                    sha_cell = cell
                    continue
                text_cell = self._plain(cell)
                if text_cell is not None:
                    cells[name] = text_cell
            digest = ""
            if sha_cell is not None:
                text_sha = self._plain(sha_cell)
                if text_sha is not None:
                    digest = KindNames.check_sha(path, relative, text_sha)
            if KindNames.empty_path(relative):
                if cells or digest:
                    logger.info("%s has a row with an empty PATH", path)
                    raw_rows.append(KindLine(relative, digest, cells))
                continue
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
        return KindParsed(header, rows, raw_rows)

    def full_text(
        self,
        sep: str,
        columns: tuple[str, ...] | None,
        rows: list[KindLine],
    ) -> str:
        """Header plus every row. A missing header is filled from the cells."""
        if columns is None:
            columns = (
                KIND_CSV_PATH,
                KIND_CSV_SHA,
                *(name for line in rows for name in line.cells),
            )
            columns = tuple(dict.fromkeys(columns))
        return self._csv_rows(sep, columns, rows)

    def pending_text(
        self,
        sep: str,
        columns: tuple[str, ...],
        pending: list[tuple[str, str]],
        header: bool,
    ) -> str:
        """PATH and SHA only. Other columns are empty."""
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=sep, lineterminator="\n")
        if header:
            writer.writerow(columns)
        for relative, digest in pending:
            writer.writerow(
                [
                    relative
                    if name == KIND_CSV_PATH
                    else digest
                    if name == KIND_CSV_SHA
                    else ""
                    for name in columns
                ]
            )
        return buffer.getvalue()

    def extend_columns(
        self,
        text: str,
        sep: str,
        width: int,
        added: tuple[str, ...],
    ) -> str | None:
        """Append empty cells. Existing cell text stays on each line."""
        records = self._split_records(text)
        header_at = self._header_record(records, sep)
        if header_at is None:
            return None
        names = sep.join(added)
        updated: list[str] = []
        for index, (body, ending) in enumerate(records):
            if index == header_at:
                updated.append(f"{body}{sep}{names}{ending}")
                continue
            row = self._record_cells(body, sep)
            if row is None:
                updated.append(body + ending)
                continue
            missing = width + len(added) - len(row)
            if missing > 0:
                updated.append(f"{body}{sep * missing}{ending}")
                continue
            updated.append(body + ending)
        return "".join(updated)

    def insert_sha(
        self,
        text: str,
        sep: str,
        values: Mapping[str, str],
    ) -> tuple[str, list[str]]:
        """Insert SHA after the first field. The list is paths given a non-empty digest."""
        records = self._split_records(text)
        header_at = self._header_record(records, sep)
        filled: set[str] = set()
        remembered: list[str] = []
        updated: list[str] = []
        for index, (body, ending) in enumerate(records):
            if header_at is not None and index == header_at:
                updated.append(self._insert_after_first(body, sep, KIND_CSV_SHA) + ending)
                continue
            cells = self._record_cells(body, sep)
            if cells is None:
                updated.append(body + ending)
                continue
            relative = cells[0]
            value = ""
            if relative not in filled:
                value = values.get(relative, "")
                filled.add(relative)
                if value:
                    remembered.append(relative)
            updated.append(self._insert_after_first(body, sep, value) + ending)
        return "".join(updated), remembered

    def _csv_rows(self, sep: str, columns: tuple[str, ...], rows: list[KindLine]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=sep, lineterminator="\n")
        writer.writerow(columns)
        for line in rows:
            writer.writerow([self._csv_cell(line, name) for name in columns])
        return buffer.getvalue()

    @staticmethod
    def _csv_cell(line: KindLine, name: str) -> str:
        if name == KIND_CSV_PATH:
            return line.path
        if name == KIND_CSV_SHA:
            return line.sha
        return line.cells.get(name, "")

    @staticmethod
    def _split_records(text: str) -> list[tuple[str, str]]:
        """Split CSV text into records, keeping each body and its line ending."""
        records: list[tuple[str, str]] = []
        start = 0
        in_quotes = False
        index = 0
        length = len(text)
        while index < length:
            char = text[index]
            if char == '"':
                if in_quotes and index + 1 < length and text[index + 1] == '"':
                    index += 2
                    continue
                in_quotes = not in_quotes
                index += 1
                continue
            if not in_quotes and char in "\r\n":
                if char == "\r" and index + 1 < length and text[index + 1] == "\n":
                    ending = "\r\n"
                else:
                    ending = char
                records.append((text[start:index], ending))
                index += len(ending)
                start = index
                continue
            index += 1
        if start < length:
            records.append((text[start:], ""))
        return records

    def _header_record(self, records: list[tuple[str, str]], sep: str) -> int | None:
        for index, (body, _ending) in enumerate(records):
            if self._record_cells(body, sep) is not None:
                return index
        return None

    @staticmethod
    def _record_cells(body: str, sep: str) -> list[str] | None:
        if body.strip() == "":
            return None
        try:
            rows = list(csv.reader([body], delimiter=sep))
        except csv.Error:
            return None
        if len(rows) != 1 or not any(cell.strip() for cell in rows[0]):
            return None
        return rows[0]

    @staticmethod
    def _insert_after_first(body: str, sep: str, value: str) -> str:
        in_quotes = False
        index = 0
        while index < len(body):
            char = body[index]
            if char == '"':
                if in_quotes and index + 1 < len(body) and body[index + 1] == '"':
                    index += 2
                    continue
                in_quotes = not in_quotes
                index += 1
                continue
            if not in_quotes and char == sep:
                return f"{body[:index]}{sep}{value}{body[index:]}"
            index += 1
        return f"{body}{sep}{value}"

    def _check_header(self, path: Path, header: tuple[str, ...], sep: str) -> None:
        advice = self._header_advice(sep, header)
        if len(header) != len(set(header)):
            repeated = next(name for name in header if header.count(name) > 1)
            raise VarConfigError(
                f"{path} column {repeated!r} is repeated",
                advice=advice,
            )
        if not header or header[0] not in (KIND_CSV_SHA, KIND_CSV_PATH):
            found = header[0] if header else ""
            raise VarConfigError(
                f"{path} first column is {found!r}. The first column must be SHA or PATH.",
                advice=advice,
            )
        if header[0] == KIND_CSV_SHA and (len(header) < 2 or header[1] != KIND_CSV_PATH):
            found = header[1] if len(header) > 1 else ""
            raise VarConfigError(
                f"{path} second column is {found!r}. "
                "When the first column is SHA, the second column must be PATH.",
                advice=advice,
            )
        rest = header[2:] if header[0] == KIND_CSV_SHA else header[1:]
        for name in rest:
            if name == KIND_CSV_SHA:
                continue
            if name in KindNames._SHA_BAD:
                raise VarConfigError(
                    f"{path} column {name!r} is not the hash column. Use SHA.",
                    advice=advice,
                )
            if KindNames.is_feed_column(name):
                continue
            if KindNames._LOWER_NAME.fullmatch(name) is None:
                raise VarConfigError(
                    f"{path} column {name!r} must be lowercase.",
                    advice=advice,
                )
            check_assignment_key(name, str(path))

    def _header_advice(self, sep: str, columns: tuple[str, ...]) -> str:
        example = self._header_example(sep, columns)
        return (
            "The first column must be SHA or PATH. "
            "When SHA is first, PATH is second. "
            "When PATH is first, SHA may follow it. "
            "Other columns are lowercase names. "
            f"kind_overrides_sep is {sep!r}. For example: {example}"
        )

    @staticmethod
    def _header_example(sep: str, columns: tuple[str, ...]) -> str:
        names = [KIND_CSV_SHA, KIND_CSV_PATH]
        for name in columns:
            if name in KindNames._SHA_BAD or name == KIND_CSV_SHA or name == KIND_CSV_PATH:
                continue
            if KindNames.is_feed_column(name):
                continue
            lowered = name.lower()
            if (
                KindNames._LOWER_NAME.fullmatch(lowered)
                and lowered not in names
                and lowered not in {"path", "sha"}
            ):
                names.append(lowered)
        return sep.join(names)

    @staticmethod
    def _plain(cell: str) -> str | None:
        if cell.strip() == "":
            return None
        return cell


CSV = KindCsv()
