# 2.3.3 File metadata

Status: the shipped drivers live in [behavior.md](../behavior.md) 2.3.3, and `content_meta` lives in [architecture.md](../architecture.md) section 3. This draft keeps `pdfinfo`, `mutool`, `ffprobe`, `mediainfo`, `zipinfo`, and `strings`.

The goal is to read metadata, and text, from a kept file by calling an external program or a small Python driver. The result is an ordinary variable. There is no `metadata_fields` key.

`pdf_cdate()`, `pdf_mdate()`, and `file()` stay as they are until a later migration. They keep their own in-process cache. They do not read `content_meta`.

## Out of this step

- A match-rule `when`. Matching stays on the filename.
- `scan meta`.
- Pillow, mutagen, and a `tika` builtin. Apache Tika is a Java server. Call it through `supershelf.meta_driver` or a custom module.
- A driver named `ffmpeg`. The media probe is `ffprobe`.
- Rewriting `pdf_cdate()` and `pdf_mdate()` as calls to the `pdf` driver.
- A size cap on tool stdout.

## When a driver runs

`scan files` and `scan kinds` do not call drivers and do not open the database. `--quick` stays on `scan files` only.

`scan vars` and `record run` call a driver only while a var candidate renders `meta()`. The layers stay facts, then `default_vars`, then rule `vars`, then the kind file, then overrides. A profile that never calls `meta()` does nothing new.

A candidate that already succeeded skips the rest of the list, so a filename group written first never opens the file. A kind-file cell is a literal. It does not call `meta()`. An override template can.

The source label stays the layer that wrote the name: `default`, `rule:<name>`, `kind:<path>`, or `override:<path>`. There is no `meta:` label.

Locked internals stay locked. `__date__` may be set by a candidate. The result must be `YYYY-MM-DD` or that candidate misses.

Var resolution still requires sha256. That hash is the cache key. A file with no sha256 fails with the existing missing-metadata error before any driver runs.

## meta()

`meta(driver, field)` is one Jinja command. Use it in `default_vars`, rule `vars`, and overrides. `field` may be omitted only when that driver has a single text result (`text`). Omitting it on any other driver fails the candidate.

```yaml
default_vars:
  author:
    - '{{ author }}'
    - '{{ meta("pdf", "author") }}'
    - "UNKNOWN"
```

While `author` renders, `{{ author }}` sees the previous layer. A missing group fails that candidate. The next candidate calls the driver.

- An unknown driver name stops the command. When both arguments are string literals, that check happens when the template is loaded.
- A disabled driver, a file the driver does not accept, a missing field, a blank value, a timeout, a non-zero exit, or undecodable stdout fails that candidate only. The next string runs.
- `VarCandidateError` from a custom driver fails that candidate only.
- Any other exception stops the command.
- If every candidate in the layer misses, the layer does not write the name. An earlier value stays. `vars_schema.mandatory` after the last layer stops the file when the value is still unset.
- A last literal such as `"UNKNOWN"` forces a text value. This is the existing candidate rule.

A blank value is empty after strip. `text` vars still treat `""` from a literal candidate as a value. A driver that returns blank fails the candidate. It does not store `""`.

## metadata_driver

`metadata_driver` is a top-level profile key, next to `default_vars` and `match_rules`. It is not under `config`. `default.toml` stays one `[config]` table and does not list drivers.

Omitted, null, and `{}` mean no overrides. Every builtin keeps the enable flag on its class. A `metadata_driver` table inside `config` stops the command. The message says to move the key to the top level.

The value is a mapping of name to mapping. A present table overlays those names only. Omitted builtins stay at the class default. This is not a replacement of the whole catalog.

Each entry is one of three kinds:

- Builtin overlay. The key is a builtin name and `driver` is omitted. An unknown option for that builtin is a config error.
- Generic command. `driver` is `supershelf.meta_driver`. The key is the name `meta()` uses. Several entries may use this module. Each has its own command.
- Custom module. `driver` is an import path, such as `my_code.supershelf.driver`. The key is the name `meta()` uses.

A key that is not a builtin and has no `driver` is a config error. A `driver` value that cannot be imported is a config error at load. Setting `driver` on a builtin name replaces that builtin for this profile. The builtin class of that name is not called.

Reserved keys on every entry: `driver`, `enable`, `timeout`, `ext`, `mime`. Supershelf reads those. For a builtin or for `supershelf.meta_driver`, any other key must be one that driver declares. For a custom module, any other key is passed through in `options`.

`var_modules` still provides `GLOBALS` and `FILTERS`. It does not register drivers.

## Enable

