"""Turn tool stdout into a flat string map."""

from __future__ import annotations

import configparser
import re
import tomllib
from collections.abc import Mapping

import yaml

from supershelf.errors import VarCandidateError

_SHELL_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\Z")


class OutputParser:
    """yaml, toml, ini, and shell. A bad document fails the candidate."""

    def parse(self, output_format: str, text: str) -> dict[str, str]:
        """Parse stdout. Nested mappings flatten with a dot."""
        if output_format == "yaml":
            return self._mapping(self._yaml(text))
        if output_format == "toml":
            return self._mapping(self._toml(text))
        if output_format == "ini":
            return self._ini(text)
        if output_format == "shell":
            return self._shell(text)
        raise VarCandidateError(f"Unknown output format {output_format!r}")

    def _yaml(self, text: str) -> object:
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise VarCandidateError(f"YAML metadata is invalid: {exc}") from exc

    def _toml(self, text: str) -> object:
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise VarCandidateError(f"TOML metadata is invalid: {exc}") from exc

    def _mapping(self, document: object) -> dict[str, str]:
        if not isinstance(document, Mapping):
            raise VarCandidateError("metadata output must be a mapping")
        found: dict[str, str] = {}
        self._flatten(document, "", found)
        return found

    def _flatten(self, node: Mapping[object, object], prefix: str, found: dict[str, str]) -> None:
        for key, value in node.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, Mapping):
                self._flatten(value, name, found)
                continue
            if value is None or isinstance(value, list):
                continue
            found[name] = value if isinstance(value, str) else str(value)

    def _ini(self, text: str) -> dict[str, str]:
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(text)
        except configparser.Error as exc:
            raise VarCandidateError(f"INI metadata is invalid: {exc}") from exc
        found: dict[str, str] = {}
        for key, value in parser.defaults().items():
            found[key] = value
        sections = getattr(parser, "_sections", {})
        for section, pairs in sections.items():
            for key, value in pairs.items():
                found[f"{section}.{key}"] = value
        return found

    def _shell(self, text: str) -> dict[str, str]:
        found: dict[str, str] = {}
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export ") :].strip()
            if "=" not in stripped:
                raise VarCandidateError("shell metadata has no key")
            key, value = stripped.split("=", 1)
            key = key.strip()
            if _SHELL_KEY.fullmatch(key) is None:
                raise VarCandidateError(f"shell metadata key {key!r} is invalid")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            found[key] = value
        return found
