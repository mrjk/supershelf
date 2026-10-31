# Override one file

`overrides` is the last assignment layer. The first item whose `path` matches the file wins. Later items are not merged. See [Variables](../concepts/variables.md).

`path` is a glob, matched against the whole path relative to the input. `*` stays in one directory. `**` crosses directories. A path with no glob characters is an exact match.

=== "TOML"

    ```toml title="profile.books.toml"
    [[overrides]]
    path = "Bank2000/card/CARD_1234_20211231.pdf"

    [overrides.vars]
    __kind__ = "card_statement"
    __date__ = "2021-12-31"
    vendor = "Bank2000"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    overrides:
      - path: Bank2000/card/CARD_1234_20211231.pdf
        vars:
          __kind__: card_statement
          __date__: "2021-12-31"
          vendor: Bank2000
    ```

Quote `__date__`. The value must already be `YYYY-MM-DD`. This layer does not parse another date format.

This is the only layer that may set `__kind__`. The printed kind becomes `card_statement`. The rule name stays the name of the rule that matched. The kind file, if any, was already chosen from the rule kind, so this change does not load a different kind file. See [Kind files](../concepts/kind-files.md).

An item that matches nothing is fine. An item needs both `path` and `vars`. An empty `vars` mapping changes nothing.

The next page sets values for every file of one kind: [Share variables for a kind](share-variables-for-a-kind.md).
