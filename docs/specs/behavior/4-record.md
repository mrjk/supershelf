# 4 Record

Behavior. Index: [README](../README.md).

`supershelf record` stores matched files in the profile sqlite file from `config.database_file`. The schema, the decision order, and the output-event slot are architecture 3. One file per profile. Profiles do not share rows. `cache_file` stays unused. This step does not write an output tree. Behavior 5 does.

`scan vars`, `record run`, `data feed`, and `data show` create it when `meta()` runs and the cache misses. `--dry-run` does not. `scan files`, `scan kinds`, `scan inspect`, `schema`, `profiles`, and `data prune` do not. `record run` also creates it when a document row would change. `data feed` and `data show` do not insert a document or an event. A feed prompt answer of no can leave the cache, and a schema 1 file already migrated to schema 2.

The walk is the full walk from 2.1.2. There is no `--quick`. Variables resolve as in 2.3.1, including kind-file reads. `record` does not call the kind-file commit, so it does not create or append a kind file.

## 4.1 Commands

`PATH` is the optional scan selector from 2.1.1. A value that matches no kept file and no in-scope document stops `record status` and `record run`. `record history` and `record duplicates` do not scan. A selector that matches nothing there prints no rows.

Columns are a clak table.

### record status

- supershelf record status [PATH]
- Prints every in-scope live matched file, plus every in-scope document this scan would mark missing or unmatched.
- Writes nothing. A missing sqlite file stays missing. An existing file is opened read-only.
- Columns: profile, input, path, status, hash, generation, kind, rule, duplicates.
- input is the 1-based index. path is relative to the input directory.
- status is `new`, `generation`, `move`, `vars`, `missing`, `present`, `unmatched`, `refresh`, `unchanged`, or `duplicate`.
- duplicates is how many other in-scope present documents share that hash, plus how many extra live files this plan reports as `duplicate` for that hash.
- A `duplicate` row is an extra live file. path is that file. The hash is the owner's hash. It is not inserted. `record history` has no row for it.
- `--record-identity` is a word or a comma-separated list. 4.2.

### record run

- supershelf record run [PATH]
- Prints the status rows whose status is not `unchanged`, then writes every printed row except `duplicate`.
- `--dry-run` prints those rows and writes nothing. It does not create the sqlite file, its parents, or a journal.
- A run with no changes does not create a missing sqlite file.
- A run that prints only `duplicate` rows writes nothing and does not create a missing sqlite file.
- A run with changes creates parent directories, then writes one transaction per profile.
- A later profile can commit after an earlier profile already committed.
- `--record-identity` is the same flag as `record status`.

### record history

- supershelf record history [PATH]
- Reads events in id order. It does not scan and does not write.
- No database means no rows.
- PATH matches a document when any of its event paths, or its current path, equals the selector or starts with it. The command then prints every event for that document, so a move is still found from the old path.
- Columns: profile, document, seq, event, identity, input, path, hash, generation, kind, rule, at.

### record duplicates

- supershelf record duplicates [PATH]
- Reads the database. It does not scan and does not write.
- A hash is listed when two or more documents have carried it on any event.
- PATH filters on the document's current relative path.
- Columns: profile, hash, document, current, path, generation.
- current is `yes` when that hash is the document's current hash, and `no` when the hash is an earlier generation.

## 4.2 Link

- A document has a stable integer id. Rows are never deleted. Revert is a later walk of the events.
- The location is the absolute input directory plus the relative path. The input index is stored. Reordering inputs is not a move. A missing input directory leaves that input's documents untouched.
- `record_identity` is one step or a list of steps. The steps in this version are `path` and `hash`.
  A list is tried in order. The first step that matches links the document. Later steps do not run.
  A step that declines does not link and does not claim a file.
- A bare word expands. `path` means `[path, hash]`. `hash` means `[hash, path]`.
  An item inside a list does not expand. `[path]` is the path step only. `[hash]` is the hash step only.
  `path` and `[path, hash]` are the same list. `hash` and `[hash, path]` are the same list.
- The packaged default is `path`, which is `[path, hash]`.
  Precedence for the profile default is `--record-identity`, then `SUPERSHELF_RECORD_IDENTITY`, then `config.record_identity`, then `path`.
  A match rule's `record_identity` wins over that default. Omitted or null on the rule inherits the default.
  The flag and the environment variable are a word or a comma-separated list. Spaces around a comma are ignored.
  The profile value and the rule value are a string or a list of strings.
  Kind files do not carry this key. Two rules may share a kind and use different lists.
