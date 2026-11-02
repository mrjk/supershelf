# 6 Inspect

Behavior. Index: [README](../README.md).

`supershelf inspect config` prints the parsed profile after profile init. It builds one ShelfProfile per selected ShelfConfig. It does not scan, open the database, or open the cache.

## 6.1 Command

- supershelf inspect config
- One selected profile prints that profile's document.
- Several selected profiles print one mapping keyed by profile name.
- `--format` is `toml`, `yaml`, or `json`.
- With no `--format`, the format is the selected profiles' type. `.yml` is `yaml`.
- When the selection mixes `toml` and `yaml` and `--format` is omitted, the command stops. The tip says to pass `--format`.
- `--dry-run` writes nothing. The command has nothing to change.

The printed document is a copy. The loaded file and `__profile__.document` stay as parsed.

`config.profile` is already the profile name from section 1.

These `config` values are the ones profile init already resolved. An omitted key is written with that resolved value:

- `config.default_date_format` is the plain string. Omitted, it is the packaged `%Y-%m-%d`. It is not rendered as a template.
- `config.root_dir`, `config.database_file`, and `config.cache_file` are the absolute paths stored on the ShelfProfile. Omitted keys use the packaged templates from section 2.

Every other value stays the parsed text. `inputs.path`, kind-file templates, var templates, and output templates are not rendered here.

A path template that section 2 cannot render stops the command with that same error.
