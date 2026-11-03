# 6 Inspect

Behavior. Index: [README](../README.md).

`supershelf inspect` reads. It does not write the sqlite file, a kind file, or the cache. `inspect config` does not scan. `inspect schema` does not scan. `inspect scan` walks and resolves, and prints the full plan.

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

## 6.2 Schema

- supershelf inspect schema
- Prints the JSON Schema from architecture 1.9.
- Does not scan, open the database, or open the cache.
- `--dry-run` writes nothing. The command has nothing to change.
- There is no `supershelf schema` command.

## 6.3 Scan

- supershelf inspect scan STEP [PATH]
- STEP is `files`, `kinds`, `vars`, `feeds`, or `import`.
- Prints the full plan for that step, including unchanged rows. `scan` prints only rows this run would write. 2.1.
- Writes nothing. It does not create or edit a kind file, the sqlite file, or the cache file.
- `inspect scan kinds` with a PATH is the pattern trace in 2.2.1. Omit PATH to print one match or miss line per kept file.
- `inspect scan feeds` lists every fed cell and every row a real `scan feeds` would drop. It does not drop them.
- `inspect scan import` prints every in-scope status, including `unchanged`. 4.1.
- `PATH` is the relative path from 2.1. The same path in two inputs is two rows.
- `--dry-run` changes nothing.
