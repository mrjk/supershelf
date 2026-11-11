# 3 Feeds

Behavior. Index: [README](../README.md).

`supershelf scan feeds` writes kind files. `supershelf scan` runs this step after vars. 2.1. It does not write the sqlite file. There is no `data` command.

Say var, not field. A field is a match-rule slot, such as regex or filename_glob.

The kind file is the file from 2.3.2. `kind_overrides_mode`, `kind_overrides_date_format`, `kind_overrides_sep`, and `kind_overrides_config` stay. A kind may set `feed_file` and `feeds`. Architecture 1.9.

This step does not read or write documents, events, or `vars_json`. It does not create or migrate the sqlite file. Resolution does not read `vars_json`. Behavior 4 owns those tables. The sqlite schema does not follow `feeds`. Architecture 3.2.

`cache_file` is the metadata cache in 2.3.3. A real `scan feeds` may write it when a candidate calls `meta()`. `--dry-run` does not.

## 3.1 Shared rules

- The plan is computed before any write. Identity updates from 2.3.2 run first. Row drop is 3.3. Feed cells are last.
  `auto` and `always` stage those steps in memory and write each kind file once.
  Do not flush identity to disk before drop.
- Duplicate SHA recovery runs before identity updates, and only for `auto` and `always`.
  Several rows share one non-empty SHA, and exactly one of those PATH values is a live matched file of that kind in this scan:
  keep that row, delete the other rows with that SHA, and for each lowercase or feed cell, when the kept cell is empty and a discarded row has a non-empty value, copy it.
  Warn with the kind file, the digest, the kept path, and the removed paths.
  Two or more of those paths are live, or none of them are live: error, same message as 2.3.2, write nothing.
  `scan vars`, `manual`, and `disabled` do not recover.
- The fed value is the final resolve display string. That is the same layering as `scan vars --overrides`: `default_vars`, rule `vars`, then kind-file cells. 2.3.1.
- This step does not write a lowercase cell. The next resolve still uses that cell when it is set.
  When the lowercase cell is empty, a non-empty feed cell applies as the kind override for that var. 2.3.2.
  The source label is then `kind:<path>`. A non-empty lowercase cell still wins over the feed cell.
- An unset var does not blank a cell and does not add an empty cell.
- Namespace fields stay out. A name that starts with `__` is not a user variable.
- `kind_overrides_mode` gates this step.
  `disabled` does not read or write kind files. Import still runs.
  `manual` reads, writes uppercase cells on rows that already exist, and does not append, fill `SHA`, retarget `PATH`, or drop rows.
  `auto` and `always` also append, fill `SHA`, and retarget `PATH`, as in 2.3.2, and they drop rows as in 3.3.
  `always` creates a missing file from the first template. `auto` does not.
  `manual` and `disabled` do not create a missing file.
- For each profile and kind that matched a file on this run, log the kind file. 3.2.
  `disabled` does not. A kind with no matched file is silent.
  The line is a notice. 1. It is shown with no `-v`.
  `--dry-run` logs the same lines and writes nothing.
  An on-disk file logs `Profile {profile} kind {kind} kind file {path}`.
  The path is resolved. Two inputs that share one file log it once.
  Two inputs that resolve different files each log one line.
  No on-disk file logs `Profile {profile} kind {kind} has no config`.
  That is an empty `kind_overrides_config` with no `feed_file`, or templates whose files are all missing.
  The same sentence either way. Nothing is written for that kind. Import still runs.
  When some inputs have a file and some do not, log each found path, and
  `Profile {profile} kind {kind} has no config for input {input}` once per input directory that missed.
  `always` does not count a file as found until it is on disk. The notice is logged, then the create still runs.
  `manual` and `auto` do not create a missing file.
- The kind file is chosen as in 2.3.2. The first existing template wins.
- A new CSV column is appended on the right. Feed does not reorder columns.
  A file created in this run already has its feed columns when feeds is a non-empty list, in the order from 2.3.2.
  Feed fills those cells and does not append them.
  On a file that already had columns, a missing feed column is appended on the right.