- A bad value stops `record status` and `record run` before the walk. Exit 2. Nothing is written.
  Bad: a different case, an empty string, an empty list, an empty comma item, a repeated step, a step other than `path` or `hash`, or a template string.
  The word `key` is reserved and is bad in this version. drafts/record-key.md.
  The message names the flag, the environment variable, `config.record_identity`, or the match rule.
- The list for a document is the list of the rule that matches the live file at the recorded path, when that file exists.
  Otherwise it is the list of the rule named on the document, when that rule still exists.
  Otherwise the latest event's identity word is expanded.
  A file that is still in the walk and matches no rule does not change that word. The unmatched event stores the latest event's identity.
- `events.identity` stores the first step of the list used for that document. The column accepts `path` or `hash` only.
  A rename under the word `path` still stores `path`.
  `meta.identity` stores the profile default as a comma-separated list with no spaces: `path,hash` or `hash,path`.
  A stored `path` compares equal to `path,hash`. A stored `hash` compares equal to `hash,path`.
  A write that updates meta stores the normalized list.
- The profile default warns once per profile when its normalized list differs from `meta.identity` under that comparison.
  A document warns once per rule name per run when its resolved list differs from the expansion of its latest event identity.
  The message names the profile, and the rule when the warning is for a rule, plus the old list and the new list.
  Old events stay. `--dry-run` warns. A profile-default change with no document row to write still updates meta.
  A rule-list change with no document row to write does not write.
  Changing `path` to `[path, hash]`, or `hash` to `[hash, path]`, does not warn.
- `path` matches when the recorded path still has a live matched file.
  The same hash stays. Status is `vars`, `present`, `refresh`, or `unchanged`, in that order.
  A different hash is a generation. The old bytes elsewhere are not this document.
  The step declines when the path is not in the kept walk.
- The recorded path is still in the kept walk and no rule matches. Status is `unmatched`, once. The list stops. The hash is not followed. The event stores the latest identity word.
- `hash` matches when at least one eligible, unreserved, in-scope live file has the document's hash.
  Hash-first means this document's list reaches `hash` before `path`, or has no `path` step.
  Other files count for a hash-first document only when their own lists are hash-first.
  A path-first file is not absorbed. The same sha256 can be an invoice document and a draft document.
  After an earlier step declined, the hash step is this document's own continuation.
  It then sees any unclaimed in-scope matched file with that hash.
  It declines when no such file remains.
- Hash-first ownership. Among in-scope present documents that are hash-first and share a hash, the lowest id owns that hash.
  A document id is not fused into another. Rows are never deleted. Switching the list to `hash` does not merge ids.
  The owner's recorded path still has that hash: the owner stays. Every other unclaimed hash-first file with that hash is `duplicate`.
  The owner's path is gone, or now has different bytes, and exactly one unclaimed eligible file has the hash: `move`. Generation unchanged.
  Several eligible files: `move` to the lowest `(input_path, relative path)`. The others are `duplicate`.
  One warning names the document, the hash, the chosen path, and the other paths. `--dry-run` warns too.
  Bytes left at the old path are a different hash and follow the new-file rule.
  A later copy is `duplicate` of the lowest owner. It is not a new document.
  On a first run, the lowest `(input_path, relative path)` among hash-first files that share a hash is `new`. The others are `duplicate` of that document and are not written.
- A reserved file cannot be claimed again. Same path and same hash is reserved first, for every list.
  A path step that generations reserves that path.
  A hash follow cannot take a reserved path. A reserved file does not make the hash step match.
  When the only copies are reserved, the hash step declines. The path step then runs if the recorded path still has a live file.
- Path-first, path gone. Exactly one unclaimed in-scope matched file has the hash, and exactly one in-scope document whose path is gone wants it: `move`.
  Several successors: do not guess. The document is `missing`. Each of those files is `new`.
- `[path]` does not follow a renamed file. The same bytes at a new path are `missing` plus `new`.
  `[hash]` does not keep an in-place byte change. The same path with new bytes, and the old hash nowhere, is `missing` plus `new`.
- The word `path` and the word `hash` agree when the old path is gone and the old hash is not live.
  The old document is `missing`. The new path is `new`.
- `record duplicates` reads stored documents. It does not scan. A file that was never inserted does not appear there.
  The `duplicate` status row is the report for that file.
- A file that leaves the walked inputs becomes `missing`. The row and its events stay. A second run that still does not see it does not append another missing event.
- A file that is still in the walk, and that no rule matches, becomes `unmatched`. The last hash, kind, rule, and variables stay. A never-recorded unmatched file is not inserted. A later match appends `present`, `vars`, or `generation`.
- PATH limits the observed set to matching paths in inputs that were walked. The run does not mark, move, or insert anything outside that set. A filtered run can mark a selected path missing while those bytes still exist outside the filter. A full run reconciles that.
- An mtime, ctime, or input-index change updates the current row and does not append an event. The status word is `refresh`.
- A kind, rule, or variable change appends `vars` and does not bump the generation. A generation or a move carries the new variable snapshot in that one event.
- Coming back from `missing` or `unmatched` with the same hash and the same variables appends `present`. A hash change on that return is `generation`. A variable change with the same hash is `vars`.

