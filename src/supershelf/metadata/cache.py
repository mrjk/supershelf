"""Metadata payloads in config.cache_file. The in-memory bag is checked first."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from supershelf.errors import CacheError

_VERSION = 1


class ContentMetaCache:
    """Read and write one driver's payload. A dry run does not create or replace."""

    def __init__(self, path: Path | None, *, dry_run: bool) -> None:
        self._path = path
        self._dry_run = dry_run

    def read(
        self,
        digest: str,
        driver: str,
        options_key: str,
    ) -> tuple[str | None, str | None] | None:
        """None when the file is absent or the entry is missing."""
        document = self._load()
        if document is None:
            return None
        return _entry(document, digest, driver, options_key)

    def store(
        self,
        digest: str,
        driver: str,
        options_key: str,
        *,
        payload: str | None,
        error: str | None,
    ) -> None:
        """Insert one entry. An existing entry is left as it is. Dry-run writes nothing."""
        if self._dry_run or self._path is None:
            return
        document = self._load()
        if document is None:
            document = {"version": _VERSION, "entries": {}}
        if _entry(document, digest, driver, options_key) is not None:
            return
        extracted_at = datetime.now(timezone.utc).isoformat()
        entries = document["entries"]
        assert isinstance(entries, dict)
        drivers = entries.setdefault(digest, {})
        assert isinstance(drivers, dict)
        options = drivers.setdefault(driver, {})
        assert isinstance(options, dict)
        options[options_key] = {
            "error": error,
            "extracted_at": extracted_at,
            "payload": payload,
        }
        self._replace(document)

    def _load(self) -> dict[str, Any] | None:
        """The cache object, or None when the file is absent."""
        path = self._path
        if path is None or not path.exists():
            return None
        if not path.is_file():
            raise CacheError(
                f"Cache path is not a file: {path}",
                advice="Point config.cache_file at a file path.",
            )
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise _bad_cache(path) from exc
        if not isinstance(parsed, dict) or parsed.get("version") != _VERSION:
            raise _bad_cache(path)
        entries = parsed.get("entries")
        if not isinstance(entries, dict):
            raise _bad_cache(path)
        return parsed

    def _replace(self, document: dict[str, Any]) -> None:
        """Write the object by replacing a temp file in the same directory."""
        path = self._path
        assert path is not None
        parent = path.parent
        if parent.exists() and not parent.is_dir():
            raise CacheError(
                f"Cache parent is not a directory: {parent}",
                advice="Point config.cache_file at a path whose parent is a directory.",
            )
        if path.exists() and not path.is_file():
            raise CacheError(
                f"Cache path is not a file: {path}",
                advice="Point config.cache_file at a file path.",
            )
        parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)


def _entry(
    document: dict[str, Any],
    digest: str,
    driver: str,
    options_key: str,
) -> tuple[str | None, str | None] | None:
    """One entry, or None when that key is absent. A bad shape stops the command."""
    entries = document["entries"]
    assert isinstance(entries, dict)
    if digest not in entries:
        return None
    drivers = entries[digest]
    if not isinstance(drivers, dict):
        raise _bad_cache_shape()
    if driver not in drivers:
        return None
    options = drivers[driver]
    if not isinstance(options, dict):
        raise _bad_cache_shape()
    if options_key not in options:
        return None
    row = options[options_key]
    if not isinstance(row, dict) or "payload" not in row or "error" not in row:
        raise _bad_cache_shape()
    payload = row.get("payload")
    error = row.get("error")
    if payload is not None and not isinstance(payload, str):
        raise _bad_cache_shape()
    if error is not None and not isinstance(error, str):
        raise _bad_cache_shape()
    return payload, error


def _bad_cache(path: Path) -> CacheError:
    return CacheError(
        f"{path} is not a metadata cache",
        advice="Delete config.cache_file to refresh metadata.",
    )


def _bad_cache_shape() -> CacheError:
    return CacheError(
        "The metadata cache has a bad entry",
        advice="Delete config.cache_file to refresh metadata.",
    )
