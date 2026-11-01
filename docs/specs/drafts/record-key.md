# Record key

Status: accepted, blocked. This is not part of [behavior.md](../behavior.md). Nothing here is implemented. Move it into behavior 4.2 only when file metadata is accepted and the database schema can store it.

Behavior 4.2 links a document with `path` and `hash`. This step adds `key` to that list. The word `key` is a config error until then.

## Why it is blocked

- The template reads variables, including file metadata. Metadata is [file-metadata.md](file-metadata.md) and is still parked.
- `events.identity` accepts only `path` or `hash`. A `key` step has to be stored.
- The rendered string needs a `link_key` column on `documents` and on `events`.
- Schema version is `1`. Behavior 4.3 does not migrate it. This step is schema version `2`.

## Config

`record_key` is a template on the match rule. It is not an entry in `record_identity`.

`record_identity` may include the step `key`, once, beside `path` and `hash`. A bare word still expands as in behavior 4.2. `key` inside a list does not expand. A template string in `record_identity` stays a config error.

```yaml
match_rules:
  - name: invoice
    filename_glob: "INV_*.pdf"
    record_identity: [hash, path, key]
    record_key: "{{ invoice_number }}"
```

`record_key` is read only when the `key` step is reached. A rule that sets `record_key` and omits `key` from the list does not render it. A list that includes `key` and omits `record_key` is a config error before the walk. The message names the rule.

Leave `key` last. `[hash, key, path]` can move a document off a path that still has a file, when that file no longer renders the stored key and exactly one other file does.

`[path, key]` has no hash step. A renamed file of the same bytes is `missing` plus `new`, then the key step can still link it.

## Render

Render after variables resolve, from the same snapshot a `vars` event stores. Snapshot the string on the document at `new` and on every later event that keeps the document.

A blank render does not clear a stored key. A template failure means that file has no key. The warning names the rule and the path. The run continues. That file is not a target.

## Step

The step runs only when every earlier step declined.

It matches when the stored key is non-blank, exactly one unclaimed eligible file renders it, and exactly one such document wants it. A file is eligible when its rule includes `key` and the render equals the stored key.

- Same hash: `move`. The generation stays.
- Different hash: one `generation`. The generation increments. The path updates. There is no second event.

It declines when the stored key is blank, when zero files render it, when two or more files render it, or when the template failed. Later steps then run. When no step remains, the document is `missing` and the live files follow the new-file rule in behavior 4.2.

`[hash, path, key]` reaches this step only when the old hash is not live and the recorded path is gone. A second fetch onto the same filename is a generation from the path step. The key is not read.

Two live files can render the same key while an earlier step already matched. The key is not consulted. When the bytes differ and the path step kept the document, the other file stays its own document. One warning names the shared key.

The event stores `key` as its identity. `link_key` stores the rendered string.

## Cases

Rename plus edit. `invoice.pdf` is gone. `invoice-2026-04.pdf` has different bytes and renders the same invoice number. The hash step and the path step decline. The document gains a generation at the new path.

Same filename. `invoice.pdf` comes back with a new producer timestamp. The hash step declines. The path step generations. `record_key` is not rendered.

Key moved, path remains. The list is `[hash, key, path]`. The recorded path still has a file, that file renders a different key, and one other file renders the stored key. The document moves. This is why `key` stays after `path` in the invoice list.

Two targets. The path is gone, the hash is gone, and two files render the stored key. The step declines. The document is `missing`. Both files are `new`.

Blank. The stored key is blank. The step declines.

Flaky field. A creation date that changes on a second fetch is a bad `record_key`. Use a stable id.
