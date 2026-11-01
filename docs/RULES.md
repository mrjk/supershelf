# Rules

These numbers are rules, not product steps. Where a supershelf decision is written: [specs/README.md](specs/README.md).

## 1 Project

### 1.1 Naming and classifiers

Ideally, a project should respect this name pattern:
* If it's an app:
    * NAME_OF_THE_APP or CODENAME
    * For side repos, or project, either use component naming convention, or ecosystem:
        * NAME_OF_THE_APP-COMPONENENT, where component can be -cli, -web, -server, -api, -doc etc ...
* If it's a component:
    * DOMAIN-NAME, where domain is language, or a product (python, ruby, go, rust ...) or (ansible, terraform, mise/asdf, etc ...)
        


Classifiers, a project can be:
* MAINTAINED: Support is done, security is done. After 2 years of non commit, fallback to UNMAINTAINED
* UNMAINTENED: mention since what date the project is not maintained
* DEPRECATED, replaced by something else that need to be mentionned
* ABANDONNED: when a project was abandonned before it does not make sense to work on it anymore, mention the reason, no replacements or give alternative project

Tags:
* GROUP: Name of the main app, or the parent application (project name, or component DOMAIN)
* COMPONENT: Name of the component, or "app"
* COMPONENT_TYPE: Type of the component, like ansible-collection or ansible-role


List of known app-products (to be filled by the time):
* terraform:
    * terraform-module-
* ansible:
    * ansible-role-
    * ansible-collection-
* mise/asdf/...:
    * mise-
* python|shell|go|rust|:
    * python- (for python lib)
    * CODENAME



### 1.2 License, language, and examples

* Ensure a GPL license is present in project, unless another license is mentionned
* Each new code changes should come with documentation and tests. Codes changes should be small and reviewable.
* Do not use personal or private data in examples, documentations and test. Always use agnostic or fake names (ie: intead of using a name of real bank instution use Bank2000 ). As well, always use english names, no french, spanish, german or whatsoever. English should be the main language of the project.
* Assume any project may end up public, excepted personal projects.
    * I dont want to do cleanup, i want this to be clean from day one.

### 1.3 mise and task

* We use mise, aka mise-en-place.
    * Ensure a config is present
    * it must provide all the development toolkit to be able to run the whole project. Language domain dependency take the relay (pyproject.toml for python, etc ...)

* We use task and taskfile:
    * GEneral:
        * Good and consistent naming matters. A command has one name. The task, the workflow, and the job use that name, with the same case and separators.
        * CWD is where the taskfile is
        * Ensure it uses a common .env file
        * Do not hardcode versions or repo owner, use env vars.
    * Simple project:
        * Ensure there is one taskfile at the root that allow to easily work with project. Split commands
    * More complex project:
        * Include taskfiles in root taskfile
        * Only show at the top level commands general commands, if the user want to run specific tests/docsumentation commands, it changes dir to it to have more focused command
    * CI/CD commands:
        * Provide one task, `ci`, that runs the verification pipeline. A CI/CD builder runs that same task. Local and remote stay aligned. It can provide hidden shortcuts.
        * `ci` only calls other tasks. Leaf tasks do the work.
        * A workflow installs mise, then runs `mise x -- task <name>`. It does not inline pytest, uv, or the site generator.

