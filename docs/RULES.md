
# General mrjk rules

## Application project
* Ensure a GPL license is present in project, unless another license is mentionned
* Each new code changes should come with documentation and tests. Codes changes should be small and reviewable.
* Do not use personal or private data in examples, documentations and test. Always use agnostic or fake names (ie: intead of using a name of real bank instution use Bank2000 ). As well, always use english names, no french, spanish, german or whatsoever. English should be the main language of the project.
* Assume any project may end up public, excepted personal projects.
    * I dont want to do cleanup, i want this to be clean from day one.


### Generic tooling
* We use mise, aka mise-en-place. 
    * Ensure a config is present
    * it must provide all the development toolkit to be able to run the whole project. Language domain dependency take the relay (pyproject.toml for python, etc ...)

* We use task and taskfile:
    * GEneral:
        * Ensure command naming pattern make sense
        * CWD is where the taskfile is
        * Ensure it uses a common .env file
        * Do not hardcode versions or repo owner, use env vars.
    * Simple project:
        * Ensure there is one taskfile at the root that allow to easily work with project. Split commands
    * More complex project:
        * Include taskfiles in root taskfile
        * Only show at the top level commands general commands, if the user want to run specific tests/docsumentation commands, it changes dir to it to have more focused command
    * CI/CD commands:
        * It should provide a single command that a CI/CD builder can run. We want the same behavior local and remote


### Side topics

* Documentation:
    * Lives under docs/. Use a sub taskfile to allow to build, run, release, run pre scripts ... etc ..
    * Usually we will want to use a static documentation generator, use one that fit to the same language, or use static binaries provided by mise
    * Ensure also:
        * There is always a license file
        * Ensure a code of conduct is present for non personal projects
    * Documentation should be structured this way, keep only what is relevent:
        * top README.md:
            * Simple and professional README, that shows what the program do, some examples etc ..
        * If there is a documentation site
            * It lives in docs/ subdir
            * Structure:
                0. Home
                    - Quite similar to README.md, ideally inject the readme in it (instead of making a copy)
                1. Quickstart
                    - Have roughly the same content as top README.md
                    - install the program, and test with --version
                    - Show a very simple usecase
                    - show the very basic commands, give user instruction where to look next
                2. Usage and Guides
                    - Explain how to handle step by step, it must be a progressive learning, it must represent suer cases
                    - Grab specific use cases, and document them
                3. Documentation
                    - Explain and train user about all apps concepts. No learning curve needed
                    - You can go deep technical
                    - FAQ (if needed)
                4. Reference (mostly generated)
                    - CLI --help output
                    - configuration schema/reference
                    - code generated documentation for API
                    - Architectural design record, architecture document/references
                5. About
                    - how to setup developement environment (with mise and tasks)
                    - how to build, release, debug (with tasks)
                    - license, code of conduct
                    - informations, project history
    * docs/PERFECT_CONFIG.yml is the use-case catalog. It plays the role of a USECASES document: config a user would write. Keep the file name.
    * docs/ARCHITECTURE.md is behind the scenes: models, pipelines, cast rules, and edge cases. It is a different file from docs/content/reference/architecture.md.
    

* Container/OCI:
    * Lives in docker (or container) folder
    * Usually we will alway want a docker support, and eventually other support (LXC, or whatever)
    * We always want to be able to run a production deployment with a docker-compose.yml file
    * We will also want a docker-compose.dev.yml that provided a live development plateform (understand code source is exposed in a volume, and allow live changes when language allow it)
    * Try to ruse dockerfile content, with staged build, dev/test build should be derivated and extended from production build.
    * Dont make image that require root user/persmissions

* Tests:
    * If there are long tests or more complex tests scenarios, use a specific taskfile under tests/.

* CI/CD:
    * Task should provides a way to run the whole pipeline locally.
    * Local CI == remote CI, it should be aligned.
    * Use env vars
    * CI/CD tasks should actually only call other tasks.

* examples:
    * This should provide code examples to try for the user
    * Ensure there is no personal data examples in examples


# Python Coding rules


## Main rules
* Use modular code:
    * Organise code in specific files and dir
        * It should somewhat always easy to copy a folder into another project and have the logic self contained (minus all common things, just keep the domain logic together, other dependencies are implementations dependenant)
    * Sometimes the project will allow the user to extend application functionnalities by allowing custom code to be loaded
        * On this case, ensure the API is defined and documented
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
* The program must provides different kind of exceptions
    * There is ONE parent exception, and many children exceptions, that can be class nested/inherited
    * EAch exceptions should have a specific error message, that allow customization via vars. It's also possible to override exception error message.
    * Each exception should return am exit code, with a way to add a custom message or parameters.
    * Each exception should provide a tips field, that give user instructions to solve the issue. This is optional.
* Logging verbosity and output:
    * For stdout, always try to use clak views
        * If that does not fit, you can print
    * For logging levels: It must be progressive, first level show few outputs, more levels show more output
        * NOTICE (if exists) should always been shown, wihtout verbosity
        * INFO app
        * DEBUG app
        * More intermediate app debugging levels ...
        * 2 last ones
            * show info from all libs
            * show debug from all libs



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

## Mrjk Python App standard

* Structured like git-like commands, with subcommands
* must support log levels and dry run options
* COmmon options flags must be setup at the top, specific are attached to subcommand only. Use CLI flags classes+inheritabnce if ncecessary to be able to reuse common flags.
* Configuration order precedence (12 factors apps):
    * CLI
    * Env vars
    * YAML Config
    * Defaults
* For the configuration file format, i want to be able to generate a schema of it, and also raise errors when the user make configuration mistakes.


## Documentation standard with zensical/mkdocs

* all lives in docs/
* Use a taskfile: to serve, build, release
    * Add extract tasks when some custom document import/generation scripts
* docs lives in docs/content
* use yaml config
* Make the documentation TOC automatic, i dont want to edit config to change order of pages, or even keep a link to all pages. I want auto discovery.
* Documentation should be LOW maintenance, avoid recap, summaries, links to other pages that can change. Try to stay minimalist in way to facilitate maintenance.
* When using code, ensure the language tag is set, and eventually the corresponding filename. Also, if the config support many syntax format, show all formats in a tab.
* Do not use pages that are just links to other pages, wihtout content. There is the menu already for that.
* If there are need to do diagrams to explain things or concepts, use some when it brings value to the reader. Use correct diagram type according what you want to illustrate
