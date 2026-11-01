"""Shared builders for CLI and profile tests."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from supershelf.configs import ShelfConfig
from supershelf.constants import (
    ENV_CONFIG,
    ENV_KIND_OVERRIDES_MODE,
    ENV_PROFILES,
    ENV_RECORD_IDENTITY,
    LOGGER_NAME,
)
from supershelf.profile import ShelfProfile


def isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Run from `tmp_path` with discovery env vars unset."""
    monkeypatch.chdir(tmp_path)
    for name in (
        ENV_CONFIG,
        ENV_PROFILES,
        ENV_KIND_OVERRIDES_MODE,
        ENV_RECORD_IDENTITY,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def write_text(path: Path, text: str) -> None:
    """Write `text` and create missing parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_profile(
    tmp_path: Path,
    body: str,
    *,
    name: str = "work",
    suffix: str = ".toml",
) -> ShelfProfile:
    """Load one profile file written under `tmp_path`."""
    path = tmp_path / f"profile.{name}{suffix}"
    path.write_text(body, encoding="utf-8")
    loaded = ShelfConfig.from_path(path, logging.getLogger(LOGGER_NAME))
    return ShelfProfile.from_config(loaded)