### 1.4 Documentation, containers, tests, CI, and examples


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
    * Task provides a way to run the whole verification pipeline locally. `ci` only calls other tasks. Leaf tasks do the work.
    * Local CI and remote CI stay aligned. Each workflow job installs mise, then runs `mise x -- task <name>`.
    * Use env vars for deployment settings. Do not hardcode the repository owner.
    * The job names below are examples, not a list every project must implement. Add a workflow only for a task the project already has. Do not add lint, a package build, a version bump, or a registry publish just to match an example.
        * Verification examples: `ci`, and when the task exists: lint, build, test, docs lint, docs build.
        * Deploy examples: a top release workflow only when several publish tasks exist; publish documentation; registry or GitHub release publishes when those tasks exist.
    * Every workflow is runnable from the Actions tab (`workflow_dispatch`), so the user can choose the branch.
    * The name in the Actions tab is that task name. `ci` is `ci`. `docs:build` is `docs:build`. Do not replace it with a title.
    * Do not run both the pipeline workflow and the single-task workflows on the same automatic event. The single-task workflows are dispatch only.
    * Branches:
        * `main` is the stable line. `dev` is the unstable line. A branch named `dev-*` has the same behavior as `dev`.
        * Verification runs on a pull request, and on a push to `main`, `dev`, or `dev-*`. A push to any other branch does not. The pull request covers that branch.
    * Tags:
        * A stable tag is cut only from `main`. An unstable tag (a pre-release such as alpha, beta, rc, or the same idea) is cut only from `dev` or `dev-*`. No other ref is tagged.
    * Versions:
        * Semantic versioning is preferred.
        * `1.0.0` is the first version that means the product is stable and ready for production. A version below that is not a production declaration.
        * A tag with no pre-release identifier is a stable tag. A tag with a pre-release identifier is an unstable tag.
        * When semantic versioning does not fit, use a calendar version: `YY.MM`, then optional day, hour, minute, and a sequence. The shape is `YY.MM[.DD[.HH[.MM]]][.SEQ]`. Each extra field requires the fields before it, except `SEQ`, which may close any of those forms.
        * The separator is a dot by default. A use case may instead use `-`, `_`, or no separator.
    * If the project publishes a documentation site, publish it after verification succeeds on a push to `main`. Do not publish from a pull request, or from `dev` or `dev-*`. A manual dispatch publishes the branch selected in that dialog.

* examples:
    * This should provide code examples to try for the user
    * Ensure there is no personal data examples in examples

## 2 Python

### 2.1 Modules and classes

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

### 2.2 CLI, tests, DRY, and configuration vocabulary

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

### 2.3 Exceptions

* The program must provides different kind of exceptions
    * There is ONE parent exception, and many children exceptions, that can be class nested/inherited
    * EAch exceptions should have a specific error message, that allow customization via vars. It's also possible to override exception error message.
    * Each exception should return am exit code, with a way to add a custom message or parameters.
    * Each exception should provide a tips field, that give user instructions to solve the issue. This is optional.

### 2.4 Logging

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

## 3 App standard

* Structured like git-like commands, with subcommands
* must support log levels and dry run options
* COmmon options flags must be setup at the top, specific are attached to subcommand only. Use CLI flags classes+inheritabnce if ncecessary to be able to reuse common flags.
* Configuration order precedence (12 factors apps):
    * CLI
    * Env vars
    * YAML Config
    * Defaults
* For the configuration file format, i want to be able to generate a schema of it, and also raise errors when the user make configuration mistakes.

## 4 Documentation site

* all lives in docs/
* Use a taskfile: to serve, build, release
    * Add extract tasks when some custom document import/generation scripts
* docs lives in docs/content
* use yaml config
* Discover sections automatically. Do not list pages in `mkdocs.yml`.
* The page menu follows the reading path. Write that order in the section `.nav.yml`. Filename order is not the reading path. Put a new page on the path where the reader needs it.
    * Guides follow the next-page links, starting at list files.
    * Concepts follow the pipeline on the concepts page: profiles, paths, inputs, matching, variables, kind files. Then template commands, modules, errors, and limits.
    * Reference follows command line, configuration, templates, variable names, kind file, then architecture.
    * About follows development, then license.
* Documentation should be LOW maintenance, avoid recap, summaries, links to other pages that can change. Try to stay minimalist in way to facilitate maintenance.
* When using code, ensure the language tag is set, and eventually the corresponding filename. Also, if the config support many syntax format, show all formats in a tab.
* Do not use pages that are just links to other pages, wihtout content. There is the menu already for that.
* If there are need to do diagrams to explain things or concepts, use some when it brings value to the reader. Use correct diagram type according what you want to illustrate
