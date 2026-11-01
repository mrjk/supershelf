"""Decide what a record run would write, and apply that plan to the sqlite file."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from supershelf.configs import ShelfConfigs
from supershelf.constants import (
    CONFIG_SECTION,
    ENV_RECORD_IDENTITY,
    EVENT_GENERATION,
    EVENT_MISSING,
    EVENT_MOVE,
    EVENT_NEW,
    EVENT_OUTPUT,
    EVENT_PRESENT,
    EVENT_UNMATCHED,
    EVENT_VARS,
    IDENTITY_HASH,
    INTERNAL_NAMES,
    KEY_RECORD_IDENTITY,
    LOGGER_NAME,
    PRESENCE_MISSING,
    PRESENCE_PRESENT,
    PRESENCE_UNMATCHED,
    RECORD_IDENTITIES,
    STATUS_REFRESH,
    STATUS_UNCHANGED,
)
from supershelf.database import (
    DatabaseChange,
    DocumentRow,
    EventRow,
    ShelfDatabase,
    StoredFile,
)
from supershelf.defaults import PACKAGED
from supershelf.errors import RecordConfigError, SupershelfError
from supershelf.match import Matcher
from supershelf.profile import ShelfProfile
from supershelf.scan import InputFile, InputScanResult
from supershelf.var_schema import VarCatalog
from supershelf.vars import FileVars, VarPlan


class RecordIdentity:
    """path or hash. The flag wins, then the env var, then config."""

    @staticmethod
    def resolve(
        section: Mapping[str, object],
        flag: str | None,
        environ: Mapping[str, str],
    ) -> str:
        """The link rule for this run."""
        if flag is not None:
            return RecordIdentity._one(flag, "--record-identity")
        if ENV_RECORD_IDENTITY in environ:
            return RecordIdentity._one(
                environ[ENV_RECORD_IDENTITY],
                ENV_RECORD_IDENTITY,
            )
        raw = section.get(KEY_RECORD_IDENTITY)
        if raw is not None:
            return RecordIdentity._one(raw, "config.record_identity")
        return PACKAGED.record_identity

    @staticmethod
    def _one(value: object, label: str) -> str:
        if isinstance(value, str) and value in RECORD_IDENTITIES:
            return value
        raise RecordConfigError(
            f"{label} must be path or hash",
            advice="Use path or hash, in lower case.",
        )


class RecordSnapshot:
    """JSON object stored in `vars_json`."""

    @staticmethod
    def encode(resolved: FileVars, catalog: VarCatalog) -> str:
        """Bindings that are not already columns, with sorted keys."""
        body: dict[str, dict[str, object]] = {}
        for name, state in resolved.states:
            if name in INTERNAL_NAMES:
                continue
            if state.value is None:
                continue
            spec = catalog.effective(resolved.kind, name)
            body[name] = {
                "type": spec.type,
                "value": state.value,
                "display": state.display,
                "value_sources": list(state.value_sources),
            }
        return json.dumps(body, sort_keys=True, separators=(",", ":"))


class PathSelector:
    """Exact path, or a prefix, using the same rule as the scan filter."""

    def __init__(self, text: str | None, *, exact: bool) -> None:
        self.text = text
        self.exact = exact

    @classmethod
    def from_paths(cls, text: str | None, paths: list[str]) -> PathSelector:
        """None keeps every path. An exact kept path wins over a prefix."""
        if text is None:
            return cls(None, exact=False)
        return cls(text, exact=text in paths)

    def matches(self, relative: str) -> bool:
        """Whether this relative path is in the observed set."""
        if self.text is None:
            return True
        if self.exact:
            return relative == self.text
        return relative.startswith(self.text)


@dataclass(frozen=True)
class LiveFile:
    """One in-scope matched file, after variables have been resolved."""

    input_index: int
    input_path: str
    path: str
    hash: str
    mtime: str | None
    ctime: str | None
    match_kind: str
    rule: str
    file_dir: str
    file_name: str
    file_stem: str
    file_ext: str
    vars_json: str

    def location(self) -> tuple[str, str]:
        """Absolute input directory plus the relative path."""
        return (self.input_path, self.path)

    @classmethod
    def from_match(
        cls,
        result: InputScanResult,
        found: InputFile,
        *,
        kind: str,
        rule: str,
        snapshot: str,
    ) -> LiveFile:
        """Build a live file from a walk result and its resolved variables."""
        suffix = found.suffix
        extension = suffix[1:] if suffix.startswith(".") else suffix
        if not found.sha256:
            raise SupershelfError(
                f"Profile {result.profile} has no hash for {found.path}",
                advice="Run record without --quick. Record always reads the file bytes.",
            )
        return cls(
            input_index=result.index,
            input_path=str(result.config.path),
            path=found.path,
            hash=found.sha256,
            mtime=found.mtime,
            ctime=found.ctime,
            match_kind=kind,
            rule=rule,
            file_dir=found.directory,
            file_name=found.name,
            file_stem=found.stem,
            file_ext=extension,
            vars_json=snapshot,
        )

    def stored(self) -> StoredFile:
        """Facts to write if this file is the document's new state."""
        return StoredFile(
            input_index=self.input_index,
            input_path=self.input_path,
            path=self.path,
            hash=self.hash,
            mtime=self.mtime,
            ctime=self.ctime,
            match_kind=self.match_kind,
            rule=self.rule,
            file_dir=self.file_dir,
            file_name=self.file_name,
            file_stem=self.file_stem,
            file_ext=self.file_ext,
            vars_json=self.vars_json,
        )


