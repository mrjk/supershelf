"""record status, run, history, and duplicates."""

import sqlite3
from pathlib import Path

import pytest

from supershelf.cli import App
from supershelf.database import ShelfDatabase
from supershelf.record import RecordReader
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

def _history(path: str | None = None) -> list[dict[str, object]]:
    return RecordReader.load(None, None).history(path)


def _duplicates(path: str | None = None) -> list[dict[str, object]]:
    return RecordReader.load(None, None).duplicates(path)


def _profile(tmp_path: Path) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.pdf").write_bytes(b"bank-2000")
    path = tmp_path / "profile.work.toml"
    path.write_text(_PROFILE, encoding="utf-8")
    return inbox


def test_dry_run_creates_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _profile(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "import", "--dry-run"])
    output = capsys.readouterr().out
    assert "new" in output
    assert "a.pdf" in output
    assert (tmp_path / "profile.work.sqlite").exists() is False
    assert list(tmp_path.glob("*.sqlite*")) == []


def test_run_does_not_write_a_kind_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _profile(tmp_path)
    text = (tmp_path / "profile.work.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.work.toml").write_text(
        "[config]\nkind_overrides_mode = \"always\"\n" + text,
        encoding="utf-8",
    )
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    assert "new" in capsys.readouterr().out
    assert (tmp_path / "profile.work.sqlite").is_file()
    assert (tmp_path / "profile.work.bill.csv").exists() is False
    assert (tmp_path / "profile.work.cache").exists() is False


def test_run_records_and_scan_commands_stay_free_of_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _profile(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "files"])
    app.dispatch(["scan", "kinds"])
    app.dispatch(["scan", "vars"])
    app.dispatch(["inspect", "scan", "kinds"])
    app.dispatch(["inspect", "schema"])
    app.dispatch(["profiles"])
    assert (tmp_path / "profile.work.sqlite").exists() is False

    app.dispatch(["scan", "import"])
    recorded = capsys.readouterr().out
    assert "new" in recorded
    database = tmp_path / "profile.work.sqlite"
    assert database.is_file()
    assert (tmp_path / "profile.work.cache").exists() is False

    app.dispatch(["inspect", "scan", "import"])
    status = capsys.readouterr().out
    assert "unchanged" in status

    app.dispatch(["scan", "import"])
    again = capsys.readouterr().out
    assert "new" not in again
    assert "a.pdf" not in again

    (inbox / "a.pdf").write_bytes(b"bank-2001")
    app.dispatch(["scan", "import", "--dry-run"])
    preview = capsys.readouterr().out
    assert "generation" in preview
    assert database.is_file()
    history = _history()
    assert [row["event"] for row in history] == ["new"]


def test_filter_missing_then_a_later_run_moves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _profile(tmp_path)
    original = (inbox / "a.pdf").read_bytes()
    (inbox / "c.pdf").write_bytes(b"other")
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()

    (inbox / "a.pdf").unlink()
    app.dispatch(["scan", "import", "a.pdf"])
    filtered = capsys.readouterr().out
    assert "missing" in filtered
    assert "c.pdf" not in filtered

    (inbox / "b.pdf").write_bytes(original)
    app.dispatch(["scan", "import"])
    moved = capsys.readouterr().out
    assert "move" in moved
    assert "b.pdf" in moved
    history = _history("a.pdf")
    events = {row["event"] for row in history}
    paths = {row["path"] for row in history}
    assert "move" in events
    assert "a.pdf" in paths
    assert "b.pdf" in paths


def test_duplicates_lists_two_current_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _profile(tmp_path)
    (inbox / "copy.pdf").write_bytes((inbox / "a.pdf").read_bytes())
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    duplicates = _duplicates()
    assert sum(row["current"] == "yes" for row in duplicates) >= 2


