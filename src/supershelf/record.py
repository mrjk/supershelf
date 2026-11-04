"""Decide what a record run would write, and apply that plan to the sqlite file."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NoReturn, Protocol

from supershelf.common import WordChoice
from supershelf.constants import (
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
    IDENTITY_PATH,
    KEY_MATCH_RULES,
    KEY_RECORD_IDENTITY,
    LOGGER_NAME,
    PRESENCE_MISSING,
    PRESENCE_PRESENT,
    PRESENCE_UNMATCHED,
    RECORD_IDENTITIES,
    STATUS_DUPLICATE,
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
from supershelf.profile import ShelfProfile
from supershelf.scan.runs import ShelfRuns
from supershelf.scan.walk import InputFile, InputScanResult, KeptPath
from supershelf.template.environment import is_template
from supershelf.vars import FileVars, VarPlan


class RecordIdentity(WordChoice):
    """One step or a list of steps. The flag wins, then the env var, then config.

    A bare word expands. `path` is path then hash. `hash` is hash then path.
    A list, and a comma-separated flag, do not expand each item.
    """

    words = RECORD_IDENTITIES
    flag_name = "--record-identity"
    env_name = ENV_RECORD_IDENTITY
    config_key = KEY_RECORD_IDENTITY
    config_label = "config.record_identity"
    requirement = "{label} must be path or hash"
    advice = "Use path or hash, in lower case. A list does not expand each item."
    error = RecordConfigError

    @classmethod
    def packaged(cls) -> str:
        """The packaged link rule. `resolve` expands this word."""
        return PACKAGED.record_identity

    @classmethod
    def resolve(
        cls,
        section: Mapping[str, Any],
        flag: str | None,
        environ: Mapping[str, str],
    ) -> tuple[str, ...]:
        """Flag, then environment, then config, then packaged path."""
        if flag is not None:
            return cls.parse_flag(flag, cls.flag_name)
        if cls.env_name in environ:
            return cls.parse_flag(environ[cls.env_name], cls.env_name)
        raw = section.get(cls.config_key)
        if raw is not None:
            return cls.parse_config(raw, cls.config_label)
        return cls.expand_word(cls.packaged())

    @classmethod
    def parse_flag(cls, value: object, label: str) -> tuple[str, ...]:
        """A word, or comma-separated steps. Spaces around a comma are ignored."""
        if not isinstance(value, str):
            cls._reject(label)
        parts = tuple(part.strip() for part in value.split(","))
        if len(parts) == 1:
            return cls._expand_bare(parts[0], label)
        return cls._steps(parts, label)

    @classmethod
    def parse_config(cls, value: object, label: str) -> tuple[str, ...]:
        """A YAML string expands. A YAML list does not. A string is not split on commas."""
        if isinstance(value, str):
            return cls._expand_bare(value, label)
        if isinstance(value, list):
            return cls._steps(tuple(value), label)
        cls._reject(label)

    @classmethod
    def rule_lists(
        cls,
        document: Mapping[str, Any],
        profile_name: str,
        default: tuple[str, ...],
    ) -> dict[str, tuple[str, ...]]:
        """Every match rule's list. Omitted or null inherits `default`."""
        raw = document.get(KEY_MATCH_RULES)
        if not isinstance(raw, list):
            return {}
        found: dict[str, tuple[str, ...]] = {}
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, Mapping):
                continue
            name = cls._rule_name(item, index)
            if KEY_RECORD_IDENTITY not in item or item.get(KEY_RECORD_IDENTITY) is None:
                found[name] = default
                continue
            label = f"Profile {profile_name} match rule {name}"
            found[name] = cls.parse_config(item.get(KEY_RECORD_IDENTITY), label)
        return found

    @classmethod
    def text(cls, steps: tuple[str, ...]) -> str:
        """Comma-separated list with no spaces. This is the meta value."""
        return ",".join(steps)

    @classmethod
    def same(cls, stored: str, steps: tuple[str, ...]) -> bool:
        """Legacy `path` equals path then hash. Legacy `hash` equals hash then path."""
        if stored == cls.text(steps):
            return True
        if stored == IDENTITY_PATH and steps == (IDENTITY_PATH, IDENTITY_HASH):
            return True
        if stored == IDENTITY_HASH and steps == (IDENTITY_HASH, IDENTITY_PATH):
            return True
        return False

    @classmethod
    def expand_word(cls, word: str) -> tuple[str, ...]:
        """Expand a stored identity word. A list item does not use this."""
        if word == IDENTITY_PATH:
            return (IDENTITY_PATH, IDENTITY_HASH)
        if word == IDENTITY_HASH:
            return (IDENTITY_HASH, IDENTITY_PATH)
        cls._reject(cls.config_label)

    @classmethod
    def _expand_bare(cls, word: object, label: str) -> tuple[str, ...]:
        return cls.expand_word(cls._one_step(word, label))

    @classmethod
    def _steps(cls, items: tuple[object, ...], label: str) -> tuple[str, ...]:
        if not items:
            cls._reject(label)
        checked: list[str] = []
        for item in items:
            word = cls._one_step(item, label)
            if word in checked:
                cls._reject(label)
            checked.append(word)
        return tuple(checked)

    @classmethod
    def _one_step(cls, word: object, label: str) -> str:
        if (
            not isinstance(word, str)
            or not word
            or cls._templated(word)
            or word not in cls.words
        ):
            cls._reject(label)
        return word

    @staticmethod
    def _templated(word: str) -> bool:
        return is_template(word)

    @classmethod
    def _rule_name(cls, item: Mapping[str, Any], index: int) -> str:
        name = item.get("name")
        kind = item.get("kind")
        if isinstance(name, str) and name.strip():
            return name
        if isinstance(kind, str) and kind.strip():
            return kind
        return str(index)

    @classmethod
    def _reject(cls, label: str) -> NoReturn:
        raise cls.error(cls.requirement.format(label=label), advice=cls.advice)


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
    steps: tuple[str, ...]

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
        steps: tuple[str, ...],
    ) -> LiveFile:
        """Build a live file from a walk result and its resolved variables."""
        extension = found.extension
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
            steps=steps,
        )

    def stored(self) -> StoredFile:
        """Facts to write if this file is the document's new state."""
        return StoredFile.from_facts(self)


