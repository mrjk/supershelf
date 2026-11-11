"""scan feeds."""

import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from pypdf import PdfWriter

from supershelf.cli import App
from supershelf.constants import EVENT_NEW
from supershelf.database import DatabaseChange, ShelfDatabase, StoredFile
from supershelf.kind_file import backup_kind_file
from tests.helpers import isolate_env, write_text


def _dispatch(argv: list[str]) -> None:
    App(parse=False).dispatch(argv)


def _notice_lines(err: str) -> list[str]:
    return [line for line in err.splitlines() if "NOTICE" in line]


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

[kind_schema.invoice]
feeds = ["vendor", "owner", "issued"]

[kind_schema.invoice.vars_schema]
vendor = "vendor"
owner = "owner"
issued = "issued"

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

[kind_schema.invoice]
feeds = ["vendor"]

[kind_schema.invoice.vars_schema]
vendor = "vendor"

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

[kind_schema.invoice]
feeds = ["vendor"]

[kind_schema.invoice.vars_schema]
vendor = "vendor"

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
    assert row["VENDOR"] == "Mine"


def test_feed_uppercase_matches_kind_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]
kind_overrides_date_format = "%d/%m/%Y"

[vars_schema.vendor]
type = "text"

[vars_schema.issued]
type = "date"

[kind_schema.invoice]
feeds = ["vendor", "issued"]

[kind_schema.invoice.vars_schema]
vendor = "vendor"
issued = "issued"

[default_vars]
vendor = "Bank2000"
issued = "2020-01-01"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        "PATH,vendor,issued,VENDOR,ISSUED\na.pdf,Mine,25/04/2026,,\n",
        encoding="utf-8",
    )

    _dispatch(["scan", "feeds"])

    row = _cells(kind)[0]
    assert row["vendor"] == "Mine"
    assert row["VENDOR"] == "Mine"
    assert row["issued"] == "25/04/2026"
    assert row["ISSUED"] == "25/04/2026"


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

[kind_schema.invoice]
feeds = ["path", "sha", "date"]

[kind_schema.invoice.vars_schema]
path = "path"
sha = "sha"
date = "date"

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
    header = (tmp_path / "invoice.csv").read_text(encoding="utf-8").splitlines()[0]
    names = header.split(",")
    assert names[:2] == ["SHA", "PATH"]
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
    notices = _notice_lines(capsys.readouterr().err)
    assert any("Profile work kind invoice has no config" in line for line in notices)
    assert not any("has no kind file" in line for line in notices)
    assert list(tmp_path.glob("*.csv")) == []


def test_found_kind_file_is_logged_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED, {"a.pdf": b"one", "b.pdf": b"two"})
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor\na.pdf,\nb.pdf,\n", encoding="utf-8")

    _dispatch(["scan", "feeds"])

    message = f"Profile work kind invoice kind file {kind.resolve()}"
    hits = [line for line in _notice_lines(capsys.readouterr().err) if message in line]
    assert len(hits) == 1


