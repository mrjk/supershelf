# Limits

This version records matched files and can copy, symlink, or hardlink them with `output`.

- `output preview` and `output run` read `outputs`. The file driver is built in. `extension_remap` is not read. There is no output prune. A csv, json, or sql output is not in this version. See [Output](output.md).
- `record run` creates `database_file` when a row would change. `scan vars`, `record run`, `data feed`, and `data show` create it when `meta()` runs and the cache misses. `--dry-run` does not. `scan files`, `scan kinds`, `scan inspect`, `schema`, `profiles`, and `data prune` do not. `data feed` and `data show` do not insert a document or an event. `cache_file` is rendered and nothing writes it. See [Record](record.md).
- `scan vars` may create or append a kind file, and may add missing schema columns to a CSV. It does not edit a cell that is already there. `data feed` and `data prune` edit kind-file cells and columns. `data show` does not write a kind file. `scan files` and `scan kinds` do not read or write kind files. See [Kind files](kind-files.md).
- `supershelf schema` prints JSON Schema for `vars_schema` and `kind_schema`. It does not walk inputs or write a kind file. Kind-file columns are chosen when `scan vars` writes a CSV. With no schema columns, a new CSV still starts as `PATH,__date__`.
- `--dry-run` on `scan vars` still reads kind files and does not create or append. `--dry-run` on `data feed` and `data prune` prints the summary and does not write a kind file. `--dry-run` on `data show` does not create or migrate the database. The other scan commands only print. `schema` only prints. `--dry-run` on `record run` prints the rows that would change and creates nothing. `--dry-run` on `output run` prints the rows that would change and does not write a destination or an output event.
- `meta("pdf", "creation_date")` and `meta("pdf", "modification_date")` read PDF dates as `YYYY-MM-DD`. `meta()` also reads other PDF info, exiftool tags, and pdftotext. File strings are `__file__` fields. There is no `scan meta` command.

A layout can read `__date__` with `{{ __date__.Y }}`, `{{ __date__.m }}`, and `{{ __date__.d }}`. Those are `%Y`, `%m`, and `%d`. `{{ __date__ }}` is the full `YYYY-MM-DD`. A layout that uses `__date__` fails when `__date__` was omitted.
