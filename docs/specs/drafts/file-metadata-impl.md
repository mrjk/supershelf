# File metadata implementation

Status: behavior 2.3.3 dropped `fs`, `file()`, `pdf_cdate()`, and `pdf_mdate()`. This file is the old build order. It is not the rule.

Build order for [file-metadata.md](file-metadata.md). The slices below are that old order. Do not implement a later slice in the same change as an earlier one.

Leave `pdf_cdate()`, `pdf_mdate()`, and `file()` on [var_commands.py](../../../src/supershelf/var_commands.py). They keep `_pdf` in [vars.py](../../../src/supershelf/vars.py) `VarPlan._pdf`. They do not read `content_meta`.

Do not add `metadata_fields`, a match-rule `when`, `scan meta`, Pillow, mutagen, `tika`, or `ffmpeg`.

The working tree may already hold unrelated `record` edits. Do not stage `src/supershelf/record.py`, `cli.py`, `database.py`, `errors.py`, `constants.py`, or the record tests unless this plan names that edit.

## Shape

`driver = "supershelf.meta_driver"` must import. The module is [src/supershelf/meta_driver.py](../../../src/supershelf/meta_driver.py) and it exports `DRIVER`.

The rest is a package, so each review stays one class file:

- `src/supershelf/metadata/driver.py`: `MetadataDriver`, `DriverOptions`, `MetadataFile`
- `src/supershelf/metadata/registry.py`: `MetadataRegistry`
- `src/supershelf/metadata/session.py`: `MetadataSession`
- `src/supershelf/metadata/process.py`: `ProcessRunner`
- `src/supershelf/metadata/parse.py`: `OutputParser`
- `src/supershelf/metadata/cache.py`: `ContentMetaCache`
- `src/supershelf/metadata/drivers.py`: `FsDriver`, `PdfDriver`, `ExiftoolDriver`, `PdftotextDriver`, `CommandDriver`

No module-level functions. Shared argv execution is `ProcessRunner`. Rules 2.1.

`DRIVER` for the generic command is one `CommandDriver` instance. Per-entry settings live in `DriverOptions`, so two profile keys can share that instance.

A custom `driver = "pkg.mod"` uses the exported `DRIVER` object. `driver = "pkg.mod:ClassName"` constructs that class with no arguments. Extra keys on a custom entry are `options`. Reserved keys are not passed through: `driver`, `enable`, `timeout`, `ext`, `mime`.

## Wiring

`VarPlan.from_document` in [vars.py](../../../src/supershelf/vars.py) builds the registry before the var tables. It runs `require_available()` there, so `enable = "true"` fails before the walk.

`VarEnvironment.compile_source` parses the Jinja AST (`jinja2.Environment.parse`). A `meta()` call whose driver argument is a `Const` string is checked against the registry. An unknown name is `VarConfigError`. A non-literal driver name waits until render, then `VarResolveError`. Do not use a regex on the template text.

`BuiltinCommands.register` adds `meta`. The method reads `MetadataSession` and the current `MetadataFile`. `VarPlan.resolve` sets that file for the whole resolve and clears it in `finally`. `FileBinding` stays the ctime, mtime, and hash carrier. Placeholders need the relative path, name, stem, suffix, and directory, which `FileBinding` does not have.

`meta` raises `VarCandidateError` for a disabled driver, a rejected file, a missing or blank field, a timeout, a non-zero exit, and undecodable stdout. Any other exception leaves `VarEnvironment.render` and stops the command, which is the existing `TemplateError` path.

`config.metadata_driver` is `VarConfigError`. The advice says to move the key to the top level. Omitted, null, and `{}` build the builtin defaults only.

Add `KEY_METADATA_DRIVER = "metadata_driver"` in [constants.py](../../../src/supershelf/constants.py). Do not add a key to [default.toml](../../../src/supershelf/default.toml) or `PackagedConfig`.

Profile directory for a relative `command` is `profile_scope[VAR_PROFILE_DIR]`. The database path is `profile_scope[VAR_DATABASE_FILE]`. Both are already rendered in [profile.py](../../../src/supershelf/profile.py).

## Driver base

`MetadataDriver.accepts` implements the spec order:

