# 4 Import

Behavior. Index: [README](../README.md).

`supershelf db import` stores matched files in the profile sqlite file from `config.database_file`. There is no `record` command. There is no `scan import` command. The schema, the decision order, and the output-event slot are architecture 3. One file per profile. Profiles do not share rows. User vars stay in `vars_json`. The sqlite schema does not follow the user's config. Architecture 3.2. `cache_file` is the metadata cache in behavior 2.3.3. This step does not write an output tree. Behavior 5 does. This step does not write a kind file. Behavior 3 does.

`scan vars`, `scan feeds`, and `db import` create `cache_file` when `meta()` runs and the cache misses. `--dry-run` does not. `scan files`, `scan match`, `inspect`, `profiles`, `db show`, and `output` do not. `db import` creates `database_file` when a document row would change. `scan` does not. `scan feeds` does not insert a document or an event.

The walk is the full walk from 2.1.2. There is no `--quick`. Variables resolve as in 2.3.1, including kind-file reads. The kind-file row is chosen by the first step of `record_identity`, as in 2.3.2. The `--record-identity` flag does not change that key.

## 4.1 Commands

`PATH` is the optional scan selector from 2.1.1. A value that matches no kept file and no in-scope document stops `db import`. Columns are a clak table.

`supershelf db import [PATH]`

- Prints the rows this run would write, then writes every printed row except `duplicate`.
- A row is printed when this run would append an event or update the current document row. `unchanged` is omitted. A `missing` or `unmatched` document that would not append another event is omitted. `db show` still lists that document. 7.
- `--dry-run` prints the rows `db import` would print and writes nothing. It does not create the sqlite file, its parents, or a journal. It does not migrate schema `1`.
- A run with no changes does not create a missing sqlite file.
- A run that prints only `duplicate` rows writes nothing and does not create a missing sqlite file.
- A run with changes creates parent directories, then writes one transaction per profile.
- A later profile can commit after an earlier profile already committed.
- Columns: profile, input, path, status, hash, generation, kind, rule, duplicates.
- input is the 1-based index. path is relative to the input directory.
- status is `new`, `generation`, `move`, `vars`, `missing`, `present`, `unmatched`, `refresh`, `unchanged`, or `duplicate`.
- duplicates is how many other in-scope present documents share that hash, plus how many extra live files this plan reports as `duplicate` for that hash.
- A `duplicate` row is an extra live file. path is that file. The hash is the owner's hash. It is not inserted. It has no event.
- `--record-identity` is a word or a comma-separated list. 4.2.
- Events have no command. The sqlite file keeps them. `db show` prints the current document row, not the event list.

`db import PATH` observes only that path. It can mark the selection `missing` while the same bytes still exist outside the filter. A later full `db import` reconciles that. Bare `db import` is the full walk.

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
  Kind files do not store this key. The kind-file row identifier is the first step. 2.3.2.
  The `--record-identity` flag does not change that key.
  Two rules may share a kind and use different lists.
- A bad value stops `db import` and `scan files` before the walk. Exit 2. Nothing is written.
  A bad config or environment value also stops the scan steps that resolve it. 2.3.2.
  `scan match` and `inspect scan kinds` do not resolve it. 2.2.
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
- A file that was never inserted does not appear in `db show`.
  The `duplicate` status row is the report for that file.
- A file that leaves the walked inputs becomes `missing`. The row and its events stay. A second run that still does not see it does not append another missing event.
- A file that is still in the walk, and that no rule matches, becomes `unmatched`. The last hash, kind, rule, and variables stay. A never-recorded unmatched file is not inserted. A later match appends `present`, `vars`, or `generation`.
- PATH limits the observed set to matching paths in inputs that were walked. The run does not mark, move, or insert anything outside that set. A filtered run can mark a selected path missing while those bytes still exist outside the filter. A full run reconciles that.
- An mtime, ctime, or input-index change updates the current row and does not append an event. The status word is `refresh`.
- A kind, rule, or variable change appends `vars` and does not bump the generation. A generation or a move carries the new variable snapshot in that one event.
- When the clock and the variables both change, `scan files` still prints `refresh`. `db import` prints `vars`. The import row carries the new clock. The identity comparison and the import comparison are separate. 2.1.3.
- Coming back from `missing` or `unmatched` with the same hash and the same variables appends `present`. A hash change on that return is `generation`. A variable change with the same hash is `vars`.

### Cases

Two copies, path. `a.pdf` and `b.pdf` have the same sha256. `record_identity` is `path` or `[path, hash]`. The run stores two documents. `db show` lists both.

Two copies, hash. The same files. `record_identity` is `hash` or `[hash, path]`. `a.pdf` stays the document. `b.pdf` is `duplicate` and is not inserted. A second run prints `duplicate` again and writes nothing. `db show` does not list `b.pdf`.

First run, hash. No document yet. `a.pdf` and `b.pdf` share a hash and both rules are hash-first. The lower `(input_path, relative path)` is `new`. The other is `duplicate`.

Move. A recorded file leaves its path and the same hash is the only live file at a new path. The word `path` and the word `hash` both move. The generation number stays. The move event keeps the old path. `db show` prints the current path. The event stores the first step of the list, so a `path` list still stores `path`.

Generation. New bytes replace the file at the recorded path, and the old hash is not live anywhere in scope. The word `path` and the word `hash` both gain a generation. `[hash]` does not: the document is `missing` and the file is `new`.

Collision, path. The old path now has new bytes, and the old hash is live at a new path. The list is path-first. The old path keeps the document and gains a generation. The new path is a second document. Both documents share the hash. The older document's event for that hash is no longer current.

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
- Schema version is `2`. A write migrates schema `1` to schema `2`, as architecture 3.5. A read does not migrate. Any other version stops the command. The tip says to point `database_file` at a new path.
- A locked file stops the command. The tip says to run the command again.
- `--dry-run` on `db import` reports the rows that would change and creates nothing.
- `db show` does not write. Passing `--dry-run` to it changes nothing.