- The stored feed cell is the display string. A float stays `12.50`. A bool stays `true` or `false`.
- Two inputs that share one kind file and the same row identifier:
  if the fed values differ, stop and name both inputs. Do not pick one. Write nothing, including the sqlite file when this step is part of `scan`.
- Duplicate path rows: update the first, leave the later row, and keep the warning from 2.3.2.
  A rewrite must not drop that later row.
- `--dry-run` prints the same rows and writes nothing. It does not create `cache_file`.
- Before a real write to an existing kind file, copy that file to
  `{cwd}/.backups/{basename}.{YYmmdd}-{hhmmss}` using local time.
  Create `.backups` when it is missing. The basename is the kind file name only.
  When that name is already taken, append `-2`, then `-3`, and so on until free.
  Skip the copy when the kind file is not on disk yet, when `--dry-run` is set,
  or when `--no-backup` is set. A failed copy stops that kind-file write.
- A resolve error writes no kind file. A cache entry already stored during that resolve stays.
- `PATH` limits which live files are fed. It does not drop kind-file rows outside that selection. A full run drops. 3.3.
- There is no prompt and no `--force`.
- One profile can finish its kind files before a later profile fails.

### Cases

Empty kind paths. `kind_overrides_config: []` and no `feed_file`. A matched kind logs `Profile work kind invoice has no config`. `db import` still writes documents.

Missing kind file. Templates name a file that is not on disk. The same notice. `auto` does not create the file.

Found kind file. The file is on disk. One notice names the resolved path. Many matched files that share it log it once.

Two kind files. Two inputs resolve different files for one kind. Each path is logged once.

Mixed inputs. One input has a kind file and another does not. The found path is logged. The missing input logs `has no config for input` and that input directory.

Disabled mode. `kind_overrides_mode` is `disabled`. No kind file is read or written. The kind-file notice is not logged.

Shared path. Two inputs resolve the same kind file and the same relative path, and the fed `vendor` values differ. The command stops and names both inputs.

Feed fills the gap. The rule set `vendor` and the lowercase cell is empty. Feed writes the final display string into `VENDOR`. The next resolve applies that feed cell, so `vendor` is the fed text with source `kind:<path>`.

Custom cell. `vendor` holds `Mine`. Feed writes `Mine` into `VENDOR`. `vendor` stays `Mine` and still wins on the next resolve.

Documents left alone. Feed writes `VENDOR` and leaves `vendor` empty. This step still writes no document row and no event. `db import` is the step that stores the resolved value.

Dry run. `scan feeds --dry-run` prints the plan and does not create `cache_file`. The kind-file notice is still logged. No `.backups` copy.

Backup. `scan feeds` rewrites an on-disk kind file. A copy lands in `.backups` under the process cwd before that write. `--no-backup` skips it. A new kind file has no copy.

## 3.2 scan feeds

### Command

- supershelf scan feeds [PATH]
- Writes fed values into the uppercase columns, after the identity updates and the row drop.
- `PATH` is the relative path from 2.1.1. Omit it to feed every matched file.
- `--kind-overrides-mode` is the flag from 2.3.2. It belongs to `scan feeds` and to bare `scan`.
- `--no-backup` skips the kind-file copy in 3.1. It belongs to `scan feeds` and to bare `scan`.
- `--dry-run` writes nothing. It still logs the kind file. 3.1.
- For each profile and kind that matched a file, log the kind file.
  `supershelf scan` and `inspect scan feeds` log the same lines.
  `disabled` does not. A kind with no matched file is silent.
  The line is a notice. 1. It is shown with no `-v`.
  An on-disk file logs `Profile {profile} kind {kind} kind file {path}`.
  The path is resolved. Two inputs that share one file log it once.
  Two inputs that resolve different files each log one line.
  No on-disk file logs `Profile {profile} kind {kind} has no config`.
  That is an empty `kind_overrides_config` with no `feed_file`, or templates whose files are all missing.
  The same sentence either way. Nothing is written for that kind. Import still runs.
  When some inputs have a file and some do not, log each found path, and
  `Profile {profile} kind {kind} has no config for input {input}` once per input directory that missed.
  `always` does not count a file as found until it is on disk. The notice is logged, then the create still runs.
  `manual` and `auto` do not create a missing file.
