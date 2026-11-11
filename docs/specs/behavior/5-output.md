# 5 Output

Behavior. Index: [README](../README.md).

`supershelf output` writes a destination for matched files and documents that apply. The driver contract is architecture 4. This step ships the `file` and `sqlite` drivers. The file driver calls `ShelfDatabase.append_output`. The sqlite driver does not. Schema version stays `2`. No new column. `record_key` keeps the next migration.

One profile has one sqlite file. Profiles do not share events. `cache_file` is the metadata cache in behavior 2.3.3. `output` uses the document plan from behavior 4, so a miss does not write it. `extension_remap` is not read.

The walk is the full walk from 2.1.2. There is no `--quick`. Variables resolve as in 2.3.1, including kind-file reads and `meta()`. `output` does not call the kind-file commit.

The comparison is the document plan from behavior 4. Output does not implement a second linker. `record_identity` stays a step list. The packaged default `path` means `[path, hash]`. A bare `hash` means `[hash, path]`. A match rule can override the list.

The plan phase uses that document plan. A metadata cache miss does not create the sqlite file. `--dry-run` does not create it and does not migrate schema `1`. A real run opens the existing file for write only when an event would be appended. That open migrates schema `1` to schema `2`, as architecture 3.5. A missing file is not created. With no documents, a file that passes `kinds` and `when` is `new`. Preview warns, prints the row, and exits 1. `run` warns and writes nothing. The tip says to run `db import`.

`scan`, `inspect`, `db`, and `profiles` do not read `outputs`.

## 5.1 Commands

`PATH` is the optional scan selector from 2.1.1. A value that matches no kept file stops the command. Columns are a clak table: profile, input, path, output, driver, status, operation, when, dest.

input is the 1-based index. path is relative to the input directory. output is the item name. when is the boolean string `true` or `false`. dest is the path relative to that output's `path`, or blank when `when` rendered `false`. The event stores the absolute destination.

Rows follow profile selection, then output list order, then walk order.

### output preview

- supershelf output preview [PATH]
- Prints every selected row, including `unchanged` and `skip`. A file whose document status is not `unchanged` or `refresh` is still planned from the live match.
- Writes nothing. It does not create the sqlite file, a parent, a destination, or a directory.
- The database is opened read-only.
- Each stale file warns once on stderr, before the table. The text is the 5.2 message for that status.
- Exit 0 when every selected file passes the document gate. A `conflict` row is valid here. The command still exits 0.
- Exit 1 when any selected file is stale. The table is still printed.

### output run

- supershelf output run [PATH]
- Prints the same rows, except `unchanged`, when every selected file passes the document gate.
- A stale file does not print the destination table. Every stale file in the selection warns, then the command exits 1. Nothing is written.
- `--dry-run` prints those rows and writes nothing when the plan passes the gate. The database stays read-only. Schema `1` is not migrated.
- A real run that would stop does stop under `--dry-run`, and still writes nothing. A stale plan warns and prints no destination table.
- A plan with only `unchanged` and `skip` writes nothing and does not open the database for write.
- Every selected profile is planned before any profile writes. A later profile does not commit when an earlier profile's plan would stop.
- A real write creates the destination parent, performs the file operation, then calls `append_output`. The method commits itself.
- A crash after the write and before the event leaves a file this profile does not yet claim. The next run treats it as a foreign file.

Status words:

- `write`: the destination is created.
- `replace`: an existing destination is replaced.
- `unchanged`: this profile already wrote this destination, and the file still matches. No event.
- `skip`: `when` is `false`, or `on_conflict` is `skip` and the existing file is left in place. No event.
- `conflict`: the existing file is not one this profile wrote, and `on_conflict` is `error`. Preview prints the row and exits 0. `run` prints the rows and exits non-zero. Nothing is written.

## 5.2 Selection

`outputs` is a top-level list.

- Omitted or null, on an output command, stops the command. The message says outputs is not set.
- `[]` stops the command. The message says outputs is empty.
- These are the two messages `inputs` already uses. The other commands ignore the key.

Each item has `name`, `driver`, `kinds`, and `when`. The driver owns every other key. A file item that carries a key it does not know stops the command.

- `name` is required. It is a non-empty string and unique in the profile. A duplicate stops the command.
- `driver` defaults to `file`. An unknown name stops the command and names the driver.
- `kinds` omitted or null means every matched kind. The kind is the match-rule kind. A kind file does not change it.
  `[]` selects no file. That item adds no row. It is not an error.
  A listed value that is not a string stops the command.
  A name that matches no rule does not stop at load. A file of another kind is left out. It is not a `skip` row.
