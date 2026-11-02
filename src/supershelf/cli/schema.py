"""`supershelf schema`."""

from __future__ import annotations

import json

from clak import Parser

from supershelf.configs import ShelfConfigs
from supershelf.domain_schema import DomainSchema
from supershelf.template.environment import VarEnvironment


class SchemaCommand(Parser):
    """Print JSON Schema for declared variables and kinds."""

    def cli_run(self, config=None, profile=None, **_):
        loaded = ShelfConfigs.load(config_option=config, profile_option=profile)
        body = {}
        for item in loaded.config_list:
            environment = VarEnvironment()
            body[item.profile] = DomainSchema.load(
                item.config,
                compile_source=environment.compile_source,
            ).document()
        print(json.dumps(body, indent=2))
