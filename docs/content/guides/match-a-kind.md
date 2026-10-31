# Match a kind

`supershelf scan kinds` prints each kept file that a rule claims, with the rule name and the kind. Matching rules are in [Matching](../concepts/matching.md).

Rules run in list order. The first rule that matches wins. Put specific rules first and a catch-all last.

=== "TOML"

    ```toml title="profile.books.toml"
    [[inputs]]
    path = "inbox"

    [[match_rules]]
    name = "bank2000_statement"
    kind = "invoice"
    filename_regex = 'REL_(?P<date>\d{8})_(?P<receipt_id>\w{8})\.pdf'

    [[match_rules]]
    name = "bank2000_card"
    kind = "invoice"
    directory_glob = "Bank2000/card"

    [[match_rules]]
    name = "unsorted"
    glob = "**"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    inputs:
      - path: inbox

    match_rules:
      - name: bank2000_statement
        kind: invoice
        filename_regex: 'REL_(?P<date>\d{8})_(?P<receipt_id>\w{8})\.pdf'

      - name: bank2000_card
        kind: invoice
        directory_glob: Bank2000/card

      - name: unsorted
        glob: "**"
    ```

`filename_regex` is compared with the filename only, and it must match the whole name, including `.pdf`. `directory_glob` is compared with the directory under the input. For `inbox/Bank2000/card/CARD_1234_20211231.pdf` that directory is `Bank2000/card`. A file sitting directly in `inbox` has an empty directory, so a directory pattern does not claim it.

`glob = "**"` claims every remaining kept file. `kind` is omitted, so the kind is the rule name, `unsorted`.

```bash
supershelf scan kinds
```

Example:

```text
profile  input  path                                         kind     rule
books    1      Bank2000/REL_20260425_ab12cd34.pdf           invoice  bank2000_statement
books    1      Bank2000/card/CARD_1234_20211231.pdf         invoice  bank2000_card
books    1      notes/readme.txt                             unsorted unsorted
```

A kept file that no rule claims is absent from this table. The command warns once for that file and still exits successfully. `scan files` still lists it.

Two rules may share a kind. Rule names in one profile must be unique.

The next page shows the patterns behind one of those rows: [See why it matched](see-why-it-matched.md).
