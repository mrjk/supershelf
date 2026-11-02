# Supershelf

Supershelf loads one or more profile files, walks their input directories, matches each kept file to a kind, and prints the variables for that file.

A profile is a TOML or YAML file. It names the folders to read, the rules that classify files, and the values to attach to each match. `scan vars` can also keep a kind file, one row per matched path. `record run` stores matched files in the profile database. This version does not write an output tree or a cache file.

## Install

Supershelf needs Python 3.13 or newer. From a checkout of this repository:

```bash
pip install .
```

```bash
supershelf --version
```

## One profile

Create `profile.books.toml` or `profile.books.yaml` in the directory where you will run the command. This example keeps every file under `inbox` and gives each one the kind `unsorted`.

```toml
# profile.books.toml
[[inputs]]
path = "inbox"

[[match_rules]]
name = "unsorted"
glob = "**"
```

```yaml
# profile.books.yaml
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

`scan kinds` prints the kind for each matched file. `scan vars` prints the variables, and may create or append a kind file. `schema` prints a JSON Schema of the variables the profile declares. The documentation site has the quickstart, the guides, and the reference. From this repository, `task docs` serves that site.

## Development

Python, uv, and task come from `mise.toml`. Shared settings are in `.env`. Local overrides go in `mise.local.toml`, which is gitignored. From the repository root, `task test` runs the tests, `task docs` serves the documentation, and `task ci` runs the verification pipeline. GitHub Actions runs `task ci` through mise. CI runs on a pull request and on a push to `main`, `dev`, or `dev-*`. The site publishes after that succeeds on `main`. `test`, `docs:build`, and `docs:release` can also be run on their own from the Actions tab.

## License

Copyright (C) 2026 the Supershelf authors.

Supershelf is free software under the GNU General Public License, version 3, or any later version. The license text is the `LICENSE.md` file at the repository root.
