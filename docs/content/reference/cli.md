# Command line

Every command accepts `--config`, `--profile`, `--dry-run`, and `--version`, plus the log flags from the CLI library. The listings below are the program's own help text.

`--config` selects the config file or directory and overrides `SUPERSHELF_CONFIG`. `--profile` is a comma-separated list of profile names and overrides `SUPERSHELF_PROFILES`. `--dry-run` on `scan vars` reads kind files and does not create or append. On `data feed` and `data prune` it prints the summary and does not write a kind file. On `record run` it prints the rows that would change and does not create the database. `--dry-run` does not create or migrate the database. The other scan commands only print. See [Limits](../concepts/limits.md).

The help text lists `-vvvv`. This program's log tiers stop at `-vvv`. `-vvvv` is rejected.

## supershelf

<!-- extract: help -->
```text
usage: supershelf [-h] [--log-colors | --no-log-colors] [--version] [-v]
                  [--log-format {default,extended,audit,debug}]
                  [--trace | --no-trace] [--config CONFIG] [--profile PROFILE]
                  [--dry-run]
                  {profiles,schema,scan,data,record} ...

Load profiles, scan inputs, record matched files, and edit kind files.

subcommands:
  profiles                    List profile names and config paths
  schema                      Print JSON Schema for declared variables and kinds
  scan                        Scan profile inputs
    files                     List files kept by each input
    kinds                     List the kind matched for each kept file
    vars                      List variables for each matched file
    inspect                   Show how match rules test kept files
  data                        Read and write kind files
    feed                      Fill empty kind-file cells with resolved values
    prune                     Drop empty columns, unmatched rows, or every row
    show                      Print live variable values, one table per profile and kind
  record                      Record matched files and read that history
    status                    Compare matched files with the profile database
    run                       Record matched files into the profile database
    history                   Show recorded events
    duplicates                List documents that share a hash

options:
  -h, --help                  show this help message and exit
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
                              (default: None)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv) (default: 0)
  --log-format {default,extended,audit,debug}
                              Set log formatter (default: default)
  --trace, --no-trace         Enable trace logging on errors (default: False)
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG. (default: None)
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES. (default: None)
  --dry-run                   Report actions without changing anything. (default: False)
```
<!-- /extract -->

## supershelf profiles

<!-- extract: help profiles -->
```text
usage: supershelf profiles [-h] [--expand-keys | --no-expand-keys]
                           [--width {content,fit,terminal}]
                           [--columns COLUMNS] [--add-index | --no-add-index]
                           [--format {view,yaml,json,csv}]
                           [--sort-columns SORT_COLUMNS]
                           [--sort-mode {asc,desc}] [--wrap MODE|COL,...]
                           [--log-colors | --no-log-colors] [--version] [-v]
                           [--log-format {default,extended,audit,debug}]
                           [--trace | --no-trace] [--config CONFIG]
                           [--profile PROFILE] [--dry-run]

List profile names and config paths.

options:
  -h, --help                  show this help message and exit

Output options:
  --expand-keys, --no-expand-keys
                              Expand nested dict items into table columns
                              (default: None)
  --width {content,fit,terminal}
                              Table width: content (size to data), fit (shrink
                              if wider than terminal), terminal (use terminal
                              width). No wrap when stdout is not a TTY.
                              (default: None)
  --columns COLUMNS           Comma-separated columns to display (names, 1-based indexes, or negatives from end: -1=last) (default: None)
  --add-index, --no-add-index
                              Include key/index column in the table (default:
                              None)
  --format {view,yaml,json,csv}
                              Output format (default: view table) (default:
                              None)
  --sort-columns SORT_COLUMNS
                              Comma-separated columns to sort by (names,
                              1-based indexes, or negatives from end:
                              -1=last). Use --sort-columns=-1,1 when values
                              start with '-'. (default: None)
  --sort-mode {asc,desc}      Sort direction (default: asc) (default: None)
  --wrap MODE|COL,...         Flexible table columns: they expand or shrink to the terminal. last (rightmost), first (leftmost), all (any column), or comma-separated names/indexes in priority order. Use --wrap=-1 when the value starts with '-'. Ignored when width is content or stdout is not a TTY. (default: None)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf schema

Prints one JSON document for the selected profiles. The object is keyed by profile name. With `kind_schema`, each kind is an object under `$defs`. Without it, the object is the declared `vars_schema` names. Neither key stops the command. The command does not walk inputs and does not write a kind file. Column names in a new CSV come from that kind's schema. With no schema columns, they stay `PATH,__date__`.

<!-- extract: help schema -->
```text
usage: supershelf schema [-h] [--log-colors | --no-log-colors] [--version]
                         [-v] [--log-format {default,extended,audit,debug}]
                         [--trace | --no-trace] [--config CONFIG]
                         [--profile PROFILE] [--dry-run]

