"""`supershelf profiles` command."""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from supershelf.cli import App, PackageVersion
from supershelf.constants import LOGGER_NAME
from supershelf.record import RecordSession
from tests.helpers import isolate_env as _isolate
from tests.helpers import write_text as _write


def test_version_prints_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = App(parse=False)

    with pytest.raises(SystemExit) as caught:
        app.dispatch(["--version"])

    assert caught.value.code == 0
    assert capsys.readouterr().out.strip() == PackageVersion.line()


def test_profiles_lists_name_and_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / "profile.work.toml", "[config]\nprofile = 'work'\n")

    app = App(parse=False)
    app.dispatch(["profiles"])

    output = capsys.readouterr().out
    assert "work" in output
    assert "profile.work.toml" in output
    assert "toml" in output


def test_profiles_dry_run_still_lists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / "profile.work.toml", "[config]\nprofile = 'work'\n")

    app = App(parse=False)
    app.dispatch(["--dry-run", "profiles"])

    assert "work" in capsys.readouterr().out


def test_profiles_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / "profile.work.toml", "[config]\nprofile = 'work'\n")
    _write(tmp_path / "profile.home.toml", "[config]\nprofile = 'home'\n")

    app = App(parse=False)
    app.dispatch(["profiles", "--profile", "home"])

    output = capsys.readouterr().out
    assert "home" in output
    assert "work" not in output


def test_profiles_missing_config_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    app = App(parse=False)

    with pytest.raises(SystemExit) as caught:
        app.dispatch(["profiles"])

    assert caught.value.code == 1
    assert "No supershelf config found" in capsys.readouterr().err


def test_notice_is_shown_without_verbose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    app = App(parse=False)

    with pytest.raises(SystemExit):
        app.dispatch(["profiles"])

    capsys.readouterr()
    log = logging.getLogger(LOGGER_NAME)
    assert logging.NOTICE == logging.INFO + 5
    assert callable(log.notice)
    assert log.isEnabledFor(logging.NOTICE)
    assert not log.isEnabledFor(logging.INFO)

    log.notice("notice-marker")
    log.info("info-marker")
    err = capsys.readouterr().err
    assert "notice-marker" in err
    assert "info-marker" not in err


def test_info_needs_one_verbose_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    app = App(parse=False)

    with pytest.raises(SystemExit):
        app.dispatch(["-v", "profiles"])

    capsys.readouterr()
    log = logging.getLogger(LOGGER_NAME)
    assert log.isEnabledFor(logging.INFO)
    assert not log.isEnabledFor(logging.DEBUG)


def test_profiles_does_not_render_templates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nroot_dir = '{{ missing }}'\n",
    )

    app = App(parse=False)
    app.dispatch(["profiles"])

    output = capsys.readouterr().out
    assert "work" in output
    assert "profile.work.toml" in output


