"""Load profiles, walk inputs, match kinds, and resolve variables."""

from __future__ import annotations

from collections.abc import Callable

from supershelf.configs import ShelfConfigs
from supershelf.match import Matcher
from supershelf.profile import ShelfProfile
from supershelf.scan import InputFile, InputScanResult, KeptPath
from supershelf.vars import VarPlan


class ResolvedWalk:
    """Matched files with resolved variables. Does not commit kind files."""

    def __init__(
        self,
        prepared: list[tuple[ShelfProfile, Matcher, VarPlan]],
        groups: list[list[InputScanResult]],
        accept: Callable[[InputFile], bool] | None = None,
    ) -> None:
        self._prepared = prepared
        self._groups = groups
        self._accept = accept

    @property
    def plans(self) -> list[VarPlan]:
        """One plan per profile, including a profile with no matched files."""
        return [plan for _shelf, _matcher, plan in self._prepared]

    def __iter__(self):
        for (_shelf, matcher, plan), scans in zip(
            self._prepared,
            self._groups,
            strict=True,
        ):
            for result in scans:
                files = {found.path: found for found in result.results}
                for matched in matcher.collect(result):
                    found = files[matched.path]
                    if self._accept is not None and not self._accept(found):
                        continue
                    resolved = plan.resolve(found, matched, result.config.path)
                    yield _shelf, result, found, matched, resolved, plan


class ShelfRuns:
    """Profiles loaded for one scan command."""

    def __init__(self, shelves: list[ShelfProfile]) -> None:
        self.shelves = shelves

    @classmethod
    def load(cls, config: str | None, profile: str | None) -> ShelfRuns:
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        return cls([ShelfProfile.from_config(item) for item in loaded.config_list])

    def scans(self, *, quick: bool, path: str | None):
        groups = [shelf.scan(quick=quick) for shelf in self.shelves]
        return KeptPath.narrow_groups(groups, path)

    def matched(self) -> list[tuple[ShelfProfile, Matcher]]:
        return [
            (shelf, Matcher.from_document(shelf.document, shelf.name))
            for shelf in self.shelves
        ]

    def plans(
        self,
        *,
        mode: str | None = None,
        dry_run: bool = False,
    ) -> list[tuple[ShelfProfile, Matcher, VarPlan]]:
        """One matcher and var plan per profile. Does not walk."""
        prepared: list[tuple[ShelfProfile, Matcher, VarPlan]] = []
        for shelf in self.shelves:
            matcher = Matcher.from_document(shelf.document, shelf.name)
            prepared.append(
                (
                    shelf,
                    matcher,
                    VarPlan.from_document(
                        shelf.document,
                        shelf.name,
                        matcher,
                        shelf.root_dir,
                        shelf.scope,
                        mode=mode,
                        dry_run=dry_run,
                    ),
                )
            )
        return prepared

    def resolved(
        self,
        path: str | None,
        *,
        mode: str | None = None,
        dry_run: bool = False,
        groups: list[list[InputScanResult]] | None = None,
        accept: Callable[[InputFile], bool] | None = None,
    ) -> ResolvedWalk:
        """Match and resolve. A passed `groups` skips a second walk."""
        prepared = self.plans(mode=mode, dry_run=dry_run)
        if groups is None:
            groups = self.scans(quick=False, path=path)
        return ResolvedWalk(prepared, groups, accept)
