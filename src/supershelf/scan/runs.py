"""Load profiles, walk inputs, match kinds, and resolve variables."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from supershelf.configs import ShelfConfigs
from supershelf.constants import (
    EVENT_GENERATION,
    EVENT_MISSING,
    EVENT_MOVE,
    EVENT_NEW,
    EVENT_OUTPUT,
    EVENT_UNMATCHED,
    LOGGER_NAME,
    STATUS_DUPLICATE,
    STATUS_REFRESH,
    STATUS_UNCHANGED,
)
from supershelf.database import ShelfDatabase
from supershelf.errors import SupershelfError
from supershelf.profile import ShelfProfile
from supershelf.scan.match import Matcher
from supershelf.scan.walk import InputFile, InputScanResult, KeptPath
from supershelf.vars import VarPlan

_SCAN_PREFIX = ("profile", "input", "sha", "path", "status")


def order_scan_row(row: dict[str, object], *, profiles: int) -> dict[str, object]:
    """Scan stdout order. profile is included only when more than one is selected."""
    source = dict(row)
    if "sha" not in source and "sha256" in source:
        source["sha"] = source.pop("sha256")
    if profiles <= 1:
        source.pop("profile", None)
    ordered: dict[str, object] = {}
    for key in _SCAN_PREFIX:
        if key not in source:
            continue
        ordered[key] = source.pop(key)
    ordered.update(source)
    return ordered


_FILE_STATUSES = frozenset(
    {
        EVENT_NEW,
        EVENT_GENERATION,
        EVENT_MOVE,
        EVENT_MISSING,
        STATUS_REFRESH,
        STATUS_DUPLICATE,
    }
)
_KIND_STATUS = "kind"
_RULE_STATUS = "rule"


class ResolvedWalk:
    """Matched files with resolved variables. Does not commit kind files."""

    def __init__(
        self,
        prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
        groups: list[list[InputScanResult]],
        accept: Callable[[InputFile], bool] | None = None,
    ) -> None:
        self._prepared = prepared
        self._groups = groups
        self._accept = accept

    @property
    def plans(self) -> list[VarPlan]:
        """One plan per profile, including a profile with no matched files."""
        return [plan for _shelf, _matcher, plan in self._prepared]

    def __iter__(self):
        for (_shelf, matcher, plan), scans in zip(
            self._prepared,
            self._groups,
            strict=True,
        ):
            for result in scans:
                files = {found.path: found for found in result.results}
                for matched in matcher.collect(result):
                    found = files[matched.path]
                    if self._accept is not None and not self._accept(found):
                        continue
                    resolved = plan.resolve(found, matched, result.config.path)
                    yield _shelf, result, found, matched, resolved, plan


class ShelfRuns:
    """Profiles loaded for one scan command."""

    def __init__(self, shelves: list[ShelfProfile]) -> None:
        self.shelves = shelves

    @classmethod
    def load(cls, config: str | None, profile: str | None) -> ShelfRuns:
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        return cls([ShelfProfile.from_config(item) for item in loaded.config_list])

    def scans(self, *, quick: bool, path: str | None):
        groups = [shelf.scan(quick=quick) for shelf in self.shelves]
        return KeptPath.narrow_groups(groups, path)

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

    def resolved(
        self,
        path: str | None,
        *,
        mode: str | None = None,
        dry_run: bool = False,
        groups: list[list[InputScanResult]] | None = None,
        accept: Callable[[InputFile], bool] | None = None,
    ) -> ResolvedWalk:
        """Match and resolve. A passed `groups` skips a second walk."""
        prepared = self.plans(mode=mode, dry_run=dry_run)
        if groups is None:
            groups = self.scans(quick=False, path=path)
        return ResolvedWalk(prepared, groups, accept)

    def file_rows(self, path: str | None, *, changes_only: bool = True) -> list[dict[str, object]]:
        """Identity changes. Does not resolve variables or create the database."""
        from supershelf.record import LiveFile, RecordIdentity, RecordPlan

        logger = logging.getLogger(LOGGER_NAME)
        groups = [shelf.scan(quick=False) for shelf in self.shelves]
        kept_paths = [
            found.path
            for scans in groups
            for result in scans
            for found in result.results
        ]
        selector = KeptPath.from_paths(path, kept_paths)
        if path is not None and not self._path_is_in_scope(selector, groups):
            raise SupershelfError(f"No kept file {path!r}")
        rows: list[dict[str, object]] = []
        for shelf, scans in zip(self.shelves, groups, strict=True):
            steps = RecordIdentity.resolve(
                shelf.config_section(shelf.document),
                None,
                os.environ,
            )
            matcher = Matcher.from_document(shelf.document, shelf.name)
            walked = {str(result.config.path) for result in scans}
            kept: set[tuple[str, str]] = set()
            ignored: set[tuple[str, str]] = set()
            database_path = shelf.database_file.resolve()
            cache_path = shelf.cache_file.resolve()
            live: list[LiveFile] = []
            seen_files: dict[tuple[str, str], tuple[InputScanResult, InputFile]] = {}
            for result in scans:
                input_path = str(result.config.path)
                for found in result.results:
                    location = (input_path, found.path)
                    absolute = found.absolute.resolve()
                    if absolute == database_path or absolute == cache_path:
                        ignored.add(location)
                        continue
                    kept.add(location)
                    seen_files[location] = (result, found)
                    hit = matcher.claim(found)
                    if hit is None or not found.sha256:
                        continue
                    live.append(
                        LiveFile.from_match(
                            result,
                            found,
                            kind=hit.kind,
                            rule=hit.rule,
                            snapshot="{}",
                            steps=steps,
                        )
                    )
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
            stamped: list[LiveFile] = []
            for item in live:
                document = stored_at.get(item.location())
                if document is None:
                    stamped.append(item)
                    continue
                stamped.append(
                    LiveFile(
                        input_index=item.input_index,
                        input_path=item.input_path,
                        path=item.path,
                        hash=item.hash,
                        mtime=item.mtime,
                        ctime=item.ctime,
                        match_kind=document.match_kind,
                        rule=document.rule,
                        file_dir=document.file_dir,
                        file_name=document.file_name,
                        file_stem=document.file_stem,
                        file_ext=document.file_ext,
                        vars_json=document.vars_json,
                        steps=item.steps,
                    )
                )
            plan = RecordPlan(
                documents,
                stamped,
                kept,
                walked,
                selector,
                {},
                prior,
                ignored,
                profile=shelf.name,
            )
            planned = plan.rows()
            for message in plan.warnings:
                logger.warning("%s", message)
            shown: list[dict[str, object]] = []
            for row in planned:
                if not selector.matches(row.file.path):
                    continue
                if changes_only and row.status not in _FILE_STATUSES:
                    continue
                shown.append(self._file_row(shelf, row.file, row.status))
            if not changes_only:
                emitted = {(row["input"], row["path"]) for row in shown}
                for result, found in seen_files.values():
                    if not selector.matches(found.path):
                        continue
                    if (result.index, found.path) in emitted:
                        continue
                    shown.append(
                        {
                            "profile": shelf.name,
                            "input": result.index,
                            "path": found.path,
                            "status": EVENT_UNMATCHED,
                            "mtime": shelf.show_time(found.mtime or "") if found.mtime else "",
                            "ctime": shelf.show_time(found.ctime or "") if found.ctime else "",
                            "sha256": found.sha256 or "",
                        }
                    )
            rows.extend(shown)
        profiles = len(self.shelves)
        return [order_scan_row(row, profiles=profiles) for row in rows]

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

    def kind_rows(self, path: str | None, *, changes_only: bool = True) -> list[dict[str, object]]:
        """Kind and rule changes, captured groups, and unmatched files. Does not hash."""
        groups = self.scans(quick=True, path=path)
        rows: list[dict[str, object]] = []
        for shelf, scans in zip(self.shelves, groups, strict=True):
            matcher = Matcher.from_document(shelf.document, shelf.name)
            with ShelfDatabase.open_read(shelf.database_file) as database:
                stored_at = {
                    (document.input_path, document.path): document
                    for document in database.documents()
                }
            for result in scans:
                claimed = {item.path: item for item in matcher.collect(result)}
                input_path = str(result.config.path)
                for found in result.results:
                    hit = claimed.get(found.path)
                    document = stored_at.get((input_path, found.path))
                    if hit is None:
                        rows.append(
                            self._kind_row(
                                result.profile,
                                result.index,
                                found.path,
                                "",
                                "",
                                EVENT_UNMATCHED,
                                {},
                            )
                        )
                        continue
                    if document is None:
                        status = EVENT_NEW
                    elif document.match_kind != hit.kind:
                        status = _KIND_STATUS
                    elif document.rule != hit.rule:
                        status = _RULE_STATUS
                    else:
                        status = STATUS_UNCHANGED
                    if changes_only and status == STATUS_UNCHANGED:
                        continue
                    rows.append(
                        self._kind_row(
                            result.profile,
                            result.index,
                            found.path,
                            hit.kind,
                            hit.rule,
                            status,
                            hit.groups,
                        )
                    )
        profiles = len(self.shelves)
        return [order_scan_row(row, profiles=profiles) for row in rows]

    def changed_resolves(
        self,
        path: str | None,
        *,
        mode: str | None = None,
        dry_run: bool = False,
        changes_only: bool = True,
    ):
        """Matched files whose vars differ, plus new matched files."""
        walk = self.resolved(path, mode=mode, dry_run=dry_run)
        stored: dict[str, dict[tuple[str, str], str]] = {}
        for shelf in self.shelves:
            with ShelfDatabase.open_read(shelf.database_file) as database:
                stored[shelf.name] = {
                    (document.input_path, document.path): document.vars_json
                    for document in database.documents()
                }
        chosen = []
        for shelf, result, found, matched, resolved, plan in walk:
            key = (str(result.config.path), found.path)
            previous = stored.get(shelf.name, {}).get(key)
            snapshot = plan.snapshot(resolved)
            if changes_only and previous is not None and previous == snapshot:
                continue
            chosen.append((shelf, result, found, matched, resolved, plan))
        return chosen

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
