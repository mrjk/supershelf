# Kind file

A kind file is a list of rows for one kind. One row per path relative to the input. A missing variable is omitted. How the file is chosen is in [Kind files](../concepts/kind-files.md).

A cell is one string. It is not a candidate list. It is not compiled, even when it contains `{{`, `{%`, or `{#`. An empty cell, a blank string, or a YAML or TOML null is absent. When the row is applied, a non-empty cell is cast to the name's type. `text` keeps surrounding spaces. The other types strip once. `__date__` is parsed with `kind_overrides_date_format` and stored as `YYYY-MM-DD`.

Files are UTF-8. Invalid UTF-8 stops the command. A leading byte-order mark is accepted and is not part of the first column name. The suffix is `.csv`, `.toml`, `.yaml`, or `.yml`. `.yml` is the same text as YAML.

The examples below are the same two rows. The profile sets `kind_overrides_sep` to `;` and `kind_overrides_date_format` to `%d/%m/%Y`. The stored dates are `2026-04-25` and `2026-01-15`. An empty cell is absent. YAML and TOML ignore the separator.

=== "CSV"

    ```csv title="profile.books.invoice.csv"
    PATH;__date__;vendor;owner
    banking_1/REL_20260425.pdf;25/04/2026;Bank2000;
    Bank2000/card/CARD_1234_20211231.pdf;15/01/2026;;sample
    ```

=== "TOML"

    ```toml title="profile.books.invoice.toml"
    [[rows]]
    path = "banking_1/REL_20260425.pdf"

    [rows.vars]
    vendor = "Bank2000"
    __date__ = "25/04/2026"

    [[rows]]
    path = "Bank2000/card/CARD_1234_20211231.pdf"

    [rows.vars]
    __date__ = "15/01/2026"
    owner = "sample"
    ```

=== "YAML"

    ```yaml title="profile.books.invoice.yaml"
    - path: banking_1/REL_20260425.pdf
      vars:
        vendor: Bank2000
        __date__: "25/04/2026"

    - path: Bank2000/card/CARD_1234_20211231.pdf
      vars:
        __date__: "15/01/2026"
        owner: sample
    ```

## CSV

One data row per file. The header is checked by name and case. The first column is exactly `PATH`. `__date__` is optional and may sit anywhere after `PATH`. Other columns are the user's, in the user's order.

`config.kind_overrides_sep` is the separator. Omitted, it is a comma. The file is not scanned to guess it. The separator must be one character. A value that is not a string, an empty string, or more than one character stops the command. A letter, a digit, `_`, whitespace, `"`, `'`, `/`, `\`, or a newline is rejected. Comma and semicolon are the expected values. `|` is allowed.

Read and append use that separator. A file written with another separator fails the header check. Cells that contain the separator, a double quote, or a newline are quoted with `"`.

The first column must be `PATH`. `path` or `Path` is an error. A missing `PATH`, or `PATH` in a later position, is an error. A header named `SHA`, `sha`, or `Sha` is an error: rows match on `PATH`. There is no `DATE` column. `DATE`, `Date`, and `date` are errors: the date column is `__date__`. A column that is not lowercase is an error. A duplicate column is an error.

A column other than `PATH` and `__date__` must be lowercase and match `[a-z_][a-z0-9_]*`.

An empty file, or a file of whitespace only, is an empty table, not a missing-header error. A blank line is skipped. A row with values and an empty `PATH` is an error. A row with fewer cells than the header is padded with empty cells. A row with more cells than the header stops the command.

## TOML and YAML

YAML is a bare list. There is no key above it. Each item has `path` and `vars`. `vars` is a mapping of name to text. Omitted `vars`, or an empty mapping, adds no variables. Any other shape for `vars` stops the command. Unknown keys on the item are ignored.

TOML cannot be a root list, so the file is `[[rows]]` tables. Each table has `path` and a `[rows.vars]` table. The items are the same as YAML.

`path` is the path relative to the input, with `/` separators. It is an exact match, not a glob.

A name under `vars` must match `[A-Za-z_][A-Za-z0-9_]*`. TOML rejects a duplicate key in one `vars` table. YAML keeps the last value for a duplicate key and does not stop. A missing `path` stops the command. A number, boolean, date, list, or nested mapping stops the command. Quote scalars such as dates. In YAML, also quote `yes`, `no`, `on`, and `off`, because those words become booleans.

## Names

A row must not set an internal name, `file_ctime`, or `file_mtime`. `__date__` is allowed. `__kind__` is not.

Two rows with the same path: a warning, the first row is kept, and the later row stays in the file.

## A new file

A new file is an `always` create, or an `auto` or `always` replacement of an empty or whitespace-only file. `manual` does not write.

A new CSV header is `PATH` and `__date__`, joined by `kind_overrides_sep`. Omitted, that header is `PATH,__date__`. The semicolon example writes `PATH;__date__`. There is no `SHA` column, no `DATE` column, and no other column. Then one row per matched file. Each new row sets `PATH` and leaves `__date__` empty.

A new TOML or YAML file is the same rows, with `path` set and `vars` omitted.

An append uses the existing header order and does not add a column. `PATH` or `path` is filled. The other cells are empty.