Print JSON Schema for declared variables and kinds.

options:
  -h, --help                  show this help message and exit

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf scan

<!-- extract: help scan -->
```text
usage: supershelf scan [-h] [--log-colors | --no-log-colors] [--version] [-v]
                       [--log-format {default,extended,audit,debug}]
                       [--trace | --no-trace] [--config CONFIG]
                       [--profile PROFILE] [--dry-run]
                       {files,kinds,vars,inspect} ...

Scan profile inputs.

subcommands:
  files                       List files kept by each input
  kinds                       List the kind matched for each kept file
  vars                        List variables for each matched file
  inspect                     Show how match rules test kept files

options:
  -h, --help                  show this help message and exit

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf scan files

<!-- extract: help scan files -->
```text
usage: supershelf scan files [-h] [--quick] [--expand-keys | --no-expand-keys]
                             [--width {content,fit,terminal}]
                             [--columns COLUMNS]
                             [--add-index | --no-add-index]
                             [--format {view,yaml,json,csv}]
                             [--sort-columns SORT_COLUMNS]
                             [--sort-mode {asc,desc}] [--wrap MODE|COL,...]
                             [--log-colors | --no-log-colors] [--version] [-v]
                             [--log-format {default,extended,audit,debug}]
                             [--trace | --no-trace] [--config CONFIG]
                             [--profile PROFILE] [--dry-run]
                             [path]

List files kept by each input.

positional arguments:
  path                        Path relative to the input, as shown in the path column. Omit for every kept file. An exact file path selects that file. Anything else selects paths that start with it. (default: None)

options:
  -h, --help                  show this help message and exit
  --quick                     Skip mtime, ctime, and sha256. (default: False)

Output options:
  --expand-keys, --no-expand-keys
                              Expand nested dict items into table columns
                              (default: None)
  --width {content,fit,terminal}
                              Table width: content (size to data), fit (shrink
                              if wider than terminal), terminal (use terminal
                              width). No wrap when stdout is not a TTY.
                              (default: None)
  --columns COLUMNS           Comma-separated columns to display (names, 1-based indexes, or negatives from end: -1=last) (default: None)
  --add-index, --no-add-index
                              Include key/index column in the table (default:
                              None)
  --format {view,yaml,json,csv}
                              Output format (default: view table) (default:
                              None)
  --sort-columns SORT_COLUMNS
                              Comma-separated columns to sort by (names,
                              1-based indexes, or negatives from end:
                              -1=last). Use --sort-columns=-1,1 when values
                              start with '-'. (default: None)
  --sort-mode {asc,desc}      Sort direction (default: asc) (default: None)
  --wrap MODE|COL,...         Flexible table columns: they expand or shrink to the terminal. last (rightmost), first (leftmost), all (any column), or comma-separated names/indexes in priority order. Use --wrap=-1 when the value starts with '-'. Ignored when width is content or stdout is not a TTY. (default: None)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf scan kinds