`enable` is the word `auto`, `true`, or `false`. A boolean `true` or `false` is that word. Any other value is a config error. Omitted means `auto`, except where a builtin class sets another default.

- `auto`: check once, on the first call. A miss fails that candidate and is logged once. Later files do not check again.
- `true`: the same check at profile load. A miss stops the command.
- `false`: the driver is never called. A candidate that names it misses.

What the check looks up:

- A builtin tool: the binary on `PATH`.
- `supershelf.meta_driver`: `command`, by the rule below.
- A custom module: `available(options)`.

`fs` and `pdf` have no binary. They ignore `enable`.

`timeout` is a number of seconds, greater than 0. Omitted means 30. `0` and below are config errors. `fs` and `pdf` do not accept `timeout`. Setting it on them is a config error.

## Which files a driver accepts

The suffix is the file's last suffix, without the leading dot, compared case-insensitively. `archive.tar.gz` is `gz`. A leading-dot name such as `.gitignore` has no extension. A config item is `pdf`, not `.pdf`. A leading dot on a config item is stripped.

`ext` and `mime` on an entry replace that driver's class lists. An omitted key keeps the class list. An empty list is a real empty list. A string is a one-item list. Items must be strings.

1. Test the extension against `ext`. A hit accepts the file. Mime is not read.
2. If the file has no extension, or the extension does not match, test the mime type against `mime`. A hit accepts the file.

A driver with neither list accepts every file. `exiftool` is that case. A driver with only `ext` rejects a miss and does not probe mime. A driver with only `mime` always reaches step 2.

The probe is `file --mime-type --brief`, the path passed as one argument, once per hash, in memory for the process. It runs only when a driver reaches step 2 and that driver has a mime list. The MIME type for PDF is `application/pdf`. If `file` is not on `PATH`, the mime test does not match and one warning is logged. Extension hits still accept the file. The probe is not stored in `content_meta`.

A driver that does not accept the file does not spawn a program and does not write a cache row.

## supershelf.meta_driver

`supershelf.meta_driver` runs one program, or one executable script, and parses stdout into a string map. Supershelf executes that file. Arguments are argv. A shell script is the `command` path and runs by its shebang. Pipes and shell syntax belong inside the script.

`command` is required.

- A value with a path separator is a file path. A relative path is resolved from the profile directory (`__profile_dir__`). The check requires the path to exist and be a file.
- A value with no separator is looked up on `PATH`.

`arguments` is a string, a list of strings, or omitted. Omitted means the program is run with no extra arguments, so the program sees no path unless the user included one. The string form is split with `shlex`. A bad quote is a config error at load. The list form is already one argv element per item.

Placeholders are replaced after the split. A path with spaces stays one argument when `%p` is its own token.

- `%p` absolute path
- `%r` path relative to the input, `/` separators
- `%n` filename
- `%s` stem
- `%e` extension without the dot
- `%h` sha256
- `%c` ctime, the stored UTC ISO-8601 timestamp
- `%m` mtime, the stored UTC ISO-8601 timestamp
- `%d` absolute directory of the file
- `%%` one percent sign

Any other `%` token is a config error at load. Other tokens are literal arguments (`--lang`, `eng`).

`output_format` is required: `yaml`, `toml`, `ini`, or `shell`. Stdout is the cached payload. Parsing happens in process. stderr is logged at debug and is not parsed.

- `yaml`: `yaml.safe_load`. The document must be a mapping. Nested mappings flatten with `.`, so `info.author` is the field. Scalars become strings. A list value is skipped. Null is skipped.
- `toml`: `tomllib`. The same flatten rule. A duplicate key is a parse error.
- `ini`: `configparser`, interpolation off. A key in a section is `section.key`. A key in the default section is `key`.
- `shell`: one `key=value` line. Blank lines and lines whose first non-space character is `#` are ignored. A leading `export ` is stripped. One matching pair of quotes around the value is stripped. The line is not executed. The key matches `[A-Za-z_][A-Za-z0-9_.]*`. A repeated key keeps the last value.

`meta("covers", "author")` looks up `author` in that map. A missing key, a blank value, a non-zero exit, a timeout, or a parse error fails the candidate. The failure is cached: `error` is set, `payload` is null. The next file with the same hash does not run the program again.

`options_key` includes the driver identity, `command`, the argument template, `output_format`, and the class `cache_epoch`. `ext`, `mime`, `enable`, and `timeout` are not part of it.

## Custom module

`driver = "my_code.supershelf.driver"` imports that module. The module exports `DRIVER`, one object with the methods below. `driver = "my_code.supershelf.driver:InvoiceDriver"` loads that class and calls it with no arguments. The config key is the name passed to `meta()`.

