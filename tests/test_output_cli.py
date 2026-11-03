"""output preview and output run."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from supershelf.cli import App
from supershelf.database import ShelfDatabase
from tests.helpers import isolate_env as _isolate

_PROFILE = """\
[default_vars]
vendor = "Bank2000"

[vars_schema]
vendor.type = "text"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
glob = "**"
"""

_BOOKS = """
[[outputs]]
name = "books"
path = "{{ __config__.root_dir }}/output/books"
"""


def _write(tmp_path: Path, extra: str = _BOOKS, profile: str = _PROFILE) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.pdf").write_bytes(b"bank-2000")
    (tmp_path / "profile.work.toml").write_text(profile + extra, encoding="utf-8")
    return inbox


def _events(tmp_path: Path) -> list[dict[str, object]]:
    path = tmp_path / "profile.work.sqlite"
    if not path.exists():
        return []
    with ShelfDatabase.open_read(path) as database:
        return [
            {
                "output": event.output_name,
                "operation": event.operation,
                "destination": event.destination,
                "source_hash": event.source_hash,
                "previous": json.loads(event.previous_json or "{}"),
                "generation": event.generation,
                "hash": event.hash,
            }
            for event in database.events()
            if event.event == "output"
        ]


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_outputs_not_set_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra="")
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "outputs is not set" in capsys.readouterr().err


def test_outputs_empty_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, profile="outputs = []\n" + _PROFILE, extra="")
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "outputs is empty" in capsys.readouterr().err


def test_literal_when_stops_at_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_BOOKS + 'when = "maybe"\n')
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "maybe" in capsys.readouterr().err
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_yaml_bool_when_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.pdf").write_bytes(b"bank-2000")
    (tmp_path / "profile.work.yaml").write_text(
        "inputs:\n  - path: inbox\nmatch_rules:\n  - name: bill\n    glob: '**'\n"
        "outputs:\n  - name: books\n    path: '{{ __config__.root_dir }}/output/books'\n    when: true\n",
        encoding="utf-8",
    )
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "when must be a string" in capsys.readouterr().err


def test_scan_ignores_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_BOOKS + 'when = "maybe"\n')
    app = App(parse=False)
    app.dispatch(["scan", "files"])
    assert "a.pdf" in capsys.readouterr().out
    assert (tmp_path / "output").exists() is False
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_false_when_does_not_stop_a_new_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_BOOKS + 'when = "false"\n')
    app = App(parse=False)
    app.dispatch(["output", "run"])
    output = capsys.readouterr().out
    assert "skip" in output
    assert "false" in output
    assert (tmp_path / "profile.work.sqlite").exists() is False
    assert (tmp_path / "output").exists() is False


def test_new_file_stops_before_any_write(
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
    captured = capsys.readouterr()
    assert "write" not in captured.out
    assert "status is new" in captured.err
    assert "This file is not in the library." in captured.err
    assert "Run scan import." in captured.err
    assert (tmp_path / "profile.work.sqlite").exists() is False
    assert (tmp_path / "output").exists() is False


def test_preview_of_a_new_file_prints_the_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 1
    captured = capsys.readouterr()
    assert "write" in captured.out
    assert "a.pdf" in captured.out
    assert "This file is not in the library." in captured.err
    assert "status is new" in captured.err
    assert (tmp_path / "profile.work.sqlite").exists() is False
    assert (tmp_path / "output").exists() is False


def test_preview_and_dry_run_write_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_BOOKS + 'layout = "{{ vendor }}/{{ __file__.name }}"\n')
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    app.dispatch(["output", "preview"])
    preview = capsys.readouterr().out
    assert "write" in preview
    assert "Bank2000/a.pdf" in preview
    assert str(tmp_path / "output" / "books") not in preview
    assert (tmp_path / "output").exists() is False
    app.dispatch(["output", "run", "--dry-run"])
    assert "write" in capsys.readouterr().out
    assert (tmp_path / "output").exists() is False
    assert _events(tmp_path) == []


def test_run_copies_and_second_run_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _write(tmp_path, extra=_BOOKS + 'layout = "{{ vendor }}/{{ __file__.name }}"\n')
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    first = capsys.readouterr().out
    assert "write" in first
    dest = tmp_path / "output" / "books" / "Bank2000" / "a.pdf"
    assert dest.read_bytes() == (inbox / "a.pdf").read_bytes()
    events = _events(tmp_path)
    assert len(events) == 1
    assert events[0]["destination"] == str(dest)
    assert events[0]["previous"] == {"existed": False, "ours": False}
    assert events[0]["source_hash"] == _digest(b"bank-2000")
    app.dispatch(["output", "run"])
    assert "write" not in capsys.readouterr().out
    assert "unchanged" not in capsys.readouterr().out
    assert len(_events(tmp_path)) == 1
    app.dispatch(["output", "preview"])
    assert "unchanged" in capsys.readouterr().out


def test_new_bytes_replace_and_keep_the_old_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    app.dispatch(["output", "run"])
    capsys.readouterr()
    (inbox / "a.pdf").write_bytes(b"bank-2001")
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    assert "replace" in capsys.readouterr().out
    dest = tmp_path / "output" / "books" / "a.pdf"
    assert dest.read_bytes() == b"bank-2001"
    events = _events(tmp_path)
    assert events[-1]["previous"]["ours"] is True
    assert events[-1]["previous"]["existed"] is True
    assert events[-1]["previous"]["source_hash"] == _digest(b"bank-2000")
    with ShelfDatabase.open_read(tmp_path / "profile.work.sqlite") as database:
        document = database.documents()[0]
        assert document.generation == 2
        assert document.hash == _digest(b"bank-2001")


def test_foreign_conflict_preview_exits_zero_and_run_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    dest = tmp_path / "output" / "books" / "a.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"foreign")
    app.dispatch(["output", "preview"])
    assert "conflict" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "run"])
    assert caught.value.code == 1
    assert "conflict" in capsys.readouterr().out
    assert dest.read_bytes() == b"foreign"
    assert _events(tmp_path) == []


def test_skip_leaves_a_foreign_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_BOOKS + 'on_conflict = "skip"\n')
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    dest = tmp_path / "output" / "books" / "a.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"foreign")
    app.dispatch(["output", "run"])
    assert "skip" in capsys.readouterr().out
    assert dest.read_bytes() == b"foreign"
    assert _events(tmp_path) == []


def test_overwrite_replaces_a_foreign_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_BOOKS + 'on_conflict = "overwrite"\n')
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    dest = tmp_path / "output" / "books" / "a.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"foreign")
    app.dispatch(["output", "run"])
    assert "replace" in capsys.readouterr().out
    assert dest.read_bytes() == b"bank-2000"
    assert _events(tmp_path)[-1]["previous"] == {"existed": True, "ours": False}


def test_other_document_is_not_taken(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _write(tmp_path, extra=_BOOKS + 'layout = "shared.pdf"\non_conflict = "overwrite"\n')
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    app.dispatch(["output", "run", "a.pdf"])
    capsys.readouterr()
    (inbox / "b.pdf").write_bytes(b"other-file")
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "run", "b.pdf"])
    assert caught.value.code == 1
    error = capsys.readouterr().err
    assert "shared.pdf" in error
    assert "a.pdf" in error
    assert "b.pdf" in error
    dest = tmp_path / "output" / "books" / "shared.pdf"
    assert dest.read_bytes() == b"bank-2000"


def test_layout_move_keeps_the_old_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    app.dispatch(["output", "run"])
    capsys.readouterr()
    path = tmp_path / "profile.work.toml"
    path.write_text(path.read_text(encoding="utf-8") + 'layout = "moved/a.pdf"\n', encoding="utf-8")
    app.dispatch(["output", "run"])
    assert "write" in capsys.readouterr().out
    assert (tmp_path / "output" / "books" / "a.pdf").read_bytes() == b"bank-2000"
    assert (tmp_path / "output" / "books" / "moved" / "a.pdf").read_bytes() == b"bank-2000"


def test_layout_escape_creates_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_BOOKS + 'layout = "../outside.pdf"\n')
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "run"])
    assert caught.value.code == 1
    assert "segment" in capsys.readouterr().err
    assert (tmp_path / "outside.pdf").exists() is False
    assert (tmp_path / "output").exists() is False


def test_two_outputs_cannot_share_a_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    extra = """
[[outputs]]
name = "books"
path = "{{ __config__.root_dir }}/output/books"
layout = "same.pdf"

