# 1 Types and values

Architecture. Index: [README](../README.md).

Status: the variable types below are implemented. Each binding stores a Python value and a display string. Jinja still reads the display string. `scan import` writes the profile database in section 3. The sqlite schema does not follow these names. Each user variable is one key in `vars_json`. Architecture 3.2. `inspect schema` prints JSON Schema for declared `vars_schema` and `kind_schema` entries. Kind-file columns use the kind's local names. With no schema columns, a new CSV kind file still starts as `PATH,__date__`. Packaged defaults, in section 2, are loaded from `src/supershelf/default.toml`.

A declared type and a resolved value are different objects. Pydantic is the schema mechanism. `VarSpec.model_dump(mode="json")` keeps `default` and `validation`. `inspect schema` builds one model per declared object and prints `model_json_schema()`. Resolving a variable does not write the database.

## 1.1 VarSpec

One catalog entry per name, for the whole profile.

- `desc`: plain text, default empty. Not a template.
- `type`: `text` (default for a user var), `int`, `float`, `bool`, `date`, `time`, `datetime`. Lower case. `INT` and `timedate` are config errors. The keyword `datetime` is a date and a time together.
- `date` is `YYYY-MM-DD`, the spelling `__date__` already uses. `time` is `HH:MM` or `HH:MM:SS`. `datetime` is `YYYY-MM-DDTHH:MM` or `YYYY-MM-DDTHH:MM:SS`. No timezone and no fractional seconds. Seconds stay in the display only when they were written. A set `datetime` always includes a clock: midnight is `T00:00` or `T00:00:00`. A calendar day with no clock is type `date`.
- `unit`: string, or absent. Display and storage metadata. No conversion.
- `internal`: managed by supershelf. `__date__` is false. A new name that starts with `__` is a config error, so omitting this key does not create an internal. An explicit `true` on a name supershelf does not manage is a config error.
- `mandatory`: default false. After every layer, `None` fails the file. An empty text string is a value, so it passes. `time` and `datetime` use the same default.
- `default`: omitted, a typed literal, one string, or a candidate list. This is the lowest assignment.
- `validation`: optional mapping. Unknown keys, or keys that do not apply to the type, are a config error. A bad regex is a config error. Every listed constraint must pass. VarSpec rejects unknown keys, so `mendatory` is a config error.
  - Every type: `allowed`, a non-empty list of possible values. Duplicates are a config error. Items are checked at load against the var type.
  - `text`, `date`, `time`, `datetime`: `pattern` (full match), `min_length`, `max_length`, applied to the display string.
  - `int` and `float`: `ge`, `gt`, `le`, `lt`. `ge` and `le` are inclusive. An int bound is an int. A float bound is an int or a float.
  - `date`, `time`, `datetime`: `ge`, `gt`, `le`, `lt`, compared on the calendar or clock value. A bound is a string of that same type, cast at load. `15:04` and `15:04:00` are the same clock. A `date` bound on a `datetime` var is a config error.
  - `bool`: `allowed` only.

## 1.2 VarState

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

`scan vars` prints `name: value` for set vars, using the display string, one name per line, sorted alphabetically. `__file__` and `__match__` fields are omitted unless `--all` is set. With `--all`, each field is one of those lines. The name is the dotted form, such as `__file__.name`, and the source label is `fact`. `__profile__`, `__config__`, and `__input__` are never printed. The `sources` column lists the labels for that name, joined by `, `, on the matching line. A `None` value stays off the row. JSON and YAML omit that column and keep `value_sources` on each name. JSON uses the Python value (`7`, `12.5`, `true`, `null`), so a float dump can differ from a display such as `12.50`. `date`, `time`, and `datetime` dump as their display strings.

## 1.3 Catalog

Built-in entries are prefilled. The user catalog is the top-level profile key `vars_schema`, a mapping of name to VarSpec. Names match `[A-Za-z_][A-Za-z0-9_]*`.

`__date__` is the only built-in catalog entry: `internal: false`, `type: date`, `mandatory: false`. The prefix rule does not mark it internal. The user may set `desc`, `unit`, `mandatory`, `default`, and `validation` on it. `type` and `internal` stay fixed.

