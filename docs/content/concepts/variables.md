# Variables

`scan vars` takes the kept files, then the matched set, and prints one row per matched file. Columns: `profile`, `input`, `path`, `kind`, `rule`, `vars`.

`kind` is the final `__kind__` after overrides. `rule` stays the match rule name. `vars` is one cell. Each set variable uses two lines. The first is the name, `: `, then the display string. The second is `sources: ` plus the labels that wrote it, joined by `, `. An unset variable is left out. `--format json` and `--format yaml` use the Python value instead of the display string, so a float can be `12.5` while the table shows `12.50`. `date`, `time`, and `datetime` use the accepted spelling in both.

Source labels are `fact`, `filename`, `default`, `rule:<rule name>`, `kind:<kind file path>`, and `override:<path pattern>`. A later write appends a label. It keeps the earlier ones. The last label is the winner.

The walk is the full walk. mtime, ctime, and sha256 are required. There is no `--quick`. The path argument is the same as `scan files`: omit it to list every matched file, pass an exact file path to list that file, or pass any other value to list paths that start with it. A value that no kept file has stops the command. The same path in two inputs is listed twice. When a path is set, only the selected files are matched, so other files are not warned.

Unmatched files log the same warning as `scan kinds`, once per file. They add no row.

The command does not create the database file, the cache file, or an output tree. It may read, create, or append a kind file. See [Kind files](kind-files.md).

## Facts and assignments

Facts are the base scope. An assignment of the same name shadows that fact for later templates and replaces the printed value. While a key is being rendered, a reference to itself still sees the previous layer, so the fact stays visible when no earlier assignment set that name.

Profile scope from [Paths](paths.md) is available to templates. It is not printed.

Internal facts are always printed, in this order:

- `__kind__`: the kind from matching, until an override replaces it
- `__rule_name__`: the match rule name
- `__ctime__` and `__mtime__`: the stored UTC ISO-8601 timestamps, not `default_date_format`
- `__file_hash__`: lowercase sha256
- `__file_name__`: the filename
- `__file_stem__`: the filename without its last suffix. `archive.tar.gz` stores `archive.tar`
- `__file_ext__`: the last suffix without the leading dot. `archive.tar.gz` stores `gz`. A name with no suffix stores an empty string. A leading dot, as in `.gitignore`, is not a suffix, so the extension is empty and the stem is the whole name
- `__file_path__`: the path relative to the input, with `/` separators
- `__file_dir__`: the directory relative to the input. Empty when the file sits in the input directory

`file_ctime` is `__ctime__`. `file_mtime` is `__mtime__`. Both are printed after the internals.

Named groups from the winning regex are facts, printed after the aliases, in the order the pattern declared them.

## Layers

Assignments are the user layers. Later wins on the same key. Each layer is applied before the next one starts.

1. `default_vars`
2. `match_rules` `vars` for the winning rule.
3. The kind-file row for that path. See [Kind files](kind-files.md).
4. The first matching `overrides` item. This is the highest layer, and the only layer that may set `__kind__`.

`default_vars` and rule `vars` must not set an internal name, `file_ctime`, or `file_mtime`. A kind-file row must not either. Only overrides may set `__kind__`. That changes the printed kind and the `__kind__` fact seen by later override templates. It does not change `rule`, and it does not load another kind file. Overrides must not set the other internal names, `file_ctime`, or `file_mtime`.

`__date__` is not an internal. Any of these layers may set it. A kind-file `__date__` cell is parsed into `YYYY-MM-DD`. The other layers use candidates.

Omitted `default_vars`, omitted rule `vars`, or no kind-file cells for that path means that layer is empty.

A new key is appended. A key that already exists keeps its first position. The printed row uses the final display string. The kind-file row is applied after the rule template has stored its string, so the rule does not read the cell. A later override template does. Inside the cell, the lines are internals, then `file_ctime` and `file_mtime`, then regex groups, then assignment keys in first-seen order.

## Types

`vars_schema` is an optional top-level mapping. Each key is a variable name. A name with no entry is `text`. `kind_schema` is not read.

`type` is `text`, `int`, `float`, `bool`, `date`, `time`, or `datetime`, in lower case. `date` is `YYYY-MM-DD`. `time` is `HH:MM` or `HH:MM:SS`. `datetime` is `YYYY-MM-DDTHH:MM` or `YYYY-MM-DDTHH:MM:SS`, and a set value always includes a clock. No timezone and no fractional seconds. Seconds stay in the display only when they were written. `15:04` and `15:04:00` match as the same clock in `allowed` and in range checks.

