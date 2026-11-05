"""Built-in Jinja commands for variable templates."""

from __future__ import annotations

import re
from typing import Any

from supershelf.errors import VarCandidateError
from supershelf.metadata.session import MetadataSession
from supershelf.template.filters import register as register_filters


class BuiltinCommands:
    """Commands registered on every var environment."""

    def __init__(self) -> None:
        self._session: MetadataSession | None = None

    def register(self, environment: Any) -> None:
        """Add these commands as Jinja globals and filters."""
        register_filters(environment)
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
