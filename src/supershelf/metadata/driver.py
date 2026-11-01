"""Driver base, the file a driver sees, and the options for one profile entry."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol

from supershelf.errors import VarCandidateError, VarConfigError
from supershelf.scan import InputFile

_ENABLE_WORDS = ("auto", "true", "false")


@dataclass(frozen=True)
class MetadataFile:
    """Walk facts a driver may read. Paths use `/`."""

    absolute: Path
    relative: str
    name: str
    stem: str
    extension: str
    directory: str
    sha256: str
    ctime: str
    mtime: str

    @classmethod
    def from_input(cls, file: InputFile) -> MetadataFile:
        """Copy the strings the walk already stored."""
        suffix = file.suffix
        extension = suffix[1:] if suffix.startswith(".") else suffix
        return cls(
            absolute=file.absolute,
            relative=file.path,
            name=file.name,
            stem=file.stem,
            extension=extension,
            directory=file.directory,
            sha256=file.sha256 or "",
            ctime=file.ctime or "",
            mtime=file.mtime or "",
        )


class CommandRunner(Protocol):
    """which and run. ProcessRunner is the real one. Tests pass a fake."""

    def which(self, name: str) -> str | None:
        """The program on PATH, or None."""

    def run(self, argv: list[str], timeout: float) -> str:
        """Stdout as text."""


@dataclass(frozen=True)
class DriverOptions:
    """Settings for one metadata_driver entry. Reserved keys are already applied."""

    name: str
    enable: str
    timeout: float | None
    ext: tuple[str, ...] | None
    mime: tuple[str, ...] | None
    values: Mapping[str, Any]
    profile_dir: Path
    options_key: str
    runner: CommandRunner


class CachedMeta:
    """One in-memory bag entry. payload and error are not both set."""

    def __init__(
        self,
        payload: str | None,
        error: str | None,
        fields: dict[str, str],
    ) -> None:
        self.payload = payload
        self.error = error
        self.fields = fields


class FieldCache:
    """The session bag extract reads. sqlite is checked after this bag misses."""

    def cached(self, digest: str, driver_name: str, options_key: str) -> CachedMeta | None:
        """The bag entry, or None when this process has not stored it."""
        del digest, driver_name, options_key
        return None

    def load_stored(
        self,
        digest: str,
        driver_name: str,
        options_key: str,
    ) -> tuple[str | None, str | None] | None:
        """A sqlite row as payload and error, or None when the cache misses."""
        del digest, driver_name, options_key
        return None

    def remember_loaded(
        self,
        digest: str,
        driver_name: str,
        options_key: str,
        found: CachedMeta,
    ) -> None:
        """Keep a row that was already stored. This does not write sqlite."""
        del digest, driver_name, options_key, found

    def remember_success(
        self,
        digest: str,
        driver_name: str,
        options_key: str,
        payload: str,
        fields: dict[str, str],
    ) -> None:
        """Store a parsed map. A missing field does not replace this."""
        del digest, driver_name, options_key, payload, fields

    def remember_error(self, digest: str, driver_name: str, options_key: str, error: str) -> None:
        """Store a tool or parse failure so the program is not run again."""
        del digest, driver_name, options_key, error


class Extraction:
    """The bag bound while meta() runs."""

    _current: ClassVar[ContextVar[FieldCache | None]] = ContextVar(
        "supershelf_metadata_bag",
        default=None,
    )

    @classmethod
    def bind(cls, cache: FieldCache) -> Token[FieldCache | None]:
        """Install the bag for this resolve."""
        return cls._current.set(cache)

    @classmethod
    def reset(cls, token: Token[FieldCache | None]) -> None:
        """Restore the previous bag."""
        cls._current.reset(token)

    @classmethod
    def current(cls) -> FieldCache:
        """The bag for the file currently resolving."""
        found = cls._current.get()
        if found is None:
            raise VarCandidateError("No metadata session is bound")
        return found


class MimeProbe:
    """Mime lookup bound for the file currently resolving."""

    _current: ClassVar[ContextVar[Callable[[MetadataFile], str | None] | None]] = ContextVar(
        "supershelf_mime_probe",
        default=None,
    )

    @classmethod
    def bind(
        cls,
        probe: Callable[[MetadataFile], str | None],
    ) -> Token[Callable[[MetadataFile], str | None] | None]:
        """Install the probe for this resolve."""
        return cls._current.set(probe)

    @classmethod
    def reset(cls, token: Token[Callable[[MetadataFile], str | None] | None]) -> None:
        """Restore the previous probe."""
        cls._current.reset(token)

    @classmethod
    def lookup(cls, file: MetadataFile) -> str | None:
        """Return the probed mime type, or None when no probe is bound."""
        probe = cls._current.get()
        if probe is None:
            return None
        return probe(file)


class MetadataDriver:
    """Extension and mime gate, plus the enable and timeout rules."""

    extensions: tuple[str, ...] = ()
    mime_types: tuple[str, ...] = ()
    single_field: str | None = None
    cache_epoch: str = "1"
    default_enable: str = "auto"
    ignores_enable: bool = False
    accepts_timeout: bool = True
    declared_options: frozenset[str] | None = frozenset()
    identity: str = ""
    binary: str | None = None
    writes_cache: bool = True

    def available(self, options: DriverOptions) -> bool:
        """True when this driver can run. A named binary must be on PATH."""
        if not self.binary:
            return True
        return options.runner.which(self.binary) is not None

    def accepts(self, file: MetadataFile, options: DriverOptions) -> bool:
        """Extension, then mime. A hit on the extension does not probe."""
        ext_list = self.extensions if options.ext is None else options.ext
        mime_list = self.mime_types if options.mime is None else options.mime
        if not ext_list and not mime_list:
            return True
        suffix = file.extension.lower()
        if ext_list and suffix and suffix in {item.lower() for item in ext_list}:
            return True
        if not mime_list:
            return False
        found = MimeProbe.lookup(file)
        if found is None:
            return False
        return found.strip().lower() in {item.lower() for item in mime_list}

    def extract(self, file: MetadataFile, field: str, options: DriverOptions) -> str:
        """Return one field. Subclasses replace this."""
        del file, field, options
        raise VarCandidateError("This metadata driver has no extractor")

    def fields_from_payload(self, payload: str, options: DriverOptions) -> dict[str, str]:
        """Turn a stored payload back into fields. Subclasses replace this."""
        del payload, options
        raise VarCandidateError("This metadata driver has no cache parser")

    def one_field(
        self,
        file: MetadataFile,
        field: str,
        options: DriverOptions,
        read: Callable[[], tuple[str, dict[str, str]]],
    ) -> str:
        """Parse once per hash and driver name. A missing field does not store an error."""
        cache = Extraction.current()
        key = (file.sha256, options.name, options.options_key)
        found = cache.cached(*key)
        if found is None:
            found = self._from_store(cache, key, options)
        if found is None:
            try:
                payload, fields = read()
            except VarCandidateError as exc:
                self._keep_failure(cache, key, str(exc))
                raise
            self._keep_parse(cache, key, payload, fields)
            found = CachedMeta(payload, None, fields)
        if found.error:
            raise VarCandidateError(found.error)
        value = found.fields.get(field)
        if value is None or not value.strip():
            raise VarCandidateError(f"{options.name} has no {field}")
        return value.strip()

    def _from_store(
        self,
        cache: FieldCache,
        key: tuple[str, str, str],
        options: DriverOptions,
    ) -> CachedMeta | None:
        stored = cache.load_stored(*key)
        if stored is None:
            return None
        payload, error = stored
        if error:
            found = CachedMeta(None, error, {})
        else:
            fields = self.fields_from_payload(payload or "", options)
            found = CachedMeta(payload, None, fields)
        cache.remember_loaded(*key, found)
        return found

    def _keep_failure(self, cache: FieldCache, key: tuple[str, str, str], error: str) -> None:
        if self.writes_cache:
            cache.remember_error(*key, error)
            return
        cache.remember_loaded(*key, CachedMeta(None, error, {}))

    def _keep_parse(
        self,
        cache: FieldCache,
        key: tuple[str, str, str],
        payload: str,
        fields: dict[str, str],
    ) -> None:
        if self.writes_cache:
            cache.remember_success(*key, payload, fields)
            return
        cache.remember_loaded(*key, CachedMeta(payload, None, dict(fields)))

    def program_name(self, options: DriverOptions) -> str:
        """The binary or command a missing-tool log line should name."""
        if self.binary:
            return self.binary
        command = options.values.get("command")
        if isinstance(command, str) and command:
            return command
        return self.identity or options.name

    def prepare(
        self,
        name: str,
        values: Mapping[str, Any],
        profile_dir: Path,
    ) -> dict[str, Any]:
        """Check driver-specific keys at load. The default keeps the mapping."""
        del name, profile_dir
        return dict(values)

    def options_key(self, values: Mapping[str, Any]) -> str:
        """Stable cache identity. ext, mime, enable, and timeout are not included."""
        payload = {
            "cache_epoch": self.cache_epoch,
            "driver": self.identity,
            "values": values,
        }
        try:
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        except TypeError as exc:
            raise VarConfigError(
                f"metadata driver {self.identity or 'entry'!r} options are not JSON values",
                advice="Use strings, numbers, booleans, and lists in driver options.",
            ) from exc
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def enable_word(name: str, value: object, default: str) -> str:
        """auto, true, or false. Booleans true and false are those words."""
        if value is None:
            return default
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, str) and value in _ENABLE_WORDS:
            return value
        raise VarConfigError(
            f"metadata_driver.{name} enable must be auto, true, or false",
            advice="Use auto, true, or false.",
        )

    @staticmethod
    def timeout_seconds(name: str, value: object) -> float:
        """A number of seconds, greater than 0."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VarConfigError(
                f"metadata_driver.{name} timeout must be a number of seconds",
                advice="Use a number greater than 0, or omit timeout.",
            )
        if value <= 0:
            raise VarConfigError(
                f"metadata_driver.{name} timeout must be greater than 0",
                advice="Use a number greater than 0, or omit timeout.",
            )
        return float(value)
