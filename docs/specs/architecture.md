# Architecture

Behind the scenes: models, cast rules, and edge cases. Command steps live in [behavior.md](behavior.md). Pasteable config lives in [examples.md](examples.md). The short command pipeline on the doc site is `docs/content/reference/architecture.md`.

These numbers are not product steps. Cite them as architecture 1.7. Product steps are 1, 2, 3, and 4 in behavior.md.

Status: the variable types below are implemented. Each binding stores a Python value and a display string. Jinja still reads the display string. `record run` writes the profile database in section 3. Scan commands, `schema`, and `profiles` do not. `supershelf schema` prints JSON Schema for declared `vars_schema` and `kind_schema` entries. `scan vars` uses those names as CSV columns. With no schema columns, a new CSV kind file still starts as `PATH,__date__`. Packaged defaults, in section 2, are loaded from `src/supershelf/default.toml`.

## 1 Types and values

A declared type and a resolved value are different objects. Pydantic is the schema mechanism. `VarSpec.model_dump(mode="json")` keeps `default` and `validation`. `supershelf schema` builds one model per declared object and prints `model_json_schema()`. Resolving a variable does not write the database.

### 1.1 VarSpec

One catalog entry per name, for the whole profile.

- `desc`: plain text, default empty. Not a template.
- `type`: `text` (default for a user var), `int`, `float`, `bool`, `date`, `time`, `datetime`. Lower case. `INT` and `timedate` are config errors. The keyword `datetime` is a date and a time together.
- `date` is `YYYY-MM-DD`, the spelling `__date__` already uses. `time` is `HH:MM` or `HH:MM:SS`. `datetime` is `YYYY-MM-DDTHH:MM` or `YYYY-MM-DDTHH:MM:SS`. No timezone and no fractional seconds. Seconds stay in the display only when they were written. A set `datetime` always includes a clock: midnight is `T00:00` or `T00:00:00`. A calendar day with no clock is type `date`.
- `unit`: string, or absent. Display and storage metadata. No conversion.
- `internal`: managed by supershelf. Omitted means true when the name starts with `__`. An explicit value wins.
- `mandatory`: default false. After every layer, `None` fails the file. An empty text string is a value, so it passes. `time` and `datetime` use the same default.
- `default`: omitted, a typed literal, one string, or a candidate list. This is the lowest assignment.
- `validation`: optional mapping. Unknown keys, or keys that do not apply to the type, are a config error. A bad regex is a config error. Every listed constraint must pass. VarSpec rejects unknown keys, so `mendatory` is a config error.
  - Every type: `allowed`, a non-empty list of possible values. Duplicates are a config error. Items are checked at load against the var type.
  - `text`, `date`, `time`, `datetime`: `pattern` (full match), `min_length`, `max_length`, applied to the display string.
  - `int` and `float`: `ge`, `gt`, `le`, `lt`. `ge` and `le` are inclusive. An int bound is an int. A float bound is an int or a float.
  - `date`, `time`, `datetime`: `ge`, `gt`, `le`, `lt`, compared on the calendar or clock value. A bound is a string of that same type, cast at load. `15:04` and `15:04:00` are the same clock. A `date` bound on a `datetime` var is a config error.
  - `bool`: `allowed` only.

### 1.2 VarState

One resolved binding per name per file. The spec is not copied onto it.

- `value`: the coerced Python value, or `None` when unset. `None` means not set or not available. The shape is `T | None`.
- `value_sources`: text labels, in the order layers successfully wrote the name. The last label is the winner.

Later dump:

```yaml
vendor:
  value: Bank2000
  value_sources: [default, rule:invoice]
amount:
  value: null
  value_sources: []
```

`scan vars` prints `name: value` for set vars, using the display string, one name per line, sorted alphabetically. Internal names are omitted unless `--all` is set. The `sources` column lists the labels for that name, joined by `, `, on the matching line. A `None` value stays off the row. JSON and YAML omit that column and keep `value_sources` on each name. JSON uses the Python value (`7`, `12.5`, `true`, `null`), so a float dump can differ from a display such as `12.50`. `date`, `time`, and `datetime` dump as their display strings.

### 1.3 Catalog

Built-in entries are prefilled. The user catalog is the top-level profile key `vars_schema`, a mapping of name to VarSpec. Names match `[A-Za-z_][A-Za-z0-9_]*`.

