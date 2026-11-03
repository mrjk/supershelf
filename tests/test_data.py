"""data feed, data prune, and data show."""

import hashlib
import io
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from pypdf import PdfWriter

from supershelf.cli import App
from supershelf.constants import EVENT_NEW
from supershelf.database import DatabaseChange, ShelfDatabase, StoredFile
from tests.helpers import isolate_env, write_text


class _Terminal(io.StringIO):
    """A stdin that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


def _dispatch(argv: list[str]) -> None:
    App(parse=False).dispatch(argv)


def _profile(tmp_path: Path, body: str, files: dict[str, bytes] | None = None) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for name, payload in (files or {"a.pdf": b"bank-2000"}).items():
        target = inbox / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    write_text(tmp_path / "profile.work.toml", body)


def _cells(path: Path) -> list[dict[str, str]]:
    import csv

    text = path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Author": "Bank2000"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def _version_one(path: Path) -> None:
    file = StoredFile(
        input_index=1,
        input_path="/inbox",
        path="bill.pdf",
        hash="a" * 64,
        mtime="2026-04-25T00:00:00+00:00",
        ctime="2026-04-25T00:00:00+00:00",
        match_kind="invoice",
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


def _count(path: Path, table: str) -> int:
    raw = sqlite3.connect(path)
    row = raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    raw.close()
    return int(row[0])


_FEED = """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]
kind_overrides_date_format = "%d/%m/%Y"

[vars_schema.vendor]
type = "text"

[vars_schema.owner]
type = "text"

[vars_schema.issued]
type = "date"

[vars_schema.__date__]
desc = "Document date"

[default_vars]
vendor = "Bank2000"
issued = "2026-04-25"
__date__ = "2026-04-25"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
"""


def test_empty_cell_is_filled_and_filled_cell_stays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        "PATH,vendor,issued,__date__,owner\na.pdf,Bank2000,,,Clerk2000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "stdin", _Terminal("yes\n"))

    _dispatch(["data", "feed"])

    err = capsys.readouterr().err
    assert "Continue? [y/N]" in err
    assert "uppercase columns" in err
    assert "invoice" in err
    rows = _cells(kind)
    assert rows[0]["vendor"] == "Bank2000"
    assert rows[0]["VENDOR"] == "Bank2000"
    assert rows[0]["issued"] == ""
    assert rows[0]["ISSUED"] == "2026-04-25"
    assert rows[0]["__date__"] == ""
    assert rows[0]["__DATE__"] == "25/04/2026"
    assert rows[0]["owner"] == "Clerk2000"
    assert rows[0]["OWNER"] == "Clerk2000"
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_unset_var_does_not_blank_or_add_a_cell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor\na.pdf,\n", encoding="utf-8")

    _dispatch(["data", "feed", "--force"])

    text = kind.read_text(encoding="utf-8")
    assert "owner" not in text.splitlines()[0]
    assert "OWNER" not in text.splitlines()[0]
    row = _cells(kind)[0]
    assert row["vendor"] == ""
    assert row["VENDOR"] == "Bank2000"


def test_date_round_trip_uses_the_kind_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,issued,__date__\na.pdf,,\n", encoding="utf-8")

    _dispatch(["data", "feed", "--force"])

    row = _cells(kind)[0]
    assert row["__date__"] == ""
    assert row["__DATE__"] == "25/04/2026"
    assert row["issued"] == ""
    assert row["ISSUED"] == "2026-04-25"


def test_equal_uppercase_cell_is_not_a_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[vars_schema.vendor]
type = "text"

[default_vars]
vendor = "Bank2000"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )
    kind = tmp_path / "invoice.csv"
    original = "PATH,vendor,VENDOR\na.pdf,,Bank2000\n"
    kind.write_text(original, encoding="utf-8")

    _dispatch(["data", "feed", "--force"])

    assert kind.read_text(encoding="utf-8") == original


def test_different_uppercase_cell_is_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[vars_schema.vendor]
type = "text"

[default_vars]
vendor = "Bank2000"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor,VENDOR\na.pdf,Mine,Old\n", encoding="utf-8")

    _dispatch(["data", "feed", "--force"])

    row = _cells(kind)[0]
    assert row["vendor"] == "Mine"
    assert row["VENDOR"] == "Mine"


def test_reserved_names_use_wrapped_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[vars_schema.path]
type = "text"

[vars_schema.sha]
type = "text"

[vars_schema.date]
type = "date"

[default_vars]
path = "rel/a.pdf"
sha = "abc"
date = "2026-04-25"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )

    _dispatch(["data", "feed", "--force"])

    row = _cells(tmp_path / "invoice.csv")[0]
    assert row["_PATH_"] == "rel/a.pdf"
    assert row["_SHA_"] == "abc"
    assert row["_DATE_"] == "2026-04-25"
    assert "PATH" == next(iter(row))
    header = (tmp_path / "invoice.csv").read_text(encoding="utf-8").splitlines()[0]
    names = header.split(",")
    assert "SHA" in names
    assert "_SHA_" in names
    assert header.split(",").count("DATE") == 0


def test_ambiguous_kind_and_var_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[vars_schema.invoice]
type = "text"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )

    with pytest.raises(SystemExit) as caught:
        _dispatch(["data", "feed", "invoice"])

    assert caught.value.code == 2
    err = capsys.readouterr().err
    assert "--kind" in err
    assert "--var" in err
    assert (tmp_path / "invoice.csv").exists() is False


def test_not_a_terminal_asks_for_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    original = "PATH,vendor\na.pdf,\n"
    kind.write_text(original, encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        _dispatch(["data", "feed"])

    assert caught.value.code == 1
    assert "--force" in capsys.readouterr().err
    assert kind.read_text(encoding="utf-8") == original


def test_disabled_mode_still_writes_the_first_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_mode = "disabled"
kind_overrides_config = ["{{ __config__.root_dir }}/kinds/invoice.csv"]

[default_vars]
vendor = "Bank2000"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )

    _dispatch(["data", "feed", "--force"])

    created = tmp_path / "kinds" / "invoice.csv"
    assert "Bank2000" in created.read_text(encoding="utf-8")
    created.write_text("PATH,vendor,owner\na.pdf,,Clerk2000\n", encoding="utf-8")

    _dispatch(["data", "feed", "--force"])

    row = _cells(created)[0]
    assert row["vendor"] == ""
    assert row["VENDOR"] == "Bank2000"
    assert row["owner"] == "Clerk2000"


def test_empty_kind_config_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = []

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )

    for argv in (
        ["data", "feed", "--force"],
        ["data", "prune", "--force"],
        ["data", "show"],
    ):
        with pytest.raises(SystemExit) as caught:
            _dispatch(argv)
        assert caught.value.code == 2


def test_shared_path_stops_when_values_differ(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "a.pdf").write_bytes(b"left")
    (two / "a.pdf").write_bytes(b"right")
    write_text(
        tmp_path / "profile.work.toml",
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[[inputs]]
path = "one"

[[inputs]]
path = "two"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
vars.vendor = "{{ __file__.hash }}"
""",
    )

    with pytest.raises(SystemExit) as caught:
        _dispatch(["data", "feed", "--force"])

    assert caught.value.code == 2
    err = capsys.readouterr().err
    assert "input 1" in err
    assert "input 2" in err
    assert (tmp_path / "invoice.csv").exists() is False


