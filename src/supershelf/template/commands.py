"""Built-in Jinja commands for variable templates."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from supershelf.constants import DATE_TEXT
from supershelf.errors import VarCandidateError
from supershelf.metadata.session import MetadataSession


class BuiltinCommands:
    """Commands registered on every var environment."""

    def __init__(self) -> None:
        self._session: MetadataSession | None = None

    def register(self, environment: Any) -> None:
        """Add these commands as Jinja globals."""
        environment.add_global("regex_time_var", self.regex_time_var)
        environment.add_global("regex_replace", self.regex_replace)
        environment.add_global("meta", self.meta)

    def bind_session(self, session: MetadataSession) -> None:
        """Use this session when a template calls meta()."""
        self._session = session

    def meta(self, driver: object, field: object | None = None) -> str:
        """Return one metadata field. A miss raises VarCandidateError."""
        if self._session is None:
            raise VarCandidateError("No metadata session is bound")
        return self._session.extract(driver, field)

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
