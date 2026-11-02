# Kind files

A kind file stores one row per path for one kind. `scan vars` reads that row after the winning rule's `vars`. This is the last assignment layer. Each cell is one literal string, then cast to the name's type. It replaces a value the rule already stored. It does not change what the rule template already read. A cell that cannot cast stops the file. It has no next candidate.

`scan files` and `scan kinds` do not read or write kind files. The file shape is in [Kind file](../reference/kind-file.md).

## Which file

`config.kind_overrides_config` is an optional list of path templates. They use the [path template language](paths.md). Omitted, the list is:

```text
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.csv
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.toml
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yaml
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yml
```

An empty list means no kind files. Nothing is created or appended.

Each path is rendered with the profile scope, `__kind__` set to the rule kind, and `__input__.path` set to the absolute input directory. A relative result is resolved from `__root_dir__`. The first path that exists and is a file wins. A missing path tries the next. None found means no row, unless the mode is `always`. A path that exists and is not a file stops the command. A symlink to a file is that file. A bad suffix, or content that does not parse, stops the command. The next path is not tried.

The rule kind picks the file.

The row key is the path relative to the input, with `/` separators. It is an exact match. Case is not folded. Two inputs that share one kind file treat the same relative path as one row. Put `{{ __input__.path }}` in a template when those inputs must not share rows.

The parsed file is cached on that profile by its absolute path. Another profile in the same command does not share the cache. The winner is cached by kind and input directory. Nothing is written to `cache_file`. A kind with no matched file is never looked up, so `always` does not create a file for it.

`-vv` logs each path tried the first time a kind and input directory are searched: a missing path, the file when it is first loaded, or a path already loaded for another search. The search stops at the first existing file, so later templates are not rendered and are not logged. An empty list logs that there is no candidate list, except when the mode is `disabled`. A repeated search stays quiet. `-v` does not add these lines. `disabled` does not search.

## Mode

`config.kind_overrides_mode` is `auto`, `manual`, `always`, or `disabled`. Omitted means `auto`. The words are exact. Any other value stops the command.

`--kind-overrides-mode` belongs to `scan vars`. `SUPERSHELF_KIND_OVERRIDES_MODE` accepts the same four words. The flag wins over the environment variable. The environment variable wins over the config key. Unset means omitted. A different case, or an empty environment value, is an error.

| Mode | Existing file | No file found |
| --- | --- | --- |
| `auto` | Read it. Append matched paths that have no row. | No row, and no new file. |
| `manual` | Read it. Leave it unchanged. | No row. |
| `always` | Read it. Append matched paths that have no row. | Create the first template, then append those paths. |
| `disabled` | Ignore it. | No row. The path list is not rendered. |

An empty file, or a file of whitespace only, is an empty table. `auto` and `always` replace it with a new file. `manual` leaves those bytes unchanged.

`always` creates missing parent directories. If a parent exists and is a file, that is an error and no kind file is written.

`auto` and `always` do not delete a row, edit a cell, drop a column, or reorder rows. They do not rewrite existing cell text. When schema columns are missing from a CSV, those names are appended on the right and existing rows gain empty cells. A path already present is not appended again, including a duplicate row that was warned and kept as the first. New rows follow the walk, input index first. A new row sets `PATH` in CSV, or `path` in TOML and YAML. The other cells are empty, so a row created on this run does not change this run's values.

A non-empty file whose last byte is not a newline gets a newline, then the new rows. The new bytes are one write at the end. A crash during that write can leave a partial last row. There is no lock. Two overlapping runs can append the same path twice.

Writes happen after the run succeeds. A variable error writes nothing.

`--dry-run` reads when the mode reads, and does not create, append, or add columns. It logs only when something would change. A file that would be created logs its path and its row count. A file that would gain rows logs its path and how many rows would be appended. A CSV that would gain schema columns logs those names, even when no row would be appended. Otherwise zero rows logs nothing. `manual` and `disabled` log nothing. Those lines are info logs, so `-v` shows them.

When `scan vars` is given a path, only the selected files are matched, so only those paths can be appended.

## Cells

A cell is one stored string. It is not a candidate list, and it is not compiled as Jinja, even when the text contains `{{`, `{%`, or `{#`. An empty cell, a blank string, or a YAML or TOML null is absent. The previous layer stays. There is no way to force an empty string over a previous value. Surrounding spaces are kept, except on `__date__`.

A cell that sets an existing key keeps that key's first position and replaces the stored string. A new key is appended. CSV uses column order. TOML and YAML use key order inside `vars`.

A row must not set an internal name. `__date__` is allowed. `__kind__` stays the kind from the match rule.

Unmatched files have no kind, so they get no row. Files the walk skipped get no row.

## Document date

A kind-file `__date__` cell is parsed. The format is `config.kind_overrides_date_format`. When that key is omitted or null, the format is `config.default_date_format`, which defaults to `%Y-%m-%d`. The format is checked before the walk. It must be a non-empty string, valid for `strptime`, and it must include a year, a month, and a day. A time portion is allowed.

The cell is stripped, then the whole string is parsed. The stored value is `YYYY-MM-DD`. A parsed time is dropped. A value that does not match stops the command. The message names the file, the profile, the input, the path, the cell text, and the format. There is no next candidate. A blank `__date__` cell is absent, and the command does not stop.

This format applies to `__date__` only. In TOML and YAML, another key, including `date`, stays raw text.

`config.kind_overrides_sep` is checked before the walk, at the same time as the date format. The separator rules are in [Kind file](../reference/kind-file.md).

## data feed and data prune

`kind_overrides_mode` does not gate `data feed` or `data prune`. `manual` and `disabled` still write. An empty `kind_overrides_config` stops `data feed`, `data prune`, and `data show`.

`data feed` fills empty selected cells with the resolved display string. A filled cell stays. An unset var does not blank a cell and does not add an empty one. Feed does not append the empty rows `scan vars` appends. `__date__` is written with `kind_overrides_date_format`. Other date vars stay `YYYY-MM-DD`. A matched path with no row is added when a selected cell is written. A new column is appended on the right.

`data prune` edits existing files and does not create a missing one. With no flags it drops empty columns that are not in the schema. `--missing` drops a row whose path is not matched as that kind. That is not document presence. The document stays. `--clear` removes every row and leaves the file. `--all` runs every purge, so the file ends with no rows. The database is not changed. Passing one flag does not turn the others on.

Both ask once, on stderr, before any kind-file write. `y` or `yes` writes. Anything else writes nothing. When stdin is not a terminal, pass `--force`. `--force` skips the question. `--dry-run` prints the summary and writes no kind file. A resolve that calls `meta()` can write `content_meta` before the question. An answer of no leaves that cache.

`data show` prints the live values, one table per profile and kind. It does not write kind files and it does not prompt. It may write `content_meta`.

A later duplicate row for the same path stays in the file. The first row is the one a rewrite updates. Two inputs that share one kind file and the same relative path stop the command when the selected values differ.
