"""Read PDF document info. Dates are YYYY-MM-DD."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from supershelf.constants import DATE_TEXT


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
