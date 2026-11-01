"""Metadata for one profile. The bag is checked before sqlite."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextvars import ContextVar, Token
from pathlib import Path
from typing import ClassVar

from supershelf.constants import LOGGER_NAME
from supershelf.errors import VarCandidateError, VarResolveError
from supershelf.metadata.cache import ContentMetaCache
from supershelf.metadata.driver import (
    CachedMeta,
    CommandRunner,
    DriverOptions,
    Extraction,
    FieldCache,
    MetadataDriver,
    MetadataFile,
    MimeProbe,
)
from supershelf.metadata.registry import MetadataRegistry


class SessionBind:
    """Tokens that restore the previous file, probe, and bag."""

    def __init__(
        self,
        file_token: Token[MetadataFile | None],
        probe_token: Token[Callable[[MetadataFile], str | None] | None],
        cache_token: Token[FieldCache | None],
    ) -> None:
        self.file_token = file_token
        self.probe_token = probe_token
        self.cache_token = cache_token


class MetadataSession(FieldCache):
    """The file under resolve, and one bag of parsed fields for the process."""

    _current_file: ClassVar[ContextVar[MetadataFile | None]] = ContextVar(
        "supershelf_metadata_file",
        default=None,
    )

    def __init__(
        self,
        registry: MetadataRegistry,
        runner: CommandRunner,
        *,
        database: Path | None = None,
        dry_run: bool = False,
    ) -> None:
        self._registry = registry
        self._runner = runner
        self._logger = logging.getLogger(LOGGER_NAME)
        self._rows: dict[tuple[str, str, str], CachedMeta] = {}
        self._store = ContentMetaCache(database, dry_run=dry_run)
        self._mime: dict[str, str | None] = {}
        self._file_missing = False

    @property
    def registry(self) -> MetadataRegistry:
        """Drivers loaded for this profile."""
        return self._registry

    def bind(self, file: MetadataFile) -> SessionBind:
        """Make this file visible to meta() until unbind."""
        return SessionBind(
            self._current_file.set(file),
            MimeProbe.bind(self.mime_type),
            Extraction.bind(self),
        )

    def unbind(self, token: SessionBind) -> None:
        """Clear the file bound for this resolve."""
        Extraction.reset(token.cache_token)
        MimeProbe.reset(token.probe_token)
        self._current_file.reset(token.file_token)

    def mime_type(self, file: MetadataFile) -> str | None:
        """file --mime-type --brief, once per hash. A missing file command misses."""
        if file.sha256 in self._mime:
            return self._mime[file.sha256]
        if self._file_missing or self._runner.which("file") is None:
            if not self._file_missing:
                self._logger.warning("file is not on PATH; mime type was not read")
            self._file_missing = True
            self._mime[file.sha256] = None
            return None
        try:
            text = self._runner.run(
                ["file", "--mime-type", "--brief", str(file.absolute)],
                30,
            )
        except VarCandidateError:
            self._mime[file.sha256] = None
            return None
        mime = text.strip() or None
        self._mime[file.sha256] = mime
        return mime

    def cached(self, digest: str, driver_name: str, options_key: str) -> CachedMeta | None:
        """The bag entry, or None when this process has not stored it."""
        return self._rows.get((digest, driver_name, options_key))

    def load_stored(
        self,
        digest: str,
        driver_name: str,
        options_key: str,
    ) -> tuple[str | None, str | None] | None:
        """A sqlite row, after the in-memory bag misses."""
        return self._store.read(digest, driver_name, options_key)

    def remember_loaded(
        self,
        digest: str,
        driver_name: str,
        options_key: str,
        found: CachedMeta,
    ) -> None:
        """Keep a row that was already stored. This does not write sqlite."""
        self._rows[(digest, driver_name, options_key)] = found

    def remember_success(
        self,
        digest: str,
        driver_name: str,
        options_key: str,
        payload: str,
        fields: dict[str, str],
    ) -> None:
        """Store a parsed map. A missing field does not replace this."""
        self._rows[(digest, driver_name, options_key)] = CachedMeta(payload, None, dict(fields))
        self._store.store(digest, driver_name, options_key, payload=payload, error=None)

    def remember_error(self, digest: str, driver_name: str, options_key: str, error: str) -> None:
        """Store a tool or parse failure so the program is not run again."""
        self._rows[(digest, driver_name, options_key)] = CachedMeta(None, error, {})
        self._store.store(digest, driver_name, options_key, payload=None, error=error)

    def extract(self, name: object, field: object = None) -> str:
        """One field. A disabled driver, a rejected file, or a blank value misses."""
        if not isinstance(name, str) or not name.strip():
            raise VarResolveError(
                "meta() driver must be a string",
                advice="Pass the driver name as a string.",
            )
        entry = self._registry.entry(name)
        if entry is None:
            raise VarResolveError(
                f"Unknown metadata driver {name!r}",
                advice="Declare it under metadata_driver, or use a builtin name.",
            )
        current = self._current_file.get()
        if current is None:
            raise VarCandidateError("No file is bound for this command")
        driver = entry.driver
        options = entry.options
        self._check_enabled(name, driver, options)
        chosen = self._field_name(name, driver, field)
        if not driver.accepts(current, options):
            raise VarCandidateError(f"{name} does not accept this file")
        result = driver.extract(current, chosen, options)
        if not isinstance(result, str):
            raise VarCandidateError(f"{name} must return a string")
        text = result.strip()
        if not text:
            raise VarCandidateError(f"{name} {chosen} is blank")
        return text

    def _check_enabled(self, name: str, driver: MetadataDriver, options: DriverOptions) -> None:
        if driver.ignores_enable:
            return
        if options.enable == "false":
            raise VarCandidateError(f"{name} is disabled")
        if options.enable == "true":
            return
        known = self._registry.known_available(name)
        if known is True:
            return
        if known is False:
            raise VarCandidateError(f"{name} is not available")
        ok = bool(driver.available(options))
        self._registry.remember_available(name, ok)
        if ok:
            return
        self._logger.warning(
            "Metadata driver %s is not available: %s was not found",
            name,
            driver.program_name(options),
        )
        raise VarCandidateError(f"{name} is not available")

    def _field_name(self, name: str, driver: MetadataDriver, field: object) -> str:
        if field is None:
            if not driver.single_field:
                raise VarCandidateError(f"{name} needs a field")
            return driver.single_field
        if not isinstance(field, str) or not field.strip():
            raise VarCandidateError(f"{name} field must be a string")
        return field.strip()
