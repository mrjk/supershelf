# Errors

User errors stop the command and print a message without a traceback. When the error includes a tip, the tip is printed too.

`SupershelfError` covers discovery, profile files, inputs, and match rules. A missing config, an unknown profile, a bad regex, and a path that is not a directory are this kind of error.

`VarConfigError` is a `SupershelfError` for a var table, a `vars_schema` entry, a `kind_schema` entry, a template, a module, or a kind file that is invalid as written. It exits with status 2. These are checked before the walk, except a kind file, which is checked the first time that kind and input need it. A non-template literal that cannot cast to the name's type is this error, including when a later candidate might have worked. `supershelf schema` uses the same check. A profile with neither `vars_schema` nor `kind_schema` stops that command with this error.

`RecordConfigError` is a `record_identity` value other than `path` or `hash`. It exits with status 2. The message names `--record-identity`, `SUPERSHELF_RECORD_IDENTITY`, or `config.record_identity`.

`DatabaseError` is a profile sqlite file that cannot be used: the parent is not a directory, the path is not a supershelf database, the schema version is not 1, or the file is locked. It exits with status 1. The tip names a path change or a retry.

`VarResolveError` is a fact or kind-file cell that cannot cast, or a `mandatory` name that is still unset after the last layer. A candidate list that misses does not raise it. The message names the profile, the input, the path, and the variable. The tip is the cast message for a failed fact or cell, `{name} is mandatory and no layer set it.` when a mandatory name is still unset, or the date-format message for a kind-file `__date__` cell. There is no next candidate.

`VarCandidateError` is not an exit by itself. Built-in commands and user modules raise it to skip one candidate. A rendered value that misses the name's type or its validation skips that candidate the same way. The next candidate then runs. Any other exception from a module is not caught here. The command stops and the traceback is printed.

## Warnings

These do not fail the command:

- a kept file that no rule claims
- a missing input directory
- an unreadable file or directory
- a symlink cycle
- `config.profile` ignored because the filename already named the profile
- a later config format ignored because toml, yaml, or yml already won
- a second file ignored because that profile name was already loaded
- a duplicated path in a kind file; the first row is kept

`scan inspect` writes its trace to stdout. A path that no kept file has is an error for every scan command.
