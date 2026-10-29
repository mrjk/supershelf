
# General rules

## Python Coding rules

* Always use OOP and classes (when it make sense): inheritance, compositions and so ...
* Use github/mrjk/clak as main CLI library
    * Use standard CLI output/format features (especially the table output)
    * Always reuse common CLI flags in common to make code DRY
* Always add tests when you add new features or update existing tests if needed

## Main App

* Structured like git-like commands, with subcommands
* must support log levels and dry run options
* COmmon options flags must be setup at the top, specific are attached to subcommand only. Use CLI flags classes+inheritabnce if ncecessary to be able to reuse common flags.
* Configuration order precedence (12 factors apps):
    * CLI
    * Env vars
    * YAML Config
    * Defaults
* For the configuration file format, i want to be able to generate a schema of it, and also raise errors when the user make configuration mistakes.
