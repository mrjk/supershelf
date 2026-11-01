"""content_meta. Tools are faked. sqlite is the real file."""

import json
import sqlite3
from pathlib import Path

from supershelf.constants import EVENT_NEW
from supershelf.database import DatabaseChange, ShelfDatabase, StoredFile
from supershelf.scan import InputFile
from supershelf.vars import VarPlan
from tests.metadata_helpers import FakeRunner, input_file as _file
from tests.metadata_helpers import resolve_values, var_plan


def _plan(
    document: dict[str, object],
    root: Path,
    runner: FakeRunner,
    *,
    dry_run: bool = False,
) -> VarPlan:
    return var_plan(document, root, runner, dry_run=dry_run, database=True)


def _values(plan: VarPlan, file: InputFile) -> dict[str, str]:
    return resolve_values(plan, file, use_file_path=True)


def _database(root: Path) -> Path:
    return root / "profile.work.sqlite"


def _author_document() -> dict[str, object]:
    return {"default_vars": {"author": '{{ meta("exiftool", "PDF:Author") }}'}}


def _runner() -> FakeRunner:
    runner = FakeRunner()
    runner.available.add("exiftool")
    runner.output["exiftool"] = json.dumps([{"PDF:Author": "Ada", "PDF:Title": "Report"}])
    return runner


def _tool_calls(runner: FakeRunner) -> list[list[str]]:
    return [call for call in runner.calls if call and call[0] == "exiftool"]


def _version_one(path: Path) -> None:
    file = StoredFile(
        input_index=1,
        input_path="/inbox",
        path="bill.pdf",
        hash="a" * 64,
        mtime="2026-04-25T00:00:00+00:00",
        ctime="2026-04-25T00:00:00+00:00",
        match_kind="bill",
        rule="bill",
        file_dir="",
        file_name="bill.pdf",
        file_stem="bill",
        file_ext="pdf",
        vars_json="{}",
    )
    change = DatabaseChange(
        status=EVENT_NEW,
        document_id=None,
        generation=1,
        file=file,
        identity="path",
    )
    with ShelfDatabase.open_write(path) as database:
        database.apply([change], "path", "2026-04-25T00:00:00+00:00")
    raw = sqlite3.connect(path)
    raw.execute("DROP TABLE content_meta")
    raw.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
    raw.commit()
    raw.close()


def _table_names(path: Path) -> set[str]:
    raw = sqlite3.connect(path)
    names = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    raw.close()
    return names


def _version(path: Path) -> str:
    raw = sqlite3.connect(path)
    row = raw.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    raw.close()
    return str(row[0])


def _count(path: Path, table: str) -> int:
    raw = sqlite3.connect(path)
    row = raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    raw.close()
    return int(row[0])


def test_version_one_migrates_when_the_cache_misses(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _version_one(database)
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    runner = _runner()
    plan = _plan(_author_document(), tmp_path, runner)
    assert _values(plan, _file("scan.pdf", path))["author"] == "Ada"
    assert _version(database) == "2"
    assert "content_meta" in _table_names(database)
    assert _count(database, "documents") == 1
    assert _count(database, "events") == 1
    raw = sqlite3.connect(database)
    row = raw.execute("SELECT payload, error FROM content_meta").fetchone()
    raw.close()
    assert row[1] is None
    assert "Ada" in row[0]
    assert len(_tool_calls(runner)) == 1


def test_dry_run_does_not_create_a_missing_database(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    runner = _runner()
    plan = _plan(_author_document(), tmp_path, runner, dry_run=True)
    assert _values(plan, _file("scan.pdf", path))["author"] == "Ada"
    assert len(_tool_calls(runner)) == 1
    assert _database(tmp_path).exists() is False


def test_dry_run_does_not_migrate_version_one(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _version_one(database)
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    runner = _runner()
    plan = _plan(_author_document(), tmp_path, runner, dry_run=True)
    assert _values(plan, _file("scan.pdf", path))["author"] == "Ada"
    assert len(_tool_calls(runner)) == 1
    assert _version(database) == "1"
    assert "content_meta" not in _table_names(database)
    assert _count(database, "documents") == 1
    assert _count(database, "events") == 1


def test_same_hash_reads_the_row_and_does_not_spawn(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    first = _runner()
    plan = _plan(_author_document(), tmp_path, first)
    assert _values(plan, _file("scan.pdf", path, digest="abc"))["author"] == "Ada"
    database = _database(tmp_path)
    assert _count(database, "documents") == 0
    assert _count(database, "events") == 0
    assert _count(database, "content_meta") == 1
    second = _runner()
    again = _plan(_author_document(), tmp_path, second)
    other = _file("copy.pdf", path, digest="abc")
    assert _values(again, other)["author"] == "Ada"
    assert _tool_calls(second) == []
    assert _count(database, "content_meta") == 1


def test_stored_error_does_not_spawn_again(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    first = _runner()
    first.codes["exiftool"] = 2
    document = {"default_vars": {"author": ['{{ meta("exiftool", "PDF:Author") }}', "UNKNOWN"]}}
    plan = _plan(document, tmp_path, first)
    assert _values(plan, _file("scan.pdf", path))["author"] == "UNKNOWN"
    database = _database(tmp_path)
    raw = sqlite3.connect(database)
    row = raw.execute("SELECT payload, error FROM content_meta").fetchone()
    raw.close()
    assert row[0] is None
    assert row[1]
    second = _runner()
    second.codes["exiftool"] = 2
    again = _plan(document, tmp_path, second)
    assert _values(again, _file("other.pdf", path, digest="abc"))["author"] == "UNKNOWN"
    assert _tool_calls(second) == []


def test_profile_without_meta_leaves_sqlite_absent(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("x", encoding="utf-8")
    runner = FakeRunner()
    plan = _plan({"default_vars": {"title": "Note"}}, tmp_path, runner)
    assert _values(plan, _file("note.txt", path))["title"] == "Note"
    assert _database(tmp_path).exists() is False


def test_fs_and_a_rejected_file_write_nothing(tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("x", encoding="utf-8")
    runner = FakeRunner()
    plan = _plan(
        {
            "default_vars": {
                "name": '{{ meta("fs", "name") }}',
                "author": ['{{ meta("pdf", "author") }}', "NONE"],
            }
        },
        tmp_path,
        runner,
    )
    values = _values(plan, _file("note.txt", note))
    assert values["name"] == "note.txt"
    assert values["author"] == "NONE"
    assert _database(tmp_path).exists() is False
