"""`supershelf scan`."""

from __future__ import annotations

from clak import Argument, Command, ListViewMixin, Parser

from supershelf.cli.common import kept_path
from supershelf.kind_file import KindOverrideMode
from supershelf.scan.match import (
    DETAIL_NO_PATTERNS,
    STATUS_HIT,
    STATUS_MISS,
    STATUS_NOT_TRIED,
    STATUS_SKIPPED,
    FileInspection,
    PatternTrial,
)
from supershelf.scan.runs import ShelfRuns
from supershelf.scan.walk import InputFile
from supershelf.vars import FileVars

_STRUCTURED_FORMATS = frozenset({"json", "yaml"})


def _table_pairs(resolved: FileVars, *, show_all: bool = False) -> tuple[tuple[str, str], ...]:
    """Printed variables in table order: alphabetical by name."""
    visible = list(resolved.items)
    if show_all:
        visible.extend(resolved.facts.items())
    return tuple(sorted(visible))


def present_vars(resolved: FileVars, fmt: str | None, *, show_all: bool = False) -> object:
    """Table text, or the typed mapping for json and yaml."""
    if fmt in _STRUCTURED_FORMATS:
        return resolved.dump_vars(show_all=show_all)
    return "\n".join(
        f"{name}: {value}" for name, value in _table_pairs(resolved, show_all=show_all)
    )


def present_sources(resolved: FileVars, *, show_all: bool = False) -> str:
    """Source labels for the table, one line per name in present_vars order."""
    return "\n".join(
        ", ".join(resolved.source_labels(name))
        for name, _value in _table_pairs(resolved, show_all=show_all)
    )


class ScanFilesCommand(ListViewMixin, Parser):
    """List files kept by each input."""

    path = kept_path()
    quick = Argument(
        "--quick",
        action="store_true",
        help="Skip mtime, ctime, and sha256.",
    )

    def cli_run(self, config=None, profile=None, path=None, quick=False, **_):
        runs = ShelfRuns.load(config, profile)
        rows = []
        groups = runs.scans(quick=bool(quick), path=path)
        for shelf, scans in zip(runs.shelves, groups, strict=True):
            for result in scans:
                for found in result.results:
                    row = {
                        "profile": result.profile,
                        "input": result.index,
                        "path": found.path,
                    }
                    if not quick:
                        row["mtime"] = shelf.show_time(found.mtime or "")
                        row["ctime"] = shelf.show_time(found.ctime or "")
                        row["sha256"] = found.sha256
                    rows.append(row)
        return rows


