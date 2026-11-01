# Examples

Config a user would write. The rules are in [behavior.md](behavior.md) and [architecture.md](architecture.md). This file has no section numbers.

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
  root_dir: "{{ __profile_dir__ }}" # Default. Full directory of the config file.

  # Default paths
  database_file: "{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite" # 4. record run creates this when a row would change. scan vars and record run also create it when meta() misses the cache. --dry-run does not. scan files and scan kinds do not.
  cache_file: "{{ __root_dir__ }}/profile.{{ __profile__ }}.cache" # Rendered. Nothing writes it.
  record_identity: path # 4.2. Bare path means path then hash. Bare hash means hash then path. A list does not expand. Omitted uses path.
  # var_modules: # Optional importable modules. GLOBALS and FILTERS. See 2.3.1.
  #   - my_package.supershelf_vars
  kind_overrides_config: # Omitted uses this list. First existing file wins. Per-file rows. Cached by input and kind, and by path.
    - "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.csv"
    - "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.toml"
    - "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yaml"
    - "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yml"

  # Settings that can differ per input
  # root_dir: /srv/data_processing/
  # database_file: "{{ __root_dir__ }}/state.sqlite"
  # kind_overrides_config: # Same resolution. __input__.path keeps each input in its own kind file.
  #   - "{{ __input__.path }}/data/{{ __kind__ }}.csv"
  #   - "{{ __input__.path }}/data/{{ __kind__ }}.toml"
  #   - "{{ __input__.path }}/data/{{ __kind__ }}.yaml"
  #   - "{{ __input__.path }}/data/{{ __kind__ }}.yml"
  #   - "{{ __root_dir__ }}/data/{{ __kind__ }}.csv"
  #   - "{{ __root_dir__ }}/data/{{ __kind__ }}.toml"
  #   - "{{ __root_dir__ }}/data/{{ __kind__ }}.yaml"
  #   - "{{ __root_dir__ }}/data/{{ __kind__ }}.yml"


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
    # follow_symlinks: true # Default. Set false to skip symlinks.


# Correctly rename destination extensions
#extension_remap:
#  jpg: jpeg
#  tif: tiff
#  yml: yaml

# Variable types. See docs/content/concepts/variables.md and architecture 1.1.
# A name listed here without default keeps the default_vars value as its default.
# doc_type is not listed, so its default_vars template is the whole default.
vars_schema:
  vendor:
    type: text
    desc: Who issued the document
  amount:
    type: float
    unit: EUR
    validation:
      ge: 0
  paid:
    type: bool
  issued:
    type: date
  issued_at:
    type: datetime
  opens:
    type: time

# Lowest assignment layer. Specified in 2.3.1.
default_vars:
  vendor: UNKNOWN
  date: UNKNOWN
  doc_type: '{{ __kind__ }}'

  # Fallback list. The first candidate that renders wins.
  # regex_time_var reads the group date, not this list.
  __date__:
    - '{{regex_time_var(date, "%Y%m%d")}}'
    - '{{pdf_cdate()}}'
    - '{{pdf_mdate()}}'
    - '{{file("ctime")}}'
    - '{{file("mtime")}}'


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

    # 4.2. Omitted inherits config.record_identity. A list is the fallback order.
    # record_identity: [hash, path]


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

  # A file that no rule claims is a warning and is omitted from the matched set.
  # This catch-all claims the rest. It must stay last.
  # kind is omitted, so the kind is the rule name.
  - name: unsorted
    glob: '**'



outputs:
  - name: books
    path: /.../output/books
    directory_layout: "{yyyy}/{mm}/{payer}"
    filename_layout: "{yyyy}-{mm}-{dd}_{vendor}"
    mode: copy
    on_conflict: rename

    directory_for:
      invoice: '{yyyy}/{mm}/videos'
    filename_for:
      invoice: '{yyyy}-{mm}-{dd}_vid_{seq:05}'
```

## Kind files

2.3.2. Not part of the profile above. Same two rows in each format. `.yml` is the yaml text. The profile example sets `kind_overrides_sep` to `;`. Omitted, the separator is a comma. `__date__` is written with `kind_overrides_date_format` (`%d/%m/%Y`). Stored values are `2026-04-25` and `2026-01-15`. An empty cell is absent.

`profile.default.invoice.csv`

```csv
PATH;__date__;vendor;owner
banking_1/REL_20260425.pdf;25/04/2026;Bank2000;
Bank2000/card/CARD_1234_20211231.pdf;15/01/2026;;sample
```

`profile.default.invoice.toml`

```toml
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

`profile.default.invoice.yaml`

```yaml
- path: banking_1/REL_20260425.pdf
  vars:
    vendor: Bank2000
    __date__: "25/04/2026"

- path: Bank2000/card/CARD_1234_20211231.pdf
  vars:
    __date__: "15/01/2026"
    owner: sample
```
