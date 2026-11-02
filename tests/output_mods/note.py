"""A file-free driver used by output tests."""

from pathlib import Path

from supershelf.database import OutputPrevious, ShelfDatabase
from supershelf.errors import OutputConfigError
from supershelf.output import SHARED_KEYS, STATUS_WRITE, OutputAction, OutputContext, OutputDriver

_KEYS = SHARED_KEYS | {"label"}


class NoteDriver(OutputDriver):
    """Write a text note next to the profile and record it as a copy."""

    name = "note"

    def check(self, spec):
        unknown = set(spec) - _KEYS
        if unknown:
            listed = ", ".join(sorted(str(key) for key in unknown))
            raise OutputConfigError(
                f"Output driver note does not accept {listed}",
                advice="The note driver accepts label.",
            )
        label = spec.get("label", "note")
        if not isinstance(label, str) or not label.strip():
            raise OutputConfigError(
                "Output note label must be a string",
                advice="Set label to the note text.",
            )

    def prepare(self, spec, profile):
        label = spec.get("label", "note")
        return label if isinstance(label, str) else "note"

    def plan(self, prepared, context: OutputContext) -> OutputAction:
        dest = context.shelf.root_dir / "notes" / f"{context.match.found.path}.txt"
        action = context.action(
            status=STATUS_WRITE,
            operation="copy",
            dest=str(dest),
            previous=OutputPrevious(False, False),
        )
        action.extra["label"] = prepared if isinstance(prepared, str) else "note"
        return action

    def apply(self, action: OutputAction, dry_run: bool = False) -> None:
        if dry_run:
            return
        if action.document_id is None or action.previous is None or action.database is None:
            raise OutputConfigError(
                "Output note is missing a document",
                advice="Run record run.",
            )
        dest = Path(action.dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(action.extra.get("label", "note"), encoding="utf-8")
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


DRIVERS = [NoteDriver]