[[outputs]]
name = "cards"
path = "{{ __config__.root_dir }}/output/books"
layout = "same.pdf"
"""
    _write(tmp_path, extra=extra)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 1
    assert "same.pdf" in capsys.readouterr().err
    assert (tmp_path / "output").exists() is False


def test_duplicate_path_is_left_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _write(tmp_path, profile='[config]\nrecord_identity = "hash"\n' + _PROFILE)
    (inbox / "b.pdf").write_bytes((inbox / "a.pdf").read_bytes())
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    assert (tmp_path / "output" / "books" / "a.pdf").is_file()
    assert (tmp_path / "output" / "books" / "b.pdf").exists() is False
    capsys.readouterr()
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "run", "b.pdf"])
    assert caught.value.code == 1
    assert "status is new" in capsys.readouterr().err
    assert (tmp_path / "output" / "books" / "b.pdf").exists() is False


def test_other_kind_does_not_face_the_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    profile = """\
[default_vars]
vendor = "Bank2000"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
glob = "a.pdf"

[[match_rules]]
name = "note"
glob = "b.pdf"
"""
    inbox = _write(tmp_path, profile=profile, extra=_BOOKS + 'kinds = ["bill"]\n')
    app = App(parse=False)
    app.dispatch(["scan", "import", "a.pdf"])
    capsys.readouterr()
    (inbox / "b.pdf").write_bytes(b"note-file")
    app.dispatch(["output", "run"])
    assert "write" in capsys.readouterr().out
    assert (tmp_path / "output" / "books" / "a.pdf").is_file()
    assert (tmp_path / "output" / "books" / "b.pdf").exists() is False


def test_when_template_casts_bool_words_and_rejects_other_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, extra=_BOOKS + "when = '{{ __match__.kind == \"bill\" }}'\n")
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    app.dispatch(["output", "preview"])
    assert "true" in capsys.readouterr().out
    path = tmp_path / "profile.work.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('{{ __match__.kind == "bill" }}', "{{ vendor }}"), encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "run"])
    assert caught.value.code == 1
    assert "Bank2000" in capsys.readouterr().err


def test_symlink_and_hardlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _write(tmp_path, extra=_BOOKS + 'operation = "symlink"\nlayout = "link.pdf"\n')
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    link = tmp_path / "output" / "books" / "link.pdf"
    assert link.is_symlink()
    assert link.readlink() == (inbox / "a.pdf").resolve() or link.readlink() == inbox / "a.pdf"
    capsys.readouterr()
    path = tmp_path / "profile.work.toml"
    text = path.read_text(encoding="utf-8").replace('operation = "symlink"', 'operation = "hardlink"')
    text = text.replace('layout = "link.pdf"', 'layout = "hard.pdf"')
    path.write_text(text, encoding="utf-8")
    app.dispatch(["output", "run"])
    hard = tmp_path / "output" / "books" / "hard.pdf"
    assert hard.stat().st_ino == (inbox / "a.pdf").stat().st_ino
    assert link.is_symlink()


def test_refresh_is_allowed_and_vars_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    os.utime(inbox / "a.pdf", (1_700_000_000, 1_700_000_000))
    app.dispatch(["output", "preview"])
    assert "write" in capsys.readouterr().out
    capsys.readouterr()
    path = tmp_path / "profile.work.toml"
    text = path.read_text(encoding="utf-8").replace("Bank2000", "Bank2001")
    text = text.replace(
        'path = "{{ __config__.root_dir }}/output/books"\n',
        'path = "{{ __config__.root_dir }}/output/books"\n'
        'layout = "{{ vendor }}/{{ __file__.name }}"\n',
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 1
    preview = capsys.readouterr()
    assert "Bank2001/a.pdf" in preview.out
    assert 'vendor was "Bank2000", now "Bank2001".' in preview.err
    assert (tmp_path / "output").exists() is False
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "run"])
    assert caught.value.code == 1
    error = capsys.readouterr()
    assert "Bank2001/a.pdf" not in error.out
    assert "status is vars" in error.err
    assert 'vendor was "Bank2000", now "Bank2001".' in error.err
    assert "if those live values are the ones you want." in error.err
    assert (tmp_path / "output").exists() is False


def test_dry_run_does_not_migrate_schema_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    database = tmp_path / "profile.work.sqlite"
    raw = sqlite3.connect(database)
    raw.execute("DROP TABLE content_meta")
    raw.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
    raw.commit()
    raw.close()
    app.dispatch(["output", "run", "--dry-run"])
    assert "write" in capsys.readouterr().out
    raw = sqlite3.connect(database)
    version = raw.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0]
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    raw.close()
    assert version == "1"
    assert "content_meta" not in tables
    app.dispatch(["output", "run"])
    raw = sqlite3.connect(database)
    version = raw.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0]
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    raw.close()
    assert version == "2"
    assert "content_meta" in tables


def test_output_does_not_write_a_kind_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path, profile='[config]\nkind_overrides_mode = "always"\n' + _PROFILE)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    app.dispatch(["output", "run"])
    capsys.readouterr()
    assert (tmp_path / "profile.work.bill.csv").exists() is False
    assert (tmp_path / "output" / "books" / "a.pdf").is_file()


def test_note_driver_module_writes_and_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    extra = """
[[outputs]]
name = "notes"
driver = "note"
label = "hello"
"""
    _write(
        tmp_path,
        profile='[config]\noutput_modules = ["tests.output_mods.note"]\n' + _PROFILE,
        extra=extra,
    )
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    app.dispatch(["output", "run"])
    assert "note" in capsys.readouterr().out
    assert (tmp_path / "notes" / "a.pdf.txt").read_text(encoding="utf-8") == "hello"
    assert _events(tmp_path)[0]["output"] == "notes"


def test_bad_output_modules_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(
        tmp_path,
        profile='[config]\noutput_modules = ["tests.output_mods.repeat"]\n' + _PROFILE,
    )
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "already registered" in capsys.readouterr().err
    capsys.readouterr()
    (tmp_path / "profile.work.toml").write_text(
        '[config]\noutput_modules = ["tests.output_mods.empty"]\n' + _PROFILE + _BOOKS,
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "no DRIVERS" in capsys.readouterr().err
    capsys.readouterr()
    (tmp_path / "profile.work.toml").write_text(
        '[config]\noutput_modules = ["tests.output_mods.bad"]\n' + _PROFILE + _BOOKS,
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "OutputDriver" in capsys.readouterr().err
    capsys.readouterr()
    (tmp_path / "profile.work.toml").write_text(
        '[config]\noutput_modules = ["tests.output_mods.missing"]\n' + _PROFILE + _BOOKS,
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["output", "preview"])
    assert caught.value.code == 2
    assert "Cannot import" in capsys.readouterr().err
