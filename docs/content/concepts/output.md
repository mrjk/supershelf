# Output

`output` writes a destination for files that are already recorded, then appends an output event. The profile sqlite file is the same one `record` uses. One profile has one file. `output` does not create that file. Run `record run` first. It does not create or append a kind file. `extension_remap` is not read.

`cache_file` is a different path, and nothing writes it.

The walk is the same full walk as `record`. Variables are resolved the same way, including a kind-file read. A metadata cache miss does not create the sqlite file during the plan. `--dry-run` does not create it and does not migrate schema 1.

## Commands

`PATH` is the same selector as `scan files`. A value that matches no kept file stops the command.

| Command | What it prints | Write |
| --- | --- | --- |
| `output preview [PATH]` | Every selected row, including `unchanged` and `skip` | No |
| `output run [PATH]` | The same rows, except `unchanged` | Yes, unless `--dry-run` |

Columns are profile, input, path, output, driver, status, operation, when, and dest. input is the 1-based index. path is relative to the input. dest is absolute, or blank when `when` is false.

`--dry-run` prints the run rows and writes nothing. The database stays read-only. A `conflict` row stops `run` and `--dry-run` after the rows are printed, and the exit status is non-zero. `preview` still exits 0. Every selected profile is planned before any profile writes.

Status words:

| Status | Meaning |
| --- | --- |
| `write` | The destination is created. |
| `replace` | An existing destination is replaced. |
| `unchanged` | This profile already wrote this destination, and the file still matches. No event. `output run` leaves this row out. |
| `skip` | `when` is false, or `on_conflict` is `skip` and the file stays. No event. |
| `conflict` | The file is not one this profile wrote, and `on_conflict` is `error`. Nothing is written. |

## What can be written

A file has to pass `kinds` and `when`, and its record status has to be `unchanged` or `refresh`. `new`, `vars`, `generation`, `move`, `missing`, `present`, and `unmatched` stop the command before any destination is written. The message names the profile, the input, the path, and the record status. The tip says to run `record run`. A file that fails `kinds`, or whose `when` is false, does not face that check. A `duplicate` has no document. It is left out.

`when` is a string. Omitted, it is `true`. A template renders with the file's display strings, the same way a variable template does. `true`, `yes`, and `1` count as true. Empty text, `false`, `no`, and `0` count as false. Any other text stops the command. An unquoted YAML bool is a config error.

`kinds` omitted means every matched kind. `[]` selects nothing. A file of another kind is left out. It is not a `skip` row.

## File driver

`driver` defaults to `file`.

`path` is a profile path template, rendered once. A relative path resolves from `__root_dir__`. The directory is created only on a real write.

`layout` is Jinja. Omitted, it is `{{ __file_path__ }}`, so the input-relative path is kept. The rendered text is split on `/`. A segment that is empty, `.`, or `..` stops the command. An absolute path stops the command. The result has to stay inside `path`. `{{ __file_ext__ }}` is the last suffix. `{{ __date__[0:4] }}` is the year when `__date__` is set. A layout that uses `__date__` fails when `__date__` was omitted.

`operation` is `copy`, `symlink`, or `hardlink`. Omitted, it is `copy`. `copy` keeps file metadata. `symlink` points at the absolute source path. `hardlink` links that path. A cross-device hardlink stops the command. The tip says to use `copy`.

`on_conflict` is `error`, `skip`, or `overwrite`. Omitted, it is `error`. It applies when the destination exists and this profile has no output event for that path, and when this profile's last apply for that path no longer matches the file on disk. It does not apply when two actions in one run want the same destination. It does not apply when the latest event for that path belongs to another document or another output name. `overwrite` cannot take that path.

A second run that still matches prints `unchanged` on preview and appends no event. A copy matches when the destination sha256 equals the source hash. A symlink matches when its target is the source path. A hardlink matches when it is the same inode. A new hash or a new operation replaces the file. A layout change writes the new path and leaves the old file. Prune is a later command.

The file is written first. `append_output` runs after that returns, and only for `write` and `replace`. A crash between the two leaves a file this profile does not yet claim. The next run treats it as a foreign file.

## Modules

`config.output_modules` lists importable modules. Omitted, null, and `[]` add no drivers. Each module exports `DRIVERS`, a list of `OutputDriver` subclasses. Built-in `file` is registered first. Import order is list order. A repeated name stops the command. An import failure stops the command. This list is not `var_modules` and not `metadata_driver`.