- `when` omitted or null is the string `true`.
  A value that is not a string stops the command. An unquoted YAML bool is that error. A list is that error.
  A string with no Jinja marker is cast at load. A template is compiled at load. A syntax error stops the command before the walk.
  Render uses the file's display-string scope, the same commands as a variable template, and StrictUndefined.
  Strip the text. `true`, `yes`, and `1` become `true`. Empty text, `false`, `no`, and `0` become `false`. Case does not matter.
  Any other text stops the command and names the output, the path, and the rendered text.
  `{{ __match__.kind == "invoice" }}` renders `True` or `False`, and those cast.
  `false` is status `skip`. The layout is not rendered. No event is written.
  An undefined name stops the command, same as a variable template.
  The tip says to test the name with `is defined`.
- -vv logs each output item, then one line per file that item walks.
  `Output {name}: {count} files` uses the number of files in that walk, including files another kind leaves out and duplicates.
  A file of another kind logs `Output {name} {path} kind {kind} left out`.
  A rendered when logs `Output {name} {path} when true` or `Output {name} {path} when false`.
  A duplicate logs `Output {name} {path} duplicate left out`.
  -v does not add these lines.

A live file the document plan marks `duplicate` has no document. It is left out. It does not stop the other files. The owning document is the one that can be written. A `PATH` that matches only that extra file stops the command, because no kept output source was selected.

A file that passes `kinds` and `when` is planned from the live match. `output run` writes only when that file is a present document whose document status is `unchanged` or `refresh`. `new`, `vars`, `generation`, `move`, `missing`, `present`, and `unmatched` are stale. Preview warns once per file, prints the table, and exits 1. `run` and `--dry-run` warn for every stale file in the selection, print no destination table, write nothing, and exit 1.

The message starts `Profile {name} input {index} {path} status is {status}.` Then the facts. Then the fix. Values are quoted with double quotes.

- `new`: `This file is not in the library.` Fix: `Run db import.`
- `vars`: one clause per difference, in this order. `kind was "statement", now "bill".` `rule was "invoice", now "bill".` A variable uses its display string. `vendor was "Bank2000", now "Bank2001".` A new key: `amount is "12.00" and was not stored.` A removed key: `amount was "12.00" and is no longer set.` The same display, with a different type or source: `vendor is still "Bank2000" but its stored type or source changed.` `file_dir`, `file_name`, `file_stem`, and `file_ext` use the same was/now form. Fix: `Run db import, if those live values are the ones you want. If a live value is wrong, fix the match rule, the kind file, or the profile, then db import again.`
- `generation`: `The file bytes changed. hash was "{old}", now "{new}".` Then any kind, rule, variable, or file-field clauses from the same comparison. Fix: `Run db import.`
- `move`: `The file moved. path was "{stored}", now "{live}".` Then any of those clauses. Fix: `Run db import.`
- `missing`: `The recorded file is missing from the walk.` Fix: `Run db import.`
- `present`: `The file is back and is not stored as present.` Fix: `Run db import.`
- `unmatched`: `No rule matches this file.` Fix: `Change the match rule so this path matches, then run db import.`

The compared facts are `match_kind`, `rule`, `vars_json`, `file_dir`, `file_name`, `file_stem`, and `file_ext`. Variable text is the display field. A `present` row has no was/now clauses.

A passing status with no document id stops preview and run before a table. The message says `status is` that word. The tip is only `Run db import.` `refresh` is allowed because the hash and the variables are the same.

A file that fails `kinds`, or whose `when` is `false`, does not face that gate. A `duplicate` that would have passed `kinds` and `when` is still left out.

The profile sqlite file is ignored when it sits inside an input, same as `db import`.

`config.output_modules` is an optional list of importable module paths. Omitted, null, and `[]` add no drivers. The built-in `file` driver is registered first, then built-in `sqlite`. Each module is imported in list order and exports `DRIVERS`, a list of driver classes. A name that repeats `file`, `sqlite`, or an earlier module, stops the command. An import failure stops the command. This list is not `var_modules` and not `metadata_driver`.

## 5.3 File driver

`driver: file` is the default.

- `path` is required. It is a profile path template, the same language as `inputs.path`. It is rendered once. A relative result resolves from `__config__.root_dir`. An empty result stops the command. A result that exists and is not a directory stops the command. A missing directory is created only on a real write.
- `layout` is a Jinja template. Omitted, it is `{{ __file__.path }}`. The input-relative path is kept.
  The rendered text uses `/` separators. It is split on `/`.
  An absolute result stops the command. An empty result stops the command.
  A segment that is empty, `.`, or `..` stops the command.
  A slash inside a variable becomes another directory.
  The joined path must stay inside `path`. The extension is whatever the layout writes. `{{ __file__.ext }}` is the last suffix.
  A set `type: date` value prints with `default_date_format`. `Y`, `m`, and `d` are the `%Y`, `%m`, and `%d` fields.
  `{{ issued.strftime('%Y-%m') }}` is a custom pattern. A template that names a date fails when that date was omitted.
