"""Kind-file feed, prune, and show. The record tables stay untouched."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from supershelf.constants import INTERNAL_NAMES, LOGGER_NAME, VAR_DATE
from supershelf.errors import SupershelfError, VarConfigError
from supershelf.kind_file import KindFiles, KindTable
from supershelf.match import Matcher
from supershelf.profile import ShelfProfile
from supershelf.runs import ResolvedWalk, ShelfRuns
from supershelf.scan import InputScanResult
from supershelf.var_schema import VarCatalog
from supershelf.vars import VarPlan


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
    values: Mapping[str, str]
    plan: VarPlan


@dataclass(frozen=True)
class _CellWrite:
    table: KindTable
    relative: str
    name: str
    value: str


@dataclass(frozen=True)
class _Choice:
    profile: str
    index: int
    input_path: Path
    value: str | None


@dataclass
class _PruneFile:
    table: KindTable
    kind: str
    matched: set[str]
    drop_columns: tuple[str, ...]
    drop_paths: tuple[str, ...]
    clear: bool


def run_feed(
    config: str | None,
    profile: str | None,
    names: str | None,
    *,
    kind: str | None,
    var: str | None,
    force: bool,
    dry_run: bool,
    verbosity: int,
) -> None:
    """Fill empty selected cells. The prompt guards the kind-file write only."""
    runs = ShelfRuns.load(config, profile)
    prepared = runs.plans(dry_run=dry_run)
    _require_kind_files(prepared)
    kind_names, var_names = _feed_selectors(prepared, names, kind, var)
    resolved = _resolve(prepared, runs.scans(quick=False, path=None))
    selected_kinds, selected_vars, per_kind = _feed_selection(
        prepared,
        resolved,
        kind_names,
        var_names,
    )
    writes = _feed_writes(resolved, per_kind, verbosity)
    summary = _feed_summary(selected_kinds, selected_vars, writes)
    if _confirm(summary, force=force, dry_run=dry_run, changes=bool(writes)):
        _apply_writes(writes)


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
    files = _prune_files(prepared, runs.scans(quick=True, path=None), flags, verbosity)
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
    for _shelf, result, _file, matched, resolved, plan in walk:
        found.append(
            _Resolved(
                profile=matched.profile,
                index=matched.index,
                input_path=result.config.path,
                relative=matched.path,
                kind=resolved.kind,
                values=dict(resolved.items),
                plan=plan,
            )
        )
    return tuple(found)


def _feed_selectors(
    prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
    names: str | None,
    kind: str | None,
    var: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    kinds: list[str] = []
    variables: list[str] = []
    for token in _split_names(names):
        kind_hit, var_hit = _classify(prepared, token)
        if kind_hit and var_hit:
            raise VarConfigError(
                f"{token} is a kind and a var",
                advice="Pass --kind or --var to choose which one.",
            )
        if kind_hit:
            kinds.append(token)
            continue
        if var_hit:
            _reject_internal(token, "names")
            variables.append(token)
            continue
        raise VarConfigError(
            f"{token} is not a kind or a var",
            advice="Use a match rule kind, a kind_schema name, or a var name.",
        )
    for token in _split_names(kind):
        if not any(token in _known_kinds(matcher, plan.catalog) for _shelf, matcher, plan in prepared):
            raise VarConfigError(
                f"Unknown kind {token}",
                advice="Use a match rule kind or a kind_schema name.",
            )
        kinds.append(token)
    for token in _split_names(var):
        _reject_internal(token, "--var")
        if not any(_is_var(plan.catalog, token) for _shelf, _matcher, plan in prepared):
            raise VarConfigError(
                f"Unknown var {token}",
                advice="Use a declared name, a rule var, or __date__.",
            )
        variables.append(token)
    return tuple(_unique(kinds)), tuple(_unique(variables))


def _feed_selection(
    prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
    resolved: tuple[_Resolved, ...],
    kind_names: tuple[str, ...],
    var_names: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], dict[tuple[str, str], tuple[str, ...]]]:
    visible = _visible_by_kind(resolved)
    matched = _matched_kinds(resolved)
    per_kind: dict[tuple[str, str], tuple[str, ...]] = {}
    selected_kinds: list[str] = []
    selected_vars: list[str] = []
    defined_union: set[str] = set()
    for shelf, matcher, plan in prepared:
        known = _known_kinds(matcher, plan.catalog)
        if kind_names:
            kinds = tuple(name for name in kind_names if name in known)
        else:
            kinds = tuple(name for name in matched.get(shelf.name, ()) if name in known)
        for kind in kinds:
            defined = _defined_names(plan.catalog, kind, visible.get((shelf.name, kind), ()))
            chosen = defined if not var_names else tuple(name for name in defined if name in var_names)
            per_kind[(shelf.name, kind)] = chosen
            if kind not in selected_kinds:
                selected_kinds.append(kind)
            defined_union.update(defined)
            for name in chosen:
                if name not in selected_vars:
                    selected_vars.append(name)
    if var_names:
        missing = next((name for name in var_names if name not in defined_union), None)
        if missing is not None:
            raise VarConfigError(
                f"{missing} is not defined by the selected kinds",
                advice="Choose a var those kinds define, or omit --kind.",
            )
    return tuple(selected_kinds), tuple(selected_vars), per_kind


def _feed_writes(
    resolved: tuple[_Resolved, ...],
    per_kind: dict[tuple[str, str], tuple[str, ...]],
    verbosity: int,
) -> tuple[_CellWrite, ...]:
    choices: dict[tuple[Path, str, str], _Choice] = {}
    writes: list[_CellWrite] = []
    warned: set[tuple[Path, str]] = set()
    for item in resolved:
        names = per_kind.get((item.profile, item.kind), ())
        if not names:
            continue
        table = item.plan.kind_files.open_table(item.kind, item.input_path, create=True)
        if table is None:
            continue
        current = table.rows.get(item.relative, {})
        for name in names:
            value = _cell_text(name, item.values.get(name), item.plan.kind_files)
            key = (table.path.resolve(), item.relative, name)
            previous = choices.get(key)
            if previous is not None and previous.value != value:
                raise VarConfigError(
                    f"Profile {item.profile} path {item.relative} variable {name} "
                    f"differs for input {previous.index} ({previous.input_path}) "
                    f"and input {item.index} ({item.input_path})",
                    advice=(
                        "Two inputs share this kind file and this relative path. "
                        "Put {{ __input__.path }} in the kind path when they must not share rows."
                    ),
                )
            choices[key] = _Choice(item.profile, item.index, item.input_path, value)
            if value is None or name in current:
                continue
            if not table.accepts_name(name):
                mark = (table.path, name)
                if mark not in warned:
                    warned.add(mark)
                    logger.warning(
                        "Kind file %s leaves out %s. It is not a legal CSV column.",
                        table.path,
                        name,
                    )
                continue
            if verbosity >= 1:
                logger.info(
                    "Would set %s %s to %s in %s",
                    item.relative,
                    name,
                    value,
                    table.path,
                )
            writes.append(_CellWrite(table, item.relative, name, value))
    return tuple(writes)


def _cell_text(name: str, display: str | None, kinds: KindFiles) -> str | None:
    if display is None:
        return None
    if name == VAR_DATE:
        return kinds.dates.show(display)
    return display


def _feed_summary(
    kinds: tuple[str, ...],
    variables: tuple[str, ...],
    writes: tuple[_CellWrite, ...],
) -> str:
    kind_text = ", ".join(kinds) if kinds else "(none)"
    var_text = ", ".join(variables) if variables else "(none)"
    lines = [
        f"Selected kinds: {kind_text}. Selected vars: {var_text}.",
        "Writes those resolved values into empty cells. A filled cell stays.",
    ]
    counts: dict[Path, int] = {}
    order: list[Path] = []
    for write in writes:
        if write.table.path not in counts:
            order.append(write.table.path)
            counts[write.table.path] = 0
        counts[write.table.path] += 1
    if not order:
        lines.append("No kind file would change.")
    for path in order:
        lines.append(f"{path}: {_count(counts[path], 'cell')}")
    return "\n".join(lines) + "\n"


def _apply_writes(writes: tuple[_CellWrite, ...]) -> None:
    tables: list[KindTable] = []
    seen: set[int] = set()
    for write in writes:
        if not write.table.set_cell(write.relative, write.name, write.value):
            continue
        identity = id(write.table)
        if identity in seen:
            continue
        seen.add(identity)
        tables.append(write.table)
    for table in tables:
        table.save()


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
            matched = _matches_by_kind(matcher, result)
            for kind in kinds:
                table = plan.kind_files.open_table(kind, result.config.path, create=False)
                if table is None or table.missing or not table.path.is_file():
                    continue
                key = table.path.resolve()
                current = grouped.get(key)
                if current is None:
                    current = _PruneFile(table, kind, set(), (), (), False)
                    grouped[key] = current
                    order.append(key)
                elif current.kind != kind:
                    continue
                current.matched.update(matched.get(kind, set()))
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
        return _PruneFile(item.table, item.kind, item.matched, (), tuple(item.table.rows), True)
    columns: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    if drop_empty:
        schema = set(catalog.csv_headers(item.kind))
        columns = tuple(
            name
            for name in item.table.data_columns()
            if name not in schema and not item.table.column_filled(name)
        )
    if drop_missing:
        paths = tuple(path for path in item.table.rows if path not in item.matched)
    if not columns and not paths:
        return None
    return _PruneFile(item.table, item.kind, item.matched, columns, paths, False)


def _log_prune(item: _PruneFile) -> None:
    for name in item.drop_columns:
        logger.info("Would drop column %s from %s", name, item.table.path)
    for path in item.drop_paths:
        logger.info("Would drop row %s from %s", path, item.table.path)
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
    return "\n".join(lines) + "\n"


def _apply_prune(files: tuple[_PruneFile, ...]) -> None:
    for item in files:
        if item.clear:
            item.table.clear_rows()
        else:
            if item.drop_paths:
                item.table.drop_paths(set(item.drop_paths))
            for name in item.drop_columns:
                item.table.drop_column(name)
        item.table.save()


def _listed_rows(item: _PruneFile) -> int:
    raw = item.table.raw_rows
    if item.clear:
        return len(raw) if raw else len(item.table.rows)
    if not item.drop_paths:
        return 0
    dropped = set(item.drop_paths)
    if raw:
        return sum(1 for path, _cells in raw if path in dropped)
    return len(item.drop_paths)


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


def _matches_by_kind(matcher: Matcher, result: InputScanResult) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for matched in matcher.collect(result):
        found.setdefault(matched.kind, set()).add(matched.path)
    return found


def _visible_by_kind(resolved: tuple[_Resolved, ...]) -> dict[tuple[str, str], tuple[str, ...]]:
    found: dict[tuple[str, str], set[str]] = {}
    for item in resolved:
        names = found.setdefault((item.profile, item.kind), set())
        for name in item.values:
            if name in INTERNAL_NAMES:
                continue
            names.add(name)
    return {key: tuple(sorted(names)) for key, names in found.items()}


def _matched_kinds(resolved: tuple[_Resolved, ...]) -> dict[str, tuple[str, ...]]:
    found: dict[str, list[str]] = {}
    for item in resolved:
        names = found.setdefault(item.profile, [])
        if item.kind not in names:
            names.append(item.kind)
    return {profile: tuple(names) for profile, names in found.items()}


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


def _classify(
    prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
    token: str,
) -> tuple[bool, bool]:
    kind_hit = False
    var_hit = False
    for _shelf, matcher, plan in prepared:
        if token in _known_kinds(matcher, plan.catalog):
            kind_hit = True
        if _is_var(plan.catalog, token):
            var_hit = True
    return kind_hit, var_hit


def _is_var(catalog: VarCatalog, name: str) -> bool:
    if name in catalog:
        return True
    return any(name in schema.vars for schema in catalog.kind_schemas())


def _reject_internal(name: str, label: str) -> None:
    if name not in INTERNAL_NAMES:
        return
    raise VarConfigError(
        f"{label} cannot select {name}",
        advice="Internal names stay out. __date__ is allowed.",
    )


def _split_names(text: str | None) -> tuple[str, ...]:
    if text is None:
        return ()
    parts = tuple(part.strip() for part in text.split(","))
    if any(part == "" for part in parts):
        raise VarConfigError(
            "A name list has an empty item",
            advice="Separate names with commas. Spaces around commas are ignored.",
        )
    return parts


def _unique(names: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


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
