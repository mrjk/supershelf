"""`supershelf output`."""

from __future__ import annotations

from clak import Command, ListViewMixin, Parser
from clak.views import ListView

from supershelf.cli.common import kept_path
from supershelf.output import OutputSession


class OutputPreviewCommand(ListViewMixin, Parser):
    """Print destinations without writing them."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, format=None, **_):
        rows, stale = OutputSession.load(config, profile).preview(path)
        if not stale:
            return rows
        if format:
            ListView().render(rows, format=format)
        else:
            ListView().render(rows)
        raise SystemExit(1)


class OutputRunCommand(ListViewMixin, Parser):
    """Write destinations and record the apply."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, dry_run=False, format=None, **_):
        rows, failed, stale = OutputSession.load(config, profile).run(path, dry_run=bool(dry_run))
        if stale:
            raise SystemExit(1)
        if failed:
            if format:
                ListView().render(rows, format=format)
            else:
                ListView().render(rows)
            raise SystemExit(1)
        return rows


class OutputCommand(Parser):
    """Write destinations for recorded files."""

    preview = Command(OutputPreviewCommand, help="Print destinations without writing them")
    run = Command(OutputRunCommand, help="Write destinations and record the apply")
