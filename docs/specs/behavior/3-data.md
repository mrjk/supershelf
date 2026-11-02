# 3 Data

Behavior. Index: [README](../README.md).

`supershelf data` reads and writes kind files. The doc site is unchanged until implementation.

- It uses the same full walk as scan vars, and the same resolved values.
  There is no --quick and no path filter.
- It does not read or write documents, events, or vars_json, and it does not append a record event.
  Resolution does not read vars_json. Behavior 4 owns those tables.
  cache_file stays unused. content_meta is not that path.
  It does not create an output tree.
- Profile selection is the same as the other commands: --config and --profile.
- Say var, not field. A field is a match-rule slot, such as regex or filename_glob.
  The feed flag is --var.
- Say kind file. kind_overrides_mode, kind_overrides_date_format, kind_overrides_sep,
  and kind_overrides_config are the kind-file settings from 2.3.2.
- scan vars --all prints `__file__` and `__match__` fields. data prune --all runs every purge.
  The two flags do not share a meaning.

## 3.1 Shared rules

- Values are the display strings scan vars prints.
  Layers are facts, default_vars, the match rule, then the kind file.
  A filled cell is already that string. An empty cell receives the lower layer.
  An unset var stays unset. Feed does not blank a cell.
  Namespace fields stay out. `__date__` is allowed.
- kind_overrides_mode does not gate these commands.
  scan vars still owns auto, manual, always, and disabled.
  manual and disabled still allow data feed and data prune to write.
  An empty kind_overrides_config means there is no file to read or write, and the command stops.
- The kind file is chosen as in 2.3.2. The first existing template wins.
  A missing file is created from the first template when the command needs to write.
  Parent-directory rules stay the same as 2.3.2.
  data prune does not create a missing file.
- A new CSV column is appended on the right. Feed does not reorder columns.
  TOML and YAML append a new key and keep the existing key order.
- The stored cell is the display string. A float stays 12.50. A bool stays true or false.
  scan vars in auto and always must not rewrite existing cell text.
  Feed and prune do rewrite the file. Values that were not selected stay.
  CSV quoting and column adds may change bytes.
- Two inputs that share one kind file and the same relative path:
  if the selected values differ, stop and name both inputs. Do not pick one.
- A mandatory var that is still unset stops the command before any write, same as scan vars.
- Duplicate path rows: update the first, leave the later row, and keep the warning from 2.3.2.
  A rewrite must not drop that later row.
- --dry-run prints the same summary the prompt would show, asks nothing, and writes nothing.
  It does not create the sqlite file, and it does not migrate it.
- A resolve error writes no kind file.
  A content_meta row already stored during that resolve stays.
- data feed and data prune edit kind-file cells and columns only.
  Those writes are not database rows.
  Feed resolves like scan vars. When a candidate calls meta(), feed uses the content_meta rules in 2.3.3.
  That cache write happens while the preview is computed, before Continue?
  A no leaves the cache in place, including a schema 1 file migrated to schema 2, and does not edit the kind file.
  The prompt guards kind-file edits only.
  Prune does not render templates, so it does not open the database.
- A feed or prune can change what the next record run resolves.
  That run may append a vars event. data does not write the event.
  A kind cell filled by feed is later labeled kind:<path>, not rule:<name>.
- data has no PATH filter. --missing uses the full walk.
  A later PATH filter must not drop kind-file rows outside that filter.
- data feed and data prune ask once for the whole run, before any write.
  The question is on stderr. y or yes writes. Anything else writes nothing.
  Not a terminal, and no --force, stops the command and tells the user to pass --force.
  --force writes without asking.
  The prompt names which kinds, vars, or purges are enabled.
- data show does not write kind files and does not prompt.
  It may write content_meta, as in 3.4.

### Cases

Empty kind paths. `kind_overrides_config: []` stops `data feed`, `data prune`, and `data show`. There is no file to use.

Disabled mode. `kind_overrides_mode` is `disabled`. `data feed` still creates or updates the kind file from the first template.

Shared path. Two inputs resolve the same kind file and the same relative path, and the selected `vendor` values differ. The command stops and names both inputs.

Not a terminal. `data feed` with no `--force` and no `--dry-run` stops and tells the user to pass `--force`.

Documents left alone. `data feed` fills an empty `vendor` cell. No document row and no event is written. The next `record run` may append `vars`. The new source label is `kind:<path>`.

Cache before the prompt. A candidate calls `meta()` and `content_meta` misses. The preview creates or migrates the sqlite file and inserts the cache row, then asks `Continue?`. No leaves that cache and does not edit the kind file.

Dry run. `data feed --dry-run` prints the summary and does not create, migrate, or insert `content_meta`.

## 3.2 data feed

### Command

- supershelf data feed [NAMES]
- Writes resolved values into the kind files.
- NAMES is one optional comma-separated argument. Spaces around commas are ignored.
  Each token must be either a rule kind or a var name, not both.
  A token that matches both stops the command and names --kind and --var.
- --kind is a comma-separated list of kinds.
  Selecting a kind enables every schema var of that kind.
