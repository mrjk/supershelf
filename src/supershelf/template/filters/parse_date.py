"""parse_date filter. The calendar parse lives in vars.convert.date."""

from collections.abc import Mapping

from jinja2 import pass_context

from supershelf.constants import DATE_TEXT, FIELD_DATE_FORMAT, VAR_CONFIG
from supershelf.errors import VarCandidateError
from supershelf.template.render import scope_field
from supershelf.vars.convert import format_calendar, parse_calendar


@pass_context
def parse_date(
    context: object,
    value: object,
    *formats: object,
    output: object = None,
) -> str:
    """Print the first format that parses `value`. Omitted output uses the profile format."""
    if not isinstance(value, str) or not formats:
        raise VarCandidateError("parse_date needs a string and a format")
    checked: list[str] = []
    for fmt in formats:
        if not isinstance(fmt, str) or not fmt:
            raise VarCandidateError("parse_date formats must be non-empty strings")
        checked.append(fmt)
    pattern = _output_format(context, output)
    for fmt in checked:
        try:
            parsed = parse_calendar(value, fmt)
        except ValueError:
            continue
        try:
            return format_calendar(parsed, pattern)
        except (TypeError, ValueError) as exc:
            raise VarCandidateError(f"Date format {pattern!r} is invalid") from exc
    raise VarCandidateError(f"No format matched {value!r}")


def _output_format(context: object, output: object) -> str:
    if output is not None:
        if not isinstance(output, str) or not output.strip():
            raise VarCandidateError("parse_date output must be a non-empty string")
        return output
    if isinstance(context, Mapping):
        found = scope_field(context, VAR_CONFIG, FIELD_DATE_FORMAT)
        if isinstance(found, str) and found.strip():
            return found
    return DATE_TEXT
