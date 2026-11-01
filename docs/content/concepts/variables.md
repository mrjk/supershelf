# Variables

`scan vars` takes the kept files, then the matched set, and prints one row per matched file. Columns: `profile`, `input`, `path`, `kind`, `rule`, `vars`, `sources`.

`kind` is `__kind__` from the match rule. `rule` stays the match rule name. `vars` is one cell. Each set variable is one line: the name, `: `, then the display string. Names are sorted alphabetically. An unset variable is left out. `sources` is the next column. It has one line per name, in that same order. Each line is the labels that wrote the name, joined by `, `. `csv` uses those same two cells. `--format json` and `--format yaml` omit the `sources` column. They replace `vars` with one object per name: `value` is the Python value, and `value_sources` is the label list. `display` is not in the object. A float can have `value` `12.5` while the table shows `12.50`. `date`, `time`, and `datetime` use the accepted spelling for both `value` and the table.

Source labels are `fact`, `default`, `rule:<rule name>`, and `kind:<kind file path>`. A later write appends a label. It keeps the earlier ones. The last label is the winner. A layer that misses does not add a label and does not remove earlier ones.

Internal names are left out of `vars` and `sources`, and out of the json and yaml objects, unless `--all` is set. `__date__`, schema names, regex groups, and other assigned names stay.

The walk is the full walk. mtime, ctime, and sha256 are required. There is no `--quick`. The path argument is the same as `scan files`: omit it to list every matched file. If any kept path equals the selector, every input lists that exact path only. Otherwise the selector lists paths that start with it. A value that no kept file has stops the command. The same path in two inputs is listed twice. When a path is set, only the selected files are matched, so other files are not warned.

Unmatched files log the same warning as `scan kinds`, once per file. They add no row.

`scan vars` and `record run` create the database file when `meta()` runs and the cache misses. `--dry-run` does not. `scan files` and `scan kinds` do not. This command does not create the cache file or an output tree. It may read, create, or append a kind file. See [Kind files](kind-files.md).

## Facts and assignments

Facts are the base scope. An assignment of the same name shadows that fact for later templates and replaces the printed value. While a key is being rendered, a reference to itself still sees the previous layer, so the fact stays visible when no earlier assignment set that name.

Profile scope from [Paths](paths.md) is available to templates. It is not printed.

Internal facts stay in scope for templates. `scan vars` prints them only with `--all`:

- `__kind__`: the kind from matching
- `__rule_name__`: the match rule name
- `__ctime__` and `__mtime__`: the stored UTC ISO-8601 timestamps, not `default_date_format`
- `__file_hash__`: lowercase sha256
- `__file_name__`: the filename
- `__file_stem__`: the filename without its last suffix. `archive.tar.gz` stores `archive.tar`
- `__file_ext__`: the last suffix without the leading dot. `archive.tar.gz` stores `gz`. A name with no suffix stores an empty string. A leading dot, as in `.gitignore`, is not a suffix, so the extension is empty and the stem is the whole name
- `__file_path__`: the path relative to the input, with `/` separators
- `__file_dir__`: the directory relative to the input. Empty when the file sits in the input directory

Named groups from the winning regex are facts. They are stored in the order the pattern declared them. The table sorts every printed name alphabetically.

## Layers

Assignments are the user layers. Later wins on the same key. Each layer is applied before the next one starts.

1. `default_vars`
2. `match_rules` `vars` for the winning rule.
3. The kind-file row for that path. See [Kind files](kind-files.md). This is the last assignment layer.

`default_vars` and rule `vars` must not set an internal name. A kind-file row must not either. `__kind__` stays the kind from the match rule.

`__date__` is not an internal. Any of these layers may set it. The filename does not. A stem that is a date stays `__file_stem__`. To use it, write a candidate such as `{{ regex_time_var(__file_stem__, __default_date_format__) }}`. A kind-file `__date__` cell is parsed into `YYYY-MM-DD`. The other layers use candidates.

Omitted `default_vars`, omitted rule `vars`, or no kind-file cells for that path means that layer is empty.

A later write replaces the display string and keeps the name's earlier source labels. The kind-file row is applied after the rule template has stored its string, so the rule does not read the cell. The table sorts every printed name alphabetically, and the `sources` column follows that order.

## Types

