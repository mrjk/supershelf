"""Packaged defaults loaded once from default.toml."""

from __future__ import annotations

import tomllib
from importlib.resources import as_file, files
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from supershelf.constants import KIND_OVERRIDE_MODES
from supershelf.errors import SupershelfError

_PACKAGE_FILE = "default.toml"


class PackagedConfig(BaseModel):
    """The `[config]` table in `default.toml`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: str
    default_date_format: str
    root_dir: str
    database_file: str
    cache_file: str
    kind_overrides_mode: str
    kind_overrides_date_format: str | None = None
    var_modules: list[str] | None = None
    kind_overrides_sep: str
    kind_overrides_config: list[str]
    input_depth: int = Field(ge=0)
    input_follow_symlinks: bool

    @field_validator("kind_overrides_mode")
    @classmethod
    def mode_is_known(cls, value: str) -> str:
        if value not in KIND_OVERRIDE_MODES:
            raise ValueError(
                "kind_overrides_mode must be auto, manual, always, or disabled"
            )
        return value


class PackagedFile(BaseModel):
    """`default.toml` is one config table."""

    model_config = ConfigDict(extra="forbid")

    config: PackagedConfig


def load_packaged(path: Path) -> PackagedConfig:
    """Read and validate one packaged defaults file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SupershelfError(f"Packaged defaults are missing: {path}") from exc
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SupershelfError(f"Invalid packaged defaults {path}: {exc}") from exc
    try:
        loaded = PackagedFile.model_validate(raw)
    except ValidationError as exc:
        raise SupershelfError(f"Invalid packaged defaults {path}: {exc}") from exc
    return loaded.config


def _load_shipped() -> PackagedConfig:
    resource = files("supershelf").joinpath(_PACKAGE_FILE)
    try:
        with as_file(resource) as path:
            return load_packaged(Path(path))
    except SupershelfError:
        raise
    except Exception as exc:
        raise SupershelfError(f"Packaged defaults are missing: {resource}") from exc


PACKAGED = _load_shipped()
