"""One-pass `{{ name }}` templates. Dotted names read dict keys."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from supershelf.errors import SupershelfError


class Template:
    """Render `{{ name }}` placeholders against one scope."""

    _PLACEHOLDER = re.compile(
        r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\}\}"
    )

    def __init__(self, scope: Mapping[str, Any]) -> None:
        self.scope = scope

    def render(self, template: str) -> str:
        """Replace placeholders once. Text taken from the scope is not rendered again."""
        return self._PLACEHOLDER.sub(self._replace, template)

    def _replace(self, match: re.Match[str]) -> str:
        return self._lookup(match.group(1))

    def _lookup(self, expression: str) -> str:
        name, _, rest = expression.partition(".")
        if name not in self.scope:
            raise SupershelfError(f"Unknown template name {name!r}")
        current: Any = self.scope[name]
        if rest:
            for part in rest.split("."):
                if not isinstance(current, Mapping) or part not in current:
                    raise SupershelfError(f"Unknown template key {expression!r}")
                current = current[part]
        if not isinstance(current, str):
            raise SupershelfError(f"Template {expression!r} must be a string")
        return current