def test_scan_files_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    other = tmp_path / "other"
    other.mkdir()
    (other / "b.txt").write_bytes(b"there")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\ndefault_date_format = '%d/%m/%Y'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'file'\nglob = '**'\n",
    )
    _write(
        tmp_path / "profile.home.toml",
        "[config]\nprofile = 'home'\ndefault_date_format = '%d/%m/%Y'\n\n"
        "[[inputs]]\npath = 'other'\n\n"
        "[[match_rules]]\nname = 'file'\nglob = '**'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "files"])
    output = capsys.readouterr().out
    shown = datetime.fromtimestamp(
        (inbox / "a.txt").stat().st_mtime,
        timezone.utc,
    ).strftime("%d/%m/%Y")

    assert "profile" in output
    assert "sha256" in output
    assert "a.txt" in output
    assert "b.txt" in output
    assert "work" in output
    assert "home" in output
    assert shown in output
    assert "+00:00" not in output
    assert str(inbox.resolve()) not in output
    assert str(other.resolve()) not in output
    assert (tmp_path / "profile.work.sqlite").exists() is False
    assert (tmp_path / "profile.home.sqlite").exists() is False

    app.dispatch(["scan", "files", "--format", "json"])
    rows = json.loads(capsys.readouterr().out)
    assert list(rows[0]) == [
        "profile",
        "input",
        "path",
        "status",
        "mtime",
        "ctime",
        "sha256",
    ]


def test_scan_files_always_includes_the_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    _write(
        tmp_path / "profile.work.toml",
        "[[inputs]]\npath = 'inbox'\n\n[[match_rules]]\nname = 'file'\nglob = '**'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "files", "--format", "json"])
    rows = json.loads(capsys.readouterr().out)

    assert list(rows[0]) == [
        "input",
        "path",
        "status",
        "mtime",
        "ctime",
        "sha256",
    ]
    assert "profile" not in rows[0]
    assert rows[0]["path"] == "a.txt"
    assert rows[0]["status"] == "new"
    assert "mtime" in rows[0]
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_db_show_prints_vars_in_one_cell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    _write(
        tmp_path / "profile.work.toml",
        "[default_vars]\nvendor = 'Bank2000'\n\n"
        "[vars_schema]\nvendor.type = 'text'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["db", "import"])
    capsys.readouterr()

    app.dispatch(["db", "show"])
    table = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "vendor: Bank2000" in table
    assert "vars" in table

    app.dispatch(["db", "show", "--format", "json"])
    rows = json.loads(capsys.readouterr().out)
    assert list(rows[0])[-1] == "vars"
    assert rows[0]["vars"] == {"vendor": "Bank2000"}
    assert "vendor" not in rows[0]


def test_scan_files_prefix_selects_paths_that_start_with(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    (inbox / "Bank2000").mkdir(parents=True)
    (inbox / "notes").mkdir()
    (inbox / "Bank2000" / "file.pdf").write_bytes(b"hello")
    (inbox / "Bank.txt").write_bytes(b"hello")
    (inbox / "notes" / "readme.txt").write_bytes(b"hello")
    _write(
        tmp_path / "profile.work.toml",
        "[[inputs]]\npath = 'inbox'\n\n[[match_rules]]\nname = 'file'\nglob = '**'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "files", "Bank"])
    output = capsys.readouterr().out

    assert "Bank2000/file.pdf" in output
    assert "Bank.txt" in output
    assert "readme.txt" not in output


def test_scan_files_exact_file_omits_a_longer_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    (inbox / "a.txt.bak").write_bytes(b"hello")
    _write(
        tmp_path / "profile.work.toml",
        "[[inputs]]\npath = 'inbox'\n\n[[match_rules]]\nname = 'file'\nglob = '**'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "files", "a.txt"])
    output = capsys.readouterr().out

    assert "a.txt" in output
    assert "a.txt.bak" not in output


def test_scan_files_unknown_path_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    _write(tmp_path / "profile.work.toml", "[[inputs]]\npath = 'inbox'\n")

    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["scan", "files", "missing.pdf"])

    assert caught.value.code == 1
    assert "No kept file 'missing.pdf'" in capsys.readouterr().err


def test_scan_diffs_hide_rows_import_would_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    target = inbox / "a.txt"
    target.write_bytes(b"hello")
    (inbox / "b.txt").write_bytes(b"there")
    _write(
        tmp_path / "profile.work.toml",
        "[default_vars]\nvendor = 'Bank2000'\n\n"
        "[vars_schema]\nvendor.type = 'text'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )
    app = App(parse=False)
    RecordSession.load(None, None, None).run(None, dry_run=False)
    capsys.readouterr()

    app.dispatch(["scan", "files"])
    app.dispatch(["scan", "match"])
    app.dispatch(["scan", "vars"])
    quiet = capsys.readouterr()
    assert "a.txt" not in quiet.out
    assert "b.txt" in quiet.out
    assert "No match_rule for b.txt" in quiet.err

    target.write_bytes(b"hello!")
    app.dispatch(["scan", "files"])
    changed = capsys.readouterr().out
    assert "generation" in changed
    assert "a.txt" in changed
    RecordSession.load(None, None, None).run(None, dry_run=False)

    (tmp_path / "profile.work.toml").write_text(
        "[default_vars]\nvendor = 'Other'\n\n"
        "[vars_schema]\nvendor.type = 'text'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'bills'\nkind = 'bill'\nfilename_glob = 'a.txt'\n",
        encoding="utf-8",
    )
    app.dispatch(["scan", "files"])
    assert "a.txt" not in capsys.readouterr().out
    app.dispatch(["scan", "match"])
    kinds = capsys.readouterr().out
    assert "bill" in kinds
    assert "bills" in kinds
    app.dispatch(["scan", "vars"])
    assert "vendor: Other" in capsys.readouterr().out


def test_scan_kinds_lists_matches_and_warns_for_the_rest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    (inbox / "b.txt").write_bytes(b"there")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "match"])
    captured = capsys.readouterr()

    assert "kind" in captured.out
    assert "rule" in captured.out
    assert "note" in captured.out
    assert "notes" in captured.out
    assert "a.txt" in captured.out
    assert "b.txt" in captured.out
    assert "sha256" not in captured.out
    assert "No match_rule for b.txt in profile work input 1" in captured.err
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_scan_match_prints_captured_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "2000_acme.pdf").write_bytes(b"bill")
    (inbox / "a.txt").write_bytes(b"note")
    (inbox / "b.txt").write_bytes(b"other")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'dated'\nkind = 'invoice'\n"
        "filename_regex = '(?P<year>\\d{4})_(?P<vendor>\\w+)\\.pdf'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\n"
        "filename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "match"])
    table = capsys.readouterr().out
    assert "groups" in table
    assert "year: 2000" in table
    assert "vendor: acme" in table

    app.dispatch(["scan", "match", "--format", "json"])
    rows = {row["path"]: row for row in json.loads(capsys.readouterr().out)}
    assert list(rows["2000_acme.pdf"]) == ["path", "kind", "rule", "groups"]
    assert rows["2000_acme.pdf"]["groups"] == "year: 2000\nvendor: acme"
    assert rows["a.txt"]["groups"] == ""
    assert rows["b.txt"]["groups"] == ""
    assert "status" not in rows["b.txt"]

    app.dispatch(["scan", "match", "--format", "json", "--columns", "path,status"])
    shown = {row["path"]: row for row in json.loads(capsys.readouterr().out)}
    assert list(shown["b.txt"]) == ["path", "status"]
    assert shown["b.txt"]["status"] == "unmatched"


def test_scan_kinds_prefix_warns_only_for_selected_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    (inbox / "sub").mkdir(parents=True)
    (inbox / "a.txt").write_bytes(b"hello")
    (inbox / "b.txt").write_bytes(b"there")
    (inbox / "sub" / "c.txt").write_bytes(b"more")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "match", "sub"])
    captured = capsys.readouterr()

    assert "a.txt" not in captured.out
    assert "b.txt" not in captured.err
    assert "No match_rule for sub/c.txt in profile work input 1" in captured.err


def test_scan_vars_lists_resolved_values_and_skips_unmatched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    (inbox / "b.txt").write_bytes(b"there")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[default_vars]\nvendor = 'Bank2000'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "vars"])
    captured = capsys.readouterr()

    assert "work" not in captured.out
    assert "vendor: Bank2000" in captured.out
    assert "note" in captured.out
    assert "a.txt" in captured.out
    assert "b.txt" not in captured.out
    assert "No match_rule for b.txt in profile work input 1" in captured.err
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_scan_vars_named_file_lists_only_that_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    (inbox / "b.txt").write_bytes(b"there")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[default_vars]\nvendor = 'Bank2000'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = '*.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["-v", "scan", "vars", "a.txt"])
    captured = capsys.readouterr()

    plain = re.sub(r"\x1b\[[0-9;]*m", "", captured.out)
    assert "a.txt" in plain
    assert "vendor: Bank2000" in plain
    assert "sources:" not in plain
    assert "| sources |" in plain
    assert "__match__.kind:" not in plain
    assert "file_ctime:" not in plain
    assert "file_mtime:" not in plain
    assert "b.txt" not in plain
    assert "No match_rule" not in captured.err

    app = App(parse=False)
    app.dispatch(["-v", "scan", "vars", "--all", "a.txt"])
    shown = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "__match__.kind:" in shown
    assert "vendor: Bank2000" in shown
    assert "file_ctime:" not in shown
    assert "file_mtime:" not in shown


