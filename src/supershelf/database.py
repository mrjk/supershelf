"""One sqlite file per profile. Rows are kept. Events are appended."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from supershelf.constants import (
    EVENT_GENERATION,
    EVENT_MISSING,
    EVENT_MOVE,
    EVENT_NEW,
    EVENT_OUTPUT,
    EVENT_PRESENT,
    EVENT_UNMATCHED,
    EVENT_VARS,
    IDENTITY_HASH,
    IDENTITY_PATH,
    OP_COPY,
    OP_HARDLINK,
    OP_SYMLINK,
    OUTPUT_OPERATIONS,
    PRESENCE_MISSING,
    PRESENCE_PRESENT,
    PRESENCE_UNMATCHED,
    SCHEMA_VERSION,
    STATUS_REFRESH,
)
from supershelf.errors import DatabaseError

_FILE_COLUMNS = (
    "input_index",
    "input_path",
    "path",
    "hash",
    "mtime",
    "ctime",
    "match_kind",
    "rule",
    "file_dir",
    "file_name",
    "file_stem",
    "file_ext",
    "vars_json",
)

_SCHEMA = """
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE contents (
  hash TEXT PRIMARY KEY
);
CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  presence TEXT NOT NULL CHECK (presence IN ('present', 'missing', 'unmatched')),
  generation INTEGER NOT NULL,
  hash TEXT NOT NULL REFERENCES contents(hash),
  input_index INTEGER NOT NULL,
  input_path TEXT NOT NULL,
  path TEXT NOT NULL,
  mtime TEXT,
  ctime TEXT,
  match_kind TEXT NOT NULL,
  rule TEXT NOT NULL,
  file_dir TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_stem TEXT NOT NULL,
  file_ext TEXT NOT NULL,
  vars_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX documents_live_location
  ON documents(input_path, path)
  WHERE presence != 'missing';
CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id),
  seq INTEGER NOT NULL,
  event TEXT NOT NULL CHECK (
    event IN (
      'new', 'move', 'generation', 'vars', 'missing', 'present', 'unmatched', 'output'
    )
  ),
  identity TEXT NOT NULL CHECK (identity IN ('path', 'hash')),
  recorded_at TEXT NOT NULL,
  generation INTEGER NOT NULL,
  hash TEXT NOT NULL,
  input_index INTEGER NOT NULL,
  input_path TEXT NOT NULL,
  path TEXT NOT NULL,
  mtime TEXT,
  ctime TEXT,
  match_kind TEXT NOT NULL,
  rule TEXT NOT NULL,
  file_dir TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_stem TEXT NOT NULL,
  file_ext TEXT NOT NULL,
  vars_json TEXT NOT NULL,
  output_name TEXT,
  operation TEXT,
  destination TEXT,
  source_hash TEXT,
  previous_json TEXT,
  UNIQUE(document_id, seq)
);
CREATE INDEX events_hash ON events(hash);
CREATE INDEX events_destination ON events(destination);
"""

_CONTENT_META = """
CREATE TABLE content_meta (
  hash TEXT NOT NULL REFERENCES contents(hash),
  driver TEXT NOT NULL,
  options_key TEXT NOT NULL,
  payload TEXT,
  error TEXT,
  extracted_at TEXT NOT NULL,
  PRIMARY KEY (hash, driver, options_key)
)
"""

_SCHEMA += _CONTENT_META + ";\n"

_READABLE_SCHEMA = frozenset({"1", "2"})
_SCHEMA_ADVICE = (
    "Point config.database_file at a new path. This supershelf reads schema 1 and schema 2."
)

_EVENT_FOR_STATUS = {
    EVENT_NEW: EVENT_NEW,
    EVENT_MOVE: EVENT_MOVE,
    EVENT_GENERATION: EVENT_GENERATION,
    EVENT_VARS: EVENT_VARS,
    EVENT_MISSING: EVENT_MISSING,
    EVENT_PRESENT: EVENT_PRESENT,
    EVENT_UNMATCHED: EVENT_UNMATCHED,
}


class _StoredFacts(Protocol):
    """Attributes copied onto a StoredFile."""

    input_index: int
    input_path: str
    path: str
    hash: str
    mtime: str | None
    ctime: str | None
    match_kind: str
    rule: str
    file_dir: str
    file_name: str
    file_stem: str
    file_ext: str
    vars_json: str


@dataclass(frozen=True)
class StoredFile:
    """File facts stored on a document and on each event."""

    input_index: int
    input_path: str
    path: str
    hash: str
    mtime: str | None
    ctime: str | None
    match_kind: str
    rule: str
    file_dir: str
    file_name: str
    file_stem: str
    file_ext: str
    vars_json: str

    @classmethod
    def from_facts(cls, source: _StoredFacts) -> StoredFile:
        """Copy the shared file columns from a live file or a document row."""
        return cls(
            input_index=source.input_index,
            input_path=source.input_path,
            path=source.path,
            hash=source.hash,
            mtime=source.mtime,
            ctime=source.ctime,
            match_kind=source.match_kind,
            rule=source.rule,
            file_dir=source.file_dir,
            file_name=source.file_name,
            file_stem=source.file_stem,
            file_ext=source.file_ext,
            vars_json=source.vars_json,
        )

    def values(self) -> tuple[object, ...]:
        """Column values in `_FILE_COLUMNS` order."""
        return (
            self.input_index,
            self.input_path,
            self.path,
            self.hash,
            self.mtime,
            self.ctime,
            self.match_kind,
            self.rule,
            self.file_dir,
            self.file_name,
            self.file_stem,
            self.file_ext,
            self.vars_json,
        )


@dataclass(frozen=True)
class DatabaseChange:
    """One planned write. `refresh` updates the document and adds no event."""

    status: str
    document_id: int | None
    generation: int
    file: StoredFile
    identity: str


@dataclass(frozen=True)
class DocumentRow:
    """Current projection of one document."""

    id: int
    presence: str
    generation: int
    hash: str
    input_index: int
    input_path: str
    path: str
    mtime: str | None
    ctime: str | None
    match_kind: str
    rule: str
    file_dir: str
    file_name: str
    file_stem: str
    file_ext: str
    vars_json: str
    updated_at: str

    @classmethod
    def from_sql(cls, row: sqlite3.Row) -> DocumentRow:
        """Build a row from a `documents` select."""
        return cls(
            id=row["id"],
            presence=row["presence"],
            generation=row["generation"],
            hash=row["hash"],
            input_index=row["input_index"],
            input_path=row["input_path"],
            path=row["path"],
            mtime=row["mtime"],
            ctime=row["ctime"],
            match_kind=row["match_kind"],
            rule=row["rule"],
            file_dir=row["file_dir"],
            file_name=row["file_name"],
            file_stem=row["file_stem"],
            file_ext=row["file_ext"],
            vars_json=row["vars_json"],
            updated_at=row["updated_at"],
        )

    def file(self) -> StoredFile:
        """The facts this projection would write onto a later event."""
        return StoredFile.from_facts(self)


@dataclass(frozen=True)
class EventRow:
    """One append-only history row."""

    id: int
    document_id: int
    seq: int
    event: str
    identity: str
    recorded_at: str
    generation: int
    hash: str
    input_index: int
    input_path: str
    path: str
    mtime: str | None
    ctime: str | None
    match_kind: str
    rule: str
    file_dir: str
    file_name: str
    file_stem: str
    file_ext: str
    vars_json: str
    output_name: str | None
    operation: str | None
    destination: str | None
    source_hash: str | None
    previous_json: str | None

    @classmethod
    def from_sql(cls, row: sqlite3.Row) -> EventRow:
        """Build a row from an `events` select."""
        return cls(
            id=row["id"],
            document_id=row["document_id"],
            seq=row["seq"],
            event=row["event"],
            identity=row["identity"],
            recorded_at=row["recorded_at"],
            generation=row["generation"],
            hash=row["hash"],
            input_index=row["input_index"],
            input_path=row["input_path"],
            path=row["path"],
            mtime=row["mtime"],
            ctime=row["ctime"],
            match_kind=row["match_kind"],
            rule=row["rule"],
            file_dir=row["file_dir"],
            file_name=row["file_name"],
            file_stem=row["file_stem"],
            file_ext=row["file_ext"],
            vars_json=row["vars_json"],
            output_name=row["output_name"],
            operation=row["operation"],
            destination=row["destination"],
            source_hash=row["source_hash"],
            previous_json=row["previous_json"],
        )


@dataclass(frozen=True)
class OutputPrevious:
    """What revert needs to know about a destination before an output apply."""

    existed: bool
    ours: bool
    operation: str | None = None
    source_hash: str | None = None

    def as_json(self) -> str:
        """The `previous_json` object. `ours` carries the prior operation and hash."""
        if self.ours:
            if self.operation not in OUTPUT_OPERATIONS or not self.source_hash:
                raise DatabaseError(
                    "An output event that replaces our file needs operation and source_hash",
                    advice="Set operation to copy, symlink, or hardlink, and set source_hash.",
                )
        body: dict[str, object] = {"existed": self.existed, "ours": self.ours}
        if self.ours:
            body["operation"] = self.operation
            body["source_hash"] = self.source_hash
        return json.dumps(body, sort_keys=True)


class ShelfDatabase:
    """The sqlite file at one profile's `database_file`."""

    def __init__(
        self,
        path: Path,
        connection: sqlite3.Connection | None,
        *,
        writable: bool,
    ) -> None:
        self.path = path
        self._connection = connection
        self.writable = writable

    def close(self) -> None:
        """Close the connection. A missing file has nothing to close."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> ShelfDatabase:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @classmethod
    def open_read(cls, path: Path, *, timeout: float = 1.0) -> ShelfDatabase:
        """Read an existing file, or an empty view when the file is absent.

        An absent file is not created. An existing file is opened read-only.
        """
        if not path.exists():
            return cls(path, None, writable=False)
        if path.is_dir():
            raise DatabaseError(
                f"Database path is a directory: {path}",
                advice="Point config.database_file at a file path.",
            )
        try:
            connection = sqlite3.connect(
                path.resolve().as_uri() + "?mode=ro",
                uri=True,
                timeout=timeout,
            )
        except sqlite3.Error as exc:
            raise cls._file_error(path) from exc
        connection.row_factory = sqlite3.Row
        database = cls(path, connection, writable=False)
        try:
            database._require_version()
        except DatabaseError:
            database.close()
            raise
        return database

    @classmethod
    def open_write(cls, path: Path, *, timeout: float = 1.0) -> ShelfDatabase:
        """Create the parent directory and the schema, then open for writing."""
        parent = path.parent
        if parent.exists() and not parent.is_dir():
            raise DatabaseError(
                f"Database parent is not a directory: {parent}",
                advice="Point config.database_file at a path whose parent is a directory.",
            )
        if path.exists() and path.is_dir():
            raise DatabaseError(
                f"Database path is a directory: {path}",
                advice="Point config.database_file at a file path.",
            )
        parent.mkdir(parents=True, exist_ok=True)
        try:
            connection = sqlite3.connect(path, timeout=timeout)
        except sqlite3.Error as exc:
            raise cls._file_error(path) from exc
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        database = cls(path, connection, writable=True)
        try:
            database._ensure_schema()
        except DatabaseError:
            database.close()
            raise
        return database

    def documents(self) -> list[DocumentRow]:
        """Current rows, in id order. An uncreated file has none."""
        if self._connection is None:
            return []
        rows = self._connection.execute(
            "SELECT * FROM documents ORDER BY id"
        ).fetchall()
        return [DocumentRow.from_sql(row) for row in rows]

    def events(self, document_id: int | None = None) -> list[EventRow]:
        """Events in id order. Pass a document id to keep that document's seq order."""
        if self._connection is None:
            return []
        if document_id is None:
            rows = self._connection.execute(
                "SELECT * FROM events ORDER BY id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM events WHERE document_id = ? ORDER BY seq",
                (document_id,),
            ).fetchall()
        return [EventRow.from_sql(row) for row in rows]

    def events_for_destination(self, destination: str) -> list[EventRow]:
        """Output events for one absolute destination, in id order."""
        if self._connection is None:
            return []
        rows = self._connection.execute(
            "SELECT * FROM events WHERE destination = ? ORDER BY id",
            (destination,),
        ).fetchall()
        return [EventRow.from_sql(row) for row in rows]

    def identity(self) -> str | None:
        """The rule stored by the last successful run, or None."""
        if self._connection is None:
            return None
        row = self._connection.execute(
            "SELECT value FROM meta WHERE key = 'identity'"
        ).fetchone()
        if row is None:
            return None
        return str(row["value"])

    def _event_identity_word(self) -> str:
        """First step of the stored profile list. Events accept path or hash only."""
        stored = self.identity()
        if not stored:
            return IDENTITY_PATH
        word = stored.split(",", 1)[0]
        if word in (IDENTITY_PATH, IDENTITY_HASH):
            return word
        return IDENTITY_PATH

    def apply(
        self,
        changes: list[DatabaseChange],
        identity: str,
        recorded_at: str,
    ) -> None:
        """Write one run. A failure rolls this transaction back."""
        with self._transaction():
            for change in changes:
                if change.status == EVENT_MOVE:
                    self._mark_missing(change)
            for change in changes:
                self._apply_change(change, change.identity, recorded_at)
            self._set_meta("identity", identity)

    def note_identity(self, identity: str) -> None:
        """Store a new link rule when this run changes no document row."""
        with self._transaction():
            self._set_meta("identity", identity)

    def append_output(
        self,
        document_id: int,
        output_name: str,
        operation: str,
        destination: str,
        source_hash: str,
        previous: OutputPrevious,
        *,
        recorded_at: str,
    ) -> EventRow:
        """Append an output event after the file driver writes the destination.

        The document projection stays as it is. `previous` is what a later
        revert needs.
        """
        self._check_output(output_name, operation, destination, source_hash)
        payload = previous.as_json()
        with self._transaction():
            document = self._require_document(document_id)
            identity = self._event_identity_word()
            self._ensure_hash(source_hash)
            seq = self._next_seq(document_id)
            file = document.file()
            self._insert_event(
                document_id,
                seq,
                EVENT_OUTPUT,
                identity,
                recorded_at,
                document.generation,
                file,
                output_name=output_name,
                operation=operation,
                destination=destination,
                source_hash=source_hash,
                previous_json=payload,
            )
        found = self.events(document_id)[-1]
        return found

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Begin a write. Commit on success. Roll back on a database error."""
        self._require_writable()
        connection = self._begin()
        try:
            yield connection
            connection.commit()
        except DatabaseError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise self._write_error(exc) from exc

    def _require_writable(self) -> None:
        if self._connection is None or not self.writable:
            raise DatabaseError(
                f"Database is not open for writing: {self.path}",
                advice="Run db import without --dry-run.",
            )

    def _begin(self) -> sqlite3.Connection:
        connection = self._connection
        if connection is None:
            raise DatabaseError(
                f"Database is not open for writing: {self.path}",
                advice="Run db import without --dry-run.",
            )
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise self._write_error(exc) from exc
        return connection

    def _ensure_schema(self) -> None:
        connection = self._connection
        assert connection is not None
        found = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
        ).fetchone()
        if found is None:
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )
            connection.commit()
            return
        version = self._schema_version()
        if version == SCHEMA_VERSION:
            return
        if version == "1":
            self._migrate_content_meta()
            return
        self._reject_version(version)

    def _require_version(self) -> None:
        version = self._schema_version()
        if version in _READABLE_SCHEMA:
            return
        self._reject_version(version)

    def _schema_version(self) -> str | None:
        connection = self._connection
        assert connection is not None
        try:
            row = connection.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise self._file_error(self.path) from exc
        if row is None:
            return None
        return str(row["value"])

    def _reject_version(self, found: str | None) -> None:
        label = "missing" if found is None else found
        raise DatabaseError(
            f"{self.path} has database schema {label}",
            advice=_SCHEMA_ADVICE,
        )

    def _migrate_content_meta(self) -> None:
        """Add content_meta to a version 1 file and set schema_version to 2."""
        connection = self._connection
        assert connection is not None
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(_CONTENT_META)
            connection.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                (SCHEMA_VERSION,),
            )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise self._write_error(exc) from exc

    def _apply_change(
        self,
        change: DatabaseChange,
        identity: str,
        recorded_at: str,
    ) -> None:
        if change.status == STATUS_REFRESH:
            self._refresh(change, recorded_at)
            return
        if change.status == EVENT_NEW:
            self._insert_document(change, identity, recorded_at)
            return
        if change.status not in _EVENT_FOR_STATUS:
            raise DatabaseError(
                f"Unknown record change {change.status}",
                advice="Record new, move, generation, vars, missing, present, unmatched, or refresh.",
            )
        document_id = self._known_id(change)
        if change.status == EVENT_MISSING:
            presence = PRESENCE_MISSING
        elif change.status == EVENT_UNMATCHED:
            presence = PRESENCE_UNMATCHED
        else:
            presence = PRESENCE_PRESENT
        self._update_document(document_id, change, presence, recorded_at)
        self._insert_event(
            document_id,
            self._next_seq(document_id),
            _EVENT_FOR_STATUS[change.status],
            identity,
            recorded_at,
            change.generation,
            change.file,
        )

    def _mark_missing(self, change: DatabaseChange) -> None:
        document_id = self._known_id(change)
        self._require_document(document_id)
        connection = self._connection
        assert connection is not None
        connection.execute(
            "UPDATE documents SET presence = ? WHERE id = ?",
            (PRESENCE_MISSING, document_id),
        )

    def _refresh(self, change: DatabaseChange, recorded_at: str) -> None:
        document_id = self._known_id(change)
        self._require_document(document_id)
        connection = self._connection
        assert connection is not None
        connection.execute(
            """
            UPDATE documents
            SET input_index = ?, mtime = ?, ctime = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                change.file.input_index,
                change.file.mtime,
                change.file.ctime,
                recorded_at,
                document_id,
            ),
        )

    def _insert_document(
        self,
        change: DatabaseChange,
        identity: str,
        recorded_at: str,
    ) -> None:
        self._ensure_hash(change.file.hash)
        connection = self._connection
        assert connection is not None
        columns = ", ".join(("presence", "generation", *_FILE_COLUMNS, "updated_at"))
        placeholders = ", ".join("?" for _ in range(2 + len(_FILE_COLUMNS) + 1))
        cursor = connection.execute(
            f"INSERT INTO documents ({columns}) VALUES ({placeholders})",
            (PRESENCE_PRESENT, change.generation, *change.file.values(), recorded_at),
        )
        document_id = int(cursor.lastrowid)
        self._insert_event(
            document_id,
            1,
            EVENT_NEW,
            identity,
            recorded_at,
            change.generation,
            change.file,
        )

    def _update_document(
        self,
        document_id: int,
        change: DatabaseChange,
        presence: str,
        recorded_at: str,
    ) -> None:
        self._ensure_hash(change.file.hash)
        self._require_document(document_id)
        connection = self._connection
        assert connection is not None
        assignments = ", ".join(
            ("presence = ?", "generation = ?", *(f"{name} = ?" for name in _FILE_COLUMNS), "updated_at = ?")
        )
        connection.execute(
            f"UPDATE documents SET {assignments} WHERE id = ?",
            (
                presence,
                change.generation,
                *change.file.values(),
                recorded_at,
                document_id,
            ),
        )

    def _insert_event(
        self,
        document_id: int,
        seq: int,
        event: str,
        identity: str,
        recorded_at: str,
        generation: int,
        file: StoredFile,
        *,
        output_name: str | None = None,
        operation: str | None = None,
        destination: str | None = None,
        source_hash: str | None = None,
        previous_json: str | None = None,
    ) -> None:
        connection = self._connection
        assert connection is not None
        connection.execute(
            """
            INSERT INTO events (
              document_id, seq, event, identity, recorded_at, generation,
              hash, input_index, input_path, path, mtime, ctime,
              match_kind, rule, file_dir, file_name, file_stem, file_ext, vars_json,
              output_name, operation, destination, source_hash, previous_json
            ) VALUES (
              ?, ?, ?, ?, ?, ?,
              ?, ?, ?, ?, ?, ?,
              ?, ?, ?, ?, ?, ?, ?,
              ?, ?, ?, ?, ?
            )
            """,
            (
                document_id,
                seq,
                event,
                identity,
                recorded_at,
                generation,
                file.hash,
                file.input_index,
                file.input_path,
                file.path,
                file.mtime,
                file.ctime,
                file.match_kind,
                file.rule,
                file.file_dir,
                file.file_name,
                file.file_stem,
                file.file_ext,
                file.vars_json,
                output_name,
                operation,
                destination,
                source_hash,
                previous_json,
            ),
        )

    def _ensure_hash(self, digest: str) -> None:
        connection = self._connection
        assert connection is not None
        connection.execute("INSERT OR IGNORE INTO contents(hash) VALUES (?)", (digest,))

    def _require_document(self, document_id: int) -> DocumentRow:
        connection = self._connection
        assert connection is not None
        row = connection.execute(
            "SELECT * FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise DatabaseError(
                f"Document {document_id} is not in {self.path}",
                advice="Record the file before appending an output event.",
            )
        return DocumentRow.from_sql(row)

    def _known_id(self, change: DatabaseChange) -> int:
        if change.document_id is None:
            raise DatabaseError(
                f"Record change {change.status} needs a document id",
                advice="A new document is the only change without an id.",
            )
        return change.document_id

    def _next_seq(self, document_id: int) -> int:
        connection = self._connection
        assert connection is not None
        row = connection.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM events WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        return int(row[0]) + 1

    def _set_meta(self, key: str, value: str) -> None:
        connection = self._connection
        assert connection is not None
        connection.execute(
            """
            INSERT INTO meta(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def _check_output(
        self,
        output_name: str,
        operation: str,
        destination: str,
        source_hash: str,
    ) -> None:
        if not output_name or not destination or not source_hash:
            raise DatabaseError(
                "An output event needs an output name, a destination, and a source hash",
                advice="Fill output_name, destination, and source_hash.",
            )
        if operation not in (OP_COPY, OP_SYMLINK, OP_HARDLINK):
            raise DatabaseError(
                f"Output operation {operation!r} is not copy, symlink, or hardlink",
                advice="Use copy, symlink, or hardlink.",
            )

    def _write_error(self, exc: sqlite3.Error) -> DatabaseError:
        if "locked" in str(exc).lower():
            return DatabaseError(
                f"Database is locked: {self.path}",
                advice="Another record is using this file. Run this command again.",
            )
        return DatabaseError(
            f"Could not record {self.path}: {exc}",
            advice="Point config.database_file at a new path if this file is not a supershelf database.",
        )

    @staticmethod
    def _file_error(path: Path) -> DatabaseError:
        return DatabaseError(
            f"{path} is not a supershelf database",
            advice=_SCHEMA_ADVICE,
        )
