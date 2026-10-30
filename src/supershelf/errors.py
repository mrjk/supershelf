"""Errors a user can fix by changing flags or config files."""

from clak.exception import ClakUserError


class SupershelfError(ClakUserError):
    """Configuration or discovery problem, shown without a traceback."""


class VarConfigError(SupershelfError):
    """A var table, template, module, or kind file is invalid."""

    rc = 2


class VarResolveError(SupershelfError):
    """A variable had no candidate that rendered."""


class VarCandidateError(Exception):
    """Skip this candidate and try the next one.

    Built-in commands and user modules raise this. It is not a
    SupershelfError, so a caught miss does not exit the command.
    """