- `operation` is `copy`, `symlink`, or `hardlink`. Omitted, it is `copy`. Any other word stops the command.
- `on_conflict` is `error`, `skip`, or `overwrite`. Omitted, it is `error`. Any other word stops the command.
  It applies when the destination exists and this profile has no output event for that path.
  It also applies when the latest event for this document and output name matches the destination, the operation, and the source hash, but the file on disk no longer matches that apply.
  It does not apply to a destination claimed twice in this run. It does not apply when the latest event for that path belongs to another document or another output name.

The latest event for a document and output name is the prior apply. The latest event for a destination is the claim. Both reads use the events already stored. An output event does not change the document.

- The prior apply matches the new destination, the operation, and the source hash, and the file on disk matches that apply. Status `unchanged`. No write and no event.
  A copy matches when the destination sha256 equals the source hash.
  A symlink matches when its target is the absolute source path stored under the input.
  A hardlink matches when it is the same inode as that source.
- That prior apply is ours and the source hash or the operation changed. Status `replace`. `previous` is `existed` true and `ours` true, with the prior operation and source hash.
- The path does not exist, and no other document claims it. Status `write`. `previous` is `existed` false. `ours` is true only when an earlier event for this profile already recorded that same path. Then `previous` also carries that event's operation and source hash.
- The path exists and this profile has no event for it.
  `error`: status `conflict`. `run` writes nothing.
  `skip`: status `skip`. The file stays. No event.
  `overwrite`: status `replace`. `previous` is `existed` true and `ours` false. Revert cannot restore those bytes. The database stores the hash, not the file.
- The prior apply matches, but the file on disk does not. The same three words. `overwrite` stores `existed` true and `ours` true, with the prior operation and source hash.
- A new layout points the document at a new path. The old file stays. Prune is a later `output prune`. The new path follows the rules above.
- The latest event for the destination belongs to another document, or to another output name of this document. The command stops. `on_conflict` does not apply. It does not use a document id.
  Message: `Destination "{dest}" is already claimed. Owner: profile "{profile}" path "{path}" output "{output}". Requested: profile "{profile}" path "{path}" output "{output}".`
  Advice: `Choose another layout. overwrite cannot take a path recorded for someone else.`
- Two planned actions in this run resolve to the same destination. The command stops before any write. This includes two profiles selected together.
  Message: `Two files in this run map to the same destination "{dest}". First: profile "{profile}" path "{path}" output "{output}". Second: profile "{profile}" path "{path}" output "{output}".`
  Advice: `Change the layout so each file renders a different path.`
- The source path and the destination path are the same file. The command stops.
- The destination exists and is a directory. The command stops.

`copy` uses a metadata-preserving file copy. `symlink` points at the absolute source path stored under the input. `hardlink` links that path. A cross-device hardlink stops the command. The tip says to use `copy`.

Parents are created on a real write. A parent that exists and is a file stops the command. Preview and `--dry-run` create nothing.

`append_output` runs after the file operation returns, and only for `write` and `replace`. `recorded_at` is UTC ISO-8601. `source_hash` is the document hash. `output_name` is the item name. `destination` is the absolute path.

### Cases

Second run. The copy is still the same bytes. Status `unchanged`. `run` prints no row for it. No event is appended.

New bytes. `db import` stored the generation. The next output run replaces the copy. `previous` has `ours` true and the old source hash.

Not in the library. The file is `new`. Preview prints the row, warns `This file is not in the library.`, and exits 1. `run` warns and writes nothing. No sqlite file is created.

Vars. The stored vendor is `Bank2000` and the live value is `Bank2001`. The warning says `vendor was "Bank2000", now "Bank2001".` Preview prints the destination that uses `Bank2001` and exits 1. `run` writes nothing and prints no destination table.

Duplicate. `record_identity` is `hash`. The extra path has no document. Output leaves it out. The owning document is written when its own row is `unchanged`.

Foreign file. The destination exists and no output event names it. `on_conflict` is `error`. Preview shows `conflict` and exits 0. `run` writes nothing and exits non-zero.

Skip. The same foreign file, with `on_conflict: skip`. Status `skip`. The file stays. No event.

Overwrite. The same foreign file, with `on_conflict: overwrite`. The file is replaced. `previous` has `existed` true and `ours` false.

Other document. The latest event for that path belongs to another document. The command stops. The message is the already-claimed text above. `overwrite` does not take the path.

Layout move. `layout` changes. The new path is `write`. The old file stays on disk. The old event stays.

