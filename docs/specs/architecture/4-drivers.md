# 4 Output drivers

Architecture. Index: [README](../README.md).

Behavior 5. A driver writes one kind of destination. The built-in drivers are `file` and `sqlite`. Schema version stays `2`. The file driver calls `append_output`. The sqlite driver does not. `append_output` accepts only `copy`, `symlink`, and `hardlink`. A later csv or json driver is not this section. Custom SQL and views on the export database are a later sqlite mode, not this section.

Metadata drivers fill variables. They are not output drivers. `metadata_driver` and `output_modules` are different lists.

## 4.1 Contract

`OutputDriver` is the base. A plugin subclasses it.

- `name` is the driver word stored in `driver`.
- `check(spec)` validates the item at load. A bad item raises `OutputConfigError`.
- `prepare(spec, profile)` renders profile-scoped fields once. No file variables yet.
- `plan(prepared, context)` returns one action, or skips. It does not write the filesystem and it does not append an event.
- `apply(action, dry_run)` performs the action. `dry_run` true creates nothing and appends nothing.

The host owns `name`, `driver`, `kinds`, `when`, the document gate, the row shape, and plan-then-apply. The context carries the profile, the input, the source file, the document id, and the display-string scope. A driver may store extra fields on the action for its own `apply`.

The row columns are `profile`, `input`, `path`, `output`, `driver`, `status`, `operation`, `when`, `dest`. `operation` and `dest` are the driver's words. `when` is the boolean string from behavior 5.2. Status is `write`, `replace`, `unchanged`, `skip`, or `conflict`.

`OutputConfigError` is a bad output item, a bad module, or a bad literal `when`. Exit 2. `OutputResolveError` is a file the plan cannot accept: the document gate, a layout, a claim, or a destination. The tip names a fix the user can make.

## 4.2 File driver

The built-in name is `file`. Behavior 5.3 is the path, the layout, the operation, and the re-run rule.

`plan` decides the status and the `previous` payload. `apply` writes the file, then calls `append_output` for `write` and `replace`. The document projection stays as it is. `previous` is `OutputPrevious`:

- `existed` false: this apply creates the path. `ours` true only when an earlier event already recorded that path. Then `operation` and `source_hash` are that event's.
- `existed` true and `ours` true: this profile wrote the previous file. `operation` and `source_hash` are required.
- `existed` true and `ours` false: a file was already there and this profile did not write it. Revert cannot restore those bytes.

## 4.3 Modules

`config.output_modules` lists importable modules. Omitted, null, and `[]` add no drivers. Built-in `file` is registered first, then built-in `sqlite`. Each module exports `DRIVERS`, a list of `OutputDriver` subclasses. Import order is list order. A repeated name stops the command. An import failure stops the command.

A module that exports no `DRIVERS` stops the command. A value that is not a driver class stops the command. The message names the module.

## 4.4 Sqlite driver

The built-in name is `sqlite`. Behavior 5.4 is the path, the export tables, the upsert rule, and schema sync.

`plan` decides `write`, `replace`, or `unchanged` from the export database row for that content hash. `apply` upserts into the export file. It does not call `append_output`. The profile document projection stays as it is.

Identity in the export file is the content hash. One hash is one document. The `files` row and each `data_<kind>` row use that hash as the primary key. External tools may insert other rows. Supershelf does not delete them.

`operation` is the word `upsert`. The CLI `dest` is the document path relative to the input root. The destination file is the rendered `path`.