def test_yaml_rewrite_keeps_the_later_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.yaml"]

[default_vars]
vendor = "Bank2000"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )
    kind = tmp_path / "invoice.yaml"
    kind.write_text(
        "- path: a.pdf\n- path: a.pdf\n  vars:\n    vendor: Later\n",
        encoding="utf-8",
    )

    _dispatch(["data", "feed", "--force"])

    body = kind.read_text(encoding="utf-8")
    assert body.count("Later") == 1
    assert "Bank2000" in body


def test_duplicate_raw_row_is_kept(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        "PATH,vendor\na.pdf,\na.pdf,Later\n",
        encoding="utf-8",
    )

    _dispatch(["data", "feed", "--force"])

    rows = _cells(kind)
    assert rows[0]["vendor"] == ""
    assert rows[0]["VENDOR"] == "Bank2000"
    assert rows[1]["vendor"] == "Later"


def test_no_schema_feeds_visible_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/note.csv"]
kind_overrides_date_format = "%d/%m/%Y"

[default_vars]
vendor = "Bank2000"
__date__ = "2026-04-25"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "note"
glob = "**"
""",
    )

    _dispatch(["data", "feed", "--force"])

    row = _cells(tmp_path / "note.csv")[0]
    assert row["VENDOR"] == "Bank2000"
    assert row["__DATE__"] == "25/04/2026"
    assert "vendor" not in row
    assert "__date__" not in row


def test_feed_does_not_write_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    (tmp_path / "invoice.csv").write_text("PATH,vendor\na.pdf,\n", encoding="utf-8")
    _dispatch(["record", "run"])
    database = tmp_path / "profile.work.sqlite"
    documents = _count(database, "documents")
    events = _count(database, "events")

    _dispatch(["data", "feed", "--force"])

    assert _count(database, "documents") == documents
    assert _count(database, "events") == events
    row = _cells(tmp_path / "invoice.csv")[0]
    assert row["vendor"] == ""
    assert row["VENDOR"] == "Bank2000"


def test_cache_is_written_before_a_no(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _pdf(tmp_path / "inbox" / "a.pdf")
    write_text(
        tmp_path / "profile.work.toml",
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[default_vars]
author = '{{ meta("pdf", "author") }}'

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )
    kind = tmp_path / "invoice.csv"
    original = "PATH,author\na.pdf,\n"
    kind.write_text(original, encoding="utf-8")
    database = tmp_path / "profile.work.sqlite"
    _version_one(database)
    monkeypatch.setattr(sys, "stdin", _Terminal("no\n"))

    _dispatch(["data", "feed"])

    assert "Continue? [y/N]" in capsys.readouterr().err
    assert kind.read_text(encoding="utf-8") == original
    raw = sqlite3.connect(database)
    version = raw.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0]
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    documents = raw.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    raw.close()
    assert version == "1"
    assert "content_meta" not in tables
    assert documents == 1
    cache = json.loads((tmp_path / "profile.work.cache").read_text(encoding="utf-8"))
    assert "Bank2000" in json.dumps(cache)


def test_dry_run_creates_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _pdf(tmp_path / "inbox" / "a.pdf")
    write_text(
        tmp_path / "profile.work.toml",
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[default_vars]
author = '{{ meta("pdf", "author") }}'

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )
    kind = tmp_path / "invoice.csv"
    original = "PATH,author\na.pdf,\n"
    kind.write_text(original, encoding="utf-8")

    _dispatch(["data", "feed", "--dry-run"])

    err = capsys.readouterr().err
    assert "Continue?" not in err
    assert "1 cell" in err
    assert kind.read_text(encoding="utf-8") == original
    assert (tmp_path / "profile.work.sqlite").exists() is False
    assert (tmp_path / "profile.work.cache").exists() is False
    assert list(tmp_path.glob("*.sqlite*")) == []


def test_prune_drops_an_empty_feed_column(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor,VENDOR\na.pdf,Bank2000,\n", encoding="utf-8")

    _dispatch(["data", "prune", "--force"])

    header = kind.read_text(encoding="utf-8").splitlines()[0]
    assert "vendor" in header.split(",")
    assert "VENDOR" not in header.split(",")


def test_prune_default_drops_only_empty_extra_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        "PATH,vendor,note,extra\na.pdf,,,Kept\n",
        encoding="utf-8",
    )

    _dispatch(["data", "prune", "--force"])

    header = kind.read_text(encoding="utf-8").splitlines()[0]
    assert header == "PATH,vendor,extra"
    assert _cells(kind)[0]["extra"] == "Kept"
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_missing_drops_the_kind_row_and_keeps_the_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED, {"a.pdf": b"bank-2000", "gone.pdf": b"gone"})
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        "PATH,vendor,note\na.pdf,Bank2000,\ngone.pdf,Bank2000,\n",
        encoding="utf-8",
    )
    _dispatch(["record", "run"])
    (tmp_path / "inbox" / "gone.pdf").unlink()
    _dispatch(["record", "run"])
    database = tmp_path / "profile.work.sqlite"
    before = _count(database, "documents")

    _dispatch(["data", "prune", "--missing", "--force"])

    rows = _cells(kind)
    assert [row["PATH"] for row in rows] == ["a.pdf"]
    assert "note" in kind.read_text(encoding="utf-8").splitlines()[0]
    assert _count(database, "documents") == before
    raw = sqlite3.connect(database)
    presence = raw.execute(
        "SELECT presence FROM documents WHERE path = 'gone.pdf'"
    ).fetchone()[0]
    raw.close()
    assert presence == "missing"


def test_clear_leaves_the_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor,note\na.pdf,Bank2000,\n", encoding="utf-8")
    _dispatch(["record", "run"])
    database = tmp_path / "profile.work.sqlite"
    documents = _count(database, "documents")
    events = _count(database, "events")

    _dispatch(["data", "prune", "--clear", "--force"])

    assert kind.read_text(encoding="utf-8") == "PATH,vendor,note\n"
    assert kind.is_file()
    assert _count(database, "documents") == documents
    assert _count(database, "events") == events


def test_prune_flags_are_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED, {"a.pdf": b"bank-2000", "gone.pdf": b"gone"})
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        "PATH,vendor,note\na.pdf,Bank2000,\ngone.pdf,Bank2000,\n",
        encoding="utf-8",
    )
    (tmp_path / "inbox" / "gone.pdf").unlink()

    _dispatch(["data", "prune", "--empty-fields", "--force"])

    assert "gone.pdf" in kind.read_text(encoding="utf-8")
    assert "note" not in kind.read_text(encoding="utf-8").splitlines()[0]


def test_all_clears_rows_and_leaves_the_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor\na.pdf,Bank2000\n", encoding="utf-8")
    _dispatch(["record", "run"])
    database = tmp_path / "profile.work.sqlite"
    documents = _count(database, "documents")

    _dispatch(["data", "prune", "--all", "--force"])

    assert kind.read_text(encoding="utf-8") == "PATH,vendor\n"
    assert _count(database, "documents") == documents


def test_show_prints_one_table_per_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/{{ __match__.kind }}.csv"]

[vars_schema.vendor]
type = "text"

[default_vars]
vendor = "Bank2000"
title = "Statement"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bills"
kind = "invoice"
filename_glob = "bill-*"

[[match_rules]]
name = "notes"
kind = "note"
filename_glob = "note-*"
""",
        {"bill-1.pdf": b"bank-2000", "note-1.pdf": b"note"},
    )
    (tmp_path / "invoice.csv").write_text(
        "PATH,vendor\nbill-1.pdf,Bank2000\n",
        encoding="utf-8",
    )

    _dispatch(["data", "show"])

    output = capsys.readouterr().out
    assert output.count("profile work kind invoice") == 1
    assert "invoice.csv" in output
    assert output.count("profile work kind note") == 1
    assert "Bank2000" in output
    assert "Statement" in output
    assert "Continue?" not in capsys.readouterr().err