@dataclass(frozen=True)
class PlannedRow:
    """One status row. `unchanged` has no database change."""

    status: str
    document_id: int | None
    generation: int
    file: StoredFile
    duplicates: int

    def change(self) -> DatabaseChange | None:
        """The write for this row, or None when nothing would be stored."""
        if self.status == STATUS_UNCHANGED:
            return None
        return DatabaseChange(
            status=self.status,
            document_id=self.document_id,
            generation=self.generation,
            file=self.file,
        )


@dataclass(frozen=True)
class DuplicateHit:
    """One document that shares a hash with another document."""

    hash: str
    document_id: int
    current: bool
    path: str
    generation: int
    input_index: int


class DuplicateListing:
    """Hashes carried by two or more documents."""

    @staticmethod
    def collect(documents: list[DocumentRow], events: list[EventRow]) -> list[DuplicateHit]:
        """Group shared hashes. Output events do not carry a content hash."""
        carriers: dict[str, set[int]] = {}
        for event in events:
            if event.event == EVENT_OUTPUT:
                continue
            carriers.setdefault(event.hash, set()).add(event.document_id)
        shared = sorted(digest for digest, ids in carriers.items() if len(ids) >= 2)
        by_id = {document.id: document for document in documents}
        hits: list[DuplicateHit] = []
        for digest in shared:
            for document_id in sorted(carriers[digest]):
                document = by_id[document_id]
                hits.append(
                    DuplicateHit(
                        hash=digest,
                        document_id=document_id,
                        current=document.hash == digest,
                        path=document.path,
                        generation=document.generation,
                        input_index=document.input_index,
                    )
                )
        return hits


