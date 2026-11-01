# Limits

This version prints scan results. It does not record them.

- There is no output tree. `outputs` is not read. `extension_remap` is not read.
- `database_file` and `cache_file` are rendered so templates can name them. The scan commands do not create those files.
- `scan vars` may create or append a kind file, and may add missing schema columns to a CSV. It does not edit a cell that is already there. `scan files` and `scan kinds` do not read or write kind files. See [Kind files](kind-files.md).
- `supershelf schema` prints JSON Schema for `vars_schema` and `kind_schema`. It does not walk inputs or write a kind file. Kind-file columns are chosen when `scan vars` writes a CSV. With no schema columns, a new CSV still starts as `PATH,__date__`.
- `--dry-run` on `scan vars` still reads kind files and does not create or append. The other scan commands only print. `schema` only prints.
- PDF metadata is the creation date and the modification date, through `pdf_cdate()` and `pdf_mdate()`. Image tags, audio tags, and other metadata fields are not read. There is no `scan meta` command.

A `__date__` value is stored for later output paths. Nothing in this version writes a path from it.
