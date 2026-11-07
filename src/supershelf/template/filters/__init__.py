"""Built-in Jinja filters. Add a module and one entry in FILTERS."""

from typing import Any

from supershelf.template.filters.enclose import enclose
from supershelf.template.filters.parse_boolean import parse_boolean
from supershelf.template.filters.parse_date import parse_date
from supershelf.template.filters.parse_float import parse_float
from supershelf.template.filters.parse_int import parse_int

FILTERS = {
    "parse_date": parse_date,
    "parse_float": parse_float,
    "parse_int": parse_int,
    "parse_boolean": parse_boolean,
    "enclose": enclose,
}


def register(environment: Any) -> None:
    """Register each built-in filter. A repeated name is a config error."""
    for name, func in FILTERS.items():
        environment.add_filter(name, func)
