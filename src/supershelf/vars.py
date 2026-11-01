"""Resolve variables for one matched file."""

from __future__ import annotations

import csv
import importlib
import io
import json
import logging
import os
import re
import tomllib
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

import yaml

from supershelf.common import WordChoice, resolve_user_path
from supershelf.constants import (
    CONFIG_SECTION,
    DATE_TEXT,
    ENV_KIND_OVERRIDES_MODE,
    INTERNAL_NAMES,
    KEY_DEFAULT_DATE_FORMAT,
    KEY_DEFAULT_VARS,
    KEY_KIND_OVERRIDES,
    KEY_KIND_OVERRIDES_DATE_FORMAT,
    KEY_KIND_OVERRIDES_MODE,
    KEY_KIND_OVERRIDES_SEP,
    KEY_METADATA_DRIVER,
    KIND_CSV_PATH,
    KIND_MODE_ALWAYS,
    KIND_MODE_AUTO,
    KIND_MODE_DISABLED,
    KIND_OVERRIDE_MODES,
    LOGGER_NAME,
    KEY_OVERRIDE_PATH,
    KEY_OVERRIDES,
    KEY_RULE_VARS,
    KEY_VAR_MODULES,
    SOURCE_DEFAULT,
    SOURCE_FACT,
    SOURCE_KIND,
    SOURCE_OVERRIDE,
    SOURCE_RULE,
    VAR_CTIME,
    VAR_DATABASE_FILE,
    VAR_DATE,
    VAR_DEFAULT_DATE_FORMAT,
    VAR_FILE_DIR,
    VAR_FILE_EXT,
    VAR_FILE_HASH,
    VAR_FILE_NAME,
    VAR_FILE_PATH,
    VAR_FILE_STEM,
    VAR_FILTERS,
    VAR_GLOBALS,
    VAR_INPUT,
    VAR_KIND,
    VAR_MTIME,
    VAR_PROFILE_DIR,
    VAR_RULE_NAME,
)
from supershelf.defaults import PACKAGED
from supershelf.errors import SupershelfError, VarCandidateError, VarConfigError, VarResolveError
from supershelf.match import FileMatch, Matcher
from supershelf.metadata.driver import MetadataFile
from supershelf.metadata.process import ProcessRunner
from supershelf.metadata.registry import MetadataRegistry
from supershelf.metadata.session import MetadataSession
from supershelf.scan import InputFile
from supershelf.template import Template
from supershelf.var_commands import FileBinding
from supershelf.var_schema import (
    CastMiss,
    CastValue,
    VarCatalog,
    VarState,
    cast_value,
    layer_source,
)
from supershelf.var_template import VarEnvironment, is_template


_STRUCTURED_FORMATS = frozenset({"json", "yaml"})


class FileVars:
    """Resolved variables for one matched file."""

    def __init__(self, kind: str, rule: str, states: tuple[tuple[str, VarState], ...]) -> None:
        self.kind = kind
        self.rule = rule
        self.states = states

    @property
    def items(self) -> tuple[tuple[str, str], ...]:
        """Set variables in first-seen order. The value is the display string."""
        return tuple((name, state.display) for name, state in self.states)

    @property
    def sources(self) -> dict[str, tuple[str, ...]]:
        """Source labels for each set variable, in the order layers wrote it."""
        return {name: tuple(state.value_sources) for name, state in self.states}

    def dump_vars(self, *, show_all: bool = False) -> dict[str, Any]:
        """JSON-ready values. Floats can differ from their display spelling."""
        return {
            name: state.model_dump(mode="json")
            for name, state in self.states
            if show_all or name not in INTERNAL_NAMES
        }

    def _table_pairs(self, *, show_all: bool = False) -> tuple[tuple[str, str], ...]:
        """Printed variables in table order: alphabetical by name."""
        visible = self.items
        if not show_all:
            visible = tuple(
                (name, value) for name, value in visible if name not in INTERNAL_NAMES
            )
        return tuple(sorted(visible))

    def present(self, fmt: str | None, *, show_all: bool = False) -> object:
        """Table text, or the typed mapping for json and yaml."""
        if fmt in _STRUCTURED_FORMATS:
            return self.dump_vars(show_all=show_all)
        return "\n".join(
            f"{name}: {value}" for name, value in self._table_pairs(show_all=show_all)
        )

    def present_sources(self, *, show_all: bool = False) -> str:
        """Source labels for the table, one line per name in present() order."""
        return "\n".join(
            ", ".join(self.sources[name])
            for name, _value in self._table_pairs(show_all=show_all)
        )


