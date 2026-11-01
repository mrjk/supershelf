# Variable names

Printed names come from the file, the winning regex, and the assignment layers. Profile names are available while a template renders and are not printed on their own. The layer order and the types are in [Variables](../concepts/variables.md).

Built-in facts below are type `text`. `__date__` is type `date`. A user name with no `vars_schema` entry is `text`.

## Printed facts

These are set from the file and the match. Assignments cannot replace them, except `__kind__`, which only `overrides` may set.

| Name | Value |
| --- | --- |
| `__kind__` | Kind from the winning rule, then an override if one sets it. |
| `__rule_name__` | Winning rule name. An override does not change it. |
| `__ctime__` | Stored UTC ISO-8601 ctime. |
| `__mtime__` | Stored UTC ISO-8601 mtime. |
| `__file_hash__` | Lowercase sha256 of the file bytes. |
| `__file_name__` | Filename. |
| `__file_stem__` | Filename without the last suffix. `archive.tar.gz` is `archive.tar`. |
| `__file_ext__` | Last suffix without the dot. `archive.tar.gz` is `gz`. Empty when there is no suffix. |
| `__file_path__` | Path relative to the input, with `/` separators. |
| `__file_dir__` | Directory relative to the input. Empty in the input directory. |

| Name | Value |
| --- | --- |
| `file_ctime` | Same string as `__ctime__`. |
| `file_mtime` | Same string as `__mtime__`. |

Named regex groups are printed after these, in pattern order. A group name that starts with `__` stops the command before the walk. A group that reuses an internal name or an alias is dropped.

## Document date

| Name | Who may set it | Value |
| --- | --- | --- |
| `__date__` | `default_vars`, rule `vars`, kind file, `overrides` | Type `date`. Stored as `YYYY-MM-DD`. |

`__date__` is not an internal. The filename does not set it. In `default_vars`, rule `vars`, and `overrides`, an empty string does not count as success. A candidate list that misses leaves an earlier value in place. A kind-file cell is parsed with `kind_overrides_date_format` and stored as `YYYY-MM-DD`. A blank cell is absent. A cell that does not match the format stops the command.

## Profile scope

These names are in scope for path templates and variable templates. They are not printed as their own rows. An assignment cannot reuse one of them. A name that starts with `__` and is not a managed variable stops the command with "is not a supershelf variable". The managed names are the internal facts, `file_ctime`, `file_mtime`, and `__date__`.

| Name | Value |
| --- | --- |
| `__profile__` | Profile name. Alias of `__profile_name__`. |
| `__profile_name__` | Profile name. |
| `__profile_type__` | `toml` or `yaml`. |
| `__profile_path__` | Absolute path of the config file. |
| `__profile_dir__` | Directory of the config file. |
| `__profile_file__` | Filename of the config file. |
| `__default_date_format__` | `config.default_date_format`. |
| `__config_data__` | The parsed config file. Dotted keys read nested mappings. |
| `__root_dir__` | Rendered root directory. |
| `__database_file__` | Rendered database path. The file is not created. |
| `__cache_file__` | Rendered cache path. The file is not created. |

Kind-file path templates also see:

| Name | Value |
| --- | --- |
| `__kind__` | The rule kind, before an override changes the printed kind. |
| `__input__.path` | Absolute path of that input directory. |

`__kind__` and `__input__.path` are not in the general profile scope. An `inputs` path cannot read them.

## Who may assign a name

| Name | `default_vars` | Rule `vars` | Kind file | `overrides` |
| --- | --- | --- | --- | --- |
| `__kind__` | no | no | no | yes |
| other internals, `file_ctime`, `file_mtime` | no | no | no | no |
| `__date__` | yes | yes | yes | yes |
| a name that does not start with `__` | yes | yes | yes | yes |
| any other name that starts with `__` | no | no | no | no |

A variable name matches `[A-Za-z_][A-Za-z0-9_]*`.
