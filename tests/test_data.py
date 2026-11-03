"""data feed, data prune, and data show."""

import hashlib
import io
import json
import sqlite3
from pathlib import Path

import pytest
from pypdf import PdfWriter

from supershelf.cli import App
from supershelf.constants import EVENT_NEW
from supershelf.data import run_prune, run_show
from supershelf.database import DatabaseChange, ShelfDatabase, StoredFile
from supershelf.errors import VarConfigError
from tests.helpers import isolate_env, write_text


def _dispatch(argv: list[str]) -> None:
    App(parse=False).dispatch(argv)


def _prune(
    *,
    empty_fields: bool = False,
    missing: bool = False,
    clear: bool = False,
    every: bool = False,
) -> None:
    run_prune(
        None,
        None,
        empty_fields=empty_fields,
        missing=missing,
        clear=clear,
        every=every,
        force=True,
        dry_run=False,
        verbosity=0,
    )


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

[default_vars]
vendor = "Bank2000"
issued = "2026-04-25"

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
        "PATH,vendor,issued,owner\na.pdf,Bank2000,,Clerk2000\n",
        encoding="utf-8",
    )
    _dispatch(["scan", "feeds"])

    captured = capsys.readouterr()
    assert "VENDOR" in captured.out
    assert "Continue?" not in captured.err
    rows = _cells(kind)
    assert rows[0]["vendor"] == "Bank2000"
    assert rows[0]["VENDOR"] == "Bank2000"
    assert rows[0]["issued"] == ""
    assert rows[0]["ISSUED"] == "25/04/2026"
    assert rows[0]["owner"] == "Clerk2000"
    assert "OWNER" not in rows[0]
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_unset_var_does_not_blank_or_add_a_cell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor\na.pdf,\n", encoding="utf-8")

    _dispatch(["scan", "feeds"])

    header = kind.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert "OWNER" not in header
    row = _cells(kind)[0]
    assert row["vendor"] == ""
    assert row["VENDOR"] == "Bank2000"
    assert row.get("owner", "") == ""


def test_date_round_trip_uses_the_kind_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,issued\na.pdf,\n", encoding="utf-8")

    _dispatch(["scan", "feeds"])

    row = _cells(kind)[0]
    assert row["issued"] == ""
    assert row["ISSUED"] == "25/04/2026"


def test_equal_uppercase_cell_is_not_a_change(
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

    _dispatch(["scan", "feeds"])

    row = _cells(kind)[0]
    assert row["vendor"] == ""
    assert row["VENDOR"] == "Bank2000"
    assert "VENDOR" not in capsys.readouterr().out


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

    _dispatch(["scan", "feeds"])

    row = _cells(kind)[0]
    assert row["vendor"] == "Mine"
    assert row["VENDOR"] == "Bank2000"


def test_reserved_names_use_wrapped_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_mode = "always"
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

    _dispatch(["scan", "feeds"])

    row = _cells(tmp_path / "invoice.csv")[0]
    assert row["_PATH_"] == "rel/a.pdf"
    assert row["_SHA_"] == "abc"
    assert row["DATE"] == "2026-04-25"
    assert "_DATE_" not in row
    assert "PATH" == next(iter(row))
    header = (tmp_path / "invoice.csv").read_text(encoding="utf-8").splitlines()[0]
    names = header.split(",")
    assert "SHA" in names
    assert "_SHA_" in names
    assert names.count("DATE") == 1


def test_path_filter_does_not_drop_rows_outside_the_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED, {"a.pdf": b"bank-2000", "b.pdf": b"other"})
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        "PATH,vendor\na.pdf,\nb.pdf,\ngone.pdf,Mine\n",
        encoding="utf-8",
    )

    _dispatch(["scan", "feeds", "a.pdf"])

    paths = [row["PATH"] for row in _cells(kind)]
    assert paths == ["a.pdf", "b.pdf", "gone.pdf"]
    assert _cells(kind)[0]["VENDOR"] == "Bank2000"
    assert _cells(kind)[2]["vendor"] == "Mine"


def test_feed_writes_without_a_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor\na.pdf,\n", encoding="utf-8")

    _dispatch(["scan", "feeds"])

    assert "Continue?" not in capsys.readouterr().err
    assert _cells(kind)[0]["VENDOR"] == "Bank2000"
    assert _cells(kind)[0]["vendor"] == ""


