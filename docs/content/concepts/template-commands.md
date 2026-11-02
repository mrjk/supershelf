# Template commands

Variable templates can call these commands. They are registered on every profile. A user module cannot replace these names. See [Modules](modules.md).

A miss raises `VarCandidateError`. That fails the current candidate only, so the next string in the list can run. The call needs parentheses.

## regex_time_var

`regex_time_var(value, format, ...)` reads a string and tries each `strptime` format. The first hit wins. The result is `YYYY-MM-DD`. At least one format is required. Formats are separate arguments, because a format such as `%H:%M:%S` contains colons.

```jinja
{{ regex_time_var(date, "%Y%m%d") }}
```

`date` is the variable of that name, often a regex group. The command does not read `__date__` unless you pass that name. A value that matches no format fails the candidate.

## regex_replace

`regex_replace(value, pattern, replacement)` substitutes on that string. Three strings are required. Backreferences are allowed. No match fails the candidate. An invalid pattern fails the candidate.

```jinja
{{ regex_replace(account, "[0-9]{4}$", "") }}
```

## meta

`meta(driver, field)` returns one metadata field. `field` may be omitted only for a driver whose only result is text, such as `pdftotext`.

```jinja
{{ meta("pdf", "creation_date") }}
{{ meta("pdf", "author") }}
{{ meta("pdftotext") }}
```

PDF dates are `creation_date` and `modification_date`. Both are `YYYY-MM-DD`. File strings are `__file__` fields, not a driver. A disabled driver, a file the driver does not accept, a missing field, or a tool failure fails that candidate. The next string in the list can run. A cache miss can create `database_file`.
