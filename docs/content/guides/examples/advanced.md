# Advanced

Same inbox as [Base](base.md). These profiles set the document date, a value taken from the filename, and one kind-file row.

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

The institution names are stand-ins: Bank2000, Northline Telecom, Metro Phone, Civic Tax, and Signal Mobile.

## Document date

`__date__` is a calendar date `YYYY-MM-DD`. A rule that captures `date` parses that string with `regex_time_var`. The format is the one used in that filename. The commands are in [Template commands](../../concepts/template-commands.md).

Northline Telecom stores `08292025`, read with `%m%d%Y`, which is `2025-08-29`. The Bank2000 account statement stores `033123`, read with `%m%d%y`, which is `2023-03-31`. Bank2000 card, Metro Phone, and Signal Mobile already write `YYYY-MM-DD`. Civic Tax filenames have no date. `default_vars` tries the PDF creation date, then the PDF modification date.

=== "TOML"

    ```toml title="profile.books.toml"
    [[inputs]]
    path = "inbox"
    include = ["**/*.pdf"]

    [default_vars]
    __date__ = [
      '{{ meta("pdf", "creation_date") }}',
      '{{ meta("pdf", "modification_date") }}',
    ]

    [[match_rules]]
    name = "northline"
    kind = "invoice"
    filename_regex = 'INV\d+_TR\d+_(?P<date>\d{8})\.pdf'

    [match_rules.vars]
    __date__ = [
      '{{ regex_time_var(date, "%m%d%Y") }}',
      '{{ __date__ }}',
    ]

    [[match_rules]]
    name = "bank2000_account"
    kind = "invoice"
    filename_regex = 'REL_ACCTSTMT_\d+_(?P<date>\d{6})-[0-9a-f]+\.pdf'

    [match_rules.vars]
    __date__ = [
      '{{ regex_time_var(date, "%m%d%y") }}',
      '{{ __date__ }}',
    ]

    [[match_rules]]
    name = "bank2000_card"
    kind = "invoice"
    filename_regex = 'CARD_CREDCARD_\d+_(?P<date>\d{4}-\d{2}-\d{2})-[0-9a-f]+\.pdf'

    [match_rules.vars]
    __date__ = [
      '{{ regex_time_var(date, "%Y-%m-%d") }}',
      '{{ __date__ }}',
    ]

    [[match_rules]]
    name = "metro_phone"
    kind = "invoice"
    filename_regex = '(?P<date>\d{4}-\d{2}-\d{2}) (?P<amount>\d+\.\d+)\.pdf'

    [match_rules.vars]
    __date__ = [
      '{{ regex_time_var(date, "%Y-%m-%d") }}',
      '{{ __date__ }}',
    ]

    [[match_rules]]
    name = "signal_mobile"
    kind = "invoice"
    filename_regex = '(?P<date>\d{4}-\d{2}-\d{2})\.pdf'

    [match_rules.vars]
    __date__ = [
      '{{ regex_time_var(date, "%Y-%m-%d") }}',
      '{{ __date__ }}',
    ]

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

    default_vars:
      __date__:
        - '{{ meta("pdf", "creation_date") }}'
        - '{{ meta("pdf", "modification_date") }}'

    match_rules:
      - name: northline
        kind: invoice
        filename_regex: 'INV\d+_TR\d+_(?P<date>\d{8})\.pdf'
        vars:
          __date__:
            - '{{ regex_time_var(date, "%m%d%Y") }}'
            - '{{ __date__ }}'

      - name: bank2000_account
        kind: invoice
        filename_regex: 'REL_ACCTSTMT_\d+_(?P<date>\d{6})-[0-9a-f]+\.pdf'
        vars:
          __date__:
            - '{{ regex_time_var(date, "%m%d%y") }}'
            - '{{ __date__ }}'

      - name: bank2000_card
        kind: invoice
        filename_regex: 'CARD_CREDCARD_\d+_(?P<date>\d{4}-\d{2}-\d{2})-[0-9a-f]+\.pdf'
        vars:
          __date__:
            - '{{ regex_time_var(date, "%Y-%m-%d") }}'
            - '{{ __date__ }}'

      - name: metro_phone
        kind: invoice
        filename_regex: '(?P<date>\d{4}-\d{2}-\d{2}) (?P<amount>\d+\.\d+)\.pdf'
        vars:
          __date__:
            - '{{ regex_time_var(date, "%Y-%m-%d") }}'
            - '{{ __date__ }}'

      - name: signal_mobile
        kind: invoice
        filename_regex: '(?P<date>\d{4}-\d{2}-\d{2})\.pdf'
        vars:
          __date__:
            - '{{ regex_time_var(date, "%Y-%m-%d") }}'
            - '{{ __date__ }}'

      - name: civic_tax
        kind: invoice
        directory_glob: home/civic_tax
    ```