class RecordPlan:
    """Link live files to documents for one profile and one identity rule."""

    def __init__(
        self,
        identity: str,
        documents: list[DocumentRow],
        live: list[LiveFile],
        kept: set[tuple[str, str]],
        walked_inputs: set[str],
        selector: PathSelector,
        ignored: set[tuple[str, str]] | None = None,
    ) -> None:
        self.identity = identity
        self.documents = documents
        self.selector = selector
        self.walked_inputs = walked_inputs
        self.ignored = ignored or set()
        self.live = [
            item
            for item in live
            if self._location_in_scope(item.input_path, item.path)
        ]
        self.kept = {
            location
            for location in kept
            if self._location_in_scope(location[0], location[1])
        }
        for item in self.live:
            self.kept.add(item.location())

    def rows(self) -> list[PlannedRow]:
        """Status rows in document id order, then new files in walk order."""
        live_at = {item.location(): item for item in self.live}
        by_hash: dict[str, list[LiveFile]] = {}
        for item in self.live:
            by_hash.setdefault(item.hash, []).append(item)
        claimed_files: set[tuple[str, str]] = set()
        claimed_docs: set[int] = set()
        decisions: dict[int, tuple[str, StoredFile, int]] = {}
        scoped = [document for document in self.documents if self._document_in_scope(document)]
        scoped.sort(key=lambda document: document.id)

        for document in scoped:
            location = (document.input_path, document.path)
            live = live_at.get(location)
            if live is None:
                continue
            if live.hash == document.hash:
                decisions[document.id] = (
                    self._stay(document, live),
                    live.stored(),
                    document.generation,
                )
                claimed_files.add(location)
                claimed_docs.add(document.id)
                continue
            target = self._hash_target(document, location, by_hash, claimed_files)
            if target is not None:
                decisions[document.id] = (EVENT_MOVE, target.stored(), document.generation)
                claimed_files.add(target.location())
                claimed_docs.add(document.id)
                continue
            decisions[document.id] = (
                EVENT_GENERATION,
                live.stored(),
                document.generation + 1,
            )
            claimed_files.add(location)
            claimed_docs.add(document.id)

        gone = [
            document
            for document in scoped
            if document.id not in claimed_docs
            and (document.input_path, document.path) not in self.kept
        ]
        wanters: dict[str, int] = {}
        for document in gone:
            wanters[document.hash] = wanters.get(document.hash, 0) + 1

        for document in scoped:
            if document.id in claimed_docs:
                continue
            location = (document.input_path, document.path)
            if location in self.kept and location not in live_at:
                if document.presence != PRESENCE_UNMATCHED:
                    decisions[document.id] = (
                        EVENT_UNMATCHED,
                        document.file(),
                        document.generation,
                    )
                claimed_docs.add(document.id)
                continue
            if location in live_at:
                continue
            candidates = [
                item
                for item in by_hash.get(document.hash, [])
                if item.location() not in claimed_files
            ]
            if len(candidates) == 1 and wanters.get(document.hash) == 1:
                target = candidates[0]
                decisions[document.id] = (EVENT_MOVE, target.stored(), document.generation)
                claimed_files.add(target.location())
                claimed_docs.add(document.id)
                continue
            if document.presence != PRESENCE_MISSING:
                decisions[document.id] = (
                    EVENT_MISSING,
                    document.file(),
                    document.generation,
                )
            claimed_docs.add(document.id)

        fresh: list[tuple[str, StoredFile, int]] = []
        for item in self.live:
            if item.location() in claimed_files:
                continue
            fresh.append((EVENT_NEW, item.stored(), 1))
            claimed_files.add(item.location())
        return self._with_duplicates(decisions, fresh)

    def _hash_target(
        self,
        document: DocumentRow,
        location: tuple[str, str],
        by_hash: dict[str, list[LiveFile]],
        claimed_files: set[tuple[str, str]],
    ) -> LiveFile | None:
        if self.identity != IDENTITY_HASH:
            return None
        others = [
            item
            for item in by_hash.get(document.hash, [])
            if item.location() != location and item.location() not in claimed_files
        ]
        if len(others) == 1:
            return others[0]
        return None

    def _stay(self, document: DocumentRow, live: LiveFile) -> str:
        facts = (
            document.match_kind != live.match_kind
            or document.rule != live.rule
            or document.vars_json != live.vars_json
            or document.file_dir != live.file_dir
            or document.file_name != live.file_name
            or document.file_stem != live.file_stem
            or document.file_ext != live.file_ext
        )
        clock = (
            document.mtime != live.mtime
            or document.ctime != live.ctime
            or document.input_index != live.input_index
        )
        if facts:
            return EVENT_VARS
        if document.presence != PRESENCE_PRESENT:
            return EVENT_PRESENT
        if clock:
            return STATUS_REFRESH
        return STATUS_UNCHANGED

    def _document_in_scope(self, document: DocumentRow) -> bool:
        return self._location_in_scope(document.input_path, document.path)

    def _location_in_scope(self, input_path: str, relative: str) -> bool:
        if (input_path, relative) in self.ignored:
            return False
        if input_path not in self.walked_inputs:
            return False
        return self.selector.matches(relative)

    def _with_duplicates(
        self,
        decisions: dict[int, tuple[str, StoredFile, int]],
        fresh: list[tuple[str, StoredFile, int]],
    ) -> list[PlannedRow]:
        presence = {
            document.id: (document.hash, document.presence) for document in self.documents
        }
        ordered: list[tuple[int, str, StoredFile, int]] = []
        for document_id in sorted(decisions):
            status, file, generation = decisions[document_id]
            ordered.append((document_id, status, file, generation))
            if status == EVENT_MISSING:
                presence[document_id] = (file.hash, PRESENCE_MISSING)
            elif status == EVENT_UNMATCHED:
                presence[document_id] = (file.hash, PRESENCE_UNMATCHED)
            else:
                presence[document_id] = (file.hash, PRESENCE_PRESENT)
        synthetic = 0
        for status, file, generation in fresh:
            synthetic -= 1
            ordered.append((synthetic, status, file, generation))
            presence[synthetic] = (file.hash, PRESENCE_PRESENT)
        counts: dict[str, int] = {}
        for digest, state in presence.values():
            if state == PRESENCE_PRESENT:
                counts[digest] = counts.get(digest, 0) + 1
        rows: list[PlannedRow] = []
        for document_id, status, file, generation in ordered:
            state = presence[document_id][1]
            count = counts.get(file.hash, 0)
            others = count - 1 if state == PRESENCE_PRESENT else count
            rows.append(
                PlannedRow(
                    status=status,
                    document_id=None if document_id < 0 else document_id,
                    generation=generation,
                    file=file,
                    duplicates=others,
                )
            )
        return rows


