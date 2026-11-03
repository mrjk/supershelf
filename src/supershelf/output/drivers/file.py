"""File destinations: copy, symlink, or hardlink under one directory."""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from supershelf.common import render_user_path
from supershelf.constants import (
    EVENT_OUTPUT,
    FIELD_PATH,
    KEY_ROOT_DIR,
    OP_COPY,
    OP_HARDLINK,
    OP_SYMLINK,
    OUTPUT_OPERATIONS,
    VAR_CONFIG,
    VAR_FILE,
)
from supershelf.database import EventRow, OutputPrevious, ShelfDatabase
from supershelf.errors import OutputConfigError, OutputResolveError, VarCandidateError, VarResolveError
from supershelf.output.engine import (
    SHARED_KEYS,
    STATUS_CONFLICT,
    STATUS_REPLACE,
    STATUS_SKIP,
    STATUS_UNCHANGED,
    STATUS_WRITE,
    OutputAction,
    OutputContext,
    OutputDriver,
)
from supershelf.profile import ShelfProfile

_FILE_KEYS = SHARED_KEYS | {"path", "layout", "operation", "on_conflict"}
_CONFLICTS = frozenset({"error", "skip", "overwrite"})
_DEFAULT_LAYOUT = "{{ " + VAR_FILE + "." + FIELD_PATH + " }}"
_ROOT_NAME = VAR_CONFIG + "." + KEY_ROOT_DIR
_HASH_CHUNK = 1024 * 1024


@dataclass
class PreparedFile:
    """Path, layout, and conflict rule for one file output. Rendered once."""

    name: str
    root: Path
    layout: str
    operation: str
    on_conflict: str


