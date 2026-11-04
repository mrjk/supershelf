"""Kind-file feed, prune, and show. The record tables stay untouched."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from supershelf.constants import (
    IDENTITY_HASH,
    KIND_MODE_ALWAYS,
    KIND_MODE_AUTO,
    KIND_MODE_DISABLED,
    KIND_MODE_MANUAL,
    LOGGER_NAME,
    TYPE_DATE,
)
from supershelf.errors import SupershelfError, VarConfigError
from supershelf.kind_file import KindFiles, KindLine, KindTable
from supershelf.profile import ShelfProfile
from supershelf.scan.match import Matcher
from supershelf.scan.runs import ResolvedWalk, ShelfRuns, order_scan_row
from supershelf.scan.walk import InputScanResult, KeptPath
from supershelf.vars import VarCatalog, VarPlan, reserved_var_name


logger = logging.getLogger(LOGGER_NAME)


@dataclass(frozen=True)
class ShowTable:
    """One profile and kind. Rows are display strings. An unset var is blank."""

    profile: str
    kind: str
    kind_file: str | None
    rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class _Resolved:
    profile: str
    index: int
    input_path: Path
    relative: str
    kind: str
    rule: str
    sha: str
    values: Mapping[str, str]
    rule_layer: Mapping[str, str]
    plan: VarPlan


@dataclass(frozen=True)
class _CellWrite:
    table: KindTable
    relative: str
    name: str
    value: str
    sha: str
    profile: str


@dataclass(frozen=True)
class _FeedDrop:
    table: KindTable
    index: int
    path: str
    sha: str
    user_cells: bool
    profile: str


@dataclass
class _KindNotice:
    """Found kind files and inputs that have none, in first-seen order."""

    paths: list[Path]
    missing: list[Path]
    seen: set[Path]


@dataclass(frozen=True)
class _Choice:
    profile: str
    index: int
    input_path: Path
    value: str | None


@dataclass(frozen=True)
class _DroppedRow:
    index: int
    path: str
    sha: str
    user_cells: bool


@dataclass
class _PruneFile:
    table: KindTable
    kind: str
    live_paths: set[str]
    live_hashes: set[str]
    drop_columns: tuple[str, ...]
    drop_rows: tuple[_DroppedRow, ...]
    clear: bool


def run_feed(
    config: str | None,
    profile: str | None,
    path: str | None = None,
    *,
    mode: str | None = None,
    dry_run: bool = False,
    verbosity: int = 0,
    changes_only: bool = True,
) -> list[dict[str, object]]:
    """Write rule-layer display strings into uppercase columns.

    Resolve every selected profile first. A resolve error writes nothing.
    auto and always commit path and hash, then drop, then write feed cells.
    """
    runs = ShelfRuns.load(config, profile)
    prepared = runs.plans(mode=mode, dry_run=dry_run)
    groups = [shelf.scan(quick=False) for shelf in runs.shelves]
    kept = [
        found.path
        for scans in groups
        for scan in scans
        for found in scan.results
    ]
    selector = KeptPath.from_paths(path, kept)
    resolved = _resolve(prepared, selector.narrow(groups))
    _notice_kind_files(resolved)
    if _feeds_disabled(prepared):
        return []
    _reject_feed_conflicts(resolved)
    _commit_identity(prepared, dry_run=dry_run)
    writes, drops = _feed_plan(
        resolved,
        selector,
        verbosity,
        changes_only=changes_only,
    )
    rows = _feed_rows(writes, drops, profiles=len(runs.shelves))
    if not dry_run:
        _apply_feed(writes, drops)
    return rows


def run_prune(
    config: str | None,
    profile: str | None,
    *,
    empty_fields: bool,
    missing: bool,
    clear: bool,
    every: bool,
    force: bool,
    dry_run: bool,
    verbosity: int,
) -> None:
    """Edit existing kind files. This does not render var templates."""
    runs = ShelfRuns.load(config, profile)
    prepared = runs.plans(dry_run=True)
    _require_kind_files(prepared)
    flags = _prune_flags(
        empty_fields=empty_fields,
        missing=missing,
        clear=clear,
        every=every,
    )
    hash_rows = missing and not clear and not every
    files = _prune_files(
        prepared,
        runs.scans(quick=not hash_rows, path=None),
        flags,
        verbosity,
    )
    summary = _prune_summary(flags, files)
    if _confirm(summary, force=force, dry_run=dry_run, changes=bool(files)):
        _apply_prune(files)


def run_show(
    config: str | None,
    profile: str | None,
    kind: str | None,
    *,
    dry_run: bool,
) -> tuple[ShowTable, ...]:
    """Live values, one table per profile and kind. No kind-file write."""
    runs = ShelfRuns.load(config, profile)
    prepared = runs.plans(dry_run=dry_run)
    _require_kind_files(prepared)
    if kind is not None:
        _require_known_kind(prepared, kind)
    groups = runs.scans(quick=False, path=None)
    resolved = _resolve(prepared, groups)
    return _show_tables(prepared, groups, resolved, kind)


def _require_kind_files(prepared: list[tuple[ShelfProfile, Matcher, VarPlan]]) -> None:
    for shelf, _matcher, plan in prepared:
        if plan.kind_files.templates:
            continue
        raise VarConfigError(
            f"Profile {shelf.name} has no kind file",
            advice="kind_overrides_config is empty, so there is no file to use.",
        )


def _require_known_kind(
    prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
    kind: str,
) -> None:
    if any(kind in _known_kinds(matcher, plan.catalog) for _shelf, matcher, plan in prepared):
        return
    raise VarConfigError(
        f"Unknown kind {kind}",
        advice="Use a match rule kind or a kind_schema name.",
    )


def _resolve(
    prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
    groups: list[list[InputScanResult]],
) -> tuple[_Resolved, ...]:
    found: list[_Resolved] = []
    walk = ResolvedWalk(prepared, groups)
    for _shelf, result, walked, matched, resolved, plan in walk:
        found.append(
            _Resolved(
                profile=matched.profile,
                index=matched.index,
                input_path=result.config.path,
                relative=matched.path,
                kind=resolved.kind,
                rule=matched.rule,
                sha=walked.sha256 or "",
                values=dict(resolved.items),
                rule_layer=dict(resolved.rule_layer),
                plan=plan,
            )
        )
    return tuple(found)


def _feeds_disabled(prepared: list[tuple[ShelfProfile, Matcher, VarPlan]]) -> bool:
    return all(plan.kind_files.mode == KIND_MODE_DISABLED for _shelf, _matcher, plan in prepared)


def _notice_kind_files(resolved: tuple[_Resolved, ...]) -> None:
    grouped: dict[tuple[str, str], _KindNotice] = {}
    order: list[tuple[str, str]] = []
    for item in resolved:
        kinds = item.plan.kind_files
        if kinds.mode == KIND_MODE_DISABLED:
            continue
        key = (item.profile, item.kind)
        slot = grouped.get(key)
        if slot is None:
            slot = _KindNotice([], [], set())
            grouped[key] = slot
            order.append(key)
        if item.input_path in slot.seen:
            continue
        slot.seen.add(item.input_path)
        found = kinds.found_path(item.kind, item.input_path)
        if found is None:
            slot.missing.append(item.input_path)
            continue
        if found not in slot.paths:
            slot.paths.append(found)
    for profile, kind in order:
        slot = grouped[(profile, kind)]
        for path in slot.paths:
            logger.notice("Profile %s kind %s kind file %s", profile, kind, path)
        if slot.paths:
            for input_dir in slot.missing:
                logger.notice(
                    "Profile %s kind %s has no config for input %s",
                    profile,
                    kind,
                    input_dir,
                )
            continue
        logger.notice("Profile %s kind %s has no config", profile, kind)


def _reject_feed_conflicts(resolved: tuple[_Resolved, ...]) -> None:
    choices: dict[tuple[Path, str, str], _Choice] = {}
    for item in resolved:
        if item.plan.kind_files.mode == KIND_MODE_DISABLED:
            continue
        names = _feed_names(item)
        if not names:
            continue
        path = item.plan.kind_files.path_for(item.kind, item.input_path)
        if path is None:
            continue
        identity = item.plan.kind_files.identity_for(item.rule)
        row_key = item.sha if identity == IDENTITY_HASH and item.sha else item.relative
        for name in names:
            value = _cell_text(
                item.rule_layer.get(name),
                item.plan.kind_files,
                item.plan.catalog.type_of(item.kind, name),
            )
            key = (path.resolve(), row_key, name)
            previous = choices.get(key)
            if previous is not None and previous.value != value:
                raise VarConfigError(
                    f"Profile {item.profile} path {item.relative} variable {name} "
                    f"differs for input {previous.index} ({previous.input_path}) "
                    f"and input {item.index} ({item.input_path})",
                    advice=(
                        "Two inputs share this kind file and this row. "
                        "Put {{ __input__.path }} in the kind path when they must not share rows."
                    ),
                )
            choices[key] = _Choice(item.profile, item.index, item.input_path, value)


def _commit_identity(
    prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
    *,
    dry_run: bool,
) -> None:
    for _shelf, _matcher, plan in prepared:
        kinds = plan.kind_files
        if kinds.mode not in (KIND_MODE_AUTO, KIND_MODE_ALWAYS):
            continue
        kinds.commit()
        if dry_run:
            kinds.stage_identity()
            continue
        kinds.reload_tables()


def _feed_plan(
    resolved: tuple[_Resolved, ...],
    selector: KeptPath,
    verbosity: int,
    *,
    changes_only: bool = True,
) -> tuple[tuple[_CellWrite, ...], tuple[_FeedDrop, ...]]:
    blocked = _shared_hash_without_row(resolved)
    writes: list[_CellWrite] = []
    tables: list[KindTable] = []
    warned: set[tuple[Path, str]] = set()
    seen_tables: set[int] = set()
    for item in resolved:
        kinds = item.plan.kind_files
        if kinds.mode == KIND_MODE_DISABLED:
            continue
        table = _open_feed_table(item)
        if table is None:
            continue
        if id(table) not in seen_tables:
            seen_tables.add(id(table))
            tables.append(table)
        names = _feed_names(item)
        if not names:
            continue
        identity = kinds.identity_for(item.rule)
        if (table.path.resolve(), item.sha) in blocked and identity == IDENTITY_HASH:
            continue
        found = table.row_for(item.relative, item.sha, identity)
        if found is None:
            if kinds.mode == KIND_MODE_MANUAL:
                continue
            target = item.relative
            create_sha = item.sha
            current: Mapping[str, str] = {}
        else:
            target, current = found
            create_sha = ""
        for name in names:
            value = _cell_text(
                item.rule_layer.get(name),
                kinds,
                item.plan.catalog.type_of(item.kind, name),
            )
            if value is None:
                continue
            column = KindTable.feed_column_name(name)
            if changes_only and current.get(column) == value:
                continue
            if not table.accepts_name(column):
                mark = (table.path, column)
                if mark not in warned:
                    warned.add(mark)
                    logger.warning(
                        "Kind file %s leaves out %s. It is not a legal CSV column.",
                        table.path,
                        column,
                    )
                continue
            if verbosity >= 1:
                logger.info("Would set %s %s to %s in %s", target, column, value, table.path)
            writes.append(_CellWrite(table, target, column, value, create_sha, item.profile))
    drops = [
        drop
        for table in tables
        for drop in _drop_rows(table, resolved, selector)
    ]
    return tuple(writes), tuple(drops)


def _feed_names(item: _Resolved) -> tuple[str, ...]:
    """feeds when set, otherwise the schema names, otherwise printed names."""
    catalog = item.plan.catalog
    schema = catalog.kind_schema(item.kind)
    if schema is not None and schema.feeds is not None:
        return schema.feeds
    shown = tuple(name for name in item.values if not reserved_var_name(name))
    return _defined_names(catalog, item.kind, shown)


def _open_feed_table(item: _Resolved) -> KindTable | None:
    create = item.plan.kind_files.mode == KIND_MODE_ALWAYS
    return item.plan.kind_files.open_table(item.kind, item.input_path, create=create)


def _drop_rows(
    table: KindTable,
    resolved: tuple[_Resolved, ...],
    selector: KeptPath,
) -> list[_FeedDrop]:
    """auto and always only. A path filter keeps rows outside the selection."""
    live_paths: set[str] = set()
    live_hashes: set[str] = set()
    profile = ""
    writable = False
    for item in resolved:
        opened = _open_feed_table(item)
        if opened is None or opened.path.resolve() != table.path.resolve():
            continue
        profile = item.profile
        if item.plan.kind_files.mode in (KIND_MODE_AUTO, KIND_MODE_ALWAYS):
            writable = True
        if item.plan.kind_files.identity_for(item.rule) == IDENTITY_HASH:
            if item.sha:
                live_hashes.add(item.sha)
            continue
        live_paths.add(item.relative)
    if not writable:
        return []
    dropped: list[_FeedDrop] = []
    for index, line in table.unmatched(live_paths, live_hashes):
        if selector.text is not None and not selector.matches(line.path):
            continue
        dropped.append(
            _FeedDrop(table, index, line.path, line.sha, _user_cell(line), profile)
        )
    return dropped


def _user_cell(line: KindLine) -> bool:
    return any(
        value.strip() and not KindTable.is_feed_column(name)
        for name, value in line.cells.items()
    )


def _feed_rows(
    writes: tuple[_CellWrite, ...],
    drops: tuple[_FeedDrop, ...],
    *,
    profiles: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for write in writes:
        rows.append(
            order_scan_row(
                {
                    "profile": write.profile,
                    "path": write.relative,
                    "column": write.name,
                    "value": write.value,
                    "sha": "",
                    "user_cells": "",
                },
                profiles=profiles,
            )
        )
    for drop in drops:
        rows.append(
            order_scan_row(
                {
                    "profile": drop.profile,
                    "path": drop.path,
                    "column": "",
                    "value": "",
                    "sha": drop.sha,
                    "user_cells": "yes" if drop.user_cells else "no",
                },
                profiles=profiles,
            )
        )
    return rows


def _apply_feed(writes: tuple[_CellWrite, ...], drops: tuple[_FeedDrop, ...]) -> None:
    indexes: dict[int, set[int]] = {}
    tables: dict[int, KindTable] = {}
    for drop in drops:
        identity = id(drop.table)
        tables[identity] = drop.table
        indexes.setdefault(identity, set()).add(drop.index)
    for identity, table in tables.items():
        table.drop_indexes(indexes[identity])
    dirty: list[KindTable] = list(tables.values())
    seen = set(tables)
    for write in writes:
        if not write.table.set_cell(write.relative, write.name, write.value, write.sha):
            continue
        identity = id(write.table)
        if identity in seen:
            continue
        seen.add(identity)
        dirty.append(write.table)
    for table in dirty:
        table.save()


def _shared_hash_without_row(resolved: tuple[_Resolved, ...]) -> set[tuple[Path, str]]:
    """Hash-identity files that share a digest and have no row yet."""
    groups: dict[tuple[Path, str], list[str]] = {}
    for item in resolved:
        if item.plan.kind_files.identity_for(item.rule) != IDENTITY_HASH or not item.sha:
            continue
        table = item.plan.kind_files.open_table(item.kind, item.input_path, create=False)
        if table is None or table.missing:
            continue
        if table.row_for(item.relative, item.sha, IDENTITY_HASH) is not None:
            continue
        key = (table.path.resolve(), item.sha)
        paths = groups.setdefault(key, [])
        if item.relative not in paths:
            paths.append(item.relative)
    blocked: set[tuple[Path, str]] = set()
    for (path, digest), paths in groups.items():
        if len(paths) < 2:
            continue
        blocked.add((path, digest))
    return blocked


def _cell_text(display: str | None, kinds: KindFiles, var_type: str) -> str | None:
    if display is None:
        return None
    if var_type == TYPE_DATE:
        return kinds.dates.show(display)
    return display


def _prune_flags(
    *,
    empty_fields: bool,
    missing: bool,
    clear: bool,
    every: bool,
) -> tuple[str, ...]:
    if every:
        return ("empty columns", "missing rows", "clear")
    if not empty_fields and not missing and not clear:
        return ("empty columns",)
    names: list[str] = []
    if empty_fields:
        names.append("empty columns")
    if missing:
        names.append("missing rows")
    if clear:
        names.append("clear")
    return tuple(names)


def _prune_files(
    prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
    groups: list[list[InputScanResult]],
    flags: tuple[str, ...],
    verbosity: int,
) -> tuple[_PruneFile, ...]:
    drop_empty = "empty columns" in flags
    drop_missing = "missing rows" in flags
    clear = "clear" in flags
    files: list[_PruneFile] = []
    for (shelf, matcher, plan), scans in zip(prepared, groups, strict=True):
        grouped: dict[Path, _PruneFile] = {}
        order: list[Path] = []
        kinds = _known_kinds(matcher, plan.catalog)
        for result in scans:
            claimed = matcher.collect(result)
            by_path = {item.path: item for item in result.results}
            for kind in kinds:
                table = plan.kind_files.open_table(kind, result.config.path, create=False)
                if table is None or table.missing or not table.path.is_file():
                    continue
                key = table.path.resolve()
                current = grouped.get(key)
                if current is None:
                    current = _PruneFile(table, kind, set(), set(), (), (), False)
                    grouped[key] = current
                    order.append(key)
                elif current.kind != kind:
                    continue
                for matched in claimed:
                    if matched.kind != kind:
                        continue
                    walked = by_path.get(matched.path)
                    if walked is None:
                        continue
                    if plan.kind_files.identity_for(matched.rule) == IDENTITY_HASH:
                        if walked.sha256:
                            current.live_hashes.add(walked.sha256)
                        continue
                    current.live_paths.add(matched.path)
        for key in order:
            item = grouped[key]
            planned = _plan_prune(
                item,
                plan.catalog,
                drop_empty=drop_empty,
                drop_missing=drop_missing,
                clear=clear,
            )
            if planned is None:
                continue
            if verbosity >= 1:
                _log_prune(planned)
            files.append(planned)
    return tuple(files)


def _plan_prune(
    item: _PruneFile,
    catalog: VarCatalog,
    *,
    drop_empty: bool,
    drop_missing: bool,
    clear: bool,
) -> _PruneFile | None:
    if clear:
        if not item.table.rows and not item.table.raw_rows:
            return None
        return _PruneFile(
            item.table,
            item.kind,
            item.live_paths,
            item.live_hashes,
            (),
            (),
            True,
        )
    columns: tuple[str, ...] = ()
    dropped: tuple[_DroppedRow, ...] = ()
    if drop_empty:
        schema = set(catalog.csv_headers(item.kind))
        columns = tuple(
            name
            for name in item.table.data_columns()
            if name not in schema and not item.table.column_filled(name)
        )
    if drop_missing:
        dropped = tuple(
            _DroppedRow(
                index,
                line.path,
                line.sha,
                any(value.strip() for value in line.cells.values()),
            )
            for index, line in item.table.unmatched(item.live_paths, item.live_hashes)
        )
    if not columns and not dropped:
        return None
    return _PruneFile(
        item.table,
        item.kind,
        item.live_paths,
        item.live_hashes,
        columns,
        dropped,
        False,
    )


def _log_prune(item: _PruneFile) -> None:
    for name in item.drop_columns:
        logger.info("Would drop column %s from %s", name, item.table.path)
    for row in item.drop_rows:
        logger.info("Would drop row %s from %s", row.path, item.table.path)
    if item.clear:
        logger.info("Would clear %s", item.table.path)


def _prune_summary(flags: tuple[str, ...], files: tuple[_PruneFile, ...]) -> str:
    lines = [f"Purges: {', '.join(flags)}."]
    if not files:
        lines.append("No kind file would change.")
    for item in files:
        rows = _listed_rows(item)
        lines.append(
            f"{item.table.path}: {_count(rows, 'row')}, {_count(len(item.drop_columns), 'column')}"
        )
        if item.clear:
            lines.append(f"{item.table.path}: {_count(rows, 'row')} would be cleared")
            continue
        for row in item.drop_rows:
            sha_text = f" SHA {row.sha}" if row.sha else ""
            filled = "user cells" if row.user_cells else "no user cells"
            lines.append(f"drop {row.path}{sha_text}, {filled}")
    return "\n".join(lines) + "\n"


def _apply_prune(files: tuple[_PruneFile, ...]) -> None:
    for item in files:
        if item.clear:
            item.table.clear_rows()
        else:
            if item.drop_rows:
                item.table.drop_indexes({row.index for row in item.drop_rows})
            for name in item.drop_columns:
                item.table.drop_column(name)
        item.table.save()


def _listed_rows(item: _PruneFile) -> int:
    if item.clear:
        raw = item.table.raw_rows
        return len(raw) if raw else len(item.table.rows)
    return len(item.drop_rows)


def _show_tables(
    prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
    groups: list[list[InputScanResult]],
    resolved: tuple[_Resolved, ...],
    kind: str | None,
) -> tuple[ShowTable, ...]:
    grouped: dict[tuple[str, str], list[_Resolved]] = {}
    order: list[tuple[str, str]] = []
    for shelf, matcher, plan in prepared:
        known = _known_kinds(matcher, plan.catalog)
        if kind is None or kind not in known:
            continue
        key = (shelf.name, kind)
        grouped[key] = []
        order.append(key)
    for item in resolved:
        if kind is not None and item.kind != kind:
            continue
        key = (item.profile, item.kind)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(item)
    if kind is None:
        order = [key for key in order if grouped[key]]
    visible = _visible_by_kind(resolved)
    tables: list[ShowTable] = []
    plans = {shelf.name: plan for shelf, _matcher, plan in prepared}
    scans = {
        shelf.name: tuple(group)
        for (shelf, _matcher, _plan), group in zip(prepared, groups, strict=True)
    }
    for profile, kind_name in order:
        plan = plans[profile]
        rows = grouped[(profile, kind_name)]
        columns = _show_columns(
            plan.catalog,
            kind_name,
            visible.get((profile, kind_name), ()),
        )
        body = tuple(_show_row(item, columns) for item in rows)
        tables.append(
            ShowTable(
                profile=profile,
                kind=kind_name,
                kind_file=_kind_path(plan.kind_files, kind_name, scans.get(profile, ())),
                rows=body,
            )
        )
    return tuple(tables)


def _show_columns(catalog: VarCatalog, kind: str, visible: tuple[str, ...]) -> tuple[str, ...]:
    schema = catalog.csv_headers(kind)
    extras = tuple(sorted(name for name in visible if name not in schema))
    return ("path", *schema, *extras)


def _show_row(item: _Resolved, columns: tuple[str, ...]) -> dict[str, str]:
    row = {"path": item.relative}
    for name in columns:
        if name == "path":
            continue
        row[name] = item.values.get(name, "")
    return row


def _kind_path(kinds: KindFiles, kind: str, scans: tuple[InputScanResult, ...]) -> str | None:
    found: list[str] = []
    for result in scans:
        table = kinds.open_table(kind, result.config.path, create=False)
        if table is None or table.missing or not table.path.is_file():
            continue
        text = str(table.path)
        if text not in found:
            found.append(text)
    if not found:
        return None
    return ", ".join(found)


def _visible_by_kind(resolved: tuple[_Resolved, ...]) -> dict[tuple[str, str], tuple[str, ...]]:
    found: dict[tuple[str, str], set[str]] = {}
    for item in resolved:
        names = found.setdefault((item.profile, item.kind), set())
        for name in item.values:
            if reserved_var_name(name):
                continue
            names.add(name)
    return {key: tuple(sorted(names)) for key, names in found.items()}


def _defined_names(catalog: VarCatalog, kind: str, visible: tuple[str, ...]) -> tuple[str, ...]:
    headers = catalog.csv_headers(kind)
    if headers:
        return headers
    return visible


def _known_kinds(matcher: Matcher, catalog: VarCatalog) -> tuple[str, ...]:
    names: list[str] = []
    for _rule, kind, _vars in matcher.rule_vars():
        if kind not in names:
            names.append(kind)
    for schema in catalog.kind_schemas():
        if schema.name not in names:
            names.append(schema.name)
    return tuple(names)


def _confirm(summary: str, *, force: bool, dry_run: bool, changes: bool) -> bool:
    """Ask once on stderr. y or yes writes. Anything else writes nothing."""
    sys.stderr.write(summary)
    sys.stderr.flush()
    if not changes or dry_run:
        return False
    if force:
        return True
    if not sys.stdin.isatty():
        raise SupershelfError(
            "Not a terminal. Pass --force to write kind files.",
            advice="--force skips the question.",
        )
    sys.stderr.write("Continue? [y/N] ")
    sys.stderr.flush()
    answer = sys.stdin.readline().strip().lower()
    return answer in {"y", "yes"}


def _count(number: int, word: str) -> str:
    suffix = "" if number == 1 else "s"
    return f"{number} {word}{suffix}"