<!-- extract: help scan kinds -->
```text
usage: supershelf scan kinds [-h] [--expand-keys | --no-expand-keys]
                             [--width {content,fit,terminal}]
                             [--columns COLUMNS]
                             [--add-index | --no-add-index]
                             [--format {view,yaml,json,csv}]
                             [--sort-columns SORT_COLUMNS]
                             [--sort-mode {asc,desc}] [--wrap MODE|COL,...]
                             [--log-colors | --no-log-colors] [--version] [-v]
                             [--log-format {default,extended,audit,debug}]
                             [--trace | --no-trace] [--config CONFIG]
                             [--profile PROFILE] [--dry-run]
                             [path]

List the kind matched for each kept file.

positional arguments:
  path                        Path relative to the input, as shown in the path column. Omit for every kept file. An exact file path selects that file. Anything else selects paths that start with it. (default: None)

options:
  -h, --help                  show this help message and exit

Output options:
  --expand-keys, --no-expand-keys
                              Expand nested dict items into table columns
                              (default: None)
  --width {content,fit,terminal}
                              Table width: content (size to data), fit (shrink
                              if wider than terminal), terminal (use terminal
                              width). No wrap when stdout is not a TTY.
                              (default: None)
  --columns COLUMNS           Comma-separated columns to display (names, 1-based indexes, or negatives from end: -1=last) (default: None)
  --add-index, --no-add-index
                              Include key/index column in the table (default:
                              None)
  --format {view,yaml,json,csv}
                              Output format (default: view table) (default:
                              None)
  --sort-columns SORT_COLUMNS
                              Comma-separated columns to sort by (names,
                              1-based indexes, or negatives from end:
                              -1=last). Use --sort-columns=-1,1 when values
                              start with '-'. (default: None)
  --sort-mode {asc,desc}      Sort direction (default: asc) (default: None)
  --wrap MODE|COL,...         Flexible table columns: they expand or shrink to the terminal. last (rightmost), first (leftmost), all (any column), or comma-separated names/indexes in priority order. Use --wrap=-1 when the value starts with '-'. Ignored when width is content or stdout is not a TTY. (default: None)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf scan vars

<!-- extract: help scan vars -->
```text
usage: supershelf scan vars [-h] [--kind-overrides-mode KIND_OVERRIDES_MODE]
                            [--all] [--expand-keys | --no-expand-keys]
                            [--width {content,fit,terminal}]
                            [--columns COLUMNS] [--add-index | --no-add-index]
                            [--format {view,yaml,json,csv}]
                            [--sort-columns SORT_COLUMNS]
                            [--sort-mode {asc,desc}] [--wrap MODE|COL,...]
                            [--log-colors | --no-log-colors] [--version] [-v]
                            [--log-format {default,extended,audit,debug}]
                            [--trace | --no-trace] [--config CONFIG]
                            [--profile PROFILE] [--dry-run]
                            [path]

List variables for each matched file.

positional arguments:
  path                        Path relative to the input, as shown in the path column. Omit for every kept file. An exact file path selects that file. Anything else selects paths that start with it. (default: None)

options:
  -h, --help                  show this help message and exit
  --kind-overrides-mode KIND_OVERRIDES_MODE
                              Kind file mode: auto, manual, always, or
                              disabled. (default: None)
  --all                       Include internal variables in the vars column. (default: False)

Output options:
  --expand-keys, --no-expand-keys
                              Expand nested dict items into table columns
                              (default: None)
  --width {content,fit,terminal}
                              Table width: content (size to data), fit (shrink
                              if wider than terminal), terminal (use terminal
                              width). No wrap when stdout is not a TTY.
                              (default: None)
  --columns COLUMNS           Comma-separated columns to display (names, 1-based indexes, or negatives from end: -1=last) (default: None)
  --add-index, --no-add-index
                              Include key/index column in the table (default:
                              None)
  --format {view,yaml,json,csv}
                              Output format (default: view table) (default:
                              None)
  --sort-columns SORT_COLUMNS
                              Comma-separated columns to sort by (names,
                              1-based indexes, or negatives from end:
                              -1=last). Use --sort-columns=-1,1 when values
                              start with '-'. (default: None)
  --sort-mode {asc,desc}      Sort direction (default: asc) (default: None)
  --wrap MODE|COL,...         Flexible table columns: they expand or shrink to the terminal. last (rightmost), first (leftmost), all (any column), or comma-separated names/indexes in priority order. Use --wrap=-1 when the value starts with '-'. Ignored when width is content or stdout is not a TTY. (default: None)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf scan inspect

<!-- extract: help scan inspect -->
```text
usage: supershelf scan inspect [-h] [--log-colors | --no-log-colors]
                               [--version] [-v]
                               [--log-format {default,extended,audit,debug}]
                               [--trace | --no-trace] [--config CONFIG]
                               [--profile PROFILE] [--dry-run]
                               [path]

Show how match rules test kept files.

positional arguments:
  path                        Path relative to the input, as shown in the path column. Omit for every kept file. An exact file path selects that file. Anything else selects paths that start with it. (default: None)

options:
  -h, --help                  show this help message and exit

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf record

<!-- extract: help record -->
```text
usage: supershelf record [-h] [--log-colors | --no-log-colors] [--version]
                         [-v] [--log-format {default,extended,audit,debug}]
                         [--trace | --no-trace] [--config CONFIG]
                         [--profile PROFILE] [--dry-run]
                         {status,run,history,duplicates} ...

