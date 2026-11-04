"""Kind-file column names and SHA text."""

from __future__ import annotations

import re
from pathlib import Path

from supershelf.constants import KIND_CSV_PATH, KIND_CSV_SHA
from supershelf.errors import VarConfigError
from supershelf.vars.spec import check_assignment_key


class KindNames:
    """Feed columns, legal CSV names, and the sha256 text check."""

    _LOWER_NAME = re.compile(r"[a-z_][a-z0-9_]*\Z")
    _FEED_NAME = re.compile(r"[A-Z_][A-Z0-9_]*\Z")
    _SHA_BAD = frozenset({"sha", "Sha"})
    _SHA_TEXT = re.compile(r"[0-9a-f]{64}\Z")
    _WRAPPED_FEED = frozenset({KIND_CSV_PATH, "SHA"})

    @classmethod
    def feed_column_name(cls, name: str) -> str:
        """The ignored column data feed writes for this var."""
        column = "".join(char.upper() if "a" <= char <= "z" else char for char in name)
        if column in cls._WRAPPED_FEED:
            return f"_{column}_"
        return column

    @classmethod
    def is_feed_column(cls, name: str) -> bool:
        """True for an uppercase feed column. PATH and SHA stay reserved."""
        if cls._FEED_NAME.fullmatch(name) is None:
            return False
        if not any("A" <= char <= "Z" for char in name):
            return False
        if name == KIND_CSV_PATH or name == KIND_CSV_SHA or name in cls._SHA_BAD:
            return False
        return True

    @classmethod
    def legal_column(cls, name: str) -> bool:
        """True for a lowercase CSV var column."""
        if name == KIND_CSV_PATH or name == KIND_CSV_SHA or name in cls._SHA_BAD:
            return False
        if cls._LOWER_NAME.fullmatch(name) is None:
            return False
        try:
            check_assignment_key(name, "kind file")
        except VarConfigError:
            return False
        return True

    @classmethod
    def check_sha(cls, path: Path, relative: str, value: str) -> str:
        """A non-empty SHA is 64 lowercase hex digits."""
        if cls._SHA_TEXT.fullmatch(value) is None:
            raise VarConfigError(
                f"{path} path {relative} SHA {value!r} must be 64 lowercase hex digits",
                advice="Use the sha256 of the file, in lowercase hex.",
            )
        return value
