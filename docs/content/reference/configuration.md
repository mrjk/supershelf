# Configuration

A profile file is a mapping. TOML and YAML are accepted. `.yml` is YAML. Paths inside the file are described in [Paths](../concepts/paths.md). Discovery is in [Profiles](../concepts/profiles.md).

Which file is loaded, and which profiles run:

1. CLI: `--config`, `--profile`
2. Environment: `SUPERSHELF_CONFIG`, `SUPERSHELF_PROFILES`
3. Discovery in the current directory, then the user config directory
4. Built-in defaults for omitted keys inside the file

There is no environment variable for `root_dir` or the other keys below, except `kind_overrides_mode` and `record_identity`. An omitted key uses its default. On the optional `config` keys, and on `include`, `exclude`, `depth`, and `follow_symlinks`, a YAML null is the same as omitting the key. An empty string and an empty list stay set. `include: []` keeps no file. A candidate, and `vars_schema.<name>.default`, reject null: null is not unset. A command that reads a key stops if that key has the wrong type. `supershelf profiles` checks that the file is a mapping and that `config.profile`, when set, is a string. It does not render paths.

## config

These keys live under `config`.

| Key | Type | Default | Role |
| --- | --- | --- | --- |
| `profile` | string | from the filename, or `default` | Profile name when the filename is not `profile.NAME.*`. See [Profiles](../concepts/profiles.md). |
| `default_date_format` | string | `%Y-%m-%d` | `strftime` pattern for mtime and ctime in `scan files`. Not a template. |
| `root_dir` | string | `{{ __profile_dir__ }}` | Path template. Relative results resolve from the config directory. |
| `database_file` | string | `{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite` | Path template. `record run` creates it when a row would change. Scan commands do not. |
| `cache_file` | string | `{{ __root_dir__ }}/profile.{{ __profile__ }}.cache` | Path template. Rendered, not created. |
| `record_identity` | string or list of strings | `path` | `path`, `hash`, or a list of those steps. A bare `path` means path then hash. A bare `hash` means hash then path. A list does not expand. `""` and `[]` are invalid and do not fall back. See [Record](../concepts/record.md). |
| `var_modules` | list of strings | none | Importable modules. See [Modules](../concepts/modules.md). |
| `kind_overrides_mode` | string | `auto` | `auto`, `manual`, `always`, or `disabled`. See [Kind files](../concepts/kind-files.md). |
| `kind_overrides_date_format` | string | `default_date_format` | `strptime` format for a kind-file `__date__` cell. |
| `kind_overrides_sep` | one character | `,` | CSV separator. YAML and TOML ignore it. See [Kind file](kind-file.md). |
| `kind_overrides_config` | list of strings | the four default kind paths | Path templates. First existing file wins. `[]` means no kind files. See [Kind files](../concepts/kind-files.md). |

Other keys under `config` are stored. This version does not interpret them.

## Top level

| Key | Type | Default | Role |
| --- | --- | --- | --- |
| `inputs` | list of mappings | required for a scan | Folders to walk. See [Inputs](../concepts/inputs.md). |
| `match_rules` | list of mappings | none | First match wins. Missing means nothing matches. See [Matching](../concepts/matching.md). |
| `default_vars` | mapping | none | Lowest assignment layer. See [Variables](../concepts/variables.md). |
| `vars_schema` | mapping | none | Type of each variable name. A missing name is `text`. See [Variables](../concepts/variables.md). |
| `kind_schema` | mapping | none | Per-kind names that point at `vars_schema`. See [Variables](../concepts/variables.md). |
| `overrides` | list of mappings | none | Highest assignment layer. First matching path wins. |

### inputs item

| Key | Type | Default |
| --- | --- | --- |
| `path` | string | required |
| `include` | list of strings | omitted or null: keep every file the walk found. `[]` keeps no file |
| `exclude` | list of strings | omitted or null: drop nothing. `[]` drops nothing |
| `depth` | integer `0` or greater | `0`, no recursion limit |
| `follow_symlinks` | boolean | `true` |

Unknown keys on an input stop the command.

### match_rules item