class FileOutputDriver(OutputDriver):
    """Write a file tree and record the apply with append_output."""

    name = "file"

    def check(self, spec: Mapping[str, Any]) -> None:
        """Reject keys, operations, and conflict words this driver does not know."""
        name = spec.get("name")
        label = name if isinstance(name, str) and name.strip() else "file"
        unknown = set(spec) - _FILE_KEYS
        if unknown:
            listed = ", ".join(sorted(str(key) for key in unknown))
            raise OutputConfigError(
                f"Output {label!r} does not accept {listed}",
                advice="The file driver accepts path, layout, operation, and on_conflict.",
            )
        path = spec.get("path")
        if not isinstance(path, str) or not path.strip():
            raise OutputConfigError(
                f"Output {label!r} path is required",
                advice=f"Set path to a profile path template. A relative path resolves from {_ROOT_NAME}.",
            )
        self._word(spec, "layout", label, required=False)
        self._choice(spec, "operation", label, OUTPUT_OPERATIONS, OP_COPY)
        self._choice(spec, "on_conflict", label, _CONFLICTS, "error")

    def prepare(self, spec: Mapping[str, Any], profile: ShelfProfile) -> PreparedFile:
        """Render path once. A missing directory is created only on a real write."""
        name = str(spec.get("name", "file")).strip() or "file"
        root = render_user_path(
            str(spec["path"]),
            profile.scope,
            profile.root_dir,
            empty_message=f"Output {name!r} path is empty",
            error=OutputConfigError,
            advice=f"Set path to a directory under {_ROOT_NAME}.",
            resolve=True,
        )
        if root.exists() and not root.is_dir():
            raise OutputConfigError(
                f"Output {name!r} path {root} is not a directory",
                advice="Point path at a directory.",
            )
        layout = spec.get("layout")
        if layout is None:
            layout = _DEFAULT_LAYOUT
        operation = spec.get("operation") or OP_COPY
        on_conflict = spec.get("on_conflict") or "error"
        return PreparedFile(name, root, str(layout), str(operation), str(on_conflict))

    def plan(self, prepared: Any, context: OutputContext) -> OutputAction | None:
        """Choose write, replace, unchanged, skip, or conflict. Do not touch the disk."""
        if not isinstance(prepared, PreparedFile):
            raise OutputResolveError(
                f"Output {context.output_name} is not a file output",
                advice="This is a bug. Report it.",
            )
        dest = self._destination(prepared, context)
        source = context.match.found.absolute
        relative = context.match.found.path
        self._reject_same(prepared.name, relative, dest, source)
        self._reject_directory(prepared.name, dest)
        self._reject_parent(prepared.name, dest)
        return self._decide(prepared, context, dest, source)

    def apply(self, action: OutputAction, dry_run: bool = False) -> None:
        """Write the file, then append the output event. A dry run does neither."""
        if dry_run:
            return
        if (
            action.previous is None
            or action.document_id is None
            or action.source is None
            or action.database is None
        ):
            raise OutputResolveError(
                f"Output {action.output} {action.path} cannot be written",
                advice="This is a bug. Report it.",
            )
        dest = Path(action.dest)
        if action.status == STATUS_REPLACE and (dest.exists() or dest.is_symlink()):
            dest.unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._place(action, dest)
        with ShelfDatabase.open_write(action.database) as database:
            database.append_output(
                action.document_id,
                action.output,
                action.operation,
                action.dest,
                action.source_hash,
                action.previous,
                recorded_at=action.recorded_at,
            )

    def _decide(
        self,
        prepared: PreparedFile,
        context: OutputContext,
        dest: Path,
        source: Path,
    ) -> OutputAction:
        dest_text = str(dest)
        operation = prepared.operation
        source_hash = context.match.row.file.hash
        prior = self._prior(context.events, context.document_id, context.output_name)
        claim = self._claim(context.events, dest_text)
        if claim is not None and (
            context.document_id is None
            or claim.document_id != context.document_id
            or claim.output_name != context.output_name
        ):
            profile = context.shelf.name
            live = context.match.found.path
            raise OutputResolveError(
                f"Destination {dest_text} belongs to profile {profile} {claim.path} "
                f"output {claim.output_name} and profile {profile} {live} "
                f"output {context.output_name}",
                advice="Choose another layout. overwrite cannot take a path recorded for someone else.",
            )
        matched = (
            prior is not None
            and prior.destination == dest_text
            and prior.operation == operation
            and prior.source_hash == source_hash
        )
        present = dest.exists() or dest.is_symlink()
        if matched and self._disk_matches(operation, dest, source, source_hash):
            return self._action(
                prepared,
                context,
                status=STATUS_UNCHANGED,
                operation=operation,
                dest=dest_text,
            )
        if matched and prior is not None:
            return self._conflict(prepared, context, dest_text, ours=True, prior=prior)
        if prior is not None and prior.destination == dest_text and present:
            return self._action(
                prepared,
                context,
                status=STATUS_REPLACE,
                operation=operation,
                dest=dest_text,
                previous=OutputPrevious(True, True, prior.operation, prior.source_hash),
            )
        if not present:
            if claim is not None:
                previous = OutputPrevious(False, True, claim.operation, claim.source_hash)
            else:
                previous = OutputPrevious(False, False)
            return self._action(
                prepared,
                context,
                status=STATUS_WRITE,
                operation=operation,
                dest=dest_text,
                previous=previous,
            )
        return self._conflict(prepared, context, dest_text, ours=False, prior=None)

    def _conflict(
        self,
        prepared: PreparedFile,
        context: OutputContext,
        dest_text: str,
        *,
        ours: bool,
        prior: EventRow | None,
    ) -> OutputAction:
        operation = prepared.operation
        if prepared.on_conflict == "skip":
            return self._action(
                prepared, context, status=STATUS_SKIP, operation=operation, dest=dest_text
            )
        if prepared.on_conflict == "error":
            return self._action(
                prepared, context, status=STATUS_CONFLICT, operation=operation, dest=dest_text
            )
        if ours and prior is not None:
            previous = OutputPrevious(True, True, prior.operation, prior.source_hash)
        else:
            previous = OutputPrevious(True, False)
        return self._action(
            prepared,
            context,
            status=STATUS_REPLACE,
            operation=operation,
            dest=dest_text,
            previous=previous,
        )

    def _action(
        self,
        prepared: PreparedFile,
        context: OutputContext,
        *,
        status: str,
        operation: str,
        dest: str,
        previous: OutputPrevious | None = None,
    ) -> OutputAction:
        """Plan one file action. dest stays absolute. The row prints under root."""
        return context.action(
            status=status,
            operation=operation,
            dest=dest,
            dest_root=prepared.root,
            previous=previous,
        )

    def _destination(self, prepared: PreparedFile, context: OutputContext) -> Path:
        rendered = self._render(prepared, context)
        text = rendered.strip().replace("\\", "/")
        relative = context.match.found.path
        if not text:
            raise OutputResolveError(
                f"Output {prepared.name} layout for {relative} is empty",
                advice="Set layout to a relative path.",
            )
        if text.startswith("/") or Path(text).is_absolute():
            raise OutputResolveError(
                f"Output {prepared.name} layout for {relative} is absolute",
                advice="Write a path relative to the output directory.",
            )
        parts = text.split("/")
        for part in parts:
            if part in ("", ".", ".."):
                raise OutputResolveError(
                    f"Output {prepared.name} layout for {relative} has segment {part!r}",
                    advice="Do not use an empty segment, ., or .. in the layout.",
                )
        dest = prepared.root.joinpath(*parts)
        try:
            dest.relative_to(prepared.root)
        except ValueError as exc:
            raise OutputResolveError(
                f"Output {prepared.name} layout for {relative} leaves {prepared.root}",
                advice="Keep the layout inside path.",
            ) from exc
        return dest

    def _render(self, prepared: PreparedFile, context: OutputContext) -> str:
        try:
            return context.render(prepared.layout)
        except VarCandidateError as exc:
            raise OutputResolveError(
                f"Output {prepared.name} {context.match.found.path} layout failed: {exc}",
                advice="Check the layout template. A missing name such as __date__ fails the layout.",
            ) from exc
        except VarResolveError as exc:
            raise OutputResolveError(str(exc), advice=exc.advice) from exc

    @staticmethod
    def _prior(events: list[EventRow], document_id: int | None, output_name: str) -> EventRow | None:
        if document_id is None:
            return None
        found = [
            event
            for event in events
            if event.event == EVENT_OUTPUT
            and event.document_id == document_id
            and event.output_name == output_name
        ]
        if not found:
            return None
        return found[-1]

    @staticmethod
    def _claim(events: list[EventRow], destination: str) -> EventRow | None:
        found = [
            event
            for event in events
            if event.event == EVENT_OUTPUT and event.destination == destination
        ]
        if not found:
            return None
        return found[-1]

    def _disk_matches(self, operation: str, dest: Path, source: Path, source_hash: str) -> bool:
        if dest.is_symlink():
            if operation != OP_SYMLINK:
                return False
            return os.readlink(dest) == str(source)
        if not dest.is_file():
            return False
        if operation == OP_COPY:
            return self._sha256(dest) == source_hash
        if operation == OP_HARDLINK:
            source_stat = source.stat()
            dest_stat = dest.stat()
            return source_stat.st_ino == dest_stat.st_ino and source_stat.st_dev == dest_stat.st_dev
        return False

    def _place(self, action: OutputAction, dest: Path) -> None:
        source = action.source
        if source is None:
            raise OutputResolveError(
                f"Output {action.output} {action.path} has no source",
                advice="This is a bug. Report it.",
            )
        if action.operation == OP_COPY:
            shutil.copy2(source, dest)
            return
        if action.operation == OP_SYMLINK:
            dest.symlink_to(source)
            return
        try:
            os.link(source, dest)
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                raise OutputResolveError(
                    f"Output {action.output} hardlink of {action.path} crossed devices",
                    advice="Use copy.",
                ) from exc
            raise OutputResolveError(
                f"Output {action.output} hardlink of {action.path} failed: {exc}",
                advice="Use copy.",
            ) from exc

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _word(spec: Mapping[str, Any], key: str, label: str, *, required: bool) -> None:
        raw = spec.get(key)
        if raw is None:
            if required:
                raise OutputConfigError(
                    f"Output {label!r} {key} is required",
                    advice=f"Set {key} to a string.",
                )
            return
        if not isinstance(raw, str):
            raise OutputConfigError(
                f"Output {label!r} {key} must be a string",
                advice=f"Set {key} to a string.",
            )

    @staticmethod
    def _choice(
        spec: Mapping[str, Any],
        key: str,
        label: str,
        allowed: frozenset[str] | tuple[str, ...],
        default: str,
    ) -> None:
        raw = spec.get(key)
        if raw is None:
            return
        if not isinstance(raw, str) or raw not in allowed:
            listed = ", ".join(allowed)
            raise OutputConfigError(
                f"Output {label!r} {key} {raw!r} is unknown",
                advice=f"Use {listed}. Omitted is {default}.",
            )

    @staticmethod
    def _reject_same(name: str, relative: str, dest: Path, source: Path) -> None:
        if dest.parent.resolve() == source.parent.resolve() and dest.name == source.name:
            raise OutputResolveError(
                f"Output {name} destination is the source file {relative}",
                advice="Choose a path outside that file.",
            )

    @staticmethod
    def _reject_directory(name: str, dest: Path) -> None:
        if dest.is_dir() and not dest.is_symlink():
            raise OutputResolveError(
                f"Output {name} destination {dest} is a directory",
                advice="Choose a layout that writes a file.",
            )

    @staticmethod
    def _reject_parent(name: str, dest: Path) -> None:
        current = dest.parent
        while not current.exists():
            if current.parent == current:
                break
            current = current.parent
        if current.exists() and not current.is_dir():
            raise OutputResolveError(
                f"Output {name} parent of {dest} is a file",
                advice="Remove the file that blocks the destination parent.",
            )
