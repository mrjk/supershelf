# Architecture

Behind the scenes: models, pipelines, cast rules, and edge cases. Use cases live in [PERFECT_CONFIG.yml](PERFECT_CONFIG.yml). The short command pipeline on the doc site is `docs/content/reference/architecture.md`.

Status: the variable types below are implemented. Each binding stores a Python value and a display string. Jinja still reads the display string. This version adds no database and no schema command. `kind_schema` is not parsed. Packaged defaults, at the end of this file, are loaded from `src/supershelf/default.toml`.

## Variable types

A declared type and a resolved value are different objects. Pydantic is the schema mechanism, so a later step can call `model_json_schema()` and `model_dump(mode="json")` for sqlite or mysql. This version adds no database and no schema command.

### VarSpec

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

### VarState

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

`scan vars` keeps printing `name: value` for set vars, using the display string. Under each of those lines, print `sources: ` plus the labels joined by `, `. A `None` value stays off the row. JSON uses the Python value (`7`, `12.5`, `true`, `null`), so a float dump can differ from a display such as `12.50`. `date`, `time`, and `datetime` dump as their display strings.

## Catalog

Built-in entries are prefilled. The user catalog is the top-level profile key `vars_schema`, a mapping of name to VarSpec. Names match `[A-Za-z_][A-Za-z0-9_]*`.

Built-ins, all `internal: true`, `type: text`, `mandatory: true`, filled from the file and the match:

- `__kind__`, `__rule_name__`, `__ctime__`, `__mtime__`, `__file_hash__`, `__file_name__`, `__file_stem__`, `__file_ext__`, `__file_path__`, `__file_dir__`
- `file_ctime`, `file_mtime`. Internal is explicit, because these names have no `__` prefix. Empty `__file_ext__` or `__file_dir__` is `""`, which is set, so `mandatory` passes.

`__date__` is in the catalog with `internal: false`, `type: date`, `mandatory: false`. The prefix rule does not mark it internal. `__ctime__` and `__mtime__` stay `text`: their stored form has fractional seconds and a UTC offset, which `datetime` rejects. `file_ctime` and `file_mtime` stay that same text.

A name with no entry is an implicit user spec: `type: text`, `mandatory: false`, `internal` from the prefix rule.

The user may set `desc` and `unit` on a locked built-in. `type`, `internal`, `mandatory`, `default`, and `validation` on a locked built-in are a config error. On `__date__` the user may also set `mandatory`, `default`, and `validation`. `type` and `internal` stay fixed.

A new name starting with `__` is a config error. `internal: true` on a name supershelf does not manage is a config error. `internal: false` on a locked built-in is a config error.

Profile-scope names (`__profile__`, `__root_dir__`, and the rest) stay template scope. They are not catalog entries and are not printed.

Assignment rights do not change. Locked internals stay locked. Only overrides may set `__kind__`. Layers may still set `__date__` and ordinary names. The schema does not grant new writes.

## default_vars

`default` on the spec and `default_vars` are one slot. `default_vars` stays valid config: each key writes that spec's `default`, and creates an implicit text spec when the name is absent. The shape there stays a string or a list of strings.

`vars_schema.<name>.default` may be a typed literal (`12`, `1.5`, `true`, `"2026-04-25"`), one string, or a candidate list. A list item is a typed literal of the var's type, or a string. A list is never the stored value.

The same name set in both places is a config error. One of them has to be removed. A schema entry with no `default` key is free to take its default from `default_vars`.

A non-template literal is coerced at load. A string that contains `{{`, `{%`, or `{#` is checked when that file renders. Load uses the config error. Render uses the resolve error.

## Three lists

These share YAML list syntax and mean different things.

- Candidate list. An assignment value, or a spec `default`, whose YAML type is a list. Each item is tried in order. The first success is the value. The stored value is one scalar. This is the list `default_vars`, rule `vars`, and overrides already accept. Kind-file cells stay one string each: a YAML list in a kind file is a config error. An empty candidate list is a config error. A nested list is a config error.
- Possible values. `validation.allowed`. Membership of the cast value. This does not choose among candidates. `account` can be a candidate list and also `allowed: [1000, 2000]`.
- A list-typed value. `type: list` is a config error. A stored list would need an item type, a kind-file encoding, and a print rule, and it would collide with candidate-list syntax. The type stays reserved.

