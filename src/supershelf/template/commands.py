"""Built-in Jinja commands for variable templates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from jinja2 import pass_context

from supershelf.constants import DATE_TEXT, FIELD_DATE_FORMAT, VAR_CONFIG
from supershelf.errors import VarCandidateError
from supershelf.metadata.session import MetadataSession
from supershelf.template.render import scope_field


class BuiltinCommands:
    """Commands registered on every var environment."""

    def __init__(self) -> None:
        self._session: MetadataSession | None = None

    def register(self, environment: Any) -> None:
        """Add these commands as Jinja globals and filters."""
        environment.add_filter("parse_date", self.parse_date)
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

    @pass_context
    def parse_date(
        self,
        context: object,
        value: object,
        *formats: object,
        output: object = None,
    ) -> str:
        """Print the first format that parses `value`. Omitted output uses the profile format."""
        if not isinstance(value, str) or not formats:
            raise VarCandidateError("parse_date needs a string and a format")
        checked: list[str] = []
        for fmt in formats:
            if not isinstance(fmt, str) or not fmt:
                raise VarCandidateError("parse_date formats must be non-empty strings")
            checked.append(fmt)
        pattern = self._output_format(context, output)
        for fmt in checked:
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            try:
                return parsed.strftime(pattern)
            except (TypeError, ValueError) as exc:
                raise VarCandidateError(f"Date format {pattern!r} is invalid") from exc
        raise VarCandidateError(f"No format matched {value!r}")

    @staticmethod
    def _output_format(context: object, output: object) -> str:
        if output is not None:
            if not isinstance(output, str) or not output.strip():
                raise VarCandidateError("parse_date output must be a non-empty string")
            return output
        if isinstance(context, Mapping):
            found = scope_field(context, VAR_CONFIG, FIELD_DATE_FORMAT)
            if isinstance(found, str) and found.strip():
                return found
        return DATE_TEXT

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
