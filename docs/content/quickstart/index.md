# Quickstart

Supershelf is a Python command. It needs Python 3.13 or newer. From a checkout of this repository:

```bash
pip install .
```

That installs the `supershelf` command. The version line is filled from the program:

<!-- placeholder: supershelf --version -->

## One profile

Create `profile.books.toml` or `profile.books.yaml` in the directory where you will run the command. This example keeps every file under `inbox` and gives each one the kind `unsorted`.

=== "TOML"

    ```toml title="profile.books.toml"
    [[inputs]]
    path = "inbox"

    [[match_rules]]
    name = "unsorted"
    glob = "**"
    ```

=== "YAML"

    ```yaml title="profile.books.yaml"
    inputs:
      - path: inbox

    match_rules:
      - name: unsorted
        glob: "**"
    ```

Put a file in `inbox`, then list what the profile loaded and what the walk kept:

```bash
supershelf profiles
supershelf scan files
```

`profiles` prints the profile name, the file type, and the config path. `scan files` prints each kept file. The `path` column is relative to `inbox`.

A file that no rule claims is still listed by `scan files`. `scan kinds` leaves it out and prints a warning. The catch-all rule above claims every kept file, so that warning does not appear.

## Where to go next

[List files](../guides/list-files.md) adds include, exclude, and depth. [Match a kind](../guides/match-a-kind.md) separates a Bank2000 statement from the rest. [Set variables](../guides/set-variables.md) reads names out of the filename.
