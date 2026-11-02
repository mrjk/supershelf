# Behavior

What the commands do. Types, cast, and packaged defaults are in [architecture.md](architecture.md). A profile a user would paste is in [examples.md](examples.md). File metadata is 2.3.3. Later metadata builtins stay in [drafts/file-metadata.md](drafts/file-metadata.md).

## 1 App initialization

- Create one ShelfConfigs python instance, that will hold a list of ShelfConfig.
- Find profile configs. First source wins. Do not merge files from a later source.
  Format preference inside one directory: toml, then yaml, then yml.
  A later format for the same profile warns and is ignored. .yml is stored as type yaml.
- Profile selection, applied after the files are loaded:
  - --profile wins over $SUPERSHELF_PROFILES.
  - Both accept a comma-separated list. Spaces around names are ignored.
  - The result keeps the requested order. A repeated name is kept once.
  - An unknown name is an error. With no selector, every discovered profile is kept.
- Config source, first hit wins:
  - --config
    - Missing path, or a directory with no matching file: error. Do not fall through.
    - A file: load that file only.
      %PROFILE_NAME applies only when the filename is profile.%PROFILE_NAME.(toml|yaml|yml).
    - A directory: same rules as the current directory below.
  - $SUPERSHELF_CONFIG
    - Same processing as --config.
  - Current directory:
    - If supershelf.toml, supershelf.yaml, or supershelf.yml exists, load only the first of those.
      Do not also load profile.%PROFILE_NAME.* from that directory.
    - Otherwise load every:
      - profile.%PROFILE_NAME.toml
      - profile.%PROFILE_NAME.yaml
      - profile.%PROFILE_NAME.yml
      One file per %PROFILE_NAME, toml then yaml then yml. Names are sorted.
      A later format warns and is ignored.
  - User config directory ($XDG_CONFIG_HOME/supershelf, or ~/.config/supershelf):
    - Load only profile.%PROFILE_NAME.toml, then .yaml, then .yml.
    - A supershelf.toml in this directory is not a profile source.
  - If none found, fail.
- Check consistency and prepare:
  - The profile name is %PROFILE_NAME when the filename has one.
    If config.profile is a different non-empty string, warn that it is ignored.
    The same name does not warn. A blank config.profile is treated as unset.
  - If the filename has no %PROFILE_NAME, the profile name is config.profile when that is set, otherwise default.
  - Write config.profile to that profile name on the stored dict.
  - If two files resolve to the same profile, warn and keep the first.
- App is inited:
  - config_list is one or more ShelfConfig:
    - profile: the profile name
    - type: toml or yaml
    - path: config file path
    - config: parsed file contents
  - The file must be a mapping. config, when present, must be a mapping.
    config.profile, when present, must be a string. Other keys are stored and not interpreted in this step.
- App commands:
  - supershelf profiles: table of profile, type, and path.
    This is the list selected by --config / $SUPERSHELF_CONFIG and --profile / $SUPERSHELF_PROFILES.

## 2 Profile initialization

Source is who writes a value. Availability is where a template can read it. A name in this step is not a variable a layer can assign, and it is not printed.

- supershelf profiles only lists profile, type, and path. It does not build a ShelfProfile.
- A command that needs rendered paths, such as scan, creates one ShelfProfile per selected ShelfConfig.
- Profile load writes `__profile__` before any path template. Read a field. The object with no field is not a string, so the command stops.
  - `__profile__.name`: the profile name from section 1. This replaces `__profile__` and `__profile_name__`.
  - `__profile__.type`: `toml` or `yaml`
  - `__profile__.path`: absolute path of the config file
  - `__profile__.dir`: directory of the config file
  - `__profile__.file`: filename of the config file
  - `__profile__.document`: the parsed profile file. Dotted keys walk nested mappings. This replaces `__config_data__`.
- `__config__.date_format` is `config.default_date_format`. It is a plain string, not a template. `scan files` uses it to show mtime and ctime. Omitted, it is `%Y-%m-%d`. It is published before the path templates below.
- Then render these config keys, in order. After each one, resolve a relative path from `__profile__.dir`, store the absolute path on `__config__`, and publish it before the next template.
  - `root_dir` becomes `__config__.root_dir`
  - `database_file` becomes `__config__.database_file`
  - `cache_file` becomes `__config__.cache_file`
- Built-in defaults when the key is omitted:
  - `root_dir = "{{ __profile__.dir }}"`
  - `database_file = "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.sqlite"`
  - `cache_file = "{{ __config__.root_dir }}/profile.{{ __profile__.name }}.cache"`
- Available here: `__profile__` and the `__config__` fields already published. Not available: `__file__`, `__match__`, `__input__`, and `__date__`.
- This is the scope for `config.root_dir`, `config.database_file`, `config.cache_file`, `inputs.path`, and an output `path`.
- An old flat name, such as `__root_dir__` or `__profile_dir__`, is unknown and stops the command. There is no alias.

## 2.1 Scan files

### 2.1.1 Command

- supershelf scan files: clak table of the files kept by each input.
- supershelf scan files --quick: same table, but skip mtime, ctime, and sha256.
- Table columns: profile, input, path, mtime, ctime, sha256.
  input is the 1-based index in that profile's inputs list, not the directory path.
  path is relative to the input directory.
  mtime and ctime are the stored UTC times shown with config.default_date_format.
  --quick omits mtime, ctime, and sha256.

### 2.1.2 Walk

- Each selected profile is scanned on its own. Profiles do not share results.
- scan files only prints. It does not create the database file or the cache file.
- For each input, get the path value, and template render it.
- If that path is relative, resolve it from `__config__.root_dir`. Relative input paths are resolved when the input is processed.
- The input path must be a valid path. If it exists and is not a directory, that is an error.
- If the input directory is missing, log a warning and skip that input.
- Get parameters depth, include, exclude, and follow_symlinks.
- depth: 0 means no recursion limit. 1 means only the input directory. 2 means that directory and one subdirectory level. 3 adds the next level, and so on.
- Omitted depth means 0. Negative depth is an error.
- follow_symlinks is an input option. Default true. False skips symlinks.
- A followed symlink is stored as the path under the input. A symlink cycle logs a warning and that path is skipped.
- Globs match the path relative to the input directory. * stays in one directory. ** crosses directories.
- If include is set, keep files that match at least one include pattern. If include is omitted, start from every file the walk found.
- If exclude is set, drop matching files from that set. If exclude is omitted, drop nothing.
- Empty files are ignored.
- An unreadable file logs a warning and is skipped.
- An unreadable directory logs a warning and is not descended.
- Do the filesystem walk
- store results in a InputScanResult:
  - config: hold the input config
  - index: 1-based position in that profile's inputs list. A skipped input keeps its position.
  - results: hold a list of InputFile objects
- Get file metadata, unless --quick:
  - mtime is filesystem st_mtime. ctime is filesystem st_ctime. Stored as UTC ISO-8601 with a numeric offset, so datetime.fromisoformat can parse them. Example: 2026-10-29T16:28:00+00:00. Include fractional seconds when the filesystem value has them.
  - sha256 is the lowercase hex digest of the file contents.
  - InputFile expose all Path primitives (parent, stem, ext, etc ...)

## 2.2 Matching

### 2.2.1 Commands

- supershelf scan kinds:
  - Use the files kept by the scan files walk. Do not hash, and do not read mtime or ctime.
  - Print matched files only. Columns: profile, input, path, kind, rule.
  - input is the 1-based index in that profile's inputs list, same as scan files.
  - path is relative to the input directory.
  - Do not create the database file or the cache file.
  - vars and outputs are not part of this step.
