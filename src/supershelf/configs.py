"""Find, parse, and select shelf profile configs."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from supershelf.common import (
    choose_preferred,
    cli_or_env,
    load_mapping_file,
    name_from_prefixed_file,
    resolve_user_path,
    unique_csv,
    user_config_dir as app_user_config_dir,
)
from supershelf.constants import (
    CONFIG_SECTION,
    CONFIG_SUFFIXES,
    ENV_CONFIG,
    ENV_PROFILES,
    LOGGER_NAME,
    PROFILE_KEY,
    PROFILE_PREFIX,
    SINGLETON_STEM,
)
from supershelf.defaults import PACKAGED
from supershelf.errors import SupershelfError

_NO_CONFIG_ADVICE = (
    "Pass --config, set SUPERSHELF_CONFIG, or add supershelf.toml "
    "or profile.<name>.toml in the current directory or the user config directory."
)
_EMPTY_PROFILE_LIST = "Profile list contains an empty name"


class ProfileSettings(BaseModel):
    """The `config` section. Other keys are kept for later steps."""

    model_config = ConfigDict(extra="allow")

    profile: str | None = None


class ShelfDocument(BaseModel):
    """Top-level config file. Only `config.profile` is checked for now."""

    model_config = ConfigDict(extra="allow")

    config: ProfileSettings | None = None


@dataclass(frozen=True)
class ShelfConfig:
    """One loaded profile file."""

    profile: str
    type: str
    path: Path
    config: dict[str, Any]

    @classmethod
    def from_path(cls, path: Path, logger: logging.Logger) -> ShelfConfig:
        document, file_type = cls._read_document(path)
        profile = cls._resolve_profile(path, document, logger)
        cls._assign_profile(document, profile)
        return cls(
            profile=profile,
            type=file_type,
            path=path.resolve(),
            config=document,
        )

    @staticmethod
    def _read_document(path: Path) -> tuple[dict[str, Any], str]:
        data, file_type = load_mapping_file(path)
        if not isinstance(data, dict):
            raise SupershelfError(f"Config file must be a mapping: {path}")
        try:
            ShelfDocument.model_validate(data)
        except ValidationError as exc:
            raise SupershelfError(f"Invalid config {path}: {exc}") from exc
        return data, file_type

    @staticmethod
    def _configured_profile(document: dict[str, Any]) -> str | None:
        section = document.get(CONFIG_SECTION)
        if not isinstance(section, dict):
            return None
        value = section.get(PROFILE_KEY)
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None

    @classmethod
    def _resolve_profile(
        cls,
        path: Path,
        document: dict[str, Any],
        logger: logging.Logger,
    ) -> str:
        name_from_file = name_from_prefixed_file(path.name, PROFILE_PREFIX, CONFIG_SUFFIXES)
        file_profile = cls._configured_profile(document)
        if name_from_file is not None:
            if file_profile is not None and file_profile != name_from_file:
                logger.warning(
                    "config.profile %r in %s will be ignored; profile name is %r",
                    file_profile,
                    path,
                    name_from_file,
                )
            return name_from_file
        if file_profile is not None:
            return file_profile
        return PACKAGED.profile

    @staticmethod
    def _assign_profile(document: dict[str, Any], profile: str) -> None:
        section = document.get(CONFIG_SECTION)
        if not isinstance(section, dict):
            document[CONFIG_SECTION] = {PROFILE_KEY: profile}
            return
        section[PROFILE_KEY] = profile


class ShelfConfigs:
    """The profiles selected for this run."""

    def __init__(self, config_list: list[ShelfConfig]) -> None:
        self.config_list = list(config_list)

    @classmethod
    def load(
        cls,
        *,
        config_option: str | None = None,
        profile_option: str | None = None,
        cwd: Path | None = None,
        environ: Mapping[str, str] | None = None,
        user_config_dir: Path | None = None,
    ) -> ShelfConfigs:
        """Load configs. CLI options win over env, then cwd, then the user dir."""
        work_dir = Path.cwd() if cwd is None else Path(cwd)
        env = os.environ if environ is None else environ
        logger = logging.getLogger(LOGGER_NAME)
        home_dir = (
            Path(user_config_dir) if user_config_dir is not None else app_user_config_dir(env)
        )
        paths = cls._discover_paths(
            config_option=config_option,
            work_dir=work_dir,
            env=env,
            user_dir=home_dir,
            logger=logger,
        )
        loaded = [ShelfConfig.from_path(path, logger) for path in paths]
        loaded = cls._drop_duplicate_profiles(loaded, logger)
        selected = cls._select_profiles(loaded, profile_option, env)
        return cls(selected)

    @classmethod
    def _discover_paths(
        cls,
        *,
        config_option: str | None,
        work_dir: Path,
        env: Mapping[str, str],
        user_dir: Path,
        logger: logging.Logger,
    ) -> list[Path]:
        explicit = cli_or_env(
            config_option,
            env,
            ENV_CONFIG,
            blank_option_message="--config requires a path",
        )
        if explicit is not None:
            path = resolve_user_path(explicit, work_dir)
            if not path.exists():
                raise SupershelfError(f"Config path not found: {path}")
            found = cls._paths_from_source(path, allow_singleton=True, logger=logger)
            if not found:
                raise SupershelfError(
                    f"No config files found in {path}",
                    advice="Expected supershelf.toml or profile.<name>.toml.",
                )
            return found

        found = cls._paths_in_directory(work_dir, allow_singleton=True, logger=logger)
        if found:
            return found

        found = cls._paths_in_directory(user_dir, allow_singleton=False, logger=logger)
        if found:
            return found

        raise SupershelfError(
            "No supershelf config found",
            advice=f"Looked in {work_dir} and {user_dir}. {_NO_CONFIG_ADVICE}",
        )

    @classmethod
    def _paths_from_source(
        cls,
        path: Path,
        *,
        allow_singleton: bool,
        logger: logging.Logger,
    ) -> list[Path]:
        if path.is_file():
            return [path]
        if path.is_dir():
            return cls._paths_in_directory(
                path,
                allow_singleton=allow_singleton,
                logger=logger,
            )
        raise SupershelfError(f"Config path not found: {path}")

    @classmethod
    def _paths_in_directory(
        cls,
        directory: Path,
        *,
        allow_singleton: bool,
        logger: logging.Logger,
    ) -> list[Path]:
        """General `supershelf.*` wins. Otherwise load `profile.<name>.*`."""
        if not directory.is_dir():
            return []
        if allow_singleton:
            candidates = [directory / f"{SINGLETON_STEM}{suffix}" for suffix in CONFIG_SUFFIXES]
            existing = [path for path in candidates if path.is_file()]
            singleton = choose_preferred(existing, subject=None, logger=logger)
            if singleton is not None:
                return [singleton]
        return cls._named_profile_files(directory, logger)

    @staticmethod
    def _named_profile_files(directory: Path, logger: logging.Logger) -> list[Path]:
        grouped: dict[str, list[Path]] = {}
        for path in directory.iterdir():
            if not path.is_file():
                continue
            name = name_from_prefixed_file(path.name, PROFILE_PREFIX, CONFIG_SUFFIXES)
            if name is None:
                continue
            grouped.setdefault(name, []).append(path)

        chosen: list[Path] = []
        for name in sorted(grouped):
            best = choose_preferred(grouped[name], subject=f"profile {name}", logger=logger)
            if best is not None:
                chosen.append(best)
        return chosen

    @staticmethod
    def _drop_duplicate_profiles(
        items: list[ShelfConfig],
        logger: logging.Logger,
    ) -> list[ShelfConfig]:
        kept: list[ShelfConfig] = []
        seen: dict[str, ShelfConfig] = {}
        for item in items:
            previous = seen.get(item.profile)
            if previous is not None:
                logger.warning(
                    "%s will be ignored; profile %s was already loaded from %s",
                    item.path,
                    item.profile,
                    previous.path,
                )
                continue
            seen[item.profile] = item
            kept.append(item)
        return kept

    @staticmethod
    def _select_profiles(
        items: list[ShelfConfig],
        profile_option: str | None,
        env: Mapping[str, str],
    ) -> list[ShelfConfig]:
        selector = cli_or_env(
            profile_option,
            env,
            ENV_PROFILES,
            blank_option_message="--profile requires a comma-separated list of names",
        )
        if selector is None:
            return items
        requested = unique_csv(selector, empty_item_message=_EMPTY_PROFILE_LIST)
        by_name = {item.profile: item for item in items}
        selected: list[ShelfConfig] = []
        for name in requested:
            match = by_name.get(name)
            if match is None:
                known = ", ".join(item.profile for item in items) or "(none)"
                raise SupershelfError(
                    f"Unknown profile {name!r}",
                    advice=f"Known profiles: {known}",
                )
            selected.append(match)
        return selected
