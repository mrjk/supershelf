"""Profile sqlite file: schema, rollback, and read-only open."""

import sqlite3
from pathlib import Path

import pytest

from supershelf.constants import (
    EVENT_NEW,
    EVENT_OUTPUT,
    EVENT_VARS,
    OP_SYMLINK,
    SCHEMA_VERSION,
    STATUS_REFRESH,
)
from supershelf.database import (
    DatabaseChange,
    OutputPrevious,
    ShelfDatabase,
    StoredFile,
)
from supershelf.errors import DatabaseError


def _file(**overrides: object) -> StoredFile:
    values: dict[str, object] = {
        "input_index": 1,
        "input_path": "/inbox",
        "path": "bill.pdf",
        "hash": "a" * 64,
        "mtime": "2026-04-25T00:00:00+00:00",
        "ctime": "2026-04-25T00:00:00+00:00",
        "match_kind": "bill",
        "rule": "bill",
        "file_dir": "",
        "file_name": "bill.pdf",
        "file_stem": "bill",
        "file_ext": "pdf",
        "vars_json": '{"vendor":{"display":"Bank2000","type":"text","value":"Bank2000","value_sources":["default"]}}',
    }
    values.update(overrides)
    return StoredFile(**values)  # type: ignore[arg-type]


def _new(**overrides: object) -> DatabaseChange:
    return DatabaseChange(
        status=EVENT_NEW,
        document_id=None,
        generation=1,
        file=_file(**overrides),
        identity="path",
    )


def test_read_of_a_missing_file_creates_nothing(tmp_path: Path) -> None:
    path = tmp_path / "profile.work.sqlite"
    with ShelfDatabase.open_read(path) as database:
        assert database.documents() == []
        assert database.events() == []
        assert database.identity() is None
    assert path.exists() is False


def test_write_creates_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "profile.work.sqlite"
    with ShelfDatabase.open_write(path) as database:
        database.apply([_new()], "path", "2026-04-25T00:00:00+00:00")
        documents = database.documents()
        events = database.events()
    assert path.is_file()
    assert documents[0].id == 1
    assert documents[0].presence == "present"
    assert documents[0].hash == "a" * 64
    assert events[0].event == EVENT_NEW
    assert events[0].seq == 1
    assert events[0].identity == "path"
    raw = sqlite3.connect(path)
    version = raw.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    raw.close()
    assert version[0] == SCHEMA_VERSION


def test_failed_apply_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "profile.work.sqlite"
    with ShelfDatabase.open_write(path) as database:
        database.apply([_new()], "path", "2026-04-25T00:00:00+00:00")
        with pytest.raises(DatabaseError, match="Document 9"):
            database.apply(
                [
                    DatabaseChange(
                        status=EVENT_VARS,
                        document_id=9,
                        generation=1,
                        file=_file(),
                        identity="path",
                    )
                ],
                "path",
                "2026-04-25T00:00:01+00:00",
            )
        documents = database.documents()
        events = database.events()
    assert [item.id for item in documents] == [1]
    assert [item.event for item in events] == [EVENT_NEW]


def test_read_only_open_does_not_create_a_journal(tmp_path: Path) -> None:
    path = tmp_path / "profile.work.sqlite"
    with ShelfDatabase.open_write(path) as database:
        database.apply([_new()], "path", "2026-04-25T00:00:00+00:00")
    before = {item.name for item in tmp_path.iterdir()}
    with ShelfDatabase.open_read(path) as database:
        assert database.writable is False
        assert len(database.documents()) == 1
        with pytest.raises(DatabaseError, match="not open for writing"):
            database.apply([], "path", "2026-04-25T00:00:01+00:00")
    after = {item.name for item in tmp_path.iterdir()}
    assert after == before
    assert not any(name.endswith(("-journal", "-wal", "-shm")) for name in after)


def test_foreign_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "profile.work.sqlite"
    path.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(DatabaseError, match="not a supershelf database"):
        ShelfDatabase.open_read(path)


