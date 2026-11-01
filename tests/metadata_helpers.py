"""Shared builders for metadata and variable tests. Tools are not spawned."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from supershelf.errors import VarCandidateError
from supershelf.match import FileMatch, Matcher
from supershelf.metadata.process import ProcessRunner
from supershelf.scan import InputFile
from supershelf.vars import VarPlan

_MTIME = "2026-01-01T00:00:00+00:00"
_CTIME = "2026-01-02T00:00:00+00:00"


class FakeRunner(ProcessRunner):
    """Records argv. Does not spawn the named program."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[str]] = []
        self.which_calls: list[str] = []
        self.available: set[str] = set()
        self.output: dict[str, str] = {}
        self.codes: dict[str, int] = {}

    def which(self, name: str) -> str | None:
        self.which_calls.append(name)
        if name in self.available or name in self.output:
            return name
        return None

    def run(self, argv: list[str], timeout: float) -> str:
        del timeout
        self.calls.append(list(argv))
        program = argv[0]
        code = self.codes.get(program, 0)
        if code != 0:
            raise VarCandidateError(f"{program} exited {code}")
        return self.output.get(program, "")


def input_file(
    relative: str = "a.txt",
    absolute: Path | None = None,
    digest: str = "abc",
) -> InputFile:
    """A kept file with ctime, mtime, and a hash already filled in."""
    path = Path("/tmp") / relative if absolute is None else absolute
    item = InputFile.from_relative(relative, path)
    item.mtime = _MTIME
    item.ctime = _CTIME
    item.sha256 = digest
    return item


def var_plan(
    document: dict[str, object],
    root: Path,
    runner: ProcessRunner | None = None,
    scope: dict[str, object] | None = None,
    *,
    mode: str | None = None,
    dry_run: bool = False,
    environ: Mapping[str, str] | None = None,
    profile_dir: bool = False,
    database: bool = False,
) -> VarPlan:
    """One plan named work. `database` adds the profile dir and database path."""
    matcher = Matcher.from_document(document, "work")
    full: dict[str, object] = {
        "__root_dir__": str(root),
        "__profile__": "work",
    }
    if profile_dir or database:
        full["__profile_dir__"] = str(root)
    if database:
        full["__database_file__"] = str(root / "profile.work.sqlite")
    if scope:
        full.update(scope)
    return VarPlan.from_document(
        document,
        "work",
        matcher,
        root,
        full,
        mode=mode,
        dry_run=dry_run,
        environ=environ,
        runner=runner,
    )


def resolve_values(
    plan: VarPlan,
    file: InputFile | None = None,
    match: FileMatch | None = None,
    *,
    use_file_path: bool = False,
) -> dict[str, str]:
    """Resolve one file. A missing match uses kind note and rule notes."""
    chosen = input_file() if file is None else file
    if match is None:
        path = chosen.path if use_file_path else "a.txt"
        match = FileMatch("work", 1, path, "note", "notes", {})
    return dict(plan.resolve(chosen, match, Path("/in")).items)
