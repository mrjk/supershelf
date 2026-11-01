# Behavior

What the commands do. Types, cast, and packaged defaults are in [architecture.md](architecture.md). A profile a user would paste is in [examples.md](examples.md). `2.3.3` is parked in [drafts/file-metadata.md](drafts/file-metadata.md).

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
  - __profile__ is %PROFILE_NAME when the filename has one.
    If config.profile is a different non-empty string, warn that it is ignored.
    The same name does not warn. A blank config.profile is treated as unset.
  - If the filename has no %PROFILE_NAME, __profile__ is config.profile when that is set, otherwise default.
  - Write config.profile = __profile__ on the stored dict.
  - If two files resolve to the same profile, warn and keep the first.
- App is inited:
  - config_list is one or more ShelfConfig:
    - profile: __profile__
    - type: toml or yaml
    - path: config file path
    - config: parsed file contents
  - The file must be a mapping. config, when present, must be a mapping.
    config.profile, when present, must be a string. Other keys are stored and not interpreted in this step.
- App commands:
  - supershelf profiles: table of profile, type, and path.
    This is the list selected by --config / $SUPERSHELF_CONFIG and --profile / $SUPERSHELF_PROFILES.

## 2 Profile initialization

- supershelf profiles only lists profile, type, and path. It does not build a ShelfProfile.
- A command that needs rendered paths, such as scan, creates one ShelfProfile per selected ShelfConfig.
  - Read config dict:
    - setup vars:
      - base:
        - __profile_name__ = profile name from the loader
        - __profile__ = alias of __profile_name__
        - __default_date_format__ = Direct value, not templated. scan files uses it to show mtime and ctime.
      - template config values in this order:
        - root_dir
        - database_file
        - cache_file
      - After each value is rendered, a relative path is resolved from __profile_dir__, then stored before the next value is rendered.
      - Built-in defaults when the key is omitted:
        - default_date_format = '%Y-%m-%d'
        - root_dir = "{{ __profile_dir__ }}"
        - database_file = "{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite"
        - cache_file = "{{ __root_dir__ }}/profile.{{ __profile__ }}.cache"

  - User Exposed Var Scope as template. Common values use flat keys. Dot notation remains for inner config, such as __config_data__.
    # Main
    - __profile__ # Alias of __profile_name__
    - __default_date_format__
    # Core config
    - __root_dir__
    - __database_file__
    - __cache_file__
    # Profile vars
    - __profile_name__ # Profile name
    - __profile_type__
    - __profile_path__ # Full path of the config file, from /
    - __profile_dir__ # Full directory of the config file
    - __profile_file__ # Filename of the config file
    # Config vars
    - __config_data__ # Allow access to any config parameter, actually allow to self reference this file.

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
- If that path is relative, resolve it from __root_dir__. Relative input paths are resolved when the input is processed.
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
- A pattern that is not a string, a rule with neither name nor kind, or any other bad shape is a config error.
- match_rules missing, or a file that no rule claims:
  - Log a warning with profile, input, and relative path.
  - Keep the file on the scan result, with the data the walk already gathered.
  - Leave it out of the matched set. Do not store a kind.
  - The kinds table does not show that file.
  - Warnings do not fail the command.
- Files the walk skipped never reach matching.

## 2.3 Vars

`scan vars` resolves variables in 2.3.1 and may read or append a kind file in 2.3.2.

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
  - kind is the match-rule kind. rule stays the match rule name. Nothing else may set __kind__.
  - vars is one cell. Each final key is one line: the name, ": ", then the value.
    File order follows the walk. Inside the cell, the lines are
    regex groups in pattern order, then assignment keys in first-seen order.
    Internal facts are omitted unless --all is set.
    A fact replaced by an assignment is printed once, with the final value, in its fact position.
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
- Profile scope from step 2 is a fact. It is available to templates. It is not printed.
  Kind path templates below add __kind__ and __input__.path for that render only.
- Internals are facts. They stay in scope for templates. scan vars prints them only with --all:
  - __kind__: the kind from step 2.2. Nothing else may set it.
  - __rule_name__: the match rule name
  - __ctime__ and __mtime__: the stored UTC ISO-8601 timestamps from the walk, not default_date_format
  - __file_hash__: lowercase sha256
  - __file_name__ and __file_stem__: InputFile.name and InputFile.stem
  - __file_ext__: InputFile.suffix without the leading dot. No suffix stores an empty string. archive.tar.gz stores gz.
  - __file_path__: path relative to the input, with / separators
  - __file_dir__: directory relative to the input. Empty when the file sits in the input directory
- The filename does not set __date__. A stem that is a date stays __file_stem__.
  A profile that wants that date writes a candidate, such as
  {{ regex_time_var(__file_stem__, __default_date_format__) }}.
  Later layers may replace a date an earlier layer wrote.
  {{__date__}} in the next layer reads the string the earlier layer kept.
- Named groups from the winning regex are facts. Unnamed groups stay ignored.
  A group name that starts with __ is a config error before the walk.
  A group cannot replace an internal or a profile key.
- Assignments are the user layers. Later wins on the same key. Each layer is applied before the next one starts.
  Var tables are rendered. The per-file row is stored as text. 2.3.2.
  1. default_vars
  2. match_rules[].vars
  3. The per-file row from the kind file. 2.3.2.
     One literal string per cell. It replaces a value the rule already stored.
     It does not change what the rule template already read.
     This is the last assignment layer.
- default_vars and rule vars must not set an internal name.
  A per-file row must not either. 2.3.2.
  __date__ is not an internal.
- Nothing may set __kind__. It stays the kind from step 2.2. It does not change rule.
  default_vars, rule vars, and a kind-file row must not set it.
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
  PDF info for one file hash is read once per process.
