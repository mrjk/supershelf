# Import commands

This step scans import directories, stores one row per document hash, and runs import rules. It does not write files under `trees/`. The data model, the source walk, and document identity are in [SPECS.md](SPECS.md).

Shared options for `import scan`, `import sync`, and `import status`:

- `--sources name1,name2`: limit the command to these import sources. Default: all sources in the config.
- `--files PATTERN`: limit the command to `file_name` values that match `PATTERN`.
- `--files-type regex|glob`: how `--files` is interpreted. Default: `glob`.
- `--dry`, `-n`: log the work and write nothing.

`import scan` also has:

- `--scan-only`: walk, log, and run the duplicate check. Do not add rows and do not update states.
- `--db-add` / `--no-db-add`: insert hashes that have no row. Default: add.
- `--db-cleanup` / `--no-db-cleanup`: mark rows `missing` when their hash is no longer on disk. Default: cleanup.

`--scan-only` and `--dry` both write nothing. `--dry` still reports duplicates.

## import scan

Walk the selected sources as defined in [SPECS.md](SPECS.md). Then:

1. If any hash appears on more than one live file, print every duplicate and exit with an error. Write nothing. This uses the full walk of the selected sources, including names excluded by `--files`.
2. Stop here when `--scan-only` or `--dry` is set, after logging the inserts and state changes that would have been made.
3. With add (default): insert a `present` row for each live hash that has no row and whose file matches `--files`. Set `created` and `modified`.
4. With cleanup (default): for rows in the selected sources, set `state` to `missing` when that hash was not on disk. Leave rows that do not match `--files` unchanged. A hash that is still on disk keeps its row `present`, and a move of that same hash updates the location fields.
5. Never delete a row.

A content change at the same path follows [SPECS.md](SPECS.md): the old row becomes `missing`, and the new hash is inserted as `present`.

## import sync

Run the import rules on `present` rows for the selected sources and `--files` filter.

For each source, the rule list is that source's `import_rules`, then the global `import_rules`. The first matching rule wins. Omitted or empty `patterns` match every file.

When a rule matches, run its driver and store the result on the single `metadata` row for that `file_id`:

- Insert on the first success: `file_id`, `driver`, `vars`, `created`, `modified`.
- On a later sync, update `driver`, `vars`, and `modified`. Leave `created` as it is.

When no rule matches, leave any existing metadata row unchanged. When the driver raises, log the file and continue. Do not write metadata for that file.

`--dry` logs the metadata writes and does not touch the database.

## import status

Show every live file in the selected sources that matches `--files`, plus `missing` rows for those sources that match `--files`.

One row per file, with columns:

- `source`
- `dir_path`
- `file_name`
- `file_sha256`
- `state`: `present`, `missing`, or `absent`
- `scanned`: `yes` when a `file_sources` row exists, `no` when the live file is `absent`

`absent` means the hash is on disk and has no row yet. Render the rows with the CLI table output from [RULES.md](RULES.md), including its structured formats.