Built-ins, all `internal: true`, `type: text`, `mandatory: true`, filled from the file and the match:

- `__kind__`, `__rule_name__`, `__ctime__`, `__mtime__`, `__file_hash__`, `__file_name__`, `__file_stem__`, `__file_ext__`, `__file_path__`, `__file_dir__`. Empty `__file_ext__` or `__file_dir__` is `""`, which is set, so `mandatory` passes.

`__date__` is in the catalog with `internal: false`, `type: date`, `mandatory: false`. The prefix rule does not mark it internal. `__ctime__` and `__mtime__` stay `text`: their stored form has fractional seconds and a UTC offset, which `datetime` rejects.

A name with no entry is an implicit user spec: `type: text`, `mandatory: false`, `internal` from the prefix rule.

The user may set `desc` and `unit` on a locked built-in. `type`, `internal`, `mandatory`, `default`, and `validation` on a locked built-in are a config error. On `__date__` the user may also set `mandatory`, `default`, and `validation`. `type` and `internal` stay fixed.

A new name starting with `__` is a config error. `internal: true` on a name supershelf does not manage is a config error. `internal: false` on a locked built-in is a config error.

Profile-scope names (`__profile__`, `__root_dir__`, and the rest) stay template scope. They are not catalog entries and are not printed.

Assignment rights do not change. Locked internals stay locked. Nothing may set `__kind__`. It stays the kind from the match rule. Layers may still set `__date__` and ordinary names. The schema does not grant new writes. A profile `overrides` key is a config error, including an empty list. Per-file values belong in the kind file. `kind_overrides_mode`, `kind_overrides_date_format`, `kind_overrides_sep`, and `kind_overrides_config` stay. Those keys are the kind file, not the removed list.

Implicit text. A name with no schema entry stores the rendered string. `vendor: Bank2000` with no schema entry is text, source `default` when `default_vars` set it.

### 1.4 Defaults

`default` on the spec and `default_vars` are one slot. `default_vars` stays valid config: each key writes that spec's `default`, and creates an implicit text spec when the name is absent. The shape there stays a string or a list of strings.

`vars_schema.<name>.default` may be a typed literal (`12`, `1.5`, `true`, `"2026-04-25"`), one string, or a candidate list. A list item is a typed literal of the var's type, or a string. A list is never the stored value.

The same name set in both places is a config error. One of them has to be removed. A schema entry with no `default` key is free to take its default from `default_vars`.

A non-template literal is coerced at load. A string that contains `{{`, `{%`, or `{#` is checked when that file renders. Load uses the config error. Render uses the resolve error.

Two defaults. `vars_schema.vendor.default: Bank2000` together with `default_vars.vendor` is a config error.

### 1.5 Three lists

These share YAML list syntax and mean different things.

- Candidate list. An assignment value, or a spec `default`, whose YAML type is a list. Each item is tried in order. The first success is the value. The stored value is one scalar. This is the list `default_vars` and rule `vars` accept. Kind-file cells stay one string each: a YAML list in a kind file is a config error. An empty candidate list is a config error. A nested list is a config error.
- Possible values. `validation.allowed`. Membership of the cast value. This does not choose among candidates. `account` can be a candidate list and also `allowed: [1000, 2000]`.
- A list-typed value. `type: list` is a config error. A stored list would need an item type, a kind-file encoding, and a print rule, and it would collide with candidate-list syntax. The type stays reserved.

### 1.6 Jinja stays text

`VarEnvironment.render` returns a string. Built-in commands and user modules take strings and return strings. After a successful cast, the Jinja scope holds the display string. Later templates read that string. `regex_replace(account, ...)` and `regex_time_var(...)` keep working. `{{ amount ~ owner }}` keeps working.

`{{ amount + 1 }}` is not integer math. `{% if paid %}` reads the string `true` or `false`. A non-empty string is truthy in Jinja, so `{% if paid %}` is true for both. Compare with `{% if paid == "true" %}`.

The Python value lives on VarState. Jinja attribute and method access (`{{ issued.year }}`) needs that object in the scope. That is a later phase. The schema stays as it is. Profile scope is unchanged. `__config_data__` stays a mapping. File vars still overlay it on the same name.

