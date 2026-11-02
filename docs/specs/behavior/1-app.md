# 1 App initialization

Behavior. Index: [README](../README.md).

- Create one ShelfConfigs python instance, that will hold a list of ShelfConfig.
- Find profile configs. First source wins. Do not merge files from a later source.
  Format preference inside one directory: toml, then yaml, then yml.
  A later format for the same profile warns and is ignored. .yml is stored as type yaml.
- Profile selection, applied after the files are loaded:
  - --profile wins over $SUPERSHELF_PROFILES.
  - Both accept a comma-separated list. Spaces around names are ignored.
  - The result keeps the requested order. A repeated name is kept once.
  - An unknown name is an error. With no selector, every discovered profile is kept.
- Config source, first hit wins:
  - --config
    - Missing path, or a directory with no matching file: error. Do not fall through.
    - A file: load that file only.
      %PROFILE_NAME applies only when the filename is profile.%PROFILE_NAME.(toml|yaml|yml).
    - A directory: same rules as the current directory below.
  - $SUPERSHELF_CONFIG
    - Same processing as --config.
  - Current directory:
    - If supershelf.toml, supershelf.yaml, or supershelf.yml exists, load only the first of those.
      Do not also load profile.%PROFILE_NAME.* from that directory.
    - Otherwise load every:
      - profile.%PROFILE_NAME.toml
      - profile.%PROFILE_NAME.yaml
      - profile.%PROFILE_NAME.yml
      One file per %PROFILE_NAME, toml then yaml then yml. Names are sorted.
      A later format warns and is ignored.
  - User config directory ($XDG_CONFIG_HOME/supershelf, or ~/.config/supershelf):
    - Load only profile.%PROFILE_NAME.toml, then .yaml, then .yml.
    - A supershelf.toml in this directory is not a profile source.
  - If none found, fail.
- Check consistency and prepare:
  - The profile name is %PROFILE_NAME when the filename has one.
    If config.profile is a different non-empty string, warn that it is ignored.
    The same name does not warn. A blank config.profile is treated as unset.
  - If the filename has no %PROFILE_NAME, the profile name is config.profile when that is set, otherwise default.
  - Write config.profile to that profile name on the stored dict.
  - If two files resolve to the same profile, warn and keep the first.
- App is inited:
  - config_list is one or more ShelfConfig:
    - profile: the profile name
    - type: toml or yaml
    - path: config file path
    - config: parsed file contents
  - The file must be a mapping. config, when present, must be a mapping.
    config.profile, when present, must be a string. Other keys are stored and not interpreted in this step.
- App commands:
  - supershelf profiles: table of profile, type, and path.
    This is the list selected by --config / $SUPERSHELF_CONFIG and --profile / $SUPERSHELF_PROFILES.
