"""`supershelf scan`."""

from __future__ import annotations

from clak import Argument, Command, ListViewMixin, Parser
from clak.comp.views import CompositeViewMixin
from clak.views import CompositeView, ListView

from supershelf.cli.common import (
    FILES_COLUMNS,
    STRUCTURED_FORMATS,
    UNSET_TEXT,
    VARS_COLUMNS,
    kept_path,
    show_profile_first,
    shown_columns,
    view_format,
)
from supershelf.data import run_feed
from supershelf.errors import SupershelfError
from supershelf.kind_file import KindOverrideMode
from supershelf.scan.runs import ShelfRuns, order_scan_row
from supershelf.vars import FileVars

_MATCH_COLUMNS = ("path", "kind", "rule", "groups")


def kind_overrides_flag() -> Argument:
    """Kind file mode shared by vars, feeds, and bare scan."""
    return Argument(
        "--kind-overrides-mode",
        help="Kind file mode: auto, manual, always, or disabled.",
    )


def checked_kind_mode(value: str | None) -> str | None:
    """Reject a bad --kind-overrides-mode. None stays None."""
    if value is not None:
        KindOverrideMode.check(value, "--kind-overrides-mode")
    return value


def overrides_flag() -> Argument:
    """Apply kind-file cells. Default when neither flag is set."""
    return Argument(
        "--overrides",
        action="store_true",
        help="Apply kind-file cells to the printed vars. Default.",
    )


def no_overrides_flag() -> Argument:
    """Skip kind-file cells for scan vars."""
    return Argument(
        "--no-overrides",
        action="store_true",
        help="Skip kind-file cells. Print default_vars and rule vars only.",
    )


def checked_overrides(*, overrides: bool, no_overrides: bool) -> bool:
    """True applies kind cells. Both flags together are a usage error."""
    if overrides and no_overrides:
        raise SupershelfError(
            "Use --overrides or --no-overrides, not both",
            advice="Omit both flags to apply kind-file cells.",
        )
    if no_overrides:
        return False
    return True


def _table_pairs(resolved: FileVars, *, show_all: bool = False) -> tuple[tuple[str, str], ...]:
    """Printed variables in table order: alphabetical by name."""
    visible = [
        (name, UNSET_TEXT if state.value is None else state.display)
        for name, state in resolved.states
    ]
    if show_all:
        visible.extend(resolved.facts.items())
    return tuple(sorted(visible))


def present_vars(resolved: FileVars, fmt: str | None, *, show_all: bool = False) -> object:
    """Table text, or the typed mapping for json and yaml."""
    if fmt in STRUCTURED_FORMATS:
        return resolved.dump_vars(show_all=show_all)
    return "\n".join(
        f"{name}: {value}" for name, value in _table_pairs(resolved, show_all=show_all)
    )


def variable_rows(
    walk,
    fmt: str | None,
    *,
    show_all: bool = False,
    profiles: int,
) -> list[dict[str, object]]:
    """Table rows for a resolved walk. `fmt` selects the vars cell."""
    rows: list[dict[str, object]] = []
    for _shelf, _result, found, matched, resolved, _plan in walk:
        presented = present_vars(resolved, fmt, show_all=show_all)
        row: dict[str, object] = {
            "profile": matched.profile,
            "input": matched.index,
            "path": matched.path,
            "kind": resolved.kind,
            "rule": matched.rule,
            "vars": presented,
            "sha": found.sha256 or "",
        }
        if isinstance(presented, str):
            row["sources"] = present_sources(resolved, show_all=show_all)
        rows.append(order_scan_row(row, profiles=profiles))
    return rows


def present_sources(resolved: FileVars, *, show_all: bool = False) -> str:
    """Source labels for the table, one line per name in present_vars order."""
    return "\n".join(
        ", ".join(resolved.source_labels(name))
        for name, _value in _table_pairs(resolved, show_all=show_all)
    )


class ScanFilesCommand(ListViewMixin, Parser):
    """List file-identity changes against the document database."""

    class Meta:
        view_columns = FILES_COLUMNS
        view_column_names = ("profile", *FILES_COLUMNS)

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, columns=None, ctx=None, **_):
        runs = ShelfRuns.load(config, profile)
        show_profile_first(ctx, columns, len(runs.shelves))
        return runs.file_rows(path)


class ScanMatchCommand(ListViewMixin, Parser):
    """List kind and rule changes, captured groups, and files no rule claims."""

    class Meta:
        view_columns = _MATCH_COLUMNS
        view_column_names = ("profile", *_MATCH_COLUMNS, "input", "status")

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, columns=None, ctx=None, **_):
        runs = ShelfRuns.load(config, profile)
        show_profile_first(ctx, columns, len(runs.shelves))
        return runs.kind_rows(path)


