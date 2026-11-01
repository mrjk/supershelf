"""content_meta rows. The in-memory bag is checked first."""

from datetime import datetime, timezone
from pathlib import Path

from supershelf.database import ShelfDatabase


class ContentMetaCache:
    """Read and write one driver's payload. A dry run does not create or migrate."""

    def __init__(self, path: Path | None, *, dry_run: bool) -> None:
        self._path = path
        self._dry_run = dry_run

    def read(
        self,
        digest: str,
        driver: str,
        options_key: str,
    ) -> tuple[str | None, str | None] | None:
        """None when the file is absent, the schema is 1, or the row is missing."""
        if self._path is None or not self._path.is_file():
            return None
        with ShelfDatabase.open_read(self._path) as database:
            return database.read_content_meta(digest, driver, options_key)

    def store(
        self,
        digest: str,
        driver: str,
        options_key: str,
        *,
        payload: str | None,
        error: str | None,
    ) -> None:
        """Insert one row. Dry-run and a missing path do nothing."""
        if self._dry_run or self._path is None:
            return
        extracted_at = datetime.now(timezone.utc).isoformat()
        with ShelfDatabase.open_write(self._path) as database:
            database.store_content_meta(
                digest,
                driver,
                options_key,
                payload,
                error,
                extracted_at,
            )
