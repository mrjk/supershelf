# Set variables

`supershelf scan vars` prints one row per matched file. The `vars` cell lists the final values. How those values are layered is in [Variables](../concepts/variables.md).

This profile sets a default owner, then replaces the vendor on the Bank2000 statement rule. The filename regex captures `date` and `receipt_id`. Those captures are facts. The rule can read them.

=== "TOML"

    ```toml title="profile.books.toml"
    [[inputs]]
    path = "inbox"

    [default_vars]
    vendor = "UNKNOWN"
    owner = "sample"

    [[match_rules]]
    name = "bank2000_statement"
    kind = "invoice"
    filename_regex = 'REL_(?P<date>\d{8})_(?P<receipt_id>\w{8})\.pdf'

    [match_rules.vars]
    vendor = "Bank2000"
    receipt = ["{{ receipt_id }}", "UNKNOWN"]

    [[match_rules]]
    name = "unsorted"
    glob = "**"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    inputs:
      - path: inbox

    default_vars:
      vendor: UNKNOWN
      owner: sample

    match_rules:
      - name: bank2000_statement
        kind: invoice
        filename_regex: 'REL_(?P<date>\d{8})_(?P<receipt_id>\w{8})\.pdf'
        vars:
          vendor: Bank2000
          receipt:
            - "{{ receipt_id }}"
            - UNKNOWN

      - name: unsorted
        glob: "**"
    ```

`receipt` tries `{{ receipt_id }}` first. If that name is missing, the next candidate, `UNKNOWN`, is kept. A candidate with no `{{`, `{%`, or `{#` is stored as written.

```bash
supershelf scan vars "Bank2000/REL_20260425_ab12cd34.pdf"
```

Example `vars` cell, with the file facts shortened:

```text
__kind__: invoice
sources: fact
__rule_name__: bank2000_statement
sources: fact
__file_name__: REL_20260425_ab12cd34.pdf
sources: fact
date: 20260425
sources: fact
receipt_id: ab12cd34
sources: fact
vendor: Bank2000
sources: default, rule:bank2000_statement
owner: sample
sources: default
receipt: ab12cd34
sources: rule:bank2000_statement
```

Each name is two lines. The cell above leaves out the other file facts. The printed order is the internal facts, then `file_ctime` and `file_mtime`, then regex groups, then assignment keys in the order they were first stored. `vendor` was set in `default_vars` and replaced by the rule, so it keeps the earlier position, and both layers stay in `sources`. `owner` stays `sample` because the rule does not set it.

## Declare a type

`vars_schema` sets the type of a name. A filename group with that name is cast when the match stores it. The rules are in [Variables](../concepts/variables.md).

=== "TOML"

    ```toml title="profile.books.toml"
    [vars_schema.amount]
    type = "float"
    unit = "EUR"

    [[match_rules]]
    name = "bank2000_amount"
    kind = "invoice"
    filename_regex = 'REL_(?P<amount>[0-9]+[.][0-9]{2})\.pdf'
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    vars_schema:
      amount:
        type: float
        unit: EUR

    match_rules:
      - name: bank2000_amount
        kind: invoice
        filename_regex: 'REL_(?P<amount>[0-9]+[.][0-9]{2})\.pdf'
    ```

For `REL_12.50.pdf`, `amount` prints as `12.50` and the JSON value is `12.5`. Templates still read the string `12.50`. `EUR12.50` stops the file, because a regex group has no next candidate.

There is no `--quick` on this command. The walk always reads mtime, ctime, and sha256. The path argument is the same as [List files](list-files.md). Omit it to list every matched file. An exact file path lists that file in every input that has it. Any other value lists matched paths that start with it. A value that no kept file has stops the command. When a path is set, only the selected files are matched, so other files are not warned.

A key in one mapping cannot read a key that appears later in that same mapping. `{{ vendor }}` inside `default_vars`, next to `vendor`, still sees the previous layer, which is the fact scope. It does not see the candidate list being tried.

The next page turns the captured date into a calendar date: [Set the document date](set-the-document-date.md).
