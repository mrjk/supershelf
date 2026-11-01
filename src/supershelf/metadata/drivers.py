"""Builtin metadata drivers."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
from pathlib import Path

from supershelf.errors import VarCandidateError, VarConfigError
from supershelf.metadata.driver import DriverOptions, MetadataDriver, MetadataFile
from supershelf.metadata.parse import OutputParser
from supershelf.metadata.pdf import pdf_date, read_pdf_metadata

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
_PDF_TEXT = (
    ("author", "author"),
    ("title", "title"),
    ("subject", "subject"),
    ("creator", "creator"),
    ("producer", "producer"),
)


class FsDriver(MetadataDriver):
    """Walk strings already stored on the file. No cache row."""

    identity = "fs"
    ignores_enable = True
    accepts_timeout = False
    writes_cache = False

    def extract(self, file: MetadataFile, field: str, options: DriverOptions) -> str:
        """Return one walk string. A blank value is a miss."""
        del options
        values = {
            "ctime": file.ctime,
            "mtime": file.mtime,
            "hash": file.sha256,
            "name": file.name,
            "stem": file.stem,
            "ext": file.extension,
            "path": file.relative,
            "dir": file.directory,
        }
        if field not in values:
            raise VarCandidateError(f"fs has no {field}")
        return values[field]


class PdfDriver(MetadataDriver):
    """PDF info via pypdf. Dates are YYYY-MM-DD. This does not touch pdf_cdate()."""

    identity = "pdf"
    extensions = ("pdf",)
    mime_types = ("application/pdf",)
    ignores_enable = True
    accepts_timeout = False

    def extract(self, file: MetadataFile, field: str, options: DriverOptions) -> str:
        """Return one PDF info field. The parsed map is reused for this hash."""
        return self.one_field(file, field, options, lambda: self._read(file))

    def _read(self, file: MetadataFile) -> tuple[str, dict[str, str]]:
        fields = self._info(file.absolute)
        payload = json.dumps(fields, sort_keys=True, separators=(",", ":"))
        return payload, fields

    def fields_from_payload(self, payload: str, options: DriverOptions) -> dict[str, str]:
        """The stored JSON map is the field table."""
        del options
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise VarCandidateError(f"pdf cache is invalid: {exc}") from exc
        if not isinstance(raw, dict):
            raise VarCandidateError("pdf cache is not a mapping")
        found: dict[str, str] = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, str) and value.strip():
                found[key] = value
        return found

    def _info(self, path: Path) -> dict[str, str]:
        meta = read_pdf_metadata(path)
        if meta is None:
            return {}
        found: dict[str, str] = {}
        created = pdf_date(meta.creation_date)
        modified = pdf_date(meta.modification_date)
        if created:
            found["creation_date"] = created
        if modified:
            found["modification_date"] = modified
        for key, attr in _PDF_TEXT:
            text = self._text(getattr(meta, attr, None))
            if text:
                found[key] = text
        return found

    def _text(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None


class ExiftoolDriver(MetadataDriver):
    """exiftool -json -G. SourceFile and File: keys are dropped."""

    identity = "exiftool"
    binary = "exiftool"

    def extract(self, file: MetadataFile, field: str, options: DriverOptions) -> str:
        """Return one grouped tag. One JSON run is shared by later fields."""
        return self.one_field(file, field, options, lambda: self._read(file, options))

    def _read(self, file: MetadataFile, options: DriverOptions) -> tuple[str, dict[str, str]]:
        timeout = options.run_timeout()
        stdout = options.runner.run(
            ["exiftool", "-json", "-G", str(file.absolute)],
            timeout,
        )
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise VarCandidateError(f"exiftool JSON is invalid: {exc}") from exc
        return stdout, self._fields(raw)

    def fields_from_payload(self, payload: str, options: DriverOptions) -> dict[str, str]:
        """Parse the stored exiftool JSON the same way as a fresh run."""
        del options
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise VarCandidateError(f"exiftool JSON is invalid: {exc}") from exc
        return self._fields(raw)

    def _fields(self, raw: object) -> dict[str, str]:
        document = raw[0] if isinstance(raw, list) and raw else raw
        if not isinstance(document, dict):
            raise VarCandidateError("exiftool did not return a mapping")
        found: dict[str, str] = {}
        for key, value in document.items():
            if not isinstance(key, str) or key == "SourceFile" or key.startswith("File:"):
                continue
            if value is None or isinstance(value, (list, dict)):
                continue
            text = value.strip() if isinstance(value, str) else str(value).strip()
            if text:
                found[key] = text
        return found


class PdftotextDriver(MetadataDriver):
    """pdftotext stdout. The only field is text, and it may be omitted."""

    identity = "pdftotext"
    extensions = ("pdf",)
    mime_types = ("application/pdf",)
    single_field = "text"
    binary = "pdftotext"

    def extract(self, file: MetadataFile, field: str, options: DriverOptions) -> str:
        """Return stdout. The text field may be omitted."""
        return self.one_field(file, field, options, lambda: self._read(file, options))

    def _read(self, file: MetadataFile, options: DriverOptions) -> tuple[str, dict[str, str]]:
        timeout = options.run_timeout()
        stdout = options.runner.run(
            ["pdftotext", "-q", "-enc", "UTF-8", str(file.absolute), "-"],
            timeout,
        )
        text = stdout.strip()
        fields = {"text": text} if text else {}
        return stdout, fields

    def fields_from_payload(self, payload: str, options: DriverOptions) -> dict[str, str]:
        """The stored payload is stdout. The only field is text."""
        del options
        text = payload.strip()
        return {"text": text} if text else {}


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
