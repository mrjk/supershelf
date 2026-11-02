"""`supershelf profiles`."""

from __future__ import annotations

from clak import ListViewMixin, Parser

from supershelf.configs import ShelfConfigs


class ProfilesCommand(ListViewMixin, Parser):
    """List profile names and config paths."""

    def cli_run(self, config=None, profile=None, **_):
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        return [
            {
                "profile": item.profile,
                "type": item.type,
                "path": str(item.path),
            }
            for item in loaded.config_list
        ]
