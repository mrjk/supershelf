"""Load profiles, walk inputs, match kinds, and resolve variables."""

from __future__ import annotations

import logging
import os

from supershelf.configs import ShelfConfigs
from supershelf.constants import (
    EVENT_NEW,
    EVENT_OUTPUT,
    EVENT_UNMATCHED,
    LOGGER_NAME,
    STATUS_UNCHANGED,
)
from supershelf.database import ShelfDatabase
from supershelf.profile import ShelfProfile
from supershelf.scan.match import FileMatch, Matcher
from supershelf.scan.selection import (
    FILE_CHANGE_STATUSES,
    KIND_CHANGE_STATUSES,
    FileSelection,
    SelectedFile,
    selection_from_groups,
)
from supershelf.scan.walk import InputScanResult, KeptPath
from supershelf.vars import VarPlan

_SCAN_PREFIX = ("profile", "input", "sha", "path", "status")


def order_scan_row(row: dict[str, object], *, profiles: int) -> dict[str, object]:
    """Scan stdout order. profile is included only when more than one is selected."""
    source = dict(row)
    if profiles <= 1:
        source.pop("profile", None)
    ordered: dict[str, object] = {}
    for key in _SCAN_PREFIX:
        if key not in source:
            continue
        ordered[key] = source.pop(key)
    ordered.update(source)
    return ordered


_KIND_STATUS = "kind"
_RULE_STATUS = "rule"


