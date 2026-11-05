"""parse_int filter."""

from supershelf.template.filters.support import filter_text
from supershelf.vars.convert import to_int_text


def parse_int(value: object) -> str:
    """Return an int spelling. A zero fraction is dropped."""
    return filter_text("parse_int", value, to_int_text)
