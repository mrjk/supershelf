# 2 Packaged defaults

Architecture. Index: [README](../README.md).

Status: loaded from `src/supershelf/default.toml` at startup. A missing key and a YAML null are both unset before any fallback.

## 2.1 File and the null rule

`src/supershelf/default.toml` ships inside the package and is loaded once at startup. It is the source of every concrete default. The user document is not deep-merged onto it. For each known key, a missing key and an explicit null both become `None` before any fallback. `None` means not set up. It is not a usable value, so resolution falls back. A value the user wrote stays, including `""` and `[]`.

TOML has no null. A key the schema allows to be unset is left out of `default.toml` and loads as `None`. A comment in the file names that key. The loader schema names it too. A concrete key must be present and have the right type. A present key with the wrong type stops startup.

`default.toml` has one `[config]` table. There is no `[input]` section.

```toml
[config]
profile = "default"
default_date_format = "%Y-%m-%d"
root_dir = "{{ __profile__.dir }}"
database_file = "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.sqlite"
cache_file = "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.cache"
record_identity = "path"
kind_overrides_mode = "auto"
# kind_overrides_date_format is unset (None) and falls back to default_date_format
# var_modules is unset (None): no modules
kind_overrides_sep = ","
kind_overrides_config = [
  "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.csv",
  "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.toml",
  "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.yaml",
  "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.yml",
]
input_depth = 0
input_follow_symlinks = true
```

`input_depth` and `input_follow_symlinks` are the packaged fallbacks for an omitted `depth` or `follow_symlinks` on an `inputs` item. They are not keys in the user's profile.

These stay in code. The parser needs them to read both files, or they are not a user default:

- Key names, environment names, namespace roots, file suffixes, and the four kind-override mode words.
- `DATE_TEXT` (`%Y-%m-%d`) as the stored date grammar. Editing `default_date_format` in `default.toml` changes display and kind-file parsing. It does not change how dates are stored.

## 2.2 Fallbacks

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

## 2.3 Readers

Missing and null are both `None` before the type check.

- `profile.py`: `default_date_format`, `root_dir`, `database_file`, `cache_file`.
- `record.py`: `RecordIdentity.resolve`. The flag wins, then `SUPERSHELF_RECORD_IDENTITY`, then `config.record_identity`, then packaged `path`. A bare `path` expands to `path` then `hash`. A bare `hash` expands to `hash` then `path`. A list does not expand its items. An empty string, an empty list, a repeated step, or an unknown step is invalid and does not fall back. Rule lists are behavior 4.2.
- `kind_file`: `KindDateFormat.from_section`, `KindCsvSep.from_section`, `KindOverrideMode.resolve`. `KindOverrideMode` is a `WordChoice`. The date-format reader uses the user's `default_date_format` only after `kind_overrides_date_format` is `None`.
- `scan.py`: a null `inputs` uses the same "no inputs" error as a missing key. An empty list stays "inputs is empty".

These also use a missing key and null as `None`: `kind_overrides_config`, `var_modules`, `match_rules`, `default_vars`, and the profile name. A present `overrides` key is a config error, not `None`.