def test_show_unknown_kind_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)

    with pytest.raises(SystemExit) as caught:
        _dispatch(["data", "show", "missing"])

    assert caught.value.code == 2


def test_show_known_kind_with_no_files_prints_the_title(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bills"
kind = "invoice"
filename_glob = "bill-*"

[[match_rules]]
name = "notes"
kind = "note"
filename_glob = "note-*"
""",
        {"note-1.pdf": b"note"},
    )

    _dispatch(["data", "show", "invoice"])

    output = capsys.readouterr().out
    assert "profile work kind invoice" in output
    assert "note-1.pdf" not in output


def test_show_can_write_the_meta_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _pdf(tmp_path / "inbox" / "a.pdf")
    write_text(
        tmp_path / "profile.work.toml",
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[default_vars]
author = '{{ meta("pdf", "author") }}'

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,author\na.pdf,\n", encoding="utf-8")

    _dispatch(["data", "show"])

    assert kind.read_text(encoding="utf-8") == "PATH,author\na.pdf,\n"
    assert (tmp_path / "profile.work.sqlite").exists() is False
    cache = json.loads((tmp_path / "profile.work.cache").read_text(encoding="utf-8"))
    assert "Bank2000" in json.dumps(cache)


def test_prune_missing_lists_the_row_and_follows_the_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    same = b"same-bytes"
    other = b"other-bytes"
    same_sha = hashlib.sha256(same).hexdigest()
    other_sha = hashlib.sha256(other).hexdigest()
    _profile(
        tmp_path,
        _FEED.replace("[config]\n", '[config]\nrecord_identity = "hash"\n'),
        {"new.pdf": same},
    )
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        "PATH,SHA,vendor\n"
        f"old.pdf,{same_sha},Kept\n"
        f"gone.pdf,{other_sha},Gone\n",
        encoding="utf-8",
    )

    _dispatch(["data", "prune", "--missing", "--force"])

    rows = _cells(kind)
    assert [row["PATH"] for row in rows] == ["old.pdf"]
    assert rows[0]["vendor"] == "Kept"
    err = capsys.readouterr().err
    assert f"drop gone.pdf SHA {other_sha}, user cells" in err
    assert "drop old.pdf" not in err


def test_prune_missing_keeps_the_live_hash_when_the_path_is_shared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    live = b"live-bytes"
    live_sha = hashlib.sha256(live).hexdigest()
    old_sha = "b" * 64
    _profile(
        tmp_path,
        _FEED.replace("[config]\n", '[config]\nrecord_identity = "hash"\n'),
        {"a.pdf": live},
    )
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        "PATH,SHA,vendor\n"
        f"a.pdf,{old_sha},Old\n"
        f"a.pdf,{live_sha},Kept\n",
        encoding="utf-8",
    )

    _dispatch(["data", "prune", "--missing", "--force"])

    rows = _cells(kind)
    assert [(row["PATH"], row["SHA"], row["vendor"]) for row in rows] == [
        ("a.pdf", live_sha, "Kept")
    ]
    err = capsys.readouterr().err
    assert f"drop a.pdf SHA {old_sha}, user cells" in err
    assert f"drop a.pdf SHA {live_sha}" not in err