A module that exports neither `DRIVER` nor, when `:Class` is used, that class, is a config error. An import failure is a config error.

## Driver object

Builtins live in the package. `supershelf.meta_driver` is the generic command class. A custom module is loaded only when a profile names it.

A driver provides:

- `available(options) -> bool`. The enable check. Not called per file.
- `accepts(file, options) -> bool`. Extension, then mime. It does not parse the file.
- `extract(file, field, options) -> str`. One field. Raise `VarCandidateError` when the field is missing or blank. Parse once per hash and reuse the bag for later fields in the process.

The subprocess helper executes the program directly, passes the path as one argument, applies `timeout`, and reads stdout as UTF-8. Undecodable output fails the candidate. The same helper runs builtin tools and `supershelf.meta_driver`.

## Builtin drivers

Class defaults. They are not rows in `default.toml`.

- `fs`: always on. No `ext`, no `mime`, no cache row, no second stat. Fields are the strings the walk already stored: `ctime`, `mtime`, `hash`, `name`, `stem`, `ext`, `path`, `dir`. `ext` has no dot. `path` and `dir` use `/`. `dir` is empty when the file sits in the input directory.
- `pdf`: always on. `pypdf`, already a dependency. `ext: [pdf]`, `mime: [application/pdf]`. Fields: `creation_date` and `modification_date` as `YYYY-MM-DD`, plus `author`, `title`, `subject`, `creator`, `producer`. A date that cannot be parsed is a missing field. The parsed map is cached as JSON. This does not change `pdf_cdate()`.
- `exiftool`: `auto`. Binary `exiftool`. Neither `ext` nor `mime`. One JSON run per hash: `exiftool -json -G`, the path as one argument. The field is the grouped tag, such as `PDF:Author`. Drop `SourceFile` and every key in the `File:` group. Keep the other groups, including `Composite:`.
- `pdftotext`: `auto`. Binary `pdftotext`. `ext: [pdf]`, `mime: [application/pdf]`. Argv is `pdftotext -q -enc UTF-8`, the path, then `-`. The only field is `text`, and it may be omitted. The value is stdout.
- `pdfinfo`: `auto`. Binary `pdfinfo`. `ext: [pdf]`, `mime: [application/pdf]`. Argv is `pdfinfo` and the path. A line `Label: value` stores `Label` as the field. The value is the text after the colon, stripped. Dates are not rewritten.
- `mutool`: `auto`. Binary `mutool`. `ext: [pdf]`, `mime: [application/pdf]`. Argv is `mutool info` and the path. The only field is `text`.
- `ffprobe`: `auto`. Binary `ffprobe`. Argv is `ffprobe -v quiet -print_format json -show_format -show_streams` and the path. The field is a dotted path into the JSON. An array index is a decimal segment: `streams.0.codec_name`.
- `mediainfo`: `auto`. Binary `mediainfo`. Argv is `mediainfo --Output=JSON` and the path. The field is a dotted path, same rule as `ffprobe`.
- `zipinfo`: `auto`. Binary `zipinfo`. `ext: [zip]`, `mime: [application/zip]`. Argv is `zipinfo -1` and the path. The only field is `text`.
- `strings`: default `false`. Binary `strings`. Neither `ext` nor `mime`. Argv is `strings` and the path. The only field is `text`. The user opts in. It matches every file.

`ffprobe` and `mediainfo` use these lists. A hit on either list accepts the file.

- `ext`: `mp3`, `flac`, `ogg`, `oga`, `opus`, `m4a`, `aac`, `aiff`, `aif`, `wav`, `wv`, `mp4`, `m4v`, `mkv`, `webm`, `avi`, `mov`, `mpg`, `mpeg`
- `mime`: `audio/mpeg`, `audio/flac`, `audio/ogg`, `audio/opus`, `audio/mp4`, `audio/aac`, `audio/aiff`, `audio/wav`, `audio/x-wav`, `video/mp4`, `video/x-matroska`, `video/webm`, `video/x-msvideo`, `video/quicktime`, `video/mpeg`

`fs`, `pdf`, `exiftool`, `pdftotext`, and `supershelf.meta_driver` are shipped. Their rules are behavior 2.3.3. The other builtins use the same helper and can follow in a later review. Their argv above is the contract when they are added. `strings` stays default `false`.

## Cache

The cache stores raw tool stdout, or the `pdf` driver's JSON map. It does not store the finished variable. One row per content hash, driver name, and `options_key`. The driver name is the profile key (`exiftool`, `covers`). Field lookup is in process from that payload.