### Cases

Two copies, path. `a.pdf` and `b.pdf` have the same sha256. `record_identity` is `path` or `[path, hash]`. The run stores two documents. `record duplicates` lists that hash twice, and both rows say current `yes`.

Two copies, hash. The same files. `record_identity` is `hash` or `[hash, path]`. `a.pdf` stays the document. `b.pdf` is `duplicate` and is not inserted. A second run prints `duplicate` again and writes nothing. `record duplicates` does not list `b.pdf`.

First run, hash. No document yet. `a.pdf` and `b.pdf` share a hash and both rules are hash-first. The lower `(input_path, relative path)` is `new`. The other is `duplicate`.

Move. A recorded file leaves its path and the same hash is the only live file at a new path. The word `path` and the word `hash` both move. The generation number stays. `record history` with the old path still prints the move. The event stores the first step of the list, so a `path` list still stores `path`.

Generation. New bytes replace the file at the recorded path, and the old hash is not live anywhere in scope. The word `path` and the word `hash` both gain a generation. `[hash]` does not: the document is `missing` and the file is `new`.

Collision, path. The old path now has new bytes, and the old hash is live at a new path. The list is path-first. The old path keeps the document and gains a generation. The new path is a second document. The shared hash shows up in `record duplicates`. The older document's row has current `no`.

Collision, hash. The same files. The list is hash-first. The old hash moves to the new path. The new bytes at the old path are a new document. Two files still have the old hash: the document moves to the lowest path, and the other is `duplicate`. One warning names both paths.

Hash onto a stay. Document 1 at `a.pdf` and document 2 at `b.pdf` share a hash. `a.pdf` is replaced. The list is hash-first. `b.pdf` was reserved by the same-hash stay. The hash step declines. Document 1 gains a generation at `a.pdf`. Document 2 stays. The run commits.

Rename plus edit. The old path is gone and the new path has a different hash. The old document is missing. The new path is a new document. `path` and `hash` agree. `[path, key]` is that case too, and `key` is rejected in this version.

Path only. The list is `[path]`. The old path is gone and one new path has the same hash. The document is `missing`. The new path is `new`.

Mixed rules. The invoice rule is `[hash, path]`. The draft rule is `[path]`. Both files have the same sha256. They stay two documents. The draft is not `duplicate`.

No merge. Two documents already store the same hash. This run uses `hash`. Both stay. A third hash-first file is `duplicate` of the lower id.

Two wanters. Two path-first documents are gone and one file has their hash. Both are `missing`. The file is `new`.

Several hash successors, path gone. One hash-first document is gone. Two hash-first files have its hash. The document moves to the lower path. The other file is `duplicate`.

Unmatched. The file is still in the input and no rule matches. The document becomes unmatched. The row stays. The event keeps the previous identity word. A later match with the same bytes appends `present`.

Filter. PATH names one file that disappeared. Another input still has those bytes. The named document becomes missing. The other input's document is not moved and is not marked missing. A run with no PATH moves the document onto the surviving path when the move rule matches.

Refresh. Only mtime changes. Status is `refresh`. History gains no row.

Rule change. The file is still at its path with the same hash. The matched rule name changes. Status is `vars`. The event stores the first step of the new list. A change from `path` to `hash` warns once for that rule.

Identity switch. The database was written with `path`. This run passes `--record-identity hash`. The command warns. Old events keep `path`. New events store `hash`. Meta stores `hash,path`.

Same list. Meta stores `path`. The profile value is `[path, hash]`. Those compare equal. There is no warning.

Bad list. A rule sets `HASH`, `""`, `[]`, `[path, path]`, `{{ author }}`, or `key`. The command stops before the walk. Exit 2. Nothing is written.

## 4.3 Writes

- A resolve error writes nothing.
- A matched file whose absolute path is the profile sqlite file is skipped, with a warning. That location is left out of this run.
- The sqlite parent must be a directory. A parent that is a file stops the command and names `database_file`.
- A path that exists and is not a supershelf database stops the command. The tip says to point `database_file` at a new path.
- Schema version is `1`. A different version stops the same way. This step does not migrate.
- A locked file stops the command. The tip says to run the command again.
- `--dry-run` on `record run` reports the rows that would change and creates nothing.
- `record status`, `record history`, and `record duplicates` do not write. Passing `--dry-run` to them changes nothing.
