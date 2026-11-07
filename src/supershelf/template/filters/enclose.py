"""enclose filter: optional prefix/suffix around a set value."""

from __future__ import annotations

import jinja2

from supershelf.errors import VarCandidateError

_MISSING = object()


def enclose(
    value: object,
    prefix: object = "",
    suffix: object = "",
    default: object = _MISSING,
) -> str:
    """Wrap a set value with prefix and suffix.

    Absent means undefined, None, or "". Without default, absent returns "".
    With default, absent uses that string as the middle text.
    """
    _require_str("prefix", prefix)
    _require_str("suffix", suffix)
    middle = _middle(value)
    if default is _MISSING:
        if middle is None:
            return ""
        return f"{prefix}{middle}{suffix}"
    _require_str("default", default)
    text = default if middle is None else middle
    return f"{prefix}{text}{suffix}"


def _middle(value: object) -> str | None:
    if jinja2.is_undefined(value) or value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    if text == "":
        return None
    return text


def _require_str(name: str, value: object) -> None:
    if not isinstance(value, str):
        raise VarCandidateError(f"enclose {name} needs a string")