Record matched files and read that history.

subcommands:
  status                      Compare matched files with the profile database
  run                         Record matched files into the profile database
  history                     Show recorded events
  duplicates                  List documents that share a hash

options:
  -h, --help                  show this help message and exit

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf record status

<!-- extract: help record status -->
```text
usage: supershelf record status [-h] [--expand-keys | --no-expand-keys]
                                [--width {content,fit,terminal}]
                                [--columns COLUMNS]
                                [--add-index | --no-add-index]
                                [--format {view,yaml,json,csv}]
                                [--sort-columns SORT_COLUMNS]
                                [--sort-mode {asc,desc}] [--wrap MODE|COL,...]
                                [--record-identity RECORD_IDENTITY]
                                [--log-colors | --no-log-colors] [--version]
                                [-v]
                                [--log-format {default,extended,audit,debug}]
                                [--trace | --no-trace] [--config CONFIG]
                                [--profile PROFILE] [--dry-run]
                                [path]

Compare matched files with the profile database.

positional arguments:
  path                        Path relative to the input, as shown in the path column. Omit for every kept file. An exact file path selects that file. Anything else selects paths that start with it. (default: None)

options:
  -h, --help                  show this help message and exit
  --record-identity RECORD_IDENTITY
                              Link rule for this run: a word or a comma-
                              separated list. Does not override a match rule
                              that set record_identity. Overrides
                              SUPERSHELF_RECORD_IDENTITY and
                              config.record_identity. (default: None)

Output options:
  --expand-keys, --no-expand-keys
                              Expand nested dict items into table columns
                              (default: None)
  --width {content,fit,terminal}
                              Table width: content (size to data), fit (shrink
                              if wider than terminal), terminal (use terminal
                              width). No wrap when stdout is not a TTY.
                              (default: None)
  --columns COLUMNS           Comma-separated columns to display (names, 1-based indexes, or negatives from end: -1=last) (default: None)
  --add-index, --no-add-index
                              Include key/index column in the table (default:
                              None)
  --format {view,yaml,json,csv}
                              Output format (default: view table) (default:
                              None)
  --sort-columns SORT_COLUMNS
                              Comma-separated columns to sort by (names,
                              1-based indexes, or negatives from end:
                              -1=last). Use --sort-columns=-1,1 when values
                              start with '-'. (default: None)
  --sort-mode {asc,desc}      Sort direction (default: asc) (default: None)
  --wrap MODE|COL,...         Flexible table columns: they expand or shrink to the terminal. last (rightmost), first (leftmost), all (any column), or comma-separated names/indexes in priority order. Use --wrap=-1 when the value starts with '-'. Ignored when width is content or stdout is not a TTY. (default: None)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf record run

<!-- extract: help record run -->
```text
usage: supershelf record run [-h] [--expand-keys | --no-expand-keys]
                             [--width {content,fit,terminal}]
                             [--columns COLUMNS]
                             [--add-index | --no-add-index]
                             [--format {view,yaml,json,csv}]
                             [--sort-columns SORT_COLUMNS]
                             [--sort-mode {asc,desc}] [--wrap MODE|COL,...]
                             [--record-identity RECORD_IDENTITY]
                             [--log-colors | --no-log-colors] [--version] [-v]
                             [--log-format {default,extended,audit,debug}]
                             [--trace | --no-trace] [--config CONFIG]
                             [--profile PROFILE] [--dry-run]
                             [path]

Record matched files into the profile database.

positional arguments:
  path                        Path relative to the input, as shown in the path column. Omit for every kept file. An exact file path selects that file. Anything else selects paths that start with it. (default: None)

options:
  -h, --help                  show this help message and exit
  --record-identity RECORD_IDENTITY
                              Link rule for this run: a word or a comma-
                              separated list. Does not override a match rule
                              that set record_identity. Overrides
                              SUPERSHELF_RECORD_IDENTITY and
                              config.record_identity. (default: None)

