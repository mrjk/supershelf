"""Bool spellings. The cast words stay strict. The filter also accepts on and off."""

from supershelf.vars.convert.error import ConvertError

BOOL_TRUE = frozenset({"true", "yes", "1"})
BOOL_FALSE = frozenset({"false", "no", "0"})
_FILTER_TRUE = BOOL_TRUE | {"on"}
_FILTER_FALSE = BOOL_FALSE | {"off"}


def to_bool_text(value: str) -> str:
    """Return `true` or `false`. Raises ConvertError on a miss."""
    token = value.strip().lower()
    if token in _FILTER_TRUE:
        return "true"
    if token in _FILTER_FALSE:
        return "false"
    raise ConvertError(f"{value!r} is not a bool")
