"""Errors a user can fix by changing flags or config files."""

from clak.exception import ClakUserError


class SupershelfError(ClakUserError):
    """Configuration or discovery problem, shown without a traceback."""


class VarConfigError(SupershelfError):
    """A var table, template, module, or kind file is invalid."""

    rc = 2


class VarResolveError(SupershelfError):
    """A variable had no candidate that rendered."""


class RecordConfigError(SupershelfError):
    """A record_identity word or list is invalid.

    The value came from --record-identity, SUPERSHELF_RECORD_IDENTITY,
    config.record_identity, or a match rule. Exit 2.
    """

    rc = 2


class DatabaseError(SupershelfError):
    """The profile sqlite file cannot be read or written."""


class CacheError(SupershelfError):
    """The profile metadata cache cannot be read or written."""


class OutputConfigError(SupershelfError):
    """A bad output item, output module, or literal when. Exit 2."""

    rc = 2


class OutputResolveError(SupershelfError):
    """A file the output plan cannot accept.

    The record gate, a layout, a claim, or a destination. The tip names a fix.
    """


class VarCandidateError(Exception):
    """Skip this candidate and try the next one.

    Built-in commands and user modules raise this. It is not a
    SupershelfError, so a caught miss does not exit the command.
    """
