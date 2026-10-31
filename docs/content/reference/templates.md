# Templates

Supershelf has two template languages. Path settings use the small language. Variable values use Jinja when the string looks like a template.

## Path templates

Used by `config.root_dir`, `config.database_file`, `config.cache_file`, `inputs.path`, and each `kind_overrides_config` entry.

```text
{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite
{{ __config_data__.config.profile }}
```

- Replaces `{{ name }}` and `{{ name.key }}` once.
- Spaces inside the braces are allowed.
- The value must be a string. Nested keys walk mappings.
- Text copied from the scope is not rendered again.
- An unknown name, a missing key, or a non-string stops the command.
- No filters, no function calls, and no `{%` blocks.

## Variable templates

Used by `default_vars`, rule `vars`, override `vars`, and kind-file values.

A string with no `{{`, `{%`, or `{#` is a literal. It is stored as written.

```jinja
Bank2000
{{ receipt_id }}
{{ regex_time_var(date, "%Y%m%d") }}
{{ account_tail(account) }}
```

- Jinja, with strict undefined names and `autoescape` off.
- The result must be a string.
- An unknown name fails that candidate. The next candidate in the list can run.
- A syntax error stops the command when the template is loaded.
- Each distinct source is compiled once per process.
- The rendered string is not rendered again.
- A key cannot read a later key in the same mapping.
- A reference to the key being rendered sees the previous layer.

Commands are listed in [Template commands](../concepts/template-commands.md). Extra commands are in [Modules](../concepts/modules.md).