def test_disabled_mode_does_not_read_or_write(
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

    created = tmp_path / "kinds" / "invoice.csv"
    _dispatch(["scan", "feeds"])
    assert created.exists() is False

    created.parent.mkdir()
    original = "PATH,vendor,owner\na.pdf,,Clerk2000\n"
    created.write_text(original, encoding="utf-8")
    _dispatch(["scan", "feeds"])
    assert created.read_text(encoding="utf-8") == original


def test_empty_kind_config_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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

    _dispatch(["scan", "feeds"])
    assert "has no kind file" in capsys.readouterr().err
    assert list(tmp_path.glob("*.csv")) == []

    with pytest.raises(VarConfigError):
        _prune()
    with pytest.raises(VarConfigError):
        run_show(None, None, None, dry_run=False)


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
        _dispatch(["scan", "feeds"])

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

    _dispatch(["scan", "feeds"])

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

    _dispatch(["scan", "feeds"])

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
kind_overrides_mode = "always"
kind_overrides_config = ["{{ __config__.root_dir }}/note.csv"]
kind_overrides_date_format = "%d/%m/%Y"

[default_vars]
vendor = "Bank2000"
issued = "25/04/2026"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "note"
glob = "**"
""",
    )

    _dispatch(["scan", "feeds"])

    row = _cells(tmp_path / "note.csv")[0]
    assert row["VENDOR"] == "Bank2000"
    assert row["ISSUED"] == "25/04/2026"
    assert row.get("vendor", "") == ""
    assert row.get("issued", "") == ""


def test_feed_does_not_write_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    (tmp_path / "invoice.csv").write_text("PATH,vendor\na.pdf,\n", encoding="utf-8")
    _dispatch(["db", "import"])
    database = tmp_path / "profile.work.sqlite"
    documents = _count(database, "documents")
    events = _count(database, "events")

    _dispatch(["scan", "feeds"])

    assert _count(database, "documents") == documents
    assert _count(database, "events") == events
    row = _cells(tmp_path / "invoice.csv")[0]
    assert row["vendor"] == ""
    assert row["VENDOR"] == "Bank2000"


def test_feed_writes_the_cell_and_leaves_the_database(
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
    _dispatch(["scan", "feeds"])

    assert "Continue?" not in capsys.readouterr().err
    assert _cells(kind)[0]["AUTHOR"] == "Bank2000"
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

    _dispatch(["scan", "feeds", "--dry-run"])

    captured = capsys.readouterr()
    assert "Continue?" not in captured.err
    assert "AUTHOR" in captured.out
    assert "Bank2000" in captured.out
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

    _prune()

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

    _prune()

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
    _dispatch(["db", "import"])
    (tmp_path / "inbox" / "gone.pdf").unlink()
    _dispatch(["db", "import"])
    database = tmp_path / "profile.work.sqlite"
    before = _count(database, "documents")

    _prune(missing=True)

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
    _dispatch(["db", "import"])
    database = tmp_path / "profile.work.sqlite"
    documents = _count(database, "documents")
    events = _count(database, "events")

    _prune(clear=True)

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

    _prune(empty_fields=True)

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
    _dispatch(["db", "import"])
    database = tmp_path / "profile.work.sqlite"
    documents = _count(database, "documents")

    _prune(every=True)

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

    tables = run_show(None, None, None, dry_run=False)
    by_kind = {table.kind: table for table in tables}
    assert by_kind["invoice"].kind_file is not None
    assert "invoice.csv" in by_kind["invoice"].kind_file
    assert "note" in by_kind
    rendered = " ".join(str(row) for table in tables for row in table.rows)
    assert "Bank2000" in rendered
    assert "Statement" in rendered


def test_show_unknown_kind_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)

    with pytest.raises(VarConfigError):
        run_show(None, None, "missing", dry_run=False)


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

    tables = run_show(None, None, "invoice", dry_run=False)
    assert [table.kind for table in tables] == ["invoice"]
    rendered = " ".join(str(row) for table in tables for row in table.rows)
    assert "note-1.pdf" not in rendered


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

    run_show(None, None, None, dry_run=False)

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

    _prune(missing=True)

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

    _prune(missing=True)

    rows = _cells(kind)
    assert [(row["PATH"], row["SHA"], row["vendor"]) for row in rows] == [
        ("a.pdf", live_sha, "Kept")
    ]
    err = capsys.readouterr().err
    assert f"drop a.pdf SHA {old_sha}, user cells" in err
    assert f"drop a.pdf SHA {live_sha}" not in err

