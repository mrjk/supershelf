"""`supershelf inspect config`."""

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from supershelf.cli import App
from supershelf.defaults import PACKAGED
from supershelf.errors import SupershelfError
from supershelf.inspect_config import InspectedConfig
from tests.helpers import isolate_env as _isolate
from tests.helpers import load_profile as _profile
from tests.helpers import write_text as _write

_BODY = """\
[config]
root_dir = "{{ __profile__.dir }}/data"
kind_overrides_config = ["{{ __config__.root_dir }}/{{ __match__.kind }}.csv"]

[[inputs]]
path = "{{ __config__.root_dir }}/inbox"
"""


def test_resolved_paths_keep_later_templates(tmp_path: Path) -> None:
    profile = _profile(tmp_path, _BODY)
    body = InspectedConfig([profile]).document()
    section = body["config"]

    assert section["root_dir"] == str(profile.root_dir)
    assert section["database_file"] == str(profile.database_file)
    assert section["cache_file"] == str(profile.cache_file)
    assert section["default_date_format"] == PACKAGED.default_date_format
    assert section["kind_overrides_config"] == [
        "{{ __config__.root_dir }}/{{ __match__.kind }}.csv"
    ]
    assert body["inputs"][0]["path"] == "{{ __config__.root_dir }}/inbox"
    assert profile.document["config"]["root_dir"] == "{{ __profile__.dir }}/data"
    assert "database_file" not in profile.document["config"]
    assert profile.database_file.exists() is False


def test_toml_default_prints_resolved_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / "profile.work.toml", _BODY)

    app = App(parse=False)
    app.dispatch(["inspect", "config"])

    loaded = tomllib.loads(capsys.readouterr().out)
    database = Path(loaded["config"]["database_file"])
    assert database == (tmp_path / "data" / "profile.work.sqlite").resolve()
    assert database.exists() is False
    assert loaded["config"]["kind_overrides_config"] == [
        "{{ __config__.root_dir }}/{{ __match__.kind }}.csv"
    ]


def test_yaml_default_prints_resolved_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(
        tmp_path / "profile.work.yaml",
        "config:\n"
        "  root_dir: '{{ __profile__.dir }}/data'\n"
        "inputs:\n"
        "  - path: '{{ __config__.root_dir }}/inbox'\n",
    )

    app = App(parse=False)
    app.dispatch(["inspect", "config"])

    loaded = yaml.safe_load(capsys.readouterr().out)
    assert loaded["config"]["root_dir"] == str((tmp_path / "data").resolve())
    assert loaded["inputs"][0]["path"] == "{{ __config__.root_dir }}/inbox"
    assert Path(loaded["config"]["database_file"]).exists() is False


def test_format_json_overrides_the_profile_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / "profile.work.toml", "[config]\nprofile = 'work'\n")

    app = App(parse=False)
    app.dispatch(["inspect", "config", "--format", "json"])

    loaded = json.loads(capsys.readouterr().out)
    assert loaded["config"]["profile"] == "work"
    assert loaded["config"]["database_file"].endswith("profile.work.sqlite")
    assert (tmp_path / "profile.work.sqlite").exists() is False


def test_mixed_types_stop_without_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / "profile.home.toml", "[config]\nprofile = 'home'\n")
    _write(tmp_path / "profile.work.yaml", "config:\n  profile: work\n")

    app = App(parse=False)
    with pytest.raises(SystemExit) as caught:
        app.dispatch(["inspect", "config"])

    assert caught.value.code == 1
    assert "more than one config type" in capsys.readouterr().err


def test_mixed_types_with_format_key_by_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / "profile.home.toml", "[config]\nprofile = 'home'\n")
    _write(tmp_path / "profile.work.yaml", "config:\n  profile: work\n")

    app = App(parse=False)
    app.dispatch(["inspect", "config", "--format", "json"])

    loaded = json.loads(capsys.readouterr().out)
    assert set(loaded) == {"home", "work"}
    assert loaded["home"]["config"]["root_dir"]
    assert loaded["work"]["config"]["cache_file"].endswith("profile.work.cache")


def test_file_type_rejects_mixed_profiles(tmp_path: Path) -> None:
    home = _profile(tmp_path, "[config]\nprofile = 'home'\n", name="home")
    work = _profile(
        tmp_path,
        "config:\n  profile: work\n",
        name="work",
        suffix=".yaml",
    )

    with pytest.raises(SupershelfError, match="more than one config type"):
        InspectedConfig([home, work]).file_type()
