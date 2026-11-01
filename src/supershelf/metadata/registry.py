"""Load metadata_driver entries onto the builtin drivers."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from supershelf.errors import VarCandidateError, VarConfigError
from supershelf.metadata.driver import CommandRunner, DriverOptions, MetadataDriver, MetadataFile
from supershelf.metadata.drivers import (
    CommandDriver,
    ExiftoolDriver,
    FsDriver,
    PdfDriver,
    PdftotextDriver,
)

_GENERIC = "supershelf.meta_driver"
_RESERVED = frozenset({"driver", "enable", "timeout", "ext", "mime"})
_API = ("available", "accepts", "extract")
_BUILTINS: dict[str, type[MetadataDriver]] = {
    "fs": FsDriver,
    "pdf": PdfDriver,
    "exiftool": ExiftoolDriver,
    "pdftotext": PdftotextDriver,
}


class DriverEntry:
    """One profile name, its driver object, and the entry options."""

    def __init__(self, driver: MetadataDriver, options: DriverOptions) -> None:
        self.driver = driver
        self.options = options


class LoadedDriver(MetadataDriver):
    """A custom module. Config ext and mime still use the builtin gate."""

    def __init__(self, inner: object, identity: str) -> None:
        self._inner = inner
        self.identity = identity
        self.extensions = self.strings(getattr(inner, "extensions", ()))
        self.mime_types = self.strings(getattr(inner, "mime_types", ()))
        self.single_field = getattr(inner, "single_field", None)
        self.cache_epoch = str(getattr(inner, "cache_epoch", "1"))
        self.default_enable = str(getattr(inner, "default_enable", "auto"))
        self.ignores_enable = bool(getattr(inner, "ignores_enable", False))
        self.accepts_timeout = bool(getattr(inner, "accepts_timeout", True))
        self.declared_options = None
        self.writes_cache = bool(getattr(inner, "writes_cache", True))
        binary = getattr(inner, "binary", None)
        self.binary = binary if isinstance(binary, str) else None

    def available(self, options: DriverOptions) -> bool:
        """Call the module's available() with the extra keys only."""
        method = getattr(self._inner, "available")
        return bool(method(dict(options.values)))

    def accepts(self, file: MetadataFile, options: DriverOptions) -> bool:
        """Config lists first, then the module."""
        if not super().accepts(file, options):
            return False
        method = getattr(self._inner, "accepts")
        return bool(method(file, dict(options.values)))

    def extract(self, file: MetadataFile, field: str, options: DriverOptions) -> str:
        """Call the module. A non-string fails this candidate."""
        method = getattr(self._inner, "extract")
        result = method(file, field, dict(options.values))
        if not isinstance(result, str):
            raise VarCandidateError(f"{self.identity} must return a string")
        return result

    @staticmethod
    def strings(value: object) -> tuple[str, ...]:
        """Class ext or mime lists copied off a custom driver."""
        if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
            return tuple(value)
        return ()