`regex_time_var` still returns `YYYY-MM-DD`. That string satisfies type `date` and misses type `time` and type `datetime`.

### 1.7 Cast, then validate

One pipeline for every candidate and every fact. Load time uses it for non-template literals. Render time uses it after Jinja returns text. Each name is cast when it is written, before the next layer reads it. There is no cast pass after the last layer.

1. Produce text. A literal string is that string. A typed literal (`12`, `1.5`, `true`) is accepted only in `vars_schema.default`, and only when the YAML or TOML type already matches the var. A template renders to a string. Undefined names and `VarCandidateError` are misses. Any other template error stops the command, as today.
2. Classify empty. `text` keeps `""` as a value. For `int`, `float`, `bool`, `date`, `time`, and `datetime`, `""` or whitespace-only is a miss. That miss is not `None`. `None` means no layer wrote the name. An omitted `time` or `datetime` stays `None` and passes `mandatory: false`.
3. Strip. `text` is not stripped. The other types strip once, then cast the stripped string.
4. Cast. Failure is a miss. The whole string must match the grammar below. `12.0` misses for int. The words `false`, `no`, and `0` cast to false.
   - `text`: the rendered string. Whitespace-only text is a successful value.
   - `int`: optional `+` or `-`, then digits. `12.0`, `0x10`, `1_000`, and `1e2` miss. Value is a Python int. Display drops the plus and leading zeros: `007` and `+7` display as `7`. There is no overflow cap. Set `le` when a consumer needs one.
   - `float`: optional sign, then digits with an optional decimal point (`12`, `12.50`, `.5`, `12.`). No exponent, no comma, no `NaN` or `Infinity`. Value is a Python float. Display is the stripped spelling, so `12.50` stays `12.50`. `-0` and `-0.0` are valid. `allowed: [0]` matches them, because Python compares them equal. Float is IEEE binary. Keep money in `text` or in integer cents until a later decimal type exists.
   - `bool`: case-insensitive `true`/`yes`/`1` or `false`/`no`/`0`. Display is `true` or `false`. Value is a Python bool.
   - `date`: the whole string is `YYYY-MM-DD` and round-trips, same check as today's `__date__`. `2026-04-25T15:04` misses. Display and JSON are that string.
   - `time`: the whole string is `HH:MM` or `HH:MM:SS`, zero-padded, and the hour, minute, and second round-trip. `15:4`, `15:04:05.1`, and `15:04Z` miss. Display and JSON keep the accepted spelling. The Python value used for `allowed` and ranges treats `15:04` and `15:04:00` as the same clock.
   - `datetime`: the whole string is `YYYY-MM-DDTHH:MM` or `YYYY-MM-DDTHH:MM:SS`, with `T` between the parts. The date part round-trips as a date. The time part follows the `time` rules. `2026-04-25`, `2026-04-25 15:04`, and anything with `Z` or an offset misses. Display and JSON keep the accepted spelling.
5. Validate, in this order: `allowed`, then `pattern` and lengths, then range. Compare `allowed` and ranges to the Python value (`007` matches `allowed: [7]` when the type is int; the text `007` matches `allowed: ["007"]` only as text). `pattern` is `re.fullmatch` against the display string. Text is not Unicode-normalized. Lengths use that same display string.
6. Commit. Append the source label. Store the Python value and the display string. The Jinja scope receives the display string.

A non-template literal that fails step 4 or 5 is a config error at load, including when a later candidate might have worked. A template is checked only at render, and a miss there tries the next candidate.

When every candidate in a layer misses, that layer does not write the name. An earlier value and its source list stay. Later layers still run. The name stays `None` when no layer writes it. `mandatory` after the last layer stops the file when the value is still `None`. This is the same rule for `__date__` and for every other name.

Facts are one value, with no candidate list. A file fact or regex group that fails the pipeline stops the command. A filename group `amount` of `12.50`, declared as `float`, becomes the float `12.5` when the match stores it. `EUR12.50` and `12,50` stop the file. A later layer does not repair that fact. To keep fallbacks, capture the text under another name and assign the typed name from a candidate list.

