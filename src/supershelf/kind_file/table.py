"""Kind files: mode, date format, and the loaded tables."""

from __future__ import annotations

import logging
import re
from collections import ChainMap
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast

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
    KIND_CSV_SHA,
    IDENTITY_HASH,
    IDENTITY_PATH,
    KIND_MODE_ALWAYS,
    KIND_MODE_AUTO,
    KIND_MODE_DISABLED,
    KIND_MODE_MANUAL,
    KIND_OVERRIDE_MODES,
    FIELD_DATE_FORMAT,
    FIELD_KIND,
    FIELD_PATH,
    LOGGER_NAME,
    TYPE_DATE,
    VAR_CONFIG,
    VAR_INPUT,
    VAR_MATCH,
)
from supershelf.defaults import PACKAGED
from supershelf.errors import VarConfigError, VarResolveError
from supershelf.kind_file.csv import CSV
from supershelf.kind_file.line import KindLine
from supershelf.kind_file.names import KindNames
from supershelf.scan.match import FileMatch
from supershelf.template.render import ScopeObject, scope_field
from supershelf.vars.catalog import VarCatalog


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
    """strptime format for a kind-file date cell. The stored value is YYYY-MM-DD."""

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
    """One kind file. The row identifier is the path or the hash."""

    _SUFFIXES = (".csv",)
    _FRESH_COLUMNS = (KIND_CSV_PATH, KIND_CSV_SHA)

    def __init__(
        self,
        path: Path,
        columns: tuple[str, ...] | None,
        rows: dict[str, dict[str, str]],
        sep: str,
        *,
        blank: bool = False,
        missing: bool = False,
        raw_rows: list[KindLine] | None = None,
        bom: bool = False,
    ) -> None:
        self.path = path
        self.columns = columns
        self.rows = rows
        self.sep = sep
        self.blank = blank
        self.missing = missing
        self.raw_rows = [] if raw_rows is None else raw_rows
        self.row_sha = {}
        for line in self.raw_rows:
            if line.path not in self.row_sha:
                self.row_sha[line.path] = line.sha
        self._bom = bom
        self._pending: list[tuple[str, str]] = []
        self._pending_seen: set[tuple[str, str]] = set()
        self._extra_columns: list[str] = []
        self._fresh_feeds: tuple[str, ...] = ()
        self._notes: list[tuple[str, str, str, int]] = []
        self._sha_sets: dict[str, str] = {}
        self._path_sets: list[tuple[str, str, str]] = []
        self._prepared = False

    @classmethod
    def missing(cls, path: Path, sep: str) -> KindTable:
        """A file that always mode will create from the first template."""
        cls._suffix(path)
        return cls(path, None, {}, sep, missing=True)

    @classmethod
    def read(cls, path: Path, logger: logging.Logger, sep: str) -> KindTable:
        """Parse an existing file. An empty file is an empty table."""
        cls._suffix(path)
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
            return cls(path, None, {}, sep, blank=True, bom=bom)
        parsed = CSV.parse(path, text, logger, sep)
        table = cls(
            path,
            parsed.columns,
            parsed.rows,
            sep,
            raw_rows=parsed.raw_rows,
            bom=bom,
        )
        table._reject_duplicate_sha()
        return table

    def ensure(self, relative: str) -> None:
        """Remember a matched path that is not already a row."""
        self._queue_append(relative, "")

    def note(self, relative: str, digest: str, identity: str, index: int) -> None:
        """Remember one matched file for the write after this run."""
        self._notes.append((relative, digest, identity, index))

    def prepare_identity(self, logger: logging.Logger) -> None:
        """Queue path and hash edits. Log warnings before any write."""
        if self._prepared:
            return
        self._prepared = True
        self._plan_notes(logger)

    def add_schema_columns(self, names: tuple[str, ...]) -> None:
        """Remember schema columns this file does not already have."""
        present = set(self.columns or ())
        present.update(self._extra_columns)
        for name in names:
            if name in present or not self._legal_column(name):
                continue
            self._extra_columns.append(name)
            present.add(name)

    def set_fresh_feeds(self, names: tuple[str, ...]) -> None:
        """Feed columns for a file this run creates. An existing file ignores them."""
        kept: list[str] = []
        for name in names:
            column = self.feed_column_name(name)
            if not self.is_feed_column(column) or column in kept:
                continue
            kept.append(column)
        self._fresh_feeds = tuple(kept)

    def sync_schema_columns(self, dry_run: bool, logger: logging.Logger) -> None:
        """Append missing schema columns on the right of an existing file."""
        if not self._extra_columns:
            return
        if self.missing or self.blank or self.columns is None:
            return
        added = ", ".join(self._extra_columns)
        if dry_run:
            logger.info("Would add columns %s to kind file %s", added, self.path)
            return
        if self._extend_columns():
            logger.debug("Added columns %s to kind file %s", added, self.path)

    def commit(self, dry_run: bool, logger: logging.Logger, *, writable: bool = True) -> None:
        """Create, append, or rewrite after the run. A dry run only logs a real change."""
        if writable and not self._prepared:
            self.prepare_identity(logger)
        if writable and self._structural_rewrite():
            self._commit_rewrite(dry_run, logger)
            return
        if writable and self._needs_sha_insert():
            if dry_run:
                logger.info("Would add column SHA to kind file %s", self.path)
            else:
                self._insert_sha_column()
                logger.debug("Added column SHA to kind file %s", self.path)
        if writable:
            self.sync_schema_columns(dry_run, logger)
        if not writable or not self._pending:
            return
        count = len(self._pending)
        if dry_run:
            if self.missing or self.blank:
                logger.info("Would create kind file %s with %s rows", self.path, count)
                return
            logger.info("Would append %s rows to kind file %s", count, self.path)
            return
        if self.missing or self.blank:
            self._write_new()
            return
        self._append()

    def _create_columns(self) -> tuple[str, ...]:
        return (KIND_CSV_SHA, KIND_CSV_PATH, *self._fresh_feeds, *self._extra_columns)

    def _write_new(self) -> None:
        columns = self._create_columns()
        text = self._rendered(columns, header=True)
        self._replace_bytes(text.encode("utf-8"))
        self.columns = columns
        self.missing = False
        self.blank = False

    def _extend_columns(self) -> bool:
        """Append empty cells. Existing cell text stays on each line."""
        added = tuple(self._extra_columns)
        raw = self.path.read_bytes()
        bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        text = raw.decode("utf-8-sig")
        updated = CSV.extend_columns(text, self.sep, len(self.columns or ()), added)
        if updated is None:
            return False
        self._replace_bytes(bom + updated.encode("utf-8"))
        self.columns = tuple(self.columns or ()) + added
        self._extra_columns.clear()
        return True

    @classmethod
    def feed_column_name(cls, name: str) -> str:
        """The ignored column data feed writes for this var."""
        return KindNames.feed_column_name(name)

    @classmethod
    def is_feed_column(cls, name: str) -> bool:
        """True for an uppercase feed column. PATH and SHA stay reserved."""
        return KindNames.is_feed_column(name)

    def accepts_name(self, name: str) -> bool:
        """Reject a column that is not a legal header name or a feed column."""
        return self.is_feed_column(name) or self._legal_column(name)

    @classmethod
    def _legal_column(cls, name: str) -> bool:
        return KindNames.legal_column(name)

    def set_cell(self, relative: str, name: str, value: str, sha: str = "") -> bool:
        """Set one cell on the first row. An illegal column is refused."""
        if value.strip() == "":
            return False
        if not self.accepts_name(name):
            return False
        row = self.rows.get(relative)
        if row is None:
            row = {}
            self.rows[relative] = row
            self.row_sha[relative] = sha
            self.raw_rows.append(KindLine(relative, sha, row))
            if sha and (self.columns is None or KIND_CSV_SHA not in self.columns):
                base = list(self.columns or (KIND_CSV_PATH,))
                if KIND_CSV_PATH in base:
                    base.insert(base.index(KIND_CSV_PATH) + 1, KIND_CSV_SHA)
                else:
                    base.insert(0, KIND_CSV_SHA)
                self.columns = tuple(base)
        row[name] = value
        if self.columns is None:
            self.columns = (KIND_CSV_PATH, KIND_CSV_SHA)
        if name not in self.columns:
            self.columns = (*self.columns, name)
        return True

    def drop_paths(self, paths: set[str]) -> None:
        """Drop every row for these relative paths, including later duplicates."""
        indexes = {index for index, line in enumerate(self.raw_rows) if line.path in paths}
        self.drop_indexes(indexes)

    def unmatched(
        self,
        live_paths: set[str],
        live_hashes: set[str],
    ) -> tuple[tuple[int, KindLine], ...]:
        """Rows whose path is not a path-identity file and whose hash is not a hash-identity file."""
        found: list[tuple[int, KindLine]] = []
        for index, line in enumerate(self.raw_rows):
            if line.path in live_paths:
                continue
            if line.sha and line.sha in live_hashes:
                continue
            found.append((index, line))
        return tuple(found)

    def drop_indexes(self, indexes: set[int]) -> None:
        """Drop these raw rows. The first remaining row of a path becomes the lookup row."""
        if not indexes:
            return
        self.raw_rows = [
            line for index, line in enumerate(self.raw_rows) if index not in indexes
        ]
        self.rows.clear()
        self.row_sha.clear()
        for line in self.raw_rows:
            if line.path in self.rows:
                continue
            self.rows[line.path] = line.cells
            self.row_sha[line.path] = line.sha

    def output_rows(self) -> list[KindLine]:
        """File order. The first row of a path is the edited one. Later rows stay."""
        emitted: set[str] = set()
        ordered: list[KindLine] = []
        for line in self.raw_rows:
            if line.path not in self.rows:
                continue
            if line.path not in emitted:
                emitted.add(line.path)
                ordered.append(KindLine(line.path, self.row_sha.get(line.path, line.sha), self.rows[line.path]))
                continue
            ordered.append(line)
        for relative, cells in self.rows.items():
            if relative in emitted:
                continue
            ordered.append(KindLine(relative, self.row_sha.get(relative, ""), cells))
        return ordered

    def reload(self, logger: logging.Logger) -> None:
        """Replace the in-memory rows with the file on disk."""
        if not self.path.is_file():
            return
        fresh = type(self).read(self.path, logger, self.sep)
        self.columns = fresh.columns
        self.rows = fresh.rows
        self.raw_rows = fresh.raw_rows
        self.row_sha = fresh.row_sha
        self.blank = fresh.blank
        self.missing = fresh.missing
        self._bom = fresh._bom
        self._pending.clear()
        self._pending_seen.clear()
        self._extra_columns.clear()
        self._fresh_feeds = ()
        self._notes.clear()
        self._sha_sets.clear()
        self._path_sets.clear()
        self._prepared = True

    def save(self) -> None:
        """Rewrite the kind file. A later duplicate row is kept."""
        self._require_parent()
        text = self._full_text()
        payload = text.encode("utf-8")
        if self._bom:
            payload = b"\xef\xbb\xbf" + payload
        self._replace_bytes(payload)
        self.missing = False
        self.blank = False

    def _full_text(self) -> str:
        return CSV.full_text(self.sep, self.columns, self.output_rows())

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
        return CSV.pending_text(self.sep, columns, self._pending, header)

    @classmethod
    def _suffix(cls, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix not in cls._SUFFIXES:
            raise VarConfigError(
                f"Kind file {path} has an unsupported suffix",
                advice="Use .csv.",
            )
        return suffix

    def cells_for_identity(self, relative: str, digest: str, identity: str) -> dict[str, str]:
        """The cells for this file. Hash identity does not fall through to the path."""
        found = self.row_for(relative, digest, identity)
        if found is None:
            return {}
        return found[1]

    def row_for(
        self,
        relative: str,
        digest: str,
        identity: str,
    ) -> tuple[str, dict[str, str]] | None:
        """The stored path and cells, or None when this identity has no row."""
        if identity == IDENTITY_HASH and digest:
            for line in self.raw_rows:
                if line.sha != digest:
                    continue
                if line.path in self.rows and self.row_sha.get(line.path) == digest:
                    return line.path, self.rows[line.path]
                return line.path, line.cells
            return None
        cells = self.rows.get(relative)
        if cells is None:
            return None
        return relative, cells

    def _structural_rewrite(self) -> bool:
        if self.missing or self.blank:
            return False
        if self._path_sets:
            return True
        for path, digest in self._sha_sets.items():
            current = self.row_sha.get(path, "")
            if current and current != digest:
                return True
        if (
            self.columns is not None
            and KIND_CSV_SHA in self.columns
            and self._sha_sets
        ):
            return True
        return False

    def _needs_sha_insert(self) -> bool:
        if self.missing or self.blank or self.columns is None:
            return False
        if KIND_CSV_SHA in self.columns:
            return False
        return bool(self._pending or self._sha_sets)

    def _commit_rewrite(self, dry_run: bool, logger: logging.Logger) -> None:
        adding_sha = self.columns is not None and KIND_CSV_SHA not in self.columns
        if adding_sha and dry_run:
            logger.info("Would add column SHA to kind file %s", self.path)
        if self._extra_columns and dry_run:
            logger.info(
                "Would add columns %s to kind file %s",
                ", ".join(self._extra_columns),
                self.path,
            )
        if self._pending and dry_run:
            logger.info("Would append %s rows to kind file %s", len(self._pending), self.path)
        if dry_run:
            return
        self._apply_edits()
        self._ensure_sha_column()
        if self._extra_columns:
            self.columns = tuple(self.columns or ()) + tuple(self._extra_columns)
            self._extra_columns.clear()
        self.save()
        self._pending.clear()
        if adding_sha:
            logger.debug("Added column SHA to kind file %s", self.path)

    def _apply_edits(self) -> None:
        for old, new, digest in self._path_sets:
            self._retarget(old, new, digest)
        for path, digest in self._sha_sets.items():
            self._remember_sha(path, digest)
        for relative, digest in self._pending:
            self._add_line(relative, digest)
        self._pending.clear()
        self._path_sets.clear()
        self._sha_sets.clear()

    def _retarget(self, old: str, new: str, digest: str) -> None:
        for line in self.raw_rows:
            if line.sha == digest and line.path == old:
                line.path = new
                break
        cells = self.rows.pop(old, None)
        self.row_sha.pop(old, None)
        if cells is None:
            cells = {}
        self.rows[new] = cells
        self.row_sha[new] = digest

    def _add_line(self, relative: str, digest: str) -> None:
        if relative not in self.rows:
            cells: dict[str, str] = {}
            self.rows[relative] = cells
            self.row_sha[relative] = digest
            self.raw_rows.append(KindLine(relative, digest, cells))
            return
        self.raw_rows.append(KindLine(relative, digest, {}))

    def _remember_sha(self, relative: str, digest: str) -> None:
        self.row_sha[relative] = digest
        for line in self.raw_rows:
            if line.path == relative:
                line.sha = digest
                return

    def _ensure_sha_column(self) -> None:
        columns = list(self.columns or (KIND_CSV_PATH,))
        if KIND_CSV_SHA in columns:
            self.columns = tuple(columns)
            return
        if columns and columns[0] == KIND_CSV_PATH:
            columns.insert(1, KIND_CSV_SHA)
        else:
            columns.insert(0, KIND_CSV_SHA)
        self.columns = tuple(columns)

    def _insert_sha_column(self) -> None:
        raw = self.path.read_bytes()
        bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        text = raw.decode("utf-8-sig")
        values = ChainMap(self._sha_sets, self.row_sha)
        updated, filled = CSV.insert_sha(text, self.sep, values)
        for relative in filled:
            self._remember_sha(relative, values[relative])
        self._replace_bytes(bom + updated.encode("utf-8"))
        self._ensure_sha_column()
        self._sha_sets.clear()

    def _replace_bytes(self, payload: bytes) -> None:
        self._require_parent()
        temporary = self.path.parent / f".{self.path.name}.tmp"
        temporary.write_bytes(payload)
        temporary.replace(self.path)

    def _plan_notes(self, logger: logging.Logger) -> None:
        if not self._notes:
            return
        hash_groups: dict[str, list[tuple[str, int]]] = {}
        hash_seen = False
        for relative, digest, identity, index in self._notes:
            if identity != IDENTITY_HASH:
                continue
            hash_seen = True
            hash_groups.setdefault(digest, []).append((relative, index))
        skipped: set[str] = set()
        for digest, group in hash_groups.items():
            paths: list[str] = []
            for path, _index in sorted(group, key=lambda item: (item[1], item[0])):
                if path not in paths:
                    paths.append(path)
            if len(paths) < 2:
                continue
            logger.warning(
                "Kind file %s hash %s is shared by %s",
                self.path,
                digest,
                ", ".join(paths),
            )
            skipped.add(digest)
        if hash_seen:
            live = {relative for relative, _digest, _identity, _index in self._notes}
            warned: set[str] = set()
            for line in self.raw_rows:
                if line.sha or line.path in live or line.path in warned:
                    continue
                warned.add(line.path)
                logger.warning("Kind file %s path %s was not remapped", self.path, line.path)
        for relative, digest, identity, _index in self._notes:
            if identity == IDENTITY_HASH:
                if digest in skipped:
                    continue
                self._note_hash(relative, digest, logger)
                continue
            self._note_path(relative, digest, logger)

    def _note_path(self, relative: str, digest: str, logger: logging.Logger) -> None:
        if relative in self.rows or self._pending_sha(relative) is not None:
            current = self._sha_sets.get(relative, self._pending_sha(relative))
            if current is None:
                current = self.row_sha.get(relative, "")
            if current != digest:
                if current:
                    logger.warning('hash was "%s", now "%s" for path %s', current, digest, relative)
                if relative in self.rows:
                    self._sha_sets[relative] = digest
                else:
                    self._replace_pending(relative, digest)
            return
        self._queue_append(relative, digest)

    def _note_hash(self, relative: str, digest: str, logger: logging.Logger) -> None:
        matches = [line for line in self.raw_rows if line.sha == digest]
        pending = [path for path, sha in self._pending if sha == digest]
        if matches:
            old = matches[0].path
            if old == relative:
                return
            if self._path_owned(relative, old):
                raise VarConfigError(
                    f"Kind file {self.path} hash {digest} is on {old} and {relative}",
                    advice="Another row already uses that path.",
                )
            logger.warning('path was "%s", now "%s" for hash %s', old, relative, digest)
            self._path_sets.append((old, relative, digest))
            return
        if pending:
            return
        current = self.row_sha.get(relative, "")
        if relative in self.rows and current == "":
            self._sha_sets[relative] = digest
            return
        if relative in self.rows and current not in ("", digest):
            logger.warning(
                "Kind file %s path %s now has hash %s and the old row was kept",
                self.path,
                relative,
                digest,
            )
            self._queue_append(relative, digest)
            return
        self._queue_append(relative, digest)

    def _path_owned(self, relative: str, except_path: str) -> bool:
        if relative == except_path:
            return False
        if relative in self.rows:
            return True
        return any(path == relative for path, _sha in self._pending)

    def _pending_sha(self, relative: str) -> str | None:
        for path, digest in self._pending:
            if path == relative:
                return digest
        return None

    def _replace_pending(self, relative: str, digest: str) -> None:
        self._pending = [
            (path, digest if path == relative else current) for path, current in self._pending
        ]

    def _queue_append(self, relative: str, digest: str) -> None:
        mark = (relative, digest)
        if mark in self._pending_seen:
            return
        if relative in self.rows and self.row_sha.get(relative, "") == digest and digest:
            return
        self._pending.append(mark)
        self._pending_seen.add(mark)

    def _reject_duplicate_sha(self) -> None:
        seen: dict[str, str] = {}
        for line in self.raw_rows:
            if not line.sha:
                continue
            previous = seen.get(line.sha)
            if previous is not None:
                raise VarConfigError(
                    f"Kind file {self.path} hash {line.sha} is on {previous} and {line.path}",
                    advice="One hash identifies one row. Remove the extra row.",
                )
            seen[line.sha] = line.path


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
        identity: Mapping[str, str] | None = None,
        default_identity: str = IDENTITY_PATH,
    ) -> None:
        self._templates = templates
        self._root = root_dir
        self._profile_scope = profile_scope
        self._mode = mode
        self._dates = date_format
        self._sep = sep
        self._dry_run = dry_run
        self._identity = dict(identity or {})
        self._default_identity = default_identity
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
        identity: Mapping[str, str] | None = None,
        default_identity: str = IDENTITY_PATH,
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
        return cls(
            templates,
            root_dir,
            profile_scope,
            mode,
            date_format,
            sep,
            dry_run,
            identity,
            default_identity,
        )

    def bind_catalog(self, catalog: VarCatalog) -> None:
        """Use this catalog when a kind file is chosen."""
        self._catalog = catalog

    @property
    def templates(self) -> tuple[str, ...]:
        """Config path templates. A kind feed_file replaces this list."""
        return self._templates

    @property
    def mode(self) -> str:
        """Kind file mode for this profile."""
        return self._mode

    def path_for(self, kind: str, input_dir: Path) -> Path | None:
        """The winning file, or the first template when every candidate is missing."""
        table = self.open_table(kind, input_dir, create=False)
        if table is not None:
            return table.path
        templates = self.templates_for(kind)
        if not templates:
            return None
        scope = dict(self._profile_scope)
        scope[VAR_MATCH] = ScopeObject({FIELD_KIND: kind}, FIELD_KIND)
        scope[VAR_INPUT] = ScopeObject({FIELD_PATH: str(input_dir)}, FIELD_PATH)
        return self._render_path(templates[0], scope)

    def found_path(self, kind: str, input_dir: Path) -> Path | None:
        """The winning file when it is on disk. None when it is not."""
        table = self.open_table(kind, input_dir, create=False)
        if table is None or not table.path.is_file():
            return None
        return table.path.resolve()

    def templates_for(self, kind: str) -> tuple[str, ...]:
        """Path templates for one kind. A set feed_file replaces the config list."""
        catalog = self._catalog
        if catalog is not None:
            schema = catalog.kind_schema(kind)
            if schema is not None and schema.feed_file is not None:
                return schema.feed_file
        return self._templates

    def stage_identity(self) -> None:
        """Apply queued path and hash edits in memory. Does not write."""
        for table in self._tables.values():
            table._apply_edits()

    def reload_tables(self) -> None:
        """Reread every loaded kind file after an identity write."""
        for table in self._tables.values():
            table.reload(self._logger)

    @property
    def dates(self) -> KindDateFormat:
        """Format used to read and write a date cell."""
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

    def identity_for(self, rule: str) -> str:
        """The first record_identity step for this match rule."""
        return self._identity.get(rule, self._default_identity)

    def cells_for(
        self,
        kind: str,
        input_dir: Path,
        relative: str,
        match: FileMatch,
        digest: str,
    ) -> KindRow:
        """Return the literal cells for one file. auto and always record the file."""
        if self._mode == KIND_MODE_DISABLED:
            return KindRow(None, {})
        table = self.open_table(
            kind,
            input_dir,
            create=self._mode == KIND_MODE_ALWAYS,
        )
        if table is None:
            return KindRow(None, {})
        identity = self.identity_for(match.rule)
        cells = self._literals(
            table.cells_for_identity(relative, digest, identity),
            match,
            relative,
        )
        if self._mode in (KIND_MODE_AUTO, KIND_MODE_ALWAYS):
            table.note(relative, digest, identity, match.index)
        return KindRow(str(table.path), cells)

    def commit(self) -> None:
        """Write queued rows once. A failed resolve never reaches this."""
        writable = self._mode in (KIND_MODE_AUTO, KIND_MODE_ALWAYS)
        tables = list(self._tables.values())
        if writable:
            for table in tables:
                table.prepare_identity(self._logger)
        for table in tables:
            table.commit(self._dry_run, self._logger, writable=writable)

    def _find_table(self, kind: str, input_dir: Path, *, create: bool) -> KindTable | None:
        templates = self.templates_for(kind)
        if not templates:
            self._logger.debug("No kind_overrides_config for kind %s", kind)
            return None
        scope = dict(self._profile_scope)
        scope[VAR_MATCH] = ScopeObject({FIELD_KIND: kind}, FIELD_KIND)
        scope[VAR_INPUT] = ScopeObject({FIELD_PATH: str(input_dir)}, FIELD_PATH)
        rendered: list[Path] = []
        for template in templates:
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
                    advice="Point the kind file at a csv file.",
                )
            return self._with_headers(self._load_existing(path, kind), kind)
        if create and rendered:
            return self._with_headers(
                self._hold(KindTable.missing(rendered[0], self._sep)),
                kind,
            )
        return None

    def _with_headers(self, table: KindTable, kind: str) -> KindTable:
        catalog = self._catalog
        if catalog is None:
            return table
        feeds, schema = catalog.csv_create_groups(kind)
        table.add_schema_columns(schema)
        if table.missing or table.blank:
            table.set_fresh_feeds(feeds)
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
        catalog = self._catalog
        for key, value in raw.items():
            if KindTable.is_feed_column(key):
                continue
            if catalog is None or catalog.type_of(match.kind, key) != TYPE_DATE:
                parsed[key] = value
                continue
            try:
                parsed[key] = self._dates.store(value)
            except ValueError as exc:
                raise VarResolveError(
                    f"Profile {match.profile} input {match.index} path {relative} "
                    f"variable {key} failed",
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


