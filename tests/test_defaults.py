"""Packaged defaults and the null-is-unset fallback."""

from importlib.resources import files
from pathlib import Path

import pytest

from supershelf.constants import VAR_DEFAULT_DATE_FORMAT
from supershelf.defaults import PACKAGED, load_packaged
from supershelf.errors import SupershelfError, VarConfigError
from supershelf.kind_file import KindCsvSep, KindDateFormat, KindFiles, KindOverrideMode
from tests.helpers import load_profile as _profile


def _shipped_text() -> str:
    return files("supershelf").joinpath("default.toml").read_text(encoding="utf-8")


def _write_packaged(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "default.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _inbox(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_text("a", encoding="utf-8")


def _kinds(section: dict[str, object], root: Path) -> KindFiles:
    return KindFiles.from_section(
        section,
        root,
        {"__root_dir__": str(root), "__profile__": "work"},
        PACKAGED.kind_overrides_mode,
        KindDateFormat.from_section({}, {}),
        True,
    )


def test_shipped_defaults_match_the_architecture() -> None:
    assert PACKAGED.profile == "default"
    assert PACKAGED.default_date_format == "%Y-%m-%d"
    assert PACKAGED.root_dir == "{{ __profile_dir__ }}"
    assert PACKAGED.database_file == "{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite"
    assert PACKAGED.cache_file == "{{ __root_dir__ }}/profile.{{ __profile__ }}.cache"
    assert PACKAGED.record_identity == "path"
    assert PACKAGED.kind_overrides_mode == "auto"
    assert PACKAGED.kind_overrides_sep == ","
    assert PACKAGED.kind_overrides_config == [
        "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.csv",
        "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.toml",
        "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yaml",
        "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yml",
    ]
    assert PACKAGED.input_depth == 0
    assert PACKAGED.input_follow_symlinks is True
    assert PACKAGED.kind_overrides_date_format is None
    assert PACKAGED.var_modules is None


def test_loader_rejects_a_missing_concrete_key(tmp_path: Path) -> None:
    text = _shipped_text().replace('profile = "default"\n', "")
    with pytest.raises(SupershelfError, match="profile"):
        load_packaged(_write_packaged(tmp_path, text))


def test_loader_rejects_a_wrong_type(tmp_path: Path) -> None:
    text = _shipped_text().replace(
        'default_date_format = "%Y-%m-%d"',
        "default_date_format = 1",
    )
    with pytest.raises(SupershelfError, match="default_date_format"):
        load_packaged(_write_packaged(tmp_path, text))


def test_loader_rejects_an_unknown_key(tmp_path: Path) -> None:
    text = _shipped_text().replace(
        "input_follow_symlinks = true\n",
        'input_follow_symlinks = true\nbogus = "x"\n',
    )
    with pytest.raises(SupershelfError, match="bogus"):
        load_packaged(_write_packaged(tmp_path, text))


def test_null_profile_values_use_the_packaged_defaults(tmp_path: Path) -> None:
    omitted = _profile(tmp_path, "[config]\nprofile = 'work'\n")
    nulled = _profile(
        tmp_path,
        "config:\n"
        "  default_date_format: null\n"
        "  root_dir: null\n"
        "  database_file: null\n"
        "  cache_file: null\n",
        suffix=".yaml",
    )

    assert nulled.default_date_format == PACKAGED.default_date_format
    assert nulled.root_dir == omitted.root_dir
    assert nulled.database_file == omitted.database_file
    assert nulled.cache_file == omitted.cache_file
    assert nulled.scope[VAR_DEFAULT_DATE_FORMAT] == PACKAGED.default_date_format


def test_empty_date_format_and_root_dir_do_not_fall_back(tmp_path: Path) -> None:
    with pytest.raises(SupershelfError, match="non-empty"):
        _profile(tmp_path, "[config]\ndefault_date_format = ''\n")
    with pytest.raises(SupershelfError, match="non-empty"):
        _profile(tmp_path, "[config]\ndefault_date_format = '   '\n")
    with pytest.raises(SupershelfError, match="config.root_dir is empty"):
        _profile(tmp_path, "[config]\nroot_dir = ''\n")


def test_kind_date_format_falls_back_only_when_unset() -> None:
    user = {"default_date_format": "%d/%m/%Y"}
    assert KindDateFormat.from_section(user, {}).text == "%d/%m/%Y"
    assert KindDateFormat.from_section({}, {}).text == PACKAGED.default_date_format
    assert (
        KindDateFormat.from_section(
            {"kind_overrides_date_format": None, **user},
            {},
        ).text
        == "%d/%m/%Y"
    )
    assert (
        KindDateFormat.from_section({"default_date_format": None}, {}).text
        == PACKAGED.default_date_format
    )
    assert (
        KindDateFormat.from_section(
            {"default_date_format": None},
            {VAR_DEFAULT_DATE_FORMAT: "%d/%m/%Y"},
        ).text
        == "%d/%m/%Y"
    )
    with pytest.raises(VarConfigError, match="kind_overrides_date_format"):
        KindDateFormat.from_section(
            {"kind_overrides_date_format": "", **user},
            {},
        )


def test_null_kind_settings_use_the_packaged_values() -> None:
    assert KindCsvSep.from_section({"kind_overrides_sep": None}).text == (
        PACKAGED.kind_overrides_sep
    )
    assert KindOverrideMode.resolve({"kind_overrides_mode": None}, None, {}) == (
        PACKAGED.kind_overrides_mode
    )
    with pytest.raises(VarConfigError, match="kind_overrides_sep"):
        KindCsvSep.from_section({"kind_overrides_sep": ""})
    with pytest.raises(VarConfigError, match="kind_overrides_mode"):
        KindOverrideMode.resolve({"kind_overrides_mode": ""}, None, {})


def test_null_kind_paths_use_the_packaged_templates(tmp_path: Path) -> None:
    nulled = _kinds({"kind_overrides_config": None}, tmp_path)
    empty = _kinds({"kind_overrides_config": []}, tmp_path)

    assert nulled._templates == tuple(PACKAGED.kind_overrides_config)
    assert empty._templates == ()


def test_null_inputs_is_the_no_inputs_error(tmp_path: Path) -> None:
    profile = _profile(tmp_path, "inputs: null\n", suffix=".yaml")

    with pytest.raises(SupershelfError, match="no inputs"):
        profile.scan()


def test_empty_inputs_stays_empty(tmp_path: Path) -> None:
    profile = _profile(tmp_path, "inputs = []\n")

    with pytest.raises(SupershelfError, match="inputs is empty"):
        profile.scan()


def test_omitted_and_null_depth_use_the_packaged_value(tmp_path: Path) -> None:
    _inbox(tmp_path)
    omitted = _profile(tmp_path, "[[inputs]]\npath = 'inbox'\n")
    nulled = _profile(
        tmp_path,
        "inputs:\n  - path: inbox\n    depth: null\n",
        suffix=".yaml",
    )

    assert omitted.scan()[0].config.depth == PACKAGED.input_depth
    assert nulled.scan()[0].config.depth == PACKAGED.input_depth


def test_explicit_zero_depth_stays_zero(tmp_path: Path) -> None:
    _inbox(tmp_path)
    profile = _profile(tmp_path, "[[inputs]]\npath = 'inbox'\ndepth = 0\n")

    assert profile.scan()[0].config.depth == 0


def test_null_follow_symlinks_uses_the_packaged_value(tmp_path: Path) -> None:
    _inbox(tmp_path)
    profile = _profile(
        tmp_path,
        "inputs:\n  - path: inbox\n    follow_symlinks: null\n",
        suffix=".yaml",
    )

    assert profile.scan()[0].config.follow_symlinks is PACKAGED.input_follow_symlinks