class DriftFacts(Protocol):
    """Stored or live facts that can make a record status `vars`."""

    match_kind: str
    rule: str
    vars_json: str
    file_dir: str
    file_name: str
    file_stem: str
    file_ext: str


def document_drift(stored: DriftFacts, live: DriftFacts) -> list[str]:
    """Clauses for kind, rule, variables, and file fields that differ.

    Variable text is the display string. An empty list means those facts match.
    """
    clauses: list[str] = []
    if stored.match_kind != live.match_kind:
        clauses.append(
            f"kind was {_quoted(stored.match_kind)}, now {_quoted(live.match_kind)}."
        )
    if stored.rule != live.rule:
        clauses.append(f"rule was {_quoted(stored.rule)}, now {_quoted(live.rule)}.")
    clauses.extend(_variable_drift(stored.vars_json, live.vars_json))
    for label in ("file_dir", "file_name", "file_stem", "file_ext"):
        old = getattr(stored, label)
        new = getattr(live, label)
        if old != new:
            clauses.append(f"{label} was {_quoted(old)}, now {_quoted(new)}.")
    return clauses


def _quoted(text: str) -> str:
    return json.dumps(text)


def _variable_drift(stored_raw: str, live_raw: str) -> list[str]:
    stored = _var_object(stored_raw)
    live = _var_object(live_raw)
    if stored is None or live is None:
        if stored_raw != live_raw:
            return ["variables changed."]
        return []
    clauses: list[str] = []
    for name in sorted(set(stored) | set(live)):
        if name not in stored:
            shown = _quoted(_display_text(live[name]))
            clauses.append(f"{name} is {shown} and was not stored.")
            continue
        if name not in live:
            shown = _quoted(_display_text(stored[name]))
            clauses.append(f"{name} was {shown} and is no longer set.")
            continue
        old = stored[name]
        new = live[name]
        if old == new:
            continue
        old_display = _display_text(old)
        new_display = _display_text(new)
        if old_display != new_display:
            clauses.append(f"{name} was {_quoted(old_display)}, now {_quoted(new_display)}.")
        else:
            clauses.append(
                f"{name} is still {_quoted(old_display)} but its stored type or source changed."
            )
    if not clauses and stored_raw != live_raw:
        clauses.append("variables changed.")
    return clauses


