"""Kind files: mode, date format, and the csv, toml, and yaml rows."""

from __future__ import annotations

import csv
import io
import logging
import re
import tomllib
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast

import yaml

from supershelf.common import WordChoice, render_user_path
from supershelf.constants import (
    DATE_TEXT,
    ENV_KIND_OVERRIDES_MODE,
    KEY_DEFAULT_DATE_FORMAT,
    KEY_KIND_OVERRIDES,
    KEY_KIND_OVERRIDES_DATE_FORMAT,
    KEY_KIND_OVERRIDES_MODE,
    KEY_KIND_OVERRIDES_SEP,
    KIND_CSV_PATH,
    KIND_MODE_ALWAYS,
    KIND_MODE_AUTO,
    KIND_MODE_DISABLED,
    KIND_MODE_MANUAL,
    KIND_OVERRIDE_MODES,
    FIELD_DATE_FORMAT,
    FIELD_KIND,
    FIELD_PATH,
    LOGGER_NAME,
    VAR_CONFIG,
    VAR_DATE,
    VAR_INPUT,
    VAR_MATCH,
)
from supershelf.defaults import PACKAGED
from supershelf.errors import VarConfigError, VarResolveError
from supershelf.match import FileMatch
from supershelf.template import ScopeObject, scope_field
from supershelf.var_schema import VarCatalog, check_assignment_key


KindMode = Literal[
    KIND_MODE_AUTO,
    KIND_MODE_MANUAL,
    KIND_MODE_ALWAYS,
    KIND_MODE_DISABLED,
]


class KindOverrideMode(WordChoice):
    """auto, manual, always, or disabled. The flag wins, then the env var, then config."""

    words = KIND_OVERRIDE_MODES
    flag_name = "--kind-overrides-mode"
    env_name = ENV_KIND_OVERRIDES_MODE
    config_key = KEY_KIND_OVERRIDES_MODE
    config_label = "config.kind_overrides_mode"
    requirement = "{label} must be auto, manual, always, or disabled"
    advice = "Use one of those four words, in lower case."
    error = VarConfigError

    @classmethod
    def packaged(cls) -> str:
        return PACKAGED.kind_overrides_mode

    @classmethod
    def resolve(
        cls,
        section: Mapping[str, Any],
        flag: str | None,
        environ: Mapping[str, str],
    ) -> KindMode:
        """Flag, then environment, then config. The result is one of the four words."""
        return cast(KindMode, super().resolve(section, flag, environ))


class KindDateFormat:
    """strptime format for a kind-file __date__ cell. The stored value is YYYY-MM-DD."""

    _YEAR = re.compile(r"%(?:Y|y)")
    _MONTH = re.compile(r"%(?:m|b|B)")
    _DAY = re.compile(r"%d")

    def __init__(self, text: str) -> None:
        self.text = text

    @classmethod
    def from_section(
        cls,
        section: Mapping[str, Any],
        profile_scope: Mapping[str, Any],
    ) -> KindDateFormat:
        """Check the format before the walk. Omitted uses default_date_format."""
        kind_raw = section.get(KEY_KIND_OVERRIDES_DATE_FORMAT)
        if kind_raw is not None:
            raw = kind_raw
            label = "config.kind_overrides_date_format"
        else:
            user_raw = section.get(KEY_DEFAULT_DATE_FORMAT)
            if user_raw is not None:
                raw = user_raw
                label = "config.default_date_format"
            else:
                scoped = scope_field(profile_scope, VAR_CONFIG, FIELD_DATE_FORMAT)
                raw = PACKAGED.default_date_format if scoped is None else scoped
                label = "config.default_date_format"
        if not isinstance(raw, str) or not raw.strip():
            raise VarConfigError(
                f"{label} must be a non-empty string",
                advice="Use a strptime format with a year, a month, and a day.",
            )
        fmt = cls(raw)
        fmt._check(label)
        return fmt

    def store(self, cell: str) -> str:
        """Strip the cell, parse the whole string, and drop any time."""
        try:
            parsed = datetime.strptime(cell.strip(), self.text)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return parsed.strftime(DATE_TEXT)

    def _is_calendar(self) -> bool:
        return (
            self._YEAR.search(self.text) is not None
            and self._MONTH.search(self.text) is not None
            and self._DAY.search(self.text) is not None
        )

    def _check(self, label: str) -> None:
        if not self._is_calendar():
            raise VarConfigError(
                f"{label} must include a year, a month, and a day",
                advice="Use a strptime format such as %Y-%m-%d or %d/%m/%Y.",
            )
        try:
            sample = datetime(2000, 1, 2, 3, 4, 5).strftime(self.text)
            datetime.strptime(sample, self.text)
        except ValueError as exc:
            raise VarConfigError(
                f"{label} is not a strptime format",
                advice="Use directives such as %Y, %m, and %d.",
            ) from exc

    def show(self, stored: str) -> str:
        """Write a stored YYYY-MM-DD value with this kind-file format."""
        try:
            parsed = datetime.strptime(stored.strip(), DATE_TEXT)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return parsed.strftime(self.text)


