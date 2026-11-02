# Architecture

A command loads profiles, renders paths, walks inputs, matches rules, and resolves variables. The command line is the supported interface.

1. `ShelfConfigs` finds config files, parses them, and applies `--profile` or `SUPERSHELF_PROFILES`. `supershelf profiles` stops after this step.
2. `ShelfProfile` renders `root_dir`, `database_file`, and `cache_file` for one loaded file.
3. `InputScanner` walks that profile's `inputs` and returns the kept files.
4. `Matcher` compiles `match_rules` once and claims a kind for each kept file.
5. `VarPlan` resolves facts, then `default_vars`, then the winning rule's `vars`, then the kind-file row for that path. The kind file is the last assignment layer. Each written name is cast to its `vars_schema` type. When that kind has a `kind_schema` entry, the names it lists use the overlaid spec. A name with no entry stays `text`. See [Variables](../concepts/variables.md).

6. `record run` compares that result with the profile database and appends events. `record status` prints the comparison and writes nothing.
7. `output run` plans a destination for files whose record status is `unchanged` or `refresh`, writes the file, and appends an output event. `output preview` prints the plan and writes nothing.

`scan files` runs steps 1 to 3. `scan kinds` and `scan inspect` run steps 1 to 4. `scan vars` runs steps 1 to 5, and may create or append a kind file after the run succeeds. `data feed` and `data show` also run steps 1 to 5. `data feed` and `data prune` edit kind files. `data prune` does not resolve variables. `record status` and `record run` run steps 1 to 6. `record run` does not create or append a kind file. `output preview` and `output run` run steps 1 to 7. They do not create or append a kind file, and they do not create a missing sqlite file. `schema` loads the profile and prints JSON Schema. It does not walk inputs or write a kind file. `scan vars`, `record run`, `data feed`, and `data show` create the database file when `meta()` runs and the cache misses. `--dry-run` does not. `scan files`, `scan kinds`, `scan inspect`, `schema`, `profiles`, and `data prune` do not. `data feed` and `data show` do not insert a document or an event. Nothing writes `cache_file`.

Var modules are one extension point. A module listed in `config.var_modules` may export `GLOBALS` and `FILTERS`. Those callables are available inside variable templates. See [Modules](../concepts/modules.md). Output drivers are another. A module listed in `config.output_modules` exports `DRIVERS`. See [Output](../concepts/output.md).
