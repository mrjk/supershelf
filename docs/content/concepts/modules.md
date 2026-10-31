# Modules

`config.var_modules` is an optional list of importable module paths. Omitted or empty means no user modules.

Built-in commands are always registered first. Then each module is imported in list order, before the walk. An import failure stops the command.

A module may export two mappings:

- `GLOBALS`: call them as `{{ name(...) }}`
- `FILTERS`: call them as `{{ value | name(...) }}`

Values are callables. They should accept strings and return a string. A return value that is not a string fails that candidate. Raising `VarCandidateError` fails that candidate and lets the next one run. Any other exception stops the command.

A name that repeats a built-in, or an earlier module, stops the command. Built-in commands cannot be replaced. Keys must be strings. A mapping that is not a mapping, or a value that is not callable, stops the command.

```python title="my_package/supershelf_vars.py"
from supershelf.errors import VarCandidateError


def account_tail(value: str) -> str:
    if len(value) < 4:
        raise VarCandidateError("account is too short")
    return value[-4:]


GLOBALS = {"account_tail": account_tail}
```

=== "TOML"

    ```toml title="profile.books.toml"
    [config]
    var_modules = ["my_package.supershelf_vars"]
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    config:
      var_modules:
        - my_package.supershelf_vars
    ```

```jinja
{{ account_tail(account) }}
```

`FILTERS` may be omitted. `GLOBALS` may be omitted. A module that exports neither adds no commands.