`contents` stays the file table, one row per sha256. New table:

```sql
CREATE TABLE content_meta (
  hash TEXT NOT NULL REFERENCES contents(hash),
  driver TEXT NOT NULL,
  options_key TEXT NOT NULL,
  payload TEXT,
  error TEXT,
  extracted_at TEXT NOT NULL,
  PRIMARY KEY (hash, driver, options_key)
);
```

- Schema version becomes `2` when this ships. A schema `1` file is upgraded in place: create `content_meta`, then set `schema_version` to `2`. Document rows and events are unchanged. Any other version is still rejected.
- This draft shipped as schema `2`. [record-key.md](record-key.md) takes the next version and includes `content_meta`.
- Insert `contents` with the existing `INSERT OR IGNORE` before the cache row, so the foreign key holds. A hash may exist before any document. `record run` still links documents at that hash.
- A success stores `payload` and a null `error`. A failure stores `error` and a null `payload`.
- `options_key` includes `cache_epoch` from the class. A parser change bumps that constant and misses old rows. There is no TTL. Deleting the sqlite file is the refresh. Old hashes are kept.
- The process keeps the same key in memory, per profile, so several fields share one payload before the write.
- `fs` does not write a row. A driver that does not accept the file does not write a row.
- `scan vars` and `record run` create `database_file` when a driver runs and the cache misses. That write does not insert a document or an event. `scan files`, `scan kinds`, `schema`, and `profiles` do not create the file.
- `--dry-run` reads a cache that already exists. It does not create the file, does not migrate schema `1`, and does not write cache rows. An uncached dry run still calls the tool. A schema `1` file on a real run is migrated before the cache write.
- A database that holds only `contents` and `content_meta` is valid. Documents may be absent.
- The same hash on two paths runs the tool once. The second path reads the cache.
- A variable whose value is the full `pdftotext` body is stored again in `documents.vars_json`. The cache holds the payload either way. Short fields stay the cheap path.

## Examples

Builtin overlay. `exiftool` is off, so that candidate misses and `pdf` runs. `author` keeps a regex group when one was captured. The invoice rule replaces `author` for that kind. Other kinds keep the `default_vars` value. `report.pdf` matches `pdf` on extension, so `file` is not called.

```yaml
metadata_driver:
  exiftool:
    enable: "false"
  pdftotext:
    enable: auto
    timeout: 30

default_vars:
  author:
    - '{{ author }}'
    - '{{ meta("exiftool", "PDF:Author") }}'
    - '{{ meta("pdf", "author") }}'
    - "UNKNOWN"
  issued:
    - '{{ meta("pdf", "creation_date") }}'

match_rules:
  - name: invoice
    kind: invoice
    filename_glob: '*.pdf'
    vars:
      author: Bank2000
```

```toml
[metadata_driver.exiftool]
enable = "false"

[metadata_driver.pdftotext]
enable = "auto"
timeout = 30

[default_vars]
author = [
  '{{ author }}',
  '{{ meta("exiftool", "PDF:Author") }}',
  '{{ meta("pdf", "author") }}',
  "UNKNOWN",
]
issued = ['{{ meta("pdf", "creation_date") }}']
```

Custom module. The invoice rule is the only caller, so other files do not import it. `bin` and `lang` are `options`.

```yaml
metadata_driver:
  invoice:
    driver: my_code.supershelf.driver
    enable: auto
    ext:
      - pdf
    bin: invoice-scan
    lang: eng

match_rules:
  - name: invoice
    kind: invoice
    filename_glob: '*.pdf'
    vars:
      number:
        - '{{ meta("invoice", "number") }}'
      vendor:
        - '{{ meta("invoice", "vendor") }}'
```

```python
# my_code/supershelf/driver.py
from supershelf.errors import VarCandidateError


class InvoiceDriver:
    def available(self, options) -> bool:
        return True

    def accepts(self, file, options) -> bool:
        return True

    def extract(self, file, field, options) -> str:
        lang = options.get("lang", "eng")
        if field not in {"number", "vendor"}:
            raise VarCandidateError(f"invoice has no {field}")
        return f"{lang}-value"


DRIVER = InvoiceDriver()
```

`driver: my_code.supershelf.driver:InvoiceDriver` constructs `InvoiceDriver` when the module does not export `DRIVER`.

Generic command, twice. `covers` is a script beside the profile. `tags` is a program on `PATH`. `%p` is its own token.

