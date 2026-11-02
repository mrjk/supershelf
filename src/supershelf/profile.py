"""Render the paths a command needs from one loaded profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from supershelf.common import config_section as read_config_section
from supershelf.common import render_user_path
from supershelf.configs import ShelfConfig
from supershelf.constants import (
    FIELD_DATE_FORMAT,
    FIELD_DIR,
    FIELD_DOCUMENT,
    FIELD_FILE,
    FIELD_NAME,
    FIELD_PATH,
    FIELD_TYPE,
    KEY_CACHE_FILE,
    KEY_DATABASE_FILE,
    KEY_DEFAULT_DATE_FORMAT,
    KEY_ROOT_DIR,
    VAR_CONFIG,
    VAR_PROFILE,
)
from supershelf.defaults import PACKAGED
from supershelf.errors import SupershelfError
from supershelf.scan.walk import InputScanResult, InputScanner
from supershelf.template.render import ScopeObject

_PATH_STEPS = (
    KEY_ROOT_DIR,
    KEY_DATABASE_FILE,
    KEY_CACHE_FILE,
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
        section = read_config_section(document)
        directory = shelf_config.path.parent
        date_format = cls._date_format(section)
        config_scope = ScopeObject({FIELD_DATE_FORMAT: date_format}, KEY_ROOT_DIR)
        scope: dict[str, Any] = {
            VAR_PROFILE: ScopeObject(
                {
                    FIELD_NAME: shelf_config.profile,
                    FIELD_TYPE: shelf_config.type,
                    FIELD_PATH: str(shelf_config.path),
                    FIELD_DIR: str(directory),
                    FIELD_FILE: shelf_config.path.name,
                    FIELD_DOCUMENT: document,
                },
                FIELD_NAME,
            ),
            VAR_CONFIG: config_scope,
        }
        rendered: dict[str, Path] = {}
        for config_key in _PATH_STEPS:
            path = cls._render_path(
                cls._path_template(section, config_key),
                scope,
                directory,
                label=f"config.{config_key}",
            )
            config_scope[config_key] = str(path)
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
        return render_user_path(
            template,
            scope,
            base,
            empty_message=f"{label} is empty",
            resolve=True,
        )

    @staticmethod
    def config_section(document: Mapping[str, Any]) -> dict[str, Any]:
        """The `config` mapping. A missing key is an empty mapping."""
        return read_config_section(document)

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
