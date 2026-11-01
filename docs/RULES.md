# Rules

These numbers are rules, not product steps. Where a supershelf decision is written: [specs/README.md](specs/README.md).

## 1 Project

### 1.1 Naming and classifiers


**Classifiers.**

A project has one of these classifiers:

* `PROJECT_NAME`: name of the component or app.
* `PROJECT_TYPE`: type of the component. See Project types classifiers.
* `PROJECT_STATUS`: See project status classifiers. default is PROTOTYPE
* `PROJECT_LANGUAGE`: type of the component. Examples: `python`, `rust`, `go`. (use github lang tags in https://github.com/github-linguist/linguist/blob/main/lib/linguist/languages.yml)
* `PROJECT_TAGS`: custom tags, like in github tags
* `PROJECT_VISIBILITY`: Choose one of: PUBLIC|PRIVATE(default)|SECRET


**Tags.**

Project types classifiers:
* `app|codename`: Generic app, no informations, or public product
* `docs`: Generic documentation, no informations
* `python`: python library
* `go`: go library
* `shell`: shell library
* `ansible-project`: Ansible domain repository 
* `ansible-inventory`: Ansible inventory collection 
* `ansible-collection`: Ansible galaxy collection 
* `ansible-role`: Ansible galaxy role
* `mise-app`: mise app
* `asdf-app`: asdf app
* `terraform-project`: Terraform domain repository 
* `terraform-module`: Terraform module

Project status classifiers:
* `PROTOTYPE`: Default status of a project.
* `MAINTAINED`: support is handled, and security work is handled. After 2 years with no commit, fall back to `UNMAINTAINED`.
* `UNMAINTAINED`: state the date since which the project is not maintained.
* `DEPRECATED`: the project is replaced by something else. Name the replacement.
* `ABANDONED`: the project was abandoned before further work made sense. State the reason. Give no replacement, or name an alternative project.

**Naming.**

Use this naming pattern on the project, to help user find the perfect name.

* An app is `PROJECT_NAME` name or a codename.
* A side repo or side project uses one of these:
    * `PROJECT_NAME-SUFFIX`, where SUFFIX can be `-cli`, `-web`, `-server`, `-api`, `-doc`, and so on.
* A component is `PROJECT_TYPE-PROJECT_NAME`. The domain is a language (`python`, `ruby`, `go`, `rust`, and so on) or a product (`ansible`, `terraform`, `mise`/`asdf`, and so on).




### 1.2 License, language, and examples

* Include a GPL license, unless another license is stated.
* Each code change comes with documentation and tests. Keep each change small enough to review.
* Do not put personal or private data in examples, documentation, or tests. Use agnostic or fake names. For example, use `Bank2000` instead of the name of a real bank. Use English names. Do not use French, Spanish, German, or another language for those names. English is the main language of the project.
* Assume any project may become public, except a personal project.
* Write it clean from day one. Do not rely on a later cleanup.
* `examples/` holds code a user can try. That code follows the same rule: no personal data.

### 1.3 Repository layout

Most of these paths are optional. If a path exists, put it here. What happens inside `docs/`, `scripts/`, `tests/`, and the image directory is defined in the sections below.

```
Project root:
  README.md: what the project does
  LICENSE.md: recommended license
  CODE_OF_CONDUCT.md: optional code of conduct
  CHANGELOG.md: optional changelog, managed automatically

Directories:
  scripts/: scripts for the project lifecycle, not application code
  docs/: documentation
  tests/: tests
  examples/: code a user can try
  images/: default directory for Docker, LXC, and OCI images

Root files, kept minimal, and sometimes required:
  .env: generic env file, read by Docker, Taskfile and mise
  .dockerignore
  TODO: feed with other known files
```

`images/` is the default name. `docker/` and `container/` are accepted names for that same directory.

Code layout depends on the context, the language, and the size of the project. The trees below are examples. They are not part of the repository tree above.

* Python:
    * `src/PKG_NAME/`
    * `PKG_NAME/`: old style, still valid
* Shell:
    * `bin/`: ready-to-use binaries, no compilation
    * `lib/`: bash library
* TODO: feed with other language patterns

### 1.4 mise and task

**mise.**

Use mise (mise-en-place).

* A mise config is present.
    * We use it to determine required list of tools, with always a version (never latest)
    * We use it to override environment vars 
    * We only use mise on those basic tasks, configuring more stuff with mise is out of scope
* It provides the whole development toolkit needed to run the project. Language dependencies take over from there. Example: `pyproject.toml` for Python.
* use mise.local.toml file to store local override env vars. Mention it in .gitignore.

**task.**

Use task and a taskfile.

* Naming stays consistent. A command has one name. The task, the workflow, and the job use that name, with the same case and separators.
* The working directory is the directory that holds the taskfile.
* Use a common `.env` file.
* Do not hardcode versions or the repository owner. Use environment variables.

Simple project:

* One taskfile at the root, enough to work on the project easily. Split commands.

More complex project:

* Include other taskfiles from the root taskfile.
* Show only general commands at the top level. To run a specific test or documentation command, change to that directory and use the focused commands there.

CI/CD commands:

* Provide one task, `ci`, that runs the verification pipeline. A CI/CD builder runs that same task. Local and remote stay aligned. The taskfile may provide hidden shortcuts.
* `ci` only calls other tasks. Leaf tasks do the work.
* A workflow installs mise, then runs `mise x -- task <name>`. It does not inline pytest, uv, or the site generator.

Workflow words. This is the general workflow. Not every step is required.

* `fix`: auto-fix format, lint, and so on
* `lint`: check that lint rules pass
* `build`: check that the build works
* `test`: test the build
* `docs`: build the docs
* `security`: the build passes security tests, and the production result is tested, before a release
* `release`: prepare a release
* `publish`: publish the release

Stack words. These are examples. Add more later.

* `images`, `docker`, `vm`: build Docker images and VM appliances
* `terraform`, `ansible`: run CD with Ansible or Terraform

CI/CD words:

* `ci`: run CI
    * `ci-short`: run on every commit
    * `ci-full`: the full CI pipeline
* `cd`: publish

Publicly exposed CI/CD jobs. Use these names when the project has that job:

* `ci-short`
* `ci-full`
* `release`
* `publish`
* `publish-docs`

Taskfiles stay minimal and readable. Keep them DRY. Use vars and anchors when that helps.

Project logic that is not the taskfile lives in `scripts/`, ideally in bash strict or in shell. That directory is the placeholder for all project scripts, so the same script can be reused from more than one place.

### 1.5 Documentation

* Documentation lives under `docs/`. Use a taskfile there to build, run, release, and run pre-scripts.
* Prefer a static documentation generator that fits the project language, or a static binary provided by mise.
* A license file is always present.
* A code of conduct is present for a project that is not personal.
* Keep only the parts that apply.

Top `README.md`:

* A simple, professional README. It says what the program does, with some examples.

If the project has a documentation site, the site lives under `docs/`. Use this structure:

* 0. Home
    * Close to `README.md`. Inject the README into the page instead of copying it.
* 1. Quickstart
    * Roughly the same content as the top README.
    * Install the program, and check it with `--version`.
    * Show a very simple use case.
    * Show the basic commands, and say where to look next.
* 2. Usage and Guides
    * Step by step. The path is progressive, and it represents user cases.
    * Take specific use cases and document them.
* 3. Documentation
    * Explain the app concepts and train the user on them. No prior learning curve is required.
    * Technical depth is allowed.
    * FAQ, if needed.
* 4. Reference (mostly generated)
    * CLI `--help` output
    * Configuration schema and reference
    * Generated documentation for the API
    * Architectural design record, and the architecture document or references
* 5. About
    * How to set up the development environment, with mise and tasks
    * How to build, release, and debug, with tasks
    * License and code of conduct
    * Information and project history

### 1.6 Containers

* Container files live in `images/` by default. `docker/` and `container/` are accepted names for that directory. See 1.3.
* Provide Docker support. Other support, such as LXC, may be added.
* A production deployment can be run from a `docker-compose.yml` file.
* Provide `docker-compose.dev.yml` as a live development platform: the source is mounted in a volume, so edits apply live when the language allows it.
* Reuse one Dockerfile through build stages. Derive the dev and test builds from the production build, and extend them.
* The image does not require a root user or root permissions.
* Container should have standard OCI image tags.

### 1.7 Tests, CI, and git

**Tests.**

* When tests are long, or the scenarios are more complex, use a taskfile under `tests/`.

**CI/CD.**

* Task runs the whole verification pipeline locally. `ci` only calls other tasks. Leaf tasks do the work.
* Local CI and remote CI stay aligned. Each workflow job installs mise, then runs `mise x -- task <name>`.
* Use environment variables for deployment settings. Do not hardcode the repository owner.
* The job names below are examples, not a list every project must implement. Add a workflow only for a task the project already has. Do not add lint, a package build, a version bump, or a registry publish just to match an example.
    * Verification examples: `ci`, and when the task exists: lint, build, test, docs lint, docs build.
    * Deploy examples: a top release workflow only when several publish tasks exist; publish documentation; registry or GitHub release publishes when those tasks exist.
* Every workflow is runnable from the Actions tab (`workflow_dispatch`), so the user can choose the branch.
* The name in the Actions tab is that task name. `ci` is `ci`. `docs:build` is `docs:build`. Do not replace it with a title.
* Do not run both the pipeline workflow and the single-task workflows on the same automatic event. The single-task workflows are dispatch only.

**Git.**

Branches:

* `main` is the stable line. `dev` is the unstable line. A branch named `dev-*` has the same behavior as `dev`.
* Verification runs on a pull request, and on a push to `main`, `dev`, or `dev-*`. A push to any other branch does not. The pull request covers that branch.

Tags:

* A stable tag is cut only from `main`. An unstable tag (a pre-release such as alpha, beta, rc, or the same idea) is cut only from `dev` or `dev-*`. No other ref is tagged.

Versions:

* Semantic versioning is preferred.
* `1.0.0` is the first version that means the product is stable and ready for production. A version below that is not a production declaration.
* A tag with no pre-release identifier is a stable tag. A tag with a pre-release identifier is an unstable tag.
* When semantic versioning does not fit, use a calendar version: `YY.MM`, then optional day, hour, minute, and a sequence. The shape is `YY.MM[.DD[.HH[.MM]]][.SEQ]`. Each extra field requires the fields before it, except `SEQ`, which may close any of those forms.
* The separator is a dot by default. A use case may instead use `-`, `_`, or no separator.

If the project publishes a documentation site, publish it after verification succeeds on a push to `main`. Do not publish from a pull request, or from `dev` or `dev-*`. A manual dispatch publishes the branch selected in that dialog.

## 2 Python

### 2.1 Modules and classes

* Use modular code.
    * Organize code into specific files and directories.
    * Keep a folder easy to copy into another project, with its logic self-contained. Leave shared pieces out. Keep the domain logic together. Other dependencies depend on the implementation.
    * When the project lets the user extend application functionality by loading custom code, define the API and document it.
* Always use OOP and classes: inheritance, composition, and so on. This is not optional.
    * Use methods and private methods when the logic belongs to one class or object.
    * Use a parent class when several classes share the same behavior.
    * In `src/`, a module-level function is allowed as `main()`, in `common.py`, or in the module that owns the behavior when more than one caller shares it. Put it beside that type when there is one.
    * `common.py` is for a helper that has no single owner.
    * New behavior that one class owns is a method on that class.
    * Do not add a helper function because the file already has some.
    * Matching the existing style, and keeping the diff small, does not override this.
    * "When it makes sense" is not an exception for private helpers.
    * If you touch a helper that belongs to one class, move it onto the class in the same change.

### 2.2 CLI, tests, DRY, and configuration vocabulary

* Use `github/mrjk/clak` as the main CLI library.
    * Use the standard CLI output and format features, especially the table output.
    * Reuse common CLI flags from `common`, so the code stays DRY.
* Add tests when you add a feature. Update existing tests when a change requires it.
* Identify reusable code and put it on a shared class, in the module that owns the behavior, or in `common.py` when it has no single owner.
* Keep the code DRY.
* Make the app a 12-factor app, especially the top-level configuration settings.
* When there is configuration, keep the vocabulary clear.
* Avoid confusing terms.

### 2.3 Exceptions

* The program provides different kinds of exceptions.
    * There is one parent exception, and many child exceptions. A child may be nested or inherited.
    * Each exception has a specific error message. The message can be customized with variables, and it can be overridden.
    * Each exception returns an exit code, with a way to add a custom message or parameters.
    * Each exception provides a `tips` field that tells the user how to solve the issue. The field is optional.

### 2.4 Logging

* Logging verbosity and output:
    * For stdout, use clak views. If that does not fit, print.
    * Levels are progressive. The first level shows little output. Higher levels show more.
        * `NOTICE`, when it exists, is always shown, with no verbosity flag.
        * `INFO`: the app
        * `DEBUG`: the app
        * Further intermediate app debugging levels.
        * The last two levels:
            * show info from all libraries
            * show debug from all libraries

## 3 App standard

* Structure commands like git, with subcommands.
* Support log levels and a dry-run option.
* Set common option flags at the top. Attach flags that are specific to one subcommand to that subcommand only. Use CLI flag classes and inheritance when that is needed to reuse the common flags.
* Configuration precedence for a 12-factor app:
    * CLI
    * Environment variables
    * YAML config
    * Defaults
* The configuration format has a generated schema. Raise an error when the user makes a configuration mistake.

## 4 Documentation site

* The site lives in `docs/`.
* Use a taskfile to serve, build, and release.
    * Add extract tasks when custom document import or generation scripts are needed.
* Pages live in `docs/content`.
* Use a YAML config.
* Discover sections automatically. Do not list pages in `mkdocs.yml`.
* The page menu follows the reading path. Write that order in the section `.nav.yml`. Filename order is not the reading path. Put a new page on the path where the reader needs it.
* Example for this app:
    * Guides follow the next-page links, starting at list files.
    * Concepts follow the pipeline on the concepts page: profiles, paths, inputs, matching, variables, kind files. Then template commands, modules, errors, and limits.
    * Reference follows command line, configuration, templates, variable names, kind file, then architecture.
    * About follows development, then license.
* Keep documentation low-maintenance. Avoid recaps, summaries, and links to other pages that can change. Stay minimal so the pages stay easy to maintain.
* When showing code, set the language tag, and set the filename when there is one. If the config supports several syntax formats, show all of them, each in a tab.
* Do not use a page that is only links to other pages, with no content of its own. The menu already does that.
* Use a diagram when it helps the reader. Choose the diagram type that matches what you are illustrating.
