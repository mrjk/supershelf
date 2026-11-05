"""parse_boolean filter."""

from supershelf.template.filters.support import filter_text
from supershelf.vars.convert import to_bool_text


def parse_boolean(value: object) -> str:
    """Return `true` or `false`."""
    return filter_text("parse_boolean", value, to_bool_text)
