# Matching

`match_rules` is a profile-level list, a sibling of `inputs`. Every input of that profile uses it. Patterns are literal. They are not templates.

`scan kinds` uses the files `scan files` would keep, without hashing and without reading mtime or ctime. It prints matched files only. Columns: `profile`, `input`, `path`, `kind`, `rule`. `input` and `path` mean the same thing as in `scan files`.

## First hit wins

For each kept file, rules are tried in list order. The first rule that matches wins. Later rules are not tried.

A rule matches when one field matches. Fields are tried in this order. The first hit wins. Later fields are not tried.

1. `regex`
2. `directory_regex`
3. `filename_regex`
4. `glob`
5. `directory_glob`
6. `filename_glob`

A field may be a string or a list of strings. A string is one pattern. Patterns in a list are tried in order. The first hit wins. An omitted field or an empty list is skipped.

For input directory `/srv/in` and file `/srv/in/Bank2000/card/statement.pdf`:

- `regex` and `glob` see `Bank2000/card/statement.pdf`, the path relative to the input, with `/` separators.
- `directory_regex` and `directory_glob` see `Bank2000/card`. That is the path between the input directory and the file, with no filename and no leading or trailing slash.
- `filename_regex` and `filename_glob` see `statement.pdf`.
- A file in the input directory has an empty directory. `directory_regex` and `directory_glob` do not match it.
- The input directory is that input's path, not `config.root_dir`.
- A symlink uses the path stored under the input.

## Regex and glob

Regex is anchored to the whole candidate. The engine full-matches. Authors do not write `^` or `$`. A pattern that stops before the extension does not match a file that has one. `directory_regex` has no filename, so it does not include an extension.

Globs full-match the whole candidate, with the same `*` and `**` rules as include and exclude. `**` also matches a file sitting in the input directory, so `glob = "**"` claims every kept file. A glob does not capture groups. `*` consumes the extension, so `filename_glob = "REL*"` matches `REL_1.pdf`.

Named groups from the winning regex are kept. Unnamed groups are ignored. Groups are not merged across fields or rules. A group name that starts with `__` is a config error, checked before the walk. A group whose name repeats an internal fact or `file_ctime` or `file_mtime` is dropped, because those facts are already set.

Patterns are compiled once per profile, before the walk. A bad pattern stops the command before that walk.

## Name and kind

A rule needs a `name`, a `kind`, or both. A blank value counts as omitted.

- When both are set, the kind is the explicit kind and the rule name stays `name`.
- When only `name` is set, the kind is that name.
- When only `kind` is set, the rule name is that kind.

The rule name must be unique in the profile. A duplicate stops the command. Several rules may share one kind when their names differ. A rule with neither name nor kind, or with no patterns, stops the command.

Unknown keys on a rule are ignored while matching. `vars` is read later by `scan vars`, from the raw rule mapping.

If `match_rules` is missing, or a file matches no rule:

- A warning names the profile, the input, and the relative path.
- The file stays on the scan result, with the data the walk already gathered.
- It is left out of the matched set. No kind is stored.
- `scan kinds` does not show that file.
- Warnings do not fail the command.

Files the walk skipped never reach matching. `scan kinds` does not create the database file or the cache file.