Built-in facts are `text`, except `__date__`, which is `date`. `__ctime__` and `__mtime__` stay `text`, because they include fractional seconds and a UTC offset. A user entry may set `desc` and `unit` on a locked built-in. On `__date__` it may also set `mandatory`, `default`, and `validation`. A new name that starts with `__` stops the command. `internal: true` on a user name stops the command.

Other keys on a user entry: `desc`, `unit`, `mandatory` (default false), `default`, and `validation`. Unknown keys stop the command. `mandatory` is checked after the last layer. `None` fails the file. An empty text string is set, so it passes.

`default` and `default_vars` are one slot. Setting the same name in both stops the command. A schema entry with no `default` takes the `default_vars` value. `default_vars` stays a string or a list of strings. `vars_schema.<name>.default` may also be a typed literal (`12`, `1.5`, `true`). Quote date, time, and datetime defaults. `null` is not unset. Omit the key.

`validation` may set `allowed`. `text`, `date`, `time`, and `datetime` may also set `pattern`, `min_length`, and `max_length`. `pattern` must match the whole display string. `int`, `float`, `date`, `time`, and `datetime` may set `ge`, `gt`, `le`, and `lt`. A constraint that does not apply to the type stops the command.

A list in an assignment is a candidate list: the first success is kept, and the stored value is one scalar. `type: list` stops the command. A kind-file cell is one string, not a candidate list.

Jinja reads the display string after a successful cast. It does not receive the Python value. `{{ amount + 1 }}` is not integer math. `regex_replace` and `regex_time_var` still receive strings. `regex_time_var` returns `YYYY-MM-DD`, which satisfies `date` and misses `time` and `datetime`.

A regex group is cast when the fact is stored. A group that does not match its type stops the file. There is no next candidate. Capture the raw text under another name when a later candidate list should supply the typed value.

## Candidates

A var table is a mapping. This section is `default_vars`, rule `vars`, and `overrides`. A kind-file cell is one string, then cast to the name's type. Each key matches `[A-Za-z_][A-Za-z0-9_]*`. Each value is a string, or a list of strings. A string is one candidate. A list is an ordered fallback. An empty list stops the command. Numbers, booleans, nulls, dates, and nested mappings stop the command in these layers. Quote scalars such as `2026-04-25`. Typed literals belong on `vars_schema.<name>.default`.

A candidate with no `{{`, `{%`, or `{#` is a literal string. It is not compiled. Any other candidate is a Jinja template. Each distinct template source is compiled once per process. Rendered results are not cached. A syntax error stops the command when that template is loaded. Shape errors in `default_vars`, rule `vars`, and `overrides` are checked before the walk. A kind file is checked the first time that kind and input need it. `kind_overrides_sep` and `kind_overrides_date_format` are checked before the walk.

Jinja uses strict undefined names. `autoescape` is off. An unknown name fails that candidate. The rendered string is then cast to the name's type. A cast miss or a validation miss fails that candidate. The first candidate that does not fail is kept. The list is not kept. Later templates read the display string. Inserted strings are not rendered again. A non-template literal that cannot cast stops the command when the table is loaded, including when a later candidate might have worked.

A template can read facts and any assignment already rendered. It cannot read a key later in the same mapping. That name is not defined yet. The key being rendered sees the previous layer's string, not the candidate list being tried. `account = "{{ account }}"` reads the group when no earlier layer defined `account`. A `default_vars` value hides the group from the rule template of the same name. A rule's `{{ __date__ }}` reads the `__date__` string the earlier layer already kept. It does not run that layer's other candidates again.

An empty string is a success for `text`. For `int`, `float`, `bool`, `date`, `time`, and `datetime`, empty or whitespace is a miss. `__date__` is `date`, so an empty string misses.

If every candidate fails, the command stops. The error names the profile, the input, the path, and the variable. `__date__` is the exception: if no candidate yields `YYYY-MM-DD`, `__date__` is omitted and the command continues. A later step that needs `__date__` fails when it was omitted. This version does not write output paths.

A function that has nothing to return fails that candidate only, by raising `VarCandidateError`. Any other exception from a template stops the command. Built-in commands are documented in [Template commands](template-commands.md).

## Overrides

`overrides` is an optional list. Each item has `path` and `vars`. Unknown keys are ignored. `path` is a glob, full-matched against the path relative to the input, with the same `*` and `**` rules as include. A path with no glob characters is an exact match. The first matching item wins. Later items are not merged. An item that matches nothing is fine. Paths are not templated.

`__date__` on an override is already `YYYY-MM-DD`. Quote it. An unquoted YAML date is a config error.
