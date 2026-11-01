"""Walk profile inputs and collect the files each one keeps."""

from __future__ import annotations

import hashlib
import logging
import os
import stat
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)

from supershelf.common import resolve_user_path
from supershelf.constants import KEY_INPUTS, LOGGER_NAME
from supershelf.defaults import PACKAGED
from supershelf.errors import SupershelfError
from supershelf.profile import ShelfProfile
from supershelf.template import Template

_HASH_CHUNK_SIZE = 1024 * 1024
_Ancestor = tuple[int, int]


class InputSpec(BaseModel):
    """One `inputs` item. Unknown keys are errors."""

    model_config = ConfigDict(extra="forbid")

    path: str
    include: list[str] | None = None
    exclude: list[str] | None = None
    depth: int | None = None
    follow_symlinks: bool | None = None

    @field_validator("path")
    @classmethod
    def path_is_present(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("path is empty")
        return value

    @field_validator("depth")
    @classmethod
    def depth_is_zero_or_more(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 0:
            raise ValueError("depth must be 0 or greater")
        return value

    @model_validator(mode="after")
    def fill_packaged(self) -> InputSpec:
        """Omitted and null depth or follow_symlinks use the packaged values."""
        if self.depth is not None and self.follow_symlinks is not None:
            return self
        return self.model_copy(
            update={
                "depth": PACKAGED.input_depth if self.depth is None else self.depth,
                "follow_symlinks": (
                    PACKAGED.input_follow_symlinks
                    if self.follow_symlinks is None
                    else self.follow_symlinks
                ),
            }
        )


@dataclass(frozen=True)
class ResolvedInput:
    """Input settings after the path template has been resolved."""

    path: Path
    include: list[str] | None
    exclude: list[str] | None
    depth: int
    follow_symlinks: bool

    def keeps(self, relative: str) -> bool:
        path = PurePosixPath(relative)
        if self.include is not None and not any(
            path.full_match(pattern) for pattern in self.include
        ):
            return False
        if self.exclude is not None and any(
            path.full_match(pattern) for pattern in self.exclude
        ):
            return False
        return True


@dataclass
class InputFile:
    """One kept file. `path` is relative to the input directory."""

    path: str
    absolute: Path
    name: str
    stem: str
    suffix: str
    directory: str
    mtime: str | None = None
    ctime: str | None = None
    sha256: str | None = None

    @classmethod
    def from_relative(cls, relative: str, absolute: Path) -> InputFile:
        pure = PurePosixPath(relative)
        parent = pure.parent.as_posix()
        return cls(
            path=relative,
            absolute=absolute,
            name=pure.name,
            stem=pure.stem,
            suffix=pure.suffix,
            directory="" if parent == "." else parent,
        )

    def read_metadata(self, logger: logging.Logger) -> bool:
        """Fill mtime, ctime, and sha256. False when the file cannot be used."""
        try:
            info = self.absolute.stat()
            digest = self._sha256()
        except OSError as exc:
            logger.warning("Cannot read %s: %s", self.absolute, exc)
            return False
        if info.st_size == 0:
            return False
        self.mtime = self._iso_time(info.st_mtime_ns)
        self.ctime = self._iso_time(info.st_ctime_ns)
        self.sha256 = digest
        return True

    def _sha256(self) -> str:
        digest = hashlib.sha256()
        with self.absolute.open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _iso_time(nanoseconds: int) -> str:
        seconds, nanos = divmod(int(nanoseconds), 1_000_000_000)
        moment = datetime.fromtimestamp(seconds, timezone.utc).replace(
            microsecond=nanos // 1000
        )
        return moment.isoformat()


@dataclass(frozen=True)
class InputScanResult:
    """Files kept for one input."""

    profile: str
    index: int
    config: ResolvedInput
    results: list[InputFile]


class KeptPath:
    """Exact path, or a prefix. None matches every relative path."""

    def __init__(self, text: str | None, *, exact: bool) -> None:
        self.text = text
        self.exact = exact

    @classmethod
    def from_paths(cls, text: str | None, paths: list[str]) -> KeptPath:
        """None keeps every path. An exact known path wins over a prefix."""
        if text is None:
            return cls(None, exact=False)
        return cls(text, exact=text in paths)

    @classmethod
    def narrow_groups(
        cls,
        groups: list[list[InputScanResult]],
        path: str | None,
    ) -> list[list[InputScanResult]]:
        """Narrow scan groups. No match is an error. None returns `groups`."""
        paths = [
            found.path
            for scans in groups
            for scan in scans
            for found in scan.results
        ]
        return cls.from_paths(path, paths).narrow(groups)

    def matches(self, relative: str) -> bool:
        """Whether this relative path is selected."""
        if self.text is None:
            return True
        if self.exact:
            return relative == self.text
        return relative.startswith(self.text)

    def narrow(
        self,
        groups: list[list[InputScanResult]],
    ) -> list[list[InputScanResult]]:
        """Keep matching files in every input. No match is an error.

        None returns `groups` unchanged. Empty inputs stay empty.
        """
        if self.text is None:
            return groups
        narrowed: list[list[InputScanResult]] = []
        seen = 0
        for scans in groups:
            group: list[InputScanResult] = []
            for scan in scans:
                chosen = [found for found in scan.results if self.matches(found.path)]
                seen += len(chosen)
                group.append(replace(scan, results=chosen))
            narrowed.append(group)
        if seen == 0:
            raise SupershelfError(f"No kept file {self.text!r}")
        return narrowed


class InputScanner:
    """Scan one profile's inputs."""

    def __init__(self, profile: ShelfProfile, *, quick: bool = False) -> None:
        self.profile = profile
        self.quick = quick
        self._logger = logging.getLogger(LOGGER_NAME)

    def run(self) -> list[InputScanResult]:
        results: list[InputScanResult] = []
        for index, item in enumerate(self._raw_inputs(), start=1):
            resolved = self._resolve_input(self._parse_input(index, item))
            if resolved is None:
                continue
            files = self._walk(resolved)
            if not self.quick:
                files = self._with_metadata(files)
            results.append(
                InputScanResult(
                    profile=self.profile.name,
                    index=index,
                    config=resolved,
                    results=files,
                )
            )
        return results

    def _raw_inputs(self) -> list:
        document = self.profile.document
        raw = document.get(KEY_INPUTS)
        if raw is None:
            raise SupershelfError(
                f"Profile {self.profile.name} has no inputs",
                advice=f"Add an inputs list to {self.profile.path}.",
            )
        if not isinstance(raw, list):
            raise SupershelfError(f"Profile {self.profile.name} inputs must be a list")
        if not raw:
            raise SupershelfError(f"Profile {self.profile.name} inputs is empty")
        return raw

    def _parse_input(self, index: int, item: object) -> InputSpec:
        try:
            return InputSpec.model_validate(item)
        except ValidationError as exc:
            raise SupershelfError(
                f"Invalid input {index} in {self.profile.path}: {exc}"
            ) from exc

    def _resolve_input(self, spec: InputSpec) -> ResolvedInput | None:
        rendered = Template(self.profile.scope).render(spec.path).strip()
        if not rendered:
            raise SupershelfError("inputs.path is empty")
        candidate = resolve_user_path(rendered, self.profile.root_dir)
        if candidate.is_symlink() or candidate.exists():
            if not candidate.is_dir():
                raise SupershelfError(f"Input path is not a directory: {candidate}")
        else:
            self._logger.warning("Input directory is missing, skipping %s", candidate)
            return None
        return ResolvedInput(
            path=candidate.resolve(),
            include=spec.include,
            exclude=spec.exclude,
            depth=spec.depth,
            follow_symlinks=spec.follow_symlinks,
        )

    def _walk(self, spec: ResolvedInput) -> list[InputFile]:
        try:
            root_info = spec.path.stat()
        except OSError as exc:
            self._logger.warning("Cannot read directory %s: %s", spec.path, exc)
            return []
        files: list[InputFile] = []
        ancestors = ((root_info.st_dev, root_info.st_ino),)
        stack: list[tuple[Path, str, tuple[_Ancestor, ...]]] = [
            (spec.path, "", ancestors)
        ]
        while stack:
            directory, rel_dir, trail = stack.pop()
            entries = self._entries(directory)
            if entries is None:
                continue
            for entry in entries:
                rel = entry.name if not rel_dir else f"{rel_dir}/{entry.name}"
                self._visit(entry, rel, trail, spec, files, stack)
        files.sort(key=lambda item: item.path)
        return files

    def _entries(self, directory: Path) -> list[os.DirEntry[str]] | None:
        try:
            with os.scandir(directory) as scanned:
                entries = list(scanned)
        except OSError as exc:
            self._logger.warning("Cannot read directory %s: %s", directory, exc)
            return None
        entries.sort(key=lambda entry: entry.name)
        return entries

    def _visit(
        self,
        entry: os.DirEntry[str],
        rel: str,
        ancestors: tuple[_Ancestor, ...],
        spec: ResolvedInput,
        files: list[InputFile],
        stack: list[tuple[Path, str, tuple[_Ancestor, ...]]],
    ) -> None:
        try:
            is_link = entry.is_symlink()
        except OSError as exc:
            self._logger.warning("Cannot read %s: %s", entry.path, exc)
            return
        if is_link and not spec.follow_symlinks:
            return
        try:
            info = entry.stat(follow_symlinks=True)
        except OSError as exc:
            self._logger.warning("Cannot read %s: %s", entry.path, exc)
            return
        if stat.S_ISDIR(info.st_mode):
            ident = (info.st_dev, info.st_ino)
            if ident in ancestors:
                self._logger.warning("Symlink cycle at %s, skipping", entry.path)
                return
            # Level 1 is the input directory. The first subdirectory is level 2.
            child_level = rel.count("/") + 2
            if spec.depth != 0 and child_level > spec.depth:
                return
            stack.append((Path(entry.path), rel, ancestors + (ident,)))
            return
        if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
            return
        if not spec.keeps(rel):
            return
        files.append(InputFile.from_relative(rel, Path(entry.path)))

    def _with_metadata(self, files: list[InputFile]) -> list[InputFile]:
        return [item for item in files if item.read_metadata(self._logger)]