1. Compare the last suffix, dot stripped, case-insensitive, to `ext`. A hit accepts. Mime is not read.
2. No extension, or no hit: if `mime` is non-empty, probe and compare. A hit accepts.
3. Neither list: accept every file.
4. `ext` only, and the extension missed: reject, and do not probe.

`ext` and `mime` on the profile entry replace the class lists. Omitted keeps the class list. `""` is not a list. A string is a one-item list. A leading dot on an item is stripped. Empty list stays empty.

`single_field` is `"text"` or `None`. `meta(name)` is allowed only when `single_field` is set. Otherwise a missing field fails the candidate at render.

`available(options)` is the enable check. The registry calls it once per entry.

`extract` returns one stripped string or raises `VarCandidateError`. Blank after strip is a miss. The driver parses once per `(hash, driver name, options_key)` and reuses the bag from `MetadataSession`.

`cache_epoch` is a class string. It is part of `options_key`.

`fs` and `pdf` ignore `enable`. A `timeout` key on either is `VarConfigError`. Other drivers: omitted timeout is 30, and `<= 0` is `VarConfigError`.

`enable` words are `auto`, `true`, and `false`. Booleans `true` and `false` are those words. The class default is `auto`, except `strings` later. Omitted on an entry uses the class default.

## Slice 1: registry and fs

No subprocess. No sqlite. `scan vars` still does not create `database_file`.

`FsDriver` returns the walk strings: `ctime`, `mtime`, `hash`, `name`, `stem`, `ext`, `path`, `dir`. No cache row.

Tests in `tests/test_metadata_config.py`:

- Omitted `metadata_driver` leaves the builtins at their class defaults.
- `exiftool.enable = "false"` does not remove `pdf`.
- Unknown builtin option, unknown name without `driver`, bad `enable`, `timeout = 0` on `pdftotext`, `timeout` on `fs`.
- `config.metadata_driver` stops, and the advice names the top-level key.
- A literal `meta("missing", "author")` is `VarConfigError` at load.
- `{{ author }}` then `{{ meta("fs", "name") }}` keeps a regex group and does not need `fs` when the group is set.
- A profile with no `meta()` does not create the sqlite file. `tests/test_scan.py` already asserts `database_file.exists() is False`. Keep that.

`MetadataSession.extract` in this slice is in-memory only.

## Slice 2: processes and the first tools

`ProcessRunner.run(argv, timeout)` uses `subprocess.run` with `shell=False`, `check=False`, and stdout as bytes. Decode UTF-8. `UnicodeDecodeError` becomes `VarCandidateError`. Timeout kills the process and becomes `VarCandidateError`. Non-zero exit becomes `VarCandidateError`. stderr is logged at debug and is not parsed. Tests pass a fake runner. Do not call a real `exiftool` or `pdftotext`.

`OutputParser` handles `yaml`, `toml`, `ini`, and `shell` as the spec states. `ini` uses `configparser` with interpolation off. Nested mappings flatten with `.`. List and null values are skipped. A non-mapping document, a bad TOML duplicate, or a bad shell key fails the candidate.

`CommandDriver`:

- `command` is required. A path separator resolves from the profile directory and must be an existing file. Otherwise `shutil.which`.
- `arguments` omitted means argv is only the program. String form is `shlex.split` at load. A bad quote is `VarConfigError`. Placeholders are replaced after the split. Unknown `%` tokens are `VarConfigError` at load.
- `output_format` is required.
- `options_key` is sha256 of canonical JSON: driver identity, `command`, the argument template, `output_format`, `cache_epoch`. Not Python `hash()`. `ext`, `mime`, `enable`, and `timeout` stay out of the key.

`PdfDriver` uses `pypdf` the same way `_read_pdf` does today, and adds `author`, `title`, `subject`, `creator`, `producer`. Dates are `YYYY-MM-DD`. A bad date is a missing field. Cache the parsed map as JSON in the session bag. Do not write `VarPlan._pdf`.

`ExiftoolDriver` argv: `exiftool`, `-json`, `-G`, path. Drop `SourceFile` and `File:` keys.

`PdftotextDriver` argv: `pdftotext`, `-q`, `-enc`, `UTF-8`, path, `-`. Field `text` may be omitted.

