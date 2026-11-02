# Set the document date

`__date__` is the document date. When it is set, the stored value is `YYYY-MM-DD`. `{{ __date__ }}` prints with `default_date_format`. `{{ __date__.strftime('%Y-%m') }}` is a custom pattern. `Y`, `m`, and `d` are `%Y`, `%m`, and `%d`. A layout that uses `__date__` fails when `__date__` was omitted. See [Output](../concepts/output.md).

The commands used below are documented in [Template commands](../concepts/template-commands.md).

Put the fallback list on `default_vars`, then let a rule try its own captured date first:

=== "TOML"

    ```toml title="profile.books.toml"
    [default_vars]
    __date__ = [
      '{{ regex_time_var(date, "%Y%m%d") }}',
      '{{ meta("pdf", "creation_date") }}',
      '{{ meta("pdf", "modification_date") }}',
      '{{ __file__.ctime }}',
    ]

    [[match_rules]]
    name = "bank2000_statement"
    kind = "invoice"
    filename_regex = 'REL_(?P<date>\d{8})_(?P<receipt_id>\w{8})\.pdf'

    [match_rules.vars]
    __date__ = [
      '{{ regex_time_var(date, "%Y%m%d") }}',
      '{{ __date__ }}',
    ]
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    default_vars:
      __date__:
        - '{{ regex_time_var(date, "%Y%m%d") }}'
        - '{{ meta("pdf", "creation_date") }}'
        - '{{ meta("pdf", "modification_date") }}'
        - '{{ __file__.ctime }}'

    match_rules:
      - name: bank2000_statement
        kind: invoice
        filename_regex: 'REL_(?P<date>\d{8})_(?P<receipt_id>\w{8})\.pdf'
        vars:
          __date__:
            - '{{ regex_time_var(date, "%Y%m%d") }}'
            - '{{ __date__ }}'
    ```

`regex_time_var` reads the string already stored as `date` and returns `YYYY-MM-DD`. For `REL_20260425_ab12cd34.pdf` that is `2026-04-25`. The rule list tries that first. `{{ __date__ }}` reads the string the earlier layer kept. It does not run the earlier candidate list again.

`meta("pdf", "creation_date")` and `meta("pdf", "modification_date")` return `YYYY-MM-DD`. The file is opened only when a candidate calls `meta()`.

`{{ __file__.ctime }}` is the stored UTC timestamp, such as `2026-04-25T16:28:00+00:00`. That text is not `YYYY-MM-DD`, so the `__date__` check fails this candidate. In the list above it is the last `default_vars` candidate, so that layer ends. On its own it does not become `__date__`. `{{ __file__.mtime }}` is the same kind of timestamp.

A `__date__` candidate that renders to anything else fails, and the next candidate is tried. If every candidate in that layer misses, the earlier value stays. When no layer sets `__date__`, it is omitted and the command continues. The same rule applies to every other variable. The filename does not set `__date__`. `mandatory: true` stops the file when the value is still unset after the last layer.

`__date__` is type `date`. `vars_schema.__date__` may set `desc`, `unit`, `mandatory`, `default`, and `validation`. It cannot change the type. Quote date scalars in `default_vars`, rule `vars`, and kind files. An unquoted date is not a string, and those layers take a string or a list of strings.

The next page stores one path in a kind file: [Set a value in the kind file](share-variables-for-a-kind.md).