`vars_schema` is an optional top-level mapping. Each key is a variable name. A name with no entry is `text`. A kind can point at those names. See [Kind schema](#kind-schema).

`type` is `text`, `int`, `float`, `bool`, `date`, `time`, or `datetime`, in lower case. `date` is `YYYY-MM-DD`. `time` is `HH:MM` or `HH:MM:SS`. `datetime` is `YYYY-MM-DDTHH:MM` or `YYYY-MM-DDTHH:MM:SS`, and a set value always includes a clock. No timezone and no fractional seconds. Seconds stay in the display only when they were written. `15:04` and `15:04:00` match as the same clock in `allowed` and in range checks. A bool accepts `true`, `yes`, and `1`, or `false`, `no`, and `0`, in any case. The display is `true` or `false`. An int display drops a leading `+` and leading zeros, so `007` prints as `7`.

Built-in facts are `text`, except `__date__`, which is `date`. `__ctime__` and `__mtime__` stay `text`, because they include fractional seconds and a UTC offset. A user entry may set `desc` and `unit` on a locked built-in. On `__date__` it may also set `mandatory`, `default`, and `validation`. A new name that starts with `__` stops the command. `internal: true` on a user name stops the command.

Other keys on a user entry: `desc`, `unit`, `mandatory` (default false), `default`, and `validation`. Unknown keys stop the command. `mandatory` is checked after the last layer. `None` fails the file. An empty text string is set, so it passes.

`default` and `default_vars` are one slot. Setting the same name in both stops the command. A schema entry with no `default` takes the `default_vars` value. `default_vars` stays a string or a list of strings. `vars_schema.<name>.default` may also be a typed literal (`12`, `1.5`, `true`). Quote date, time, and datetime defaults. `null` is not unset. Omit the key.

`validation` may set `allowed`. `text`, `date`, `time`, and `datetime` may also set `pattern`, `min_length`, and `max_length`. `pattern` must match the whole display string. `int`, `float`, `date`, `time`, and `datetime` may set `ge`, `gt`, `le`, and `lt`. A constraint that does not apply to the type stops the command.

A list in an assignment is a candidate list: the first success is kept, and the stored value is one scalar. `type: list` stops the command. A kind-file cell is one string, not a candidate list.

Jinja reads the display string after a successful cast. It does not receive the Python value. `{{ amount + 1 }}` is not integer math. `regex_replace` and `regex_time_var` still receive strings. `regex_time_var` returns `YYYY-MM-DD`, which satisfies `date` and misses `time` and `datetime`.

A regex group is cast when the fact is stored. A group that does not match its type stops the file. There is no next candidate. Capture the raw text under another name when a later candidate list should supply the typed value.

## Kind schema

`kind_schema` is an optional top-level mapping. Each key is a kind name. A file whose kind is not listed keeps the profile catalog.

A kind has `desc` and `vars_schema`. Each key under that `vars_schema` is a variable name for files of that kind. The value names a declared `vars_schema` entry, or `__date__`. A string is that name (`my_amount: amount`). Null or a blank string uses the local name. In YAML, `amount:` is null. TOML has no null, so write `amount = ""`. An object may omit `schema`, and the local name is used (`tax: {mandatory: true}` uses `tax`). That catalog entry supplies `type` and `internal`. The kind cannot set those.

Omitted `desc`, `unit`, `mandatory`, and `validation` are copied from the catalog entry. A `validation` mapping on the kind replaces the catalog one. `default` is not copied. Set it on the kind when that local name needs a default. Profile `default` and `default_vars` apply to that catalog name on files whose kind is not listed. On a listed kind they apply only when that kind's `vars_schema` includes the name.

When the kind lists a name the profile also has, files of that kind use the kind's spec. `mandatory: false` there leaves the name optional for that kind. Names the kind does not list stay on the profile spec, including profile `mandatory`.

`supershelf schema` prints one JSON document, keyed by profile name. It does not walk inputs. With `kind_schema`, each kind is an object under `$defs`. Without it, the object is the declared `vars_schema` names. Locked internals are left out. `__date__` is included only when `vars_schema.__date__` is set. If neither key is set, the command stops with status 2. The schema describes resolved values, not the strings in a kind file or in rule `vars`. `auto` and `always` add missing schema columns on the right of a CSV. A name that is not a legal column is left out. With no schema columns, a new CSV still starts as `PATH,__date__`.

## Candidates

A var table is a mapping. This section is `default_vars` and rule `vars`. A kind-file cell is one string, then cast to the name's type. Each key matches `[A-Za-z_][A-Za-z0-9_]*`. Each value is a string, or a list of strings. A string is one candidate. A list is an ordered fallback. An empty list stops the command. Numbers, booleans, nulls, dates, and nested mappings stop the command in these layers. Quote scalars such as `2026-04-25`. In YAML, also quote `yes`, `no`, `on`, and `off`. Those words become booleans before Supershelf reads them, and a boolean is a config error here. Typed literals belong on `vars_schema.<name>.default`.

A candidate with no `{{`, `{%`, or `{#` is a literal string. It is not compiled. Any other candidate is a Jinja template. Each distinct template source is compiled once for that profile. Another profile in the same command compiles it again. Rendered results are not cached. A syntax error stops the command when that template is loaded. Shape errors in `default_vars` and rule `vars` are checked before the walk. A kind file is checked the first time that kind and input need it. `kind_overrides_sep` and `kind_overrides_date_format` are checked before the walk.

Jinja uses strict undefined names. `autoescape` is off. An unknown name fails that candidate. The rendered string is then cast to the name's type. A cast miss or a validation miss fails that candidate. The first candidate that does not fail is kept. The list is not kept. Later templates read the display string. Inserted strings are not rendered again. A non-template literal that cannot cast stops the command when the table is loaded, including when a later candidate might have worked.

A template can read facts and any assignment already rendered. It cannot read a key later in the same mapping. That name is not defined yet. The key being rendered sees the previous layer's string, not the candidate list being tried. `account = "{{ account }}"` reads the group when no earlier layer defined `account`. A `default_vars` value hides the group from the rule template of the same name. A rule's `{{ __date__ }}` reads the `__date__` string the earlier layer already kept. It does not run that layer's other candidates again.

An empty string is a success for `text`. For `int`, `float`, `bool`, `date`, `time`, and `datetime`, empty or whitespace is a miss. `__date__` is `date`, so an empty string misses.

If every candidate in a layer misses, that layer does not write the name. An earlier value stays. When no layer has written it, the name stays unset and is left off the row. The command continues. `mandatory` runs after the last layer, and `None` stops the file. A fact or a kind-file cell that cannot cast still stops the file. There is no next candidate for those. This version does not write output paths.

A function that has nothing to return fails that candidate only, by raising `VarCandidateError`. Any other exception from a template stops the command. Built-in commands are documented in [Template commands](template-commands.md).
