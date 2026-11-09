# 7 Database

Behavior. Index: [README](../README.md).

`supershelf db show`, `supershelf db vars`, and `supershelf db table` print document rows from the profile sqlite file. They do not scan, resolve, or write. They do not create the file. A missing file prints no rows. `supershelf db import` stores matched files. Behavior 4.

The sqlite schema does not follow the user's vars. Each variable stays inside `vars_json`. Architecture 3.2. `db show` and `db vars` keep vars in one cell. `db table` expands each stored name into its own column. Events have no command. A sqlite browser reads them.

Shared read rules for `show`, `vars`, and `table`:

- Profile selection is `--config` and `--profile`, same as the other commands.
- `--dry-run` changes nothing. The commands have nothing to write.
- A `duplicate` live file has no document row and is not listed. The scan plan prints it. 4.1.
- Printed cells use the display string for a set binding. A stored binding whose `value` is null prints the word `null`, same as `scan vars`. Typed `value` and `value_sources` are not printed as their own columns.

## 7.1 Show

- supershelf db show
- One row per document, including `missing` and `unmatched`.
- Columns: profile, presence, input, path, kind, rule, hash, generation, mtime, ctime, vars.
- vars is one cell. Each stored name is one line: the name, ": ", then the display string or `null` when unset, sorted by name.
  An empty object is an empty cell.
  JSON and YAML use one vars object of name to that same printed string.
  This does not add a column per name.
- input is the stored index. path is the stored relative path. kind is `match_kind`.

## 7.2 Vars

- supershelf db vars [KIND]
- One row per document, including `missing` and `unmatched`.
- Default columns: path, kind, vars.
  When more than one profile is selected, the first column is `profile`. One profile omits it.
- vars is one cell. The table format dumps the name-to-printed-string object as YAML text, keys sorted.
  An unset stored binding prints `null`. An empty object is an empty cell.
  JSON and YAML whole-row formats keep vars as one nested object of name to that same printed string.
- KIND is optional. When set, keep only documents whose `match_kind` equals KIND.
  An unknown KIND prints no rows.

## 7.3 Table

- supershelf db table [KIND]
- One row per document, including `missing` and `unmatched`. Best for data export.
- Default columns: path, kind, then one column per stored var name.
  When more than one profile is selected, the first column is `profile`. One profile omits it.
  The var columns are the sorted union of keys present in the selected rows.
  A name missing on a row is an empty cell. An unset stored binding on a row prints `null`.
  This does not use `vars_schema` or `kind_schema` to invent columns.
- KIND is optional. When set, keep only documents whose `match_kind` equals KIND.
  An unknown KIND prints no rows.
