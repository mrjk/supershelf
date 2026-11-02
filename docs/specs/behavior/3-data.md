# 3 Data

Behavior. Index: [README](../README.md).

`supershelf data` reads and writes kind files. The doc site is unchanged until implementation.

- It uses the same full walk as scan vars, and the same resolved values.
  There is no --quick and no path filter.
- It does not read or write documents, events, or vars_json, and it does not append a record event.
  Resolution does not read vars_json. Behavior 4 owns those tables.
  cache_file is the metadata cache in 2.3.3. data feed and data show may write it. data prune does not.
  It does not create an output tree.
  It does not create or migrate the sqlite file.
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
  Feed writes the uppercase column from 3.2 and does not write a lowercase cell.
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
  It does not create the sqlite file, and it does not migrate it. It does not create cache_file.
- A resolve error writes no kind file.
  A cache entry already stored during that resolve stays.
- data feed and data prune edit kind-file cells and columns only.
  Those writes are not database rows.
  Feed resolves like scan vars. When a candidate calls meta(), feed uses the cache rules in 2.3.3.
  That cache write happens while the preview is computed, before Continue?
  A no leaves cache_file in place and does not edit the kind file. It does not create or migrate the sqlite file.
  The prompt guards kind-file edits only.
  Prune does not render templates, so it does not open the cache or the database.
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
  It may write cache_file, as in 3.4.

### Cases

Empty kind paths. `kind_overrides_config: []` stops `data feed`, `data prune`, and `data show`. There is no file to use.

Disabled mode. `kind_overrides_mode` is `disabled`. `data feed` still creates or updates the kind file from the first template.

Shared path. Two inputs resolve the same kind file and the same relative path, and the selected `vendor` values differ. The command stops and names both inputs.

Not a terminal. `data feed` with no `--force` and no `--dry-run` stops and tells the user to pass `--force`.

Documents left alone. `data feed` writes `VENDOR` and leaves `vendor` empty. No document row and no event is written. The next `record run` still uses the lower layer. The source label is not `kind:<path>` from that feed column.

Cache before the prompt. A candidate calls `meta()` and the cache misses. The preview creates `cache_file` and stores the entry, then asks `Continue?`. No leaves that cache and does not edit the kind file. The sqlite file is not created.

Dry run. `data feed --dry-run` prints the summary and does not create `cache_file`.

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

- The feed column is the var name with ASCII letters uppercased.
  `vendor` is `VENDOR`. `__date__` is `__DATE__`.
  When that form is `PATH`, `SHA`, or `DATE`, wrap it: `_PATH_`, `_SHA_`, `_DATE_`.
  `Path` is still `_PATH_`. Feed never writes the headers `PATH`, `SHA`, or `DATE`.
- Write the resolved display string into that column.
  Replace the cell when the text differs. An equal cell is not a change.
  A lowercase or mixed-case cell is never written.
  An edit in the uppercase column is replaced on the next feed.
  Custom text belongs in the lowercase column.
- The value is the display string `scan vars` prints, including a filled lowercase cell.
  The uppercase column is not read back.
  It does not change the next resolve or the source label.
- `__date__` is written as `__DATE__` with kind_overrides_date_format, not the stored YYYY-MM-DD.
  Other date vars stay YYYY-MM-DD. The kind-file format applies to `__date__` only, as in 2.3.2.
- An unset var does not blank a cell and does not add an empty cell.
- A missing feed column is appended on the right. TOML and YAML append the key.
  A matched path with no row is added when a cell is written.
  Other columns and other rows stay.
- CSV column rules from 2.3.2 still apply.
  A name that is not a legal feed column is left out of CSV and reported.

### Prompt

- One paragraph plus the file list.
  It names the selected kinds and vars, then says it writes those resolved values into the uppercase columns.
  It replaces a cell when the text changes. Lowercase cells stay.
  Then each kind file path and how many cells would change.
  Question: Continue? [y/N]
- -v lists the cells that would change. The summary is enough at the default log level.

### Cases

Both names. `invoice` is a kind and a var. `data feed invoice` stops and names `--kind` and `--var`.

No schema. A kind with no schema columns feeds the user-visible names `scan vars` prints, including a set `__date__`.

Date round-trip. Stored `__date__` is `2026-04-25`. `kind_overrides_date_format` is `%d/%m/%Y`. Feed writes `__DATE__` as `25/04/2026`. The `__date__` cell stays. A `date` var that is not `__date__` is written as `_DATE_` and stays `YYYY-MM-DD`.

Filled uppercase cell. `VENDOR` already holds the resolved display string. The text stays, and the file is not rewritten for that cell. A different `VENDOR` cell is replaced. The lowercase `vendor` cell stays.

Empty custom cell. The rule set `vendor` and the `vendor` cell is empty. Feed writes the rule's display string into `VENDOR`. `vendor` stays empty. The next resolve still uses the rule.

Custom cell. `vendor` holds `Mine`. Feed writes `Mine` into `VENDOR`. `vendor` stays `Mine` and still wins on the next resolve.

Unset. No layer set `owner`. Feed does not blank `OWNER` or `owner`, and it does not add an empty cell.

Reserved name. A var named `path`, `sha`, or `date` is written to `_PATH_`, `_SHA_`, or `_DATE_`. Those columns are ignored on the next scan.

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
  A feed column is an extra column. An empty one is dropped. One filled cell keeps it.
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
  When a candidate calls meta(), show uses the cache rules in 2.3.3.
  A real show may create cache_file. --dry-run does not. It does not create the sqlite file.
- One table per profile and kind, because each kind has its own columns.
  It does not return one merged row list.
  A title line names the profile, the kind, and the kind file path when there is one.
- Columns are path, then the var names: schema order first, then any other user-visible name scan vars would print.
  Values are the display strings. An unset var is blank.
  A feed column is not a column in this table.
- KIND limits the output to that kind. An unknown kind stops the command.
  A known kind with no matched files prints the title and no rows.
- No KIND prints every kind that has a matched file.
