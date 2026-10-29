"""Errors a user can fix by changing flags or config files."""

from clak.exception import ClakUserError


class SupershelfError(ClakUserError):
    """Configuration or discovery problem, shown without a traceback."""