`__file__`, `__match__`, `__profile__`, `__config__`, and `__input__` are template objects. They are not catalog entries. `desc` and `unit` on the old flat names, such as `__file_name__` or `__kind__`, are a config error, because a new name that starts with `__` is a config error. Empty `__file__.ext` and `__file__.dir` are `""`. `__file__.ctime` and `__file__.mtime` stay text: their stored form has fractional seconds and a UTC offset, which `datetime` rejects. They do not satisfy type `date`.

A name with no entry is an implicit user spec: `type: text`, `mandatory: false`, `internal: false`. The prefix does not add a catalog entry.

A new name starting with `__` is a config error. `internal: true` on a name supershelf does not manage is a config error.

Layers may set `__date__` and names that do not start with `__`. A layer cannot set a namespace root. The schema does not grant those writes. A profile `overrides` key is a config error, including an empty list. Per-file values belong in the kind file. `kind_overrides_mode`, `kind_overrides_date_format`, `kind_overrides_sep`, and `kind_overrides_config` stay. Those keys are the kind file, not the removed list.

Implicit text. A name with no schema entry stores the rendered string. `vendor: Bank2000` with no schema entry is text, source `default` when `default_vars` set it.

## 1.4 Defaults

`default` on the spec and `default_vars` are one slot. `default_vars` stays valid config: each key writes that spec's `default`, and creates an implicit text spec when the name is absent. The shape there stays a string or a list of strings.

`vars_schema.<name>.default` may be a typed literal (`12`, `1.5`, `true`, `"2026-04-25"`), one string, or a candidate list. A list item is a typed literal of the var's type, or a string. A list is never the stored value.

The same name set in both places is a config error. One of them has to be removed. A schema entry with no `default` key is free to take its default from `default_vars`.

A non-template literal is coerced at load. A string that contains `{{`, `{%`, or `{#` is checked when that file renders. Load uses the config error. Render uses the resolve error.

Two defaults. `vars_schema.vendor.default: Bank2000` together with `default_vars.vendor` is a config error.

## 1.5 Three lists

These share YAML list syntax and mean different things.

- Candidate list. An assignment value, or a spec `default`, whose YAML type is a list. Each item is tried in order. The first success is the value. The stored value is one scalar. This is the list `default_vars` and rule `vars` accept. Kind-file cells stay one string each: a YAML list in a kind file is a config error. An empty candidate list is a config error. A nested list is a config error.
- Possible values. `validation.allowed`. Membership of the cast value. This does not choose among candidates. `account` can be a candidate list and also `allowed: [1000, 2000]`.
- A list-typed value. `type: list` is a config error. A stored list would need an item type, a kind-file encoding, and a print rule, and it would collide with candidate-list syntax. The type stays reserved.

## 1.6 Jinja stays text

`VarEnvironment.render` returns a string. Built-in commands and user modules take strings and return strings. After a successful cast, the Jinja scope holds the display string. Later templates read that string. `regex_replace(account, ...)` and `regex_time_var(...)` keep working. `{{ amount ~ owner }}` keeps working.

`{{ amount + 1 }}` is not integer math. `{% if paid %}` reads the string `true` or `false`. A non-empty string is truthy in Jinja, so `{% if paid %}` is true for both. Compare with `{% if paid == "true" %}`.

The Python value lives on VarState. Jinja attribute and method access (`{{ issued.year }}`) needs that object in the scope. That is a later phase. Assigned names stay display strings, except `__date__`. In the Jinja scope only, `__date__` is an object. `str()` uses `default_date_format`. `strftime(pattern)` uses a `strftime` pattern. The fields are `Y`, `m`, and `d` (`%Y`, `%m`, `%d`). The printed value and `vars_json` stay `YYYY-MM-DD`. `__profile__`, `__config__`, `__file__`, `__match__`, and `__input__` are mappings. With no field, each prints one string: profile name, `root_dir`, filename, kind, and input path. `{{ __file__.name }}` still reads a field. `__profile__.document` is the parsed profile file, still a mapping, and still needs a field. A field on `__file__` and `__match__` is a string.

`regex_time_var` still returns `YYYY-MM-DD`. That string satisfies type `date` and misses type `time` and type `datetime`.

## 1.7 Cast, then validate

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

