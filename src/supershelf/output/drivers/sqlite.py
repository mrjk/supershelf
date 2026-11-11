"""Sqlite export destinations: upsert hash, files, and data_<kind> rows."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from supershelf.common import render_user_path
from supershelf.constants import (
    KEY_ROOT_DIR,
    TYPE_BOOL,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INT,
    TYPE_TEXT,
    TYPE_TIME,
    VAR_CONFIG,
    VAR_NAME_PATTERN,
)
from supershelf.errors import OutputConfigError, OutputResolveError
from supershelf.output.engine import (
    SHARED_KEYS,
    STATUS_REPLACE,
    STATUS_UNCHANGED,
    STATUS_WRITE,
    OutputAction,
    OutputContext,
    OutputDriver,
    dest_source,
)
from supershelf.profile import ShelfProfile
from supershelf.vars import VarCatalog, VarSpec

_SQLITE_KEYS = SHARED_KEYS | {"path"}
_ROOT_NAME = VAR_CONFIG + "." + KEY_ROOT_DIR
_IDENT = re.compile(VAR_NAME_PATTERN)
_OP_UPSERT = "upsert"
_TABLE_HASH = "hash"
_TABLE_FILES = "files"
_FILES_COLUMNS = (
    "path",
    "file_dir",
    "file_name",
    "file_stem",
    "file_ext",
    "match_kind",
    "rule",
    "mtime",
    "ctime",
)
_DELETE_TIP = "Delete the sqlite file and re-run so the schema can be recreated."
_PAYLOAD_KEY = "export"


@dataclass
class PreparedSqlite:
    """Destination file and kind column specs. Rendered once."""

    name: str
    path: Path
    catalog: VarCatalog
    listed_kinds: list[str] | None
    kind_columns: dict[str, list[tuple[str, str]]]
    seen_hashes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExportRow:
    """One hash, files, and data_<kind> payload to compare or upsert."""

    hash: str
    kind: str
    files: dict[str, str | None]
    vars: dict[str, object | None]


class SqliteOutputDriver(OutputDriver):
    """Upsert selected documents into an external sqlite file."""

    name = "sqlite"

    def check(self, spec: Mapping[str, Any]) -> None:
        """Reject unknown keys and require a path template."""
        name = spec.get("name")
        label = name if isinstance(name, str) and name.strip() else "sqlite"
        unknown = set(spec) - _SQLITE_KEYS
        if unknown:
            listed = ", ".join(sorted(str(key) for key in unknown))
            raise OutputConfigError(
                f"Output {label!r} does not accept {listed}",
                advice="The sqlite driver accepts path.",
            )
        path = spec.get("path")
        if not isinstance(path, str) or not path.strip():
            raise OutputConfigError(
                f"Output {label!r} path is required",
                advice=f"Set path to a profile path template. A relative path resolves from {_ROOT_NAME}.",
            )
        kinds = spec.get("kinds")
        if kinds is None:
            return
        if not isinstance(kinds, list):
            return
        for kind in kinds:
            if isinstance(kind, str) and kind.strip():
                self._require_ident(kind.strip(), label, "kind")

    def prepare(self, spec: Mapping[str, Any], profile: ShelfProfile) -> PreparedSqlite:
        """Render path once. The export file is created only on a real write."""
        name = str(spec.get("name", "sqlite")).strip() or "sqlite"
        path = render_user_path(
            str(spec["path"]),
            profile.scope,
            profile.root_dir,
            empty_message=f"Output {name!r} path is empty",
            error=OutputConfigError,
            advice=f"Set path to a sqlite file under {_ROOT_NAME}.",
            resolve=True,
        )
        if path.exists() and path.is_dir():
            raise OutputConfigError(
                f"Output {name!r} path {path} is a directory",
                advice="Point path at a sqlite file.",
            )
        catalog = VarCatalog.load(profile.document)
        listed = spec.get("kinds")
        kinds: list[str] | None
        if listed is None:
            kinds = None
        else:
            kinds = [str(item).strip() for item in listed if str(item).strip()]
        kind_columns = self._kind_columns(catalog, kinds)
        return PreparedSqlite(name, path, catalog, kinds, kind_columns)

    def plan(self, prepared: Any, context: OutputContext) -> OutputAction | None:
        """Choose write, replace, or unchanged from the export row for this hash."""
        if not isinstance(prepared, PreparedSqlite):
            raise OutputResolveError(
                f"Output {context.output_name} is not a sqlite output",
                advice="This is a bug. Report it.",
            )
        kind = context.match.resolved.kind
        if not _IDENT.fullmatch(kind):
            raise OutputResolveError(
                f"Output {prepared.name!r} kind {kind!r} is not a SQL identifier",
                advice="Use a name that matches [A-Za-z_][A-Za-z0-9_]*.",
            )
        source_hash = context.match.row.file.hash
        prior_path = prepared.seen_hashes.get(source_hash)
        if prior_path is not None:
            raise OutputResolveError(
                f'Two files in this run map to the same hash "{source_hash}". '
                f"First: {dest_source(context.shelf.name, prior_path, context.output_name)}. "
                f"Second: {dest_source(context.shelf.name, context.match.found.path, context.output_name)}.",
                advice="Each hash may appear once in this sqlite output.",
            )
        prepared.seen_hashes[source_hash] = context.match.found.path
        columns = prepared.kind_columns.get(kind)
        if columns is None:
            columns = self._columns_for_kind(prepared.catalog, kind)
            prepared.kind_columns[kind] = columns
        row = self._export_row(context, columns)
        relative = row.files["path"] or context.match.found.path
        dest = prepared.path.joinpath(*relative.split("/"))
        existing = self._read_existing(prepared.path, row.kind, columns, source_hash)
        needs_schema = self._needs_schema(
            prepared.path, prepared.kind_columns, row.kind, columns
        )
        if existing is None:
            status = STATUS_WRITE
        elif needs_schema or existing != row:
            status = STATUS_REPLACE
        else:
            status = STATUS_UNCHANGED
        action = context.action(
            status=status,
            operation=_OP_UPSERT,
            dest=str(dest),
            dest_root=prepared.path,
        )
        action.extra[_PAYLOAD_KEY] = json.dumps(
            {
                "hash": row.hash,
                "kind": row.kind,
                "files": row.files,
                "vars": row.vars,
                "columns": columns,
                "ensure": [
                    {"kind": name, "columns": cols}
                    for name, cols in prepared.kind_columns.items()
                ],
            },
            sort_keys=True,
        )
        return action

    def apply(self, action: OutputAction, dry_run: bool = False) -> None:
        """Ensure the export schema and upsert one document. A dry run does neither."""
        if dry_run:
            return
        raw = action.extra.get(_PAYLOAD_KEY)
        if not raw or action.dest_root is None:
            raise OutputResolveError(
                f"Output {action.output} {action.path} cannot be written",
                advice="This is a bug. Report it.",
            )
        payload = json.loads(raw)
        path = action.dest_root
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = [(str(name), str(sql_type)) for name, sql_type in payload["columns"]]
        kind = str(payload["kind"])
        with ExportDatabase.open_write(path) as database:
            database.ensure_base()
            for item in payload.get("ensure", []):
                ensure_kind = str(item["kind"])
                ensure_columns = [
                    (str(name), str(sql_type)) for name, sql_type in item["columns"]
                ]
                database.ensure_kind(ensure_kind, ensure_columns)
            database.ensure_kind(kind, columns)
            database.upsert(
                hash_value=str(payload["hash"]),
                kind=kind,
                files=dict(payload["files"]),
                values=dict(payload["vars"]),
                columns=columns,
            )

    def _export_row(
        self,
        context: OutputContext,
        columns: Sequence[tuple[str, str]],
    ) -> ExportRow:
        stored = context.match.row.file
        resolved = context.match.resolved
        states = {name: state for name, state in resolved.states}
        values: dict[str, object | None] = {}
        for name, sql_type in columns:
            state = states.get(name)
            if state is None or state.value is None:
                values[name] = None
            else:
                values[name] = self._sql_value(state.value, sql_type)
        return ExportRow(
            hash=stored.hash,
            kind=resolved.kind,
            files={
                "path": stored.path,
                "file_dir": stored.file_dir,
                "file_name": stored.file_name,
                "file_stem": stored.file_stem,
                "file_ext": stored.file_ext,
                "match_kind": stored.match_kind,
                "rule": stored.rule,
                "mtime": stored.mtime,
                "ctime": stored.ctime,
            },
            vars=values,
        )

    def _read_existing(
        self,
        path: Path,
        kind: str,
        columns: Sequence[tuple[str, str]],
        source_hash: str,
    ) -> ExportRow | None:
        if not path.exists() or not path.is_file():
            return None
        try:
            with ExportDatabase.open_read(path) as database:
                return database.read_row(source_hash, kind, columns)
        except OutputResolveError:
            raise
        except sqlite3.Error:
            return None

    def _needs_schema(
        self,
        path: Path,
        kind_columns: Mapping[str, list[tuple[str, str]]],
        kind: str,
        columns: Sequence[tuple[str, str]],
    ) -> bool:
        if not path.exists() or not path.is_file():
            return False
        try:
            with ExportDatabase.open_read(path) as database:
                if database.missing_schema(kind_columns):
                    return True
                return database.missing_schema({kind: list(columns)})
        except OutputResolveError:
            raise
        except sqlite3.Error:
            return True

    def _kind_columns(
        self,
        catalog: VarCatalog,
        kinds: list[str] | None,
    ) -> dict[str, list[tuple[str, str]]]:
        names = kinds if kinds is not None else [kind.name for kind in catalog.kind_schemas()]
        return {kind: self._columns_for_kind(catalog, kind) for kind in names}

    @staticmethod
    def _columns_for_kind(catalog: VarCatalog, kind: str) -> list[tuple[str, str]]:
        schema = catalog.kind_schema(kind)
        if schema is None:
            return []
        return [(name, _sql_type(spec)) for name, spec in schema.vars.items()]

    @staticmethod
    def _sql_value(value: object, sql_type: str) -> object | None:
        if value is None:
            return None
        if sql_type == "INTEGER" and isinstance(value, bool):
            return 1 if value else 0
        if sql_type == "INTEGER" and isinstance(value, int) and not isinstance(value, bool):
            return value
        if sql_type == "REAL" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if sql_type == "TEXT":
            return str(value)
        return value

    @staticmethod
    def _require_ident(value: str, label: str, what: str) -> None:
        if not _IDENT.fullmatch(value):
            raise OutputConfigError(
                f"Output {label!r} {what} {value!r} is not a SQL identifier",
                advice="Use a name that matches [A-Za-z_][A-Za-z0-9_]*.",
            )


def _sql_type(spec: VarSpec) -> str:
    if spec.type in (TYPE_INT, TYPE_BOOL):
        return "INTEGER"
    if spec.type == TYPE_FLOAT:
        return "REAL"
    if spec.type in (TYPE_TEXT, TYPE_DATE, TYPE_TIME, TYPE_DATETIME):
        return "TEXT"
    return "TEXT"


def _quote(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _data_table(kind: str) -> str:
    return f"data_{kind}"


class ExportDatabase:
    """One external export sqlite file."""

    def __init__(self, connection: sqlite3.Connection, path: Path) -> None:
        self._connection = connection
        self._path = path

    @classmethod
    def open_read(cls, path: Path) -> ExportDatabase:
        """Open an existing export file read-only."""
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return cls(connection, path)

    @classmethod
    def open_write(cls, path: Path) -> ExportDatabase:
        """Open or create the export file for schema sync and upserts."""
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return cls(connection, path)

    def __enter__(self) -> ExportDatabase:
        return self

    def __exit__(self, *args: object) -> None:
        self._connection.close()

    def ensure_base(self) -> None:
        """Create or verify the hash and files tables."""
        self._ensure_table(
            _TABLE_HASH,
            [("hash", "TEXT")],
            primary_key="hash",
        )
        files_cols = [("hash", "TEXT"), *((name, "TEXT") for name in _FILES_COLUMNS)]
        self._ensure_table(
            _TABLE_FILES,
            files_cols,
            primary_key="hash",
            references=(_TABLE_HASH, "hash"),
        )

    def ensure_kind(self, kind: str, columns: Sequence[tuple[str, str]]) -> None:
        """Create or sync one data_<kind> table to the kind schema."""
        table = _data_table(kind)
        expected = [("hash", "TEXT"), *columns]
        self._ensure_table(
            table,
            expected,
            primary_key="hash",
            references=(_TABLE_HASH, "hash"),
        )

    def missing_schema(
        self,
        kind_columns: Mapping[str, Sequence[tuple[str, str]]],
    ) -> bool:
        """True when base tables or a kind table is missing an expected column."""
        if not self._table_exists(_TABLE_HASH) or not self._table_exists(_TABLE_FILES):
            return True
        files_cols = self._columns(_TABLE_FILES)
        for name in ("hash", *_FILES_COLUMNS):
            if name not in files_cols:
                return True
        for kind, columns in kind_columns.items():
            table = _data_table(kind)
            if not self._table_exists(table):
                return True
            existing = self._columns(table)
            if "hash" not in existing:
                return True
            for name, sql_type in columns:
                found = existing.get(name)
                if found is None:
                    return True
                if found.upper() != sql_type.upper():
                    raise OutputResolveError(
                        f"Export {self._path} table {table} column {name} is {found}, expected {sql_type}",
                        advice=_DELETE_TIP,
                    )
        return False

    def read_row(
        self,
        hash_value: str,
        kind: str,
        columns: Sequence[tuple[str, str]],
    ) -> ExportRow | None:
        """The stored export row for this hash, or None when missing."""
        if not self._table_exists(_TABLE_HASH):
            return None
        found = self._connection.execute(
            f"SELECT hash FROM {_quote(_TABLE_HASH)} WHERE hash = ?",
            (hash_value,),
        ).fetchone()
        if found is None:
            return None
        if not self._table_exists(_TABLE_FILES):
            return None
        files_row = self._connection.execute(
            f"SELECT * FROM {_quote(_TABLE_FILES)} WHERE hash = ?",
            (hash_value,),
        ).fetchone()
        if files_row is None:
            return None
        files = {name: files_row[name] for name in _FILES_COLUMNS}
        values: dict[str, object | None] = {name: None for name, _sql in columns}
        table = _data_table(kind)
        if self._table_exists(table):
            data_row = self._connection.execute(
                f"SELECT * FROM {_quote(table)} WHERE hash = ?",
                (hash_value,),
            ).fetchone()
            if data_row is not None:
                available = set(data_row.keys())
                for name, _sql in columns:
                    if name in available:
                        values[name] = data_row[name]
        return ExportRow(hash=hash_value, kind=kind, files=files, vars=values)

    def upsert(
        self,
        *,
        hash_value: str,
        kind: str,
        files: Mapping[str, object | None],
        values: Mapping[str, object | None],
        columns: Sequence[tuple[str, str]],
    ) -> None:
        """Insert or replace hash, files, and data_<kind> for one document."""
        self._connection.execute("BEGIN")
        try:
            self._connection.execute(
                f"INSERT INTO {_quote(_TABLE_HASH)} (hash) VALUES (?) "
                f"ON CONFLICT(hash) DO NOTHING",
                (hash_value,),
            )
            file_names = ["hash", *_FILES_COLUMNS]
            file_values = [hash_value, *[files.get(name) for name in _FILES_COLUMNS]]
            placeholders = ", ".join("?" for _ in file_names)
            assignments = ", ".join(
                f"{_quote(name)} = excluded.{_quote(name)}" for name in _FILES_COLUMNS
            )
            self._connection.execute(
                f"INSERT INTO {_quote(_TABLE_FILES)} ({', '.join(_quote(n) for n in file_names)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT(hash) DO UPDATE SET {assignments}",
                file_values,
            )
            table = _data_table(kind)
            data_names = ["hash", *[name for name, _sql in columns]]
            data_values = [hash_value, *[values.get(name) for name, _sql in columns]]
            data_placeholders = ", ".join("?" for _ in data_names)
            if columns:
                data_assignments = ", ".join(
                    f"{_quote(name)} = excluded.{_quote(name)}" for name, _sql in columns
                )
                update_sql = f"ON CONFLICT(hash) DO UPDATE SET {data_assignments}"
            else:
                update_sql = "ON CONFLICT(hash) DO NOTHING"
            self._connection.execute(
                f"INSERT INTO {_quote(table)} ({', '.join(_quote(n) for n in data_names)}) "
                f"VALUES ({data_placeholders}) {update_sql}",
                data_values,
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _ensure_table(
        self,
        table: str,
        columns: Sequence[tuple[str, str]],
        *,
        primary_key: str,
        references: tuple[str, str] | None = None,
    ) -> None:
        if not self._table_exists(table):
            parts = [f"{_quote(name)} {sql_type}" for name, sql_type in columns]
            parts.append(f"PRIMARY KEY ({_quote(primary_key)})")
            if references is not None:
                ref_table, ref_col = references
                parts.append(
                    f"FOREIGN KEY ({_quote(primary_key)}) "
                    f"REFERENCES {_quote(ref_table)}({_quote(ref_col)})"
                )
            self._connection.execute(
                f"CREATE TABLE {_quote(table)} ({', '.join(parts)})"
            )
            return
        existing = self._columns(table)
        expected = {name: sql_type for name, sql_type in columns}
        for name, sql_type in expected.items():
            found = existing.get(name)
            if found is None:
                self._connection.execute(
                    f"ALTER TABLE {_quote(table)} ADD COLUMN {_quote(name)} {sql_type}"
                )
                continue
            if found.upper() != sql_type.upper():
                raise OutputResolveError(
                    f"Export {self._path} table {table} column {name} is {found}, expected {sql_type}",
                    advice=_DELETE_TIP,
                )

    def _table_exists(self, table: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    def _columns(self, table: str) -> dict[str, str]:
        rows = self._connection.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
        return {str(row["name"]): str(row["type"] or "TEXT") for row in rows}
