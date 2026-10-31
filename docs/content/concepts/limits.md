# Limits

This version prints scan results. It does not record them.

- There is no output tree. `outputs` is not read. `extension_remap` is not read.
- `database_file` and `cache_file` are rendered so templates can name them. The scan commands do not create those files.
- Kind files are read when they already exist. Supershelf does not create them, append rows, or edit cells. There is no kind-overrides mode and no flag that turns writing on.
- `--dry-run` is accepted. The scan commands only print, so the flag does not change their result.
- PDF metadata is the creation date and the modification date, through `pdf_cdate()` and `pdf_mdate()`. Image tags, audio tags, and other metadata fields are not read. There is no `scan meta` command.

A `__date__` value is stored for later output paths. Nothing in this version writes a path from it.
