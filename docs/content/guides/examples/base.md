# Base

These profiles classify one inbox. Copy the profile closest to your folders.

The institution names are stand-ins: Bank2000, Northline Telecom, Metro Phone, Civic Tax, and Signal Mobile.

## The inbox

```text
inbox/
  company/
    bank2000_account/
      REL_ACCTSTMT_100200300400_033123-ab12cd34.pdf
    bank2000_card/
      CARD_CREDCARD_1234_2023-11-15-ab12cd34.pdf
  home/
    northline/
      INV00000001_TR00000001_08292025.pdf
    metro_phone/
      2022-08-27 64.33.pdf
    civic_tax/
      Invoice 52.pdf
    signal_mobile/
      2025-05-18.pdf
```

`inbox` is the input. A path in a rule is relative to that directory. Rules run in list order. The first rule that matches wins. Matching rules are in [Matching](../../concepts/matching.md).

`include` keeps PDF files. Each profile below is complete.

## One folder, one kind

Signal Mobile and Civic Tax each have their own folder. One filename is only a date. The other has no shared pattern. `directory_glob` is that folder.

```text
inbox/
  home/
    civic_tax/
      Invoice 52.pdf
    signal_mobile/
      2025-05-18.pdf
```

=== "TOML"

    ```toml title="profile.books.toml"
    [[inputs]]
    path = "inbox"
    include = ["**/*.pdf"]

    [[match_rules]]
    name = "signal_mobile"
    kind = "invoice"
    directory_glob = "home/signal_mobile"

    [[match_rules]]
    name = "civic_tax"
    kind = "invoice"
    directory_glob = "home/civic_tax"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    inputs:
      - path: inbox
        include:
          - "**/*.pdf"

    match_rules:
      - name: signal_mobile
        kind: invoice
        directory_glob: home/signal_mobile

      - name: civic_tax
        kind: invoice
        directory_glob: home/civic_tax
    ```

A file in `home/signal_mobile` is `signal_mobile`. `Invoice 52.pdf` is `civic_tax`. Both kinds are `invoice`.

## A specific folder, then a wider one

The Bank2000 card folder and the Bank2000 account folder share the prefix `company/bank2000_`. The card rule is the exact directory. The account rule matches every remaining directory at that level.

```text
inbox/
  company/
    bank2000_account/
      REL_ACCTSTMT_100200300400_033123-ab12cd34.pdf
    bank2000_card/
      CARD_CREDCARD_1234_2023-11-15-ab12cd34.pdf
```

=== "TOML"

    ```toml title="profile.books.toml"
    [[inputs]]
    path = "inbox"
    include = ["**/*.pdf"]

    [[match_rules]]
    name = "bank2000_card"
    kind = "invoice"
    directory_glob = "company/bank2000_card"

    [[match_rules]]
    name = "bank2000_account"
    kind = "invoice"
    directory_glob = "company/bank2000_*"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    inputs:
      - path: inbox
        include:
          - "**/*.pdf"

    match_rules:
      - name: bank2000_card
        kind: invoice
        directory_glob: company/bank2000_card

      - name: bank2000_account
        kind: invoice
        directory_glob: "company/bank2000_*"
    ```

`*` stays in one directory level. `company/bank2000_*` matches `company/bank2000_card` and `company/bank2000_account`. The card rule is first, so the card file is `bank2000_card`.

## The filename is the kind

Northline Telecom invoices look like `INV00000001_TR00000001_08292025.pdf`. Metro Phone bills look like `2022-08-27 64.33.pdf`. `filename_regex` full-matches the filename, including `.pdf`. The folder is not part of the match.

```text
inbox/
  home/
    northline/
      INV00000001_TR00000001_08292025.pdf
    metro_phone/
      2022-08-27 64.33.pdf
```

=== "TOML"

    ```toml title="profile.books.toml"
    [[inputs]]
    path = "inbox"
    include = ["**/*.pdf"]

    [[match_rules]]
    name = "northline"
    kind = "invoice"
    filename_regex = 'INV\d+_TR\d+_\d{8}\.pdf'

    [[match_rules]]
    name = "metro_phone"
    kind = "invoice"
    filename_regex = '(?P<date>\d{4}-\d{2}-\d{2}) (?P<amount>\d+\.\d+)\.pdf'
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    inputs:
      - path: inbox
        include:
          - "**/*.pdf"

    match_rules:
      - name: northline
        kind: invoice
        filename_regex: 'INV\d+_TR\d+_\d{8}\.pdf'

      - name: metro_phone
        kind: invoice
        filename_regex: '(?P<date>\d{4}-\d{2}-\d{2}) (?P<amount>\d+\.\d+)\.pdf'
    ```

The Metro Phone pattern keeps the groups `date` and `amount`. The next page reads them.

## The whole inbox

This profile is the rules above, in the same order, plus a catch-all. `glob = "**"` claims every kept file the earlier rules left.

=== "TOML"

    ```toml title="profile.books.toml"
    [[inputs]]
    path = "inbox"
    include = ["**/*.pdf"]

    [[match_rules]]
    name = "signal_mobile"
    kind = "invoice"
    directory_glob = "home/signal_mobile"

    [[match_rules]]
    name = "civic_tax"
    kind = "invoice"
    directory_glob = "home/civic_tax"

    [[match_rules]]
    name = "bank2000_card"
    kind = "invoice"
    directory_glob = "company/bank2000_card"

    [[match_rules]]
    name = "bank2000_account"
    kind = "invoice"
    directory_glob = "company/bank2000_*"

    [[match_rules]]
    name = "northline"
    kind = "invoice"
    filename_regex = 'INV\d+_TR\d+_\d{8}\.pdf'

    [[match_rules]]
    name = "metro_phone"
    kind = "invoice"
    filename_regex = '(?P<date>\d{4}-\d{2}-\d{2}) (?P<amount>\d+\.\d+)\.pdf'

    [[match_rules]]
    name = "unsorted"
    glob = "**"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    inputs:
      - path: inbox
        include:
          - "**/*.pdf"

    match_rules:
      - name: signal_mobile
        kind: invoice
        directory_glob: home/signal_mobile

      - name: civic_tax
        kind: invoice
        directory_glob: home/civic_tax

      - name: bank2000_card
        kind: invoice
        directory_glob: company/bank2000_card

      - name: bank2000_account
        kind: invoice
        directory_glob: "company/bank2000_*"

      - name: northline
        kind: invoice
        filename_regex: 'INV\d+_TR\d+_\d{8}\.pdf'

      - name: metro_phone
        kind: invoice
        filename_regex: '(?P<date>\d{4}-\d{2}-\d{2}) (?P<amount>\d+\.\d+)\.pdf'

      - name: unsorted
        glob: "**"
    ```

`kind` is omitted on `unsorted`, so the kind is the rule name. The card rule stays ahead of `company/bank2000_*`.

The next page reads dates and other values from these files: [Advanced](advanced.md).
