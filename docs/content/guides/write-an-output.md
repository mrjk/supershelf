# Write an output

`output` copies, symlinks, or hardlinks recorded files into a directory. The concepts are in [Output](../concepts/output.md). Record the files first. See [Record matched files](record-matched-files.md).

Add an output to that profile:

```toml
[[outputs]]
name = "books"
path = "{{ __config__.root_dir }}/output/books"
layout = "{{ vendor }}/{{ __file__.name }}"
```

`path` is rendered once. A relative path resolves from `__config__.root_dir`. `layout` runs per file. Omitted, the input-relative path is kept. `operation` omitted means `copy`.

Preview the plan. This creates no directory and no output event:

```bash
supershelf output preview
```

Write it:

```bash
supershelf output run
```

Run it again. Files that still match are omitted. `supershelf output preview` shows them as `unchanged`.

`--dry-run` prints the rows a run would write and does not write the files or an output event.

`when` is a string template. Omitted, every file that passed `kinds` is kept. `kinds` omitted means every matched kind. A file whose record status is `new` stops the command. Run `record run` before `output run`.