class _ProfileRun:
    """One profile's scan, plan, and optional write."""

    def __init__(self, shelf: ShelfProfile, identity: str) -> None:
        self.shelf = shelf
        self.identity = identity
        self._logger = logging.getLogger(LOGGER_NAME)

    def plan(self, path: str | None) -> list[PlannedRow]:
        """Resolve this profile and compare it with the database. Does not write."""
        scans = self.shelf.scan(quick=False)
        walked = {str(result.config.path) for result in scans}
        kept_paths: list[str] = []
        ignored: set[tuple[str, str]] = set()
        kept: set[tuple[str, str]] = set()
        database_path = self.shelf.database_file.resolve()
        for result in scans:
            input_path = str(result.config.path)
            for found in result.results:
                kept_paths.append(found.path)
                location = (input_path, found.path)
                if found.absolute.resolve() == database_path:
                    self._logger.warning("Skipping database file %s", database_path)
                    ignored.add(location)
                    continue
                kept.add(location)
        selector = PathSelector.from_paths(path, kept_paths)
        matcher = Matcher.from_document(self.shelf.document, self.shelf.name)
        variables = VarPlan.from_document(
            self.shelf.document,
            self.shelf.name,
            matcher,
            self.shelf.root_dir,
            self.shelf.scope,
        )
        live: list[LiveFile] = []
        for result in scans:
            files = {found.path: found for found in result.results}
            for matched in matcher.collect(result):
                found = files.get(matched.path)
                if found is None or not selector.matches(found.path):
                    continue
                if found.absolute.resolve() == database_path:
                    continue
                resolved = variables.resolve(found, matched, result.config.path)
                live.append(
                    LiveFile.from_match(
                        result,
                        found,
                        kind=resolved.kind,
                        rule=matched.rule,
                        snapshot=RecordSnapshot.encode(resolved, variables.catalog),
                    )
                )
        with ShelfDatabase.open_read(self.shelf.database_file) as database:
            stored = database.identity()
            if stored is not None and stored != self.identity:
                self._logger.warning(
                    "Profile %s record_identity was %s and this run uses %s. "
                    "Existing events stay.",
                    self.shelf.name,
                    stored,
                    self.identity,
                )
            rows = RecordPlan(
                self.identity,
                database.documents(),
                live,
                kept,
                walked,
                selector,
                ignored,
            ).rows()
        if path is not None and not rows and not self._selector_saw_file(selector, kept):
            raise SupershelfError(
                f"No kept file {path!r}",
                advice="Use a path from scan files, or run record without a path.",
            )
        return rows

    def write(self, rows: list[PlannedRow], *, dry_run: bool) -> None:
        """Apply rows that would change. A dry run and an empty plan create nothing."""
        changes = [row.change() for row in rows if row.change() is not None]
        if dry_run or (not changes and not self._identity_differs()):
            return
        recorded_at = datetime.now(timezone.utc).isoformat()
        with ShelfDatabase.open_write(self.shelf.database_file) as database:
            if changes:
                database.apply(changes, self.identity, recorded_at)
                return
            database.note_identity(self.identity)

    def _identity_differs(self) -> bool:
        with ShelfDatabase.open_read(self.shelf.database_file) as database:
            stored = database.identity()
        return stored is not None and stored != self.identity

    @staticmethod
    def _selector_saw_file(selector: PathSelector, kept: set[tuple[str, str]]) -> bool:
        return any(selector.matches(relative) for _input_path, relative in kept)

    def display(self, rows: list[PlannedRow], *, changes_only: bool) -> list[dict[str, object]]:
        """Clak rows for this profile."""
        shown = rows
        if changes_only:
            shown = [row for row in rows if row.status != STATUS_UNCHANGED]
        return [
            {
                "profile": self.shelf.name,
                "input": row.file.input_index,
                "path": row.file.path,
                "status": row.status,
                "hash": row.file.hash,
                "generation": row.generation,
                "kind": row.file.match_kind,
                "rule": row.file.rule,
                "duplicates": row.duplicates,
            }
            for row in shown
        ]


