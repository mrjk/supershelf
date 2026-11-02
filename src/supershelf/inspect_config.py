"""Print the parsed profile after profile init."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tomli_w
import yaml

from supershelf.configs import ShelfConfigs
from supershelf.constants import (
    CONFIG_SECTION,
    FILE_TYPE_TOML,
    FILE_TYPE_YAML,
    KEY_CACHE_FILE,
    KEY_DATABASE_FILE,
    KEY_DEFAULT_DATE_FORMAT,
    KEY_ROOT_DIR,
)
from supershelf.errors import SupershelfError
from supershelf.profile import ShelfProfile

FORMAT_JSON = "json"
OUTPUT_FORMATS = (FILE_TYPE_TOML, FILE_TYPE_YAML, FORMAT_JSON)
_FORMAT_LIST = ", ".join(OUTPUT_FORMATS)

_OVERLAY = (
    KEY_DEFAULT_DATE_FORMAT,
    KEY_ROOT_DIR,
    KEY_DATABASE_FILE,
    KEY_CACHE_FILE,
)


class InspectedConfig:
    """Parsed documents with the values profile init already resolved."""

    def __init__(self, shelves: list[ShelfProfile]) -> None:
        self._shelves = shelves

    @classmethod
    def load(
        cls,
        config_option: str | None = None,
        profile_option: str | None = None,
    ) -> InspectedConfig:
        """Load the selected profiles and build one ShelfProfile each."""
        loaded = ShelfConfigs.load(
            config_option=config_option,
            profile_option=profile_option,
        )
        return cls([ShelfProfile.from_config(item) for item in loaded.config_list])

    def document(self) -> dict[str, Any]:
        """One rendered document, or a mapping keyed by profile name."""
        rendered = [self._one(shelf) for shelf in self._shelves]
        if len(rendered) == 1:
            return rendered[0]
        return {
            shelf.name: body
            for shelf, body in zip(self._shelves, rendered, strict=True)
        }

    def file_type(self) -> str:
        """The shared profile type. Mixed toml and yaml stops the command."""
        types = {shelf.type for shelf in self._shelves}
        if len(types) == 1:
            return types.pop()
        raise SupershelfError(
            "Selected profiles use more than one config type",
            advice=f"Pass --format {_FORMAT_LIST}.",
        )

    def text(self, fmt: str | None = None) -> str:
        """Dump the document. An omitted format uses the profile type."""
        chosen = self.file_type() if fmt is None else fmt
        if chosen not in OUTPUT_FORMATS:
            raise SupershelfError(
                f"Unknown inspect format {chosen!r}",
                advice=f"Use {_FORMAT_LIST}.",
            )
        return self._dump(self.document(), chosen)

    @staticmethod
    def _one(shelf: ShelfProfile) -> dict[str, Any]:
        document = copy.deepcopy(shelf.document)
        section = document.get(CONFIG_SECTION)
        if not isinstance(section, dict):
            section = {}
            document[CONFIG_SECTION] = section
        for key in _OVERLAY:
            value = getattr(shelf, key)
            section[key] = str(value) if isinstance(value, Path) else value
        return document

    @staticmethod
    def _dump(document: Mapping[str, Any], fmt: str) -> str:
        if fmt == FORMAT_JSON:
            rendered = json.dumps(document, indent=2, ensure_ascii=False)
        elif fmt == FILE_TYPE_YAML:
            rendered = yaml.safe_dump(
                document,
                sort_keys=False,
                allow_unicode=True,
            )
        else:
            rendered = tomli_w.dumps(document)
        if rendered.endswith("\n"):
            return rendered
        return rendered + "\n"
