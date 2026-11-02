# Paths

Profile paths use a small template language. Variable values use Jinja, which is a different language. Both are compared in [Templates](../reference/templates.md).

A path template replaces `{{ name }}` and `{{ name.key }}` once. Spaces inside the braces are allowed. The name must already be in scope. Dotted keys read nested mappings. The value must be a string. Text taken from the scope is not rendered again, so a value that itself contains `{{` is stored as text.

Unknown names, missing keys, and non-string values stop the command. There are no filters and no function calls.

## Render order

These `config` keys are rendered in order. After each one, a relative result is resolved from the directory that contains the config file, stored as an absolute path, and published in the scope before the next key renders.

| Key | Scope name | Default |
| --- | --- | --- |
| `root_dir` | `__root_dir__` | `{{ __profile_dir__ }}` |
| `database_file` | `__database_file__` | `{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite` |
| `cache_file` | `__cache_file__` | `{{ __root_dir__ }}/profile.{{ __profile__ }}.cache` |

`~` is expanded. An empty result stops the command. A relative `database_file` such as `state.sqlite` is resolved from the config directory, not from `root_dir`. To place it under the root, write `{{ __root_dir__ }}/state.sqlite`.

`config.default_date_format` is a plain string. It is not a template. The default is `%Y-%m-%d`. It formats mtime and ctime in `scan files`. The stored timestamps used by variables stay UTC ISO-8601.

`scan vars`, `record run`, `data feed`, and `data show` create `database_file` when `meta()` runs and the cache misses. `--dry-run` does not. `scan files`, `scan kinds`, and `data prune` do not. `record run` also creates `database_file` when a row would change. Nothing writes `cache_file`. The paths are rendered so later templates can read them.

## Other paths

`inputs.path` uses this same language, with the profile scope. A relative result is resolved from `__root_dir__`.

`kind_overrides_config` uses it too. For that render, the scope also has `__kind__` and `__input__.path`. `__input__.path` is the absolute input directory. A relative result is resolved from `__root_dir__`. Those two names are not part of the general profile scope, so an input path cannot read them.

The names available in the profile scope are listed in [Variable names](../reference/variable-names.md).
