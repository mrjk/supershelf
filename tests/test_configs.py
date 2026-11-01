"""Discovery and profile selection."""

import logging
from pathlib import Path

import pytest

from supershelf.configs import ShelfConfig, ShelfConfigs, ShelfDocument
from supershelf.constants import (
    CONFIG_SECTION,
    ENV_CONFIG,
    ENV_PROFILES,
    LOGGER_NAME,
    PROFILE_KEY,
)
from supershelf.defaults import PACKAGED
from supershelf.errors import SupershelfError
from tests.helpers import write_text as _write

WORK_TOML = """\
note = "keep"

[config]
profile = "work"
"""

OTHER_TOML = """\
[config]
profile = "other"
"""

HOME_YAML = """\
config:
  profile: home
"""


def _load(tmp_path: Path, **kwargs) -> ShelfConfigs:
    environ = kwargs.pop("environ", {})
    return ShelfConfigs.load(
        cwd=tmp_path,
        environ=environ,
        user_config_dir=tmp_path / "user-config",
        **kwargs,
    )


def _names(loaded: ShelfConfigs) -> list[str]:
    return [item.profile for item in loaded.config_list]


def test_singleton_wins_over_named_profiles(tmp_path: Path) -> None:
    _write(tmp_path / "supershelf.toml", "[config]\nprofile = 'main'\n")
    _write(tmp_path / "profile.work.toml", WORK_TOML)

    loaded = _load(tmp_path)

    assert _names(loaded) == ["main"]
    assert loaded.config_list[0].type == "toml"
    assert loaded.config_list[0].config[CONFIG_SECTION][PROFILE_KEY] == "main"


