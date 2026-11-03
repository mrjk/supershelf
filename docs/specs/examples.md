# Examples

Config a user would write. The rules are indexed in [README.md](README.md). This file has no section numbers.

The profile below sets every user key. `var_modules`, `output_modules`, and a custom metadata module stay commented: a missing import stops the command. `extension_remap` and `overrides` are not profile keys.

## Profile

```yaml
# Profile configuration
# =====================
config:
  profile: default # Can be overriden if profile is not set in filename.
  default_date_format: '%Y-%m-%d' # Shows mtime and ctime in scan files. Not templated.
  kind_overrides_mode: auto # 2.3.2. auto appends when the file exists. manual only reads. always creates and appends. disabled ignores kind files.
  kind_overrides_date_format: '%d/%m/%Y' # Optional. Kind-file __date__ cells. Omitted uses default_date_format. Stored as YYYY-MM-DD.
  kind_overrides_sep: ';' # Optional. Kind-file CSV separator. Omitted uses a comma. YAML and TOML ignore it.
  root_dir: "{{ __profile__.dir }}" # Default. Directory of the config file.

  # Default paths
  database_file: "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.sqlite" # 4. record run creates this when a row would change. A meta() miss does not. --dry-run does not. scan files and scan kinds do not.
  cache_file: "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.cache" # 2.3.3. JSON metadata cache. scan vars, record run, data feed, and data show create it when meta() misses. --dry-run does not.
  record_identity: path # 4.2. Bare path means path then hash. Bare hash means hash then path. A list does not expand. Omitted uses path.
  # var_modules: # Optional importable modules. GLOBALS and FILTERS. See 2.3.1.
  #   - my_package.supershelf_vars
  # output_modules: # Optional importable modules. DRIVERS. See architecture 4. Not metadata_driver.
  #   - my_package.supershelf_outputs
  kind_overrides_config: # Omitted uses this list. First existing file wins. Per-file rows. Cached by input and kind, and by path.
    - "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.csv"
    - "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.toml"
    - "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.yaml"
    - "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.yml"

  # Settings that can differ per input
  # root_dir: /srv/data_processing/
  # database_file: "{{ __config__.root_dir }}/state.sqlite"
  # kind_overrides_config: # Same resolution. __input__.path keeps each input in its own kind file.
  #   - "{{ __input__.path }}/data/{{ __match__.kind }}.csv"
  #   - "{{ __input__.path }}/data/{{ __match__.kind }}.toml"
  #   - "{{ __input__.path }}/data/{{ __match__.kind }}.yaml"
  #   - "{{ __input__.path }}/data/{{ __match__.kind }}.yml"
  #   - "{{ __config__.root_dir }}/data/{{ __match__.kind }}.csv"
  #   - "{{ __config__.root_dir }}/data/{{ __match__.kind }}.toml"
  #   - "{{ __config__.root_dir }}/data/{{ __match__.kind }}.yaml"
  #   - "{{ __config__.root_dir }}/data/{{ __match__.kind }}.yml"


# Source of files
# =====================
inputs:
  # Path to scan, with include and exclude. Generate a list of files paths (relative to path), with hashs, ctime, mtime.
  # All the matched files will be tested against match_rules.
  - path: /.../input1
    include:
      - '*.jpg'
      - '*.jpeg'
    exclude:
      - '**/cache/**'
    depth: 0 # 0 is unlimited. 1 is the input directory only.
    follow_symlinks: true # Packaged default. false skips symlinks.

  # No include means every file. depth 1 is this directory only.
  - path: /.../input2
    exclude:
      - '**/tmp/**'
    depth: 1
    follow_symlinks: false


# Variable types. Architecture 1.1.
# A name listed here without default keeps the default_vars value as its default.
# The same name in both places is a config error.
# doc_type is not listed, so its default_vars template is the whole default.
# internal is omitted. true on a name supershelf does not manage is a config error.
# On __date__, type and internal stay fixed. desc, unit, mandatory, and validation may be set.
# Do not set default on __date__ here: default_vars already owns that slot.
vars_schema:
  vendor:
    type: text
    desc: Who issued the document
    mandatory: false
    validation:
      min_length: 1
      max_length: 80
  owner:
    type: text
    desc: Account holder
  amount:
    type: float
    unit: EUR
    validation:
      ge: 0
      le: 1000000
  pages:
    type: int
    desc: Page count
    validation:
      gt: 0
      lt: 10000
  currency:
    type: text
    validation:
      allowed: [EUR, USD]
      pattern: '[A-Z]{3}'
  paid:
    type: bool
    validation:
      allowed: [true, false]
  issued:
    type: date
    validation:
      ge: "2020-01-01"
      lt: "2030-01-01"
  issued_at:
    type: datetime
    validation:
      ge: "2020-01-01T00:00"
      le: "2030-12-31T23:59:59"
  opens:
    type: time
    validation:
      gt: "08:00"
      lt: "18:00:00"
  doc_code:
    type: text
    default: DRAFT
  company_name:
    type: text
    desc: Payer
  employee_name:
    type: text
  __date__:
    desc: Document date
    unit: day
    mandatory: false
    validation:
      ge: "2000-01-01"

# Architecture 1.9. Optional. A kind with no entry keeps the profile catalog.
# A string names a vars_schema entry. Null or "" uses the local name.
# An object may set schema, desc, unit, mandatory, default, and validation.
# type and internal stay on the referenced spec.
# default is not copied from the profile. It applies only to files of this kind.
# A present validation mapping replaces the referenced one. It is not merged.
kind_schema:
  invoice:
    desc: A vendor bill
    vars_schema:
      vendor: vendor
      owner: ""
      amount:
      paid:
        schema: paid
        mandatory: false
      __date__:
  payslip:
    desc: A payroll slip
    vars_schema:
      company: company_name
      employee:
        schema: employee_name
        desc: Person paid
        unit: person
        mandatory: true
        default: UNKNOWN
        validation:
          min_length: 1
          max_length: 120

# Lowest assignment layer. Specified in 2.3.1.
default_vars:
  vendor: UNKNOWN
  date: UNKNOWN
  doc_type: '{{ __match__.kind }}'

  # Fallback list. The first candidate that renders wins.
  # regex_time_var reads the group date, not this list.
  __date__:
    - '{{regex_time_var(date, "%Y%m%d")}}'
    - '{{ meta("pdf", "creation_date") }}'
    - '{{ meta("pdf", "modification_date") }}'

# 2.3.3. Top-level, next to default_vars. Not under config.
# Omitted, null, and {} keep the builtin defaults. A present key overlays that name.
# pdf ignores enable. A timeout key on pdf is a config error.
# enable is auto, true, or false. false never calls the driver. Omitted timeout is 30.
# ext and mime replace the class lists. A string is one item. Omitted keeps the class list.
# driver: supershelf.meta_driver is a generic command. command and output_format are required.
# A bare command is looked up on PATH. A path is resolved from the profile directory.
# arguments omitted means no extra argv. A string is split with shlex. A list is used as written.
# Placeholders are %p %r %n %s %e %h %c %m %d and %%. output_format is yaml, toml, ini, or shell.
metadata_driver:
  pdf:
    ext: pdf
    mime: application/pdf
  exiftool:
    enable: auto
    timeout: 30
  pdftotext:
    enable: false
    timeout: 20
    ext:
      - pdf
    mime: application/pdf
  covers:
    driver: supershelf.meta_driver
    enable: auto
    timeout: 15
    ext: pdf
    command: echo
    arguments:
      - "%p"
      - "%%"
    output_format: yaml
  # Custom module. Imported at load. pkg.mod uses DRIVER. pkg.mod:ClassName takes no arguments.
  # Keys other than driver, enable, timeout, ext, and mime are options.
  # tags:
  #   driver: my_package.supershelf_meta:TagDriver
  #   enable: true
  #   timeout: 10
  #   label: sample


# Match rules. Tried in list order. The first rule that matches wins.
# Inside a rule, the first matching field wins. Order is regex, directory_regex,
# filename_regex, then glob, directory_glob, filename_glob.
match_rules:

  - name: rule1
    kind: invoice

    # A field is one pattern or a list. The first pattern that matches the whole candidate wins.
    # Regex is anchored to that whole candidate, so filename patterns include the extension.
    regex:
      - 'banking_(?P<account>\d{12})/REL_(?P<date>[\d]*)_(?P<receipt_id>\w{8})\.pdf'
    directory_regex:
      - 'banking_(?P<account>\d{12})'
    filename_regex:
      - 'REL_(?P<date>[\d]*)_(?P<receipt_id>\w{8})\.pdf'

    # Globs full-match the same candidates. They do not capture groups.
    glob:
      - banking*/REL*
    directory_glob:
      - banking*
    filename_glob:
      - REL*

    # 4.2. Omitted inherits config.record_identity. A list does not expand.
    record_identity: [hash, path]


    # Specified in 2.3.1. A string is one template. A list is tried in order.
    # {{account}} reads the regex group when no earlier layer set account.
    # {{__date__}} reads the __date__ string kept by the earlier layer.
    vars:
      # Simple static vars
      key1: 'val1'
      key2: 'val2'
      vendor: 'Bank2000'
      owner: 'sample'

      account:
        - '{{account}}'
      account2:
        - '{{regex_replace(account, "[0-9]{4}$", "")}}'
      account3:
        - '{{account}}-{{owner}}'
      __date__: # Try this pattern's date first, else keep the earlier __date__ string.
        - '{{regex_time_var(date, "%Y%m%d")}}'
        - '{{__date__}}'

  # Payslip files use kind_schema local names company and employee.
  - name: payroll
    kind: payslip
    filename_glob: 'PAY_*.pdf'
    vars:
      company: 'Acme'
      employee: '{{ __file__.stem }}'

  # A file that no rule claims is a warning and is omitted from the matched set.
  # This catch-all claims the rest. It must stay last.
  # kind is omitted, so the kind is the rule name.
  # A rule may instead omit name and keep kind. The name then becomes the kind.
  - name: unsorted
    glob: '**'



# 5. File driver. A second layout is a second item. extension_remap is not read.
outputs:
  - name: books
    path: "{{ __config__.root_dir }}/output/books" # Profile path template. Relative paths resolve from __config__.root_dir.
    layout: "{{ __date__.Y }}/{{ __date__.m }}/{{ vendor }}.{{ __file__.ext }}" # Jinja. Omitted layout is {{ __file__.path }}.
    operation: copy # copy, symlink, or hardlink. Omitted is copy.
    on_conflict: error # error, skip, or overwrite. A file this profile did not write.
    kinds:
      - invoice
    when: '{{ paid == "true" }}' # Boolean string true or false. Omitted is true.

  # driver omitted above is file. layout omitted is {{ __file__.path }}.
  # operation is copy, symlink, or hardlink. on_conflict is error, skip, or overwrite.
  - name: cards
    driver: file
    path: "{{ __config__.root_dir }}/output/cards"
    layout: "{{ __file__.path }}"
    operation: symlink
    on_conflict: skip
    kinds:
      - payslip
    when: '{{ __match__.kind == "payslip" }}'
```

