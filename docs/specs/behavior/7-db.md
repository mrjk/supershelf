# 7 Database

Behavior. Index: [README](../README.md).

`supershelf db show` prints document rows from the profile sqlite file. It does not scan, resolve, or write. It does not create the file. A missing file prints no rows.

The sqlite schema does not follow the user's vars. Each variable stays inside `vars_json`. Architecture 3.2. This command does not expand `vars_json` into columns. Events have no command. A sqlite browser reads them.

## 7.1 Show

- supershelf db show
- One row per document, including `missing` and `unmatched`.
- Columns: profile, presence, input, path, kind, rule, hash, generation, mtime, ctime, vars.
- vars is one cell. Each stored name is one line: the name, ": ", then the display string, sorted by name.
  An empty object is an empty cell.
  JSON and YAML use one vars object of name to display string.
  This does not add a column per name.
- input is the stored index. path is the stored relative path. kind is `match_kind`.
- A `duplicate` live file has no document row and is not listed. The scan plan prints it. 4.1.
- Profile selection is `--config` and `--profile`, same as the other commands.
- `--dry-run` changes nothing. The command has nothing to write.
