"""PDF info via pypdf. Dates are YYYY-MM-DD."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from supershelf.constants import DATE_TEXT
from supershelf.errors import VarCandidateError
from supershelf.metadata.driver import DriverOptions, MetadataDriver, MetadataFile

_PDF_TEXT = (
    ("author", "author"),
    ("title", "title"),
    ("subject", "subject"),
    ("creator", "creator"),
    ("producer", "producer"),
)


def read_pdf_metadata(path: Path) -> Any:
    """Document info, or None when the file cannot be read."""
    try:
        return PdfReader(str(path)).metadata
    except (OSError, PyPdfError):
        return None


def pdf_date(value: object) -> str | None:
    """YYYY-MM-DD for a PDF date, or None when the value is not a datetime."""
    if not isinstance(value, datetime):
        return None
    return value.strftime(DATE_TEXT)


class PdfDriver(MetadataDriver):
    """PDF info via pypdf. Dates are YYYY-MM-DD."""

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