class MetadataRegistry:
    """Builtin drivers overlaid by one profile's metadata_driver table."""

    def __init__(self, entries: dict[str, DriverEntry]) -> None:
        self._entries = entries
        self._known: dict[str, bool] = {}

    @classmethod
    def from_document(
        cls,
        raw: object,
        profile_dir: Path,
        runner: CommandRunner,
    ) -> MetadataRegistry:
        """Omitted, null, and {} keep every builtin at its class default."""
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise VarConfigError(
                "metadata_driver must be a mapping",
                advice="Map a driver name to its settings. Omit the key to keep the builtins.",
            )
        entries: dict[str, DriverEntry] = {}
        instances = {name: kind() for name, kind in _BUILTINS.items()}
        for name, driver in instances.items():
            overlay = raw.get(name)
            if name not in raw or overlay is None:
                entries[name] = cls._entry(name, driver, {}, profile_dir, runner)
                continue
            entries[name] = cls._overlay(name, driver, overlay, profile_dir, runner)
        for name, overlay in raw.items():
            if name in _BUILTINS:
                continue
            entries[name] = cls._custom(name, overlay, profile_dir, runner)
        return cls(entries)

    def require_available(self) -> None:
        """enable = true is checked now. auto waits until the first extract."""
        for name, entry in self._entries.items():
            if entry.driver.ignores_enable or entry.options.enable != "true":
                continue
            if entry.driver.available(entry.options):
                self._known[name] = True
                continue
            raise VarConfigError(
                f"metadata driver {name!r} is not available",
                advice=(
                    f"Install {entry.driver.program_name(entry.options)}, "
                    "or set enable to auto or false."
                ),
            )

    def entry(self, name: str) -> DriverEntry | None:
        """The entry for this profile key, or None."""
        return self._entries.get(name)

    def known_available(self, name: str) -> bool | None:
        """True or False after a check. None means auto has not run yet."""
        return self._known.get(name)

    def remember_available(self, name: str, ok: bool) -> None:
        """Remember one auto check for the rest of the process."""
        self._known[name] = ok

    @classmethod
    def _overlay(
        cls,
        name: str,
        builtin: MetadataDriver,
        overlay: object,
        profile_dir: Path,
        runner: CommandRunner,
    ) -> DriverEntry:
        if not isinstance(overlay, dict):
            raise VarConfigError(
                f"metadata_driver.{name} must be a mapping",
                advice="Set enable, timeout, ext, mime, or driver.",
            )
        driver = builtin
        if "driver" in overlay and overlay.get("driver") is not None:
            driver = cls._load(cls._spec(name, overlay.get("driver")))
        return cls._entry(name, driver, overlay, profile_dir, runner)

    @classmethod
    def _custom(
        cls,
        name: object,
        overlay: object,
        profile_dir: Path,
        runner: CommandRunner,
    ) -> DriverEntry:
        if not isinstance(name, str) or not name.strip():
            raise VarConfigError(
                "metadata_driver names must be strings",
                advice="Use the name meta() will call.",
            )
        if not isinstance(overlay, dict):
            raise VarConfigError(
                f"metadata_driver.{name} must be a mapping",
                advice="Set driver to a module path.",
            )
        if "driver" not in overlay or overlay.get("driver") is None:
            raise VarConfigError(
                f"metadata_driver.{name} is not a builtin and has no driver",
                advice="Set driver to a module path, or use a builtin name.",
            )
        driver = cls._load(cls._spec(name, overlay.get("driver")))
        return cls._entry(name, driver, overlay, profile_dir, runner)

    @classmethod
    def _entry(
        cls,
        name: str,
        driver: MetadataDriver,
        raw: Mapping[str, Any],
        profile_dir: Path,
        runner: CommandRunner,
    ) -> DriverEntry:
        enable = MetadataDriver.enable_word(
            name,
            raw.get("enable") if "enable" in raw else None,
            driver.default_enable,
        )
        timeout = cls._timeout(name, driver, raw)
        ext = cls._choice_list(name, raw, "ext")
        mime = cls._choice_list(name, raw, "mime")
        values: dict[str, Any] = {}
        declared = driver.declared_options
        for key, value in raw.items():
            if key in _RESERVED:
                continue
            if declared is not None and key not in declared:
                raise VarConfigError(
                    f"metadata_driver.{name} has unknown option {key!r}",
                    advice="Remove it, or use a driver that declares that option.",
                )
            values[key] = value
        prepared = driver.prepare(name, values, profile_dir)
        options = DriverOptions(
            name=name,
            enable=enable,
            timeout=timeout,
            ext=ext,
            mime=mime,
            values=prepared,
            profile_dir=profile_dir,
            options_key=driver.options_key(prepared),
            runner=runner,
        )
        return DriverEntry(driver, options)

    @classmethod
    def _timeout(cls, name: str, driver: MetadataDriver, raw: Mapping[str, Any]) -> float | None:
        present = "timeout" in raw and raw.get("timeout") is not None
        if not driver.accepts_timeout:
            if present:
                raise VarConfigError(
                    f"metadata_driver.{name} does not accept timeout",
                    advice="Remove timeout. fs and pdf do not take a timeout.",
                )
            return None
        if not present:
            return 30.0
        return MetadataDriver.timeout_seconds(name, raw.get("timeout"))

    @classmethod
    def _choice_list(
        cls,
        name: str,
        raw: Mapping[str, Any],
        key: str,
    ) -> tuple[str, ...] | None:
        if key not in raw or raw.get(key) is None:
            return None
        value = raw.get(key)
        label = f"metadata_driver.{name}.{key}"
        if isinstance(value, str):
            items: list[object] = [value]
        elif isinstance(value, list):
            items = list(value)
        else:
            raise VarConfigError(
                f"{label} must be a string or a list of strings",
                advice="Use one name, or a list. An empty list matches nothing.",
            )
        cleaned: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise VarConfigError(
                    f"{label} items must be strings",
                    advice="Each entry is a suffix or a mime type.",
                )
            text = item[1:] if item.startswith(".") else item
            if not text:
                raise VarConfigError(
                    f"{label} has an empty item",
                    advice="Use a suffix or a mime type, not an empty string.",
                )
            cleaned.append(text)
        return tuple(cleaned)

    @classmethod
    def _spec(cls, name: str, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise VarConfigError(
                f"metadata_driver.{name} driver must be a module path",
                advice="Use a module path, or module.path:ClassName.",
            )
        return value.strip()

    @classmethod
    def _load(cls, spec: str) -> MetadataDriver:
        if spec == _GENERIC:
            return cls._generic()
        try:
            if ":" in spec:
                module_name, class_name = spec.rsplit(":", 1)
                module = importlib.import_module(module_name)
                class_obj = getattr(module, class_name, None)
                if class_obj is None:
                    raise VarConfigError(
                        f"Metadata driver {spec!r} has no class {class_name}",
                        advice="Export that class, or use the module's DRIVER.",
                    )
                try:
                    instance = class_obj()
                except Exception as exc:
                    raise VarConfigError(
                        f"Cannot construct metadata driver {spec!r}: {exc}",
                        advice="The class must construct with no arguments.",
                    ) from exc
            else:
                module = importlib.import_module(spec)
                instance = getattr(module, "DRIVER", None)
                if instance is None:
                    raise VarConfigError(
                        f"Metadata driver {spec!r} does not export DRIVER",
                        advice="Export DRIVER, or use module.path:ClassName.",
                    )
        except VarConfigError:
            raise
        except Exception as exc:
            raise VarConfigError(
                f"Cannot import metadata driver {spec!r}: {exc}",
                advice="Install the package and check the module path.",
            ) from exc
        if isinstance(instance, MetadataDriver):
            return instance
        cls._require_api(spec, instance)
        return LoadedDriver(instance, spec)

    @classmethod
    def _generic(cls) -> MetadataDriver:
        import supershelf.meta_driver as meta_driver

        driver = getattr(meta_driver, "DRIVER", None)
        if not isinstance(driver, CommandDriver):
            raise VarConfigError(
                "supershelf.meta_driver must export DRIVER",
                advice="Use the packaged command driver.",
            )
        return driver

    @classmethod
    def _require_api(cls, spec: str, instance: object) -> None:
        for method in _API:
            if not callable(getattr(instance, method, None)):
                raise VarConfigError(
                    f"Metadata driver {spec!r} needs {method}()",
                    advice="Export DRIVER with available, accepts, and extract.",
                )
