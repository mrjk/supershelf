# Record

`record` stores each matched file in the profile sqlite file. The path is `config.database_file`. The packaged path is `{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite`. One profile has one file. `cache_file` is a different path, and nothing writes it.

`scan files`, `scan kinds`, `scan vars`, `scan inspect`, `schema`, and `profiles` do not create the sqlite file. `record run` does, when a row would change. `--dry-run` prints those rows and creates nothing.

The walk is the same full walk as `scan vars`. Variables are resolved the same way, including a kind-file read. `record` does not create or append a kind file.

## Commands

`PATH` is the same selector as `scan files`. On `record status` and `record run`, a value that matches no kept file and no recorded document stops the command.

| Command | What it prints | Write |
| --- | --- | --- |
| `record status [PATH]` | Every in-scope matched file, plus a document this scan would mark missing or unmatched | No |
| `record run [PATH]` | The same rows, except `unchanged` | Yes, unless `--dry-run` |
| `record history [PATH]` | Events, oldest first | No |
| `record duplicates [PATH]` | Hashes carried by two or more documents | No |

`record history` and `record duplicates` do not scan. With no database they print no rows. A history path matches a document when any of its event paths, or its current path, equals the selector or starts with it. The command then prints every event for that document, so a move is still found from the old path.

Status words:

| Status | Meaning |
| --- | --- |
| `new` | First time this document is recorded. Generation 1. |
| `generation` | New bytes at the document's path. The previous generation stays in the history. |
| `move` | The same hash is at a new path and the old path is gone. The generation number stays. |
| `vars` | Kind, rule, or variables changed. The generation number stays. |
| `missing` | The path left the walked inputs. The row stays. |
| `present` | A missing or unmatched document matched again, with the same hash and variables. |
| `unmatched` | The file is still in the walk, and no rule matches. The last hash and variables stay. |
| `refresh` | Only mtime, ctime, or the input index changed. No history row. |
| `unchanged` | Nothing to write. `record run` leaves this row out. |

`duplicates` on a status row is how many other documents would be present with that same current hash. `record duplicates` is the wider query: a hash is listed when two or more documents have carried it, including an older generation. `current` is `yes` when that hash is the document's hash now.

## What stays the same document

A document has a stable id. Rows are not deleted. A later revert walks the events.

The location is the input directory plus the path relative to that input. Reordering the `inputs` list is not a move. A missing input directory leaves that input's documents as they are.

`config.record_identity` chooses the link when a scan could be read two ways. The packaged default is `path`. `--record-identity` wins, then `SUPERSHELF_RECORD_IDENTITY`, then the config key.

`path`. A file that is still at the recorded path keeps that document. New bytes there are a new generation. A move happens when the recorded path is gone, exactly one in-scope file has the hash, and only one document wants that hash.

`hash`. The current hash owns the document. One live file with that hash is that document, including when the old path now holds different bytes. Those new bytes are a new document.

Both rules agree when a file is renamed and edited in the same run. The old path is gone and the old hash is not live, so the old document becomes missing and the new path is a new document.

A path filter observes only the selected paths. It does not mark, move, or insert anything outside that set. A filtered run can mark a selected path missing while those bytes still exist under another name. A later run with no path can move the document onto that name.

Changing the rule later warns. Old events keep the rule that wrote them. The new run decides new links with the new rule.

Bank2000 invoice `2026-04-25.pdf` is recorded. The next scan finds new bytes at that path, and the old bytes at `2026-04-25-copy.pdf`.

With `path`, `2026-04-25.pdf` stays the same document and gains a generation. `2026-04-25-copy.pdf` is a second document. `record duplicates` lists the old hash on both. The first document's row says current `no`.

With `hash`, the old hash moves to `2026-04-25-copy.pdf`. The new bytes at `2026-04-25.pdf` are a new document.

## History and a later output

Each change appends an event: `new`, `move`, `generation`, `vars`, `missing`, `present`, or `unmatched`. A `refresh` does not. Deleting an event is not how a revert works.

The event row also has room for a later output apply: output name, operation (`copy`, `symlink`, or `hardlink`), destination, source hash, and the previous state of that destination. No command writes that event yet. This version does not build an output tree.
