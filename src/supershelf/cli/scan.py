"""`supershelf scan`."""

from __future__ import annotations

from clak import Argument, Command, ListViewMixin, Parser
from clak.comp.views import CompositeViewMixin
from clak.views import CompositeView, ListView

from supershelf.cli.common import kept_path
from supershelf.data import run_feed
from supershelf.kind_file import KindOverrideMode
from supershelf.scan.runs import ShelfRuns, order_scan_row
from supershelf.vars import FileVars

_STRUCTURED_FORMATS = frozenset({"json", "yaml"})

_FILES_COLUMNS = ("input", "path", "status", "mtime", "ctime", "sha256")
_MATCH_COLUMNS = ("path", "kind", "rule", "groups")
_VARS_COLUMNS = ("path", "kind", "vars", "sources")


def _shown_columns(columns: tuple[str, ...], profiles: int) -> tuple[str, ...]:
    """Lead the default columns with profile when more than one profile is selected."""
    if profiles <= 1:
        return columns
    return ("profile", *columns)


def show_profile_first(ctx, columns, profiles: int) -> None:
    """Default columns lead with profile when more than one profile is selected."""
    if profiles <= 1 or columns is not None or ctx is None:
        return
    settings = ctx.plugins.get("view_settings")
    if not isinstance(settings, dict):
        return
    chosen = settings.get("columns")
    if not chosen or "profile" in chosen:
        return
    settings["columns"] = ["profile", *chosen]


def _table_pairs(resolved: FileVars, *, show_all: bool = False) -> tuple[tuple[str, str], ...]:
    """Printed variables in table order: alphabetical by name."""
    visible = list(resolved.items)
    if show_all:
        visible.extend(resolved.facts.items())
    return tuple(sorted(visible))


def present_vars(resolved: FileVars, fmt: str | None, *, show_all: bool = False) -> object:
    """Table text, or the typed mapping for json and yaml."""
    if fmt in _STRUCTURED_FORMATS:
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
        view_columns = _FILES_COLUMNS
        view_column_names = ("profile", *_FILES_COLUMNS)

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
        view_columns = _VARS_COLUMNS
        view_column_names = ("profile", *_VARS_COLUMNS, "input", "sha", "rule")

    path = kept_path()
    kind_overrides_mode = Argument(
        "--kind-overrides-mode",
        help="Kind file mode: auto, manual, always, or disabled.",
    )
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
        show_all=False,
        columns=None,
        ctx=None,
        **_,
    ):
        fmt = ctx.view_settings.get("format") if ctx is not None else None
        if kind_overrides_mode is not None:
            KindOverrideMode.check(kind_overrides_mode, "--kind-overrides-mode")
        runs = ShelfRuns.load(config, profile)
        show_profile_first(ctx, columns, len(runs.shelves))
        walk = runs.changed_resolves(
            path,
            mode=kind_overrides_mode,
            dry_run=bool(dry_run),
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
    kind_overrides_mode = Argument(
        "--kind-overrides-mode",
        help="Kind file mode: auto, manual, always, or disabled.",
    )

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
        if kind_overrides_mode is not None:
            KindOverrideMode.check(kind_overrides_mode, "--kind-overrides-mode")
        return run_feed(
            config,
            profile,
            path,
            mode=kind_overrides_mode,
            dry_run=bool(dry_run),
            verbosity=int(verbosity or 0),
        )


class ScanCommand(CompositeViewMixin, Parser):
    """Scan profile inputs. With no step, run files, kinds, vars, then feeds."""

    kind_overrides_mode = Argument(
        "--kind-overrides-mode",
        help="Kind file mode: auto, manual, always, or disabled.",
    )

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
        if kind_overrides_mode is not None:
            KindOverrideMode.check(kind_overrides_mode, "--kind-overrides-mode")
        fmt = ctx.view_settings.get("format") if ctx is not None else None
        runs = ShelfRuns.load(config, profile)
        dry = bool(dry_run)
        # Resolve in the vars step before the feed write. A resolve error stops here.
        profiles = len(runs.shelves)
        var_rows = variable_rows(
            runs.changed_resolves(path, mode=kind_overrides_mode, dry_run=dry),
            fmt,
            profiles=profiles,
        )
        feed_rows = run_feed(
            config,
            profile,
            path,
            mode=kind_overrides_mode,
            dry_run=dry,
            verbosity=int(verbosity or 0),
        )
        return CompositeView(
            [
                (
                    "files",
                    ListView(
                        list(runs.file_rows(path)),
                        columns=_shown_columns(_FILES_COLUMNS, profiles),
                    ),
                    {"title": "files"},
                ),
                (
                    "kinds",
                    ListView(
                        list(runs.kind_rows(path)),
                        columns=_shown_columns(_MATCH_COLUMNS, profiles),
                    ),
                    {"title": "kinds"},
                ),
                (
                    "vars",
                    ListView(
                        list(var_rows),
                        columns=_shown_columns(_VARS_COLUMNS, profiles),
                    ),
                    {"title": "vars"},
                ),
                ("feeds", ListView(list(feed_rows)), {"title": "feeds"}),
            ]
        )