## Jinja stays text

`VarEnvironment.render` returns a string. Built-in commands and user modules take strings and return strings. After a successful cast, the Jinja scope holds the display string. Later templates read that string. `regex_replace(account, ...)` and `regex_time_var(...)` keep working. `{{ amount ~ owner }}` keeps working.

`{{ amount + 1 }}` is not integer math. `{% if paid %}` reads the string `true` or `false`. A non-empty string is truthy in Jinja, so `{% if paid %}` is true for both. Compare with `{% if paid == "true" %}`.

The Python value lives on VarState. Jinja attribute and method access (`{{ issued.year }}`) needs that object in the scope. That is a later phase. The schema stays as it is. Profile scope is unchanged. `__config_data__` stays a mapping. File vars still overlay it on the same name.

`regex_time_var` still returns `YYYY-MM-DD`. That string satisfies type `date` and misses type `time` and type `datetime`.

## Cast, then validate

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

When every candidate in a layer misses, the command stops with today's resolve error (profile, input, path, variable, last miss as the advice). Later layers do not run. `__date__` keeps its exception: total failure clears the value and the source list, and the command continues. If `__date__` is `mandatory` and still `None` after the last layer, the command stops.

Facts are one value, with no candidate list. A file fact or regex group that fails the pipeline stops the command. A filename group `amount` of `12.50`, declared as `float`, becomes the float `12.5` when the match stores it. `EUR12.50` and `12,50` stop the file. A later layer does not repair that fact. To keep fallbacks, capture the text under another name and assign the typed name from a candidate list.

A filename stem that is not a date does not set `__date__`. A blank kind-file cell stays unset and is not a miss. A kind-file cell that fails cast stops the file. It has no next candidate.

`mandatory` runs after the last layer, and only on `None`.

`null` does not mean unset. Omit the key to leave the var unset. Quote scalars in `default_vars`, rule `vars`, overrides, and kind files. An unquoted YAML date, number, bool, or null is a config error there. Typed literals belong on `vars_schema.<name>.default`. Quote date, time, and datetime defaults too, including on the schema, so TOML and YAML stay on the same string grammar. YAML 1.1 may already have turned `yes`, `no`, `on`, and `off` into bools before supershelf sees them. Quote those words when the type is text.

While a key is rendering, `{{ that_key }}` reads the previous layer's display string. A default layer that misses all of its candidates stops the file before rule, kind, and override layers. Omit the default if a later layer should supply the value.

Leading zeros are data only for `text`. An int schema on a regex group `0012` stores `12`. Pad in the template if the width matters.

## value_sources

Append a label only when that layer writes the name. A later write appends. It keeps the earlier labels. Total failure of `__date__` clears the value and the source list together.

Labels:

- `fact` for file metadata, aliases, and regex groups
- `filename` when `__date__` comes from the stem
- `default` for the spec default or `default_vars`
- `rule:<rule name>`
- `kind:<kind file path>`
- `override:<path pattern>`

Resolver order in `VarPlan.resolve`: facts, then `default_vars`, then match-rule `vars`, then the kind file, then overrides. The concept pages use that same order.

## kind_schema

`kind_schema` is reserved and is not parsed in this phase. Catalog names stay the references a kind will use. The shape is a mapping:

```yaml
vars_schema:
  company_name:
    type: text
    desc: Payer

kind_schema:
  invoice:
    desc: A vendor bill
    vars_schema:
      company:
        schema: company_name
        mandatory: true
      employee:
        schema: employee_name
```

A kind entry points at a catalog spec with `schema` and overlays any fields it sets. A later phase defines how that overlay meets profile `mandatory`.

## Cases

Implicit text. A name with no schema entry stores the rendered string. `vendor: Bank2000` with no schema entry is text, source `default` when `default_vars` set it.

Candidate list. `amount` is `int`, and the candidates are `"nope"` then `"12"`. `"nope"` is a literal, so load fails before the walk. The same key as `"{{ missing }}"` then `"12"` misses the template and keeps `12`.

`allowed`. `amount` is `int` with `allowed: [10, 20]`. The rendered `15` casts and then misses. The next candidate can still run.