class RecordSession:
    """status and run for the selected profiles."""

    def __init__(self, runs: list[_ProfileRun]) -> None:
        self.runs = runs

    @classmethod
    def load(
        cls,
        config: str | None,
        profile: str | None,
        identity_flag: str | None,
        environ: Mapping[str, str] | None = None,
    ) -> RecordSession:
        """Resolve the link rule before any walk."""
        env = os.environ if environ is None else environ
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        runs: list[_ProfileRun] = []
        for item in loaded.config_list:
            shelf = ShelfProfile.from_config(item)
            section = shelf.document.get(CONFIG_SECTION)
            if not isinstance(section, dict):
                section = {}
            identity = RecordIdentity.resolve(section, identity_flag, env)
            runs.append(_ProfileRun(shelf, identity))
        return cls(runs)

    def status(self, path: str | None) -> list[dict[str, object]]:
        """Every in-scope row. Writes nothing."""
        rows: list[dict[str, object]] = []
        for run in self.runs:
            planned = run.plan(path)
            rows.extend(run.display(planned, changes_only=False))
        return rows

    def run(self, path: str | None, *, dry_run: bool) -> list[dict[str, object]]:
        """Rows that would change. `--dry-run` skips the write."""
        rows: list[dict[str, object]] = []
        for run in self.runs:
            planned = run.plan(path)
            rows.extend(run.display(planned, changes_only=True))
            run.write(planned, dry_run=dry_run)
        return rows


class RecordReader:
    """history and duplicates. Neither command scans or writes."""

    def __init__(self, shelves: list[ShelfProfile]) -> None:
        self.shelves = shelves

    @classmethod
    def load(cls, config: str | None, profile: str | None) -> RecordReader:
        """Load profiles so each database path can be opened read-only."""
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        return cls([ShelfProfile.from_config(item) for item in loaded.config_list])

    def history(self, path: str | None) -> list[dict[str, object]]:
        """Events in id order. A move is still found from its old path."""
        rows: list[dict[str, object]] = []
        for shelf in self.shelves:
            with ShelfDatabase.open_read(shelf.database_file) as database:
                documents = database.documents()
                events = database.events()
            chosen = self._history_ids(documents, events, path)
            for event in events:
                if event.document_id not in chosen:
                    continue
                rows.append(
                    {
                        "profile": shelf.name,
                        "document": event.document_id,
                        "seq": event.seq,
                        "event": event.event,
                        "identity": event.identity,
                        "input": event.input_index,
                        "path": event.path,
                        "hash": event.hash,
                        "generation": event.generation,
                        "kind": event.match_kind,
                        "rule": event.rule,
                        "at": event.recorded_at,
                    }
                )
        return rows

    def duplicates(self, path: str | None) -> list[dict[str, object]]:
        """Recorded documents that share a hash."""
        rows: list[dict[str, object]] = []
        for shelf in self.shelves:
            with ShelfDatabase.open_read(shelf.database_file) as database:
                documents = database.documents()
                hits = DuplicateListing.collect(documents, database.events())
            selector = PathSelector.from_paths(path, [document.path for document in documents])
            for hit in hits:
                if not selector.matches(hit.path):
                    continue
                rows.append(
                    {
                        "profile": shelf.name,
                        "hash": hit.hash,
                        "document": hit.document_id,
                        "current": "yes" if hit.current else "no",
                        "path": hit.path,
                        "generation": hit.generation,
                    }
                )
        return rows

    @staticmethod
    def _history_ids(
        documents: list[DocumentRow],
        events: list[EventRow],
        path: str | None,
    ) -> set[int]:
        by_document: dict[int, list[str]] = {document.id: [document.path] for document in documents}
        for event in events:
            by_document.setdefault(event.document_id, []).append(event.path)
        known = [relative for paths in by_document.values() for relative in paths]
        selector = PathSelector.from_paths(path, known)
        return {
            document_id
            for document_id, paths in by_document.items()
            if any(selector.matches(relative) for relative in paths)
        }