The filename does not set `__date__`. A stem that is a date stays `__file_stem__`. A profile that wants that date writes a candidate, such as `{{ regex_time_var(__file_stem__, __default_date_format__) }}`. A blank kind-file cell stays unset and is not a miss. A kind-file cell that fails cast stops the file. It has no next candidate.

`mandatory` runs after the last layer, and only on `None`.

`null` does not mean unset. Omit the key to leave the var unset. Quote scalars in `default_vars`, rule `vars`, and kind files. An unquoted YAML date, number, bool, or null is a config error there. Typed literals belong on `vars_schema.<name>.default`. Quote date, time, and datetime defaults too, including on the schema, so TOML and YAML stay on the same string grammar. YAML 1.1 may already have turned `yes`, `no`, `on`, and `off` into bools before supershelf sees them. Quote those words when the type is text.

While a key is rendering, `{{ that_key }}` reads the previous layer's display string. A layer that misses all of its candidates does not write the name, so a later layer can still set it.

Leading zeros are data only for `text`. An int schema on a regex group `0012` stores `12`. Pad in the template if the width matters.

Candidate list. `amount` is `int`, and the candidates are `"nope"` then `"12"`. `"nope"` is a literal, so load fails before the walk. The same key as `"{{ missing }}"` then `"12"` misses the template and keeps `12`.

`allowed`. `amount` is `int` with `allowed: [10, 20]`. The rendered `15` casts and then misses. The next candidate can still run.

Bool. `YES` and `1` display as `true`. `no` displays as `false`.

Load error ahead of a template. `default: ["12.0", "{{ other }}"]` on an int fails at load because `12.0` cannot cast.

Mandatory. `amount` with `mandatory: true` and no successful write stops the file. An omitted `opens` of type `time` stays unset and the file continues.

`__date__`. A filename that is a date does not set it. Every candidate in a layer missing leaves the earlier value, or leaves it unset when nothing wrote it. `mandatory: true` stops the file when the value is still `None`. A new name `__custom__` is a config error. `type: list` is a config error.

Leading zeros. Regex group `0012` declared as `int` stores `12`. A group `007` displays as `7`.

Datetime. `2026-04-25T15:04` and `2026-04-25T15:04:05` are valid. `2026-04-25` misses. Time `15:04` matches `allowed: ["15:04:00"]`. An omitted time var stays unset.

### 1.8 value_sources

Append a label only when that layer writes the name. A later write appends. It keeps the earlier labels. A layer that misses does not clear the value or the source list.

Labels:

- `fact` for file metadata, aliases, and regex groups
- `default` for the spec default or `default_vars`
- `rule:<rule name>`
- `kind:<kind file path>`

Resolver order in `VarPlan.resolve`: facts, then `default_vars`, then match-rule `vars`, then the kind file. The kind file is the last assignment layer.

Sources. `default_vars` sets `vendor`, the rule replaces it, and the kind file replaces it. The labels are `default`, `rule:invoice`, and `kind:<path>`. The value is the kind-file cell.

### 1.9 kind_schema

`kind_schema` is an optional top-level mapping. A profile with no `kind_schema` resolves as before. A bad entry stops `scan vars` and `schema`.

```yaml
vars_schema:
  company_name:
    type: text
    desc: Payer
  employee_name:
    type: text

kind_schema:
  invoice:
    desc: A vendor bill
    vars_schema:
      company: company_name
      employee:
        schema: employee_name
        mandatory: true
      __date__:
```

The value names a declared `vars_schema` entry, or `__date__`. A string is that name (`company: company_name`). Null or a blank string uses the local name, so `__date__:` and `__date__: ""` both use `__date__`. TOML has no null, so the blank form there is `""`. On an object, omitted, null, or blank `schema` uses the local name. An explicit `schema` remaps (`employee` above). A locked internal, or a name that was never declared, is a config error. The local name (`company`) is the variable for files of that kind. It follows the variable-name pattern and cannot be a locked internal. `type` and `internal` cannot be set on the kind var. They come from the referenced spec.

Omitted `desc`, `unit`, `mandatory`, and `validation` are copied from the referenced spec. A present `validation` mapping replaces the referenced one. It is not merged key by key. `default` is not copied. A kind `default` applies only when that kind entry sets it, as the default layer for that local name on files of that kind. Profile `default` and `default_vars` apply to that catalog name on files whose kind is not listed. On a listed kind they apply only when that kind's `vars_schema` includes the name.

