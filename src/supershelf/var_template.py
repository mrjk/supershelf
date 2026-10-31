"""Jinja rendering for variable values."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import jinja2

from supershelf.constants import TEMPLATE_MARKERS
from supershelf.errors import VarCandidateError, VarConfigError, VarResolveError
from supershelf.var_commands import BuiltinCommands, FileBinding


def is_template(source: str) -> bool:
    """True when the candidate contains a Jinja marker."""
    return any(marker in source for marker in TEMPLATE_MARKERS)


class _StringCommand:
    """Call a command and require it to return a string."""

    def __init__(self, name: str, func: Any) -> None:
        self._name = name
        self._func = func

    def __call__(self, *args: object, **kwargs: object) -> str:
        try:
            result = self._func(*args, **kwargs)
        except VarCandidateError:
            raise
        if not isinstance(result, str):
            raise VarCandidateError(f"{self._name} must return a string")
        return result


class VarEnvironment:
    """Compile each var template once. Literals are not compiled."""

    def __init__(self) -> None:
        self._env = jinja2.Environment(
            undefined=jinja2.StrictUndefined,
            autoescape=False,
        )
        self._compiled: dict[str, jinja2.Template] = {}
        self._names: set[str] = set()
        self._commands = BuiltinCommands()
        self._commands.register(self)

    def add_global(self, name: str, func: Any) -> None:
        """Register a Jinja global. A repeated name is a config error."""
        self._add(name, func, self._env.globals)

    def add_filter(self, name: str, func: Any) -> None:
        """Register a Jinja filter. A repeated name is a config error."""
        self._add(name, func, self._env.filters)

    def compile_source(self, source: str) -> None:
        """Compile a candidate now, so a syntax error fails before the walk."""
        self._template(source)

    def render(
        self,
        source: str,
        scope: Mapping[str, Any],
        file: FileBinding,
        pdf_cache: dict[str, tuple[str | None, str | None]],
    ) -> str:
        """Render one candidate. A miss raises VarCandidateError."""
        if self._is_literal(source):
            return source
        template = self._template(source)
        if template is None:
            return source
        token = self._commands.bind(file, pdf_cache)
        try:
            rendered = template.render(dict(scope))
        except VarCandidateError:
            raise
        except jinja2.UndefinedError as exc:
            raise VarCandidateError(str(exc)) from exc
        except jinja2.TemplateError as exc:
            raise VarResolveError(
                f"Var template failed: {exc}",
                advice="Check the template and custom commands.",
            ) from exc
        finally:
            self._commands.unbind(token)
        if not isinstance(rendered, str):
            raise VarCandidateError("A var template must render to a string")
        return rendered

    def _add(self, name: str, func: Any, target: dict[str, Any]) -> None:
        if name in self._names or name in target:
            raise VarConfigError(
                f"Var command {name!r} is already defined",
                advice="Rename it. Built-in commands cannot be replaced.",
            )
        if not callable(func):
            raise VarConfigError(
                f"Var command {name!r} must be callable",
                advice="Set GLOBALS and FILTERS to functions.",
            )
        target[name] = _StringCommand(name, func)
        self._names.add(name)

    def _template(self, source: str) -> jinja2.Template | None:
        if self._is_literal(source):
            return None
        found = self._compiled.get(source)
        if found is not None:
            return found
        try:
            compiled = self._env.from_string(source)
        except jinja2.TemplateSyntaxError as exc:
            raise VarConfigError(
                f"Invalid var template: {source}",
                advice="Fix the Jinja syntax. A literal must not contain {{, {% or {#.",
            ) from exc
        self._compiled[source] = compiled
        return compiled

    def _is_literal(self, source: str) -> bool:
        return not is_template(source)