| Key | Type | Role |
| --- | --- | --- |
| `name` | string | Rule name. Unique in the profile. |
| `kind` | string | Kind stored for a hit. Defaults to `name`. |
| `regex` | string or list of strings | Whole relative path. |
| `directory_regex` | string or list of strings | Directory under the input. |
| `filename_regex` | string or list of strings | Filename, including the extension. |
| `glob` | string or list of strings | Whole relative path. |
| `directory_glob` | string or list of strings | Directory under the input. |
| `filename_glob` | string or list of strings | Filename. |
| `vars` | mapping | Assignment layer for this rule. Ignored by matching. Read by `scan vars`. |
| `record_identity` | string or list of strings | the profile default | Fallback order for this rule. Omitted or null inherits `config.record_identity`. Ignored by scan commands. Read by `record status` and `record run`. |

A rule needs `name` or `kind`, and at least one pattern. Other unknown keys are ignored while matching.

### overrides item

| Key | Type | Role |
| --- | --- | --- |
| `path` | string | Glob, full-matched against the relative path. Not a template. |
| `vars` | mapping | Values for a hit. The only layer that may set `__kind__`. |

Unknown keys on an override item are ignored. `path` and `vars` are required.

### vars_schema item

| Key | Type | Default |
| --- | --- | --- |
| `desc` | string | empty |
| `type` | `text`, `int`, `float`, `bool`, `date`, `time`, or `datetime` | `text` |
| `unit` | string | omitted |
| `mandatory` | boolean | `false` |
| `default` | typed literal, string, or list of candidates | omitted. Same slot as `default_vars`. |
| `validation` | mapping | omitted |

Unknown keys stop the command. `default` set here and in `default_vars` for the same name stops the command.

### kind_schema item

| Key | Type | Default |
| --- | --- | --- |
| `desc` | string | empty |
| `vars_schema` | mapping | required |

Each `vars_schema` value is a catalog reference:

| Value | Meaning |
| --- | --- |
| null or `""` | `schema` is the local name. YAML `amount:` is null. TOML has no null, so use `amount = ""`. A blank string is the same. |
| string | That string is `schema`. `my_amount: amount` remaps the local name. |
| mapping | Keys below. Omitted, null, or blank `schema` uses the local name. |

Each mapping:

| Key | Type | Default |
| --- | --- | --- |
| `schema` | string | the local name. A `vars_schema` name, or `__date__`. |
| `desc` | string | copied from the referenced spec |
| `unit` | string | copied from the referenced spec |
| `mandatory` | boolean | copied from the referenced spec. `false` loosens it for this kind. |
| `default` | typed literal, string, or list of candidates | omitted. Not copied. Applies only to this kind's local name. |
| `validation` | mapping | copied when omitted. A present mapping replaces the referenced one. |

`type` and `internal` cannot be set here. Unknown keys stop the command. On a CSV, `auto` and `always` use these local names as columns. A kind that is not listed uses the declared `vars_schema` names. A name that is not a legal column is left out. With no schema columns, a new CSV still starts as `PATH,__date__`.

### Variable values

In `default_vars`, rule `vars`, and override `vars`, each value is a string or a list of strings. Quote scalars such as dates. An empty list stops the command. A kind-file cell is one string, not a list. After a candidate or a cell is accepted, it is cast to the name's type. A typed literal belongs on `vars_schema.<name>.default`. Details are in [Variables](../concepts/variables.md) and [Kind file](kind-file.md).

## Environment

| Variable | Overrides | Meaning |
| --- | --- | --- |
| `SUPERSHELF_CONFIG` | `--config` wins | File or directory. A blank or whitespace flag stops the command. A blank or whitespace variable is unset. A set value uses the same path rules as `--config`. |
| `SUPERSHELF_PROFILES` | `--profile` wins | Comma-separated profile names. A blank flag stops the command. A blank or whitespace variable is unset, so every discovered profile is kept. |
| `SUPERSHELF_KIND_OVERRIDES_MODE` | `--kind-overrides-mode` wins | `auto`, `manual`, `always`, or `disabled`. Wins over `config.kind_overrides_mode`. |