When a kind lists a name the profile also has, files of that kind use the overlaid spec. The kind may set `mandatory: false`. A matched kind with no `kind_schema` entry keeps the profile catalog. Names a kind does not list keep the profile spec, including profile `mandatory`.

`supershelf schema` prints one JSON document. Several profiles are one object keyed by profile name. With `kind_schema`, each kind is an object under `$defs`. Property names are the kind's local names. `additionalProperties` is false. Without `kind_schema`, the object is the declared `vars_schema` names, excluding locked internals. `__date__` is included only when the profile sets `vars_schema.__date__`. Neither key stops the command. The schema describes resolved values. Kind-file cells and rule `vars` are still strings before the cast. A CSV for a listed kind uses that kind's local names as columns. A kind that is not listed uses the declared `vars_schema` names. Missing names are appended on the right. Columns the schema does not name stay. With no schema columns, a new CSV still starts as `PATH,__date__`.

## 2 Packaged defaults

Status: loaded from `src/supershelf/default.toml` at startup. A missing key and a YAML null are both unset before any fallback.

### 2.1 File and the null rule

`src/supershelf/default.toml` ships inside the package and is loaded once at startup. It is the source of every concrete default. The user document is not deep-merged onto it. For each known key, a missing key and an explicit null both become `None` before any fallback. `None` means not set up. It is not a usable value, so resolution falls back. A value the user wrote stays, including `""` and `[]`.

TOML has no null. A key the schema allows to be unset is left out of `default.toml` and loads as `None`. A comment in the file names that key. The loader schema names it too. A concrete key must be present and have the right type. A present key with the wrong type stops startup.

`default.toml` has one `[config]` table. There is no `[input]` section.

```toml
[config]
profile = "default"
default_date_format = "%Y-%m-%d"
root_dir = "{{ __profile_dir__ }}"
database_file = "{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite"
cache_file = "{{ __root_dir__ }}/profile.{{ __profile__ }}.cache"
record_identity = "path"
kind_overrides_mode = "auto"
# kind_overrides_date_format is unset (None) and falls back to default_date_format
# var_modules is unset (None): no modules
kind_overrides_sep = ","
kind_overrides_config = [
  "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.csv",
  "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.toml",
  "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yaml",
  "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yml",
]
input_depth = 0
input_follow_symlinks = true
```

`input_depth` and `input_follow_symlinks` are the packaged fallbacks for an omitted `depth` or `follow_symlinks` on an `inputs` item. They are not keys in the user's profile.

These stay in code. The parser needs them to read both files, or they are not a user default:

- Key names, environment names, internal variable names, file suffixes, and the four kind-override mode words.
- `DATE_TEXT` (`%Y-%m-%d`) as the stored date grammar. Editing `default_date_format` in `default.toml` changes display and kind-file parsing. It does not change how dates are stored.

### 2.2 Fallbacks

Only `None` falls back.

- `kind_overrides_date_format` uses `default_date_format`. That is the user's string, or the packaged `%Y-%m-%d` when `default_date_format` is also `None`.
- `default_date_format`, `root_dir`, `database_file`, `cache_file`, `record_identity`, `kind_overrides_mode`, `kind_overrides_sep`, and `kind_overrides_config` use the packaged value.
- An input item's `depth` uses packaged `input_depth`. `follow_symlinks` uses packaged `input_follow_symlinks`.
- `profile` uses the filename, then the packaged `"default"`. Blank text is unset, the same as `None`. On `profile.NAME.*`, the filename still wins over `config.profile`.
- `var_modules`, `match_rules`, and `default_vars` have no next key. The layer is off. A present `overrides` key is a config error. There is no fallback for it.
- `inputs` has no next key. A scan stops. There is no empty input list to invent.

`""` for a date format, a path, or a separator is set, and it is invalid. The command stops. It does not fall back.

`kind_overrides_config = []` means no kind files. It does not fall back to the four packaged paths. `var_modules = []` means no modules. It is a real empty list. An input item's `include` or `exclude` set to `None` means no filter. An empty list is a real filter. A match rule's `kind` set to `None` uses that rule's `name`, and a `None` name uses `kind`. That rule already holds. There is no static kind string in `default.toml`.

