# Template commands

Variable templates can call these commands. They are registered on every profile. A user module cannot replace these names. See [Modules](modules.md).

A miss raises `VarCandidateError`. That fails the current candidate only, so the next string in the list can run. The call needs parentheses. `pdf_cdate` without `()` is the command object, not the date.

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

## file

`file("ctime")` and `file("mtime")` return the same UTC ISO-8601 timestamps as `file_ctime` and `file_mtime`. Any other argument fails the candidate. The result includes the time. It is not rewritten to `YYYY-MM-DD`, so it does not satisfy `__date__` by itself.

## pdf_cdate and pdf_mdate

`pdf_cdate()` and `pdf_mdate()` read the PDF creation and modification dates. The result is `YYYY-MM-DD`. A file that is not a PDF, a missing date, or an unreadable file fails the candidate.

The file is opened only when a candidate calls one of these. Both dates for one file hash are read once per process. A failed read is cached too, so a later candidate does not open the file again.

These two dates are the only file-metadata fields in this version. See [Limits](limits.md).