Mime probe argv: `file`, `--mime-type`, `--brief`, path. Cache the string on the session by hash. If `file` is not on `PATH`, the mime test misses and one warning is logged. Extension hits do not call it.

`enable = "true"` calls `available` from `VarPlan.from_document`. `auto` calls it on the first `extract`, then remembers the answer. One log line per missing program per process.

Tests in `tests/test_metadata_command.py` and `tests/test_metadata_drivers.py`:

- `%p` as its own token keeps a path that contains a space as one argv item.
- Shell, YAML, TOML, and INI samples from the spec.
- A script path is executed, not `sh -c`.
- Two `supershelf.meta_driver` entries do not share a bag.
- `scan.pdf` does not spawn `file`. A file named `scan` with mime `application/pdf` does, once per hash.
- Fake `exiftool` and `pdftotext` on `PATH` via the injected runner.
- A non-zero exit fails the candidate and the next candidate runs.
- `pdf` author on a file written with `PdfWriter`.

Still no sqlite writes.

## Slice 3: content_meta

Only this slice changes schema version. New databases are created at version `2` with `content_meta` in `_SCHEMA`. A version `1` file opened for write runs:

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

Then set `meta.schema_version` to `2`. Version `3` or anything else is still `DatabaseError`.

`ShelfDatabase.open_read` must accept version `1` and version `2`. Version `1` has no `content_meta`. The cache read is a miss. It must not migrate. Today [database.py](../../../src/supershelf/database.py) `_require_version` rejects every value other than `SCHEMA_VERSION`, and `tests/test_database.py` `test_wrong_schema_version_is_rejected` stores `'2'` as the bad version. After this slice the bad version in that test is `'3'`. `test_write_creates_schema_version` expects `'2'`.

`ContentMetaCache` is used only after the in-memory bag misses.

- `--dry-run`: if the sqlite file is absent, or it is version `1`, do not create it and do not migrate. Run the tool. Do not insert.
- A real run: `open_write` (this migrates version `1`), `INSERT OR IGNORE INTO contents(hash)`, then insert the cache row. Success stores `payload` and a null `error`. Failure stores `error` and a null `payload`.
- `fs` writes nothing. A driver that does not accept the file writes nothing.
- The same hash on a second path reads the row and does not spawn.
- A cached `error` does not spawn again.
- No document row and no event row from this path.
- `record run` uses the same `VarPlan.resolve`, so it sees the same cache.

`tests/test_metadata_cache.py`: migration, dry-run absent file, dry-run version `1`, same hash, stored error, and a profile with no `meta()` still leaves the sqlite file absent.

`scan files` and `scan kinds` do not construct a session that opens the database. `schema` and `profiles` do not either.

## Docs in slice 3

Move the implemented rules into [behavior.md](../behavior.md) `2.3.3` and the table into [architecture.md](../architecture.md) section 3. Update the sentences that say `scan vars` never creates `database_file`. The new sentence is: `scan vars` and `record run` create it when `meta()` runs and the cache misses. `--dry-run` does not. `scan files` and `scan kinds` do not.

Same change on the public pages that say the sqlite file is never created by scan, and that PDF metadata is only the two date commands:

- `docs/content/concepts/limits.md`
- `docs/content/concepts/variables.md`
- `docs/content/concepts/template-commands.md`
- `docs/content/reference/architecture.md`
- `docs/content/guides/record-matched-files.md`

Leave `pdfinfo`, `mutool`, `ffprobe`, `mediainfo`, `zipinfo`, and `strings` in the draft. Their argv is already specified. They are a later review, each a thin `ProcessRunner` subclass plus one test with a fake binary. `strings` stays default `false`.

## Done when

- A profile with no `meta()` matches today's walk, vars, and database behavior.
- `meta("fs", "name")`, `meta("pdf", "author")`, a fake `exiftool`, a fake `pdftotext`, and `supershelf.meta_driver` follow the cases at the bottom of the product draft.
- Version `1` databases gain `content_meta` only on a real run that misses the cache.
- `file()`, `pdf_cdate()`, and `pdf_mdate()` tests in `tests/test_var_commands.py` stay green without reading `content_meta`.
