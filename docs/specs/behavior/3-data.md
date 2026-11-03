# 3 Feeds

Behavior. Index: [README](../README.md).

`supershelf scan feeds` writes kind files. `supershelf scan` runs this step after vars and before import. 2.1. There is no `data` command.

Say var, not field. A field is a match-rule slot, such as regex or filename_glob.

The kind file is the file from 2.3.2. `kind_overrides_mode`, `kind_overrides_date_format`, `kind_overrides_sep`, and `kind_overrides_config` stay. A kind may set `feed_file` and `feeds`. Architecture 1.9.

This step does not read or write documents, events, or `vars_json`. It does not create or migrate the sqlite file. Resolution does not read `vars_json`. Behavior 4 owns those tables. The sqlite schema does not follow `feeds`. Architecture 3.2.

`cache_file` is the metadata cache in 2.3.3. A real `scan feeds` may write it when a candidate calls `meta()`. `--dry-run` does not.

## 3.1 Shared rules

- The plan is computed before any write. Identity updates from 2.3.2 run first. Row drop is 3.3. Feed cells are last.
- The fed value is the display string of the resolve with the kind-file layer skipped. Facts, `default_vars`, and rule `vars` are included. A lowercase cell is not copied into the uppercase column.
- A lowercase cell is the user override. The next resolve still uses it. The uppercase column is not read back. The source label is not `kind:<path>` from that feed column.
- An unset var does not blank a cell and does not add an empty cell.
- Namespace fields stay out. `__date__` is allowed.
- `kind_overrides_mode` gates this step.
  `disabled` does not read or write kind files. Import still runs.
  `manual` reads, writes uppercase cells on rows that already exist, and does not append, fill `SHA`, retarget `PATH`, or drop rows.
  `auto` and `always` also append, fill `SHA`, and retarget `PATH`, as in 2.3.2, and they drop rows as in 3.3.
  `always` creates a missing file from the first template. `auto` does not.
  `manual` and `disabled` do not create a missing file.
- An empty `kind_overrides_config` and no `feed_file` means there is no file. `scan feeds` prints that and writes nothing. Import still runs.
- The kind file is chosen as in 2.3.2. The first existing template wins.
- A new CSV column is appended on the right. Feed does not reorder columns.
  TOML and YAML append a new key and keep the existing key order.
- The stored feed cell is the display string. A float stays `12.50`. A bool stays `true` or `false`.
- Two inputs that share one kind file and the same row identifier:
  if the fed values differ, stop and name both inputs. Do not pick one. Write nothing, including the sqlite file when this step is part of `scan`.
- A mandatory var that is still unset stops the command before any write.
- Duplicate path rows: update the first, leave the later row, and keep the warning from 2.3.2.
  A rewrite must not drop that later row.
- `--dry-run` prints the same rows and writes nothing. It does not create `cache_file`.
- A resolve error writes no kind file. A cache entry already stored during that resolve stays.
- `PATH` limits which live files are fed. It does not drop kind-file rows outside that selection. A full run drops. 3.3.
- There is no prompt and no `--force`.
- One profile can finish its kind files before a later profile fails.

### Cases

Empty kind paths. `kind_overrides_config: []` and no `feed_file`. `scan feeds` prints that there is no file. `scan import` still writes documents.

Disabled mode. `kind_overrides_mode` is `disabled`. No kind file is read or written.

Shared path. Two inputs resolve the same kind file and the same relative path, and the fed `vendor` values differ. The command stops and names both inputs.

Override stays put. The rule set `vendor` and the lowercase cell is empty. Feed writes the rule display string into `VENDOR`. `vendor` stays empty. The next resolve still uses the rule.

Custom cell. `vendor` holds `Mine`. Feed writes the rule-layer string into `VENDOR`. `vendor` stays `Mine` and still wins on the next resolve. `VENDOR` does not become `Mine`.

Documents left alone. Feed writes `VENDOR` and leaves `vendor` empty. No document row and no event is written.

Dry run. `scan feeds --dry-run` prints the plan and does not create `cache_file`.

## 3.2 scan feeds

### Command

- supershelf scan feeds [PATH]
- Writes fed values into the uppercase columns, after the identity updates and the row drop.
- `PATH` is the relative path from 2.1.1. Omit it to feed every matched file.
- `--kind-overrides-mode` is the flag from 2.3.2. It belongs to `scan feeds` and to bare `scan`.
- `--dry-run` writes nothing.
- There is no name filter and no `--var` flag. The names are `feeds` on the kind, or every schema var when `feeds` is omitted. Architecture 1.9.

