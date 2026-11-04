"""YAML kind-file reader and writer."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from supershelf.errors import VarConfigError
from supershelf.kind_file.format import KindMappingFormat, KindParsed
from supershelf.kind_file.line import KindLine


class KindYaml(KindMappingFormat):
    """A bare list. .yml is the same text as .yaml."""

    suffixes = (".yaml", ".yml")

    def parse(
        self,
        path: Path,
        text: str,
        logger: logging.Logger,
        sep: str,
    ) -> KindParsed:
        """A bare list of path, sha, and vars. `sep` is unused."""
        del sep
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise VarConfigError(
                f"Invalid YAML in {path}: {exc}",
                advice="Use a bare list of path and vars items.",
            ) from exc
        if raw is None:
            return KindParsed(None, {}, [])
        if not isinstance(raw, list):
            raise VarConfigError(
                f"{path} must be a bare list",
                advice="Each item has path and an optional vars mapping.",
            )
        return self.items(path, raw, logger)

    def full_text(
        self,
        sep: str,
        columns: tuple[str, ...] | None,
        rows: list[KindLine],
    ) -> str:
        """A bare list. path, sha, and vars are quoted."""
        del sep, columns
        if not rows:
            return "[]\n"
        chunks: list[str] = []
        for line in rows:
            dumped_path = yaml.safe_dump(
                line.path,
                allow_unicode=True,
                default_style='"',
            ).strip()
            lines = [f"- path: {dumped_path}\n"]
            if line.sha:
                dumped_sha = yaml.safe_dump(
                    line.sha,
                    allow_unicode=True,
                    default_style='"',
                ).strip()
                lines.append(f"  sha: {dumped_sha}\n")
            if line.cells:
                lines.append("  vars:\n")
                for key, value in line.cells.items():
                    dumped = yaml.safe_dump(
                        value,
                        allow_unicode=True,
                        default_style='"',
                    ).strip()
                    lines.append(f"    {key}: {dumped}\n")
            chunks.append("".join(lines))
        return "".join(chunks)

    def pending_text(
        self,
        sep: str,
        columns: tuple[str, ...],
        pending: list[tuple[str, str]],
        header: bool,
    ) -> str:
        """path and sha only. This append is not quoted the way a full rewrite is."""
        del sep, columns, header
        return "".join(self._pending_yaml(relative, digest) for relative, digest in pending)

    @staticmethod
    def _pending_yaml(relative: str, digest: str) -> str:
        dumped = yaml.safe_dump(relative, allow_unicode=True).strip()
        lines = [f"- path: {dumped}\n"]
        if digest:
            dumped_sha = yaml.safe_dump(digest, allow_unicode=True).strip()
            lines.append(f"  sha: {dumped_sha}\n")
        return "".join(lines)


YAML = KindYaml()
