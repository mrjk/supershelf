# Command line

Every command accepts `--config`, `--profile`, `--dry-run`, and `--version`, plus the log flags from the CLI library. The listings below are the program's own help text.

`--config` selects the config file or directory and overrides `SUPERSHELF_CONFIG`. `--profile` is a comma-separated list of profile names and overrides `SUPERSHELF_PROFILES`. `--dry-run` on `scan vars` reads kind files and does not create or append. The other scan commands only print. See [Limits](../concepts/limits.md).

The help text lists `-vvvv`. This program's log tiers stop at `-vvv`. `-vvvv` is rejected.

## supershelf

<!-- extract: help -->
```text
usage: supershelf [-h] [--log-colors | --no-log-colors] [--version] [-v]
                  [--log-format {default,extended,audit,debug}]
                  [--trace | --no-trace] [--config CONFIG] [--profile PROFILE]
                  [--dry-run]
                  {profiles,scan} ...

Load supershelf profiles and scan their inputs.

subcommands:
  profiles                    List profile names and config paths
  scan                        Scan profile inputs
    files                     List files kept by each input
    kinds                     List the kind matched for each kept file
    vars                      List variables for each matched file
    inspect                   Show how match rules test kept files

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
                            [--expand-keys | --no-expand-keys]
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
