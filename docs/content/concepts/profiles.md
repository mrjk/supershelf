# Profiles

A profile is one config file. Supershelf loads a list of them, then a command can filter that list. `supershelf profiles` prints `profile`, `type`, and `path`. It does not render path templates and does not scan inputs.

The file must be a mapping. TOML and YAML are accepted. The stored type is `toml` or `yaml`. A `.yml` file is stored as `yaml`.

## Where files come from

The first source that yields a file wins. Later sources are not merged in.

1. `--config` points at a file or a directory. It overrides `SUPERSHELF_CONFIG`. A missing path, or a directory with no matching file, stops the command. Supershelf does not fall through to the current directory.
2. `SUPERSHELF_CONFIG` uses the same rules as `--config`.
3. The current directory.
4. The user config directory: `$XDG_CONFIG_HOME/supershelf`, or `~/.config/supershelf` when `XDG_CONFIG_HOME` is unset.

An explicit file is loaded as that file only. An explicit directory uses the directory rules below.

In the current directory, and in an explicit directory, a singleton wins. If `supershelf.toml`, `supershelf.yaml`, or `supershelf.yml` exists, Supershelf loads only the first of those, in that order. It does not also load `profile.NAME.*` from that directory. A later format is ignored, with a warning.

If there is no singleton, Supershelf loads every:

- `profile.NAME.toml`
- `profile.NAME.yaml`
- `profile.NAME.yml`

One file per name. Preference is toml, then yaml, then yml. A later format is ignored, with a warning. Names are sorted.

The user config directory does not treat `supershelf.toml` as a profile source. Only `profile.NAME.*` files are loaded there.

If none of these sources has a file, the command stops.

## The profile name

When the filename is `profile.NAME.*`, the profile name is `NAME`. If `config.profile` is a different non-empty string, it is ignored and a warning is printed. The same name does not warn. A blank `config.profile` is unset.

When the filename has no `profile.NAME` prefix, the name is `config.profile` when that is a non-empty string, otherwise `default`. A file passed with `--config` follows this same rule.

The stored document always has `config.profile` set to the resolved name.

If two loaded files resolve to the same name, the later file is ignored, with a warning. The first is kept.

## Which profiles a command uses

Selection happens after the files are loaded.

- `--profile` wins over `SUPERSHELF_PROFILES`.
- Both accept a comma-separated list. Spaces around names are ignored.
- The result keeps the requested order. A repeated name is kept once.
- An unknown name stops the command. The message lists the known names.
- With no selector, every discovered profile is kept.

Each selected profile is scanned on its own. Profiles do not share results.