Omitted kind date format. The user sets `default_date_format` to `%d/%m/%Y` and omits `kind_overrides_date_format`. Kind files parse with `%d/%m/%Y`.

Both date formats unset. Neither key is present. Kind files parse with the packaged `%Y-%m-%d`.

Null date format. `kind_overrides_date_format: null` follows `default_date_format`, the same as a missing key. `default_date_format: null` uses the packaged `%Y-%m-%d`.

Empty date format. `kind_overrides_date_format: ""` stops the command. It does not follow `default_date_format`.

Kind paths. A missing or null `kind_overrides_config` uses the four packaged templates. `[]` means no kind files.

Inputs. A missing or null `inputs` stops a scan with the "no inputs" error. `inputs: []` stops with "inputs is empty".

Input depth. An item that omits `depth` uses packaged `input_depth`, which is `0`. `depth: 0` is the user setting that same number.

Modules. A missing or null `var_modules` loads no modules. `[]` loads no modules and stays an empty list.

### 2.3 Readers

Missing and null are both `None` before the type check.

- `profile.py`: `default_date_format`, `root_dir`, `database_file`, `cache_file`.
- `record.py`: `RecordIdentity.resolve`. The flag wins, then `SUPERSHELF_RECORD_IDENTITY`, then `config.record_identity`, then packaged `path`. A bare `path` expands to `path` then `hash`. A bare `hash` expands to `hash` then `path`. A list does not expand its items. An empty string, an empty list, a repeated step, or an unknown step is invalid and does not fall back. Rule lists are behavior 4.2.
- `vars.py`: `KindDateFormat.from_section`, `KindCsvSep.from_section`, `KindOverrideMode.resolve`. `KindOverrideMode` is a `WordChoice`. The date-format reader uses the user's `default_date_format` only after `kind_overrides_date_format` is `None`.
- `scan.py`: a null `inputs` uses the same "no inputs" error as a missing key. An empty list stays "inputs is empty".

These also use a missing key and null as `None`: `kind_overrides_config`, `var_modules`, `match_rules`, `default_vars`, and the profile name. A present `overrides` key is a config error, not `None`.

## 3 Profile database

Behavior 4. One sqlite file per profile, stdlib `sqlite3`, schema version `1`. Foreign keys are on. Rows are never deleted. `ShelfDatabase.append_output` can append an output event. No command calls it.

### 3.1 Tables

`meta` stores `schema_version` and, after a successful `record run`, `identity`. The value is the profile default list, comma-separated, no spaces: `path,hash` or `hash,path`. A legacy `path` compares equal to `path,hash`. A legacy `hash` compares equal to `hash,path`. Behavior 4.2.

`contents` is one row per sha256. The primary key is `hash`. Many documents reference one row.

`documents` is the current projection:

- `id` integer primary key, never reused
- `presence`: `present`, `missing`, or `unmatched`
- `generation` integer, starting at 1
- `hash` references `contents`
- `input_index`, `input_path` (absolute input directory), `path` (relative, slash separators)
- `mtime` and `ctime`, the stored UTC timestamps, or null
- `match_kind`, `rule`
- `file_dir`, `file_name`, `file_stem`, `file_ext` (`archive.tar.gz` stores `gz`; no suffix stores `""`)
- `vars_json`
- `updated_at`, UTC ISO-8601

A partial unique index on `(input_path, path)` applies where `presence` is not `missing`. Two missing documents may keep the same last path.

`events` is append-only:

- `id`, `document_id`, `seq` unique per document, starting at 1
- `event`: `new`, `move`, `generation`, `vars`, `missing`, `present`, `unmatched`, or `output`
- `identity`: the first step of the list that decided this event. `path` or `hash`. A `path` list stores `path` even when the hash step performed a move.
- `recorded_at`
- the same file facts and `vars_json` as `documents`
- nullable output columns: `output_name`, `operation`, `destination`, `source_hash`, `previous_json`

Indexes: `events.hash`, `events.destination`.

`refresh` updates `mtime`, `ctime`, and `input_index` on the document and does not insert an event.

### 3.2 Variable snapshot

`vars_json` is one JSON object. Keys are sorted. Identity facts that already have columns are left out: `__kind__`, `__rule_name__`, `__ctime__`, `__mtime__`, `__file_hash__`, `__file_name__`, `__file_stem__`, `__file_ext__`, `__file_path__`, `__file_dir__`. `__date__` is included when it is set. Profile-scope names are not included. An unset name is left out.

