# 3 Profile database

Architecture. Index: [README](../README.md).

Behavior 4. One sqlite file per profile, stdlib `sqlite3`, schema version `2`. Foreign keys are on. Rows are never deleted. `ShelfDatabase.append_output` appends an output event. Behavior 5 is the command that calls it.

A read accepts schema `1` and schema `2`. Schema `1` has no `content_meta`. A read does not migrate it. A write migrates schema `1` to schema `2`: create `content_meta`, then set `schema_version` to `2`. Documents and events stay. Any other version is rejected. The tip names `database_file`. `content_meta` is not a cache. A metadata miss does not open this file. Behavior 2.3.3 stores payloads in `cache_file`.

## 3.1 Tables

`meta` stores `schema_version` and, after a successful `record run`, `identity`. The value is the profile default list, comma-separated, no spaces: `path,hash` or `hash,path`. A legacy `path` compares equal to `path,hash`. A legacy `hash` compares equal to `hash,path`. Behavior 4.2.

`contents` is one row per sha256. The primary key is `hash`. Many documents reference one row.

`documents` is the current projection:

- `id` integer primary key, never reused
- `presence`: `present`, `missing`, or `unmatched`
- `generation` integer, starting at 1
- `hash` references `contents`
- `input_index`, `input_path` (absolute input directory), `path` (relative, slash separators)
- `mtime` and `ctime`, the stored UTC timestamps, or null
- `match_kind`, `rule`
- `file_dir`, `file_name`, `file_stem`, `file_ext` (`archive.tar.gz` stores `gz`; no suffix stores `""`)
- `vars_json`
- `updated_at`, UTC ISO-8601

A partial unique index on `(input_path, path)` applies where `presence` is not `missing`. Two missing documents may keep the same last path.

`events` is append-only:

- `id`, `document_id`, `seq` unique per document, starting at 1
- `event`: `new`, `move`, `generation`, `vars`, `missing`, `present`, `unmatched`, or `output`
- `identity`: the first step of the list that decided this event. `path` or `hash`. A `path` list stores `path` even when the hash step performed a move.
- `recorded_at`
- the same file facts and `vars_json` as `documents`
- nullable output columns: `output_name`, `operation`, `destination`, `source_hash`, `previous_json`

Indexes: `events.hash`, `events.destination`.

`content_meta` is unused. Schema 2 still creates it, and a version 1 write still adds it, so old files open. Nothing reads or writes the rows. Columns stay: `hash` references `contents`, `driver`, `options_key`, `payload`, `error`, `extracted_at`. The metadata cache is `cache_file` in behavior 2.3.3. There is no `fs` driver.

`refresh` updates `mtime`, `ctime`, and `input_index` on the document and does not insert an event.

## 3.2 Variable snapshot

`vars_json` is one JSON object. Keys are sorted. `__file__` and `__match__` are not included. Those facts already have columns: `match_kind`, `rule`, `mtime`, `ctime`, `file_dir`, `file_name`, `file_stem`, `file_ext`, `path`, and `hash` on `contents`. The column names stay. There is no schema migration. `__date__` is included when it is set. `__profile__` and `__config__` are not included. An unset name is left out.

Each binding is `type`, `value`, `display`, and `value_sources`. `value` is the JSON form of the Python value. A float can be `12.5` while `display` is `12.50`. A difference in the name set, the type, the value, the display, or the sources is a variable change.

## 3.3 Decision order

The observed set is the walked inputs, then PATH. Documents whose input directory was not walked are left as they are. Documents outside PATH are left as they are. The database file and the cache file are ignored.

The list for each document is behavior 4.2. A file reserved in an earlier step cannot be taken later. Inside a step, documents run in id order.

1. The location still has a matched file and the hash matches. The document stays, for every list. Status is `vars`, `present`, `refresh`, or `unchanged`, in that order of precedence. `present` is the return from `missing` or `unmatched` when the variables did not change. Reserve the file.
2. The location is still in the kept walk and no rule matches. Status `unmatched`, unless it is already unmatched. The list stops. The hash is not followed. The event keeps the latest identity word.
3. Walk the remaining list. Stop at the first step that matches.
   `path` matches when the location still has a matched file. A different hash is a generation. Reserve that path. The step declines when the location is not in the kept walk.
   `hash`, and this document's list reaches it before `path`: eligibility and ownership are behavior 4.2. One eligible unreserved successor is a move. Several hash-first successors move to the lowest `(input_path, relative path)` and the others are `duplicate`. The old path is not reserved when the document leaves it. A reserved file does not make this step match. The step declines when none remain.
   `hash` after `path` declined: this document's own continuation. Any unclaimed in-scope matched file with that hash counts. The move happens only when exactly one gone document wants that hash. Several successors do not match.
   When the list is exhausted, the document is `missing` unless it is already missing.
4. Each unclaimed in-scope matched file becomes a new document, generation 1, event `new`, identity the first step of its rule list. A hash-first file whose hash is already owned is `duplicate` instead. It is not written. On a first run the lowest path of a shared hash is the new document.

A move keeps the generation number. A generation increments it. A move or a generation stores the new snapshot on that event and does not also append `vars`.

`duplicate` is a status word. It is not an event and not a presence. The plan prints it. The write skips it.

Location changes are written by first marking the moving documents `missing`, so a swap of two paths can commit under the partial unique index, then writing the final presence and path.

`duplicates` on the status row counts other in-scope present documents with that hash, plus extra live files reported as `duplicate` for that hash. Documents left out of scope still count. A never-inserted copy is not in `record duplicates`.

## 3.4 Output event

Behavior 5 calls `ShelfDatabase.append_output`. The method inserts one event and does not change the document projection. `operation` is `copy`, `symlink`, or `hardlink`. `previous_json` is the revert payload:

```json
{"existed": false, "ours": false}
```

When this profile wrote the previous destination, `ours` is true and the object also has `operation` and `source_hash` from that earlier event. `existed` true and `ours` false means a file was already there and this profile did not write it. Behavior 5.3 chooses which of these objects to store.

## 3.5 Open and errors

A missing file opened for reading is an empty previous state. The file is not created. A real read of an existing file uses SQLite read-only mode.

`record run` opens for write when a row would change, or when the stored identity rule differs and the file already exists. `record status` does not. `--dry-run` does not create the file and does not migrate schema `1`. A `meta()` miss does not open the file. The identity key is updated in the record transaction. A failure rolls that transaction back. The schema created for a new file stays.

`RecordConfigError` is a bad `record_identity` word or list, on the flag, the environment variable, the profile, or a match rule. Exit 2. `DatabaseError` is a bad file, a wrong schema version, a parent that is not a directory, or a lock. Exit 1. The tip names a fix the user can make.

Two copies, path. Both documents reference the same `contents.hash`. `record duplicates` groups that hash.

Two copies, hash. One document references `contents.hash`. The extra path is a `duplicate` status row and has no document row.

Collision under `path`. The generation event keeps the document id. The new document's `new` event stores the old hash. The duplicate query shows current `no` on the generation that was replaced and current `yes` on the new document.

Collision under `hash`. The move keeps the document id and the generation. The new bytes are a new document. A second hash-first file with the old hash is not inserted.

Output slot. After `append_output`, `events` has one `output` row and the document's presence, hash, and generation are unchanged.
