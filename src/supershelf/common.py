"""Small helpers shared by later steps."""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from supershelf.constants import (
    APP_NAME,
    CONFIG_SUFFIXES,
    FILE_TYPE_TOML,
    SUFFIX_TYPES,
)
from supershelf.errors import SupershelfError


def user_config_dir(environ: Mapping[str, str]) -> Path:
    """`$XDG_CONFIG_HOME/supershelf`, or `~/.config/supershelf`."""
    xdg_home = environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        return Path(xdg_home).expanduser() / APP_NAME
    return Path.home() / ".config" / APP_NAME


def resolve_user_path(value: str, base: Path) -> Path:
    """Expand `~` and resolve a relative path against `base`."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path


def cli_or_env(
    option: str | None,
    environ: Mapping[str, str],
    env_name: str,
    *,
    blank_option_message: str,
) -> str | None:
    """CLI text wins. A blank env value is treated as unset."""
    if option is not None:
        text = option.strip()
        if not text:
            raise SupershelfError(blank_option_message)
        return text
    env_value = environ.get(env_name)
    if env_value is None:
        return None
    return env_value.strip() or None


def unique_csv(text: str, *, empty_item_message: str) -> list[str]:
    """Split a comma-separated list, drop repeats, and keep the first order."""
    names = [part.strip() for part in text.split(",")]
    if any(not name for name in names):
        raise SupershelfError(empty_item_message)
    ordered: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def name_from_prefixed_file(
    filename: str,
    prefix: str,
    suffixes: tuple[str, ...],
) -> str | None:
    """Return the text between `prefix` and a known suffix, or None."""
    for suffix in suffixes:
        if filename.startswith(prefix) and filename.endswith(suffix):
            name = filename[len(prefix) : -len(suffix)]
            if name:
                return name
    return None


def suffix_rank(path: Path) -> int:
    """Lower rank is preferred: toml, then yaml, then yml."""
    try:
        return CONFIG_SUFFIXES.index(path.suffix.lower())
    except ValueError:
        return len(CONFIG_SUFFIXES)


def choose_preferred(
    paths: list[Path],
    *,
    subject: str | None,
    logger: logging.Logger,
) -> Path | None:
    """Keep the preferred format and warn about the rest."""
    if not paths:
        return None
    ordered = sorted(paths, key=suffix_rank)
    chosen = ordered[0]
    for ignored in ordered[1:]:
        if subject is None:
            logger.warning("%s will be ignored; %s is preferred", ignored, chosen)
        else:
            logger.warning(
                "%s will be ignored; %s is preferred for %s",
                ignored,
                chosen,
                subject,
            )
    return chosen


def config_file_type(path: Path) -> str:
    """Return `toml` or `yaml`. `.yml` is yaml."""
    file_type = SUFFIX_TYPES.get(path.suffix.lower())
    if file_type is None:
        supported = ", ".join(CONFIG_SUFFIXES)
        raise SupershelfError(
            f"Unsupported config format {path.suffix!r} for {path}",
            advice=f"Use one of: {supported}.",
        )
    return file_type


def load_toml(path: Path) -> Any:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise SupershelfError(f"Invalid TOML in {path}: {exc}") from exc


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SupershelfError(f"Invalid YAML in {path}: {exc}") from exc


def load_mapping_file(path: Path) -> tuple[Any, str]:
    """Load a toml or yaml file and return the raw value plus its type."""
    file_type = config_file_type(path)
    if file_type == FILE_TYPE_TOML:
        return load_toml(path), file_type
    return load_yaml(path), file_type