class KindCsvSep:
    """One-character separator for a kind-file CSV. Omitted means a comma."""

    def __init__(self, text: str) -> None:
        self.text = text

    @classmethod
    def from_section(cls, section: Mapping[str, Any]) -> KindCsvSep:
        """Check the separator before the walk. Omitted uses a comma."""
        raw = section.get(KEY_KIND_OVERRIDES_SEP)
        if raw is None:
            return cls(PACKAGED.kind_overrides_sep)
        label = "config.kind_overrides_sep"
        if not isinstance(raw, str) or len(raw) != 1:
            raise VarConfigError(
                f"{label} must be one character",
                advice="Use a comma or a semicolon. For example: ';'",
            )
        if raw.isalnum() or raw == "_" or raw.isspace() or raw in {'"', "'", "/", "\\"}:
            raise VarConfigError(
                f"{label} {raw!r} cannot separate columns",
                advice="Use a comma or a semicolon. For example: ','",
            )
        return cls(raw)


class KindTable:
    """One kind file. Rows are literal cells keyed by the relative path."""

    _SUFFIXES = (".csv", ".toml", ".yaml", ".yml")
    _FRESH_COLUMNS = (KIND_CSV_PATH, VAR_DATE)
    _LOWER_NAME = re.compile(r"[a-z_][a-z0-9_]*\Z")
    _DATE_ALIASES = frozenset({"DATE", "Date", "date"})
    _SHA_ALIASES = frozenset({"SHA", "sha", "Sha"})

    def __init__(
        self,
        path: Path,
        suffix: str,
        columns: tuple[str, ...] | None,
        rows: dict[str, dict[str, str]],
        sep: str,
        *,
        blank: bool = False,
        missing: bool = False,
        raw_rows: list[tuple[str, dict[str, str]]] | None = None,
        bom: bool = False,
    ) -> None:
        self.path = path
        self.suffix = suffix
        self.columns = columns
        self.rows = rows
        self.sep = sep
        self.blank = blank
        self.missing = missing
        self.raw_rows = [] if raw_rows is None else raw_rows
        self._bom = bom
        self._pending: list[str] = []
        self._pending_seen: set[str] = set()
        self._extra_columns: list[str] = []

    @classmethod
    def missing(cls, path: Path, sep: str) -> KindTable:
        """A file that always mode will create from the first template."""
        suffix = cls._suffix(path)
        return cls(path, suffix, None, {}, sep, missing=True)

    @classmethod
    def read(cls, path: Path, logger: logging.Logger, sep: str) -> KindTable:
        """Parse an existing file. An empty file is an empty table."""
        suffix = cls._suffix(path)
        payload = path.read_bytes()
        bom = payload.startswith(b"\xef\xbb\xbf")
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise VarConfigError(
                f"{path} is not UTF-8",
                advice="Save the kind file as UTF-8.",
            ) from exc
        if text.strip() == "":
            return cls(path, suffix, None, {}, sep, blank=True, bom=bom)
        if suffix == ".csv":
            columns, rows, raw_rows = cls._parse_csv(path, text, logger, sep)
            return cls(path, suffix, columns, rows, sep, raw_rows=raw_rows, bom=bom)
        if suffix == ".toml":
            rows, raw_rows = cls._parse_toml(path, text, logger)
            return cls(path, suffix, None, rows, sep, raw_rows=raw_rows, bom=bom)
        rows, raw_rows = cls._parse_yaml(path, text, logger)
        return cls(path, suffix, None, rows, sep, raw_rows=raw_rows, bom=bom)

    def ensure(self, relative: str) -> None:
        """Remember a matched path that is not already a row."""
        if relative in self.rows or relative in self._pending_seen:
            return
        self._pending.append(relative)
        self._pending_seen.add(relative)

    def add_schema_columns(self, names: tuple[str, ...]) -> None:
        """Remember schema columns this CSV does not already have."""
        if self.suffix != ".csv":
            return
        present = set(self.columns or ())
        present.update(self._extra_columns)
        for name in names:
            if name in present or not self._legal_column(name):
                continue
            self._extra_columns.append(name)
            present.add(name)

    def sync_schema_columns(self, dry_run: bool, logger: logging.Logger) -> None:
        """Append missing schema columns on the right of an existing CSV."""
        if self.suffix != ".csv" or not self._extra_columns:
            return
        if self.missing or self.blank or self.columns is None:
            return
        added = ", ".join(self._extra_columns)
        if dry_run:
            logger.info("Would add columns %s to kind file %s", added, self.path)
            return
        if self._extend_columns():
            logger.debug("Added columns %s to kind file %s", added, self.path)

    def commit(self, dry_run: bool, logger: logging.Logger) -> None:
        """Create or append after the run. A dry run only logs a real change."""
        if not self._pending:
            return
        count = len(self._pending)
        if dry_run:
            if self.missing:
                logger.info("Would create kind file %s with %s rows", self.path, count)
                return
            logger.info("Would append %s rows to kind file %s", count, self.path)
            return
        if self.missing or self.blank:
            self._write_new()
            return
        self._append()

    def _create_columns(self) -> tuple[str, ...]:
        if self.suffix == ".csv" and self._extra_columns:
            return (KIND_CSV_PATH, *self._extra_columns)
        return self._FRESH_COLUMNS

    def _write_new(self) -> None:
        self._require_parent()
        self.path.write_text(
            self._rendered(self._create_columns(), header=True),
            encoding="utf-8",
        )

    def _extend_columns(self) -> bool:
        """Append empty cells. Existing cell text stays on each line."""
        added = tuple(self._extra_columns)
        raw = self.path.read_bytes()
        bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        text = raw.decode("utf-8-sig")
        records = self._split_records(text)
        header_at = self._header_record(records)
        if header_at is None:
            return False
        width = len(self.columns or ())
        names = self.sep.join(added)
        updated: list[str] = []
        for index, (body, ending) in enumerate(records):
            if index == header_at:
                updated.append(f"{body}{self.sep}{names}{ending}")
                continue
            row = self._record_cells(body)
            if row is None:
                updated.append(body + ending)
                continue
            missing = width + len(added) - len(row)
            if missing > 0:
                updated.append(f"{body}{self.sep * missing}{ending}")
                continue
            updated.append(body + ending)
        self.path.write_bytes(bom + "".join(updated).encode("utf-8"))
        self.columns = tuple(self.columns or ()) + added
        self._extra_columns.clear()
        return True

    @classmethod
    def _split_records(cls, text: str) -> list[tuple[str, str]]:
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

    def _header_record(self, records: list[tuple[str, str]]) -> int | None:
        for index, (body, _ending) in enumerate(records):
            if self._record_cells(body) is not None:
                return index
        return None

    def _record_cells(self, body: str) -> list[str] | None:
        if body.strip() == "":
            return None
        try:
            rows = list(csv.reader([body], delimiter=self.sep))
        except csv.Error:
            return None
        if len(rows) != 1 or not any(cell.strip() for cell in rows[0]):
            return None
        return rows[0]

    def accepts_name(self, name: str) -> bool:
        """CSV rejects a column that is not a legal header name."""
        if self.suffix != ".csv":
            return True
        return self._legal_column(name)

    @classmethod
    def _legal_column(cls, name: str) -> bool:
        if name == KIND_CSV_PATH or name in cls._SHA_ALIASES or name in cls._DATE_ALIASES:
            return False
        if cls._LOWER_NAME.fullmatch(name) is None:
            return False
        if name == VAR_DATE:
            return True
        try:
            check_assignment_key(name, "kind file")
        except VarConfigError:
            return False
        return True

    def set_cell(self, relative: str, name: str, value: str) -> bool:
        """Set one cell on the first row. An illegal CSV column is refused."""
        if value.strip() == "":
            return False
        if not self.accepts_name(name):
            return False
        row = self.rows.get(relative)
        if row is None:
            row = {}
            self.rows[relative] = row
        row[name] = value
        if self.suffix == ".csv":
            if self.columns is None:
                self.columns = (KIND_CSV_PATH,)
            if name not in self.columns:
                self.columns = (*self.columns, name)
        return True

    def drop_column(self, name: str) -> None:
        """Remove one column or key from every row, including a later duplicate."""
        if self.columns is not None:
            self.columns = tuple(item for item in self.columns if item != name)
        for cells in self.rows.values():
            cells.pop(name, None)
        self.raw_rows = [
            (path, {key: item for key, item in cells.items() if key != name})
            for path, cells in self.raw_rows
        ]

    def drop_paths(self, paths: set[str]) -> None:
        """Drop every row for these relative paths, including later duplicates."""
        for path in paths:
            self.rows.pop(path, None)
        self.raw_rows = [(path, cells) for path, cells in self.raw_rows if path not in paths]

    def clear_rows(self) -> None:
        """Remove every data row. A CSV header stays on the table."""
        self.rows.clear()
        self.raw_rows.clear()

    def column_filled(self, name: str) -> bool:
        """True when any raw row, including a later duplicate, has this cell."""
        for cells in self.rows.values():
            if cells.get(name, "").strip():
                return True
        for _path, cells in self.raw_rows:
            if cells.get(name, "").strip():
                return True
        return False

    def data_columns(self) -> tuple[str, ...]:
        """CSV header names after PATH, or TOML and YAML keys in file order."""
        if self.suffix == ".csv":
            return tuple(name for name in (self.columns or ()) if name != KIND_CSV_PATH)
        names: list[str] = []
        seen: set[str] = set()
        for _path, cells in self.output_rows():
            for name in cells:
                if name in seen:
                    continue
                seen.add(name)
                names.append(name)
        return tuple(names)

    def output_rows(self) -> list[tuple[str, dict[str, str]]]:
        """File order. The first row of a path is the edited one. Later rows stay."""
        emitted: set[str] = set()
        ordered: list[tuple[str, dict[str, str]]] = []
        for relative, cells in self.raw_rows:
            if relative not in self.rows:
                continue
            if relative not in emitted:
                emitted.add(relative)
                ordered.append((relative, self.rows[relative]))
                continue
            ordered.append((relative, cells))
        for relative, cells in self.rows.items():
            if relative in emitted:
                continue
            ordered.append((relative, cells))
        return ordered

    def save(self) -> None:
        """Rewrite the kind file. A later duplicate row is kept."""
        self._require_parent()
        text = self._full_text()
        payload = text.encode("utf-8")
        if self._bom:
            payload = b"\xef\xbb\xbf" + payload
        self.path.write_bytes(payload)
        self.missing = False
        self.blank = False

    def _full_text(self) -> str:
        rows = self.output_rows()
        if self.suffix == ".csv":
            columns = self.columns
            if columns is None:
                columns = (KIND_CSV_PATH, *(name for _path, cells in rows for name in cells))
                columns = tuple(dict.fromkeys(columns))
            return self._csv_rows(columns, rows)
        if self.suffix == ".toml":
            return "".join(self._toml_row(relative, cells) for relative, cells in rows)
        return self._yaml_rows(rows)

    def _csv_rows(self, columns: tuple[str, ...], rows: list[tuple[str, dict[str, str]]]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=self.sep, lineterminator="\n")
        writer.writerow(columns)
        for relative, cells in rows:
            writer.writerow(
                [relative if name == KIND_CSV_PATH else cells.get(name, "") for name in columns]
            )
        return buffer.getvalue()

    def _toml_row(self, relative: str, cells: dict[str, str]) -> str:
        lines = [f"[[rows]]\npath = {self._toml_string(relative)}\n"]
        if cells:
            lines.append("[rows.vars]\n")
            for key, value in cells.items():
                lines.append(f"{key} = {self._toml_string(value)}\n")
        return "".join(lines)

    @classmethod
    def _yaml_rows(cls, rows: list[tuple[str, dict[str, str]]]) -> str:
        if not rows:
            return "[]\n"
        chunks: list[str] = []
        for relative, cells in rows:
            dumped_path = yaml.safe_dump(
                relative,
                allow_unicode=True,
                default_style='"',
            ).strip()
            lines = [f"- path: {dumped_path}\n"]
            if cells:
                lines.append("  vars:\n")
                for key, value in cells.items():
                    dumped = yaml.safe_dump(
                        value,
                        allow_unicode=True,
                        default_style='"',
                    ).strip()
                    lines.append(f"    {key}: {dumped}\n")
            chunks.append("".join(lines))
        return "".join(chunks)

    def _append(self) -> None:
        block = self._rendered(
            self.columns or self._FRESH_COLUMNS,
            header=False,
        ).encode("utf-8")
        raw = self.path.read_bytes()
        prefix = b"\n" if raw and not raw.endswith(b"\n") else b""
        with self.path.open("ab") as handle:
            handle.write(prefix + block)

    def _require_parent(self) -> None:
        parent = self.path.parent
        for ancestor in (parent, *parent.parents):
            if ancestor.exists() and not ancestor.is_dir():
                raise VarConfigError(
                    f"Kind file {self.path} parent is not a directory",
                    advice="Choose a path whose parents are directories.",
                )
            if ancestor.exists():
                break
        parent.mkdir(parents=True, exist_ok=True)

    def _rendered(self, columns: tuple[str, ...], *, header: bool) -> str:
        if self.suffix == ".csv":
            return self._csv_text(columns, header=header)
        if self.suffix == ".toml":
            return self._toml_text()
        return self._yaml_text()

    def _csv_text(self, columns: tuple[str, ...], *, header: bool = True) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=self.sep, lineterminator="\n")
        if header:
            writer.writerow(columns)
        for relative in self._pending:
            writer.writerow([relative if name == KIND_CSV_PATH else "" for name in columns])
        return buffer.getvalue()

    def _toml_text(self) -> str:
        return "".join(
            f"[[rows]]\npath = {self._toml_string(relative)}\n" for relative in self._pending
        )

    def _yaml_text(self) -> str:
        return "".join(self._yaml_item(relative) for relative in self._pending)

    @classmethod
    def _suffix(cls, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix not in cls._SUFFIXES:
            raise VarConfigError(
                f"Kind file {path} has an unsupported suffix",
                advice="Use .csv, .toml, .yaml, or .yml.",
            )
        return suffix

    @classmethod
    def _parse_csv(
        cls,
        path: Path,
        text: str,
        logger: logging.Logger,
        sep: str,
    ) -> tuple[tuple[str, ...], dict[str, dict[str, str]], list[tuple[str, dict[str, str]]]]:
        try:
            parsed = [
                row
                for row in csv.reader(io.StringIO(text), delimiter=sep)
                if any(cell.strip() for cell in row)
            ]
        except csv.Error as exc:
            raise VarConfigError(
                f"Invalid CSV in {path}: {exc}",
                advice=cls._header_advice(sep, ()),
            ) from exc
        if not parsed:
            raise VarConfigError(
                f"{path} header is empty",
                advice=cls._header_advice(sep, ()),
            )
        header = tuple(cell.strip() for cell in parsed[0])
        cls._check_header(path, header, sep)
        rows: dict[str, dict[str, str]] = {}
        raw_rows: list[tuple[str, dict[str, str]]] = []
        for raw in parsed[1:]:
            if len(raw) > len(header):
                raise VarConfigError(
                    f"{path} row has too many columns",
                    advice=cls._header_advice(sep, header),
                )
            padded = list(raw) + [""] * (len(header) - len(raw))
            relative = ""
            cells: dict[str, str] = {}
            for name, cell in zip(header, padded, strict=True):
                if name == KIND_CSV_PATH:
                    relative = cell
                    continue
                text_cell = cls._plain(cell)
                if text_cell is not None:
                    cells[name] = text_cell
            if relative.strip() == "":
                if cells:
                    raise VarConfigError(
                        f"{path} has a row with an empty PATH",
                        advice=cls._header_advice(sep, header),
                    )
                continue
            raw_rows.append((relative, dict(cells)))
            if relative in rows:
                logger.warning(
                    "Kind file %s path %r is duplicated; keeping the first row",
                    path,
                    relative,
                )
                continue
            rows[relative] = cells
        return header, rows, raw_rows

    @classmethod
    def _check_header(cls, path: Path, header: tuple[str, ...], sep: str) -> None:
        advice = cls._header_advice(sep, header)
        if len(header) != len(set(header)):
            repeated = next(name for name in header if header.count(name) > 1)
            raise VarConfigError(
                f"{path} column {repeated!r} is repeated",
                advice=advice,
            )
        if not header or header[0] != KIND_CSV_PATH:
            found = header[0] if header else ""
            raise VarConfigError(
                f"{path} first column is {found!r}. The first column must be PATH.",
                advice=advice,
            )
        for name in header[1:]:
            if name in cls._SHA_ALIASES:
                raise VarConfigError(
                    f"{path} column {name!r} is not a kind-file column. Rows match on PATH.",
                    advice=advice,
                )
            if name in cls._DATE_ALIASES:
                raise VarConfigError(
                    f"{path} column {name!r} is not the date column. Use __date__.",
                    advice=advice,
                )
            if cls._LOWER_NAME.fullmatch(name) is None:
                raise VarConfigError(
                    f"{path} column {name!r} must be lowercase.",
                    advice=advice,
                )
            if name != VAR_DATE:
                check_assignment_key(name, str(path))

    @classmethod
    def _header_advice(cls, sep: str, columns: tuple[str, ...]) -> str:
        example = cls._header_example(sep, columns)
        return (
            "The first column must be PATH. __date__ is optional. "
            "Other columns are lowercase names. "
            f"kind_overrides_sep is {sep!r}. For example: {example}"
        )

    @classmethod
    def _header_example(cls, sep: str, columns: tuple[str, ...]) -> str:
        names = [KIND_CSV_PATH]
        for name in columns[1:]:
            if name in cls._DATE_ALIASES or name == VAR_DATE:
                if VAR_DATE not in names:
                    names.append(VAR_DATE)
                continue
            if name in cls._SHA_ALIASES or name == KIND_CSV_PATH:
                continue
            lowered = name.lower()
            if (
                cls._LOWER_NAME.fullmatch(lowered)
                and lowered not in names
                and lowered != "path"
            ):
                names.append(lowered)
        if len(names) == 1:
            names.append(VAR_DATE)
        return sep.join(names)

    @classmethod
    def _parse_yaml(
        cls,
        path: Path,
        text: str,
        logger: logging.Logger,
    ) -> tuple[dict[str, dict[str, str]], list[tuple[str, dict[str, str]]]]:
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise VarConfigError(
                f"Invalid YAML in {path}: {exc}",
                advice="Use a bare list of path and vars items.",
            ) from exc
        if raw is None:
            return {}, []
        if not isinstance(raw, list):
            raise VarConfigError(
                f"{path} must be a bare list",
                advice="Each item has path and an optional vars mapping.",
            )
        return cls._items(path, raw, logger)

    @classmethod
    def _parse_toml(
        cls,
        path: Path,
        text: str,
        logger: logging.Logger,
    ) -> tuple[dict[str, dict[str, str]], list[tuple[str, dict[str, str]]]]:
        try:
            raw = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise VarConfigError(
                f"Invalid TOML in {path}: {exc}",
                advice="Use [[rows]] tables with path and an optional vars table.",
            ) from exc
        if raw == {}:
            return {}, []
        rows = raw.get("rows") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            raise VarConfigError(
                f"{path} must be [[rows]] tables",
                advice="Each table has path and an optional vars table.",
            )
        return cls._items(path, rows, logger)

    @classmethod
    def _items(
        cls,
        path: Path,
        items: list[object],
        logger: logging.Logger,
    ) -> tuple[dict[str, dict[str, str]], list[tuple[str, dict[str, str]]]]:
        rows: dict[str, dict[str, str]] = {}
        raw_rows: list[tuple[str, dict[str, str]]] = []
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
            cells = cls._vars(path, index, item.get("vars"))
            raw_rows.append((relative, dict(cells)))
            if relative in rows:
                logger.warning(
                    "Kind file %s path %r is duplicated; keeping the first row",
                    path,
                    relative,
                )
                continue
            rows[relative] = cells
        return rows, raw_rows

    @classmethod
    def _vars(cls, path: Path, index: int, raw: object) -> dict[str, str]:
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
            check_assignment_key(key, label)
            text = cls._typed(value, label, str(key))
            if text is not None:
                cells[str(key)] = text
        return cells

    @staticmethod
    def _plain(cell: str) -> str | None:
        if cell.strip() == "":
            return None
        return cell

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
    def _toml_string(value: str) -> str:
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'

    @staticmethod
    def _yaml_item(relative: str) -> str:
        dumped = yaml.safe_dump(relative, allow_unicode=True).strip()
        return f"- path: {dumped}\n"


class KindRow(NamedTuple):
    """Cells from the winning kind file, plus that file's path."""

    path: str | None
    cells: dict[str, str]


class KindFiles:
    """Per-file kind rows. The first existing path wins, then the parse is cached."""

    def __init__(
        self,
        templates: tuple[str, ...],
        root_dir: Path,
        profile_scope: Mapping[str, Any],
        mode: KindMode,
        date_format: KindDateFormat,
        sep: str,
        dry_run: bool,
    ) -> None:
        self._templates = templates
        self._root = root_dir
        self._profile_scope = profile_scope
        self._mode = mode
        self._dates = date_format
        self._sep = sep
        self._dry_run = dry_run
        self._tables: dict[Path, KindTable] = {}
        self._winners: dict[tuple[str, str], KindTable | None] = {}
        self._seen: set[tuple[str, str]] = set()
        self._catalog: VarCatalog | None = None
        self._logger = logging.getLogger(LOGGER_NAME)

    @classmethod
    def from_section(
        cls,
        section: Mapping[str, Any],
        root_dir: Path,
        profile_scope: Mapping[str, Any],
        mode: KindMode,
        date_format: KindDateFormat,
        dry_run: bool,
    ) -> KindFiles:
        """Check the path list. Files are read later, when a kind is used."""
        sep = KindCsvSep.from_section(section).text
        raw = section.get(KEY_KIND_OVERRIDES)
        if raw is None:
            templates = tuple(PACKAGED.kind_overrides_config)
        elif raw == []:
            templates = ()
        elif not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
            raise VarConfigError(
                "config.kind_overrides_config must be a list of path templates",
                advice="Omit it to use the default profile paths, use [], or list path templates.",
            )
        else:
            templates = tuple(raw)
        return cls(templates, root_dir, profile_scope, mode, date_format, sep, dry_run)

    def bind_catalog(self, catalog: VarCatalog) -> None:
        """Use this catalog when a kind file is chosen."""
        self._catalog = catalog

    @property
    def templates(self) -> tuple[str, ...]:
        """Path templates. An empty tuple means there is no kind file."""
        return self._templates

    @property
    def dates(self) -> KindDateFormat:
        """Format used to read and write a __date__ cell."""
        return self._dates

    def open_table(self, kind: str, input_dir: Path, *, create: bool) -> KindTable | None:
        """The winning file. `create` holds a missing file and does not write it.

        Mode does not apply. A cached miss stays a miss until `create` is set.
        """
        search = (kind, str(input_dir))
        if search in self._seen:
            cached = self._winners.get(search)
            if cached is not None or not create:
                return cached
        table = self._find_table(kind, input_dir, create=create)
        self._seen.add(search)
        self._winners[search] = table
        return table

    def cells_for(
        self,
        kind: str,
        input_dir: Path,
        relative: str,
        match: FileMatch,
    ) -> KindRow:
        """Return the literal cells for one file. auto and always record a missing path."""
        if self._mode == KIND_MODE_DISABLED:
            return KindRow(None, {})
        table = self.open_table(
            kind,
            input_dir,
            create=self._mode == KIND_MODE_ALWAYS,
        )
        if table is None:
            return KindRow(None, {})
        cells = self._literals(table.rows.get(relative, {}), match, relative)
        if self._mode in (KIND_MODE_AUTO, KIND_MODE_ALWAYS):
            table.ensure(relative)
        return KindRow(str(table.path), cells)

    def commit(self) -> None:
        """Write queued rows once. A failed resolve never reaches this."""
        writable = self._mode in (KIND_MODE_AUTO, KIND_MODE_ALWAYS)
        for table in self._tables.values():
            if writable:
                table.sync_schema_columns(self._dry_run, self._logger)
            table.commit(self._dry_run, self._logger)

    def _find_table(self, kind: str, input_dir: Path, *, create: bool) -> KindTable | None:
        if not self._templates:
            self._logger.debug("No kind_overrides_config for kind %s", kind)
            return None
        scope = dict(self._profile_scope)
        scope[VAR_MATCH] = ScopeObject({FIELD_KIND: kind}, FIELD_KIND)
        scope[VAR_INPUT] = ScopeObject({FIELD_PATH: str(input_dir)}, FIELD_PATH)
        rendered: list[Path] = []
        for template in self._templates:
            path = self._render_path(template, scope)
            rendered.append(path)
            if not path.exists():
                self._logger.debug(
                    "Kind file %s is missing for kind %s",
                    path.resolve(),
                    kind,
                )
                continue
            if not path.is_file():
                raise VarConfigError(
                    f"Kind file {path} is not a file",
                    advice="Point kind_overrides_config at a csv, toml, or yaml file.",
                )
            return self._with_headers(self._load_existing(path, kind), kind)
        if create and rendered:
            return self._with_headers(
                self._hold(KindTable.missing(rendered[0], self._sep)),
                kind,
            )
        return None

    def _with_headers(self, table: KindTable, kind: str) -> KindTable:
        if self._catalog is not None:
            table.add_schema_columns(self._catalog.csv_headers(kind))
        return table

    def _load_existing(self, path: Path, kind: str) -> KindTable:
        resolved = path.resolve()
        cached = self._tables.get(resolved)
        if cached is not None:
            self._logger.debug(
                "Kind file %s already loaded for kind %s",
                resolved,
                kind,
            )
            return cached
        table = self._hold(KindTable.read(path, self._logger, self._sep))
        self._logger.debug("Loaded kind file %s for kind %s", resolved, kind)
        return table

    def _hold(self, table: KindTable) -> KindTable:
        resolved = table.path.resolve()
        current = self._tables.get(resolved)
        if current is not None:
            return current
        self._tables[resolved] = table
        return table

    def _literals(
        self,
        raw: Mapping[str, str],
        match: FileMatch,
        relative: str,
    ) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for key, value in raw.items():
            if key != VAR_DATE:
                parsed[key] = value
                continue
            try:
                parsed[key] = self._dates.store(value)
            except ValueError as exc:
                raise VarResolveError(
                    f"Profile {match.profile} input {match.index} path {relative} "
                    f"variable {VAR_DATE} failed",
                    advice=f"{value!r} does not match {self._dates.text}. {exc}",
                ) from exc
        return parsed

    def _render_path(self, template: str, scope: Mapping[str, Any]) -> Path:
        return render_user_path(
            template,
            scope,
            self._root,
            empty_message="A kind_overrides_config path rendered empty",
            error=VarConfigError,
            advice="The path template must render to a file path.",
        )


