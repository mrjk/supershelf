# Configuration

A profile file is a mapping. TOML and YAML are accepted. `.yml` is YAML. Paths inside the file are described in [Paths](../concepts/paths.md). Discovery is in [Profiles](../concepts/profiles.md).

Which file is loaded, and which profiles run:

1. CLI: `--config`, `--profile`
2. Environment: `SUPERSHELF_CONFIG`, `SUPERSHELF_PROFILES`
3. Discovery in the current directory, then the user config directory
4. Built-in defaults for omitted keys inside the file

There is no environment variable for `root_dir` or the other keys below. An omitted key uses its default. A command that reads a key stops if that key has the wrong type. `supershelf profiles` checks that the file is a mapping and that `config.profile`, when set, is a string. It does not render paths.

## config

These keys live under `config`.

| Key | Type | Default | Role |
| --- | --- | --- | --- |
| `profile` | string | from the filename, or `default` | Profile name when the filename is not `profile.NAME.*`. See [Profiles](../concepts/profiles.md). |
| `default_date_format` | string | `%Y-%m-%d` | `strftime` pattern for mtime and ctime in `scan files`. Not a template. |
| `root_dir` | string | `{{ __profile_dir__ }}` | Path template. Relative results resolve from the config directory. |
| `database_file` | string | `{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite` | Path template. Rendered, not created. |
| `cache_file` | string | `{{ __root_dir__ }}/profile.{{ __profile__ }}.cache` | Path template. Rendered, not created. |
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
| `overrides` | list of mappings | none | Highest assignment layer. First matching path wins. |

### inputs item

| Key | Type | Default |
| --- | --- | --- |
| `path` | string | required |
| `include` | list of strings | omitted: keep every file the walk found |
| `exclude` | list of strings | omitted: drop nothing |
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

A rule needs `name` or `kind`, and at least one pattern. Other unknown keys are ignored while matching.

### overrides item

| Key | Type | Role |
| --- | --- | --- |
| `path` | string | Glob, full-matched against the relative path. Not a template. |
| `vars` | mapping | Values for a hit. The only layer that may set `__kind__`. |

Unknown keys on an override item are ignored. `path` and `vars` are required.

### Variable values

In `default_vars`, rule `vars`, and override `vars`, each value is a string or a list of strings. Quote scalars such as dates. An empty list stops the command. A kind-file cell is one string, not a list. Details are in [Variables](../concepts/variables.md) and [Kind file](kind-file.md).

## Environment

| Variable | Overrides | Meaning |
| --- | --- | --- |
| `SUPERSHELF_CONFIG` | `--config` wins | File or directory, same rules as `--config`. |
| `SUPERSHELF_PROFILES` | `--profile` wins | Comma-separated profile names. |
| `SUPERSHELF_KIND_OVERRIDES_MODE` | `--kind-overrides-mode` wins | `auto`, `manual`, `always`, or `disabled`. Wins over `config.kind_overrides_mode`. |

<!-- placeholder: config schema -->