class ScanKindsCommand(ListViewMixin, Parser):
    """List the kind matched for each kept file."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, **_):
        runs = ShelfRuns.load(config, profile)
        prepared = runs.matched()
        groups = runs.scans(quick=True, path=path)
        rows = []
        for (_shelf, matcher), scans in zip(prepared, groups, strict=True):
            for result in scans:
                for found in matcher.collect(result):
                    rows.append(
                        {
                            "profile": found.profile,
                            "input": found.index,
                            "path": found.path,
                            "kind": found.kind,
                            "rule": found.rule,
                        }
                    )
        return rows


class ScanVarsCommand(ListViewMixin, Parser):
    """List variables for each matched file."""

    path = kept_path()
    kind_overrides_mode = Argument(
        "--kind-overrides-mode",
        help="Kind file mode: auto, manual, always, or disabled.",
    )
    show_all = Argument(
        "--all",
        action="store_true",
        help="Include internal variables in the vars column.",
    )

    def cli_run(
        self,
        config=None,
        profile=None,
        path=None,
        dry_run=False,
        kind_overrides_mode=None,
        show_all=False,
        ctx=None,
        **_,
    ):
        fmt = ctx.view_settings.get("format") if ctx is not None else None
        if kind_overrides_mode is not None:
            KindOverrideMode.check(kind_overrides_mode, "--kind-overrides-mode")
        runs = ShelfRuns.load(config, profile)
        walk = runs.resolved(
            path,
            mode=kind_overrides_mode,
            dry_run=bool(dry_run),
        )
        rows = []
        for _shelf, _result, _found, matched, resolved, _plan in walk:
            presented = present_vars(resolved, fmt, show_all=bool(show_all))
            row = {
                "profile": matched.profile,
                "input": matched.index,
                "path": matched.path,
                "kind": resolved.kind,
                "rule": matched.rule,
                "vars": presented,
            }
            if isinstance(presented, str):
                row["sources"] = present_sources(resolved, show_all=bool(show_all))
            rows.append(row)
        for plan in walk.plans:
            plan.commit()
        return rows


class ScanInspectCommand(Parser):
    """Show how match rules test kept files."""

    path = kept_path()

    def cli_run(self, config=None, profile=None, path=None, verbosity=0, **_):
        runs = ShelfRuns.load(config, profile)
        prepared = runs.matched()
        groups = runs.scans(quick=True, path=path)
        level = int(verbosity or 0)
        named = path is not None
        for (_shelf, matcher), scans in zip(prepared, groups, strict=True):
            for result in scans:
                for found in result.results:
                    self._show_inspection(
                        level,
                        result.profile,
                        result.index,
                        found,
                        matcher.explain(found),
                        named=named,
                    )
        return None

    def _show_inspection(
        self,
        verbosity: int,
        profile: str,
        index: int,
        file: InputFile,
        inspection: FileInspection,
        *,
        named: bool,
    ) -> None:
        prefix = f"profile {profile} input {index}"
        if not named:
            self._show_summary(prefix, file, inspection)
            return
        if verbosity >= 1:
            self._print(
                f"{prefix} path {file.path!r} directory {file.directory!r} "
                f"filename {file.name!r}"
            )
        for trial in inspection.trials:
            self._show_trial(verbosity, prefix, trial)
        if inspection.match is None:
            self._print(
                f"No match_rule for {file.path} in profile {profile} input {index}"
            )
            return
        self._print(
            f"Matched rule {inspection.match.rule} kind {inspection.match.kind} "
            f"for {file.path} in profile {profile} input {index}"
        )
        if verbosity < 1:
            return
        if inspection.match.groups:
            rendered = " ".join(
                f"{name}={value!r}" for name, value in inspection.match.groups.items()
            )
            self._print(f"{prefix} groups {rendered}")
        if any(trial.rule != inspection.match.rule for trial in inspection.trials):
            self._print(f"{prefix} stopped, later rules not tried")

    def _show_summary(
        self,
        prefix: str,
        file: InputFile,
        inspection: FileInspection,
    ) -> None:
        if inspection.match is None:
            self._print(f"miss {prefix} {file.path}")
            return
        self._print(
            f"match {prefix} {file.path} rule {inspection.match.rule} "
            f"kind {inspection.match.kind}"
        )

    def _show_trial(self, verbosity: int, prefix: str, trial: PatternTrial) -> None:
        if trial.status in (STATUS_HIT, STATUS_MISS):
            self._print(self._trial_line(prefix, trial))
            return
        if trial.status == STATUS_SKIPPED and verbosity >= 1:
            self._print(self._trial_line(prefix, trial))
            return
        if trial.status == STATUS_NOT_TRIED and verbosity >= 2:
            self._print(self._trial_line(prefix, trial))

    def _trial_line(self, prefix: str, trial: PatternTrial) -> str:
        if trial.detail == DETAIL_NO_PATTERNS:
            return f"{prefix} rule {trial.rule} {trial.field}: skipped, {trial.detail}"
        tail = trial.status
        if trial.status == STATUS_SKIPPED:
            tail = f"skipped, {trial.detail}"
        return (
            f"{prefix} rule {trial.rule} {trial.field} {trial.pattern!r} "
            f"against {trial.candidate!r}: {tail}"
        )

    @staticmethod
    def _print(line: str) -> None:
        print(line)


class ScanCommand(Parser):
    """Scan profile inputs."""

    files = Command(ScanFilesCommand, help="List files kept by each input")
    kinds = Command(ScanKindsCommand, help="List the kind matched for each kept file")
    vars = Command(ScanVarsCommand, help="List variables for each matched file")
    inspect = Command(ScanInspectCommand, help="Show how match rules test kept files")
