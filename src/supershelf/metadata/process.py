"""Run one program and return UTF-8 stdout."""

from __future__ import annotations

import logging
import shutil
import subprocess

from supershelf.constants import LOGGER_NAME
from supershelf.errors import VarCandidateError


class ProcessRunner:
    """subprocess.run with shell off. stderr is logged and not parsed."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(LOGGER_NAME)

    def which(self, name: str) -> str | None:
        """The program on PATH, or None."""
        return shutil.which(name)

    def run(self, argv: list[str], timeout: float) -> str:
        """Stdout as text. Timeout, a bad exit, or undecodable bytes miss."""
        try:
            completed = subprocess.run(
                argv,
                shell=False,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise VarCandidateError(f"{argv[0]} timed out") from exc
        if completed.stderr:
            self._logger.debug("%s", completed.stderr.decode("utf-8", errors="replace"))
        if completed.returncode != 0:
            raise VarCandidateError(f"{argv[0]} exited {completed.returncode}")
        try:
            return completed.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VarCandidateError(f"{argv[0]} stdout is not UTF-8") from exc