class VarTable:
    """Ordered variable definitions. Each value is one or more candidates."""

    _IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
    _LOCKED = tuple(name for name in INTERNAL_NAMES if name != VAR_KIND)

    def __init__(self, keys: tuple[str, ...], candidates: dict[str, tuple[str, ...]]) -> None:
        self.keys = keys
        self.candidates = candidates

    @classmethod
    def empty(cls) -> VarTable:
        """A table with no keys."""
        return cls((), {})

    @classmethod
    def parse(
        cls,
        raw: object,
        *,
        label: str,
        allows_kind: bool,
        environment: VarEnvironment,
    ) -> VarTable:
        """Parse a mapping of strings or string lists and compile every candidate."""
        if raw is None:
            return cls.empty()
        if not isinstance(raw, dict):
            raise VarConfigError(
                f"{label} must be a mapping",
                advice="Use a name, then a string or a list of strings.",
            )
        keys: list[str] = []
        candidates: dict[str, tuple[str, ...]] = {}
        for key, value in raw.items():
            cls._check_key(key, label, allows_kind)
            items = cls._candidates(value, label, str(key))
            for item in items:
                environment.compile_source(item)
            keys.append(str(key))
            candidates[str(key)] = items
        return cls(tuple(keys), candidates)

    @classmethod
    def _check_key(cls, key: object, label: str, allows_kind: bool) -> None:
        if not isinstance(key, str) or cls._IDENT.fullmatch(key) is None:
            raise VarConfigError(
                f"{label} key {key!r} is not a variable name",
                advice="Start with a letter or underscore, then use letters, digits, and underscores.",
            )
        if key in cls._LOCKED or (key == VAR_KIND and not allows_kind):
            raise VarConfigError(
                f"{label} cannot set {key}",
                advice="Only an override may set __kind__. Other internal names are fixed.",
            )

    @classmethod
    def _candidates(cls, value: object, label: str, key: str) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list):
            if not value:
                raise VarConfigError(
                    f"{label} key {key} has an empty list",
                    advice="Add at least one string, or remove the key.",
                )
            if all(isinstance(item, str) for item in value):
                return tuple(value)
        raise VarConfigError(
            f"{label} key {key} must be a string or a list of strings",
            advice="Quote scalars such as dates so they stay strings.",
        )