def test_scan_vars_named_file_lists_each_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    for name in ("inbox", "other"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "a.txt").write_bytes(b"hello")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[inputs]]\npath = 'other'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "vars", "--format", "json", "--columns", "input,path", "a.txt"])
    captured = capsys.readouterr()
    rows = json.loads(captured.out)

    assert [row["input"] for row in rows] == [1, 2]
    assert [row["path"] for row in rows] == ["a.txt", "a.txt"]


def test_scan_vars_json_uses_python_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[vars_schema.amount]\ntype = 'int'\ndefault = 12\n\n"
        "[vars_schema.paid]\ntype = 'bool'\ndefault = false\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "vars", "--format", "json", "a.txt"])
    rows = json.loads(capsys.readouterr().out)
    amount = rows[0]["vars"]["amount"]
    paid = rows[0]["vars"]["paid"]

    assert amount["value"] == 12
    assert amount["value_sources"] == ["default"]
    assert paid["value"] is False
    assert "display" not in amount
    assert "sources" not in rows[0]


def test_scan_vars_named_unmatched_file_warns_only_for_that_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    (inbox / "b.txt").write_bytes(b"there")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "vars", "b.txt"])
    captured = capsys.readouterr()

    assert "a.txt" not in captured.out
    assert "No match_rule for b.txt in profile work input 1" in captured.err
    assert "No match_rule for a.txt" not in captured.err