Bool. `YES` and `1` display as `true`. `no` displays as `false`.

Load error ahead of a template. `default: ["12.0", "{{ other }}"]` on an int fails at load because `12.0` cannot cast.

Two defaults. `vars_schema.vendor.default: Bank2000` together with `default_vars.vendor` is a config error.

Mandatory. `amount` with `mandatory: true` and no successful write stops the file. An omitted `opens` of type `time` stays unset and the file continues.

`__date__`. Every candidate missing clears it and the command continues. `mandatory: true` on `__date__` stops the file when the value is still `None`. A new name `__custom__` is a config error. `type: list` is a config error.

Leading zeros. Regex group `0012` declared as `int` stores `12`. A group `007` displays as `7`.

Sources. `default_vars` sets `vendor`, the rule replaces it, the kind file replaces it, an override replaces it. The labels are `default`, `rule:invoice`, `kind:<path>`, `override:<pattern>`, and the value is the override.

Datetime. `2026-04-25T15:04` and `2026-04-25T15:04:05` are valid. `2026-04-25` misses. Time `15:04` matches `allowed: ["15:04:00"]`. An omitted time var stays unset.

## Packaged defaults

Status: loaded from `src/supershelf/default.toml` at startup. A missing key and a YAML null are both unset before any fallback.

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

### Fallbacks

Only `None` falls back.

- `kind_overrides_date_format` uses `default_date_format`. That is the user's string, or the packaged `%Y-%m-%d` when `default_date_format` is also `None`.
- `default_date_format`, `root_dir`, `database_file`, `cache_file`, `kind_overrides_mode`, `kind_overrides_sep`, and `kind_overrides_config` use the packaged value.
- An input item's `depth` uses packaged `input_depth`. `follow_symlinks` uses packaged `input_follow_symlinks`.
- `profile` uses the filename, then the packaged `"default"`. Blank text is unset, the same as `None`. On `profile.NAME.*`, the filename still wins over `config.profile`.
- `var_modules`, `match_rules`, `default_vars`, and `overrides` have no next key. The layer is off.
- `inputs` has no next key. A scan stops. There is no empty input list to invent.

`""` for a date format, a path, or a separator is set, and it is invalid. The command stops. It does not fall back.

`kind_overrides_config = []` means no kind files. It does not fall back to the four packaged paths. `var_modules = []` means no modules. It is a real empty list. An input item's `include` or `exclude` set to `None` means no filter. An empty list is a real filter. A match rule's `kind` set to `None` uses that rule's `name`, and a `None` name uses `kind`. That rule already holds. There is no static kind string in `default.toml`.

### Readers

Missing and null are both `None` before the type check.

- `profile.py`: `default_date_format`, `root_dir`, `database_file`, `cache_file`.
- `vars.py`: `KindDateFormat.from_section`, `KindCsvSep.from_section`, `KindOverrideMode.resolve`. The date-format reader uses the user's `default_date_format` only after `kind_overrides_date_format` is `None`.
- `scan.py`: a null `inputs` uses the same "no inputs" error as a missing key. An empty list stays "inputs is empty".

These also use a missing key and null as `None`: `kind_overrides_config`, `var_modules`, `match_rules`, `default_vars`, `overrides`, and the profile name.

### Cases

Omitted kind date format. The user sets `default_date_format` to `%d/%m/%Y` and omits `kind_overrides_date_format`. Kind files parse with `%d/%m/%Y`.

Both date formats unset. Neither key is present. Kind files parse with the packaged `%Y-%m-%d`.

Null date format. `kind_overrides_date_format: null` follows `default_date_format`, the same as a missing key. `default_date_format: null` uses the packaged `%Y-%m-%d`.

Empty date format. `kind_overrides_date_format: ""` stops the command. It does not follow `default_date_format`.

Kind paths. A missing or null `kind_overrides_config` uses the four packaged templates. `[]` means no kind files.

Inputs. A missing or null `inputs` stops a scan with the "no inputs" error. `inputs: []` stops with "inputs is empty".

Input depth. An item that omits `depth` uses packaged `input_depth`, which is `0`. `depth: 0` is the user setting that same number.

Modules. A missing or null `var_modules` loads no modules. `[]` loads no modules and stays an empty list.