Output options:
  --expand-keys, --no-expand-keys
                              Expand nested dict items into table columns
                              (default: None)
  --width {content,fit,terminal}
                              Table width: content (size to data), fit (shrink
                              if wider than terminal), terminal (use terminal
                              width). No wrap when stdout is not a TTY.
                              (default: None)
  --columns COLUMNS           Comma-separated columns to display (names, 1-based indexes, or negatives from end: -1=last) (default: None)
  --add-index, --no-add-index
                              Include key/index column in the table (default:
                              None)
  --format {view,yaml,json,csv}
                              Output format (default: view table) (default:
                              None)
  --sort-columns SORT_COLUMNS
                              Comma-separated columns to sort by (names,
                              1-based indexes, or negatives from end:
                              -1=last). Use --sort-columns=-1,1 when values
                              start with '-'. (default: None)
  --sort-mode {asc,desc}      Sort direction (default: asc) (default: None)
  --wrap MODE|COL,...         Flexible table columns: they expand or shrink to the terminal. last (rightmost), first (leftmost), all (any column), or comma-separated names/indexes in priority order. Use --wrap=-1 when the value starts with '-'. Ignored when width is content or stdout is not a TTY. (default: None)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf record history

<!-- extract: help record history -->
```text
usage: supershelf record history [-h] [--expand-keys | --no-expand-keys]
                                 [--width {content,fit,terminal}]
                                 [--columns COLUMNS]
                                 [--add-index | --no-add-index]
                                 [--format {view,yaml,json,csv}]
                                 [--sort-columns SORT_COLUMNS]
                                 [--sort-mode {asc,desc}]
                                 [--wrap MODE|COL,...]
                                 [--log-colors | --no-log-colors] [--version]
                                 [-v]
                                 [--log-format {default,extended,audit,debug}]
                                 [--trace | --no-trace] [--config CONFIG]
                                 [--profile PROFILE] [--dry-run]
                                 [path]

Show recorded events.

positional arguments:
  path                        Path relative to the input, as shown in the path column. Omit for every kept file. An exact file path selects that file. Anything else selects paths that start with it. (default: None)

options:
  -h, --help                  show this help message and exit

Output options:
  --expand-keys, --no-expand-keys
                              Expand nested dict items into table columns
                              (default: None)
  --width {content,fit,terminal}
                              Table width: content (size to data), fit (shrink
                              if wider than terminal), terminal (use terminal
                              width). No wrap when stdout is not a TTY.
                              (default: None)
  --columns COLUMNS           Comma-separated columns to display (names, 1-based indexes, or negatives from end: -1=last) (default: None)
  --add-index, --no-add-index
                              Include key/index column in the table (default:
                              None)
  --format {view,yaml,json,csv}
                              Output format (default: view table) (default:
                              None)
  --sort-columns SORT_COLUMNS
                              Comma-separated columns to sort by (names,
                              1-based indexes, or negatives from end:
                              -1=last). Use --sort-columns=-1,1 when values
                              start with '-'. (default: None)
  --sort-mode {asc,desc}      Sort direction (default: asc) (default: None)
  --wrap MODE|COL,...         Flexible table columns: they expand or shrink to the terminal. last (rightmost), first (leftmost), all (any column), or comma-separated names/indexes in priority order. Use --wrap=-1 when the value starts with '-'. Ignored when width is content or stdout is not a TTY. (default: None)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf record duplicates

<!-- extract: help record duplicates -->
```text
usage: supershelf record duplicates [-h] [--expand-keys | --no-expand-keys]
                                    [--width {content,fit,terminal}]
                                    [--columns COLUMNS]
                                    [--add-index | --no-add-index]
                                    [--format {view,yaml,json,csv}]
                                    [--sort-columns SORT_COLUMNS]
                                    [--sort-mode {asc,desc}]
                                    [--wrap MODE|COL,...]
                                    [--log-colors | --no-log-colors]
                                    [--version] [-v]
                                    [--log-format {default,extended,audit,debug}]
                                    [--trace | --no-trace] [--config CONFIG]
                                    [--profile PROFILE] [--dry-run]
                                    [path]

List documents that share a hash.

positional arguments:
  path                        Path relative to the input, as shown in the path column. Omit for every kept file. An exact file path selects that file. Anything else selects paths that start with it. (default: None)

options:
  -h, --help                  show this help message and exit