class ScanVarsCommand(ListViewMixin, Parser):
    """List variables for each matched file."""

    class Meta:
        view_columns = VARS_COLUMNS
        view_column_names = ("profile", *VARS_COLUMNS, "input", "sha", "rule")

    path = kept_path()
    kind_overrides_mode = kind_overrides_flag()
    overrides = overrides_flag()
    no_overrides = no_overrides_flag()
    show_all = Argument(
        "--all",
        action="store_true",
        help="Include internal variables in the vars column.",
    )

    def cli_run(
        self,
        config=None,
        profile=None,
        path=None,
        dry_run=False,
        kind_overrides_mode=None,
        overrides=False,
        no_overrides=False,
        show_all=False,
        columns=None,
        ctx=None,
        **_,
    ):
        fmt = view_format(ctx)
        mode = checked_kind_mode(kind_overrides_mode)
        apply_overrides = checked_overrides(
            overrides=bool(overrides),
            no_overrides=bool(no_overrides),
        )
        runs = ShelfRuns.load(config, profile)
        show_profile_first(ctx, columns, len(runs.shelves))
        walk = runs.changed_resolves(
            path,
            mode=mode,
            dry_run=bool(dry_run),
            overrides=apply_overrides,
        )
        return variable_rows(
            walk,
            fmt,
            show_all=bool(show_all),
            profiles=len(runs.shelves),
        )


class ScanFeedsCommand(ListViewMixin, Parser):
    """Write rule-layer values into the uppercase kind-file columns."""

    path = kept_path()
    kind_overrides_mode = kind_overrides_flag()

    def cli_run(
        self,
        config=None,
        profile=None,
        path=None,
        dry_run=False,
        kind_overrides_mode=None,
        verbosity=0,
        **_,
    ):
        return run_feed(
            config,
            profile,
            path,
            mode=checked_kind_mode(kind_overrides_mode),
            dry_run=bool(dry_run),
            verbosity=int(verbosity or 0),
        )


class ScanCommand(CompositeViewMixin, Parser):
    """Scan profile inputs. With no step, run files, kinds, vars, then feeds."""

    kind_overrides_mode = kind_overrides_flag()

    files = Command(ScanFilesCommand, help="List file-identity changes")
    match = Command(
        ScanMatchCommand,
        help="List kind and rule changes, and captured groups",
    )
    vars = Command(ScanVarsCommand, help="List variable changes for each matched file")
    feeds = Command(ScanFeedsCommand, help="Write rule-layer values into kind files")

    def cli_run(
        self,
        config=None,
        profile=None,
        path=None,
        dry_run=False,
        kind_overrides_mode=None,
        verbosity=0,
        ctx=None,
        **_,
    ):
        mode = checked_kind_mode(kind_overrides_mode)
        fmt = view_format(ctx)
        runs = ShelfRuns.load(config, profile)
        dry = bool(dry_run)
        profiles = len(runs.shelves)
        # One list for every step. Resolve before the feed write.
        runs.check_identity()
        selection = runs.open_selection(path, quick=False, require_kept=True)
        runs.apply_match(selection)
        runs.apply_files(selection, log=False)
        runs.apply_vars(selection, mode=mode, dry_run=dry)
        var_rows = variable_rows(
            runs.changed_resolves(
                path,
                mode=mode,
                dry_run=dry,
                selection=selection,
            ),
            fmt,
            profiles=profiles,
        )
        feed_rows = run_feed(
            config,
            profile,
            path,
            mode=mode,
            dry_run=dry,
            verbosity=int(verbosity or 0),
            selection=selection,
        )
        return CompositeView(
            [
                (
                    "files",
                    ListView(
                        list(runs.file_rows(path, selection=selection)),
                        columns=shown_columns(FILES_COLUMNS, profiles),
                    ),
                    {"title": "files"},
                ),
                (
                    "kinds",
                    ListView(
                        list(runs.kind_rows(path, selection=selection)),
                        columns=shown_columns(_MATCH_COLUMNS, profiles),
                    ),
                    {"title": "kinds"},
                ),
                (
                    "vars",
                    ListView(
                        list(var_rows),
                        columns=shown_columns(VARS_COLUMNS, profiles),
                    ),
                    {"title": "vars"},
                ),
                ("feeds", ListView(list(feed_rows)), {"title": "feeds"}),
            ]
        )