- supershelf scan inspect [PATH]:
  - Use the files kept by the scan files walk. Do not hash, and do not read mtime or ctime.
  - PATH is the relative path of one kept file. Omit it to print one line per kept file: match or miss, with profile, input, rule, and kind. That mode never prints patterns.
  - A PATH that no kept file has is an error. The same path in two inputs is traced twice. Each line includes profile and input.
  - Compile patterns once per profile, before the walk. A bad pattern fails the command before that walk.
  - Do not create the database file or the cache file.
  - Lines go to stdout. -v and -vv choose how many lines, not the log level. -vvv adds no extra inspect lines.
  - With a PATH, default prints each pattern that was actually tried, in rule and field order, and stops at the first hit:
    rule NAME FIELD 'pattern' against 'candidate': hit or miss
    A miss ends with the same warning as scan kinds. A hit ends with: Matched rule NAME kind KIND for PATH in profile PROFILE input INDEX
  - -v also prints the path, directory, and filename candidates, skipped fields (no patterns, or empty directory), captured groups, and "stopped, later rules not tried" when an earlier rule won.
  - -vv also prints later patterns and later rules that matching never runs, marked not tried, with the candidate they would have used.

### 2.2.2 Algorithm

- match_rules is a profile-level list, sibling of inputs. Every input of that profile uses it.
- Compile patterns once per profile, before the walk. A bad pattern fails the command before that walk.
- For each kept file, try rules in list order. The first rule that matches wins. Later rules are not tried.
- A rule matches when one field matches. Try fields in this order. The first hit wins. Later fields are not tried.
  - regex
  - directory_regex
  - filename_regex
  - glob
  - directory_glob
  - filename_glob
- Candidates, for input directory /srv/in and file /srv/in/a/b/c.pdf:
  - regex and glob see a/b/c.pdf. That is the path relative to the input directory, with / separators.
  - directory_regex and directory_glob see a/b. That is the path between the input directory and the file: no filename, no leading or trailing slash.
  - filename_regex and filename_glob see c.pdf.
  - A file in the input directory has an empty directory string. directory_* does not match it.
  - The input directory is that input's path, not config.root_dir.
  - A symlink uses the path stored under the input.
- Regex is anchored to the whole candidate. The engine full-matches. Authors do not write ^ or $.
  A pattern that stops before the extension does not match a file that has one.
  directory_regex has no filename, so it does not include an extension.
- Globs full-match the whole candidate, same rules as include and exclude.
  * stays in one directory. ** crosses directories.
  ** also matches a file sitting in the input directory, so glob: '**' claims every kept file.
  A glob does not capture groups. * does consume the extension, so filename_glob REL* matches REL_1.pdf.
- A field may be a string or a list of strings. A string is one pattern.
  Patterns in a list are tried in order. The first hit wins.
  An omitted field or an empty list is skipped.
- A rule with no patterns is a config error.
- A rule needs a name, a kind, or both. A blank value counts as omitted.
  When both are set, the kind is the explicit kind and the rule name stays name.
  When only name is set, the kind is that name.
  When only kind is set, the rule name is that kind.
- The rule name must be unique in the profile. A duplicate is a config error.
  Several rules may share one kind when their names differ.
- A rule with neither name nor kind is a config error.
- Named groups from the winning regex are kept. Unnamed groups are ignored.
  Groups are not merged across fields or rules. Globs keep no groups.
- Patterns are literal. Do not template them.
- Unknown keys on a rule, including vars, are ignored in this step.
- `record_identity` on a rule is ignored here. `record status` and `record run` read it. 4.2.
  A bad value does not stop a scan.
- A pattern that is not a string, a rule with neither name nor kind, or any other bad shape is a config error.
- match_rules missing, or a file that no rule claims:
  - Log a warning with profile, input, and relative path.
  - Keep the file on the scan result, with the data the walk already gathered.
  - Leave it out of the matched set. Do not store a kind.
  - The kinds table does not show that file.
  - Warnings do not fail the command.
- Files the walk skipped never reach matching.

## 2.3 Vars

`scan vars` resolves variables in 2.3.1, may read or append a kind file in 2.3.2, and may read file metadata in 2.3.3.

### 2.3.1 Resolve

#### Command

- supershelf scan vars [PATH]:
  - Use the files kept by the scan files walk, then the matched set from step 2.2.
  - PATH is the relative path of one kept file. Omit it to list every matched file.
    A PATH that no kept file has is an error. The same path in two inputs is listed twice.
    When PATH is set, only that file is matched. Other files are not warned.
  - The walk is the full walk. mtime, ctime, and sha256 are required. There is no --quick.
  - Print matched files only. One row per file.
    Columns: profile, input, path, kind, rule, vars.
  - input is the 1-based index in that profile's inputs list, same as scan kinds.
  - path is relative to the input directory.
  - kind is the match-rule kind. rule stays the match rule name. Nothing else may set the match kind.
  - vars is one cell. Each final key is one line: the name, ": ", then the value.
    File order follows the walk. Inside the cell, the lines are
    regex groups in pattern order, then assignment keys in first-seen order.
    `__file__` and `__match__` fields are omitted unless --all is set.
    With --all, each field is one line. The name is the dotted form, such as `__file__.name`.
    The source label is `fact`.
    `__profile__`, `__config__`, and `__input__` are never printed.
    A regex group replaced by an assignment is printed once, with the final value, in its fact position.
  - Log the same unmatched-file warning as scan kinds, once per file. Do not log it again.
  - -vv logs each kind_overrides_config candidate the first time a kind and input try it.
    A missing path logs that path and the kind. The winning file logs when it is first loaded.
    A path already loaded for another search logs that it was found.
    An empty kind_overrides_config logs that there is no candidate list.
    disabled does not try candidates, so it does not log these lines. 2.3.2.
    A repeated search for that kind and input stays quiet. -v does not add these lines.
  - Do not create the database file, the cache file, or any output tree.
    scan vars may create or append a kind file. 2.3.2.
  - outputs and extension_remap are not part of this step.
  - Step 2.2 still ignores vars. This step reads them from the raw rule mapping.

#### Algorithm

- Facts and assignments are different sets.
- Facts are the base scope. An assignment of the same name shadows that fact for later templates and replaces the printed value.
  While a key is being rendered, a reference to itself still sees the previous layer, so the fact stays visible when no earlier assignment set that name.
- Source and availability for a variable template:
  - Step 2 is already in scope: `__profile__` and `__config__`. They are not printed. A layer cannot set those roots.
  - The walk writes `__file__`. The match writes `__match__`. Both are in scope for variable templates, and for output `when` and `layout`. They are not in path templates. `scan vars` prints their fields only with `--all`.
  - `__input__` is not in a variable template. Kind-file path templates are the only place that reads it.
  - `__date__`, regex groups, and other assigned names appear only after the layer that set them.
- `__file__` fields. Read a field. The object with no field fails that candidate. Empty `.ext` and `.dir` are `""`, which is set.
  - `__file__.name` and `__file__.stem`: InputFile.name and InputFile.stem. `archive.tar.gz` stores stem `archive.tar`.
  - `__file__.ext`: the last suffix without the leading dot. No suffix stores `""`. `archive.tar.gz` stores `gz`. A leading dot, as in `.gitignore`, is not a suffix.
  - `__file__.path`: path relative to the input, with `/` separators
  - `__file__.dir`: directory relative to the input. Empty when the file sits in the input directory.
  - `__file__.hash`: lowercase sha256
  - `__file__.ctime` and `__file__.mtime`: the stored UTC ISO-8601 timestamps from the walk, not `default_date_format`. They are text. They do not satisfy type `date`.
- `__match__.kind` is the kind from step 2.2. `__match__.rule` is the match rule name. Nothing may set `__match__`. It does not change the rule.
- The filename does not set `__date__`. A stem that is a date stays `__file__.stem`.
  A profile that wants that date writes a candidate, such as
  `{{ regex_time_var(__file__.stem, __config__.date_format) }}`.
  A PDF date is `{{ meta("pdf", "creation_date") }}` or `{{ meta("pdf", "modification_date") }}`.
  Later layers may replace a date an earlier layer wrote.
  `{{ __date__ }}` in the next layer reads the string the earlier layer kept.
- Named groups from the winning regex are facts. Unnamed groups stay ignored.
  A group name that starts with `__` is a config error before the walk.
  A group cannot be a namespace root.
- Assignments are the user layers. Later wins on the same key. Each layer is applied before the next one starts.
  Var tables are rendered. The per-file row is stored as text. 2.3.2.
  1. default_vars
  2. match_rules[].vars
  3. The per-file row from the kind file. 2.3.2.
     One literal string per cell. It replaces a value the rule already stored.
     It does not change what the rule template already read.
     This is the last assignment layer.
