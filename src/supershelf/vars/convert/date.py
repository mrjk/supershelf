"""Calendar parse shared by the date cast and the parse_date filter."""

from datetime import datetime


def parse_calendar(text: str, fmt: str) -> datetime:
    """Parse `text` with a strptime format. Raises ValueError on a miss."""
    return datetime.strptime(text, fmt)


def format_calendar(parsed: datetime, pattern: str) -> str:
    """Format a parsed date. Raises ValueError when the pattern is invalid."""
    return parsed.strftime(pattern)


def parse_round_trip(text: str, fmt: str) -> datetime:
    """Parse `text` and require the same format to print it back."""
    parsed = parse_calendar(text, fmt)
    if format_calendar(parsed, fmt) != text:
        raise ValueError(f"{text!r} does not match {fmt}")
    return parsed
