"""Kind-file feed. The record tables stay untouched."""

from __future__ import annotations

import logging
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
from supershelf.errors import VarConfigError
from supershelf.kind_file import KindFiles, KindLine, KindTable
from supershelf.profile import ShelfProfile
from supershelf.scan.match import Matcher
from supershelf.scan.runs import ShelfRuns, order_scan_row
from supershelf.scan.selection import FileSelection
from supershelf.scan.walk import KeptPath
from supershelf.vars import VarPlan


logger = logging.getLogger(LOGGER_NAME)


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


def run_feed(
    config: str | None,
    profile: str | None,
    path: str | None = None,
    *,
    mode: str | None = None,
    dry_run: bool = False,
    verbosity: int = 0,
    changes_only: bool = True,
    selection: FileSelection | None = None,
) -> list[dict[str, object]]:
    """Write rule-layer display strings into uppercase columns.

    Resolve every selected profile first. A resolve error writes nothing.
    auto and always commit path and hash, then drop, then write feed cells.
    A passed ``selection`` is not walked again.
    """
    if selection is None:
        runs = ShelfRuns.load(config, profile)
        selection = runs.use_selection(path, None, quick=False, require_kept=True)
        runs.apply_match(selection)
        runs.apply_vars(selection, mode=mode, dry_run=dry_run)
    else:
        runs = ShelfRuns(selection.shelves)
        selection = runs.use_selection(path, selection, quick=False, require_kept=False)
        if not selection.vars_ready:
            runs.apply_match(selection)
            runs.apply_vars(selection, mode=mode, dry_run=dry_run)
    prepared = selection.prepared
    resolved = _resolved_from(selection)
    selector = selection.selector
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


def _resolved_from(selection: FileSelection) -> tuple[_Resolved, ...]:
    """Matched files already resolved on ``selection``, in walk order."""
    found: list[_Resolved] = []
    for item in selection.inventory:
        if item.match is None or item.resolved is None or item.var_plan is None:
            continue
        found.append(
            _Resolved(
                profile=item.profile,
                index=item.index,
                input_path=item.result.config.path,
                relative=item.found.path,
                kind=item.resolved.kind,
                rule=item.match.rule,
                sha=item.found.sha256 or "",
                values=dict(item.resolved.items),
                rule_layer=dict(item.resolved.rule_layer),
                plan=item.var_plan,
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
                item.values.get(name),
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
                item.values.get(name),
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
    """The kind's feeds list. Omitted or empty writes no uppercase columns."""
    schema = item.plan.catalog.kind_schema(item.kind)
    if schema is None or not schema.feeds:
        return ()
    return schema.feeds


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

