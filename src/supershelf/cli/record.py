"""`supershelf record`."""

from __future__ import annotations

from clak import Argument, Command, ListViewMixin, Parser

from supershelf.cli.common import kept_path
from supershelf.record import RecordReader, RecordSession


class RecordIdentityFlag:
    """Link rule shared by the commands that compare a scan with the database."""

    record_identity = Argument(
        "--record-identity",
        help=(
            "Link rule for this run: a word or a comma-separated list. "
            "Does not override a match rule that set record_identity. "
            "Overrides SUPERSHELF_RECORD_IDENTITY and config.record_identity."
        ),
    )


class RecordStatusCommand(ListViewMixin, RecordIdentityFlag, Parser):
    """Compare matched files with the profile database."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, record_identity=None, **_):
        session = RecordSession.load(config, profile, record_identity)
        return session.status(path)


class RecordRunCommand(ListViewMixin, RecordIdentityFlag, Parser):
    """Record matched files into the profile database."""

    path = kept_path()

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


class RecordHistoryCommand(ListViewMixin, Parser):
    """Show recorded events."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, **_):
        return RecordReader.load(config, profile).history(path)


class RecordDuplicatesCommand(ListViewMixin, Parser):
    """List documents that share a hash."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, **_):
        return RecordReader.load(config, profile).duplicates(path)


class RecordCommand(Parser):
    """Record matched files and read that history."""

    status = Command(
        RecordStatusCommand,
        help="Compare matched files with the profile database",
    )
    run = Command(RecordRunCommand, help="Record matched files into the profile database")
    history = Command(RecordHistoryCommand, help="Show recorded events")
    duplicates = Command(
        RecordDuplicatesCommand,
        help="List documents that share a hash",
    )
