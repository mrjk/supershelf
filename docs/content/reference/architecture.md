# Architecture

A command loads profiles, renders paths, walks inputs, matches rules, and resolves variables. The command line is the supported interface.

1. `ShelfConfigs` finds config files, parses them, and applies `--profile` or `SUPERSHELF_PROFILES`. `supershelf profiles` stops after this step.
2. `ShelfProfile` renders `root_dir`, `database_file`, and `cache_file` for one loaded file.
3. `InputScanner` walks that profile's `inputs` and returns the kept files.
4. `Matcher` compiles `match_rules` once and claims a kind for each kept file.
5. `VarPlan` resolves facts and assignment layers for each claimed file, including a kind file when one exists.

`scan files` runs steps 1 to 3. `scan kinds` and `scan inspect` run steps 1 to 4. `scan vars` runs all five. None of these steps create the database file, the cache file, or an output tree.

Var modules are the extension point. A module listed in `config.var_modules` may export `GLOBALS` and `FILTERS`. Those callables are available inside variable templates. See [Modules](../concepts/modules.md).

<!-- placeholder: api docs -->