class OverrideRule:
    """One per-file override. The first matching path wins."""

    def __init__(self, pattern: str, table: VarTable) -> None:
        self.pattern = pattern
        self.table = table

    def matches(self, relative: str) -> bool:
        """Full-match the path relative to the input directory."""
        return PurePosixPath(relative).full_match(self.pattern)


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
                scoped = profile_scope.get(VAR_DEFAULT_DATE_FORMAT)
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
    ) -> None:
        self.path = path
        self.suffix = suffix
        self.columns = columns
        self.rows = rows
        self.sep = sep
        self.blank = blank
        self.missing = missing
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
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise VarConfigError(
                f"{path} is not UTF-8",
                advice="Save the kind file as UTF-8.",
            ) from exc
        if text.strip() == "":
            return cls(path, suffix, None, {}, sep, blank=True)
        if suffix == ".csv":
            columns, rows = cls._parse_csv(path, text, logger, sep)
            return cls(path, suffix, columns, rows, sep)
        if suffix == ".toml":
            return cls(path, suffix, None, cls._parse_toml(path, text, logger), sep)
        return cls(path, suffix, None, cls._parse_yaml(path, text, logger), sep)

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

    @classmethod
    def _legal_column(cls, name: str) -> bool:
        if name == KIND_CSV_PATH or name in cls._SHA_ALIASES or name in cls._DATE_ALIASES:
            return False
        if cls._LOWER_NAME.fullmatch(name) is None:
            return False
        if name == VAR_DATE:
            return True
        try:
            VarTable._check_key(name, "kind file", False)
        except VarConfigError:
            return False
        return True

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
    ) -> tuple[tuple[str, ...], dict[str, dict[str, str]]]:
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
            if relative in rows:
                logger.warning(
                    "Kind file %s path %r is duplicated; keeping the first row",
                    path,
                    relative,
                )
                continue
            rows[relative] = cells
        return header, rows

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
                VarTable._check_key(name, str(path), False)

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
    ) -> dict[str, dict[str, str]]:
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise VarConfigError(
                f"Invalid YAML in {path}: {exc}",
                advice="Use a bare list of path and vars items.",
            ) from exc
        if raw is None:
            return {}
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
    ) -> dict[str, dict[str, str]]:
        try:
            raw = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise VarConfigError(
                f"Invalid TOML in {path}: {exc}",
                advice="Use [[rows]] tables with path and an optional vars table.",
            ) from exc
        if raw == {}:
            return {}
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
    ) -> dict[str, dict[str, str]]:
        rows: dict[str, dict[str, str]] = {}
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
            if relative in rows:
                logger.warning(
                    "Kind file %s path %r is duplicated; keeping the first row",
                    path,
                    relative,
                )
                continue
            rows[relative] = cells
        return rows

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
            VarTable._check_key(key, label, False)
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
        mode: str,
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
        self._catalog: VarCatalog | None = None
        self._logger = logging.getLogger(LOGGER_NAME)

    @classmethod
    def from_section(
        cls,
        section: Mapping[str, Any],
        root_dir: Path,
        profile_scope: Mapping[str, Any],
        mode: str,
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
        search = (kind, str(input_dir))
        if search not in self._winners:
            self._winners[search] = self._winner(kind, input_dir)
        table = self._winners[search]
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

    def _winner(self, kind: str, input_dir: Path) -> KindTable | None:
        if not self._templates:
            self._logger.debug("No kind_overrides_config for kind %s", kind)
            return None
        scope = dict(self._profile_scope)
        scope[VAR_KIND] = kind
        scope[VAR_INPUT] = {"path": str(input_dir)}
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
        if self._mode == KIND_MODE_ALWAYS and rendered:
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
        try:
            rendered = Template(scope).render(template).strip()
        except SupershelfError as exc:
            raise VarConfigError(str(exc), advice=exc.advice) from exc
        if not rendered:
            raise VarConfigError(
                "A kind_overrides_config path rendered empty",
                advice="The path template must render to a file path.",
            )
        return resolve_user_path(rendered, self._root)


class VarPlan:
    """Facts, then default, rule, kind row, and override assignments."""

    def __init__(
        self,
        environment: VarEnvironment,
        catalog: VarCatalog,
        rules: dict[str, VarTable],
        overrides: tuple[OverrideRule, ...],
        kinds: KindFiles,
        profile_scope: Mapping[str, Any],
        session: MetadataSession,
    ) -> None:
        self._environment = environment
        self._catalog = catalog
        self._rules = rules
        self._overrides = overrides
        self._kinds = kinds
        self._profile_scope = dict(profile_scope)
        self._session = session
        self._pdf: dict[str, tuple[str | None, str | None]] = {}

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
        profile_name: str,
        matcher: Matcher,
        root_dir: Path,
        profile_scope: Mapping[str, Any],
        *,
        mode: str | None = None,
        dry_run: bool = False,
        environ: Mapping[str, str] | None = None,
        runner: ProcessRunner | None = None,
    ) -> VarPlan:
        """Load modules and var tables before any walk."""
        environment = VarEnvironment()
        section = cls._section(document)
        cls._reject_metadata_in_config(section)
        session = cls._metadata_session(
            document,
            profile_scope,
            environment,
            runner,
            dry_run,
        )
        chosen = KindOverrideMode.resolve(section, mode, os.environ if environ is None else environ)
        dates = KindDateFormat.from_section(section, profile_scope)
        cls._load_modules(environment, section)
        cls._reject_reserved_groups(matcher)
        defaults = VarTable.parse(
            document.get(KEY_DEFAULT_VARS),
            label="default_vars",
            allows_kind=False,
            environment=environment,
        )
        rules, rule_kinds = cls._rule_tables(matcher, environment)
        overrides = cls._override_tables(document, environment)
        kinds = KindFiles.from_section(
            section,
            root_dir,
            profile_scope,
            chosen,
            dates,
            dry_run,
        )
        names: list[str] = list(defaults.keys)
        for table in rules.values():
            names.extend(table.keys)
        for rule in overrides:
            names.extend(rule.table.keys)
        names.extend(matcher.named_groups())
        catalog = VarCatalog.load(
            document,
            compile_source=environment.compile_source,
            names=names,
        )
        kinds.bind_catalog(catalog)
        for rule_name, table in rules.items():
            cls._check_literals(
                catalog,
                table,
                f"match rule {rule_name} vars",
                rule_kinds[rule_name],
            )
        for index, rule in enumerate(overrides, start=1):
            cls._check_literals(catalog, rule.table, f"overrides item {index} vars", "")
        return cls(environment, catalog, rules, overrides, kinds, profile_scope, session)

    def resolve(self, file: InputFile, match: FileMatch, input_dir: Path) -> FileVars:
        """Resolve one matched file. Kind files use the rule kind, not an override."""
        self._require_metadata(file, match)
        token = self._session.bind(MetadataFile.from_input(file))
        try:
            return self._resolve_bound(file, match, input_dir)
        finally:
            self._session.unbind(token)

    def _resolve_bound(self, file: InputFile, match: FileMatch, input_dir: Path) -> FileVars:
        scope: dict[str, str] = {}
        states: dict[str, VarState] = {}
        order: list[str] = []
        for key, value, label in self._fact_rows(file, match):
            self._save_raw(key, value, label, scope, states, order, match, file.path)
        binding = FileBinding(file.absolute, file.sha256 or "", file.ctime or "", file.mtime or "")
        self._apply_defaults(scope, states, order, binding, match.kind)
        self._apply(
            self._rules.get(match.rule, VarTable.empty()),
            layer_source(SOURCE_RULE, match.rule),
            scope,
            states,
            order,
            binding,
            match.kind,
        )
        self._apply_cells(
            self._kinds.cells_for(match.kind, input_dir, file.path, match),
            scope,
            states,
            order,
            match,
            file.path,
        )
        override = self._override_for(file.path)
        if override is not None:
            self._apply(
                override.table,
                layer_source(SOURCE_OVERRIDE, override.pattern),
                scope,
                states,
                order,
                binding,
                match.kind,
            )
        self._require_mandatory(states, match, file.path)
        chosen = tuple(
            (key, states[key])
            for key in order
            if key in states and states[key].value is not None
        )
        return FileVars(states[VAR_KIND].display, match.rule, chosen)

    @property
    def catalog(self) -> VarCatalog:
        """The catalog used to resolve this plan."""
        return self._catalog

    @property
    def metadata(self) -> MetadataRegistry:
        """Drivers loaded for this profile."""
        return self._session.registry

    def snapshot(self, resolved: FileVars) -> str:
        """JSON object stored on a document. Identity columns are omitted."""
        body: dict[str, dict[str, object]] = {}
        for name, state in resolved.states:
            if name in INTERNAL_NAMES:
                continue
            if state.value is None:
                continue
            spec = self._catalog.effective(resolved.kind, name)
            body[name] = {
                "type": spec.type,
                "value": state.value,
                "display": state.display,
                "value_sources": list(state.value_sources),
            }
        return json.dumps(body, sort_keys=True, separators=(",", ":"))

    def commit(self) -> None:
        """Create or append kind rows after every file in this plan has resolved."""
        self._kinds.commit()

    def _apply_cells(
        self,
        row: KindRow,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
        match: FileMatch,
        path: str,
    ) -> None:
        if row.path is None:
            return
        label = layer_source(SOURCE_KIND, row.path)
        for key, value in row.cells.items():
            self._save_raw(key, value, label, scope, states, order, match, path)

    def _apply_defaults(
        self,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
        binding: FileBinding,
        kind: str,
    ) -> None:
        for key in self._catalog.names_for(kind):
            candidates = self._catalog.default_candidates(kind, key)
            if not candidates:
                continue
            cast = self._first(
                key,
                candidates,
                self._render_scope(scope),
                binding,
                kind,
            )
            if cast is None:
                continue
            self._save(key, cast, SOURCE_DEFAULT, scope, states, order)

    def _apply(
        self,
        table: VarTable,
        label: str,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
        binding: FileBinding,
        kind: str,
    ) -> None:
        for key in table.keys:
            cast = self._first(
                key,
                table.candidates[key],
                self._render_scope(scope),
                binding,
                kind,
            )
            if cast is None:
                continue
            self._save(key, cast, label, scope, states, order)

    def _render_scope(self, scope: Mapping[str, str]) -> dict[str, Any]:
        """Profile names, then the display strings written so far."""
        render_scope = dict(self._profile_scope)
        render_scope.update(scope)
        return render_scope

    def _first(
        self,
        key: str,
        candidates: tuple[object, ...],
        scope: Mapping[str, Any],
        binding: FileBinding,
        kind: str,
    ) -> CastValue | None:
        spec = self._catalog.effective(kind, key)
        for source in candidates:
            try:
                if isinstance(source, str):
                    rendered = self._environment.render(source, scope, binding, self._pdf)
                    cast = cast_value(spec, rendered, allow_typed=False)
                else:
                    cast = cast_value(spec, source, allow_typed=True)
            except (VarCandidateError, CastMiss):
                continue
            return cast
        return None

    def _save(
        self,
        key: str,
        cast: CastValue,
        label: str,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
    ) -> None:
        state = states.get(key)
        if state is None:
            state = VarState()
            states[key] = state
        state.write(cast, label)
        scope[key] = cast.display
        if key not in order:
            order.append(key)

    def _save_raw(
        self,
        key: str,
        raw: str,
        label: str,
        scope: dict[str, str],
        states: dict[str, VarState],
        order: list[str],
        match: FileMatch,
        path: str,
    ) -> None:
        spec = self._catalog.effective(match.kind, key)
        try:
            cast = cast_value(spec, raw, allow_typed=False)
        except CastMiss as exc:
            raise self._failed(match, path, key, str(exc)) from exc
        self._save(key, cast, label, scope, states, order)

    def _require_mandatory(
        self,
        states: dict[str, VarState],
        match: FileMatch,
        path: str,
    ) -> None:
        for name in self._catalog.names_for(match.kind):
            spec = self._catalog.effective(match.kind, name)
            if not spec.mandatory:
                continue
            state = states.get(name)
            if state is None or state.value is None:
                raise self._failed(
                    match,
                    path,
                    name,
                    f"{name} is mandatory and no layer set it.",
                )

    def _failed(self, match: FileMatch, path: str, key: str, advice: str) -> VarResolveError:
        return VarResolveError(
            f"Profile {match.profile} input {match.index} path {path} variable {key} failed",
            advice=advice,
        )

    def _override_for(self, relative: str) -> OverrideRule | None:
        for rule in self._overrides:
            if rule.matches(relative):
                return rule
        return None

    def _fact_rows(self, file: InputFile, match: FileMatch) -> list[tuple[str, str, str]]:
        ext = file.suffix[1:] if file.suffix.startswith(".") else file.suffix
        values = {
            VAR_KIND: match.kind,
            VAR_RULE_NAME: match.rule,
            VAR_CTIME: file.ctime or "",
            VAR_MTIME: file.mtime or "",
            VAR_FILE_HASH: file.sha256 or "",
            VAR_FILE_NAME: file.name,
            VAR_FILE_STEM: file.stem,
            VAR_FILE_EXT: ext,
            VAR_FILE_PATH: file.path,
            VAR_FILE_DIR: file.directory,
        }
        rows = [(name, values[name], SOURCE_FACT) for name in INTERNAL_NAMES]
        seen = {name for name, _value, _label in rows}
        for name, value in match.groups.items():
            if name in seen:
                continue
            rows.append((name, value, SOURCE_FACT))
        return rows

    def _require_metadata(self, file: InputFile, match: FileMatch) -> None:
        if file.ctime is None or file.mtime is None or file.sha256 is None:
            raise VarResolveError(
                f"Profile {match.profile} input {match.index} path {file.path} has no file metadata",
                advice="scan vars reads mtime, ctime, and sha256.",
            )

    @classmethod
    def _check_literals(
        cls,
        catalog: VarCatalog,
        table: VarTable,
        label: str,
        kind: str,
    ) -> None:
        """Cast non-template literals now. A miss is a config error, not a fallback."""
        for key in table.keys:
            spec = catalog.effective(kind, key)
            for item in table.candidates[key]:
                if is_template(item):
                    continue
                try:
                    cast_value(spec, item, allow_typed=False)
                except CastMiss as exc:
                    raise VarConfigError(
                        f"{label} key {key} cannot be cast",
                        advice=str(exc),
                    ) from exc

    @classmethod
    def _reject_metadata_in_config(cls, section: Mapping[str, Any]) -> None:
        if KEY_METADATA_DRIVER not in section:
            return
        raise VarConfigError(
            "config.metadata_driver is not a config key",
            advice="Move metadata_driver to the top level, next to default_vars.",
        )

    @classmethod
    def _metadata_session(
        cls,
        document: Mapping[str, Any],
        profile_scope: Mapping[str, Any],
        environment: VarEnvironment,
        runner: ProcessRunner | None,
        dry_run: bool,
    ) -> MetadataSession:
        tool = ProcessRunner() if runner is None else runner
        registry = MetadataRegistry.from_document(
            document.get(KEY_METADATA_DRIVER),
            cls._profile_dir(profile_scope),
            tool,
        )
        registry.require_available()
        session = MetadataSession(
            registry,
            tool,
            database=cls._database_file(profile_scope),
            dry_run=dry_run,
        )
        environment.bind_metadata(registry, session)
        return session

    @staticmethod
    def _profile_dir(profile_scope: Mapping[str, Any]) -> Path:
        raw = profile_scope.get(VAR_PROFILE_DIR, "")
        if not isinstance(raw, str) or not raw:
            return Path(".")
        return Path(raw)

    @staticmethod
    def _database_file(profile_scope: Mapping[str, Any]) -> Path | None:
        raw = profile_scope.get(VAR_DATABASE_FILE, "")
        if not isinstance(raw, str) or not raw:
            return None
        return Path(raw)

    @classmethod
    def _section(cls, document: Mapping[str, Any]) -> Mapping[str, Any]:
        section = document.get(CONFIG_SECTION)
        if section is None:
            return {}
        if not isinstance(section, dict):
            raise VarConfigError(
                "config must be a mapping",
                advice="Put profile settings under config:.",
            )
        return section

    @classmethod
    def _load_modules(cls, environment: VarEnvironment, section: Mapping[str, Any]) -> None:
        raw = section.get(KEY_VAR_MODULES)
        if raw is None or raw == []:
            return
        if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
            raise VarConfigError(
                "config.var_modules must be a list of module paths",
                advice="Use importable module names, such as my_package.supershelf_vars.",
            )
        for module_name in raw:
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                raise VarConfigError(
                    f"Cannot import var module {module_name!r}: {exc}",
                    advice="Install the package and check the module path.",
                ) from exc
            cls._register_exports(environment, module, VAR_GLOBALS, environment.add_global)
            cls._register_exports(environment, module, VAR_FILTERS, environment.add_filter)

    @classmethod
    def _register_exports(cls, environment: VarEnvironment, module: object, attr: str, add: Any) -> None:
        raw = getattr(module, attr, None)
        if raw is None:
            return
        if not isinstance(raw, dict):
            raise VarConfigError(
                f"{getattr(module, '__name__', module)}.{attr} must be a mapping",
                advice="Map command names to functions.",
            )
        for name, func in raw.items():
            if not isinstance(name, str):
                raise VarConfigError(
                    f"{attr} keys must be strings",
                    advice="Use the command name as the key.",
                )
            add(name, func)

    @classmethod
    def _reject_reserved_groups(cls, matcher: Matcher) -> None:
        for name in matcher.named_groups():
            if name.startswith("__"):
                raise VarConfigError(
                    f"Regex group {name!r} is reserved",
                    advice="Name regex groups without a __ prefix. Those names are reserved.",
                )

    @classmethod
    def _rule_tables(
        cls,
        matcher: Matcher,
        environment: VarEnvironment,
    ) -> tuple[dict[str, VarTable], dict[str, str]]:
        tables: dict[str, VarTable] = {}
        kinds: dict[str, str] = {}
        for name, kind, raw in matcher.rule_vars():
            tables[name] = VarTable.parse(
                raw,
                label=f"match rule {name} vars",
                allows_kind=False,
                environment=environment,
            )
            kinds[name] = kind
        return tables, kinds

    @classmethod
    def _override_tables(
        cls,
        document: Mapping[str, Any],
        environment: VarEnvironment,
    ) -> tuple[OverrideRule, ...]:
        raw = document.get(KEY_OVERRIDES)
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise VarConfigError(
                "overrides must be a list",
                advice="Each item has a path and a vars mapping.",
            )
        rules: list[OverrideRule] = []
        for index, item in enumerate(raw, start=1):
            rules.append(cls._one_override(item, index, environment))
        return tuple(rules)

    @classmethod
    def _one_override(cls, item: object, index: int, environment: VarEnvironment) -> OverrideRule:
        if not isinstance(item, dict):
            raise VarConfigError(
                f"overrides item {index} must be a mapping",
                advice="Set path and vars.",
            )
        path = item.get(KEY_OVERRIDE_PATH)
        if not isinstance(path, str) or not path.strip():
            raise VarConfigError(
                f"overrides item {index} needs a path",
                advice="Path is a glob matched against the path relative to the input.",
            )
        if KEY_RULE_VARS not in item:
            raise VarConfigError(
                f"overrides item {index} needs vars",
                advice="Set vars to a mapping. An empty mapping changes nothing.",
            )
        table = VarTable.parse(
            item.get(KEY_RULE_VARS),
            label=f"overrides item {index} vars",
            allows_kind=True,
            environment=environment,
        )
        return OverrideRule(path, table)
