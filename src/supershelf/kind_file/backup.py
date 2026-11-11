"""Pre-write copies of kind files under the process cwd."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from supershelf.errors import VarConfigError

BACKUP_DIR_NAME = ".backups"
_STAMP_FORMAT = "%y%m%d-%H%M%S"


def backup_kind_file(path: Path, *, now: datetime | None = None) -> Path:
    """Copy an existing kind file into ``{cwd}/.backups/{name}.{stamp}``.

    When that name is taken, append ``-2``, ``-3``, and so on.
    """
    stamp = (now or datetime.now()).strftime(_STAMP_FORMAT)
    folder = Path.cwd() / BACKUP_DIR_NAME
    base = f"{path.name}.{stamp}"
    target = folder / base
    if target.exists():
        index = 2
        while True:
            candidate = folder / f"{base}-{index}"
            if not candidate.exists():
                target = candidate
                break
            index += 1
    try:
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    except OSError as exc:
        raise VarConfigError(
            f"Could not back up kind file {path} to {target}: {exc}",
            advice="Fix permissions on .backups, or pass --no-backup.",
        ) from exc
    return target
