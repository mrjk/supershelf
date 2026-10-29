"""Rendered profile paths."""

import logging
from pathlib import Path

import pytest

from supershelf.configs import ShelfConfig
from supershelf.constants import DEFAULT_DATE_FORMAT, LOGGER_NAME
from supershelf.errors import SupershelfError
from supershelf.profile import ShelfProfile


def _profile(tmp_path: Path, body: str, name: str = "work") -> ShelfProfile:
    path = tmp_path / f"profile.{name}.toml"
    path.write_text(body, encoding="utf-8")
    loaded = ShelfConfig.from_path(path, logging.getLogger(LOGGER_NAME))
    return ShelfProfile.from_config(loaded)


def test_omitted_paths_use_the_config_directory(tmp_path: Path) -> None:
    profile = _profile(tmp_path, "[config]\nprofile = 'work'\n")
    root = tmp_path.resolve()

    assert profile.name == "work"
    assert profile.scope["__profile__"] == "work"
    assert profile.scope["__profile_name__"] == "work"
    assert profile.scope["__profile_dir__"] == str(root)
    assert profile.scope["__profile_file__"] == "profile.work.toml"
    assert profile.default_date_format == DEFAULT_DATE_FORMAT
    assert profile.root_dir == root
    assert profile.database_file == root / "profile.work.sqlite"
    assert profile.cache_file == root / "profile.work.cache"
    assert profile.database_file.exists() is False
    assert profile.cache_file.exists() is False


def test_relative_root_dir_is_joined_before_later_paths(tmp_path: Path) -> None:
    profile = _profile(tmp_path, "[config]\nroot_dir = 'data'\n")

    assert profile.root_dir == (tmp_path / "data").resolve()
    assert profile.database_file == (tmp_path / "data" / "profile.work.sqlite").resolve()
    assert profile.cache_file == (tmp_path / "data" / "profile.work.cache").resolve()
    assert profile.scope["__root_dir__"] == str(profile.root_dir)


def test_default_date_format_is_not_templated(tmp_path: Path) -> None:
    profile = _profile(
        tmp_path,
        "[config]\ndefault_date_format = '{{ __profile__ }}'\n",
    )

    assert profile.default_date_format == "{{ __profile__ }}"


def test_root_dir_must_be_a_string(tmp_path: Path) -> None:
    with pytest.raises(SupershelfError, match="config.root_dir must be a string"):
        _profile(tmp_path, "[config]\nroot_dir = 1\n")


def test_unknown_template_name_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(SupershelfError, match="Unknown template name 'missing'"):
        _profile(tmp_path, "[config]\nroot_dir = '{{ missing }}'\n")
