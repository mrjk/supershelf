# Set a value in the kind file

A kind file stores one row for a path. `scan vars` applies that row after the winning rule's `vars` and before `overrides`. The cell replaces the value the rule stored. The lookup and the modes are in [Kind files](../concepts/kind-files.md). The file shape is in [Kind file](../reference/kind-file.md).

For profile `books` and kind `invoice`, the first default path is `profile.books.invoice.csv` under the profile root.

Set the separator and the date format, then add a row for one statement:

=== "TOML"

    ```toml title="profile.books.toml"
    [config]
    kind_overrides_sep = ";"
    kind_overrides_date_format = "%d/%m/%Y"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    config:
      kind_overrides_sep: ";"
      kind_overrides_date_format: "%d/%m/%Y"
    ```

```csv title="profile.books.invoice.csv"
PATH;__date__;vendor;owner
banking_1/REL_20260425.pdf;25/04/2026;Bank2000;
Bank2000/card/CARD_1234_20211231.pdf;15/01/2026;;sample
```

`vendor` on the first row replaces the rule's vendor for that path only. The empty `owner` cell leaves the earlier owner in place. The text is stored as written. `{{ owner }}` would be those characters, not a template.

`25/04/2026` is parsed with `kind_overrides_date_format` and stored as `2026-04-25`. A cell that does not match that format stops the command. A blank `__date__` cell leaves the earlier date in place.

```bash
supershelf scan vars
```

The default mode is `auto`. When the CSV already exists, invoice paths that are not in the file are appended. The new cells are empty, so this run still prints the values from the rule. Fill a cell and run the command again to use it.

`manual` reads the file and does not append. `always` creates `profile.books.invoice.csv` when no candidate exists. `disabled` ignores kind files. `--kind-overrides-mode` sets the mode for this command. `--dry-run` reads and does not write. `-v` shows the dry-run message when a file would change.

The kind in the filename is the kind from the match rule. An override that changes `__kind__` does not switch files.

The next page loads more than one profile: [Use several profiles](use-several-profiles.md).
