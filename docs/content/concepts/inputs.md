# Inputs

`inputs` is a top-level list. A profile with no inputs, an empty list, or a value that is not a list stops the command when a scan runs. `supershelf profiles` does not check this.

Each item is a mapping. Unknown keys stop the command. The fields are `path`, `include`, `exclude`, `depth`, and `follow_symlinks`.

## The path

`path` is required and uses the [path template language](paths.md). A relative path is resolved from `__root_dir__`.

If the path exists and is not a directory, the command stops. If the directory is missing, Supershelf logs a warning and skips that input. The input keeps its 1-based position, so a later input is still index 2 when the first was skipped. The skipped input adds no rows.

## Depth, symlinks, and globs

`depth` defaults to `0`. `0` means no recursion limit. `1` means only the input directory. `2` means that directory and one subdirectory level. A negative depth stops the command.

`follow_symlinks` defaults to true. `false` skips symlinks. A followed symlink is stored as the path under the input, not as the target path. A symlink cycle logs a warning and that path is skipped.

`include` and `exclude` are lists of globs. They match the path relative to the input directory. `*` stays in one directory. `**` crosses directories. The match is against the whole relative path.

If `include` is set, a file must match at least one include pattern. If `include` is omitted, the walk starts from every file it found. If `exclude` is set, matching files are dropped. If `exclude` is omitted, nothing is dropped for that reason. Exclude runs after include.

`**/*.pdf` matches a PDF in any nested directory. `*.pdf` matches a PDF sitting in the input directory only.

## What is kept

The walk keeps regular files that pass include and exclude. Within one input, paths are sorted.

Skipped, and not recorded:

- directories, which are entered only while `depth` allows
- symlinks when `follow_symlinks` is false
- symlink cycles
- empty files
- anything that is not a regular file
- files that fail include or match exclude

An unreadable file or directory logs a warning and is skipped. That directory is not descended.

`scan files` then reads mtime, ctime, and sha256, unless `--quick` is set. An unreadable file at that step logs a warning and is dropped. `--quick` still ignores empty files. It does not hash.

Stored mtime and ctime are UTC ISO-8601 with a numeric offset, so they can be parsed later. Fractional seconds are included when the filesystem value has them. `scan files` shows those instants with `config.default_date_format`.

`path` in the table is relative to the input directory, with `/` separators. `input` is the 1-based index in that profile's `inputs` list.

`scan files` takes an optional path, the same text as that column. Omit it to list every kept file. An exact file path lists that file. Any other value lists paths that start with it. A value that no kept file has stops the command. The same path in two inputs is listed twice.

The columns are `profile`, `input`, `path`, `mtime`, `ctime`, and `sha256`. `--quick` omits the last three.

`scan files` only prints. It does not create the database file or the cache file.
