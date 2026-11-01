"""Render the paths a command needs from one loaded profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from supershelf.common import resolve_user_path
from supershelf.configs import ShelfConfig
from supershelf.constants import (
    CONFIG_SECTION,
    KEY_CACHE_FILE,
    KEY_DATABASE_FILE,
    KEY_DEFAULT_DATE_FORMAT,
    KEY_ROOT_DIR,
    VAR_CACHE_FILE,
    VAR_CONFIG_DATA,
    VAR_DATABASE_FILE,
    VAR_DEFAULT_DATE_FORMAT,
    VAR_PROFILE,
    VAR_PROFILE_DIR,
    VAR_PROFILE_FILE,
    VAR_PROFILE_NAME,
    VAR_PROFILE_PATH,
    VAR_PROFILE_TYPE,
    VAR_ROOT_DIR,
)
from supershelf.defaults import PACKAGED
from supershelf.errors import SupershelfError
from supershelf.template import Template

if TYPE_CHECKING:
    from supershelf.scan import InputScanResult

_PATH_STEPS = (
    (KEY_ROOT_DIR, VAR_ROOT_DIR),
    (KEY_DATABASE_FILE, VAR_DATABASE_FILE),
    (KEY_CACHE_FILE, VAR_CACHE_FILE),
)


@dataclass(frozen=True)
class ShelfProfile:
    """Rendered paths and the template scope for one profile."""

    name: str
    type: str
    path: Path
    directory: Path
    filename: str
    default_date_format: str
    root_dir: Path
    database_file: Path
    cache_file: Path
    scope: dict[str, Any]
    document: dict[str, Any]

    @classmethod
    def from_config(cls, shelf_config: ShelfConfig) -> ShelfProfile:
        document = shelf_config.config
        section = cls._config_section(document)
        directory = shelf_config.path.parent
        date_format = cls._date_format(section)
        scope: dict[str, Any] = {
            VAR_PROFILE_NAME: shelf_config.profile,
            VAR_PROFILE: shelf_config.profile,
            VAR_PROFILE_TYPE: shelf_config.type,
            VAR_PROFILE_PATH: str(shelf_config.path),
            VAR_PROFILE_DIR: str(directory),
            VAR_PROFILE_FILE: shelf_config.path.name,
            VAR_DEFAULT_DATE_FORMAT: date_format,
            VAR_CONFIG_DATA: document,
        }
        rendered: dict[str, Path] = {}
        for config_key, scope_key in _PATH_STEPS:
            path = cls._render_path(
                cls._path_template(section, config_key),
                scope,
                directory,
                label=f"config.{config_key}",
            )
            scope[scope_key] = str(path)
            rendered[config_key] = path
        return cls(
            name=shelf_config.profile,
            type=shelf_config.type,
            path=shelf_config.path,
            directory=directory,
            filename=shelf_config.path.name,
            default_date_format=date_format,
            root_dir=rendered[KEY_ROOT_DIR],
            database_file=rendered[KEY_DATABASE_FILE],
            cache_file=rendered[KEY_CACHE_FILE],
            scope=scope,
            document=document,
        )

    def scan(self, *, quick: bool = False) -> list[InputScanResult]:
        """Scan this profile's inputs. Does not create the database or cache."""
        from supershelf.scan import InputScanner

        return InputScanner(self, quick=quick).run()

    def show_time(self, stored: str) -> str:
        """Show a stored UTC timestamp with this profile's date format."""
        try:
            return datetime.fromisoformat(stored).strftime(self.default_date_format)
        except ValueError as exc:
            raise SupershelfError(
                "config.default_date_format cannot format a time: "
                f"{self.default_date_format}"
            ) from exc

    @classmethod
    def _render_path(
        cls,
        template: str,
        scope: Mapping[str, Any],
        base: Path,
        *,
        label: str,
    ) -> Path:
        rendered = Template(scope).render(template).strip()
        if not rendered:
            raise SupershelfError(f"{label} is empty")
        return resolve_user_path(rendered, base).resolve()

    @staticmethod
    def _config_section(document: Mapping[str, Any]) -> dict[str, Any]:
        section = document.get(CONFIG_SECTION)
        if section is None:
            return {}
        if not isinstance(section, dict):
            raise SupershelfError("config must be a mapping")
        return section

    @staticmethod
    def _date_format(section: Mapping[str, Any]) -> str:
        value = section.get(KEY_DEFAULT_DATE_FORMAT)
        if value is None:
            return PACKAGED.default_date_format
        if not isinstance(value, str) or not value.strip():
            raise SupershelfError(
                "config.default_date_format must be a non-empty string"
            )
        return value

    @staticmethod
    def _path_template(section: Mapping[str, Any], key: str) -> str:
        value = section.get(key)
        if value is None:
            return getattr(PACKAGED, key)
        if not isinstance(value, str):
            raise SupershelfError(f"config.{key} must be a string")
        return value
