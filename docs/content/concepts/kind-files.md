# Kind files

A kind file adds one variable table for a kind. It is the second assignment layer: after `default_vars`, before the winning rule's `vars`. Every matched file of that kind and input receives the same table. The file is not a list of per-file rows. The shape is in [Kind file](../reference/kind-file.md).

## Which file

`config.kind_overrides_config` is an optional list of path templates. They use the [path template language](paths.md). Omitted, the list is:

```text
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.csv
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.toml
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yaml
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yml
```

An empty list means no kind files.

Each path is rendered with the profile scope, `__kind__` set to the rule kind, and `__input__.path` set to the absolute input directory. A relative result is resolved from `__root_dir__`. The first path that exists and is a file wins. A missing path tries the next. None found means an empty table. A path that exists and is not a file stops the command.

The parsed file is cached for the process by its absolute path. Two inputs that resolve the same file share one table. Nothing is written to `cache_file`.

The search is remembered per kind and input directory. `-vv` logs each candidate the first time that pair is searched: a missing path, the file that was loaded, or a path already loaded for another search. An empty list logs that there is no candidate list. A repeated search for that kind and input stays quiet. `-v` does not add these lines.

## What it changes

The rule kind picks the file. A profile override that changes `__kind__` does not switch files and does not change the row lookup, because there is one table for the kind, not a row keyed by path.

Cells use the same candidate language as `default_vars`. A value that contains `{{` is a Jinja template. In CSV, a repeated `name` is the next candidate for that name. The first candidate that succeeds is kept.

A kind file must not set an internal name, `file_ctime`, or `file_mtime`. It may set `__date__` and other names. It may not set `__kind__`.

Supershelf does not create the file, append rows, or rewrite cells. A missing file is skipped.