def test_unmatched_file_stays_in_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _profile(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    (tmp_path / "profile.work.toml").write_text(
        _PROFILE.replace('glob = "**"', 'glob = "missing-*.pdf"'),
        encoding="utf-8",
    )
    app.dispatch(["scan", "import"])
    output = capsys.readouterr().out
    assert "unmatched" in output
    history = _history()
    events = {row["event"] for row in history}
    assert "unmatched" in events
    assert "new" in events
    assert (inbox / "a.pdf").is_file()


def test_bad_identity_exits_before_creating_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _profile(tmp_path)
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["scan", "import", "--record-identity", "PATH"])
    assert caught.value.code == 2
    assert "path or hash" in capsys.readouterr().err
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_identity_switch_warns_and_keeps_old_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _profile(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    (inbox / "a.pdf").write_bytes(b"edited")
    app.dispatch(["scan", "import", "--record-identity", "hash"])
    warned = capsys.readouterr().err
    assert "was path" in warned
    assert "uses hash" in warned
    history = _history()
    assert [row["identity"] for row in history] == ["path", "hash"]
    assert [row["event"] for row in history] == ["new", "generation"]
    with ShelfDatabase.open_read(tmp_path / "profile.work.sqlite") as database:
        assert database.identity() == "hash,path"


def test_two_hash_copies_are_not_inserted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = _profile(tmp_path)
    text = (tmp_path / "profile.work.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.work.toml").write_text(
        '[config]\nrecord_identity = "hash"\n' + text,
        encoding="utf-8",
    )
    (inbox / "b.pdf").write_bytes((inbox / "a.pdf").read_bytes())
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    first = capsys.readouterr().out
    assert "new" in first
    assert "duplicate" in first
    assert "b.pdf" in first
    history = _history()
    assert [row["path"] for row in history] == ["a.pdf"]
    assert "b.pdf" not in {row["path"] for row in _duplicates()}
    app.dispatch(["scan", "import"])
    second = capsys.readouterr().out
    assert "duplicate" in second
    assert "new" not in second
    again = _history()
    assert [row["event"] for row in again] == ["new"]


def test_bad_rule_identity_exits_before_the_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _profile(tmp_path)
    (tmp_path / "profile.work.toml").write_text(
        """\
[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
glob = "**"

[[match_rules]]
name = "other"
glob = "nope-*"
record_identity = "key"
""",
        encoding="utf-8",
    )
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["scan", "import"])
    assert caught.value.code == 2
    assert "match rule other" in capsys.readouterr().err
    assert (tmp_path / "profile.work.sqlite").exists() is False


@pytest.mark.parametrize(
    "record_identity",
    ['"HASH"', '""', "[]", '["path", "path"]', '"{{ author }}"', '"key"'],
)
def test_bad_rule_lists_exit_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record_identity: str,
) -> None:
    _isolate(monkeypatch, tmp_path)
    _profile(tmp_path)
    (tmp_path / "profile.work.toml").write_text(
        f"""\
[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
glob = "**"
record_identity = {record_identity}
""",
        encoding="utf-8",
    )
    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["scan", "import"])
    assert caught.value.code == 2
    assert (tmp_path / "profile.work.sqlite").exists() is False
    capsys.readouterr()


def test_path_list_matches_legacy_meta_without_a_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _profile(tmp_path)
    app = App(parse=False)
    app.dispatch(["scan", "import"])
    capsys.readouterr()
    database = tmp_path / "profile.work.sqlite"
    raw = sqlite3.connect(database)
    raw.execute("UPDATE meta SET value = 'path' WHERE key = 'identity'")
    raw.commit()
    raw.close()
    text = (tmp_path / "profile.work.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.work.toml").write_text(
        '[config]\nrecord_identity = ["path", "hash"]\n' + text,
        encoding="utf-8",
    )
    app.dispatch(["scan", "import"])
    assert "record_identity was" not in capsys.readouterr().err
    with ShelfDatabase.open_read(database) as stored:
        assert stored.identity() == "path"


def test_history_without_a_database_prints_no_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _profile(tmp_path)
    app = App(parse=False)
    app.dispatch(["db", "show"])
    assert (tmp_path / "profile.work.sqlite").exists() is False
    assert "a.pdf" not in capsys.readouterr().out