When. `when` renders `false`. Status `skip`. The column is `false`. The layout is not rendered. A file whose document status is `new` does not stop the command when `when` is `false`.

Bool words. `when: '{{ __match__.kind == "invoice" }}'` becomes `true` or `false`. `when: maybe` stops at load. `when: '{{ vendor }}'` stops when vendor renders `Bank2000`.

Escape. A layout that renders `../outside` stops the command. A layout that renders an absolute path stops the command. No directory is created.

Two outputs. One file matches `books` and `cards`. Both destinations are planned. The same destination from both items stops the command before any write.

## 5.4 Sqlite driver

`driver: sqlite` writes an external sqlite file. Architecture 4.4. It does not call `append_output`. Profile schema version stays `2`.

- `path` is required. It is a profile path template, the same language as `inputs.path`. It is rendered once. A relative result resolves from `__config__.root_dir`. An empty result stops the command. A result that exists and is a directory stops the command. A missing parent is created only on a real write. Preview and `--dry-run` create nothing.
- Shared `kinds` and `when` follow 5.2. Listed kinds also name which `data_<kind>` tables to ensure. Omitted `kinds` means every matched kind. A kind name that is not a SQL identifier `[A-Za-z_][A-Za-z0-9_]*` stops the command.
- Unknown keys stop the command. The sqlite driver accepts only `path` beyond the shared keys.
- Custom SQL, views, and user queries are a later mode. They are not read in this step.

Export tables:

- `hash`: primary key `hash` TEXT, the content sha256.
- `files`: primary key `hash` references `hash(hash)`. Columns: `path`, `file_dir`, `file_name`, `file_stem`, `file_ext`, `match_kind`, `rule`, `mtime`, `ctime`. `path` is the input-relative path with `/` separators, the same meaning as the profile document path.
- `data_<kind>`: one table per kind that is listed or appears in the planned set. Primary key `hash` references `hash(hash)`. One column per `kind_schema` local var name for that kind. A kind with no `kind_schema` entry still gets `data_<kind>` with only `hash`.

Type map: `text`, `date`, `time`, and `datetime` are TEXT. `int` and `bool` are INTEGER. `float` is REAL. Unset variables store SQL NULL. Bool stores `0` or `1`. Date, time, and datetime store their display strings.

Identity is the content hash. One hash is one document. The `files` row and the `data_<kind>` row for that kind use the same hash. Two planned files in this run that share a hash for the same output item stop the command before any write. External rows that supershelf did not write are left alone. Supershelf does not delete rows when a document leaves the library.

Schema sync runs on a real write, before the upsert:

1. Ensure `hash` and `files` exist with the fixed columns.
2. For each required kind, ensure `data_<kind>` exists with the expected columns and declared types.
3. A missing column is added with `ALTER TABLE ... ADD COLUMN`.
4. An incompatible existing column type, or any other unrecoverable drift, stops the command. The tip says to delete the sqlite file and re-run so the schema can be recreated.
5. Extra columns that the schema no longer lists stay. Unrelated rows stay.

`plan` opens the export file read-only when it already exists. A missing file is not created at plan time.

- No row for this hash: status `write`.
- A row exists and every compared `files` and `data_<kind>` value matches: status `unchanged`. No write.
- A row exists and any compared value differs: status `replace`.

`operation` is `upsert`. The CLI `dest` is the document relative path. `run` prints `write` and `replace` rows the same way as the file driver. Preview prints `unchanged` too.

`apply` creates the parent directory and the sqlite file when needed, syncs the schema, then upserts `hash`, `files`, and `data_<match_kind>` in one transaction. It does not append a profile output event.

The document gate from 5.2 still applies. A stale file does not write the export database.

### Cases

First run. The export file is missing. Status `write`. The file, `hash`, `files`, and `data_<kind>` are created. No profile output event.

Second run. The same hash and the same values. Status `unchanged`. `run` prints no row for it. The export file is not opened for write.

Vars change. `db import` stored the new snapshot. The next output run replaces the `data_<kind>` row. Status `replace`.

New kind column. The kind schema gains a local var. The next real write adds the column and upserts. Existing rows keep NULL in that column until updated.

Incompatible schema. A column type does not match the kind schema. The command stops. The tip says to delete the sqlite file and re-run.

Preview and dry-run. Status `write` is planned. The export file is not created.

Duplicate hash. Two selected files share a hash for the same sqlite output. The command stops before any write.

Stale document. The file is `new`. Preview warns and exits 1. `run` writes nothing. The export file is not created when it was missing.

When. `when` renders `false`. Status `skip`. No upsert.

Two sqlite outputs. Different `path` values. The same document relative path is allowed. The host destination key includes the export file.
