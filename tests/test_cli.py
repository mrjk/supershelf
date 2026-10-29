"""`supershelf profiles` command."""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from supershelf.cli import App
from supershelf.constants import LOGGER_NAME


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SUPERSHELF_CONFIG", raising=False)
    monkeypatch.delenv("SUPERSHELF_PROFILES", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


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
        "[[inputs]]\npath = 'inbox'\n",
    )
    _write(
        tmp_path / "profile.home.toml",
        "[config]\nprofile = 'home'\ndefault_date_format = '%d/%m/%Y'\n\n"
        "[[inputs]]\npath = 'other'\n",
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


def test_scan_files_quick_omits_metadata(
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
    app.dispatch(["scan", "files", "--quick"])
    output = capsys.readouterr().out

    assert "a.txt" in output
    assert "sha256" not in output
    assert "mtime" not in output


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
    app.dispatch(["scan", "kinds"])
    captured = capsys.readouterr()

    assert "kind" in captured.out
    assert "rule" in captured.out
    assert "note" in captured.out
    assert "notes" in captured.out
    assert "a.txt" in captured.out
    assert "b.txt" not in captured.out
    assert "sha256" not in captured.out
    assert "No match_rule for b.txt in profile work input 1" in captured.err
    assert (tmp_path / "profile.work.sqlite").exists() is False


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
        app.dispatch(["scan", "kinds"])

    assert caught.value.code == 1
    assert "Invalid regex" in capsys.readouterr().err
    assert "missing-inbox" not in caplog.text