Facts are one value, with no candidate list. A regex group that fails the pipeline stops the command. A filename group `amount` of `12.50`, declared as `float`, becomes the float `12.5` when the match stores it. `EUR12.50` and `12,50` stop the file. A later layer does not repair that fact. To keep fallbacks, capture the text under another name and assign the typed name from a candidate list. `__file__` and `__match__` are not catalog entries. Their fields are already strings.

The filename does not set `__date__`. A stem that is a date stays `__file__.stem`. A profile that wants that date writes a candidate, such as `{{ regex_time_var(__file__.stem, __config__.date_format) }}`. A blank kind-file cell stays unset and is not a miss. A kind-file cell that fails cast stops the file. It has no next candidate.

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

## 1.8 value_sources

Append a label only when that layer writes the name. A later write appends. It keeps the earlier labels. A layer that misses does not clear the value or the source list.

Labels:

- `fact` for file metadata, aliases, and regex groups
- `default` for the spec default or `default_vars`
- `rule:<rule name>`
- `kind:<kind file path>`

Resolver order in `VarPlan.resolve`: facts, then `default_vars`, then match-rule `vars`, then the kind file. The kind file is the last assignment layer.

Sources. `default_vars` sets `vendor`, the rule replaces it, and the kind file replaces it. The labels are `default`, `rule:invoice`, and `kind:<path>`. The value is the kind-file cell.

## 1.9 kind_schema

`kind_schema` is an optional top-level mapping. A profile with no `kind_schema` resolves as before. A bad entry stops `scan vars`, `scan feeds`, `scan import`, and `inspect schema`.

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
    feed_file: "{{ __config__.root_dir }}/invoices.csv"
    feeds:
      - company
      - __date__
    vars_schema:
      company: company_name
      employee:
        schema: employee_name
        mandatory: true
      __date__:
```

The nested key is `vars_schema`. `fields` is not a key. A field is a match-rule slot. Behavior 3.

`feed_file` is optional. A string is one path template. A list is templates in order. Omitted uses `kind_overrides_config`. Rendering is the kind-file path language in behavior 2.3.1. `kind_overrides_config: []` and no `feed_file` means that kind has no kind file. Feeds are skipped. Import still runs.

`feeds` is an optional list of var names. Omitted means every schema var of that kind. `__date__` is included only when that schema lists it. A name the kind does not resolve is a config error. A var left off the list is still resolved and is still stored in `vars_json` on import. It has no feed column. The uppercase column name is behavior 3.2.

The value names a declared `vars_schema` entry, or `__date__`. A string is that name (`company: company_name`). Null or a blank string uses the local name, so `__date__:` and `__date__: ""` both use `__date__`. TOML has no null, so the blank form there is `""`. On an object, omitted, null, or blank `schema` uses the local name. An explicit `schema` remaps (`employee` above). A namespace root, a name that starts with `__` and is not `__date__`, or a name that was never declared, is a config error. The local name (`company`) is the variable for files of that kind. It follows the variable-name pattern and cannot start with `__` unless it is `__date__`. `type` and `internal` cannot be set on the kind var. They come from the referenced spec.

Omitted `desc`, `unit`, `mandatory`, and `validation` are copied from the referenced spec. A present `validation` mapping replaces the referenced one. It is not merged key by key. `default` is not copied. A kind `default` applies only when that kind entry sets it, as the default layer for that local name on files of that kind. Profile `default` and `default_vars` apply to that catalog name on files whose kind is not listed. On a listed kind they apply only when that kind's `vars_schema` includes the name.

When a kind lists a name the profile also has, files of that kind use the overlaid spec. The kind may set `mandatory: false`. A matched kind with no `kind_schema` entry keeps the profile catalog. Names a kind does not list keep the profile spec, including profile `mandatory`.

`inspect schema` prints one JSON document. Several profiles are one object keyed by profile name. With `kind_schema`, each kind is an object under `$defs`. Property names are the kind's local names. `additionalProperties` is false. Without `kind_schema`, the object is the declared `vars_schema` names. A name that starts with `__` is left out, except `__date__` when the profile sets `vars_schema.__date__`. Neither key stops the command. The schema describes resolved values. Kind-file cells and rule `vars` are still strings before the cast. A CSV for a listed kind uses that kind's local names as columns. A kind that is not listed uses the declared `vars_schema` names. Missing names are appended on the right. Columns the schema does not name stay. With no schema columns, a new CSV still starts as `PATH,__date__`.