def test_scan_vars_prefix_warns_only_for_selected_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    (inbox / "b.txt").write_bytes(b"there")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "vars", "b"])
    captured = capsys.readouterr()

    assert "a.txt" not in captured.out
    assert "No match_rule for b.txt in profile work input 1" in captured.err
    assert "No match_rule for a.txt" not in captured.err


def test_scan_vars_unknown_path_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    _write(tmp_path / "profile.work.toml", "[[inputs]]\npath = 'inbox'\n")

    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["scan", "vars", "missing.pdf"])

    assert caught.value.code == 1
    assert "No kept file 'missing.pdf'" in capsys.readouterr().err


def test_scan_vars_logs_a_kind_file_at_vv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    kind_file = tmp_path / "note.csv"
    kind_file.write_text("PATH,owner\na.txt,ada\n", encoding="utf-8")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n"
        "kind_overrides_config = ['{{ __config__.root_dir }}/note.csv']\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["-v", "scan", "vars"])
    quiet = capsys.readouterr()
    assert "owner: ada" in quiet.out
    assert "Loaded kind file" not in quiet.err

    app.dispatch(["-vv", "scan", "vars"])
    verbose = capsys.readouterr()
    assert f"Loaded kind file {kind_file.resolve()} for kind note" in verbose.err


def test_scan_vars_manual_flag_does_not_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    kind_file = tmp_path / "note.csv"
    kind_file.write_text("PATH\n", encoding="utf-8")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n"
        "kind_overrides_config = ['{{ __config__.root_dir }}/note.csv']\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["scan", "vars", "--kind-overrides-mode", "manual"])
    capsys.readouterr()
    assert kind_file.read_text(encoding="utf-8") == "PATH\n"

    app.dispatch(["scan", "vars"])
    assert kind_file.read_text(encoding="utf-8") == "PATH\n"


def test_scan_vars_rejects_a_bad_kind_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    app = App(parse=False)

    with pytest.raises(SystemExit) as caught:
        app.dispatch(["scan", "vars", "--kind-overrides-mode", "nope"])

    assert caught.value.code == 2
    error = capsys.readouterr().err
    assert "--kind-overrides-mode must be auto, manual, always, or disabled" in error


def test_scan_vars_dry_run_does_not_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    kind_file = tmp_path / "note.csv"
    kind_file.write_text("PATH\n", encoding="utf-8")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n"
        "kind_overrides_config = ['{{ __config__.root_dir }}/note.csv']\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["-v", "--dry-run", "scan", "vars"])
    captured = capsys.readouterr()
    assert kind_file.read_text(encoding="utf-8") == "PATH\n"
    assert "Would append" not in captured.err


