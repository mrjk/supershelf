
# General rules

## Application project
* Ensure a GPL license is present in project, unless another license is mentionned
* Documentation should be structured this way, keep only what is relevent:
    * top README.md:
        * Simple and professional README, that shows what the program do, some examples etc ..
    * If there is a documentation site
        * It lives in docs/ subdir
        * Structure:
            1. Quickstart
                - Have roughly the same content as top README.md
                - install the program, and test with --version
                - show the very basic commands
            2. Usage
                - Explain how to handle step by step, it must be a progressive learning, it must
            3. Guides
                - Grab specific use cases, and document them
            4. Reference (mostly generated)
                - CLI --help output
                - configuration schema/reference
                - code generated documentation for API
            5. Project
                - how to setup developement environment
                - how to build, release, debug
                - license, code of conduct
                - informations

* We use mise, aka mise-en-place. Ensure a config is present, and it must provide all the development toolkit to be able to run the whole project. Language domain dependency take the relay (pyproject.toml for python, etc ...)

## Python Coding rules

* Always use OOP and classes: inheritance, composition, and so on. THIS IS NOT OPTIONAL
    * Use methods and private methods when logic belongs to a class or object. A clean file only has class definitions.
    * Use a parent class when several classes share the same behavior.
    * In src/, module-level functions are forbidden except common.py and main().
    * New behavior is a method on the class that owns the data.
    * Do not add a helper function because the file already has some.
    * Matching the existing style, and keeping the diff small, do not override this.
    * "When it makes sense" is not an exception for private helpers.
    * If you touch an existing helper, move it onto the class in the same change.
    * Reusable behavior that belongs to no one class goes in common.py.
* Use github/mrjk/clak as main CLI library
    * Use standard CLI output/format features (especially the table output)
    * Always reuse common CLI flags in common to make code DRY
* Always add tests when you add new features or update existing tests if needed
* Always try to identify reusable code, and put it on a shared class or in common.py
* Ensure the code is DRY
* Ensure the app is 12foctor app
    * Especially on the top level configuration settings.
* If there is any configuration:
    * Ensure the vocabulary is clear or not confusing
* Avoid any confusing terms or vocabulary



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