- --var is a comma-separated list of var names.
- --kind and --var together keep only those vars on those kinds.
  A --var name that none of the selected kinds define stops the command.
- Positional names and the flags combine. An explicit flag is how a shared name is chosen.
- An unknown kind or var stops the command. A namespace root, or any other name that starts with `__` and is not `__date__`, stops the command.
- --force skips the prompt.
- Feed does not also append the empty rows scan vars appends.

### Selectors

- No arguments: every kind that has a matched file, and every schema var of that kind.
- Schema vars are the CSV header names for that kind. 2.3.2.
  A kind_schema entry uses its local names. Otherwise the declared vars_schema names are used.
  __date__ is included only when that schema lists it.
- A kind with no schema columns has no schema vars.
  Feed then uses the user-visible names scan vars would print for files of that kind,
  so dates and rule vars still get a cell.
- Selecting a kind enables all of that kind's schema vars, or the no-schema fallback above.

### Write

- Write the resolved display string into the selected cell.
  A filled cell is already that string, so the text stays.
  An empty cell receives it.
- __date__ is written with kind_overrides_date_format, not the stored YYYY-MM-DD.
  Other date vars stay YYYY-MM-DD. The kind-file format applies to __date__ only, as in 2.3.2.
- An unset var does not blank a cell.
- A selected name missing from the file is added. A matched path with no row is added.
  Other columns and other rows stay.
- CSV column rules from 2.3.2 still apply.
  A name that is not a legal column is left out of CSV and reported.

### Prompt

- One paragraph plus the file list.
  It names the selected kinds and vars, then says it writes those resolved values into empty cells.
  A filled cell stays.
  Then each kind file path and how many cells would change.
  Question: Continue? [y/N]
- -v lists the cells that would change. The summary is enough at the default log level.

### Cases

Both names. `invoice` is a kind and a var. `data feed invoice` stops and names `--kind` and `--var`.

No schema. A kind with no schema columns feeds the user-visible names `scan vars` prints, including a set `__date__`.

Date round-trip. Stored `__date__` is `2026-04-25`. `kind_overrides_date_format` is `%d/%m/%Y`. Feed writes `25/04/2026`. A `date` var that is not `__date__` stays `YYYY-MM-DD`.

Filled cell. The kind file already holds `Bank2000`. Feed writes `Bank2000` again. The text stays.

Empty cell. The rule set `vendor` and the cell is empty. Feed writes the rule's display string.

Unset. No layer set `owner`. Feed does not blank a hand-written `owner` cell, and it does not add an empty cell.

## 3.3 data prune

### Command

- supershelf data prune
- Edits existing kind files. It does not create a missing file.
- Flags are independent. Passing one flag does not turn the others on.
- No flags means the empty-column purge only.
- --all means every purge below.
  With --clear, each file is left empty, so the other purges do not change that result.
- --force skips the prompt.
- The prompt names which purges are enabled, lists the files, and gives the row and column counts.
  Same --force, terminal, and --dry-run rules as data feed.

### Purges

- Default, also available as --empty-fields:
  Drop a column or key that is not in that kind's schema and whose cells are all empty.
  An empty schema column stays. A non-empty extra column stays. One filled cell keeps the column.
  CSV drops the column. TOML and YAML omit the key.
- --missing:
  Drop a kind-file row whose path is not a matched file of that kind in this scan.
  This is not document presence missing. It does not delete a document, an event, or a hash.
  A document can stay missing or unmatched in the database after its kind-file row is gone.
  A file that moved to another kind is dropped from the old kind file.
  Two inputs that share one kind file keep the row when either input still matches that path for that kind.
- --clear:
  Rewrite each existing kind file with no rows. The file stays.
  CSV keeps its header. TOML and YAML keep an empty document.
  It does not delete the kind file, and it does not empty the database.
  The next record run sees the lower layers and may append vars.

### Cases

Prune default. A column `note` is not in the schema and every cell is empty. No flags drops it. A schema column that is empty stays. A non-schema column with one filled cell stays.

Prune flags. `--missing` does not also drop empty columns. `--empty-fields` does not also drop missing rows. `--all` includes `--clear`, so the kind file ends with no rows. The database rows stay.

Missing word. `--missing` drops a kind-file row for a path that is not matched as that kind. The document row stays, including when its presence is `missing`.

## 3.4 data show

### Command

- supershelf data show [KIND]
- Prints the live resolve. It does not read documents, events, or vars_json.
  It does not write kind files and it does not prompt.
  A recorded document is not required. A file that was never recorded is still shown.
  When a candidate calls meta(), show uses the content_meta rules in 2.3.3.
  A real show may create or migrate the sqlite file. --dry-run does not.
- One table per profile and kind, because each kind has its own columns.
  It does not return one merged row list.
  A title line names the profile, the kind, and the kind file path when there is one.
- Columns are path, then the var names: schema order first, then any other user-visible name scan vars would print.
  Values are the display strings. An unset var is blank.
- KIND limits the output to that kind. An unknown kind stops the command.
  A known kind with no matched files prints the title and no rows.
- No KIND prints every kind that has a matched file.
