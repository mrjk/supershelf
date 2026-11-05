"""parse_float filter."""

from supershelf.template.filters.support import filter_text
from supershelf.vars.convert import to_float_text


def parse_float(value: object) -> str:
    """Return a dot spelling the float cast accepts."""
    return filter_text("parse_float", value, to_float_text)