- A layer may set `__date__` and names that do not start with `__`.
  A namespace root (`__file__`, `__match__`, `__profile__`, `__config__`, `__input__`) is a config error.
  Any other name that starts with `__` is a config error.
  A key cannot contain a dot, so a layer cannot write `__file__.name` or `__match__.kind`.
  This applies to `default_vars`, rule `vars`, and a kind-file row. 2.3.2.
- overrides is not a profile key. A present overrides key is a config error, including an empty list.
  Per-file values belong in the kind file.
  kind_overrides_mode, kind_overrides_date_format, kind_overrides_sep, and kind_overrides_config stay.
  Those keys are the kind file, not the removed list.
- A resolved var is always one string. A template can read facts and any assignment already rendered.
  It cannot read a key later in the same mapping. That name is not defined yet.
  The key being rendered sees the previous layer's string, not the candidate list being tried.
  account: ['{{account}}'] reads the group when no earlier layer defined account.
  A default_vars account hides the group from the rule template of the same name.
  The per-file cell is applied after the rule template has stored its string.
  A rule's {{__date__}} reads the __date__ string the earlier layer already kept. It does not run that layer's other candidates again.
- Omitted default_vars, omitted rule vars, or an omitted kind file means that layer is empty.
- A var table is a mapping. Each key matches [A-Za-z_][A-Za-z0-9_]*.
  Each value is a string, or a list of strings. A string is one candidate. A list is an ordered fallback.
  An empty list is a config error.
  Numbers, booleans, nulls, dates, and nested mappings are config errors. Quote scalars such as 2026-04-25.
- Each var table is rendered in mapping order before the next layer.
  A new key is appended. A key that already exists is rendered again and keeps its first position.
  The printed row uses the final string.
- A string is one candidate. A list means try each candidate in order. The first one that does not fail is kept.
  The stored value is that string. The list is not kept.