def test_missing_kind_file_logs_no_config(
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
name = "bill"
kind = "invoice"
glob = "**"
""",
    )

    _dispatch(["scan", "feeds"])

    notices = _notice_lines(capsys.readouterr().err)
    assert any("Profile work kind invoice has no config" in line for line in notices)
    assert not any("kind file" in line for line in notices)
    assert (tmp_path / "invoice.csv").exists() is False


def test_two_inputs_log_each_kind_file(
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
    (one / "invoice.csv").write_text("PATH\na.pdf\n", encoding="utf-8")
    (two / "invoice.csv").write_text("PATH\na.pdf\n", encoding="utf-8")
    write_text(
        tmp_path / "profile.work.toml",
        """\
[config]
kind_overrides_config = ["{{ __input__.path }}/invoice.csv"]

[[inputs]]
path = "one"

[[inputs]]
path = "two"

[[match_rules]]
name = "bill"
kind = "invoice"
filename_glob = "*.pdf"
""",
    )

    _dispatch(["scan", "feeds"])

    notices = _notice_lines(capsys.readouterr().err)
    hits = [line for line in notices if "kind file" in line]
    assert len(hits) == 2
    assert str((one / "invoice.csv").resolve()) in hits[0]
    assert str((two / "invoice.csv").resolve()) in hits[1]


def test_mixed_inputs_log_the_file_and_the_miss(
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
    (one / "invoice.csv").write_text("PATH\na.pdf\n", encoding="utf-8")
    write_text(
        tmp_path / "profile.work.toml",
        """\
[config]
kind_overrides_config = ["{{ __input__.path }}/invoice.csv"]

[[inputs]]
path = "one"

[[inputs]]
path = "two"

[[match_rules]]
name = "bill"
kind = "invoice"
filename_glob = "*.pdf"
""",
    )

    _dispatch(["scan", "feeds"])

    notices = _notice_lines(capsys.readouterr().err)
    found = f"Profile work kind invoice kind file {(one / 'invoice.csv').resolve()}"
    missed = f"Profile work kind invoice has no config for input {two.resolve()}"
    assert any(found in line for line in notices)
    assert any(missed in line for line in notices)
    assert not any("has no config" in line and "for input" not in line for line in notices)


def test_disabled_mode_logs_neither_kind_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(
        tmp_path,
        """\
[config]
kind_overrides_mode = "disabled"
kind_overrides_config = ["{{ __config__.root_dir }}/invoice.csv"]

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "invoice"
glob = "**"
""",
    )
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH\na.pdf\n", encoding="utf-8")

    _dispatch(["scan", "feeds"])

    err = capsys.readouterr().err
    assert "kind file" not in err
    assert "has no config" not in err

    write_text(
        tmp_path / "profile.work.toml",
        """\
[config]
kind_overrides_mode = "disabled"
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
    err = capsys.readouterr().err
    assert "kind file" not in err
    assert "has no config" not in err


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

[vars_schema.vendor]
type = "text"

[kind_schema.invoice]
feeds = ["vendor"]

[kind_schema.invoice.vars_schema]
vendor = "vendor"

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


def test_omitted_feeds_adds_no_uppercase_columns(
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

    header = (tmp_path / "note.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "SHA,PATH"
    assert "VENDOR" not in header
    assert "ISSUED" not in header


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

[vars_schema.author]
type = "text"

[kind_schema.invoice]
feeds = ["author"]

[kind_schema.invoice.vars_schema]
author = "author"

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

[vars_schema.author]
type = "text"

[kind_schema.invoice]
feeds = ["author"]

[kind_schema.invoice.vars_schema]
author = "author"

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


_BANK_DIGEST = "50e49cfc799678461fb17d3c3e7fd9d7ae1fa4821e6fb0204876cc5fbe41cdec"


def test_path_identity_rename_keeps_one_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED, {"bills/a.pdf": b"bank-2000"})
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        f"PATH,SHA,owner\na.pdf,{_BANK_DIGEST},Kept\n",
        encoding="utf-8",
    )

    _dispatch(["scan", "feeds"])

    rows = _cells(kind)
    assert len(rows) == 1
    assert rows[0]["PATH"] == "bills/a.pdf"
    assert rows[0]["SHA"] == _BANK_DIGEST
    _dispatch(["scan", "feeds"])
    assert len(_cells(kind)) == 1


def test_duplicate_sha_recovers_onto_the_live_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED, {"bills/a.pdf": b"bank-2000"})
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        f"PATH,SHA,owner\n"
        f"a.pdf,{_BANK_DIGEST},Kept\n"
        f"bills/a.pdf,{_BANK_DIGEST},\n",
        encoding="utf-8",
    )

    _dispatch(["scan", "feeds"])

    err = capsys.readouterr().err
    assert "kept path bills/a.pdf" in err
    assert "removed a.pdf" in err
    rows = _cells(kind)
    assert len(rows) == 1
    assert rows[0]["PATH"] == "bills/a.pdf"
    assert rows[0]["SHA"] == _BANK_DIGEST
    assert rows[0]["owner"] == "Kept"


