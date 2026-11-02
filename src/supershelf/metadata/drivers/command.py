"""One program, shared by every supershelf.meta_driver entry."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
from pathlib import Path

from supershelf.errors import VarCandidateError, VarConfigError
from supershelf.metadata.driver import DriverOptions, MetadataDriver, MetadataFile
from supershelf.metadata.parse import OutputParser

_TOKENS = {
    "p": "absolute",
    "r": "relative",
    "n": "name",
    "s": "stem",
    "e": "extension",
    "h": "sha256",
    "c": "ctime",
    "m": "mtime",
    "d": "directory",
}
_FORMATS = frozenset({"yaml", "toml", "ini", "shell"})


class CommandDriver(MetadataDriver):
    """One program, shared by every supershelf.meta_driver entry."""

    identity = "supershelf.meta_driver"
    declared_options = frozenset({"command", "arguments", "output_format"})

    def available(self, options: DriverOptions) -> bool:
        """A path must be a file. A bare name must be on PATH."""
        program = options.values.get("program")
        command = options.values.get("command")
        if not isinstance(program, str) or not program:
            return False
        if isinstance(command, str) and self._is_path(command):
            return Path(program).is_file()
        return options.runner.which(program) is not None

    def prepare(
        self,
        name: str,
        values: dict[str, object],
        profile_dir: Path,
    ) -> dict[str, object]:
        """Require command and output_format. Split arguments and check % tokens."""
        command = values.get("command")
        if not isinstance(command, str) or not command.strip():
            raise VarConfigError(
                f"metadata_driver.{name} needs command",
                advice="Set command to a program name or a path.",
            )
        command = command.strip()
        if self._is_path(command):
            path = Path(command)
            if not path.is_absolute():
                path = profile_dir / path
            path = path.resolve()
            if not path.is_file():
                raise VarConfigError(
                    f"metadata_driver.{name} command is not a file: {command}",
                    advice="A relative command is resolved from the profile directory.",
                )
            program = str(path)
        else:
            program = command
        arguments = self._arguments(name, values.get("arguments", None))
        self._check_tokens(name, arguments)
        output_format = values.get("output_format")
        if not isinstance(output_format, str) or output_format not in _FORMATS:
            raise VarConfigError(
                f"metadata_driver.{name} needs output_format",
                advice="Use yaml, toml, ini, or shell.",
            )
        return {
            "command": command,
            "program": program,
            "arguments": arguments,
            "output_format": output_format,
        }

    def options_key(self, values: dict[str, object]) -> str:
        """sha256 of the command template. ext, mime, enable, and timeout stay out."""
        payload = {
            "arguments": list(values.get("arguments", [])),
            "cache_epoch": self.cache_epoch,
            "command": values.get("command", ""),
            "driver": self.identity,
            "output_format": values.get("output_format", ""),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def extract(self, file: MetadataFile, field: str, options: DriverOptions) -> str:
        """Run the program once and look the field up in the parsed map."""
        return self.one_field(file, field, options, lambda: self._run(file, options))

    def _run(self, file: MetadataFile, options: DriverOptions) -> tuple[str, dict[str, str]]:
        program = options.values.get("program")
        if not isinstance(program, str) or not program:
            raise VarCandidateError(f"{options.name} has no command")
        argv = [program]
        arguments = options.values.get("arguments", [])
        if isinstance(arguments, list):
            for template in arguments:
                argv.append(self._replace(str(template), file))
        timeout = options.run_timeout()
        stdout = options.runner.run(argv, timeout)
        return stdout, self.fields_from_payload(stdout, options)

    def fields_from_payload(self, payload: str, options: DriverOptions) -> dict[str, str]:
        """Parse stored stdout with the configured output format."""
        output_format = str(options.values.get("output_format", ""))
        return OutputParser().parse(output_format, payload)

    def _arguments(self, name: str, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            try:
                return shlex.split(value, posix=True)
            except ValueError as exc:
                raise VarConfigError(
                    f"metadata_driver.{name} arguments have a bad quote",
                    advice="Close the quote, or pass arguments as a list.",
                ) from exc
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return list(value)
        raise VarConfigError(
            f"metadata_driver.{name} arguments must be a string or a list of strings",
            advice="Omit arguments to run the program with no extra arguments.",
        )

    def _check_tokens(self, name: str, arguments: list[str]) -> None:
        known = set(_TOKENS) | {"%"}
        for template in arguments:
            index = 0
            while index < len(template):
                if template[index] != "%":
                    index += 1
                    continue
                if index + 1 >= len(template) or template[index + 1] not in known:
                    token = template[index : index + 2]
                    raise VarConfigError(
                        f"metadata_driver.{name} has unknown placeholder {token!r}",
                        advice="Use %p %r %n %s %e %h %c %m %d or %%.",
                    )
                index += 2

    def _replace(self, template: str, file: MetadataFile) -> str:
        parts: list[str] = []
        index = 0
        while index < len(template):
            if template[index] != "%":
                parts.append(template[index])
                index += 1
                continue
            code = template[index + 1]
            if code == "%":
                parts.append("%")
            elif code == "d":
                parts.append(str(file.absolute.parent))
            else:
                parts.append(str(getattr(file, _TOKENS[code])))
            index += 2
        return "".join(parts)

    def _is_path(self, command: str) -> bool:
        return "/" in command or os.sep in command
