"""`supershelf db`."""

from __future__ import annotations

from clak import Command, ListViewMixin, Parser

from supershelf.database import ShelfDatabase
from supershelf.scan.runs import ShelfRuns


class DbShowCommand(ListViewMixin, Parser):
    """Print document rows. Does not scan or create the database."""

    def cli_run(self, config=None, profile=None, **_):
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
                        }
                    )
        return rows


class DbCommand(Parser):
    """Read the profile database."""

    show = Command(DbShowCommand, help="Print document rows")
