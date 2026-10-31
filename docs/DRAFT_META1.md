# Draft: file metadata providers

Status: parked. This is not part of [PERFECT_CONFIG.yml](PERFECT_CONFIG.yml). Nothing here is implemented. Come back to this before writing step 2.3.3.

The goal is to read more than the filename from a kept file: PDF info, picture tags, audio tags, plus whatever a later user module knows how to read. The config schema stays as it is. There is no `vars_metadata` key. Templates keep using Jinja candidate lists.

A file is opened only when a rendered candidate calls `meta` or `exiftool`, or when the user runs `scan meta`.

## Template commands

Two commands, plus the PDF date shortcuts that already exist.

- `meta("TYPE", "FIELD", default=...)` calls one backend. `TYPE` is `pdf`, `image`, `audio`, or a name registered by a user module.
- `exiftool("FIELD", default=...)` runs the `exiftool` binary and reads one grouped tag, such as `PDF:Author` or `EXIF:DateTimeOriginal`. The command name is `exiftool`, so it stays distinct from image EXIF fields on `meta("image", ...)`.
- `pdf_cdate()` and `pdf_mdate()` stay. They are aliases of `meta("pdf", "creation_date")` and `meta("pdf", "modification_date")` and share that cache.

A user module does not become its own Jinja function. It registers a provider, and the template calls `meta` with that name. `GLOBALS` and `FILTERS` stay string in, string out.

```yaml
author:
  - '{{ meta("pdf", "author") }}'
  - '{{ meta("image", "artist") }}'
  - '{{ exiftool("PDF:Author") }}'
  - '{{ meta("pdf", "author", default="UNKNOWN") }}'
keywords:
  - '{{ meta("pdf", "/Keywords") }}'
__date__:
  - '{{ regex_time_var(date, "%Y%m%d") }}'
  - '{{ meta("pdf", "creation_date") }}'
  - '{{ meta("image", "datetime_original") }}'
  - '{{ file("ctime") }}'
```

`default` is optional.

- Omit it, and a miss fails that candidate. The next string in the list can run.
- Pass a string, and that string is returned. The candidate succeeds, so later strings in the list do not run.
- `default=""` is a successful empty string.
- A non-string `default` fails the candidate.

A bad call, an unknown type, a suffix that provider does not claim, a parse failure, a missing `exiftool` binary, or a missing or blank field fails that candidate only, unless `default` was passed. Any other exception stops the command.

## When a file is read

`scan vars` does not open file contents for metadata unless the candidate that is actually rendering calls `meta` or `exiftool`. An earlier candidate that already succeeded skips the rest, so a filename date never opens the PDF.

Each backend load runs once per provider and file hash in the process. A failed parse is cached too, so a later field does not open the file again. The suffix check uses the filename and does not parse.

`exiftool` is the same: one subprocess per file hash, then tag lookup. A template that never calls `exiftool()` never starts the binary.

## Builtin backends

Blank text after strip is a miss. The key is omitted. It is not stored as an empty string.

### pdf

Library: pypdf, already a dependency. Suffix: `.pdf`.

Documented:

- `creation_date`, `modification_date`: `YYYY-MM-DD`
- `author`, `title`, `subject`, `creator`, `producer`: stripped text

Raw: other PDF info keys, leading slash kept (`/Keywords`, `/Author`, `/CreationDate`). A documented date that cannot be parsed is omitted. The raw PDF date string can still be present under its slash key.

### image

Library: Pillow. Suffixes: `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.webp`, `.gif`, `.bmp`.

Documented:

- `datetime_original`, `datetime`: `YYYY-MM-DD` from EXIF
- `make`, `model`, `artist`, `image_description`: stripped text

Raw: EXIF tag names (`DateTimeOriginal`, `Make`, and the rest). GPS is left out of this draft. PNG text items that are strings are raw keys. The raw EXIF blob is not a field.

### audio

Library: mutagen. Suffixes: `.mp3`, `.flac`, `.ogg`, `.oga`, `.opus`, `.m4a`, `.mp4`, `.aac`, `.aiff`, `.aif`, `.wav`, `.wv`.

Documented easy tags, text as stored: `artist`, `album`, `albumartist`, `title`, `date`, `genre`, `tracknumber`. `date` stays the tag text. It is often a year, so it is not forced to `YYYY-MM-DD`.

Raw: native frame keys, such as `TPE1` for ID3 and the MP4 artist atom.

## exiftool

Separate from `meta`. No extra Python package. The binary is `exiftool` on `PATH`.

- The field is the grouped tag, such as `PDF:Author` or `EXIF:DateTimeOriginal`.
- The value is the string exiftool printed. Dates are not rewritten to `YYYY-MM-DD`.
- Run it with JSON and group names. Pass the path as an argument, not through a shell.
- Drop `SourceFile` and the `File:` group. Keep the other groups, including `Composite:`.
- Missing binary, non-zero exit, or unreadable output: `exiftool()` fails that candidate, or returns `default` when it was passed. The message tells the user to install exiftool.

`exiftool` is not a `meta` type. A user module cannot register that name.

## User providers

`config.var_modules` already imports modules before the walk. A module may also export `PROVIDERS`, next to the optional `GLOBALS` and `FILTERS`. No new config key.

A provider has:

- a name
- a suffix tuple (empty means every file is eligible)
- `load(path)` returning a mapping of strings

Return stable names already normalized, and any extra raw keys. Omit blanks. Raise `VarCandidateError` when that file has nothing to give, so the candidate fails and a later one can run. Any other exception stops the command.

A name that repeats `pdf`, `image`, `audio`, or an earlier module is a config error. Those three builtins cannot be replaced.

## scan meta

`supershelf scan meta` prints every file the walk kept. `supershelf scan meta PATH` prints that relative path only.

- `PATH` is the path relative to the input directory, same rule as `scan vars`.
- A `PATH` that no kept file has is an error. The same path in two inputs is printed twice.
- The walk is the full walk. mtime, ctime, and sha256 are read. There is no `--quick`.
- This command is allowed to be slow. `scan vars` stays lazy.
- Kept files are printed whether or not a rule matches. The command does not match rules, resolve vars, or read or write kind files. It does not create the database file or the cache file.
- Columns: `profile`, `input`, `path`, `source`, `field`, `value`. One row per present tag.
- A file with no tags adds no row and no warning.
- For each selected file, run the providers whose suffix matches, and user providers with an empty suffix list. Then run exiftool when the binary is present.
- Field order for a builtin source: documented names in the order listed above, then the other raw keys sorted. A user provider uses the order `load()` returned. exiftool tags are sorted by field name.
- When exiftool is missing, warn once, skip that source, and still print the other sources.

## Left out on purpose

- An `auto` type that guesses the format from the file
- A generated Jinja function per provider (`pdf("author")`, `invoice("number")`)
- Putting this text into `PERFECT_CONFIG.yml` until the draft is accepted
- Code, tests, and adding Pillow and mutagen
