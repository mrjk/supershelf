"""`supershelf data`."""

from __future__ import annotations

from clak import Argument, Command, Parser
from clak.comp.views import CompositeViewMixin
from clak.views import CompositeView, ListView

from supershelf.data import ShowTable, run_feed, run_prune, run_show


class DataFeedCommand(Parser):
    """Fill empty kind-file cells with resolved values."""

    names = Argument(
        "names",
        nargs="?",
        default=None,
        help=(
            "Comma-separated kinds or var names. Spaces around commas are ignored. "
            "A name that is both needs --kind or --var."
        ),
    )
    kind = Argument(
        "--kind",
        help="Comma-separated kinds. Each selected kind enables its schema vars.",
    )
    var = Argument(
        "--var",
        help="Comma-separated var names. With --kind, only these vars are written.",
    )
    force = Argument(
        "--force",
        action="store_true",
        help="Write kind files without asking. Required when stdin is not a terminal.",
    )

    def cli_run(
        self,
        config=None,
        profile=None,
        names=None,
        kind=None,
        var=None,
        force=False,
        dry_run=False,
        verbosity=0,
        **_,
    ):
        run_feed(
            config,
            profile,
            names,
            kind=kind,
            var=var,
            force=bool(force),
            dry_run=bool(dry_run),
            verbosity=int(verbosity or 0),
        )


class DataPruneCommand(Parser):
    """Drop empty columns, unmatched rows, or every row in existing kind files."""

    empty_fields = Argument(
        "--empty-fields",
        action="store_true",
        help="Drop empty columns that are not in the schema. This is the default.",
    )
    missing = Argument(
        "--missing",
        action="store_true",
        help="Drop rows whose path is not matched as that kind. Documents stay.",
    )
    clear = Argument(
        "--clear",
        action="store_true",
        help="Remove every row. The kind file and the database stay.",
    )
    every = Argument(
        "--all",
        action="store_true",
        help="Run every purge, including --clear. The database stays.",
    )
    force = Argument(
        "--force",
        action="store_true",
        help="Write kind files without asking. Required when stdin is not a terminal.",
    )

    def cli_run(
        self,
        config=None,
        profile=None,
        empty_fields=False,
        missing=False,
        clear=False,
        every=False,
        force=False,
        dry_run=False,
        verbosity=0,
        **_,
    ):
        run_prune(
            config,
            profile,
            empty_fields=bool(empty_fields),
            missing=bool(missing),
            clear=bool(clear),
            every=bool(every),
            force=bool(force),
            dry_run=bool(dry_run),
            verbosity=int(verbosity or 0),
        )


class DataShowCommand(CompositeViewMixin, Parser):
    """Print live variable values, one table per profile and kind."""

    class Meta:
        view_format_scope = "all"

    kind = Argument(
        "kind",
        nargs="?",
        default=None,
        help="Kind to print. Omit for every kind that has a matched file.",
    )

    def cli_run(self, config=None, profile=None, kind=None, dry_run=False, **_):
        tables = run_show(config, profile, kind, dry_run=bool(dry_run))
        return _show_view(tables)


def _show_view(tables: tuple[ShowTable, ...]) -> CompositeView:
    sections = []
    for index, table in enumerate(tables):
        title = f"profile {table.profile} kind {table.kind}"
        if table.kind_file:
            title = f"{title} {table.kind_file}"
        sections.append(
            (
                f"{table.profile}-{table.kind}-{index}",
                ListView(list(table.rows)),
                {"title": title},
            )
        )
    return CompositeView(sections)


class DataCommand(Parser):
    """Read and write kind files."""

    feed = Command(DataFeedCommand, help="Fill empty kind-file cells with resolved values")
    prune = Command(
        DataPruneCommand,
        help="Drop empty columns, unmatched rows, or every row",
    )
    show = Command(
        DataShowCommand,
        help="Print live variable values, one table per profile and kind",
    )