- Jinja uses StrictUndefined. An unknown name fails that candidate. autoescape is off.
  The rendered result is stored as a string.
- A string candidate is rendered once. Failure aborts that candidate.
- Inserted strings are not rendered again.
- An empty string is a success for text. For every other type, empty or whitespace is a miss.
- If every candidate in a layer misses, that layer does not write the name.
  An earlier value stays. When no layer has written it, the name stays unset.
  The command continues. mandatory after the last layer stops the file when the value is still unset.
  A fact or a kind-file cell that cannot cast stops the file. There is no next candidate for those.
- __date__, when set, is a calendar date YYYY-MM-DD. A candidate that renders to anything else fails, and the next candidate is tried.
  Supershelf uses this date as the document date, including for output paths.
  This step does not write outputs. A later output that uses __date__ fails when __date__ was omitted.
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
- pdf_cdate() and pdf_mdate() read the PDF info dates. The result is YYYY-MM-DD.
  The call needs parentheses. Bare pdf_cdate is the command, not the date.
  Not a PDF, no such date, or an unreadable file fails the candidate.
  The file is read only when a candidate calls one of these.
- file("ctime") and file("mtime") return the same ISO timestamps as the aliases above.
  Any other argument fails the candidate.
- kind_overrides_config is an optional list of path templates.
  Omitted uses this list, in order:
  - {{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.csv
  - {{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.toml
  - {{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yaml
  - {{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yml
  An empty list means no kind files. -vv logs that once for each kind and input, except when the mode is disabled.
  Render each path with the step 2 language, the profile scope, __kind__ set to the rule kind, and __input__.path set to the absolute input directory.
  A relative result is resolved from __root_dir__.
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
  a bad name, or a forbidden internal name is an error.
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
- A row must not set an internal name.
  Other __ names, including __date__, are allowed.
  A row must not set __kind__. Nothing may set __kind__.

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
- The rule kind picks the file. __kind__ does not change after matching, so the file and the row stay on that kind.
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
  Locked internals are left out. __date__ is included only when that schema lists it.
  A name that is not a legal column is left out.
  With no schema columns, the header is PATH and __date__.
  Omitted, that header is PATH,__date__. The example semicolon with no schema writes PATH;__date__.
  No SHA column and no DATE column. The header line has no data.
  Then one row per matched file. Each new row sets PATH and leaves the other cells empty.
  A new TOML or YAML file is the same rows, with path set and vars omitted.
- An empty kind_overrides_config creates and appends nothing in every mode.
  In every mode except disabled, -vv still logs that there is no candidate list.
  Omitted uses the default list from 2.3.1.

## 3 Data

`supershelf data` reads and writes kind files. The doc site is unchanged until implementation.

- It uses the same full walk as scan vars, and the same resolved values.
  There is no --quick and no path filter.
  It does not create the database file, the cache file, or an output tree.
- Profile selection is the same as the other commands: --config and --profile.
- Say var, not field. A field is a match-rule slot, such as regex or filename_glob.
  The feed flag is --var.
- Say kind file. kind_overrides_mode, kind_overrides_date_format, kind_overrides_sep,
  and kind_overrides_config are the kind-file settings from 2.3.2.
- scan vars --all prints internal vars. data prune --all runs every purge.
  The two flags do not share a meaning.

### 3.1 Shared rules

- Values are the display strings scan vars prints.
  Layers are facts, default_vars, the match rule, then the kind file.
  A filled cell is already that string. An empty cell receives the lower layer.
  An unset var stays unset. Feed does not blank a cell.
  Internal names stay out. __date__ is allowed.
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
- --dry-run prints the same summary the prompt would show, asks nothing, and writes nothing.
- A resolve error writes nothing.
- data feed and data prune ask once for the whole run, before any write.
  The question is on stderr. y or yes writes. Anything else writes nothing.
  Not a terminal, and no --force, stops the command and tells the user to pass --force.
  --force writes without asking.
  The prompt names which kinds, vars, or purges are enabled.
- data show does not write and does not prompt.

#### Cases

Empty kind paths. `kind_overrides_config: []` stops `data feed`, `data prune`, and `data show`. There is no file to use.

Disabled mode. `kind_overrides_mode` is `disabled`. `data feed` still creates or updates the kind file from the first template.

Shared path. Two inputs resolve the same kind file and the same relative path, and the selected `vendor` values differ. The command stops and names both inputs.

Not a terminal. `data feed` with no `--force` and no `--dry-run` stops and tells the user to pass `--force`.

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
- An unknown kind or var stops the command. A locked internal name stops the command.
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
  Drop a row whose path is not a matched file of that kind in this scan.
  A file that moved to another kind is dropped from the old file.
  Two inputs that share one kind file keep the row when either input still matches that path for that kind.
- --clear:
  Rewrite each existing kind file with no rows. The file stays.
  CSV keeps its header. TOML and YAML keep an empty document.
  It does not delete the file.

#### Cases

Prune default. A column `note` is not in the schema and every cell is empty. No flags drops it. A schema column that is empty stays. A non-schema column with one filled cell stays.

Prune flags. `--missing` does not also drop empty columns. `--empty-fields` does not also drop missing rows. `--all` includes `--clear`, so the file ends with no rows.

### 3.4 data show

#### Command

- supershelf data show [KIND]
- Prints resolved values. It does not write and does not prompt.
- One table per profile and kind, because each kind has its own columns.
  It does not return one merged row list.
  A title line names the profile, the kind, and the kind file path when there is one.
- Columns are path, then the var names: schema order first, then any other user-visible name scan vars would print.
  Values are the display strings. An unset var is blank.
- KIND limits the output to that kind. An unknown kind stops the command.
  A known kind with no matched files prints the title and no rows.
- No KIND prints every kind that has a matched file.