- There is no name filter and no `--var` flag. The names are the non-empty `feeds` list on the kind. Omitted or empty feeds writes no uppercase columns. Architecture 1.9.

### Selectors

- Schema vars are the CSV header names for that kind. 2.3.2.
  A `kind_schema` entry uses its local names. Otherwise the declared `vars_schema` names are used.
- A kind with no `feeds` list, or an empty one, has no uppercase columns.
  `scan feeds` does not add them.
- A name in `feeds` that the kind does not resolve stops the command. Architecture 1.9.

### Write

- The feed column is the var name with ASCII letters uppercased.
  `vendor` is `VENDOR`. `issued` is `ISSUED`.
  When that form is `PATH` or `SHA`, wrap it: `_PATH_` or `_SHA_`.
  Feed never writes the headers `PATH` or `SHA`.
- Write the final resolve display string into that column.
  Replace the cell when the text differs. An equal cell is not a change.
  A lowercase or mixed-case cell is never written by this step.
  An edit in the uppercase column is replaced on the next feed.
  Custom text belongs in the lowercase column.
- A `type: date` value is written with `kind_overrides_date_format`, not the stored `YYYY-MM-DD`.
  Other types use the display string. The kind-file format applies to every date-typed cell, as in 2.3.2.
- A file created in this run already has its feed columns when feeds is a non-empty list, in the create order from 2.3.2.
  Feed fills those cells and does not append them.
  On a file that already had columns, a missing feed column is appended on the right.
  The row is the kind-file row for this file's identifier. 2.3.2.
  Feed does not rewrite `PATH` or `SHA` on a row that already exists. Identity updates do. 2.3.2.
  A matched file with no row is added when a cell is written, in `auto` and `always`. The new row sets `PATH` and `SHA`. Other lowercase cells are empty.
  Several live files that share a digest, whose first step is hash, and that have no row:
  do not pick a path and do not add a row. One warning names the digest and every path.
- CSV column rules from 2.3.2 still apply.
  A name that is not a legal feed column is left out of CSV and reported.
- The report lists cells that would change, and rows that would be dropped. 3.3.
  `scan feeds` prints changes. `inspect scan feeds` prints every fed cell. 6.
  Columns: sha, path, column, value, user_cells.
  profile is the first column when more than one profile is selected. 2.1.
  There is no input column and no status column.
  sha stays the value this step already prints: empty on a cell write for an existing row, the kind-file SHA on a dropped row.

### Cases

Date round-trip. Stored `issued` is `2026-04-25` and its type is `date`. `kind_overrides_date_format` is `%d/%m/%Y`. Feed writes `ISSUED` as `25/04/2026`. The `issued` cell stays. A text var stays its display string.

Filled uppercase cell. `VENDOR` already holds the final display string. The text stays, and the file is not rewritten for that cell. A different `VENDOR` cell is replaced. The lowercase `vendor` cell stays.

Unset. No layer set `owner`. Feed does not blank `OWNER` or `owner`, and it does not add an empty cell.

Reserved name. A var named `path` or `sha` is written to `_PATH_` or `_SHA_`. Those columns are ignored on the next scan. A var named `date` is written to `DATE`.

Left off `feeds`. `owner` is a schema var and is not listed in `feeds`. No `OWNER` column is written. Import still stores `owner` in `vars_json`.

## 3.3 Row drop

- This is part of `scan feeds`. It is not its own command.
- It runs after the path and hash updates in 2.3.2, and before feed cells are written.
  Those steps stay in memory until the one kind-file write. 3.1.
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
  A row with an empty PATH is not dropped.
- List every dropped row before the write: the path, the SHA when set, and whether any user cell is non-empty.
  `--dry-run` prints that list and writes nothing.
  `--force` is not a flag.
- A `PATH` filter does not drop rows outside the selection.
- Empty-column purge and a full clear of the kind file are not commands.
- This does not delete a document, an event, or a hash.
