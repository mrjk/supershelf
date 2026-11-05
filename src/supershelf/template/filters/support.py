"""Shared checks for a filter that converts one string."""

from collections.abc import Callable

from supershelf.errors import VarCandidateError
from supershelf.vars.convert import ConvertError


def filter_text(name: str, value: object, convert: Callable[[str], str]) -> str:
    """Convert one string. A miss raises VarCandidateError."""
    if not isinstance(value, str):
        raise VarCandidateError(f"{name} needs a string")
    try:
        return convert(value)
    except ConvertError as exc:
        raise VarCandidateError(str(exc)) from exc
