"""`supershelf db`."""

from __future__ import annotations

import json

import yaml
from clak import Argument, Command, ListViewMixin, Parser

from supershelf.cli.common import (
    STRUCTURED_FORMATS,
    kept_path,
    show_profile_first,
    shown_columns,
    view_format,
)
from supershelf.database import DocumentRow, ShelfDatabase
from supershelf.profile import ShelfProfile
from supershelf.record import RecordSession
from supershelf.scan.runs import ShelfRuns

_VARS_COLUMNS = ("path", "kind", "vars")
_TABLE_FIXED = ("path", "kind")


def kind_arg() -> Argument:
    """Optional kind shared by db vars and db table."""
    return Argument(
        "kind",
        nargs="?",
        default=None,
        help=(
            "Keep only documents whose match_kind equals this value. "
            "Omit for every document."
        ),
    )


def present_stored_vars(raw: str, fmt: str | None) -> object:
    """One vars cell. Table lines are name, colon, display, sorted by name."""
    shown = stored_var_map(raw)
    if fmt in STRUCTURED_FORMATS:
        return shown
    return "\n".join(f"{name}: {shown[name]}" for name in shown)


def stored_var_map(raw: str) -> dict[str, str]:
    """Display map from a stored vars_json cell, keys sorted."""
    body = json.loads(raw) if raw else {}
    return {
        name: body[name].get("display", "") if isinstance(body[name], dict) else ""
        for name in sorted(body)
    }


def present_vars_yaml(shown: dict[str, str], fmt: str | None) -> object:
    """One vars cell. Table format is YAML text; json/yaml keep the map."""
    if fmt in STRUCTURED_FORMATS:
        return shown
    if not shown:
        return ""
    return yaml.safe_dump(
        shown,
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip("\n")


def document_rows(
    config,
    profile,
    kind: str | None,
) -> tuple[list[ShelfProfile], list[tuple[ShelfProfile, DocumentRow]]]:
    """Load shelves and selected documents. Missing databases contribute no rows."""
    runs = ShelfRuns.load(config, profile)
    selected: list[tuple[ShelfProfile, DocumentRow]] = []
    for shelf in runs.shelves:
        with ShelfDatabase.open_read(shelf.database_file) as database:
            for document in database.documents():
                if kind is not None and document.match_kind != kind:
                    continue
                selected.append((shelf, document))
    return runs.shelves, selected


def order_db_row(row: dict[str, object], *, profiles: int) -> dict[str, object]:
    """Drop profile when one shelf is selected. Keep insertion order otherwise."""
    if profiles <= 1:
        row = {key: value for key, value in row.items() if key != "profile"}
    return row


def set_view_columns(ctx, columns: tuple[str, ...], *, user_columns) -> None:
    """Set the default display columns when the user did not pass --columns."""
    if user_columns is not None or ctx is None:
        return
    settings = ctx.plugins.get("view_settings")
    if not isinstance(settings, dict):
        return
    settings["columns"] = list(columns)


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


class DbVarsCommand(ListViewMixin, Parser):
    """Print path, kind, and stored vars as one YAML cell."""

    class Meta:
        view_columns = _VARS_COLUMNS
        view_column_names = ("profile", *_VARS_COLUMNS)

    kind = kind_arg()

    def cli_run(
        self,
        config=None,
        profile=None,
        kind=None,
        columns=None,
        ctx=None,
        **_,
    ):
        fmt = view_format(ctx)
        shelves, selected = document_rows(config, profile, kind)
        profiles = len(shelves)
        show_profile_first(ctx, columns, profiles)
        rows = []
        for shelf, document in selected:
            shown = stored_var_map(document.vars_json)
            rows.append(
                order_db_row(
                    {
                        "profile": shelf.name,
                        "path": document.path,
                        "kind": document.match_kind,
                        "vars": present_vars_yaml(shown, fmt),
                    },
                    profiles=profiles,
                )
            )
        return rows


class DbTableCommand(ListViewMixin, Parser):
    """Print path, kind, and one column per stored var name."""

    class Meta:
        view_columns = _TABLE_FIXED
        view_column_names = ("profile", *_TABLE_FIXED)

    kind = kind_arg()

    def cli_run(
        self,
        config=None,
        profile=None,
        kind=None,
        columns=None,
        ctx=None,
        **_,
    ):
        shelves, selected = document_rows(config, profile, kind)
        profiles = len(shelves)
        names: set[str] = set()
        prepared: list[tuple[ShelfProfile, DocumentRow, dict[str, str]]] = []
        for shelf, document in selected:
            shown = stored_var_map(document.vars_json)
            names.update(shown)
            prepared.append((shelf, document, shown))
        var_names = tuple(sorted(names))
        default_columns = shown_columns((*_TABLE_FIXED, *var_names), profiles)
        set_view_columns(ctx, default_columns, user_columns=columns)
        show_profile_first(ctx, columns, profiles)
        rows = []
        for shelf, document, shown in prepared:
            row: dict[str, object] = {
                "profile": shelf.name,
                "path": document.path,
                "kind": document.match_kind,
            }
            for name in var_names:
                row[name] = shown.get(name, "")
            rows.append(order_db_row(row, profiles=profiles))
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
    vars = Command(DbVarsCommand, help="Print path, kind, and vars as YAML")
    table = Command(
        DbTableCommand,
        help="Print path, kind, and one column per stored var",
    )


setattr(
    DbCommand,
    "import",
    Command(DbImportCommand, help="Record matched files into the profile database"),
)
