# Kind file

A kind file is one variable table for a kind, not one row per file. How it is chosen is in [Kind files](../concepts/kind-files.md). Values follow the same rules as `default_vars`: a string or a list of strings, and Jinja when the text contains `{{`, `{%`, or `{#`.

Files are UTF-8. Invalid UTF-8 stops the command. The CSV header must be the two names `name` and `value`, so a leading byte-order mark is not accepted. The suffix must be `.csv`, `.toml`, `.yaml`, or `.yml`.

Forbidden names are the internals other than a document date, plus `file_ctime` and `file_mtime`. `__kind__` is forbidden here. `__date__` is allowed and must render to `YYYY-MM-DD`.

## CSV

The header row is `name,value`. Each later row is one candidate. A repeated name adds the next candidate, in file order. Blank lines are skipped. Every data row has two columns. Cells are stripped of surrounding space.

```csv title="profile.books.invoice.csv"
name,value
vendor,Bank2000
owner,{{ missing }}
owner,sample
__date__,2026-04-25
```

`vendor` is the literal `Bank2000`. `owner` tries `{{ missing }}`, fails that candidate, and keeps `sample`. An empty cell is an empty string. An empty string succeeds for every name except `__date__`.

## TOML and YAML

A mapping at the root. A list value is a candidate list. `.yml` is the same text as YAML.

Quote scalars that YAML would otherwise read as dates, numbers, or booleans. A value that is a number, a boolean, a date, a nested mapping, or an empty list stops the command.

=== "TOML"

    ```toml title="profile.books.invoice.toml"
    vendor = "Bank2000"
    owner = ["{{ missing }}", "sample"]
    __date__ = ['{{ regex_time_var(date, "%Y%m%d") }}', "2026-04-25"]
    ```

=== "YAML"

    ```yaml title="profile.books.invoice.yaml"
    vendor: Bank2000
    owner:
      - "{{ missing }}"
      - sample
    __date__:
      - '{{ regex_time_var(date, "%Y%m%d") }}'
      - "2026-04-25"
    ```