class ShelfRuns:
    """Profiles loaded for one scan command."""

    def __init__(self, shelves: list[ShelfProfile]) -> None:
        self.shelves = shelves
        self._identity: (
            dict[str, tuple[tuple[str, ...], dict[str, tuple[str, ...]]]] | None
        ) = None

    @classmethod
    def load(cls, config: str | None, profile: str | None) -> ShelfRuns:
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        return cls([ShelfProfile.from_config(item) for item in loaded.config_list])

    def check_identity(
        self,
    ) -> dict[str, tuple[tuple[str, ...], dict[str, tuple[str, ...]]]]:
        """Resolve record_identity for every profile. Raises before any walk."""
        if self._identity is not None:
            return self._identity
        from supershelf.record import RecordIdentity

        checked: dict[str, tuple[tuple[str, ...], dict[str, tuple[str, ...]]]] = {}
        for shelf in self.shelves:
            steps = RecordIdentity.resolve(
                shelf.config_section(shelf.document),
                None,
                os.environ,
            )
            rules = RecordIdentity.rule_lists(shelf.document, shelf.name, steps)
            checked[shelf.name] = (steps, rules)
        self._identity = checked
        return checked

    def scans(self, *, quick: bool, path: str | None):
        groups = [shelf.scan(quick=quick) for shelf in self.shelves]
        return KeptPath.narrow_groups(groups, path)

    def open_selection(
        self,
        path: str | None,
        *,
        quick: bool,
        require_kept: bool,
        allow_document: bool = False,
    ) -> FileSelection:
        """Walk once. ``PATH`` filters the inventory."""
        groups = [shelf.scan(quick=quick) for shelf in self.shelves]
        return selection_from_groups(
            self.shelves,
            groups,
            path,
            hashed=not quick,
            require_kept=require_kept,
            allow_document=allow_document,
            in_scope=self._path_is_in_scope,
        )

    def use_selection(
        self,
        path: str | None,
        selection: FileSelection | None,
        *,
        quick: bool,
        require_kept: bool,
        allow_document: bool = False,
    ) -> FileSelection:
        """Use ``selection`` when given. Otherwise walk. ``PATH`` intersects either source."""
        if selection is None:
            return self.open_selection(
                path,
                quick=quick,
                require_kept=require_kept,
                allow_document=allow_document,
            )
        chosen = selection.intersect(path, require_kept=require_kept)
        if not quick:
            chosen.ensure_hashed()
        return chosen

    def matched(self) -> list[tuple[ShelfProfile, Matcher]]:
        return [
            (shelf, Matcher.from_document(shelf.document, shelf.name))
            for shelf in self.shelves
        ]

    def plans(
        self,
        *,
        mode: str | None = None,
        dry_run: bool = False,
    ) -> list[tuple[ShelfProfile, Matcher, VarPlan]]:
        """One matcher and var plan per profile. Does not walk."""
        prepared: list[tuple[ShelfProfile, Matcher, VarPlan]] = []
        for shelf in self.shelves:
            matcher = Matcher.from_document(shelf.document, shelf.name)
            prepared.append(
                (
                    shelf,
                    matcher,
                    VarPlan.from_document(
                        shelf.document,
                        shelf.name,
                        matcher,
                        shelf.root_dir,
                        shelf.scope,
                        mode=mode,
                        dry_run=dry_run,
                    ),
                )
            )
        return prepared

    def apply_files(
        self,
        selection: FileSelection,
        *,
        log: bool,
    ) -> FileSelection:
        """Annotate identity on every kept file. The inventory stays intact."""
        if selection.files_ready:
            if log:
                self._log_file_warnings(selection)
            return selection
        if not selection.match_ready:
            self.apply_match(selection)
        selection.ensure_hashed()
        from supershelf.record import LiveFile, RecordPlan

        identity = self.check_identity()
        for shelf, scans in zip(selection.shelves, selection.groups, strict=True):
            profile_steps, rules = identity[shelf.name]
            walked = {str(result.config.path) for result in scans}
            ignored = set(selection.ignored.get(shelf.name, ()))
            kept: set[tuple[str, str]] = set()
            live: list[LiveFile] = []
            seen: list[SelectedFile] = []
            with ShelfDatabase.open_read(shelf.database_file) as database:
                documents = database.documents()
                stored_at = {
                    (document.input_path, document.path): document
                    for document in documents
                }
                prior: dict[int, str] = {}
                for event in database.events():
                    if event.event == EVENT_OUTPUT:
                        continue
                    prior[event.document_id] = event.identity
            for item in selection.inventory:
                if item.profile != shelf.name:
                    continue
                if item.location() in ignored:
                    continue
                kept.add(item.location())
                seen.append(item)
                hit = item.match
                if hit is None or not item.found.sha256:
                    continue
                rule_steps = rules.get(hit.rule, profile_steps)
                document = stored_at.get(item.location())
                if document is None:
                    live.append(
                        LiveFile.from_match(
                            item.result,
                            item.found,
                            kind=hit.kind,
                            rule=hit.rule,
                            snapshot="{}",
                            steps=rule_steps,
                        )
                    )
                    continue
                live.append(
                    LiveFile(
                        input_index=item.index,
                        input_path=str(item.result.config.path),
                        path=item.found.path,
                        hash=item.found.sha256,
                        mtime=item.found.mtime,
                        ctime=item.found.ctime,
                        match_kind=document.match_kind,
                        rule=document.rule,
                        file_dir=document.file_dir,
                        file_name=document.file_name,
                        file_stem=document.file_stem,
                        file_ext=document.file_ext,
                        vars_json=document.vars_json,
                        steps=rule_steps,
                    )
                )
            plan = RecordPlan(
                documents,
                live,
                kept,
                walked,
                selection.selector,
                rules,
                prior,
                ignored,
                profile=shelf.name,
            )
            planned = plan.rows()
            selection.planned[shelf.name] = planned
            selection.seen[shelf.name] = seen
            selection.warnings[shelf.name] = list(plan.warnings)
            by_location = {
                (row.file.input_path, row.file.path): row.status for row in planned
            }
            for item in seen:
                item.identity_status = by_location.get(item.location())
        selection.files_ready = True
        if log:
            self._log_file_warnings(selection)
        return selection

    def apply_match(self, selection: FileSelection) -> FileSelection:
        """Annotate kind and rule on the inventory. Unmatched files are warned once."""
        if selection.match_ready:
            return selection
        for shelf, scans in zip(selection.shelves, selection.groups, strict=True):
            matcher = Matcher.from_document(shelf.document, shelf.name)
            claimed: dict[tuple[int, str], FileMatch] = {}
            for result in scans:
                for hit in matcher.collect(result):
                    claimed[(result.index, hit.path)] = hit
            with ShelfDatabase.open_read(shelf.database_file) as database:
                stored_at = {
                    (document.input_path, document.path): document
                    for document in database.documents()
                }
            for item in selection.inventory:
                if item.profile != shelf.name:
                    continue
                hit = claimed.get((item.index, item.found.path))
                document = stored_at.get(item.location())
                if hit is None:
                    item.kind_status = EVENT_UNMATCHED
                    continue
                item.match = hit
                if document is None:
                    item.kind_status = EVENT_NEW
                elif document.match_kind != hit.kind:
                    item.kind_status = _KIND_STATUS
                elif document.rule != hit.rule:
                    item.kind_status = _RULE_STATUS
                else:
                    item.kind_status = STATUS_UNCHANGED
        selection.match_ready = True
        return selection

    def apply_vars(
        self,
        selection: FileSelection,
        *,
        mode: str | None = None,
        dry_run: bool = False,
        overrides: bool | None = None,
    ) -> FileSelection:
        """Resolve every matched file. The working list stays the provided subset.

        ``overrides`` is None for bare scan and import. Scan vars passes True or False.
        """
        if not selection.match_ready:
            self.apply_match(selection)
        if selection.vars_ready:
            return selection
        prepared = self.plans(mode=mode, dry_run=dry_run)
        by_name = {shelf.name: plan for shelf, _matcher, plan in prepared}
        stored: dict[str, dict[tuple[str, str], str]] = {}
        for shelf in selection.shelves:
            with ShelfDatabase.open_read(shelf.database_file) as database:
                stored[shelf.name] = {
                    (document.input_path, document.path): document.vars_json
                    for document in database.documents()
                }
        for item in selection.inventory:
            if item.match is None:
                continue
            plan = by_name[item.profile]
            resolved = plan.resolve(
                item.found,
                item.match,
                item.result.config.path,
                overrides=overrides,
            )
            item.resolved = resolved
            item.var_plan = plan
            previous = stored.get(item.profile, {}).get(item.location())
            item.vars_changed = previous is None or previous != plan.snapshot(resolved)
        selection.prepared = prepared
        selection.vars_ready = True
        return selection

    def file_rows(
        self,
        path: str | None,
        *,
        changes_only: bool = True,
        selection: FileSelection | None = None,
    ) -> list[dict[str, object]]:
        """Identity changes. Does not resolve variables or create the database."""
        if selection is None:
            self.check_identity()
        chosen = self.use_selection(
            path,
            selection,
            quick=False,
            require_kept=False,
            allow_document=selection is None,
        )
        self.apply_files(chosen, log=True)
        return self._file_table(chosen, changes_only=changes_only)

    def _file_table(
        self,
        selection: FileSelection,
        *,
        changes_only: bool,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for shelf in selection.shelves:
            planned = selection.planned.get(shelf.name, [])
            shown: list[dict[str, object]] = []
            for row in planned:
                if not selection.selector.matches(row.file.path):
                    continue
                if changes_only and row.status not in FILE_CHANGE_STATUSES:
                    continue
                shown.append(self._file_row(shelf, row.file, row.status))
            if not changes_only:
                emitted = {(row["input"], row["path"]) for row in shown}
                for item in selection.seen.get(shelf.name, []):
                    if not selection.selector.matches(item.found.path):
                        continue
                    if (item.index, item.found.path) in emitted:
                        continue
                    found = item.found
                    shown.append(
                        {
                            "profile": shelf.name,
                            "input": item.index,
                            "path": found.path,
                            "status": EVENT_UNMATCHED,
                            "mtime": shelf.show_time(found.mtime or "") if found.mtime else "",
                            "ctime": shelf.show_time(found.ctime or "") if found.ctime else "",
                            "sha256": found.sha256 or "",
                        }
                    )
            rows.extend(shown)
        profiles = len(selection.shelves)
        return [order_scan_row(row, profiles=profiles) for row in rows]

    def _log_file_warnings(self, selection: FileSelection) -> None:
        if selection.file_warnings_logged:
            return
        logger = logging.getLogger(LOGGER_NAME)
        for shelf in selection.shelves:
            for message in selection.warnings.get(shelf.name, []):
                logger.warning("%s", message)
        selection.file_warnings_logged = True

    @staticmethod
    def _file_row(shelf: ShelfProfile, file, status: str) -> dict[str, object]:
        shown_mtime = file.mtime or ""
        shown_ctime = file.ctime or ""
        return {
            "profile": shelf.name,
            "input": file.input_index,
            "path": file.path,
            "status": status,
            "mtime": shelf.show_time(shown_mtime) if shown_mtime else "",
            "ctime": shelf.show_time(shown_ctime) if shown_ctime else "",
            "sha256": file.hash,
        }

    def kind_rows(
        self,
        path: str | None,
        *,
        changes_only: bool = True,
        selection: FileSelection | None = None,
    ) -> list[dict[str, object]]:
        """Kind and rule changes, captured groups, and unmatched files. Does not hash."""
        chosen = self.use_selection(
            path,
            selection,
            quick=True,
            require_kept=selection is None,
        )
        self.apply_match(chosen)
        return self._kind_table(chosen, changes_only=changes_only)

    def _kind_table(
        self,
        selection: FileSelection,
        *,
        changes_only: bool,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for item in selection.inventory:
            status = item.kind_status
            if status is None:
                continue
            if status == EVENT_UNMATCHED:
                rows.append(
                    self._kind_row(
                        item.profile,
                        item.index,
                        item.found.path,
                        "",
                        "",
                        EVENT_UNMATCHED,
                        {},
                    )
                )
                continue
            if changes_only and status == STATUS_UNCHANGED:
                continue
            matched = item.match
            if matched is None:
                continue
            rows.append(
                self._kind_row(
                    item.profile,
                    item.index,
                    item.found.path,
                    matched.kind,
                    matched.rule,
                    status,
                    matched.groups,
                )
            )
        profiles = len(selection.shelves)
        return [order_scan_row(row, profiles=profiles) for row in rows]

    def changed_resolves(
        self,
        path: str | None,
        *,
        mode: str | None = None,
        dry_run: bool = False,
        overrides: bool | None = None,
        changes_only: bool = True,
        provided_only: bool = True,
        selection: FileSelection | None = None,
    ):
        """Vars for files the earlier steps provide. Inspect passes ``provided_only=False``."""
        if selection is None and provided_only:
            self.check_identity()
        chosen = self.use_selection(
            path,
            selection,
            quick=False,
            require_kept=selection is None,
        )
        if provided_only:
            self.apply_files(chosen, log=False)
        self.apply_match(chosen)
        self.apply_vars(chosen, mode=mode, dry_run=dry_run, overrides=overrides)
        return list(self._var_walk(chosen, changes_only=changes_only, provided_only=provided_only))

    def _var_walk(
        self,
        selection: FileSelection,
        *,
        changes_only: bool,
        provided_only: bool,
    ):
        shelves = {shelf.name: shelf for shelf in selection.shelves}
        for item in selection.inventory:
            if item.match is None or item.resolved is None or item.var_plan is None:
                continue
            if provided_only:
                identity_hit = item.identity_status in FILE_CHANGE_STATUSES
                kind_hit = item.kind_status in KIND_CHANGE_STATUSES
                if not identity_hit and not kind_hit:
                    continue
            if changes_only and not item.vars_changed:
                continue
            yield (
                shelves[item.profile],
                item.result,
                item.found,
                item.match,
                item.resolved,
                item.var_plan,
            )

    def _path_is_in_scope(self, selector: KeptPath, groups: list[list[InputScanResult]]) -> bool:
        for scans in groups:
            for result in scans:
                for found in result.results:
                    if selector.matches(found.path):
                        return True
        for shelf in self.shelves:
            with ShelfDatabase.open_read(shelf.database_file) as database:
                for document in database.documents():
                    if selector.matches(document.path):
                        return True
        return False

    @staticmethod
    def _kind_row(
        profile: str,
        index: int,
        path: str,
        kind: str,
        rule: str,
        status: str,
        groups: dict[str, str],
    ) -> dict[str, object]:
        return {
            "profile": profile,
            "input": index,
            "path": path,
            "kind": kind,
            "rule": rule,
            "groups": "\n".join(f"{name}: {value}" for name, value in groups.items()),
            "status": status,
        }
