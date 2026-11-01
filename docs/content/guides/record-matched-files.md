# Record matched files

`record` keeps a history of the files a profile matches. The concepts are in [Record](../concepts/record.md). This version does not build an output tree.

Use the profile from [Set variables](set-variables.md), with a file in `inbox`:

```toml
[default_vars]
vendor = "Bank2000"

[[inputs]]
path = "inbox"

[[match_rules]]
name = "bill"
glob = "**"
```

Preview the rows a run would write. This creates nothing, including the sqlite file:

```bash
supershelf record run --dry-run
```

The status is `new`. Write it:

```bash
supershelf record run
```

That creates `profile.<name>.sqlite` next to the config file, unless `config.database_file` says otherwise. A second run with no file changes prints no rows.

`record status` prints every matched file, including `unchanged`. `record history` prints the events. `record duplicates` prints hashes that belong to more than one document.

Rename the file and keep the bytes, then run again. The history shows `move` for the same document. Replace the bytes at the same path and the history shows `generation`. Delete the file and the document becomes `missing`. The row stays. `record history` still prints it.

`scan files`, `scan kinds`, `scan vars`, and `scan inspect` do not create the sqlite file. `record` reads kind files the same way `scan vars` does, and it does not create or append one.

To follow the hash instead of the path when both change in one run, set the link rule:

```bash
supershelf record run --record-identity hash
```

The config key is `record_identity`, and the environment variable is `SUPERSHELF_RECORD_IDENTITY`. The default is `path`. The two readings of one Bank2000 invoice are in [Record](../concepts/record.md).
