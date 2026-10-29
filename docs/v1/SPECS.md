# Barbu Accounting Specs

## Overview

The user drops documents from other sources (bank, receipts, and so on) into import directories. The CLI records those files, applies import rules, and stores the result in its data directory. Later it will place links or copies in an organised tree. This step records files and rule results only. It does not organise that tree.

- The user works in the import directories.
- `db_dir` is the application data directory, on the model of `/var/lib/barbu_accounting/`. The user does not manage it by hand.
- Import directories are left unchanged, except for a source whose `mode` is `move`. `move` may relocate an import file. `symlink`, `rsymlink`, and `copy` leave it in place. `rsymlink` means a relative symlink. Those modes are applied when the tree step exists, not in this step.

Command behavior for this step is in [STEP1_import.md](STEP1_import.md). Coding rules are in [RULES.md](RULES.md).

## Data directory

`db_dir` in the YAML holds:

```text
db_dir/
  barbu.sqlite
  trees/
```

This step creates `db_dir`, `barbu.sqlite`, and an empty `trees/`. No documents are written under `trees/`.

## Configuration (YAML)

- File name: `barbu_accounting.yml`
- Location: current directory, or the path given by `--config`
- Paths inside the file (`db_dir`, each source `dir`) are relative to the directory that contains the config file
- Precedence is defined in [RULES.md](RULES.md): CLI, then environment, then YAML, then defaults

```yaml
importer:
  db_dir: ../accounting_db
  import_sources:
    download_dir:
      dir: path/to/downloads
      depth: 0
      mode: rsymlink   # symlink | rsymlink (default) | move | copy
      import_rules: [] # optional, prepended to the global import_rules
    network_share:
      dir: path/to/share
      depth: 3
      mode: rsymlink

import_rules: # first match wins, after any source-specific rules
  - name: PROVIDER_TYPE
    driver: barbu_accounting.import_driver.default
    patterns:
      - type: regex
        expr: invoice
      - type: glob
        expr: "*.pdf"
    vars:
      provider: OVH
      type: facture
    extract:
      invoice_id:
        source: file_name
        regex: "(INV-\\d+)"
  - name: PROVIDER2
    driver: barbu_accounting.import_driver.custom1
```

`depth` is how many directory levels below the source root are included. `0` is the source root only. A file in `root/a/b` is depth 2 and is included when `depth` is at least 2.

Source `import_rules` are prepended to the global `import_rules`. The first matching rule wins.

`patterns` match `file_name`. Each entry sets `type` to `regex` or `glob`. Omitted or empty `patterns` match every file.

`extract` is a mapping. The key is the variable name. Each value has `source` (`file_name` or `dir_path`) and `regex`. When the regex has a capture group, the value is group 1. Otherwise it is the whole match. A regex that does not match omits that variable, and the rule still applies. `vars` are literal strings in this step.

## Reading a source

For each regular file that is kept:

- `source` is the import source name from the config
- `dir_path` is relative to the source root, with `/` separators. A file in the root stores an empty `dir_path`
- `file_name` is the basename (`archive.tar.gz`)
- `file_ext` is the text after the first dot, with no leading or trailing dot. `archive.tar.gz` stores `tar.gz`. `file.pdf` stores `pdf`. A name with no dot, or nothing after the dot, stores an empty string. `.gitignore` stores `gitignore`
- `file_sha256` is the SHA-256 of the file bytes

Skip, and do not record:

- directories (entered only while `depth` allows)
- symlinks (not followed)
- unreadable files (logged, then skipped)
- empty files
- the config file and `barbu.sqlite`, when either path sits inside a source

## Database (SQLite)

File: `<db_dir>/barbu.sqlite`. Rows are never deleted.

`file_sources`:

- `id`: integer primary key
- `file_sha256`: indexed, not a SQL unique constraint
- `file_name`
- `file_ext`
- `dir_path`
- `source`
- `state`: `present` or `missing`
- `modified`: UTC ISO-8601, set when the row changes
- `created`: UTC ISO-8601, set once

`metadata`:

- `id`: integer primary key
- `file_id`: foreign key to `file_sources.id`, one metadata row per file
- `driver`: Python module name
- `vars`: JSON object as text
- `modified`: UTC ISO-8601, set when the row changes
- `created`: UTC ISO-8601, set once

On the success path there is one `file_sources` row per hash. The unique constraint is omitted so a duplicate can be reported in full before any write.

Stored `state` is `present` or `missing`. `absent` is not stored: it is a live file whose hash has no row yet.

## Document identity

A row is one document, identified by its hash.

- The same hash on two or more live files, in the sources being scanned, is a duplicate. The command lists every copy (`file_sha256`, `source`, `dir_path`, `file_name`) and writes nothing. Names excluded by `--files` still count.
- One live file with a hash that already has a row: the row stays `present`. If that file moved, update `source`, `dir_path`, `file_name`, and `file_ext`.
- A live hash with no row is `absent` until it is inserted, then `present`.
- A row whose hash is not on disk in the scanned sources becomes `missing`. The row and its last path stay.

When the file is still on disk and the bytes changed, that is two documents:

- The old hash is no longer on disk, so its row becomes `missing`. Its path stays the last place that content was seen.
- The new hash has no row, so the live file is `absent` until insert, which adds a new `present` row at the current path.
- If the new hash is already on another live file, the duplicate report runs and nothing is written.

A rename of the same bytes is one live hash. The existing row stays `present` and its location fields are updated.

A `--files` filter does not mark a skipped document `missing`. Cleanup applies only to sources included in the command. Inserts and location updates apply only to live files selected by `--files`. A row left out by `--files` is not modified.

## Import drivers (Python)

A driver is a Python class in an importable module. It receives the `file_sources` fields for one file and returns a dict of variables.

The default driver is `barbu_accounting.import_driver.default`. It implements `patterns`, `extract`, and `vars` as specified above. The returned dict is `vars` plus any extracted keys. Extracted keys override the same name in `vars`.

The minimum rule is a name, a driver, and optional literal `vars`. Other drivers may be named by module path. Only the default driver is part of this step.
