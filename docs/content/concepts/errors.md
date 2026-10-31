# Errors

User errors stop the command and print a message without a traceback. When the error includes a tip, the tip is printed too.

`SupershelfError` covers discovery, profile files, inputs, and match rules. A missing config, an unknown profile, a bad regex, and a path that is not a directory are this kind of error.

`VarConfigError` is a `SupershelfError` for a var table, a template, a module, or a kind file that is invalid as written. It exits with status 2. These are checked before the walk, except a kind file, which is checked the first time that kind and input need it.

`VarResolveError` is a variable whose candidates all failed while a file was being resolved. The message names the profile, the input, the path, and the variable. The tip is the last candidate miss, when there is one.

`VarCandidateError` is not an exit by itself. Built-in commands and user modules raise it to skip one candidate. The next candidate then runs. If you raise any other exception from a module, the command stops.

## Warnings

These do not fail the command:

- a kept file that no rule claims
- a missing input directory
- an unreadable file or directory
- a symlink cycle
- `config.profile` ignored because the filename already named the profile
- a later config format ignored because toml, yaml, or yml already won
- a second file ignored because that profile name was already loaded

`scan inspect` writes its trace to stdout. A path that no kept file has is an error for every scan command.