def test_scan_kinds_rejects_a_bad_regex_before_walking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    _isolate(monkeypatch, tmp_path)
    _write(
        tmp_path / "profile.work.toml",
        "[[inputs]]\npath = 'missing-inbox'\n\n"
        "[[match_rules]]\nname = 'bad'\nkind = 'k'\nregex = '('\n",
    )

    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["scan", "match"])

    assert caught.value.code == 1
    assert "Invalid regex" in capsys.readouterr().err
    assert "missing-inbox" not in caplog.text


def test_scan_inspect_named_file_prints_the_pattern(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    folder = tmp_path / "inbox" / "company" / "bank2000_card"
    folder.mkdir(parents=True)
    (folder / "file.pdf").write_bytes(b"hello")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'bank2000_card'\nkind = 'invoice'\n"
        "directory_glob = ['company/bank2000_card/*']\n",
    )

    app = App(parse=False)
    app.dispatch(["inspect", "scan", "kinds", "company/bank2000_card/file.pdf"])
    captured = capsys.readouterr()

    assert (
        "directory_glob 'company/bank2000_card/*' "
        "against 'company/bank2000_card': miss"
    ) in captured.out
    assert (
        "No match_rule for company/bank2000_card/file.pdf in profile work input 1"
    ) in captured.out
    assert "skipped" not in captured.out
    assert "directory_glob" not in captured.err
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_scan_inspect_without_a_path_does_not_print_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    (inbox / "b.txt").write_bytes(b"there")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["inspect", "scan", "kinds"])
    captured = capsys.readouterr()

    assert "match profile work input 1 a.txt rule notes kind note" in captured.out
    assert "miss profile work input 1 b.txt" in captured.out
    assert "against" not in captured.out
    assert "filename_glob" not in captured.out
    assert "match profile" not in captured.err


def test_scan_inspect_prefix_traces_only_selected_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    folder = tmp_path / "inbox" / "company"
    folder.mkdir(parents=True)
    (folder / "a.txt").write_bytes(b"hello")
    (folder / "b.txt").write_bytes(b"there")
    (tmp_path / "inbox" / "other.txt").write_bytes(b"other")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["inspect", "scan", "kinds", "company"])
    captured = capsys.readouterr()

    assert "against 'a.txt': hit" in captured.out
    assert "against 'b.txt': miss" in captured.out
    assert "other.txt" not in captured.out
    assert "match profile" not in captured.out


def test_scan_inspect_verbose_prints_skipped_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "b.txt").write_bytes(b"there")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["-v", "inspect", "scan", "kinds", "b.txt"])
    captured = capsys.readouterr()

    assert "rule notes regex: skipped, no patterns" in captured.out
    assert "filename_glob 'a.txt' against 'b.txt': miss" in captured.out
    assert "skipped" not in captured.err


def test_scan_inspect_debug_prints_rules_that_were_not_tried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n\n"
        "[[match_rules]]\nname = 'later'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["-vv", "inspect", "scan", "kinds", "a.txt"])
    captured = capsys.readouterr()

    assert "filename_glob 'a.txt' against 'a.txt': hit" in captured.out
    assert "rule later filename_glob 'a.txt' against 'a.txt': not tried" in captured.out
    assert "stopped, later rules not tried" in captured.out
    assert "not tried" not in captured.err


def test_scan_inspect_traces_the_same_path_in_each_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    for name in ("inbox", "other"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "a.txt").write_bytes(b"hello")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[inputs]]\npath = 'other'\n\n"
        "[[match_rules]]\nname = 'notes'\nkind = 'note'\nfilename_glob = 'a.txt'\n",
    )

    app = App(parse=False)
    app.dispatch(["inspect", "scan", "kinds", "a.txt"])
    captured = capsys.readouterr()

    assert "profile work input 1" in captured.out
    assert "profile work input 2" in captured.out
    assert captured.out.count(": hit") == 2
    assert ": hit" not in captured.err


