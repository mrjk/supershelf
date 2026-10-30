"""Built-in Jinja commands for variable templates."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from pypdf import PdfReader

from supershelf.constants import DATE_TEXT
from supershelf.errors import VarCandidateError


@dataclass(frozen=True)
class FileBinding:
    """The file a var command can read while a template renders."""

    absolute: Path
    sha256: str
    ctime: str
    mtime: str


class BuiltinCommands:
    """Commands registered on every var environment."""

    _PdfDates = tuple[str | None, str | None]
    _Binding = tuple[FileBinding, dict[str, _PdfDates]]
    _current_file: ClassVar[ContextVar[_Binding | None]] = ContextVar(
        "supershelf_var_file",
        default=None,
    )

    def register(self, environment: Any) -> None:
        """Add these commands as Jinja globals."""
        environment.add_global("regex_time_var", self.regex_time_var)
        environment.add_global("regex_replace", self.regex_replace)
        environment.add_global("file", self.file)
        environment.add_global("pdf_cdate", self.pdf_cdate)
        environment.add_global("pdf_mdate", self.pdf_mdate)

    def bind(
        self,
        file: FileBinding,
        pdf_cache: dict[str, _PdfDates],
    ) -> Token[_Binding | None]:
        """Make this file visible to commands for the current render."""
        return self._current_file.set((file, pdf_cache))

    def unbind(self, token: Token[_Binding | None]) -> None:
        """Restore the previous file."""
        self._current_file.reset(token)

    def regex_time_var(self, value: object, *formats: object) -> str:
        """Return YYYY-MM-DD for the first format that parses `value`."""
        if not isinstance(value, str) or not formats:
            raise VarCandidateError("regex_time_var needs a string and a format")
        for fmt in formats:
            if not isinstance(fmt, str) or not fmt:
                raise VarCandidateError("regex_time_var formats must be strings")
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            return parsed.strftime(DATE_TEXT)
        raise VarCandidateError(f"No format matched {value!r}")

    def regex_replace(self, value: object, pattern: object, replacement: object) -> str:
        """Replace `pattern` in `value`. No match skips this candidate."""
        if (
            not isinstance(value, str)
            or not isinstance(pattern, str)
            or not isinstance(replacement, str)
        ):
            raise VarCandidateError("regex_replace needs three strings")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise VarCandidateError(f"Invalid pattern {pattern!r}: {exc}") from exc
        if compiled.search(value) is None:
            raise VarCandidateError(f"Pattern {pattern!r} did not match")
        return compiled.sub(replacement, value)

    def file(self, field: object) -> str:
        """Return the stored ctime or mtime ISO timestamp."""
        binding, _cache = self._current()
        if field == "ctime":
            return binding.ctime
        if field == "mtime":
            return binding.mtime
        raise VarCandidateError("file() accepts ctime or mtime")

    def pdf_cdate(self) -> str:
        """Return the PDF creation date as YYYY-MM-DD."""
        return self._pdf_date(0)

    def pdf_mdate(self) -> str:
        """Return the PDF modification date as YYYY-MM-DD."""
        return self._pdf_date(1)

    def _pdf_date(self, index: int) -> str:
        binding, cache = self._current()
        if binding.sha256 not in cache:
            cache[binding.sha256] = self._read_pdf(binding.absolute)
        value = cache[binding.sha256][index]
        if value is None:
            raise VarCandidateError("PDF date is missing")
        return value

    def _read_pdf(self, path: Path) -> _PdfDates:
        try:
            meta = PdfReader(str(path)).metadata
        except Exception:
            return (None, None)
        if meta is None:
            return (None, None)
        return (self._as_date(meta.creation_date), self._as_date(meta.modification_date))

    def _as_date(self, value: object) -> str | None:
        if not isinstance(value, datetime):
            return None
        return value.strftime(DATE_TEXT)

    def _current(self) -> _Binding:
        found = self._current_file.get()
        if found is None:
            raise VarCandidateError("No file is bound for this command")
        return found