## Kind files

2.3.2. Not part of the profile above. Same two rows in each format. `.yml` is the yaml text. The profile example sets `kind_overrides_sep` to `;`. Omitted, the separator is a comma. `__date__` is written with `kind_overrides_date_format` (`%d/%m/%Y`). Stored values are `2026-04-25` and `2026-01-15`. An empty cell is absent.

`invoice` lists local names, so a new CSV header is `PATH;SHA` plus those names in kind_schema order: `vendor`, `owner`, `amount`, `paid`, `__date__`. The file below already has columns. Missing schema names are appended on the right. Columns the schema does not name stay.

`payslip` lists `company` and `employee` only. `__date__` is not in that entry, so a new CSV header is `PATH;SHA;company;employee`.

`unsorted` has no `kind_schema` entry, so a new CSV uses the declared `vars_schema` names, including `__date__`.

`profile.default.invoice.csv`

```csv
PATH;SHA;__date__;vendor;owner
banking_1/REL_20260425.pdf;aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;25/04/2026;Bank2000;
Bank2000/card/CARD_1234_20211231.pdf;bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb;15/01/2026;;sample
```

`profile.default.invoice.toml`

```toml
[[rows]]
path = "banking_1/REL_20260425.pdf"
sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

[rows.vars]
vendor = "Bank2000"
__date__ = "25/04/2026"

[[rows]]
path = "Bank2000/card/CARD_1234_20211231.pdf"
sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

[rows.vars]
__date__ = "15/01/2026"
owner = "sample"
```

`profile.default.invoice.yaml`

```yaml
- path: banking_1/REL_20260425.pdf
  sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  vars:
    vendor: Bank2000
    __date__: "25/04/2026"

- path: Bank2000/card/CARD_1234_20211231.pdf
  sha: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  vars:
    __date__: "15/01/2026"
    owner: sample
```

`profile.default.payslip.csv`

Local names from `kind_schema`. `company` is `company_name`. `employee` is `employee_name`. TOML and YAML use the same row shape as the invoice files, with these keys under `vars`.

```csv
PATH;SHA;company;employee
payroll/PAY_ada.pdf;cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc;Acme;Ada
```
