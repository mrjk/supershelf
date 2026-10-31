# Share variables for a kind

A kind file is one variable table for a kind. Every matched file of that kind receives the same table. It is applied after `default_vars` and before the winning rule's `vars`. The lookup rules are in [Kind files](../concepts/kind-files.md). The file shape is in [Kind file](../reference/kind-file.md).

The default path list looks for these files, in order, and uses the first one that exists:

```text
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.csv
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.toml
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yaml
{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yml
```

For profile `books` and kind `invoice`, the first candidate is `profile.books.invoice.csv` under the profile root. Supershelf does not create that file. If none of the candidates exist, the kind layer is empty.

## CSV

A CSV kind file has the header `name,value`. A repeated name is the next candidate.

```csv title="profile.books.invoice.csv"
name,value
vendor,Bank2000
owner,{{ missing }}
owner,sample
```

`owner` tries `{{ missing }}` first. That name is not defined, so the candidate fails and `sample` is kept. `vendor` is the literal `Bank2000`.

## TOML and YAML

TOML and YAML use the same mapping shape as `default_vars`. `.yml` is the same text as YAML.

=== "TOML"

    ```toml title="profile.books.invoice.toml"
    vendor = "Bank2000"
    owner = ["{{ missing }}", "sample"]
    ```

=== "YAML"

    ```yaml title="profile.books.invoice.yaml"
    vendor: Bank2000
    owner:
      - "{{ missing }}"
      - sample
    ```

The kind in the path is the kind from the match rule. An override that later changes `__kind__` does not switch files.

`-vv` logs each candidate path the first time a kind and input are searched, and logs which file was loaded. `-v` does not add those lines.

The next page loads more than one profile: [Use several profiles](use-several-profiles.md).
