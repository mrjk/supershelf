"""PATH-scoped file list passed from one scan step to the next."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from supershelf.constants import (
    EVENT_GENERATION,
    EVENT_MISSING,
    EVENT_MOVE,
    EVENT_NEW,
    STATUS_DUPLICATE,
    STATUS_REFRESH,
)
from supershelf.errors import SupershelfError
from supershelf.profile import ShelfProfile
from supershelf.scan.match import FileMatch
from supershelf.scan.walk import InputFile, InputScanResult, KeptPath
from supershelf.vars.resolve import FileVars, VarPlan

# Identity rows scan files prints. Kind and var drift are later steps.
FILE_CHANGE_STATUSES = frozenset(
    {
        EVENT_NEW,
        EVENT_GENERATION,
        EVENT_MOVE,
        EVENT_MISSING,
        STATUS_REFRESH,
        STATUS_DUPLICATE,
    }
)
# Match rows that hand a file to scan vars besides the identity list.
KIND_CHANGE_STATUSES = frozenset({EVENT_NEW, "kind", "rule"})


@dataclass
class SelectedFile:
    """One kept file. Later steps fill match and vars on this object."""

    result: InputScanResult
    found: InputFile
    identity_status: str | None = None
    match: FileMatch | None = None
    kind_status: str | None = None
    resolved: FileVars | None = None
    var_plan: VarPlan | None = None
    vars_changed: bool = False

    @property
    def profile(self) -> str:
        return self.result.profile

    @property
    def index(self) -> int:
        return self.result.index

    def location(self) -> tuple[str, str]:
        """Absolute input directory plus the relative path."""
        return (str(self.result.config.path), self.found.path)


@dataclass
class FileSelection:
    """Inventory in PATH scope, and the working list the next step receives.

    ``inventory`` stays the full scoped walk so a later flag can add a file back.
    ``files`` is the list this step hands to the next one.
    """

    shelves: list[ShelfProfile]
    selector: KeptPath
    path: str | None
    hashed: bool
    groups: list[list[InputScanResult]]
    inventory: list[SelectedFile]
    files: list[SelectedFile]
    ignored: dict[str, set[tuple[str, str]]] = field(default_factory=dict)
    planned: dict[str, list] = field(default_factory=dict)
    seen: dict[str, list[SelectedFile]] = field(default_factory=dict)
    warnings: dict[str, list[str]] = field(default_factory=dict)
    prepared: list = field(default_factory=list)
    files_ready: bool = False
    match_ready: bool = False
    vars_ready: bool = False
    file_warnings_logged: bool = False

    def intersect(self, path: str | None, *, require_kept: bool) -> FileSelection:
        """Keep files ``path`` selects. None leaves this selection as it is."""
        if path is None or path == self.path:
            return self
        paths = [item.found.path for item in self.inventory]
        selector = KeptPath.from_paths(path, paths)
        if require_kept and not any(selector.matches(item) for item in paths):
            raise SupershelfError(f"No kept file {path!r}")
        groups = _filter_groups(selector, self.groups)
        inventory = [item for item in self.inventory if selector.matches(item.found.path)]
        files = [item for item in self.files if selector.matches(item.found.path)]
        return FileSelection(
            shelves=self.shelves,
            selector=selector,
            path=path,
            hashed=self.hashed,
            groups=groups,
            inventory=inventory,
            files=files,
            ignored=self.ignored,
            planned=self.planned,
            seen=self.seen,
            warnings=self.warnings,
            prepared=self.prepared,
            files_ready=self.files_ready,
            match_ready=self.match_ready,
            vars_ready=self.vars_ready,
            file_warnings_logged=self.file_warnings_logged,
        )

    def ensure_hashed(self) -> None:
        """Fill sha256, mtime, and ctime on a quick list. Already hashed lists stay."""
        if self.hashed:
            return
        import logging

        from supershelf.constants import LOGGER_NAME

        logger = logging.getLogger(LOGGER_NAME)
        kept: list[SelectedFile] = []
        for item in self.inventory:
            if item.found.sha256 or item.found.read_metadata(logger):
                kept.append(item)
        drop = {id(item) for item in self.inventory} - {id(item) for item in kept}
        self.inventory = kept
        self.files = [item for item in self.files if id(item) not in drop]
        kept_ids = {id(item.found) for item in kept}
        groups: list[list[InputScanResult]] = []
        for scans in self.groups:
            group: list[InputScanResult] = []
            for scan in scans:
                chosen = [found for found in scan.results if id(found) in kept_ids]
                group.append(replace(scan, results=chosen))
            groups.append(group)
        self.groups = groups
        self.hashed = True


def filter_groups(
    selector: KeptPath,
    groups: list[list[InputScanResult]],
) -> list[list[InputScanResult]]:
    """Drop files outside ``selector``. Empty inputs stay. Never raises."""
    if selector.text is None:
        return groups
    return _filter_groups(selector, groups)


def _filter_groups(
    selector: KeptPath,
    groups: list[list[InputScanResult]],
) -> list[list[InputScanResult]]:
    narrowed: list[list[InputScanResult]] = []
    for scans in groups:
        group: list[InputScanResult] = []
        for scan in scans:
            chosen = [found for found in scan.results if selector.matches(found.path)]
            group.append(replace(scan, results=chosen))
        narrowed.append(group)
    return narrowed


def selection_from_groups(
    shelves: list[ShelfProfile],
    groups: list[list[InputScanResult]],
    path: str | None,
    *,
    hashed: bool,
    require_kept: bool,
    allow_document: bool,
    in_scope,
) -> FileSelection:
    """Build a selection. ``in_scope(selector, groups)`` covers document-only paths."""
    paths = [
        found.path
        for scans in groups
        for scan in scans
        for found in scan.results
    ]
    selector = KeptPath.from_paths(path, paths)
    if path is not None and require_kept and not any(selector.matches(item) for item in paths):
        raise SupershelfError(f"No kept file {path!r}")
    if path is not None and allow_document and not in_scope(selector, groups):
        raise SupershelfError(f"No kept file {path!r}")
    scoped = filter_groups(selector, groups)
    inventory: list[SelectedFile] = []
    ignored: dict[str, set[tuple[str, str]]] = {}
    for shelf, scans in zip(shelves, scoped, strict=True):
        database_path = shelf.database_file.resolve()
        cache_path = shelf.cache_file.resolve()
        bucket: set[tuple[str, str]] = set()
        for result in scans:
            input_path = str(result.config.path)
            for found in result.results:
                item = SelectedFile(result=result, found=found)
                inventory.append(item)
                absolute = found.absolute.resolve()
                if absolute == database_path or absolute == cache_path:
                    bucket.add(item.location())
        ignored[shelf.name] = bucket
    return FileSelection(
        shelves=shelves,
        selector=selector,
        path=path,
        hashed=hashed,
        groups=scoped,
        inventory=inventory,
        files=list(inventory),
        ignored=ignored,
    )
