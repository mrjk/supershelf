"""Jinja rendering for variable values."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import jinja2

from supershelf.constants import TEMPLATE_MARKERS
from supershelf.errors import VarCandidateError, VarConfigError, VarResolveError
from supershelf.template import ScopeObject
from supershelf.var_commands import BuiltinCommands


def _finalize(value: object) -> object:
    """A bare namespace prints its text. A plain mapping still needs a field."""
    if isinstance(value, ScopeObject):
        return str(value)
    if isinstance(value, Mapping):
        raise VarCandidateError("A namespace needs a field")
    return value


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
            finalize=_finalize,
        )
        self._compiled: dict[str, jinja2.Template] = {}
        self._names: set[str] = set()
        self._commands = BuiltinCommands()
        self._commands.register(self)
        self._registry: Any = None

    def bind_metadata(self, registry: Any, session: Any) -> None:
        """Check meta() names against this registry, and call this session."""
        self._registry = registry
        self._commands.bind_session(session)

    def add_global(self, name: str, func: Any) -> None:
        """Register a Jinja global. A repeated name is a config error."""
        self._add(name, func, self._env.globals)

    def add_filter(self, name: str, func: Any) -> None:
        """Register a Jinja filter. A repeated name is a config error."""
        self._add(name, func, self._env.filters)

    def compile_source(self, source: str) -> None:
        """Compile a candidate now, so a syntax error fails before the walk."""
        self._template(source)

    def render(self, source: str, scope: Mapping[str, Any]) -> str:
        """Render one candidate. A miss raises VarCandidateError."""
        if self._is_literal(source):
            return source
        template = self._template(source)
        if template is None:
            return source
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
        self._reject_unknown_meta(source)
        try:
            compiled = self._env.from_string(source)
        except jinja2.TemplateSyntaxError as exc:
            raise VarConfigError(
                f"Invalid var template: {source}",
                advice="Fix the Jinja syntax. A literal must not contain {{, {% or {#.",
            ) from exc
        self._compiled[source] = compiled
        return compiled

    def _reject_unknown_meta(self, source: str) -> None:
        registry = self._registry
        if registry is None or self._is_literal(source):
            return
        try:
            parsed = self._env.parse(source)
        except jinja2.TemplateSyntaxError:
            return
        for call in parsed.find_all(jinja2.nodes.Call):
            driver_name = self._meta_driver_const(call)
            if driver_name is None:
                continue
            if registry.entry(driver_name) is None:
                raise VarConfigError(
                    f"Unknown metadata driver {driver_name!r}",
                    advice="Declare it under metadata_driver, or use a builtin name.",
                )

    def _meta_driver_const(self, call: jinja2.nodes.Call) -> str | None:
        node = call.node
        if not isinstance(node, jinja2.nodes.Name) or node.name != "meta":
            return None
        chosen: jinja2.nodes.Node | None = None
        if call.args:
            chosen = call.args[0]
        else:
            for keyword in call.kwargs:
                if keyword.key == "driver":
                    chosen = keyword.value
                    break
        if not isinstance(chosen, jinja2.nodes.Const) or not isinstance(chosen.value, str):
            return None
        return chosen.value

    def _is_literal(self, source: str) -> bool:
        return not is_template(source)
