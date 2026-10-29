
# General rules

## Python Coding rules

* Always use OOP and classes (when it make sense): inheritance, compositions and so ...
    * Use methods and private methods when logic belong to a class/object. A clean code i like only have class definitions, if possible.
    * Use standard reusable functions from common.py when possible
    * In last resort, use functions alongside the classes.
* Use github/mrjk/clak as main CLI library
    * Use standard CLI output/format features (especially the table output)
    * Always reuse common CLI flags in common to make code DRY
* Always add tests when you add new features or update existing tests if needed
* Always try to identify reusable code, and expose it in a common or helper.py library
* Ensure the code is DRY


## Development workflow
- I'll ask to plan the idea
    - I will ask you to reiterate many times on asking me questions, and clarifying the plan in way
    - Do not implement if you have doubts
    - Be sure to ask me questions that I can answer, otherwise I'll ask to clarify
    - Usually, I use a spec file, I will want it to be updated before implementation
    - ask for edge cases
- Once it's done, I'll ask for an integration plan:
    - It litterally prepare what need to be written, how, etc ...
    - After the ideation, the plan should be quite ready to use, but i'll still do a review before implementation
- Then we go on implementation from the integration plan
    - Any features should be documented in specs
    - I;ll review the code, ask questions
    - I'll probably ask for changes. Be sure thoses changes are documented in the specs. Warn if it brings inconsistency.

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