def test_wrong_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "profile.work.sqlite"
    with ShelfDatabase.open_write(path) as database:
        database.apply([_new()], "path", "2026-04-25T00:00:00+00:00")
    raw = sqlite3.connect(path)
    raw.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
    raw.commit()
    raw.close()
    with pytest.raises(DatabaseError, match="schema 2") as caught:
        ShelfDatabase.open_read(path)
    assert caught.value.advice is not None
    assert "database_file" in caught.value.advice


def test_parent_that_is_a_file_is_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.write_text("x", encoding="utf-8")
    with pytest.raises(DatabaseError, match="parent is not a directory"):
        ShelfDatabase.open_write(parent / "profile.work.sqlite")
    assert parent.is_file()


def test_locked_database_stops(tmp_path: Path) -> None:
    path = tmp_path / "profile.work.sqlite"
    holder = ShelfDatabase.open_write(path, timeout=0.2)
    holder._connection.execute("BEGIN IMMEDIATE")  # noqa: SLF001
    try:
        with pytest.raises(DatabaseError, match="locked") as caught:
            with ShelfDatabase.open_write(path, timeout=0.2) as other:
                other.apply([_new()], "path", "2026-04-25T00:00:00+00:00")
        assert caught.value.advice is not None
        assert "again" in caught.value.advice
    finally:
        holder.close()


def test_refresh_updates_mtime_without_an_event(tmp_path: Path) -> None:
    path = tmp_path / "profile.work.sqlite"
    with ShelfDatabase.open_write(path) as database:
        database.apply([_new()], "path", "2026-04-25T00:00:00+00:00")
        database.apply(
            [
                DatabaseChange(
                    status=STATUS_REFRESH,
                    document_id=1,
                    generation=1,
                    file=_file(mtime="2026-05-01T00:00:00+00:00", input_index=2),
                    identity="path",
                )
            ],
            "path",
            "2026-05-01T00:00:00+00:00",
        )
        document = database.documents()[0]
        events = database.events()
    assert document.mtime == "2026-05-01T00:00:00+00:00"
    assert document.input_index == 2
    assert document.generation == 1
    assert [item.event for item in events] == [EVENT_NEW]


def test_append_output_keeps_the_document(tmp_path: Path) -> None:
    path = tmp_path / "profile.work.sqlite"
    destination = "/out/2026/bill.pdf"
    with ShelfDatabase.open_write(path) as database:
        database.apply([_new()], "path", "2026-04-25T00:00:00+00:00")
        before = database.documents()[0]
        event = database.append_output(
            1,
            "books",
            OP_SYMLINK,
            destination,
            before.hash,
            OutputPrevious(existed=False, ours=False),
            recorded_at="2026-04-25T01:00:00+00:00",
        )
        after = database.documents()[0]
        found = database.events_for_destination(destination)
    assert event.event == EVENT_OUTPUT
    assert event.operation == OP_SYMLINK
    assert event.output_name == "books"
    assert event.source_hash == before.hash
    assert event.previous_json == '{"existed": false, "ours": false}'
    assert event.seq == 2
    assert after.presence == before.presence
    assert after.hash == before.hash
    assert after.generation == before.generation
    assert found == [event]


def test_output_operation_must_be_known(tmp_path: Path) -> None:
    path = tmp_path / "profile.work.sqlite"
    with ShelfDatabase.open_write(path) as database:
        database.apply([_new()], "path", "2026-04-25T00:00:00+00:00")
        with pytest.raises(DatabaseError, match="copy, symlink, or hardlink"):
            database.append_output(
                1,
                "books",
                "move",
                "/out/bill.pdf",
                "a" * 64,
                OutputPrevious(existed=True, ours=True, operation=OP_SYMLINK, source_hash="b" * 64),
                recorded_at="2026-04-25T01:00:00+00:00",
            )
