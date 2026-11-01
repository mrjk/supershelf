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
| `duplicate` | An extra live file whose hash this run already keeps. It is printed and not inserted. |

`duplicates` on a status row counts other present documents with that hash, including documents outside the path filter, plus other extra files reported as `duplicate` for that hash. `record duplicates` is the wider query: a hash is listed when two or more documents have carried it, including an older generation. `current` is `yes` when that hash is the document's hash now. A file that was never inserted does not appear there.

## What stays the same document

A document has a stable id. Rows are not deleted. A later revert walks the events.

The location is the input directory plus the path relative to that input. Reordering the `inputs` list is not a move. A missing input directory leaves that input's documents as they are.

`record_identity` chooses the link when a scan could be read two ways. The packaged default is `path`. For the profile default, `--record-identity` wins, then `SUPERSHELF_RECORD_IDENTITY`, then `config.record_identity`. A match rule's `record_identity` wins over that default for files that rule claims. Omitted or null on the rule inherits the profile default. The flag does not override a rule that set the key.

A bare word expands. `path` means path then hash. `hash` means hash then path. A list does not expand: `[path]` is the path step only, and `[hash]` is the hash step only. The flag and the environment variable are a word or a comma-separated list (`hash, path`). The profile value and the rule value are a string or a list of strings.

The list is tried in order. The first step that matches links the document. `events.identity` stores the first step of that list, `path` or `hash`, even when a later step did the work. `meta.identity` stores the profile default only, as `path,hash` or `hash,path`. A stored `path` compares equal to `path,hash`. A stored `hash` compares equal to `hash,path`. A rule override is not written to meta.

`path`. A file that is still at the recorded path keeps that document. New bytes there are a new generation. A move happens when the recorded path is gone, exactly one in-scope file has the hash, and only one document wants that hash.

`hash`. The current hash owns the document among hash-first files. One live file with that hash is that document, including when the old path now holds different bytes. Those new bytes are a new document. A second hash-first file with that hash is `duplicate` and is not inserted. On a first run the lower path is the new document.

Both rules agree when a file is renamed and edited in the same run. The old path is gone and the old hash is not live, so the old document becomes missing and the new path is a new document.

Changing the profile default warns once and still updates meta when no document row changes. Changing one rule's list warns once for that rule name. `--dry-run` warns too. Old events keep the identity word that wrote them. `path` and `[path, hash]` are the same list, so that change does not warn. A bad list, a template, or the word `key` stops `record status` and `record run` before the walk. Scan commands ignore the key.

A path filter observes only the selected paths. It does not mark, move, or insert anything outside that set. A filtered run can mark a selected path missing while those bytes still exist under another name. A later run with no path can move the document onto that name.

Bank2000 invoice `2026-04-25.pdf` is recorded. The next scan finds new bytes at that path, and the old bytes at `2026-04-25-copy.pdf`.

With `path`, `2026-04-25.pdf` stays the same document and gains a generation. `2026-04-25-copy.pdf` is a second document. `record duplicates` lists the old hash on both. The first document's row says current `no`.

With `hash`, the old hash moves to `2026-04-25-copy.pdf`. The new bytes at `2026-04-25.pdf` are a new document.

## History and a later output

Each change appends an event: `new`, `move`, `generation`, `vars`, `missing`, `present`, or `unmatched`. A `refresh` does not. Deleting an event is not how a revert works.

The event row also has room for a later output apply: output name, operation (`copy`, `symlink`, or `hardlink`), destination, source hash, and the previous state of that destination. No command writes that event yet. This version does not build an output tree.
