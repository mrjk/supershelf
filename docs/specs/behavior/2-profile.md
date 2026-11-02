# 2 Profile initialization

Behavior. Index: [README](../README.md).

Source is who writes a value. Availability is where a template can read it. A name in this step is not a variable a layer can assign, and it is not printed.

- supershelf profiles only lists profile, type, and path. It does not build a ShelfProfile.
- A command that needs rendered paths, such as scan, creates one ShelfProfile per selected ShelfConfig.
- supershelf inspect config also builds one ShelfProfile per selected ShelfConfig, and it does not scan.
- Profile load writes `__profile__` before any path template. Read a field. The object with no field is not a string, so the command stops.
  - `__profile__.name`: the profile name from section 1. This replaces `__profile__` and `__profile_name__`.
  - `__profile__.type`: `toml` or `yaml`
  - `__profile__.path`: absolute path of the config file
  - `__profile__.dir`: directory of the config file
  - `__profile__.file`: filename of the config file
  - `__profile__.document`: the parsed profile file. Dotted keys walk nested mappings. This replaces `__config_data__`.
- `__config__.date_format` is `config.default_date_format`. It is a plain string, not a template. `scan files` uses it to show mtime and ctime. Omitted, it is `%Y-%m-%d`. It is published before the path templates below.
- Then render these config keys, in order. After each one, resolve a relative path from `__profile__.dir`, store the absolute path on `__config__`, and publish it before the next template.
  - `root_dir` becomes `__config__.root_dir`
  - `database_file` becomes `__config__.database_file`
  - `cache_file` becomes `__config__.cache_file`
- Built-in defaults when the key is omitted:
  - `root_dir = "{{ __profile__.dir }}"`
  - `database_file = "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.sqlite"`
  - `cache_file = "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.cache"`
- Available here: `__profile__` and the `__config__` fields already published. Not available: `__file__`, `__match__`, `__input__`, and `__date__`.
- This is the scope for `config.root_dir`, `config.database_file`, `config.cache_file`, `inputs.path`, and an output `path`.
- An old flat name, such as `__root_dir__` or `__profile_dir__`, is unknown and stops the command. There is no alias.