def test_named_profiles_when_no_singleton(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    _write(tmp_path / "profile.b.yaml", "config:\n  profile: b\n")
    _write(tmp_path / "profile.a.toml", "[config]\nprofile = 'a'\n")
    _write(tmp_path / "profile.a.yml", "config:\n  profile: ignored\n")

    loaded = _load(tmp_path)

    assert _names(loaded) == ["a", "b"]
    assert [item.type for item in loaded.config_list] == ["toml", "yaml"]
    assert "profile.a.yml" in caplog.text
    assert "will be ignored" in caplog.text


def test_singleton_yaml_preferred_over_yml(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    _write(tmp_path / "supershelf.yaml", HOME_YAML)
    _write(tmp_path / "supershelf.yml", "config:\n  profile: ignored\n")
    _write(tmp_path / "profile.work.toml", WORK_TOML)

    loaded = _load(tmp_path)

    assert _names(loaded) == ["home"]
    assert loaded.config_list[0].type == "yaml"
    assert "supershelf.yml" in caplog.text


def test_yml_singleton_type_is_yaml(tmp_path: Path) -> None:
    _write(tmp_path / "supershelf.yml", HOME_YAML)

    loaded = _load(tmp_path)

    item = loaded.config_list[0]
    assert item.profile == "home"
    assert item.type == "yaml"


def test_missing_profile_key_becomes_default(tmp_path: Path) -> None:
    _write(tmp_path / "supershelf.toml", "note = 'x'\n")

    loaded = _load(tmp_path)

    item = loaded.config_list[0]
    assert item.profile == PACKAGED.profile
    assert item.config["note"] == "x"
    assert item.config[CONFIG_SECTION][PROFILE_KEY] == PACKAGED.profile


def test_filename_wins_and_mismatch_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    _write(tmp_path / "profile.work.toml", OTHER_TOML)

    loaded = _load(tmp_path)

    item = loaded.config_list[0]
    assert item.profile == "work"
    assert item.config[CONFIG_SECTION][PROFILE_KEY] == "work"
    assert "will be ignored" in caplog.text
    assert "other" in caplog.text


def test_matching_filename_profile_does_not_warn(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    _write(tmp_path / "profile.work.toml", WORK_TOML)

    loaded = _load(tmp_path)

    assert _names(loaded) == ["work"]
    assert loaded.config_list[0].config["note"] == "keep"
    assert caplog.records == []


def test_config_option_beats_cwd_and_env(tmp_path: Path) -> None:
    chosen = tmp_path / "chosen" / "profile.home.yaml"
    _write(chosen, HOME_YAML)
    _write(tmp_path / "profile.work.toml", WORK_TOML)
    _write(tmp_path / "env" / "supershelf.toml", "[config]\nprofile = 'env'\n")

    loaded = _load(
        tmp_path,
        config_option=str(chosen),
        environ={ENV_CONFIG: str(tmp_path / "env" / "supershelf.toml")},
    )

    assert _names(loaded) == ["home"]


def test_env_config_beats_cwd(tmp_path: Path) -> None:
    env_file = tmp_path / "env" / "supershelf.toml"
    _write(env_file, "[config]\nprofile = 'from-env'\n")
    _write(tmp_path / "profile.work.toml", WORK_TOML)

    loaded = _load(tmp_path, environ={ENV_CONFIG: str(env_file)})

    assert _names(loaded) == ["from-env"]


def test_missing_explicit_config_does_not_fall_through(tmp_path: Path) -> None:
    _write(tmp_path / "profile.work.toml", WORK_TOML)

    with pytest.raises(SupershelfError, match="Config path not found"):
        _load(tmp_path, config_option=str(tmp_path / "missing.toml"))


def test_empty_explicit_directory_does_not_fall_through(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    user = tmp_path / "user-config"
    _write(user / "profile.work.toml", WORK_TOML)

    with pytest.raises(SupershelfError, match="No config files found"):
        _load(tmp_path, config_option=str(empty))


def test_cwd_empty_uses_user_config_profiles_only(tmp_path: Path) -> None:
    user = tmp_path / "user-config"
    _write(user / "supershelf.toml", "[config]\nprofile = 'hidden'\n")
    _write(user / "profile.work.toml", WORK_TOML)
    _write(user / "profile.home.yaml", HOME_YAML)

    loaded = _load(tmp_path)

    assert _names(loaded) == ["home", "work"]


def test_user_config_singleton_alone_is_not_used(tmp_path: Path) -> None:
    _write(tmp_path / "user-config" / "supershelf.toml", "[config]\nprofile = 'hidden'\n")

    with pytest.raises(SupershelfError, match="No supershelf config found"):
        _load(tmp_path)


def test_profile_option_filters_and_orders(tmp_path: Path) -> None:
    _write(tmp_path / "profile.a.toml", "[config]\nprofile = 'a'\n")
    _write(tmp_path / "profile.b.toml", "[config]\nprofile = 'b'\n")
    _write(tmp_path / "profile.c.toml", "[config]\nprofile = 'c'\n")

    loaded = _load(tmp_path, profile_option="c, a")

    assert _names(loaded) == ["c", "a"]


def test_profile_option_beats_env(tmp_path: Path) -> None:
    _write(tmp_path / "profile.a.toml", "[config]\nprofile = 'a'\n")
    _write(tmp_path / "profile.b.toml", "[config]\nprofile = 'b'\n")

    loaded = _load(
        tmp_path,
        profile_option="b",
        environ={ENV_PROFILES: "a"},
    )

    assert _names(loaded) == ["b"]


def test_env_profiles_used_when_option_absent(tmp_path: Path) -> None:
    _write(tmp_path / "profile.a.toml", "[config]\nprofile = 'a'\n")
    _write(tmp_path / "profile.b.toml", "[config]\nprofile = 'b'\n")

    loaded = _load(tmp_path, environ={ENV_PROFILES: "b, a"})

    assert _names(loaded) == ["b", "a"]


def test_unknown_profile_is_an_error(tmp_path: Path) -> None:
    _write(tmp_path / "profile.work.toml", WORK_TOML)

    with pytest.raises(SupershelfError, match="Unknown profile 'missing'") as caught:
        _load(tmp_path, profile_option="missing")

    assert caught.value.advice is not None
    assert "work" in caught.value.advice


def test_profile_must_be_a_string(tmp_path: Path) -> None:
    _write(tmp_path / "supershelf.yaml", "config:\n  profile: 1\n")

    with pytest.raises(SupershelfError, match="Invalid config"):
        _load(tmp_path)


def test_document_must_be_a_mapping(tmp_path: Path) -> None:
    _write(tmp_path / "supershelf.yaml", "- one\n- two\n")

    with pytest.raises(SupershelfError, match="must be a mapping"):
        _load(tmp_path)


def test_invalid_toml(tmp_path: Path) -> None:
    _write(tmp_path / "supershelf.toml", "this is not =\n")

    with pytest.raises(SupershelfError, match="Invalid TOML"):
        _load(tmp_path)


def test_duplicate_resolved_profile_keeps_the_first(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    first = ShelfConfig(profile="work", type="toml", path=Path("/a.toml"), config={})
    second = ShelfConfig(profile="work", type="yaml", path=Path("/b.yaml"), config={})
    logger = logging.getLogger(LOGGER_NAME)

    kept = ShelfConfigs._drop_duplicate_profiles([first, second], logger)

    assert kept == [first]
    assert "b.yaml" in caplog.text
    assert "will be ignored" in caplog.text


def test_schema_describes_config_profile() -> None:
    schema = ShelfDocument.model_json_schema()

    assert CONFIG_SECTION in schema["properties"]
    assert PROFILE_KEY in schema["$defs"]["ProfileSettings"]["properties"]