def test_scan_inspect_unknown_path_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_bytes(b"hello")
    _write(tmp_path / "profile.work.toml", "[[inputs]]\npath = 'inbox'\n")

    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["inspect", "scan", "kinds", "missing.pdf"])

    assert caught.value.code == 1
    assert "No kept file 'missing.pdf'" in capsys.readouterr().err


def test_scan_inspect_rejects_a_bad_regex_before_walking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    _isolate(monkeypatch, tmp_path)
    _write(
        tmp_path / "profile.work.toml",
        "[[inputs]]\npath = 'missing-inbox'\n\n"
        "[[match_rules]]\nname = 'bad'\nkind = 'k'\nregex = '('\n",
    )

    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["inspect", "scan", "kinds", "a.txt"])

    assert caught.value.code == 1
    assert "Invalid regex" in capsys.readouterr().err
    assert "missing-inbox" not in caplog.text


def test_bare_scan_dry_run_creates_nothing_and_does_not_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.pdf").write_bytes(b"bank-2000")
    _write(
        tmp_path / "profile.work.toml",
        "[config]\n"
        "kind_overrides_mode = 'always'\n"
        "kind_overrides_config = ['{{ __config__.root_dir }}/invoice.csv']\n\n"
        "[[inputs]]\npath = 'inbox'\n\n"
        "[[match_rules]]\nname = 'bill'\nkind = 'invoice'\nglob = '**'\n",
    )
    app = App(parse=False)
    app.dispatch(
        [
            "scan",
            "--dry-run",
            "--kind-overrides-mode",
            "always",
        ]
    )
    preview = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    vars_section = preview.split("=== vars ===", 1)[1].split("=== feeds ===", 1)[0]
    assert "| path " in vars_section
    assert "| kind " in vars_section
    assert "| vars " in vars_section
    assert "| sources " in vars_section
    assert "| input " not in vars_section
    assert "| sha " not in vars_section
    assert "| rule " not in vars_section
    assert "a.pdf" in preview
    assert "new" in preview
    assert "import" not in preview
    assert (tmp_path / "invoice.csv").exists() is False
    assert (tmp_path / "profile.work.sqlite").exists() is False
    assert (tmp_path / "profile.work.cache").exists() is False

    app.dispatch(["scan"])
    first = capsys.readouterr().out
    assert "new" in first
    assert "import" not in first
    assert (tmp_path / "invoice.csv").is_file()
    assert (tmp_path / "profile.work.sqlite").exists() is False

    app.dispatch(["scan"])
    again = capsys.readouterr().out
    assert "import" not in again
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_removed_commands_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / "profile.work.toml", "[[inputs]]\npath = 'inbox'\n")
    app = App(parse=False)
    for argv in (
        ["data"],
        ["record"],
        ["schema"],
        ["scan", "inspect"],
        ["scan", "import"],
        ["inspect", "scan", "import"],
    ):
        with pytest.raises(SystemExit) as caught:
            app.dispatch(argv)
        assert caught.value.code != 0


def test_schema_prints_json_for_the_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(
        tmp_path / "profile.work.toml",
        "[config]\nprofile = 'work'\n\n"
        "[vars_schema.amount]\ntype = 'float'\nunit = 'EUR'\n\n"
        "[kind_schema.invoice]\ndesc = 'A vendor bill'\n\n"
        "[kind_schema.invoice.vars_schema.amount]\nschema = 'amount'\nmandatory = true\n",
    )

    app = App(parse=False)
    app.dispatch(["inspect", "schema"])
    document = json.loads(capsys.readouterr().out)
    invoice = document["work"]["$defs"]["invoice"]

    assert invoice["required"] == ["amount"]
    assert invoice["properties"]["amount"]["x-unit"] == "EUR"
    assert invoice["additionalProperties"] is False


def test_schema_without_declarations_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / "profile.work.toml", "[config]\nprofile = 'work'\n")

    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["inspect", "schema"])

    assert caught.value.code == 2
    assert "vars_schema or kind_schema" in capsys.readouterr().err