`covers` lists `ext` and no `mime`, so `report.pdf` matches on extension. A PDF named `report` does not match `covers`. `tags` lists only `mime`, so the extension test misses and the mime type is tested.

```yaml
metadata_driver:
  covers:
    driver: supershelf.meta_driver
    command: tools/covers.sh
    arguments: "--file %p --hash %h --lang eng"
    output_format: shell
    ext:
      - pdf
    enable: auto
    timeout: 30
  tags:
    driver: supershelf.meta_driver
    command: tagtool
    arguments:
      - --path
      - "%p"
      - --name
      - "%n"
    output_format: yaml
    mime:
      - application/pdf
    enable: "true"

default_vars:
  title:
    - '{{ meta("covers", "title") }}'
    - '{{ meta("tags", "info.title") }}'
  pages:
    - '{{ meta("covers", "pages") }}'
```

```toml
[metadata_driver.covers]
driver = "supershelf.meta_driver"
command = "tools/covers.sh"
arguments = "--file %p --hash %h --lang eng"
output_format = "shell"
ext = ["pdf"]
enable = "auto"
timeout = 30

[metadata_driver.tags]
driver = "supershelf.meta_driver"
command = "tagtool"
arguments = ["--path", "%p", "--name", "%n"]
output_format = "yaml"
mime = ["application/pdf"]
enable = "true"
```

Stdout those formats accept:

```shell
# output_format = shell
title=Quarterly report
pages=12
```

```yaml
# output_format = yaml
info:
  title: Quarterly report
```

```toml
# output_format = toml
title = "Quarterly report"
pages = "12"
```

```ini
# output_format = ini
# field name is section.key, so meta("covers", "doc.title")
[doc]
title = Quarterly report
```

```bash
#!/bin/sh
# argv: --file /abs/path --hash abc --lang eng
printf 'title=Quarterly report\npages=12\n'
```

## Cases

No call. The profile has no `meta()`. The walk and the variables match today. The database file is not created for this feature.

Group wins. The filename regex captured `author`. The first candidate `{{ author }}` succeeds. `pdf` is not opened.

Group missing. The winning rule captured no `author`. `{{ author }}` fails the candidate. `meta("pdf", "author")` runs.

All miss. Every candidate fails and `author` is not `mandatory`. The name stays unset. The file continues.

Mandatory. Every candidate fails and `author` is `mandatory`. The file stops after the last layer.

Unknown name. `meta("nosuch", "author")` stops the command when that template is loaded.

Turned off. `exiftool` has `enable: "false"`. The exiftool candidate misses. The next candidate runs. `exiftool` is not spawned.

Required tool missing. `enable: "true"` and `exiftool` is not on `PATH`. The command stops at load.

Optional tool missing. `enable: auto` and `pdftotext` is not on `PATH`. The candidate misses. One log line names the driver. Later files do not search `PATH` again.

Extension. `scan.pdf` and the `pdf` driver. The extension matches. `file` is not run.

No extension. A file named `scan` whose mime type is `application/pdf`, and the `pdf` driver. The extension test misses. `file` runs once for that hash. The mime matches.

Wrong suffix, no mime list. `covers` has `ext: [pdf]` and no `mime`. `notes.txt` does not match. `file` is not run.

Mime only. `tags` has no `ext` and `mime: [application/pdf]`. `report.pdf` reaches the mime test. A PDF with no suffix does too, when the mime is `application/pdf`.

`file` missing. A driver reaches the mime test and `file` is not on `PATH`. The mime test misses. One warning is logged. An extension hit on another driver still accepts that driver.

Replaced builtin. The key `exiftool` sets `driver` to a custom module. The builtin exiftool class is not called. `meta("exiftool", ...)` calls the module.

Two commands. `covers` and `tags` both use `supershelf.meta_driver`. Their cache rows are separate because the driver name is the profile key.

Same bytes. Two paths share a sha256. The first `meta("pdftotext")` runs the tool and stores the payload. The second reads the cache.

Failed tool. `pdftotext` exits non-zero. The candidate misses. The next run of that hash reads `error` and does not spawn again.

Dry run. The database file is absent. `--dry-run` still runs the tool and does not create the file. The next real run stores the payload.

Old schema, dry run. The file is schema `1`. `--dry-run` does not create `content_meta`. The cache misses. The tool runs.

Old schema, real run. The file is schema `1`. The run creates `content_meta` and sets the version to `2`. Existing documents stay.

Full text. `body` is `{{ meta("pdftotext", "text") }}`. The payload is in `content_meta`. The variable value is also in `vars_json`.

Inside config. `config.metadata_driver` stops the command. The message says to use the top-level key.
