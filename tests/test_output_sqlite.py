"""sqlite output driver."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from supershelf.cli import App
from tests.helpers import isolate_env as _isolate

_PROFILE = """\
[default_vars]
vendor = "Bank2000"
amount = 12.5

[vars_schema]
vendor.type = "text"
amount.type = "float"

[kind_schema.bill]
desc = "A bill"

[kind_schema.bill.vars_schema]
vendor = "vendor"
amount = "amount"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "bill"
glob = "**"
"""

_EXPORT = """
[[outputs]]
name = "export"
driver = "sqlite"
path = "{{ __config__.root_dir }}/export.sqlite"
kinds = ["bill"]
"""


def _write(
    tmp_path: Path,
    *,
    extra: str = _EXPORT,
    profile: str = _PROFILE,
    payload: bytes = b"bank-2000",
) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.pdf").write_bytes(payload)
    (tmp_path / "profile.work.toml").write_text(profile + extra, encoding="utf-8")
    return inbox


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    return {str(row[0]) for row in rows}


def _files_row(path: Path, digest: str) -> sqlite3.Row:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM files WHERE hash = ?", (digest,)
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return row


def _data_row(path: Path, kind: str, digest: str) -> sqlite3.Row:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            f'SELECT * FROM "data_{kind}" WHERE hash = ?', (digest,)
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return row


def test_sqlite_missing_path_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(
        tmp_path,
        extra="""
[[outputs]]
name = "export"
driver = "sqlite"
""",
    )
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "path is required" in capsys.readouterr().err


def test_sqlite_unknown_key_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_EXPORT + 'layout = "{{ vendor }}"\n')
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "does not accept layout" in capsys.readouterr().err


def test_sqlite_preview_and_dry_run_write_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["db", "import"])
    capsys.readouterr()
    app.dispatch(["output", "preview"])
    preview = capsys.readouterr().out
    assert "write" in preview
    assert "upsert" in preview
    assert "a.pdf" in preview
    assert (tmp_path / "export.sqlite").exists() is False
    app.dispatch(["output", "run", "--dry-run"])
    assert "write" in capsys.readouterr().out
    assert (tmp_path / "export.sqlite").exists() is False


def test_sqlite_run_upserts_and_second_run_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["db", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    first = capsys.readouterr().out
    assert "write" in first
    assert "upsert" in first
    export = tmp_path / "export.sqlite"
    assert export.is_file()
    assert {"hash", "files", "data_bill"} <= _tables(export)
    digest = _digest(b"bank-2000")
    files = _files_row(export, digest)
    assert files["path"] == "a.pdf"
    assert files["match_kind"] == "bill"
    assert files["file_name"] == "a.pdf"
    data = _data_row(export, "bill", digest)
    assert data["vendor"] == "Bank2000"
    assert data["amount"] == 12.5
    app.dispatch(["output", "run"])
    assert "write" not in capsys.readouterr().out
    app.dispatch(["output", "preview"])
    assert "unchanged" in capsys.readouterr().out


def test_sqlite_replace_on_var_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["db", "import"])
    app.dispatch(["output", "run"])
    capsys.readouterr()
    text = (tmp_path / "profile.work.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.work.toml").write_text(
        text.replace('vendor = "Bank2000"', 'vendor = "Bank2001"'),
        encoding="utf-8",
    )
    app.dispatch(["db", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    assert "replace" in capsys.readouterr().out
    data = _data_row(tmp_path / "export.sqlite", "bill", _digest(b"bank-2000"))
    assert data["vendor"] == "Bank2001"


def test_sqlite_second_kind_table_leaves_other_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    profile = """\
[default_vars]
vendor = "Bank2000"
amount = 12.5

[vars_schema]
vendor.type = "text"
amount.type = "float"

[kind_schema.bill]
desc = "A bill"

[kind_schema.bill.vars_schema]
vendor = "vendor"
amount = "amount"

[kind_schema.note]
desc = "A note"

[kind_schema.note.vars_schema]
vendor = "vendor"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "note"
kind = "note"
glob = "notes/**"

[[match_rules]]
name = "bill"
kind = "bill"
glob = "**"
"""
    extra = """