def _var_object(raw: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _display_text(entry: object) -> str:
    if isinstance(entry, dict) and isinstance(entry.get("display"), str):
        return entry["display"]
    return json.dumps(entry, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class PlannedRow:
    """One status row. `unchanged` and `duplicate` have no database change."""

    status: str
    document_id: int | None
    generation: int
    file: StoredFile
    duplicates: int
    identity: str

    def change(self) -> DatabaseChange | None:
        """The write for this row, or None when nothing would be stored."""
        if self.status in (STATUS_UNCHANGED, STATUS_DUPLICATE):
            return None
        return DatabaseChange(
            status=self.status,
            document_id=self.document_id,
            generation=self.generation,
            file=self.file,
            identity=self.identity,
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
    """Link live files to documents. Each document walks its own step list."""

    def __init__(
        self,
        documents: list[DocumentRow],
        live: list[LiveFile],
        kept: set[tuple[str, str]],
        walked_inputs: set[str],
        selector: KeptPath,
        rules: Mapping[str, tuple[str, ...]],
        prior: Mapping[int, str],
        ignored: set[tuple[str, str]] | None = None,
        profile: str = "",
    ) -> None:
        self.documents = documents
        self.selector = selector
        self.walked_inputs = walked_inputs
        self.rules = dict(rules)
        self.prior = dict(prior)
        self.profile = profile
        self.ignored = ignored or set()
        self.warnings: list[str] = []
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
        self._live_at: dict[tuple[str, str], LiveFile] = {}
        self._claimed_files: set[tuple[str, str]] = set()
        self._claimed_docs: set[int] = set()
        self._decisions: dict[int, tuple[str, StoredFile, int, str]] = {}
        self._duplicates: dict[tuple[str, str], LiveFile] = {}
        self._scoped: list[DocumentRow] = []
        self._wanters: dict[str, int] = {}

    def rows(self) -> list[PlannedRow]:
        """Status rows in document id order, then unclaimed files in walk order."""
        self.warnings = []
        self._live_at = {item.location(): item for item in self.live}
        self._claimed_files = set()
        self._claimed_docs = set()
        self._decisions = {}
        self._duplicates = {}
        self._scoped = [
            document for document in self.documents if self._document_in_scope(document)
        ]
        self._scoped.sort(key=lambda document: document.id)
        self._stay_phase()
        self._unmatched_phase()
        self._walk_phase()
        fresh = self._fresh_files()
        self._note_rule_warnings()
        return self._with_duplicates(fresh)

    def _stay_phase(self) -> None:
        """Same path and same hash stays, for every list. Reserve that file."""
        for document in self._scoped:
            location = (document.input_path, document.path)
            live = self._live_at.get(location)
            if live is None or live.hash != document.hash:
                continue
            if location in self._claimed_files:
                continue
            self._decisions[document.id] = (
                self._stay(document, live),
                live.stored(),
                document.generation,
                live.steps[0],
            )
            self._claimed_files.add(location)
            self._claimed_docs.add(document.id)

    def _unmatched_phase(self) -> None:
        """A path still in the walk with no rule stops. The hash is not followed."""
        for document in self._scoped:
            if document.id in self._claimed_docs:
                continue
            location = (document.input_path, document.path)
            if location not in self.kept or location in self._live_at:
                continue
            if document.presence != PRESENCE_UNMATCHED:
                self._decisions[document.id] = (
                    EVENT_UNMATCHED,
                    document.file(),
                    document.generation,
                    self.prior.get(document.id, IDENTITY_PATH),
                )
            self._claimed_docs.add(document.id)

    def _walk_phase(self) -> None:
        """Walk each remaining document's list. Stop at the first step that matches."""
        self._wanters = {}
        for document in self._scoped:
            if document.id in self._claimed_docs or self._hash_first(self._steps_for(document)):
                continue
            if not self._reaches_hash_after_path(document):
                continue
            if not self._path_gone(document):
                continue
            self._wanters[document.hash] = self._wanters.get(document.hash, 0) + 1
        for document in self._scoped:
            if document.id in self._claimed_docs:
                continue
            steps = self._steps_for(document)
            if self._take_steps(document, steps):
                continue
            if document.presence != PRESENCE_MISSING:
                self._decisions[document.id] = (
                    EVENT_MISSING,
                    document.file(),
                    document.generation,
                    steps[0],
                )
            self._claimed_docs.add(document.id)

    def _take_steps(self, document: DocumentRow, steps: tuple[str, ...]) -> bool:
        """True when a step links the document."""
        location = (document.input_path, document.path)
        for step in steps:
            if step == IDENTITY_PATH and self._take_path(document, location, steps[0]):
                return True
            if step != IDENTITY_HASH:
                continue
            if self._hash_first(steps) and self._take_hash_first(document, steps[0]):
                return True
            if not self._hash_first(steps) and self._take_hash_continuation(document, steps[0]):
                return True
        return False

    def _take_path(
        self,
        document: DocumentRow,
        location: tuple[str, str],
        identity: str,
    ) -> bool:
        """Generation at the recorded path. Declines when the path is gone or reserved."""
        live = self._live_at.get(location)
        if live is None or location not in self.kept or location in self._claimed_files:
            return False
        self._decisions[document.id] = (
            EVENT_GENERATION,
            live.stored(),
            document.generation + 1,
            identity,
        )
        self._claimed_files.add(location)
        self._claimed_docs.add(document.id)
        return True

    def _take_hash_first(self, document: DocumentRow, identity: str) -> bool:
        """One successor moves. Several move to the lowest path and duplicate the rest."""
        eligible = self._hash_eligible(document)
        if not eligible:
            return False
        ordered = sorted(eligible, key=lambda item: (item.input_path, item.path))
        chosen = ordered[0]
        self._decisions[document.id] = (
            EVENT_MOVE,
            chosen.stored(),
            document.generation,
            identity,
        )
        self._claimed_files.add(chosen.location())
        self._claimed_docs.add(document.id)
        if len(ordered) > 1:
            for item in ordered[1:]:
                self._duplicates[item.location()] = item
                self._claimed_files.add(item.location())
            self._warn_successors(document, chosen, ordered[1:])
        return True

    def _take_hash_continuation(self, document: DocumentRow, identity: str) -> bool:
        """After path declined: move only when one gone document wants the one file."""
        if not self._path_gone(document):
            return False
        candidates = [
            item
            for item in self.live
            if item.hash == document.hash and item.location() not in self._claimed_files
        ]
        if len(candidates) != 1 or self._wanters.get(document.hash) != 1:
            return False
        target = candidates[0]
        self._decisions[document.id] = (
            EVENT_MOVE,
            target.stored(),
            document.generation,
            identity,
        )
        self._claimed_files.add(target.location())
        self._claimed_docs.add(document.id)
        return True

    def _fresh_files(self) -> list[tuple[str, StoredFile, int, str]]:
        """New documents, and hash-first copies that are not inserted."""
        classified: dict[tuple[str, str], tuple[str, str]] = {}
        for location, item in self._duplicates.items():
            classified[location] = (STATUS_DUPLICATE, item.steps[0])
        pending: dict[str, list[LiveFile]] = {}
        for item in self.live:
            if item.location() in classified or item.location() in self._claimed_files:
                continue
            if self._hash_first(item.steps) and self._hash_owned(item.hash):
                classified[item.location()] = (STATUS_DUPLICATE, item.steps[0])
                continue
            if self._hash_first(item.steps):
                pending.setdefault(item.hash, []).append(item)
                continue
            classified[item.location()] = (EVENT_NEW, item.steps[0])
        for files in pending.values():
            ordered = sorted(files, key=lambda item: (item.input_path, item.path))
            classified[ordered[0].location()] = (EVENT_NEW, ordered[0].steps[0])
            for item in ordered[1:]:
                classified[item.location()] = (STATUS_DUPLICATE, item.steps[0])
        fresh: list[tuple[str, StoredFile, int, str]] = []
        for item in self.live:
            found = classified.get(item.location())
            if found is None:
                continue
            status, identity = found
            fresh.append((status, item.stored(), 1, identity))
        return fresh

    def _hash_eligible(self, document: DocumentRow) -> list[LiveFile]:
        """Unreserved hash-first files that carry this document's hash."""
        found: list[LiveFile] = []
        for item in self.live:
            if item.hash != document.hash or item.location() in self._claimed_files:
                continue
            if self._hash_first(item.steps):
                found.append(item)
        return found

    def _hash_owned(self, digest: str) -> bool:
        """An in-scope present hash-first document already has this hash."""
        for document in self._scoped:
            if not self._hash_first(self._steps_for(document)):
                continue
            decision = self._decisions.get(document.id)
            if decision is None:
                if document.presence == PRESENCE_PRESENT and document.hash == digest:
                    return True
                continue
            status, file, _generation, _identity = decision
            if status in (EVENT_MISSING, EVENT_UNMATCHED):
                continue
            if file.hash == digest:
                return True
        return False

    def _steps_for(self, document: DocumentRow) -> tuple[str, ...]:
        """Live file at the recorded path, else the named rule, else the prior word."""
        live = self._live_at.get((document.input_path, document.path))
        if live is not None:
            return live.steps
        if document.rule in self.rules:
            return self.rules[document.rule]
        word = self.prior.get(document.id, IDENTITY_PATH)
        return RecordIdentity.expand_word(word)

    def _rule_name_for(self, document: DocumentRow) -> str:
        live = self._live_at.get((document.input_path, document.path))
        if live is not None:
            return live.rule
        return document.rule

    def _path_gone(self, document: DocumentRow) -> bool:
        return (document.input_path, document.path) not in self.kept

    def _reaches_hash_after_path(self, document: DocumentRow) -> bool:
        steps = self._steps_for(document)
        if IDENTITY_PATH not in steps or IDENTITY_HASH not in steps:
            return False
        return steps.index(IDENTITY_HASH) > steps.index(IDENTITY_PATH)

    @staticmethod
    def _hash_first(steps: tuple[str, ...]) -> bool:
        """Hash occurs before path, or the list has no path step."""
        if IDENTITY_HASH not in steps:
            return False
        if IDENTITY_PATH not in steps:
            return True
        return steps.index(IDENTITY_HASH) < steps.index(IDENTITY_PATH)

    def _warn_successors(
        self,
        document: DocumentRow,
        chosen: LiveFile,
        rest: list[LiveFile],
    ) -> None:
        others = ", ".join(
            item.path
            for item in sorted(rest, key=lambda item: (item.input_path, item.path))
        )
        self.warnings.append(
            f"Profile {self.profile} document {document.id} hash {document.hash} "
            f"moves to {chosen.path}. Other paths: {others}."
        )

    def _note_rule_warnings(self) -> None:
        """Once per rule name when the resolved list differs from the prior word."""
        seen: set[str] = set()
        for document in self._scoped:
            word = self.prior.get(document.id)
            if word is None:
                continue
            steps = self._steps_for(document)
            old = RecordIdentity.expand_word(word)
            if steps == old:
                continue
            rule = self._rule_name_for(document)
            if rule in seen:
                continue
            seen.add(rule)
            self.warnings.append(
                f"Profile {self.profile} match rule {rule} record_identity was "
                f"{RecordIdentity.text(old)} and this run uses {RecordIdentity.text(steps)}. "
                "Existing events stay."
            )

    def _stay(self, document: DocumentRow, live: LiveFile) -> str:
        facts = bool(document_drift(document, live))
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
        fresh: list[tuple[str, StoredFile, int, str]],
    ) -> list[PlannedRow]:
        presence = {
            document.id: (document.hash, document.presence) for document in self.documents
        }
        ordered: list[tuple[int, str, StoredFile, int, str]] = []
        for document_id in sorted(self._decisions):
            status, file, generation, identity = self._decisions[document_id]
            ordered.append((document_id, status, file, generation, identity))
            if status == EVENT_MISSING:
                presence[document_id] = (file.hash, PRESENCE_MISSING)
            elif status == EVENT_UNMATCHED:
                presence[document_id] = (file.hash, PRESENCE_UNMATCHED)
            else:
                presence[document_id] = (file.hash, PRESENCE_PRESENT)
        duplicate_counts: dict[str, int] = {}
        synthetic = 0
        for status, file, generation, identity in fresh:
            synthetic -= 1
            ordered.append((synthetic, status, file, generation, identity))
            if status == STATUS_DUPLICATE:
                duplicate_counts[file.hash] = duplicate_counts.get(file.hash, 0) + 1
                continue
            presence[synthetic] = (file.hash, PRESENCE_PRESENT)
        present_counts: dict[str, int] = {}
        for digest, state in presence.values():
            if state == PRESENCE_PRESENT:
                present_counts[digest] = present_counts.get(digest, 0) + 1
        rows: list[PlannedRow] = []
        for document_id, status, file, generation, identity in ordered:
            state = presence[document_id][1] if document_id in presence else None
            others = present_counts.get(file.hash, 0)
            if state == PRESENCE_PRESENT:
                others -= 1
            extras = duplicate_counts.get(file.hash, 0)
            if status == STATUS_DUPLICATE:
                extras -= 1
            rows.append(
                PlannedRow(
                    status=status,
                    document_id=None if document_id < 0 else document_id,
                    generation=generation,
                    file=file,
                    duplicates=others + extras,
                    identity=identity,
                )
            )
        return rows


@dataclass(frozen=True)
class LinkedMatch:
    """One walked file and the record row that describes it."""

    shelf: ShelfProfile
    row: PlannedRow
    found: InputFile
    resolved: FileVars
    var_plan: VarPlan


class _ProfileRun:
    """One profile's scan, plan, and optional write."""

    def __init__(
        self,
        shelf: ShelfProfile,
        steps: tuple[str, ...],
        rules: Mapping[str, tuple[str, ...]],
    ) -> None:
        self.shelf = shelf
        self.steps = steps
        self.rules = rules
        self.linked: list[LinkedMatch] = []
        self._logger = logging.getLogger(LOGGER_NAME)

    def plan(self, path: str | None, *, dry_run: bool = False) -> list[PlannedRow]:
        """Resolve this profile and compare it with the database. Kind files are not committed."""
        self.linked = []
        scans = self.shelf.scan(quick=False)
        walked = {str(result.config.path) for result in scans}
        kept_paths: list[str] = []
        ignored: set[tuple[str, str]] = set()
        kept: set[tuple[str, str]] = set()
        database_path = self.shelf.database_file.resolve()
        cache_path = self.shelf.cache_file.resolve()
        for result in scans:
            input_path = str(result.config.path)
            for found in result.results:
                kept_paths.append(found.path)
                location = (input_path, found.path)
                absolute = found.absolute.resolve()
                if absolute == database_path:
                    self._logger.warning("Skipping database file %s", database_path)
                    ignored.add(location)
                    continue
                if absolute == cache_path:
                    self._logger.warning("Skipping cache file %s", cache_path)
                    ignored.add(location)
                    continue
                kept.add(location)
        selector = KeptPath.from_paths(path, kept_paths)

        def accept(found: InputFile) -> bool:
            if not selector.matches(found.path):
                return False
            absolute = found.absolute.resolve()
            return absolute != database_path and absolute != cache_path

        walk = ShelfRuns([self.shelf]).resolved(
            None,
            groups=[scans],
            accept=accept,
            dry_run=dry_run,
        )
        live: list[LiveFile] = []
        seen: list[tuple[str, InputFile, FileVars, VarPlan]] = []
        for _shelf, result, found, matched, resolved, variables in walk:
            live.append(
                LiveFile.from_match(
                    result,
                    found,
                    kind=resolved.kind,
                    rule=matched.rule,
                    snapshot=variables.snapshot(resolved),
                    steps=self.rules.get(matched.rule, self.steps),
                )
            )
            seen.append((str(result.config.path), found, resolved, variables))
        with ShelfDatabase.open_read(self.shelf.database_file) as database:
            stored = database.identity()
            if stored is not None and not RecordIdentity.same(stored, self.steps):
                self._logger.warning(
                    "Profile %s record_identity was %s and this run uses %s. "
                    "Existing events stay.",
                    self.shelf.name,
                    stored,
                    RecordIdentity.text(self.steps),
                )
            prior: dict[int, str] = {}
            for event in database.events():
                if event.event == EVENT_OUTPUT:
                    continue
                prior[event.document_id] = event.identity
            plan = RecordPlan(
                database.documents(),
                live,
                kept,
                walked,
                selector,
                self.rules,
                prior,
                ignored,
                profile=self.shelf.name,
            )
            rows = plan.rows()
        for message in plan.warnings:
            self._logger.warning("%s", message)
        self.linked = self._linked(seen, rows)
        if path is not None and not rows and not self._selector_saw_file(selector, kept):
            raise SupershelfError(
                f"No kept file {path!r}",
                advice="Use a path from scan files, or run db import without a path.",
            )
        return rows

    def _linked(
        self,
        walked: list[tuple[str, InputFile, FileVars, VarPlan]],
        rows: list[PlannedRow],
    ) -> list[LinkedMatch]:
        by_location = {(row.file.input_path, row.file.path): row for row in rows}
        linked: list[LinkedMatch] = []
        for input_path, found, resolved, variables in walked:
            row = by_location.get((input_path, found.path))
            if row is None:
                continue
            linked.append(
                LinkedMatch(
                    shelf=self.shelf,
                    row=row,
                    found=found,
                    resolved=resolved,
                    var_plan=variables,
                )
            )
        return linked

    def write(self, rows: list[PlannedRow], *, dry_run: bool) -> None:
        """Apply rows that would change. A dry run and an empty plan create nothing."""
        changes = [row.change() for row in rows if row.change() is not None]
        if dry_run or (not changes and not self._identity_differs()):
            return
        recorded_at = datetime.now(timezone.utc).isoformat()
        meta = RecordIdentity.text(self.steps)
        with ShelfDatabase.open_write(self.shelf.database_file) as database:
            if changes:
                database.apply(changes, meta, recorded_at)
                return
            database.note_identity(meta)

    def _identity_differs(self) -> bool:
        with ShelfDatabase.open_read(self.shelf.database_file) as database:
            stored = database.identity()
        return stored is not None and not RecordIdentity.same(stored, self.steps)

    @staticmethod
    def _selector_saw_file(selector: KeptPath, kept: set[tuple[str, str]]) -> bool:
        return any(selector.matches(relative) for _input_path, relative in kept)

    def display(self, rows: list[PlannedRow], *, changes_only: bool) -> list[dict[str, object]]:
        """Clak rows for this profile."""
        shown = rows
        if changes_only:
            shown = [
                row
                for row in rows
                if row.status == STATUS_DUPLICATE or row.change() is not None
            ]
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
        runs = ShelfRuns.load(config, profile)
        built: list[_ProfileRun] = []
        for shelf in runs.shelves:
            steps = RecordIdentity.resolve(
                ShelfProfile.config_section(shelf.document),
                identity_flag,
                env,
            )
            rules = RecordIdentity.rule_lists(shelf.document, shelf.name, steps)
            built.append(_ProfileRun(shelf, steps, rules))
        return cls(built)

    def sources(self, path: str | None) -> list[LinkedMatch]:
        """Live files in walk order, with the record row for each. Writes nothing."""
        found: list[LinkedMatch] = []
        for run in self.runs:
            run.plan(path, dry_run=True)
            found.extend(run.linked)
        return found

    def status(self, path: str | None) -> list[dict[str, object]]:
        """Every in-scope row. Writes nothing."""
        rows: list[dict[str, object]] = []
        for run in self.runs:
            planned = run.plan(path, dry_run=True)
            rows.extend(run.display(planned, changes_only=False))
        return rows

    def run(self, path: str | None, *, dry_run: bool) -> list[dict[str, object]]:
        """Rows that would change. `--dry-run` skips the write."""
        rows: list[dict[str, object]] = []
        for run in self.runs:
            planned = run.plan(path, dry_run=dry_run)
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
        return cls(ShelfRuns.load(config, profile).shelves)

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
            selector = KeptPath.from_paths(path, [document.path for document in documents])
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
        selector = KeptPath.from_paths(path, known)
        return {
            document_id
            for document_id, paths in by_document.items()
            if any(selector.matches(relative) for relative in paths)
        }
