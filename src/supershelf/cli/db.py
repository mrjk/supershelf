"""`supershelf db`."""

from __future__ import annotations

import json

from clak import Argument, Command, ListViewMixin, Parser

from supershelf.cli.common import STRUCTURED_FORMATS, kept_path, view_format
from supershelf.database import ShelfDatabase
from supershelf.record import RecordSession
from supershelf.scan.runs import ShelfRuns


def present_stored_vars(raw: str, fmt: str | None) -> object:
    """One vars cell. Table lines are name, colon, display, sorted by name."""
    body = json.loads(raw) if raw else {}
    names = sorted(body)
    shown = {
        name: body[name].get("display", "") if isinstance(body[name], dict) else ""
        for name in names
    }
    if fmt in STRUCTURED_FORMATS:
        return shown
    return "\n".join(f"{name}: {shown[name]}" for name in names)


class DbShowCommand(ListViewMixin, Parser):
    """Print document rows. Does not scan or create the database."""

    def cli_run(self, config=None, profile=None, ctx=None, **_):
        fmt = view_format(ctx)
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


class DbImportCommand(ListViewMixin, Parser):
    """Record matched files into the profile database."""

    path = kept_path()
    record_identity = Argument(
        "--record-identity",
        help=(
            "Link rule for this run: a word or a comma-separated list. "
            "Does not override a match rule that set record_identity. "
            "Overrides SUPERSHELF_RECORD_IDENTITY and config.record_identity."
        ),
    )

    def cli_run(
        self,
        config=None,
        profile=None,
        path=None,
        dry_run=False,
        record_identity=None,
        **_,
    ):
        session = RecordSession.load(config, profile, record_identity)
        return session.run(path, dry_run=bool(dry_run))


class DbCommand(Parser):
    """Read or import the profile database."""

    show = Command(DbShowCommand, help="Print document rows")


setattr(
    DbCommand,
    "import",
    Command(DbImportCommand, help="Record matched files into the profile database"),
)
