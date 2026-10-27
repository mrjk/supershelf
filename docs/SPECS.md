
# Barbu Accounting Specs

## Overview

THe concept is to have documents the user can download and roughly organise in import directories, and then to import all those files, apply rules, and create an output directory under a specific hierarchy. It's like a big document sorter.

We assume:
- managed documents are never edited by the user, documents comes from other sources (bank, receipt, etc ...)
- the user is only allowed to work in the import dir
- the output dirs should be considered as read only, only the CLI is allowed to manage those files.
- the CLI never modify or delete data in the import_dirs

## Configuration (yaml)

- Configuration is made in YAML
- it is barbu_accounting.yml
- it is located in current dir, or explicitely mentionned with top level flag: --config


COnfiguration example
```
# COnfiguration for barbu-accounting CLI

importer:
  db_dir: ../accounting_db  # Output of managed directory
  import_sources:   # Default sources to lookup for import
    download_dir:
      dir: path...
      depth: 3   # Depth of dirs to scan
      mode: symlink|rsymlink(default)|move|copy
      import_rules: [] # Optional, a list of import_rules specific for this source, added first
    network_share: # another example ...


import_rules:  # Order matters, first match win. DEfault rules for all import_sources
  - name: PROVIDER[_TYPE]
    driver: barbu_accounting.import_driver.default
    patterns:
      - regex1
      - regex2
    vars:  # Custom vars, can use regex extracted patterns
      var1: val1
      var2: val2
      provider: PROVIDER|OVH|BNC|...
      type: facture|relevé|legal|...

  # Example of unimplemented yet driver
  - name: PROVIDER2
    driver: barbu_accounting.import_driver.custom1

```


## Database (sqlite)

Schema:
* file_sources:
    * id: Index, UNIQUE
    * file_sha256: UNIQUE
    * file_name:
    * file_ext:
    * dir_path:
    * source: str=CONFIG_SOURCE_NAME
    * state: enum=present|absent
    * modified: timestamp
    * created: timestamp
* metadata:
    * id: Index: UNique
    * file: Link N:1 to files
    * driver: NAME_OF_PYTHON_IMPORT_DRIVER_MODULE
    * vars: str: json string with all imported data
    * modified: timestamp
    * created: timestamp

## Import drivers (Python)

- Implemented as python code/module
- Provides a standard python API to generate vars from files.

API:
* input:
    * All informations in for a given file from the file_sources table
* output:
    * Key/Value dict:
        * Generated vars from the driver

### Default config api

This is the minimum API contract:
```
import_rules:
    - name: NAME # Name of the rule
      driver: barbu_accounting.import_driver.default # By default
      vars:
        var1: val1 # CUstom KV to attach to output
```

### Default import driver: barbu_accounting.import_driver.default

This driver add more options:

```
import_rules:
    - name: NAME # Name of the rule
      driver: barbu_accounting.import_driver.default # By default
      vars:
        var1: val1 # CUstom KV to attach to output

      # Driver options:
      patterns: # Match only the files matching the following regex/glob
        - regex1
        - regex2
        - ...
      extract: # Create vars from regex on specific fields
        - var1: file_name;regex1
        - var2: dir_path;regex2
        - var3: FIELD|REGEX
        - ...
```


