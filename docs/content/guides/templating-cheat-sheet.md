# Templating

Two languages. Path settings (`root_dir`, `database_file`, `cache_file`, `inputs.path`, output `path`, kind-file paths) replace `{{ name }}` and `{{ name.field }}` once. Variable values, output `when`, and output `layout` use Jinja.

This page uses one fake file. Nothing here is a real profile.

The file is `inbox/bills/acme-2026-04-25.pdf`. The profile name is `paper`. `default_date_format` is `%d/%m/%Y`. The winning rule is `acme`, kind `bill`. `__date__` is set to `2026-04-25`. `root_dir` is `/srv/paper`. The input directory is `/srv/paper/inbox`.

=== "TOML"

    ```toml title="profile.paper.toml"
    [config]
    profile = "paper"
    default_date_format = "%d/%m/%Y"
    root_dir = "{{ __profile__.dir }}"

    [[inputs]]
    path = "inbox"

    [default_vars]
    __date__ = "2026-04-25"
    folder = "{{ __date__.strftime('%Y-%m') }}"

    [[match_rules]]
    name = "acme"
    kind = "bill"
    filename_glob = "bills/*.pdf"

    [[outputs]]
    name = "filed"
    path = "{{ __config__.root_dir }}/out"
    layout = "{{ __date__.Y }}/{{ __date__.m }}/{{ __file__ }}"
    ```

=== "YAML"

    ```yaml title="profile.paper.yaml"
    config:
      profile: paper
      default_date_format: "%d/%m/%Y"
      root_dir: "{{ __profile__.dir }}"

    inputs:
      - path: inbox

    default_vars:
      __date__: "2026-04-25"
      folder: "{{ __date__.strftime('%Y-%m') }}"

    match_rules:
      - name: acme
        kind: bill
        filename_glob: "bills/*.pdf"

    outputs:
      - name: filed
        path: "{{ __config__.root_dir }}/out"
        layout: "{{ __date__.Y }}/{{ __date__.m }}/{{ __file__ }}"
    ```

`folder` is `2026-04`. The layout path under `out` is `2026/04/acme-2026-04-25.pdf`. `scan vars` still prints `__date__` as `2026-04-25`.

## Bare object

With no field, the object prints one string.

| Template | Result |
| --- | --- |
| `{{ __file__ }}` | `acme-2026-04-25.pdf` |
| `{{ __match__ }}` | `bill` |
| `{{ __profile__ }}` | `paper` |
| `{{ __config__ }}` | `/srv/paper` |
| `{{ __input__ }}` | `/srv/paper/inbox` |
| `{{ __date__ }}` | `25/04/2026` |

`__input__` exists only on a kind-file path. `__file__` and `__match__` exist in variable templates and in output `when` and `layout`.

## Fields

| Template | Result |
| --- | --- |
| `{{ __file__.path }}` | `bills/acme-2026-04-25.pdf` |
| `{{ __file__.dir }}` | `bills` |
| `{{ __file__.stem }}` | `acme-2026-04-25` |
| `{{ __file__.ext }}` | `pdf` |
| `{{ __file__.name }}` | `acme-2026-04-25.pdf` |
| `{{ __match__.kind }}` | `bill` |
| `{{ __match__.rule }}` | `acme` |
| `{{ __profile__.dir }}` | directory of the config file |
| `{{ __config__.root_dir }}` | `/srv/paper` |
| `{{ __config__.date_format }}` | `%d/%m/%Y` |
| `{{ __date__.Y }}` | `2026` |
| `{{ __date__.m }}` | `04` |
| `{{ __date__.d }}` | `25` |
| `{{ __date__.strftime('%Y-%m') }}` | `2026-04` |
| `{{ __date__.strftime(__config__.date_format) }}` | `25/04/2026` |

`Y`, `m`, and `d` are the same letters as `%Y`, `%m`, and `%d`. `strftime` takes a normal `strftime` pattern. `%Y` is the four-digit year. `%m` is the month. `%YY` is the year plus a literal `Y`, not a different year code.

`__file__.hash` is the lowercase sha256. `__file__.ctime` and `__file__.mtime` are UTC ISO-8601 text, so they do not count as a date.

## Where a name works

| Template | Can read |
| --- | --- |
| `root_dir`, `database_file`, `cache_file`, `inputs.path`, output `path` | `__profile__`, `__config__` |
| Kind-file path | those, plus `__match__.kind` and `__input__` |
| `default_vars`, rule `vars`, output `when`, output `layout` | those profile objects, plus `__file__`, `__match__`, and `__date__` once a layer set it |

A kind-file path does not see `__match__.rule` or `__file__`. A variable template does not see `__input__`.

PDF dates are `{{ meta("pdf", "creation_date") }}` and `{{ meta("pdf", "modification_date") }}`. Both are `YYYY-MM-DD`.

The next page lists config keys and the environment variables that override them: [Config](config.md).
