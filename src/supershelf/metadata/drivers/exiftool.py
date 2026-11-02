"""exiftool -json -G. SourceFile and File: keys are dropped."""

from __future__ import annotations

import json

from supershelf.errors import VarCandidateError
from supershelf.metadata.driver import DriverOptions, MetadataDriver, MetadataFile


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
