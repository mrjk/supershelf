"""One kind-file row."""

from __future__ import annotations


class KindLine:
    """One kind-file row. `sha` is empty when the file has no digest yet."""

    def __init__(self, path: str, sha: str, cells: dict[str, str]) -> None:
        self.path = path
        self.sha = sha
        self.cells = cells
