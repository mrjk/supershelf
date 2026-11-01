# Set the document date

`__date__` is the document date. When it is set, the value is a calendar date `YYYY-MM-DD`. Supershelf uses that date for the document, including later output paths. This version does not write those paths. See [Limits](../concepts/limits.md).

The commands used below are documented in [Template commands](../concepts/template-commands.md).

Put the fallback list on `default_vars`, then let a rule try its own captured date first:

=== "TOML"

    ```toml title="profile.books.toml"
    [default_vars]
    __date__ = [
      '{{ regex_time_var(date, "%Y%m%d") }}',
      '{{ pdf_cdate() }}',
      '{{ pdf_mdate() }}',
      '{{ file("ctime") }}',
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
        - '{{ pdf_cdate() }}'
        - '{{ pdf_mdate() }}'
        - '{{ file("ctime") }}'

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

`pdf_cdate()` and `pdf_mdate()` read PDF info and also return `YYYY-MM-DD`. The file is opened only when a candidate calls one of them.

`file("ctime")` returns the stored UTC timestamp, such as `2026-04-25T16:28:00+00:00`. That text is not `YYYY-MM-DD`, so the `__date__` check fails this candidate and the next one runs. On its own it does not become `__date__`. `file("mtime")`, `file_ctime`, and `file_mtime` are the same kind of timestamp.

A `__date__` candidate that renders to anything else fails, and the next candidate is tried. If every candidate fails, `__date__` is omitted and the command continues. Any other variable whose candidates all fail stops the command. The error names the profile, the input, the path, and the variable.

`__date__` is type `date`. `vars_schema.__date__` may set `desc`, `unit`, `mandatory`, `default`, and `validation`. It cannot change the type. Quote date scalars in `default_vars`, rule `vars`, overrides, and kind files. An unquoted date is not a string, and those layers take a string or a list of strings.

The next page changes one file after these layers: [Override one file](override-one-file.md).