[[outputs]]
name = "export"
driver = "sqlite"
path = "{{ __config__.root_dir }}/export.sqlite"
kinds = ["bill", "note"]
"""
    inbox = _write(tmp_path, profile=profile, extra=extra)
    notes = inbox / "notes"
    notes.mkdir()
    (notes / "b.pdf").write_bytes(b"note-bytes")
    app = App(parse=False)
    app.dispatch(["db", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    capsys.readouterr()
    export = tmp_path / "export.sqlite"
    assert {"data_bill", "data_note"} <= _tables(export)
    bill = _data_row(export, "bill", _digest(b"bank-2000"))
    assert bill["vendor"] == "Bank2000"
    note = _data_row(export, "note", _digest(b"note-bytes"))
    assert note["vendor"] == "Bank2000"
    assert "amount" not in note.keys()


def test_sqlite_schema_adds_column(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["db", "import"])
    app.dispatch(["output", "run"])
    capsys.readouterr()
    text = (tmp_path / "profile.work.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.work.toml").write_text(
        text.replace(
            "[vars_schema]\nvendor.type = \"text\"\namount.type = \"float\"",
            "[vars_schema]\nvendor.type = \"text\"\namount.type = \"float\"\n"
            "memo.type = \"text\"",
        ).replace(
            "[kind_schema.bill.vars_schema]\nvendor = \"vendor\"\namount = \"amount\"",
            "[kind_schema.bill.vars_schema]\nvendor = \"vendor\"\namount = \"amount\"\n"
            "memo = \"memo\"",
        ),
        encoding="utf-8",
    )
    app.dispatch(["db", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    assert "replace" in capsys.readouterr().out
    connection = sqlite3.connect(tmp_path / "export.sqlite")
    try:
        cols = {
            str(row[1])
            for row in connection.execute('PRAGMA table_info("data_bill")').fetchall()
        }
    finally:
        connection.close()
    assert "memo" in cols


def test_sqlite_incompatible_schema_tips_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["db", "import"])
    app.dispatch(["output", "run"])
    capsys.readouterr()
    export = tmp_path / "export.sqlite"
    with sqlite3.connect(export) as connection:
        connection.execute("DROP TABLE data_bill")
        connection.execute(
            'CREATE TABLE data_bill (hash TEXT PRIMARY KEY, vendor INTEGER, amount REAL)'
        )
        connection.execute(
            "INSERT INTO data_bill (hash, vendor, amount) VALUES (?, ?, ?)",
            (_digest(b"bank-2000"), 1, 12.5),
        )
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "run"])
    assert caught.value.code != 0
    err = capsys.readouterr().err
    assert "vendor" in err
    assert "Delete the sqlite file" in err


def test_sqlite_duplicate_hash_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _write(tmp_path)
    (inbox / "copy.pdf").write_bytes(b"bank-2000")
    profile = (tmp_path / "profile.work.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.work.toml").write_text(
        profile.replace(
            '[[match_rules]]\nname = "bill"\nkind = "bill"\nglob = "**"',
            '[config]\nrecord_identity = "path"\n\n'
            '[[match_rules]]\nname = "bill"\nkind = "bill"\nglob = "**"',
        ),
        encoding="utf-8",
    )
    app = App(parse=False)
    app.dispatch(["db", "import"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "run"])
    assert caught.value.code != 0
    assert "same hash" in capsys.readouterr().err
    assert (tmp_path / "export.sqlite").exists() is False


def test_sqlite_stale_document_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "run"])
    assert caught.value.code == 1
    assert "not in the library" in capsys.readouterr().err
    assert (tmp_path / "export.sqlite").exists() is False


def test_sqlite_when_false_skips_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_EXPORT + 'when = "false"\n')
    app = App(parse=False)
    app.dispatch(["db", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    out = capsys.readouterr().out
    assert "skip" in out
    assert "false" in out
    assert (tmp_path / "export.sqlite").exists() is False


def test_sqlite_when_template_filters_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(
        tmp_path,
        extra=_EXPORT + "when = '{{ __match__.kind == \"bill\" }}'\n",
    )
    app = App(parse=False)
    app.dispatch(["db", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    assert "write" in capsys.readouterr().out
    assert (tmp_path / "export.sqlite").is_file()
    text = (tmp_path / "profile.work.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.work.toml").write_text(
        text.replace(
            "when = '{{ __match__.kind == \"bill\" }}'",
            "when = '{{ __match__.kind == \"other\" }}'",
        ),
        encoding="utf-8",
    )
    app.dispatch(["output", "run"])
    out = capsys.readouterr().out
    assert "skip" in out
    assert "write" not in out


def test_sqlite_no_profile_output_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["db", "import"])
    app.dispatch(["output", "run"])
    capsys.readouterr()
    with sqlite3.connect(tmp_path / "profile.work.sqlite") as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event = 'output'"
        ).fetchone()[0]
    assert count == 0