On a rule that captured `date`, the first candidate parses that group. `{{ __date__ }}` keeps the value `default_vars` already stored. Civic Tax has no capture, so its date comes from the PDF. A PDF with neither date leaves `__date__` unset.

## A value from the name

Metro Phone captures `amount`. The rule stores that number and sets the vendor. `amount` is a float, and it must be zero or greater.

Northline Telecom is matched by its filename. The override sets `__date__` on that one file. Quote it. The value is already `YYYY-MM-DD`.

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

    [vars_schema.amount]
    type = "float"

    [vars_schema.amount.validation]
    ge = 0

    [[match_rules]]
    name = "northline"
    kind = "invoice"
    filename_regex = 'INV\d+_TR\d+_\d{8}\.pdf'

    [[match_rules]]
    name = "metro_phone"
    kind = "invoice"
    filename_regex = '(?P<date>\d{4}-\d{2}-\d{2}) (?P<amount>\d+\.\d+)\.pdf'

    [match_rules.vars]
    vendor = "Metro Phone"
    amount = ["{{ amount }}"]
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    inputs:
      - path: inbox
        include:
          - "**/*.pdf"

    vars_schema:
      amount:
        type: float
        validation:
          ge: 0

    match_rules:
      - name: northline
        kind: invoice
        filename_regex: 'INV\d+_TR\d+_\d{8}\.pdf'

      - name: metro_phone
        kind: invoice
        filename_regex: '(?P<date>\d{4}-\d{2}-\d{2}) (?P<amount>\d+\.\d+)\.pdf'
        vars:
          vendor: Metro Phone
          amount:
            - "{{ amount }}"
    ```

`{{ amount }}` reads the group from the Metro Phone filename, `64.33`.

## A value stored for one path

For profile `books` and kind `invoice`, the first default kind file is `profile.books.invoice.csv` under the profile root. This row sets the Bank2000 account statement. `31/03/2023` is read with `kind_overrides_date_format` and stored as `2023-03-31`.

```text
inbox/
  company/
    bank2000_account/
      REL_ACCTSTMT_100200300400_033123-ab12cd34.pdf
```

=== "TOML"

    ```toml title="profile.books.toml"
    [config]
    kind_overrides_sep = ";"
    kind_overrides_date_format = "%d/%m/%Y"

    [[inputs]]
    path = "inbox"
    include = ["**/*.pdf"]

    [[match_rules]]
    name = "bank2000_account"
    kind = "invoice"
    directory_glob = "company/bank2000_account"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    config:
      kind_overrides_sep: ";"
      kind_overrides_date_format: "%d/%m/%Y"

    inputs:
      - path: inbox
        include:
          - "**/*.pdf"

    match_rules:
      - name: bank2000_account
        kind: invoice
        directory_glob: company/bank2000_account
    ```

```csv title="profile.books.invoice.csv"
PATH;__date__;vendor
company/bank2000_account/REL_ACCTSTMT_100200300400_033123-ab12cd34.pdf;31/03/2023;Bank2000
```

The default mode is `auto`. An invoice path that is missing from the file is appended. The modes are in [Kind files](../../concepts/kind-files.md).

The same mechanisms, without the walkthrough, are in [Concepts](../../concepts/index.md).
