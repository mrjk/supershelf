"""`supershelf db`."""

from __future__ import annotations

import json

from clak import Command, ListViewMixin, Parser

from supershelf.database import ShelfDatabase
from supershelf.scan.runs import ShelfRuns

_STRUCTURED_FORMATS = frozenset({"json", "yaml"})


def present_stored_vars(raw: str, fmt: str | None) -> object:
    """One vars cell. Table lines are name, colon, display, sorted by name."""
    body = json.loads(raw) if raw else {}
    names = sorted(body)
    shown = {
        name: body[name].get("display", "") if isinstance(body[name], dict) else ""
        for name in names
    }
    if fmt in _STRUCTURED_FORMATS:
        return shown
    return "\n".join(f"{name}: {shown[name]}" for name in names)


class DbShowCommand(ListViewMixin, Parser):
    """Print document rows. Does not scan or create the database."""

    def cli_run(self, config=None, profile=None, ctx=None, **_):
        fmt = ctx.view_settings.get("format") if ctx is not None else None
        rows = []
        for shelf in ShelfRuns.load(config, profile).shelves:
            with ShelfDatabase.open_read(shelf.database_file) as database:
                for document in database.documents():
                    rows.append(
                        {
                            "profile": shelf.name,
                            "presence": document.presence,
                            "input": document.input_index,
                            "path": document.path,
                            "kind": document.match_kind,
                            "rule": document.rule,
                            "hash": document.hash,
                            "generation": document.generation,
                            "mtime": shelf.show_time(document.mtime or "")
                            if document.mtime
                            else "",
                            "ctime": shelf.show_time(document.ctime or "")
                            if document.ctime
                            else "",
                            "vars": present_stored_vars(document.vars_json, fmt),
                        }
                    )
        return rows


class DbCommand(Parser):
    """Read the profile database."""

    show = Command(DbShowCommand, help="Print document rows")
