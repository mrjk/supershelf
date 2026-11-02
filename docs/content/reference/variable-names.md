# Variable names

Printed names come from the file, the winning regex, and the assignment layers. Profile names are available while a template renders and are not printed on their own. The layer order and the types are in [Variables](../concepts/variables.md).

Built-in facts below are type `text`. `__date__` is type `date`. A user name with no `vars_schema` entry is `text`.

## Printed facts

These are set from the file and the match. Assignments cannot replace them. `__match__.kind` stays the kind from the match rule. `scan vars` prints them only with `--all`.

| Name | Value |
| --- | --- |
| `__match__.kind` | Kind from the winning rule. |
| `__match__.rule` | Winning rule name. |
| `__file__.ctime` | Stored UTC ISO-8601 ctime. |
| `__file__.mtime` | Stored UTC ISO-8601 mtime. |
| `__file__.hash` | Lowercase sha256 of the file bytes. |
| `__file__.name` | Filename. |
| `__file__.stem` | Filename without the last suffix. `archive.tar.gz` is `archive.tar`. |
| `__file__.ext` | Last suffix without the dot. `archive.tar.gz` is `gz`. Empty when there is no suffix. |
| `__file__.path` | Path relative to the input, with `/` separators. |
| `__file__.dir` | Directory relative to the input. Empty in the input directory. |

Named regex groups are stored in pattern order and printed with the other names. The table sorts every name alphabetically. A group name that starts with `__` stops the command before the walk.

## Document date

| Name | Who may set it | Value |
| --- | --- | --- |
| `__date__` | `default_vars`, rule `vars`, kind file | Type `date`. Stored as `YYYY-MM-DD`. |

`__date__` is not an internal. The filename does not set it. In `default_vars` and rule `vars`, an empty string does not count as success. A candidate list that misses leaves an earlier value in place. A kind-file cell is parsed with `kind_overrides_date_format` and stored as `YYYY-MM-DD`. `data feed` writes `__date__` with that format. A `date` var that is not `__date__` stays `YYYY-MM-DD`. A blank cell is absent. A cell that does not match the format stops the command.

`{{ __date__ }}` prints with `default_date_format`. The stored value stays `YYYY-MM-DD`. In a Jinja template the same value also has `Y`, `m`, and `d`: `%Y`, `%m`, and `%d`. `{{ __date__.strftime('%Y-%m') }}` is a custom pattern. The printed value and `vars_json` stay the full stored date.

## Profile scope

`__profile__` and `__config__` are objects. With no field, `__profile__` prints the name and `__config__` prints `root_dir`. Read a field for anything else. They are not printed. A layer cannot set them. `__date__` is the only assignable name that starts with `__`.

These fields are in profile path templates (`root_dir`, `database_file`, `cache_file`, `inputs.path`, and an output `path`):

| Name | Value |
| --- | --- |
| `__profile__.name` | Profile name. |
| `__profile__.type` | `toml` or `yaml`. |
| `__profile__.path` | Absolute path of the config file. |
| `__profile__.dir` | Directory of the config file. |
| `__profile__.file` | Filename of the config file. |
| `__profile__.document` | The parsed config file. Dotted keys read nested mappings. |
| `__config__.date_format` | `config.default_date_format`. |
| `__config__.root_dir` | Rendered root directory. |
| `__config__.database_file` | Rendered database path. `record run` creates it when a row would change. `scan vars`, `record run`, `data feed`, and `data show` also create it when `meta()` runs and the cache misses. `--dry-run` does not. |
| `__config__.cache_file` | Rendered cache path. The file is not created. |

`__file__`, `__match__`, `__input__`, and `__date__` are not in those path templates.

Kind-file path templates also see `__match__.kind` and `__input__.path`. They do not see `__match__.rule` or `__file__`. A relative kind path and a relative input path resolve from `__config__.root_dir`. A relative `root_dir`, `database_file`, or `cache_file` resolves from the profile directory.

Variable templates and output `when` and `layout` see `__file__` and the full `__match__` (`kind` and `rule`). They do not see `__input__`.

## Who may assign a name

| Name | `default_vars` | Rule `vars` | Kind file |
| --- | --- | --- | --- |
| a namespace root | no | no | no |
| `__date__` | yes | yes | yes |
| a name that does not start with `__` | yes | yes | yes |
| any other name that starts with `__` | no | no | no |

A variable name matches `[A-Za-z_][A-Za-z0-9_]*`. A key cannot contain a dot.