### Selectors

- Schema vars are the CSV header names for that kind. 2.3.2.
  A `kind_schema` entry uses its local names. Otherwise the declared `vars_schema` names are used.
  `__date__` is included only when that schema lists it.
- A kind with no schema columns has no schema vars.
  Feed then uses the user-visible names `scan vars` would print for files of that kind, so dates and rule vars still get a cell.
- A name in `feeds` that is not one of those names stops the command.

### Write

- The feed column is the var name with ASCII letters uppercased.
  `vendor` is `VENDOR`. `__date__` is `__DATE__`.
  When that form is `PATH`, `SHA`, or `DATE`, wrap it: `_PATH_`, `_SHA_`, or `_DATE_`.
  Feed never writes the headers `PATH`, `SHA`, or `DATE`.
- Write the rule-layer display string into that column.
  Replace the cell when the text differs. An equal cell is not a change.
  A lowercase or mixed-case cell is never written by this step.
  An edit in the uppercase column is replaced on the next feed.
  Custom text belongs in the lowercase column.
- `__date__` is written as `__DATE__` with `kind_overrides_date_format`, not the stored `YYYY-MM-DD`.
  Other date vars stay `YYYY-MM-DD`. The kind-file format applies to `__date__` only, as in 2.3.2.
- A missing feed column is appended on the right. TOML and YAML append the key.
  The row is the kind-file row for this file's identifier. 2.3.2.
  Feed does not rewrite `PATH` or `SHA` on a row that already exists. Identity updates do. 2.3.2.
  A matched file with no row is added when a cell is written, in `auto` and `always`. The new row sets `PATH` and `SHA`. Other lowercase cells are empty.
  Several live files that share a digest, whose first step is hash, and that have no row:
  do not pick a path and do not add a row. One warning names the digest and every path.
- CSV column rules from 2.3.2 still apply.
  A name that is not a legal feed column is left out of CSV and reported.
- The report lists cells that would change, and rows that would be dropped. 3.3.
  `scan feeds` prints changes. `inspect scan feeds` prints every fed cell. 6.

### Cases

Date round-trip. Stored `__date__` is `2026-04-25`. `kind_overrides_date_format` is `%d/%m/%Y`. Feed writes `__DATE__` as `25/04/2026`. The `__date__` cell stays. A `date` var that is not `__date__` is written as `_DATE_` and stays `YYYY-MM-DD`.

Filled uppercase cell. `VENDOR` already holds the rule-layer display string. The text stays, and the file is not rewritten for that cell. A different `VENDOR` cell is replaced. The lowercase `vendor` cell stays.

Unset. No layer set `owner`. Feed does not blank `OWNER` or `owner`, and it does not add an empty cell.

Reserved name. A var named `path`, `sha`, or `date` is written to `_PATH_`, `_SHA_`, or `_DATE_`. Those columns are ignored on the next scan.

Left off `feeds`. `owner` is a schema var and is not listed in `feeds`. No `OWNER` column is written. Import still stores `owner` in `vars_json`.

## 3.3 Row drop

- This is part of `scan feeds`. It is not its own command.
- It runs after the path and hash updates in 2.3.2, and before feed cells are written.
- `auto` and `always` only. `manual` and `disabled` do not drop rows.
- Drop a kind-file row whose identifier is not a matched file of that kind in this scan.
  A row is kept when its path is a live file of that kind whose first step is path,
  or its SHA is a live file of that kind whose first step is hash.
  An empty SHA is not a live hash. A hash-identity rename is kept, including when the stored path is gone,
  until the path rewrite in 2.3.2 has run.
  A path-identity rename is dropped. The new path is a new row when a cell is written.
  Overrides on a dropped row are gone. A later return of that path starts from empty lowercase cells.
  A file that moved to another kind is dropped from the old kind file when its identifier is not still live there.
  Two inputs that share one kind file keep the row when either input still matches that identifier for that kind.
- List every dropped row before the write: the path, the SHA when set, and whether any user cell is non-empty.
  `--dry-run` prints that list and writes nothing.
  `--force` is not a flag.
- A `PATH` filter does not drop rows outside the selection.
- Empty-column purge and a full clear of the kind file are not commands.
- This does not delete a document, an event, or a hash.