- A candidate with no {{, {%, or {# is a literal string. It is not compiled.
  Any other candidate is a Jinja2 template. Profile path templates stay the step 2 language and are not Jinja.
- Each distinct var template source is compiled once per process. Rendered results are not cached.
- Jinja uses StrictUndefined. An unknown name fails that candidate. autoescape is off.
  The rendered result is stored as a string.
  An old flat name, such as `__file_name__` or `__kind__`, is unknown and fails that candidate. There is no alias.
  A namespace with no field prints one string: `__profile__` is the name, `__config__` is `root_dir`, `__file__` is the filename, `__match__` is the kind, `__input__` is the input path.
  A plain mapping, such as `__profile__.document`, still needs a field.
- A string candidate is rendered once. Failure aborts that candidate.
- Inserted strings are not rendered again.
- An empty string is a success for text. For every other type, empty or whitespace is a miss.
- If every candidate in a layer misses, that layer does not write the name.
  An earlier value stays. When no layer has written it, the name stays unset.
  The command continues. mandatory after the last layer stops the file when the value is still unset.
  A fact or a kind-file cell that cannot cast stops the file. There is no next candidate for those.
- __date__, when set, is a calendar date YYYY-MM-DD. A candidate that renders to anything else fails, and the next candidate is tried.
  The stored value, the printed value, and vars_json stay that string.
  In a Jinja template `{{ __date__ }}` uses `default_date_format`. The packaged format is `%Y-%m-%d`, so the text is `YYYY-MM-DD`.
  `strftime` takes one `strftime` pattern. `{{ __date__.strftime('%Y-%m') }}` is the year and the month. `%YY` is not a year code.
  The fields are `Y`, `m`, and `d`, the `%Y`, `%m`, and `%d` parts of that date.
  `{{ __date__.Y }}` is the four-digit year. There is no string slicing.
  A date candidate that is not `YYYY-MM-DD` is parsed with `default_date_format` and stored as `YYYY-MM-DD`. If that also fails, the candidate misses.
  Supershelf uses this date as the document date, including for output paths.
  This step does not write outputs. Behavior 5 does. A layout that uses __date__ fails when __date__ was omitted.
- Shape errors and template syntax errors fail the command before the walk.
  The kind file is checked when it is first loaded.
- A broken Jinja template is a config error when that template is loaded.
  A function that has nothing to return fails that candidate only, so a later option can run.
  Built-in commands and user commands do that by raising supershelf.errors.VarCandidateError.
  Any other exception stops the command.
- config.var_modules is an optional list of importable module paths. Omitted or empty means no user modules.
  Built-in commands are always registered. Then each module is imported in list order, before the walk.
  A module provides two optional dicts: GLOBALS for {{ name(...) }}, and FILTERS for {{ value | name(...) }}.
  Values are callables. They receive strings and return a string.
  A name that repeats a built-in, or an earlier module, is a config error. An import failure is a config error.
- regex_time_var(name, "fmt", ...) reads the named string and tries each strptime format.
  The first hit wins. The result is YYYY-MM-DD. At least one format is required.
  Formats are separate quoted arguments. A format such as %H:%M:%S contains colons, so arguments are not split on colons.
  regex_time_var(date, "%Y%m%d") reads the group date. It does not read __date__.
- regex_replace(name, "pattern", "replacement") runs a substitution on that string.
  Backreferences are allowed. No match fails the candidate. Three arguments are required.
- A function stays only when it transforms text or fetches a value that is not already in scope.
  `regex_time_var`, `regex_replace`, and `meta` are those functions.
  `file()`, `pdf_cdate()`, and `pdf_mdate()` are removed. There is no alias.
  File strings are `__file__` fields. PDF dates are `meta("pdf", "creation_date")` and `meta("pdf", "modification_date")`. 2.3.3.
- kind_overrides_config is an optional list of path templates.
  Omitted uses this list, in order:
  - `{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.csv`
  - `{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.toml`
  - `{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.yaml`
  - `{{ __config__.root_dir }}/profile.{{ __profile__.name }}.{{ __match__.kind }}.yml`
  An empty list means no kind files. -vv logs that once for each kind and input, except when the mode is disabled.
  Render each path with the step 2 language and the profile scope.
  For that render only, add `__match__.kind` (the rule kind) and `__input__.path` (the absolute input directory).
  `__match__.rule` is not in this scope. Reading it stops the command.
  `__file__` is not in this scope. The kind path is per kind and input, not per rule or file.
  A relative result is resolved from `__config__.root_dir`.
  The first path that exists and is a file wins. A missing path tries the next.
  None found means no per-file row, unless kind_overrides_mode is always.
  disabled does not run this search. 2.3.2.
  A path that exists and is not a file is an error. Do not try the next path.
  The parsed file is cached for the process by its absolute path. Nothing is written to cache_file.
  The file shape, the cell values, and when a file is created or extended are 2.3.2.
- Files the walk skipped never reach this step.

#### Cases

Present overrides. A profile with an `overrides` key stops at load. The key is removed.

### 2.3.2 Kind files

#### Command

- supershelf scan vars reads the kind file from 2.3.1 and may create or append it.
  scan files and scan kinds do not read or write kind files.
- --kind-overrides-mode MODE sets the mode for this command.
  MODE is auto, manual, always, or disabled. The words are exact.
  A missing MODE, a different case, or any other value is a usage error.
  The flag belongs to scan vars only.
- SUPERSHELF_KIND_OVERRIDES_MODE accepts the same four words.
  Any other value is an error, including a different case and an empty value.
  Unset means omitted.
  The flag wins over the env var. The env var wins over config.kind_overrides_mode.
  Omitted everywhere means auto.
- --dry-run reads when the mode reads, and does not create or append.
  Log only when something would change.
  A file that would be created logs its path and its row count.
  A file that would gain rows logs its path and how many rows would be appended.
  Zero rows logs nothing. manual and disabled log nothing.
- Writes happen after the run succeeds. A var error writes nothing.
  There is no lock. Two overlapping runs can append the same path twice.
- scan vars PATH matches only that file, so only that path can be fed.
  Other files of the same kind stay as they are.

#### File

- The winning kind file is a list of rows. CSV, TOML, and YAML are the same list.
  One row per relative path. A missing var is omitted.
  The examples are in [examples.md](examples.md). .yml is the same text as .yaml.
- Files are UTF-8. Invalid UTF-8 is an error.
- .csv: one data row per file. The header is checked by name and case.
  The first column is exactly PATH. __date__ is optional and may sit anywhere after PATH.
  Other columns are the user's, in the user's order.
  config.kind_overrides_sep is the separator. Omitted, it is a comma.
  The example profile sets ';'. YAML and TOML ignore it.
  The file is not scanned to guess the separator.
  Check the separator before the walk, at the same time as the date format.
  It must be a string of one character.
  A value that is not a string, an empty string, or more than one character is a config error.
  The message names kind_overrides_sep.
  Reject a letter, a digit, _, whitespace (including tab), ", ', /, \, or a newline.
  The message names the character and says to use a comma or a semicolon.
  Comma and semicolon are the expected values. | is allowed.
  Cells that contain the separator, a double quote, or a newline are quoted with ".
  The quote character stays ".
  Read and append use the configured separator.
  A file written with another separator fails the header check.
  That user error names the first column that was seen and mentions kind_overrides_sep.
  A leading BOM is accepted and left in place. It is not part of the first column name.
- .yaml and .yml: a bare list. There is no wrapping key.
  Each item has path and vars.
  vars is a mapping of var name to text. Omitted vars, or an empty mapping, adds no vars.
  Any other shape for vars is a config error. Unknown keys on the item are ignored.
- .toml cannot be a root list, so the file is [[rows]] tables.
  Each table has path and a [rows.vars] table. The items are the same as yaml.
- PATH in CSV, and path in TOML and YAML, is the path relative to the input, with / separators.
  It is an exact match, not a glob. Case is not folded.
  In CSV, PATH is the row key. Every other column except __date__ is a var name.
  In TOML and YAML, the names under vars are the var names. path plus a vars mapping is unchanged.
  A TOML or YAML var name must match [A-Za-z_][A-Za-z0-9_]*.
  A CSV column other than PATH and __date__ must be lowercase and match [a-z_][a-z0-9_]*.
  A non-empty CSV is checked before rows are applied. Any miss is a user error.
  The message names the file and what is wrong.
  The first column must be PATH. path or Path says to use PATH.
  A missing PATH, or PATH in any later position, is an error.
  A header named SHA, sha, or Sha says rows match on PATH. SHA is not a column in this version.
  There is no DATE column. DATE, Date, and date say the date column is __date__.
  A column that is not lowercase names that column and says other columns must be lowercase.
  A duplicate CSV column, a duplicate name in one vars mapping, a missing path key in TOML or YAML,
  a bad name, or a namespace root is an error.
  An empty file, or a file of whitespace only, is an empty table, not a missing-header error.
  A blank line is skipped. A row with values and an empty PATH or path is an error.
  Two rows with the same path: warn, keep the first, leave the later row in the file.
- A cell is one stored string. It is not a candidate list, and it is not compiled as Jinja,
  even when the text contains {{, {%, or {#.
  The rule layer has already stored its string, so the row does not change what that layer read.
  The kind file is the last assignment layer.
- An empty cell, a blank string, or a yaml or toml null is absent. The previous layer stays.
  This is not the template rule that an empty string is a success.
  There is no way to force an empty string over a previous value.
  A non-empty value is kept as text, including surrounding spaces, except __date__ below.
  A var value that is a number, boolean, date, list, or nested mapping is a config error. Quote scalars.
- A cell that sets an existing key keeps that key's first position and replaces the stored string.
  A new key is appended. CSV uses column order. TOML and YAML use key order inside vars.
- A row may set `__date__` and names that do not start with `__`.
  A namespace root (`__file__`, `__match__`, `__profile__`, `__config__`, `__input__`) is an error.
  Any other name that starts with `__` is an error.
  A key cannot contain a dot.

#### Date

- A kind-file cell may set __date__. The kind-file cell is the one that is parsed.
- In CSV, the document date is the optional column __date__. It may sit anywhere after PATH.
  There is no DATE column. DATE, Date, and date are user errors that say the date column is __date__.
- config.kind_overrides_date_format is an optional strptime format.
  When it is omitted, use config.default_date_format. That default is %Y-%m-%d.
  A blank or non-string value is a config error.
  The format must be valid for strptime and must include a year, a month, and a day.
  A time portion is allowed. Check that before the walk.
- Strip the cell, then parse the whole string. Store year, month, and day as YYYY-MM-DD.
  Drop any parsed time. scan vars prints that stored value.
  A value that does not match stops the command.
  The message names the file, profile, input, path, the cell text, and the format that was required.
  There is no next candidate.
  A blank __date__ cell is absent. The previous layer stays, and the command does not stop.
- This format applies to __date__ only.
  In TOML and YAML, another key, including date, stays raw text.
- default_date_format still shows mtime and ctime in scan files, and it is this fallback.

#### Load

- disabled does not render, open, create, or append kind files.
  A listed path that exists is ignored. There is no per-file row.
- For each other mode, for each input and each rule kind that has a matched file, render the path list once.
  A kind with no matched file is never looked up, so always does not create a file for it.
  Cache that winner for the process by input index and kind.
  Cache the parsed rows by absolute path. Two inputs that resolve the same file share one table.
- The first existing file wins. Later hits are ignored, with no log.
  A path that exists and is not a file is an error. Do not try the next path.
  A symlink to a file is that file. Read and append follow it.
  A bad suffix, or any other content that does not parse, is an error.
  Do not try the next path, and do not append.
  An empty file, or a file of whitespace only, is an existing empty table.
- Create of a missing file is always only, and only when every candidate is missing.
  Create uses the first template only. Create missing parent directories.
  If a parent exists and is a file, that is an error and no kind file is written.
  auto appends only when a candidate exists. It does not create a missing file.
  manual reads a candidate when one exists. It does not create a file and does not add rows.
- The rule kind picks the file. `__match__.kind` does not change after matching, so the file and the row stay on that kind.
- The row key is the relative path alone.
  Two inputs that share one kind file treat the same relative path as one row.
  Put {{ __input__.path }} in the template when those inputs must not share rows.
- config.kind_overrides_mode is auto, manual, always, or disabled.
  Omitted means auto. Any other value is a config error. The words are exact.
  auto reads the winning file and appends every matched path of that kind that is not already a row.
  When no candidate exists, auto has no per-file row.
  manual reads the winning file and leaves it unchanged.
  When no candidate exists, manual has no per-file row.
  always reads the winning file, or creates it, and appends every missing matched path of that kind.
  Unmatched files have no kind, so they get no row. Files the walk skipped get no row.
  Rows already in the file stay, including paths that are not in this scan.
- auto and always may append missing paths.
  They must not delete a row, edit a cell, drop a column, or reorder rows.
  They must not rewrite existing cell text.
  When schema columns are missing from a CSV, append those names on the right.
  Pad each existing data row with empty cells. Leave a blank line blank.
  A path already present is not appended again, including a duplicate row that was warned and kept as the first.
  Append in walk order, input index first.
  Do that once per absolute path, after the rows for this run have been read, and only if the run succeeds.
  A new row sets PATH in CSV, or path in TOML and YAML. Other cells are empty, so a row created on this run does not change this run's values.
  A non-empty file whose last byte is not a newline gets a newline, then the new rows.
  When no schema column is added, earlier bytes stay.
  The new row bytes are one write at the end. A crash during that write can leave a partial last row.
  There is no temp file.
  Adding schema columns rewrites the CSV so every row has the new empty cells. The text of each existing cell stays.
  CSV append uses the header after those columns are added, and config.kind_overrides_sep.
  PATH is filled. Other columns are empty.
- A new file is an always create, or an auto or always fill of an empty or whitespace-only file.
  manual leaves that file unchanged. Whitespace in a filled file is not kept.
  A new CSV header starts with PATH.
  When that kind has schema columns, those names follow, in schema order, joined by kind_overrides_sep.
  A kind_schema entry supplies its local names. Otherwise declared vars_schema names are used.
  A name that starts with `__` is left out, except `__date__` when that schema lists it.
  A name that is not a legal column is left out.
  With no schema columns, the header is PATH and __date__.
  Omitted, that header is PATH,__date__. The example semicolon with no schema writes PATH;__date__.
  No SHA column and no DATE column. The header line has no data.
  Then one row per matched file. Each new row sets PATH and leaves the other cells empty.
  A new TOML or YAML file is the same rows, with path set and vars omitted.
- An empty kind_overrides_config creates and appends nothing in every mode.
  In every mode except disabled, -vv still logs that there is no candidate list.
  Omitted uses the default list from 2.3.1.

### 2.3.3 File metadata

`meta()` reads one field from a kept file. The result is an ordinary variable. There is no `metadata_fields` key and no `scan meta` command.

`file()`, `pdf_cdate()`, and `pdf_mdate()` are not commands. File strings are `__file__` fields. PDF dates are `meta("pdf", "creation_date")` and `meta("pdf", "modification_date")`. Those dates use this cache. A cache miss can create `database_file`. There is no second in-process PDF cache.

The `fs` driver is not shipped. Walk strings are already on `__file__`. A `metadata_driver` key named `fs` with no `driver` is a config error, same as any other unknown name.

`scan files` and `scan kinds` do not call drivers and do not open the database. `schema` and `profiles` do not either.

`scan vars`, `record run`, and `record status` call a driver only while a var candidate renders `meta()`. A profile that never calls `meta()` does nothing new. `record status` writes nothing.

A candidate that already succeeded skips the rest of the list. A kind-file cell is a literal. It does not call `meta()`.

#### meta()

`meta(driver, field)` is one Jinja command. Use it in `default_vars` and rule `vars`. `field` may be omitted only when that driver has a single text result (`text`). Omitting it on any other driver fails the candidate.

- An unknown driver name stops the command. When the driver argument is a string literal, that check happens when the template is loaded. A non-literal driver is checked at render.
- A disabled driver, a file the driver does not accept, a missing field, a blank value, a timeout, a non-zero exit, or undecodable stdout fails that candidate only. The next string runs.
- `VarCandidateError` from a custom driver fails that candidate only.
- Any other exception stops the command.
- A blank value is empty after strip. A driver that returns blank fails the candidate. It does not store `""`.

#### metadata_driver

`metadata_driver` is a top-level profile key, next to `default_vars`. It is not under `config`. `default.toml` does not list drivers.

Omitted, null, and `{}` build the builtin defaults only. A present mapping overlays those names. A `metadata_driver` table inside `config` stops the command. The message says to move the key to the top level.

- Builtin overlay. The key is a builtin name and `driver` is omitted. An unknown option for that builtin is a config error.
- Generic command. `driver` is `supershelf.meta_driver`. Several entries may use this module. Each has its own command.
- Custom module. `driver` is `pkg.mod` or `pkg.mod:ClassName`. `pkg.mod` uses the exported `DRIVER`. `pkg.mod:ClassName` constructs that class with no arguments. An import failure, or a missing `DRIVER` or class, is a config error at load.

A key that is not a builtin and has no `driver` is a config error. Setting `driver` on a builtin name replaces that builtin for this profile.

Reserved keys are `driver`, `enable`, `timeout`, `ext`, and `mime`. They are not passed through. Extra keys on a custom entry are `options`.

`enable` is `auto`, `true`, or `false`. Booleans `true` and `false` are those words. Anything else is a config error. Omitted uses the class default (`auto` for the shipped tools).

- `auto`: check once, on the first call. A miss fails that candidate and is logged once.
- `true`: the same check at profile load. A miss stops the command before the walk.
- `false`: the driver is never called. A candidate that names it misses.

`pdf` ignores `enable`. A `timeout` key on it is a config error. Other drivers: omitted timeout is 30, and `0` or below is a config error.

#### Which files a driver accepts

The suffix is the last suffix, without the leading dot, compared case-insensitively. `ext` and `mime` on an entry replace the class lists. Omitted keeps the class list. A string is a one-item list. A leading dot is stripped. An empty list stays empty. Items must be strings.

1. A matching extension accepts the file. Mime is not read.
2. No extension, or no hit: if `mime` is non-empty, probe and compare. A hit accepts.
3. Neither list: accept every file. `exiftool` is that case.
4. `ext` only, and the extension missed: reject, and do not probe.

The probe is `file --mime-type --brief`, once per hash, in memory. If `file` is not on `PATH`, the mime test misses and one warning is logged. The probe is not stored in `content_meta`. A driver that does not accept the file does not spawn and does not write a row.

#### supershelf.meta_driver

`command` is required. A path separator resolves from the profile directory and must be an existing file. The file is executed directly. A bare name is looked up on `PATH`.

`arguments` omitted means argv is only the program. A string is split with `shlex` at load. A bad quote is a config error. Placeholders are replaced after the split. `%p` as its own token keeps a path that contains a space as one argv item. Tokens are `%p %r %n %s %e %h %c %m %d` and `%%`. Any other `%` token is a config error at load. `%r` is `__file__.path`, `%n` is `.name`, `%s` is `.stem`, `%e` is `.ext`, `%h` is `.hash`, `%c` is `.ctime`, and `%m` is `.mtime`. `%p` is the absolute path. `%d` is that path's directory. `%%` is a percent sign. The tokens are argv placeholders for those facts, not a second set of template names.

`output_format` is required: `yaml`, `toml`, `ini`, or `shell`. Nested mappings flatten with `.`. List and null values are skipped. A non-mapping document, a bad TOML duplicate, or a bad shell key fails the candidate. stderr is logged at debug and is not parsed.

`options_key` is the sha256 of canonical JSON: driver identity, `command`, the argument template, `output_format`, and `cache_epoch`. `ext`, `mime`, `enable`, and `timeout` stay out. The bag key is the content hash, the profile key, and `options_key`.

#### Shipped drivers

- `pdf`: always on. `pypdf`. `ext` is `pdf`. `mime` is `application/pdf`. Fields: `creation_date` and `modification_date` as `YYYY-MM-DD`, plus `author`, `title`, `subject`, `creator`, `producer`. A bad date is a missing field. The parsed map is JSON in the cache. `creation_date` and `modification_date` are the PDF dates. There is no `pdf_cdate()` or `pdf_mdate()`.
- `exiftool`: `auto`. Argv is `exiftool -json -G` and the path. Drop `SourceFile` and `File:` keys.
- `pdftotext`: `auto`. `ext` is `pdf`. `mime` is `application/pdf`. Argv is `pdftotext -q -enc UTF-8`, the path, then `-`. The only field is `text`, and it may be omitted.

`pdfinfo`, `mutool`, `ffprobe`, `mediainfo`, `zipinfo`, and `strings` are not shipped. They stay in [drafts/file-metadata.md](drafts/file-metadata.md).

#### Cache

The table is architecture 3. One row per content hash, driver name, and `options_key`. The payload is raw tool stdout, or the `pdf` JSON map. Field lookup is in process.

The process bag is checked first. sqlite is read only after that misses.

- A success stores `payload` and a null `error`. A non-zero exit, timeout, undecodable stdout, or parse error stores `error` and a null `payload`.
- A missing field after a successful parse does not store an error. The payload stays, so a later field on that hash still uses it.
- A driver that does not accept the file writes nothing.
- `scan vars` and `record run` create `database_file` when `meta()` runs and the cache misses. `--dry-run` does not. `scan files` and `scan kinds` do not.
- `--dry-run` reads a version 2 file. If the file is absent, or it is version 1, it does not create it and does not migrate. The tool still runs. Nothing is inserted.
- A real run opens the file for write, which migrates version 1, then inserts the row. That write does not insert a document or an event.
- The same hash on a second path reads the row and does not spawn. A cached error does not spawn again.

## 3 Data

`supershelf data` reads and writes kind files. The doc site is unchanged until implementation.

- It uses the same full walk as scan vars, and the same resolved values.
  There is no --quick and no path filter.
- It does not read or write documents, events, or vars_json, and it does not append a record event.
  Resolution does not read vars_json. Behavior 4 owns those tables.
  cache_file stays unused. content_meta is not that path.
  It does not create an output tree.
- Profile selection is the same as the other commands: --config and --profile.
- Say var, not field. A field is a match-rule slot, such as regex or filename_glob.
  The feed flag is --var.
- Say kind file. kind_overrides_mode, kind_overrides_date_format, kind_overrides_sep,
  and kind_overrides_config are the kind-file settings from 2.3.2.
- scan vars --all prints `__file__` and `__match__` fields. data prune --all runs every purge.
  The two flags do not share a meaning.

### 3.1 Shared rules

- Values are the display strings scan vars prints.
  Layers are facts, default_vars, the match rule, then the kind file.
  A filled cell is already that string. An empty cell receives the lower layer.
  An unset var stays unset. Feed does not blank a cell.
  Namespace fields stay out. `__date__` is allowed.
- kind_overrides_mode does not gate these commands.
  scan vars still owns auto, manual, always, and disabled.
  manual and disabled still allow data feed and data prune to write.
  An empty kind_overrides_config means there is no file to read or write, and the command stops.
- The kind file is chosen as in 2.3.2. The first existing template wins.
  A missing file is created from the first template when the command needs to write.
  Parent-directory rules stay the same as 2.3.2.
  data prune does not create a missing file.
- A new CSV column is appended on the right. Feed does not reorder columns.
  TOML and YAML append a new key and keep the existing key order.
- The stored cell is the display string. A float stays 12.50. A bool stays true or false.
  scan vars in auto and always must not rewrite existing cell text.
  Feed and prune do rewrite the file. Values that were not selected stay.
  CSV quoting and column adds may change bytes.
- Two inputs that share one kind file and the same relative path:
  if the selected values differ, stop and name both inputs. Do not pick one.
- A mandatory var that is still unset stops the command before any write, same as scan vars.
- Duplicate path rows: update the first, leave the later row, and keep the warning from 2.3.2.
  A rewrite must not drop that later row.
- --dry-run prints the same summary the prompt would show, asks nothing, and writes nothing.
  It does not create the sqlite file, and it does not migrate it.
- A resolve error writes no kind file.
  A content_meta row already stored during that resolve stays.
- data feed and data prune edit kind-file cells and columns only.
  Those writes are not database rows.
  Feed resolves like scan vars. When a candidate calls meta(), feed uses the content_meta rules in 2.3.3.
  That cache write happens while the preview is computed, before Continue?
  A no leaves the cache in place, including a schema 1 file migrated to schema 2, and does not edit the kind file.
  The prompt guards kind-file edits only.
  Prune does not render templates, so it does not open the database.
- A feed or prune can change what the next record run resolves.
  That run may append a vars event. data does not write the event.
  A kind cell filled by feed is later labeled kind:<path>, not rule:<name>.
- data has no PATH filter. --missing uses the full walk.
  A later PATH filter must not drop kind-file rows outside that filter.
- data feed and data prune ask once for the whole run, before any write.
  The question is on stderr. y or yes writes. Anything else writes nothing.
  Not a terminal, and no --force, stops the command and tells the user to pass --force.
  --force writes without asking.
  The prompt names which kinds, vars, or purges are enabled.
- data show does not write kind files and does not prompt.
  It may write content_meta, as in 3.4.

#### Cases

Empty kind paths. `kind_overrides_config: []` stops `data feed`, `data prune`, and `data show`. There is no file to use.

Disabled mode. `kind_overrides_mode` is `disabled`. `data feed` still creates or updates the kind file from the first template.

Shared path. Two inputs resolve the same kind file and the same relative path, and the selected `vendor` values differ. The command stops and names both inputs.

Not a terminal. `data feed` with no `--force` and no `--dry-run` stops and tells the user to pass `--force`.

Documents left alone. `data feed` fills an empty `vendor` cell. No document row and no event is written. The next `record run` may append `vars`. The new source label is `kind:<path>`.

Cache before the prompt. A candidate calls `meta()` and `content_meta` misses. The preview creates or migrates the sqlite file and inserts the cache row, then asks `Continue?`. No leaves that cache and does not edit the kind file.

Dry run. `data feed --dry-run` prints the summary and does not create, migrate, or insert `content_meta`.

### 3.2 data feed

#### Command

- supershelf data feed [NAMES]
- Writes resolved values into the kind files.
- NAMES is one optional comma-separated argument. Spaces around commas are ignored.
  Each token must be either a rule kind or a var name, not both.
  A token that matches both stops the command and names --kind and --var.
- --kind is a comma-separated list of kinds.
  Selecting a kind enables every schema var of that kind.
- --var is a comma-separated list of var names.
- --kind and --var together keep only those vars on those kinds.
  A --var name that none of the selected kinds define stops the command.
- Positional names and the flags combine. An explicit flag is how a shared name is chosen.
- An unknown kind or var stops the command. A namespace root, or any other name that starts with `__` and is not `__date__`, stops the command.
- --force skips the prompt.
- Feed does not also append the empty rows scan vars appends.

#### Selectors

- No arguments: every kind that has a matched file, and every schema var of that kind.
- Schema vars are the CSV header names for that kind. 2.3.2.
  A kind_schema entry uses its local names. Otherwise the declared vars_schema names are used.
  __date__ is included only when that schema lists it.
- A kind with no schema columns has no schema vars.
  Feed then uses the user-visible names scan vars would print for files of that kind,
  so dates and rule vars still get a cell.
- Selecting a kind enables all of that kind's schema vars, or the no-schema fallback above.

#### Write

- Write the resolved display string into the selected cell.
  A filled cell is already that string, so the text stays.
  An empty cell receives it.
- __date__ is written with kind_overrides_date_format, not the stored YYYY-MM-DD.
  Other date vars stay YYYY-MM-DD. The kind-file format applies to __date__ only, as in 2.3.2.
- An unset var does not blank a cell.
- A selected name missing from the file is added. A matched path with no row is added.
  Other columns and other rows stay.
- CSV column rules from 2.3.2 still apply.
  A name that is not a legal column is left out of CSV and reported.

#### Prompt

- One paragraph plus the file list.
  It names the selected kinds and vars, then says it writes those resolved values into empty cells.
  A filled cell stays.
  Then each kind file path and how many cells would change.
  Question: Continue? [y/N]
- -v lists the cells that would change. The summary is enough at the default log level.

#### Cases

Both names. `invoice` is a kind and a var. `data feed invoice` stops and names `--kind` and `--var`.

No schema. A kind with no schema columns feeds the user-visible names `scan vars` prints, including a set `__date__`.

Date round-trip. Stored `__date__` is `2026-04-25`. `kind_overrides_date_format` is `%d/%m/%Y`. Feed writes `25/04/2026`. A `date` var that is not `__date__` stays `YYYY-MM-DD`.

Filled cell. The kind file already holds `Bank2000`. Feed writes `Bank2000` again. The text stays.

Empty cell. The rule set `vendor` and the cell is empty. Feed writes the rule's display string.

Unset. No layer set `owner`. Feed does not blank a hand-written `owner` cell, and it does not add an empty cell.

### 3.3 data prune

#### Command

- supershelf data prune
- Edits existing kind files. It does not create a missing file.
- Flags are independent. Passing one flag does not turn the others on.
- No flags means the empty-column purge only.
- --all means every purge below.
  With --clear, each file is left empty, so the other purges do not change that result.
- --force skips the prompt.
- The prompt names which purges are enabled, lists the files, and gives the row and column counts.
  Same --force, terminal, and --dry-run rules as data feed.

#### Purges

- Default, also available as --empty-fields:
  Drop a column or key that is not in that kind's schema and whose cells are all empty.
  An empty schema column stays. A non-empty extra column stays. One filled cell keeps the column.
  CSV drops the column. TOML and YAML omit the key.
- --missing:
  Drop a kind-file row whose path is not a matched file of that kind in this scan.
  This is not document presence missing. It does not delete a document, an event, or a hash.
  A document can stay missing or unmatched in the database after its kind-file row is gone.
  A file that moved to another kind is dropped from the old kind file.
  Two inputs that share one kind file keep the row when either input still matches that path for that kind.
- --clear:
  Rewrite each existing kind file with no rows. The file stays.
  CSV keeps its header. TOML and YAML keep an empty document.
  It does not delete the kind file, and it does not empty the database.
  The next record run sees the lower layers and may append vars.

#### Cases

Prune default. A column `note` is not in the schema and every cell is empty. No flags drops it. A schema column that is empty stays. A non-schema column with one filled cell stays.

Prune flags. `--missing` does not also drop empty columns. `--empty-fields` does not also drop missing rows. `--all` includes `--clear`, so the kind file ends with no rows. The database rows stay.

Missing word. `--missing` drops a kind-file row for a path that is not matched as that kind. The document row stays, including when its presence is `missing`.

### 3.4 data show

#### Command

- supershelf data show [KIND]
- Prints the live resolve. It does not read documents, events, or vars_json.
  It does not write kind files and it does not prompt.
  A recorded document is not required. A file that was never recorded is still shown.
  When a candidate calls meta(), show uses the content_meta rules in 2.3.3.
  A real show may create or migrate the sqlite file. --dry-run does not.
- One table per profile and kind, because each kind has its own columns.
  It does not return one merged row list.
  A title line names the profile, the kind, and the kind file path when there is one.
- Columns are path, then the var names: schema order first, then any other user-visible name scan vars would print.
  Values are the display strings. An unset var is blank.
- KIND limits the output to that kind. An unknown kind stops the command.
  A known kind with no matched files prints the title and no rows.
- No KIND prints every kind that has a matched file.

## 4 Record

`supershelf record` stores matched files in the profile sqlite file from `config.database_file`. The schema, the decision order, and the output-event slot are architecture 3. One file per profile. Profiles do not share rows. `cache_file` stays unused. This step does not write an output tree. Behavior 5 does.

`scan vars`, `record run`, `data feed`, and `data show` create it when `meta()` runs and the cache misses. `--dry-run` does not. `scan files`, `scan kinds`, `scan inspect`, `schema`, `profiles`, and `data prune` do not. `record run` also creates it when a document row would change. `data feed` and `data show` do not insert a document or an event. A feed prompt answer of no can leave the cache, and a schema 1 file already migrated to schema 2.

The walk is the full walk from 2.1.2. There is no `--quick`. Variables resolve as in 2.3.1, including kind-file reads. `record` does not call the kind-file commit, so it does not create or append a kind file.

### 4.1 Commands

`PATH` is the optional scan selector from 2.1.1. A value that matches no kept file and no in-scope document stops `record status` and `record run`. `record history` and `record duplicates` do not scan. A selector that matches nothing there prints no rows.

Columns are a clak table.

#### record status

- supershelf record status [PATH]
- Prints every in-scope live matched file, plus every in-scope document this scan would mark missing or unmatched.
- Writes nothing. A missing sqlite file stays missing. An existing file is opened read-only.
- Columns: profile, input, path, status, hash, generation, kind, rule, duplicates.
- input is the 1-based index. path is relative to the input directory.
- status is `new`, `generation`, `move`, `vars`, `missing`, `present`, `unmatched`, `refresh`, `unchanged`, or `duplicate`.
- duplicates is how many other in-scope present documents share that hash, plus how many extra live files this plan reports as `duplicate` for that hash.
- A `duplicate` row is an extra live file. path is that file. The hash is the owner's hash. It is not inserted. `record history` has no row for it.
- `--record-identity` is a word or a comma-separated list. 4.2.

#### record run

- supershelf record run [PATH]
- Prints the status rows whose status is not `unchanged`, then writes every printed row except `duplicate`.
- `--dry-run` prints those rows and writes nothing. It does not create the sqlite file, its parents, or a journal.
- A run with no changes does not create a missing sqlite file.
- A run that prints only `duplicate` rows writes nothing and does not create a missing sqlite file.
- A run with changes creates parent directories, then writes one transaction per profile.
- A later profile can commit after an earlier profile already committed.
- `--record-identity` is the same flag as `record status`.

#### record history

- supershelf record history [PATH]
- Reads events in id order. It does not scan and does not write.
- No database means no rows.
- PATH matches a document when any of its event paths, or its current path, equals the selector or starts with it. The command then prints every event for that document, so a move is still found from the old path.
- Columns: profile, document, seq, event, identity, input, path, hash, generation, kind, rule, at.

#### record duplicates

- supershelf record duplicates [PATH]
- Reads the database. It does not scan and does not write.
- A hash is listed when two or more documents have carried it on any event.
- PATH filters on the document's current relative path.
- Columns: profile, hash, document, current, path, generation.
- current is `yes` when that hash is the document's current hash, and `no` when the hash is an earlier generation.

### 4.2 Link

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

#### Cases

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

### 4.3 Writes

- A resolve error writes nothing.
- A matched file whose absolute path is the profile sqlite file is skipped, with a warning. That location is left out of this run.
- The sqlite parent must be a directory. A parent that is a file stops the command and names `database_file`.
- A path that exists and is not a supershelf database stops the command. The tip says to point `database_file` at a new path.
- Schema version is `1`. A different version stops the same way. This step does not migrate.
- A locked file stops the command. The tip says to run the command again.
- `--dry-run` on `record run` reports the rows that would change and creates nothing.
- `record status`, `record history`, and `record duplicates` do not write. Passing `--dry-run` to them changes nothing.

## 5 Output

`supershelf output` writes a destination for matched files and records that apply. The driver contract is architecture 4. This step ships the file driver. It calls `ShelfDatabase.append_output`. Schema version stays `2`. No new column. `record_key` keeps the next migration.

One profile has one sqlite file. Profiles do not share events. `cache_file` stays unused. `extension_remap` is not read.

The walk is the full walk from 2.1.2. There is no `--quick`. Variables resolve as in 2.3.1, including kind-file reads and `meta()`. `output` does not call the kind-file commit.

The comparison is the record status plan from behavior 4. Output does not implement a second linker. `record_identity` stays a step list. The packaged default `path` means `[path, hash]`. A bare `hash` means `[hash, path]`. A match rule can override the list.

The plan phase resolves like `record status`. A metadata cache miss does not create the sqlite file. `--dry-run` does not create it and does not migrate schema `1`. A real run opens the existing file for write only when an event would be appended. That open migrates schema `1` to schema `2`, as architecture 3.5. A missing file is not created. With no documents, a file that passes `kinds` and `when` is `new`, and the gate in 5.2 stops the command. The tip says to run `record run`.

`scan`, `data`, `record`, `schema`, and `profiles` do not read `outputs`.

### 5.1 Commands

`PATH` is the optional scan selector from 2.1.1. A value that matches no kept file stops the command. Columns are a clak table: profile, input, path, output, driver, status, operation, when, dest.

input is the 1-based index. path is relative to the input directory. output is the item name. when is the boolean string `true` or `false`. dest is the absolute destination, or blank when `when` rendered `false`.

Rows follow profile selection, then output list order, then walk order.

#### output preview

- supershelf output preview [PATH]
- Prints every selected row, including `unchanged` and `skip`.
- Writes nothing. It does not create the sqlite file, a parent, a destination, or a directory.
- The database is opened read-only.
- Exit 0 when the plan is valid. A `conflict` row is valid here. The command still exits 0.

#### output run

- supershelf output run [PATH]
- Prints the same rows, except `unchanged`.
- `--dry-run` prints those rows and writes nothing. The database stays read-only. Schema `1` is not migrated.
- A real run that would stop does stop under `--dry-run`, and still writes nothing.
- A plan with only `unchanged` and `skip` writes nothing and does not open the database for write.
- Every selected profile is planned before any profile writes. A later profile does not commit when an earlier profile's plan would stop.
- A real write creates the destination parent, performs the file operation, then calls `append_output`. The method commits itself.
- A crash after the write and before the event leaves a file this profile does not yet claim. The next run treats it as a foreign file.

Status words:

- `write`: the destination is created.
- `replace`: an existing destination is replaced.
- `unchanged`: this profile already wrote this destination, and the file still matches. No event.
- `skip`: `when` is `false`, or `on_conflict` is `skip` and the existing file is left in place. No event.
- `conflict`: the existing file is not one this profile wrote, and `on_conflict` is `error`. Preview prints the row and exits 0. `run` prints the rows and exits non-zero. Nothing is written.

### 5.2 Selection

`outputs` is a top-level list.

- Omitted or null, on an output command, stops the command. The message says outputs is not set.
- `[]` stops the command. The message says outputs is empty.
- These are the two messages `inputs` already uses. The other commands ignore the key.

Each item has `name`, `driver`, `kinds`, and `when`. The driver owns every other key. A file item that carries a key it does not know stops the command.

- `name` is required. It is a non-empty string and unique in the profile. A duplicate stops the command.
- `driver` defaults to `file`. An unknown name stops the command and names the driver.
- `kinds` omitted or null means every matched kind. The kind is the final kind after overrides.
  `[]` selects no file. That item adds no row. It is not an error.
  A listed value that is not a string stops the command.
  A name that matches no rule does not stop at load. A file of another kind is left out. It is not a `skip` row.
- `when` omitted or null is the string `true`.
  A value that is not a string stops the command. An unquoted YAML bool is that error. A list is that error.
  A string with no Jinja marker is cast at load. A template is compiled at load. A syntax error stops the command before the walk.
  Render uses the file's display-string scope, the same commands as a variable template, and StrictUndefined.
  Strip the text. `true`, `yes`, and `1` become `true`. Empty text, `false`, `no`, and `0` become `false`. Case does not matter.
  Any other text stops the command and names the output, the path, and the rendered text.
  `{{ __match__.kind == "invoice" }}` renders `True` or `False`, and those cast.
  `false` is status `skip`. The layout is not rendered. No event is written.
  An undefined name stops the command, same as a variable template.

A live file the record plan marks `duplicate` has no document. It is left out. It does not stop the other files. The owning document is the one that can be written. A `PATH` that matches only that extra file stops the command, because no kept output source was selected.

A file that passes `kinds` and `when` must already be a present document whose record status is `unchanged` or `refresh`. `new`, `vars`, `generation`, `move`, `missing`, `present`, and `unmatched` stop the command before any destination is written and before any output event. The message names the profile, the input, the path, and the record status. The tip says to run `record run`. `refresh` is allowed because the hash and the variables are the same.

A file that fails `kinds`, or whose `when` is `false`, does not face that gate. A `duplicate` that would have passed `kinds` and `when` is still left out.

The profile sqlite file is ignored when it sits inside an input, same as record.

`config.output_modules` is an optional list of importable module paths. Omitted, null, and `[]` add no drivers. The built-in `file` driver is registered first. Each module is imported in list order and exports `DRIVERS`, a list of driver classes. A name that repeats `file`, or an earlier module, stops the command. An import failure stops the command. This list is not `var_modules` and not `metadata_driver`.

### 5.3 File driver

`driver: file` is the default.

- `path` is required. It is a profile path template, the same language as `inputs.path`. It is rendered once. A relative result resolves from `__config__.root_dir`. An empty result stops the command. A result that exists and is not a directory stops the command. A missing directory is created only on a real write.
- `layout` is a Jinja template. Omitted, it is `{{ __file__.path }}`. The input-relative path is kept.
  The rendered text uses `/` separators. It is split on `/`.
  An absolute result stops the command. An empty result stops the command.
  A segment that is empty, `.`, or `..` stops the command.
  A slash inside a variable becomes another directory.
  The joined path must stay inside `path`. The extension is whatever the layout writes. `{{ __file__.ext }}` is the last suffix.
  `{{ __date__ }}` prints with `default_date_format`. `Y`, `m`, and `d` are the `%Y`, `%m`, and `%d` fields.
  `{{ __date__.strftime('%Y-%m') }}` is a custom pattern. A template that uses `__date__` fails when `__date__` was omitted.
- `operation` is `copy`, `symlink`, or `hardlink`. Omitted, it is `copy`. Any other word stops the command.
- `on_conflict` is `error`, `skip`, or `overwrite`. Omitted, it is `error`. Any other word stops the command.
  It applies when the destination exists and this profile has no output event for that path.
  It also applies when the latest event for this document and output name matches the destination, the operation, and the source hash, but the file on disk no longer matches that apply.
  It does not apply to a destination claimed twice in this run. It does not apply when the latest event for that path belongs to another document or another output name.

The latest event for a document and output name is the prior apply. The latest event for a destination is the claim. Both reads use the events already stored. An output event does not change the document.

- The prior apply matches the new destination, the operation, and the source hash, and the file on disk matches that apply. Status `unchanged`. No write and no event.
  A copy matches when the destination sha256 equals the source hash.
  A symlink matches when its target is the absolute source path stored under the input.
  A hardlink matches when it is the same inode as that source.
- That prior apply is ours and the source hash or the operation changed. Status `replace`. `previous` is `existed` true and `ours` true, with the prior operation and source hash.
- The path does not exist, and no other document claims it. Status `write`. `previous` is `existed` false. `ours` is true only when an earlier event for this profile already recorded that same path. Then `previous` also carries that event's operation and source hash.
- The path exists and this profile has no event for it.
  `error`: status `conflict`. `run` writes nothing.
  `skip`: status `skip`. The file stays. No event.
  `overwrite`: status `replace`. `previous` is `existed` true and `ours` false. Revert cannot restore those bytes. The database stores the hash, not the file.
- The prior apply matches, but the file on disk does not. The same three words. `overwrite` stores `existed` true and `ours` true, with the prior operation and source hash.
- A new layout points the document at a new path. The old file stays. Prune is a later `output prune`. The new path follows the rules above.
- The latest event for the destination belongs to another document, or to another output name of this document. The command stops. `on_conflict` does not apply. The message names the destination and both owners.
- Two planned actions in this run resolve to the same destination. The command stops before any write. The message names the destination and both sources. This includes two profiles selected together.
- The source path and the destination path are the same file. The command stops.
- The destination exists and is a directory. The command stops.

`copy` uses a metadata-preserving file copy. `symlink` points at the absolute source path stored under the input. `hardlink` links that path. A cross-device hardlink stops the command. The tip says to use `copy`.

Parents are created on a real write. A parent that exists and is a file stops the command. Preview and `--dry-run` create nothing.

`append_output` runs after the file operation returns, and only for `write` and `replace`. `recorded_at` is UTC ISO-8601. `source_hash` is the document hash. `output_name` is the item name. `destination` is the absolute path.

#### Cases

Second run. The copy is still the same bytes. Status `unchanged`. `run` prints no row for it. No event is appended.

New bytes. `record run` stored the generation. The next output run replaces the copy. `previous` has `ours` true and the old source hash.

Not recorded. The file is `new`. The command stops. The tip says to run `record run`. Nothing is written.

Duplicate. `record_identity` is `hash`. The extra path has no document. Output leaves it out. The owning document is written when its own row is `unchanged`.

Foreign file. The destination exists and no output event names it. `on_conflict` is `error`. Preview shows `conflict` and exits 0. `run` writes nothing and exits non-zero.

Skip. The same foreign file, with `on_conflict: skip`. Status `skip`. The file stays. No event.

Overwrite. The same foreign file, with `on_conflict: overwrite`. The file is replaced. `previous` has `existed` true and `ours` false.

Other document. The latest event for that path belongs to another document. The command stops. `overwrite` does not take the path.

Layout move. `layout` changes. The new path is `write`. The old file stays on disk. The old event stays.

When. `when` renders `false`. Status `skip`. The column is `false`. The layout is not rendered. A file whose record status is `new` does not stop the command when `when` is `false`.

Bool words. `when: '{{ __match__.kind == "invoice" }}'` becomes `true` or `false`. `when: maybe` stops at load. `when: '{{ vendor }}'` stops when vendor renders `Bank2000`.

Escape. A layout that renders `../outside` stops the command. A layout that renders an absolute path stops the command. No directory is created.

Two outputs. One file matches `books` and `cards`. Both destinations are planned. The same destination from both items stops the command before any write.