Output options:
  --expand-keys, --no-expand-keys
                              Expand nested dict items into table columns
                              (default: None)
  --width {content,fit,terminal}
                              Table width: content (size to data), fit (shrink
                              if wider than terminal), terminal (use terminal
                              width). No wrap when stdout is not a TTY.
                              (default: None)
  --columns COLUMNS           Comma-separated columns to display (names, 1-based indexes, or negatives from end: -1=last) (default: None)
  --add-index, --no-add-index
                              Include key/index column in the table (default:
                              None)
  --format {view,yaml,json,csv}
                              Output format (default: view table) (default:
                              None)
  --sort-columns SORT_COLUMNS
                              Comma-separated columns to sort by (names,
                              1-based indexes, or negatives from end:
                              -1=last). Use --sort-columns=-1,1 when values
                              start with '-'. (default: None)
  --sort-mode {asc,desc}      Sort direction (default: asc) (default: None)
  --wrap MODE|COL,...         Flexible table columns: they expand or shrink to the terminal. last (rightmost), first (leftmost), all (any column), or comma-separated names/indexes in priority order. Use --wrap=-1 when the value starts with '-'. Ignored when width is content or stdout is not a TTY. (default: None)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf data

`data` reads and writes kind files. It uses the same walk and the same resolved values as `scan vars`. It does not read or write documents, events, or `vars_json`. `cache_file` stays unused.

`kind_overrides_mode` does not gate these commands. `manual` and `disabled` still allow `data feed` and `data prune` to write. An empty `kind_overrides_config` stops all three.

`data feed` and `data prune` ask once on stderr, before any kind-file write. `y` or `yes` writes. Anything else writes nothing. When stdin is not a terminal, pass `--force`. `--force` skips the question. `--dry-run` prints the summary and writes no kind file. A candidate that calls `meta()` can write `content_meta` during the preview. An answer of no leaves that cache.

<!-- extract: help data -->
```text
usage: supershelf data [-h] [--log-colors | --no-log-colors] [--version] [-v]
                       [--log-format {default,extended,audit,debug}]
                       [--trace | --no-trace] [--config CONFIG]
                       [--profile PROFILE] [--dry-run]
                       {feed,prune,show} ...

Read and write kind files.

subcommands:
  feed                        Fill empty kind-file cells with resolved values
  prune                       Drop empty columns, unmatched rows, or every row
  show                        Print live variable values, one table per profile and kind

options:
  -h, --help                  show this help message and exit

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf data feed

Fills empty selected cells with the resolved display string. A filled cell stays. An unset var does not blank a cell. `__date__` is written with `kind_overrides_date_format`. Other date vars stay `YYYY-MM-DD`. Feed does not append the empty rows `scan vars` appends.

`NAMES` is an optional comma-separated list of kinds or var names. Spaces around commas are ignored. A name that is both a kind and a var stops the command. Pass `--kind` or `--var` to choose. `--kind` selects every schema var of those kinds. `--kind` and `--var` together keep only those vars on those kinds. With no schema columns, feed uses the names `scan vars` would print.

<!-- extract: help data feed -->
```text
usage: supershelf data feed [-h] [--kind KIND] [--var VAR] [--force]
                            [--log-colors | --no-log-colors] [--version] [-v]
                            [--log-format {default,extended,audit,debug}]
                            [--trace | --no-trace] [--config CONFIG]
                            [--profile PROFILE] [--dry-run]
                            [names]

Fill empty kind-file cells with resolved values.

positional arguments:
  names                       Comma-separated kinds or var names. Spaces around commas are ignored. A name that is both needs --kind or --var. (default: None)

options:
  -h, --help                  show this help message and exit
  --kind KIND                 Comma-separated kinds. Each selected kind enables its schema vars. (default: None)
  --var VAR                   Comma-separated var names. With --kind, only these vars are written. (default: None)
  --force                     Write kind files without asking. Required when stdin is not a terminal. (default: False)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf data prune

Edits existing kind files and does not create a missing one. With no flags, empty columns that are not in the schema are dropped. A schema column stays, and one filled cell keeps an extra column. `--missing` drops a row whose path is not matched as that kind. The document row stays, including when its presence is `missing`. `--clear` removes every row and leaves the file. The header stays on a CSV. `--all` runs every purge, so the file ends with no rows. The database is not changed. Passing one flag does not turn the others on.

