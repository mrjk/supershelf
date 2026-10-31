# List files

`supershelf scan files` prints the files one input keeps. The rules for the walk are in [Inputs](../concepts/inputs.md).

## A folder of statements

These examples use profile `books`, from `profile.books.toml` or `profile.books.yaml` in the [quickstart](../quickstart/index.md). This profile reads `inbox`. It keeps PDF files and drops anything under a `draft` directory. `depth` `0` walks every nested directory.

=== "TOML"

    ```toml title="profile.books.toml"
    [[inputs]]
    path = "inbox"
    depth = 0
    include = ["**/*.pdf"]
    exclude = ["**/draft/**"]

    [[match_rules]]
    name = "unsorted"
    glob = "**"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    inputs:
      - path: inbox
        depth: 0
        include:
          - "**/*.pdf"
        exclude:
          - "**/draft/**"

    match_rules:
      - name: unsorted
        glob: "**"
    ```

`path` is resolved from the profile root. A relative path such as `inbox` starts at `root_dir`, which defaults to the directory of the config file. See [Paths](../concepts/paths.md).

```bash
supershelf scan files
```

Example columns for one kept file:

```text
profile  input  path                                      mtime       ctime       sha256
books    1      Bank2000/REL_20260425_ab12cd34.pdf        2026-04-25  2026-04-25  0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

`input` is the 1-based position of that input in the profile, not the folder path. `path` is relative to the input directory. `mtime` and `ctime` are shown with `config.default_date_format`, which defaults to `%Y-%m-%d`. `sha256` is the lowercase hex digest of the file bytes.

```bash
supershelf scan files --quick
```

`--quick` prints `profile`, `input`, and `path` only. It does not read mtime, ctime, or the hash.

Empty files are left out. A missing input directory is a warning, and that input is skipped. A path that exists and is not a directory stops the command.

The next page classifies those files: [Match a kind](match-a-kind.md).
