# Use several profiles

Each profile file is a separate shelf. Profiles do not share scan results. Discovery rules are in [Profiles](../concepts/profiles.md).

## Named files

In the current directory, with no `supershelf.toml`, Supershelf loads every `profile.NAME.toml`, then `.yaml`, then `.yml`. One file per name. Names are sorted.

```text
profile.books.toml
profile.cards.toml
```

The name comes from the filename. `profile.books.toml` is profile `books`. If `config.profile` inside that file is a different non-empty string, it is ignored and a warning is printed.

```bash
supershelf profiles
supershelf scan files
```

`profiles` lists both files. `scan files` walks each selected profile on its own. The `profile` column shows which file a row came from.

## Choose a subset

`--profile` is a comma-separated list. Spaces around names are ignored. The result keeps the requested order. A repeated name is kept once. An unknown name stops the command.

```bash
supershelf --profile cards,books profiles
```

`SUPERSHELF_PROFILES` is the same list. `--profile` wins when both are set.

```bash
SUPERSHELF_PROFILES=books supershelf scan kinds
```

With no selector, every discovered profile is kept.

## One file for one profile

If `supershelf.toml`, `supershelf.yaml`, or `supershelf.yml` exists in the directory, Supershelf loads only the first of those. It does not also load `profile.NAME.*` from that directory. The profile name is `config.profile` when that is set, otherwise `default`.

=== "TOML"

    ```toml title="supershelf.toml"
    [config]
    profile = "books"

    [[inputs]]
    path = "inbox"
    ```

=== "YAML"

    ```yaml title="supershelf.yaml"
    config:
      profile: books

    inputs:
      - path: inbox
    ```

`--config` points at a file or a directory and overrides `SUPERSHELF_CONFIG`. A missing explicit path does not fall through to the current directory.

The next page is a catalog of profiles for one inbox: [Base](examples/base.md).