<!-- extract: help data prune -->
```text
usage: supershelf data prune [-h] [--empty-fields] [--missing] [--clear]
                             [--all] [--force]
                             [--log-colors | --no-log-colors] [--version] [-v]
                             [--log-format {default,extended,audit,debug}]
                             [--trace | --no-trace] [--config CONFIG]
                             [--profile PROFILE] [--dry-run]

Drop empty columns, unmatched rows, or every row in existing kind files.

options:
  -h, --help                  show this help message and exit
  --empty-fields              Drop empty columns that are not in the schema. This is the default. (default: False)
  --missing                   Drop rows whose path is not matched as that kind. Documents stay. (default: False)
  --clear                     Remove every row. The kind file and the database stay. (default: False)
  --all                       Run every purge, including --clear. The database stays. (default: False)
  --force                     Write kind files without asking. Required when stdin is not a terminal. (default: False)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->

## supershelf data show

Prints the live resolve. One table per profile and kind. A title line names the profile, the kind, and the kind file path when there is one. Columns are `path`, then schema names, then any other name `scan vars` would print. An unset var is blank. It does not write kind files and it does not prompt. It may write `content_meta`. `--dry-run` does not create or migrate the database. `KIND` limits the output to that kind. A known kind with no matched files prints the title and no rows.

<!-- extract: help data show -->
```text
usage: supershelf data show [-h] [--expand-keys | --no-expand-keys]
                            [--format-scope {all,first}]
                            [--line-length N|terminal|nowrap]
                            [--width {content,fit,terminal}]
                            [--columns COLUMNS] [--add-index | --no-add-index]
                            [--format {view,yaml,json,csv}]
                            [--sort-columns SORT_COLUMNS]
                            [--sort-mode {asc,desc}] [--wrap MODE|COL,...]
                            [--log-colors | --no-log-colors] [--version] [-v]
                            [--log-format {default,extended,audit,debug}]
                            [--trace | --no-trace] [--config CONFIG]
                            [--profile PROFILE] [--dry-run]
                            [kind]

Print live variable values, one table per profile and kind.

positional arguments:
  kind                        Kind to print. Omit for every kind that has a matched file. (default: None)

options:
  -h, --help                  show this help message and exit

Output options:
  --expand-keys, --no-expand-keys
                              Expand nested dict items into table columns
                              (default: None)
  --format-scope {all,first}  When using CompositeView with machine formats: first (primary section only) or all (envelope of every section). Default: first (default: None)
  --line-length N|terminal|nowrap
                              Wrap text at N columns (default 120), terminal,
                              or nowrap. No wrap when stdout is not a TTY.
                              (default: None)
  --width {content,fit,terminal}
                              Table width: content (size to data), fit (shrink
                              if wider than terminal), terminal (use terminal
                              width). No wrap when stdout is not a TTY.
                              (default: None)
  --columns COLUMNS           Comma-separated columns to display (names, 1-based indexes, or negatives from end: -1=last) (default: None)
  --add-index, --no-add-index
                              Include key/index column in the table (default:
                              None)
  --format {view,yaml,json,csv}
                              Output format (default: view table) (default:
                              None)
  --sort-columns SORT_COLUMNS
                              Comma-separated columns to sort by (names,
                              1-based indexes, or negatives from end:
                              -1=last). Use --sort-columns=-1,1 when values
                              start with '-'. (default: None)
  --sort-mode {asc,desc}      Sort direction (default: asc) (default: None)
  --wrap MODE|COL,...         Flexible table columns: they expand or shrink to the terminal. last (rightmost), first (leftmost), all (any column), or comma-separated names/indexes in priority order. Use --wrap=-1 when the value starts with '-'. Ignored when width is content or stdout is not a TTY. (default: None)

parent options:
  --log-colors, --no-log-colors
                              Enable colored logs (default: on for TTY;
                              override with CLAK_LOG_COLORS or this flag)
  --version                   Print the installed version and exit.
  -v, --verbose               Increase verbosity level (-v, -vv, -vvv, -vvvv)
  --log-format {default,extended,audit,debug}
                              Set log formatter
  --trace, --no-trace         Enable trace logging on errors
  --config CONFIG             Config file or directory. Overrides SUPERSHELF_CONFIG.
  --profile PROFILE           Comma-separated profile names. Overrides SUPERSHELF_PROFILES.
  --dry-run                   Report actions without changing anything.
```
<!-- /extract -->