Each binding is `type`, `value`, `display`, and `value_sources`. `value` is the JSON form of the Python value. A float can be `12.5` while `display` is `12.50`. A difference in the name set, the type, the value, the display, or the sources is a variable change.

### 3.3 Decision order

The observed set is the walked inputs, then PATH. Documents whose input directory was not walked are left as they are. Documents outside PATH are left as they are. The database file is ignored.

The list for each document is behavior 4.2. A file reserved in an earlier step cannot be taken later. Inside a step, documents run in id order.

1. The location still has a matched file and the hash matches. The document stays, for every list. Status is `vars`, `present`, `refresh`, or `unchanged`, in that order of precedence. `present` is the return from `missing` or `unmatched` when the variables did not change. Reserve the file.
2. The location is still in the kept walk and no rule matches. Status `unmatched`, unless it is already unmatched. The list stops. The hash is not followed. The event keeps the latest identity word.
3. Walk the remaining list. Stop at the first step that matches.
   `path` matches when the location still has a matched file. A different hash is a generation. Reserve that path. The step declines when the location is not in the kept walk.
   `hash`, and this document's list reaches it before `path`: eligibility and ownership are behavior 4.2. One eligible unreserved successor is a move. Several hash-first successors move to the lowest `(input_path, relative path)` and the others are `duplicate`. The old path is not reserved when the document leaves it. A reserved file does not make this step match. The step declines when none remain.
   `hash` after `path` declined: this document's own continuation. Any unclaimed in-scope matched file with that hash counts. The move happens only when exactly one gone document wants that hash. Several successors do not match.
   When the list is exhausted, the document is `missing` unless it is already missing.
4. Each unclaimed in-scope matched file becomes a new document, generation 1, event `new`, identity the first step of its rule list. A hash-first file whose hash is already owned is `duplicate` instead. It is not written. On a first run the lowest path of a shared hash is the new document.

A move keeps the generation number. A generation increments it. A move or a generation stores the new snapshot on that event and does not also append `vars`.

`duplicate` is a status word. It is not an event and not a presence. The plan prints it. The write skips it.

Location changes are written by first marking the moving documents `missing`, so a swap of two paths can commit under the partial unique index, then writing the final presence and path.

`duplicates` on the status row counts other in-scope present documents with that hash, plus extra live files reported as `duplicate` for that hash. Documents left out of scope still count. A never-inserted copy is not in `record duplicates`.

### 3.4 Output event

No command inserts `output`. `ShelfDatabase.append_output` inserts one event and does not change the document projection. `operation` is `copy`, `symlink`, or `hardlink`. `previous_json` is the revert payload:

```json
{"existed": false, "ours": false}
```

When this profile wrote the previous destination, `ours` is true and the object also has `operation` and `source_hash` from that earlier event. `existed` true and `ours` false means a file was already there and this profile did not write it. The outputs story fills these keys. This story only reserves them.

### 3.5 Open and errors

A missing file opened for reading is an empty previous state. The file is not created. A real read of an existing file uses SQLite read-only mode.

`record run` opens for write only when a row would change, or when the stored identity rule differs and the file already exists. The identity key is updated in that transaction. A failure rolls the transaction back. The schema created for a new file stays.

`RecordConfigError` is a bad `record_identity` word or list, on the flag, the environment variable, the profile, or a match rule. Exit 2. `DatabaseError` is a bad file, a wrong schema version, a parent that is not a directory, or a lock. Exit 1. The tip names a fix the user can make.

Two copies, path. Both documents reference the same `contents.hash`. `record duplicates` groups that hash.

Two copies, hash. One document references `contents.hash`. The extra path is a `duplicate` status row and has no document row.

Collision under `path`. The generation event keeps the document id. The new document's `new` event stores the old hash. The duplicate query shows current `no` on the generation that was replaced and current `yes` on the new document.

Collision under `hash`. The move keeps the document id and the generation. The new bytes are a new document. A second hash-first file with the old hash is not inserted.

Output slot. After `append_output`, `events` has one `output` row and the document's presence, hash, and generation are unchanged.