def test_duplicate_sha_with_two_live_paths_is_an_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED, {"a.pdf": b"bank-2000", "b.pdf": b"bank-2000"})
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        f"PATH,SHA,owner\na.pdf,{_BANK_DIGEST},One\nb.pdf,{_BANK_DIGEST},Two\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as raised:
        _dispatch(["scan", "feeds"])
    assert raised.value.code == 2
    assert len(_cells(kind)) == 2


def test_scan_vars_still_errors_on_duplicate_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED, {"a.pdf": b"bank-2000"})
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        f"PATH,SHA,owner\na.pdf,{_BANK_DIGEST},One\nb.pdf,{_BANK_DIGEST},Two\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as raised:
        _dispatch(["scan", "vars"])
    assert raised.value.code == 2


def test_hash_identity_recovers_stuck_duplicate_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    body = _FEED.replace("[config]\n", "[config]\nrecord_identity = \"hash\"\n", 1)
    _profile(tmp_path, body, {"bills/a.pdf": b"bank-2000"})
    kind = tmp_path / "invoice.csv"
    kind.write_text(
        f"PATH,SHA,owner\n"
        f"a.pdf,{_BANK_DIGEST},Kept\n"
        f"bills/a.pdf,{_BANK_DIGEST},\n",
        encoding="utf-8",
    )

    _dispatch(["scan", "feeds"])

    rows = _cells(kind)
    assert len(rows) == 1
    assert rows[0]["PATH"] == "bills/a.pdf"
    assert rows[0]["owner"] == "Kept"


def test_existing_kind_file_is_backed_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    original = "PATH,vendor\na.pdf,\n"
    kind.write_text(original, encoding="utf-8")

    _dispatch(["scan", "feeds"])

    backups = list((tmp_path / ".backups").iterdir())
    assert len(backups) == 1
    assert backups[0].name.startswith("invoice.csv.")
    assert backups[0].read_text(encoding="utf-8") == original
    assert _cells(kind)[0]["VENDOR"] == "Bank2000"


def test_no_backup_skips_kind_file_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor\na.pdf,\n", encoding="utf-8")

    _dispatch(["scan", "feeds", "--no-backup"])

    assert (tmp_path / ".backups").exists() is False
    assert _cells(kind)[0]["VENDOR"] == "Bank2000"


def test_dry_run_makes_no_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    _profile(tmp_path, _FEED)
    kind = tmp_path / "invoice.csv"
    original = "PATH,vendor\na.pdf,\n"
    kind.write_text(original, encoding="utf-8")

    _dispatch(["scan", "feeds", "--dry-run"])

    assert (tmp_path / ".backups").exists() is False
    assert kind.read_text(encoding="utf-8") == original


def test_new_kind_file_makes_no_backup(
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

[vars_schema.vendor]
type = "text"

[kind_schema.note]
feeds = ["vendor"]

[kind_schema.note.vars_schema]
vendor = "vendor"

[default_vars]
vendor = "Bank2000"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
kind = "note"
glob = "**"
""",
    )

    _dispatch(["scan", "feeds"])

    assert (tmp_path / "note.csv").exists()
    assert (tmp_path / ".backups").exists() is False


def test_backup_collision_uses_numeric_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolate_env(monkeypatch, tmp_path)
    kind = tmp_path / "invoice.csv"
    kind.write_text("PATH,vendor\na.pdf,\n", encoding="utf-8")
    folder = tmp_path / ".backups"
    folder.mkdir()
    stamp = datetime(2026, 4, 25, 13, 45, 6)
    taken = folder / f"invoice.csv.{stamp.strftime('%y%m%d-%H%M%S')}"
    taken.write_text("taken\n", encoding="utf-8")

    target = backup_kind_file(kind, now=stamp)

    assert target == folder / "invoice.csv.260425-134506-2"
    assert target.read_text(encoding="utf-8") == "PATH,vendor\na.pdf,\n"
    assert taken.read_text(encoding="utf-8") == "taken\n"


