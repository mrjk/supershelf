# Specs

Working notes for this repository. The public site is `docs/content/` and is not numbered.

## Lookup

Read this file, then open the one section file for that id. Do not open the other section files.

The cite id is the filename prefix. `behavior 2.3.2` is [behavior/2.3.2-kind-files.md](behavior/2.3.2-kind-files.md). `architecture 1.7` is inside [architecture/1-types.md](architecture/1-types.md). `architecture 3.5` is inside [architecture/3-database.md](architecture/3-database.md).

`scan vars` resolves variables in 2.3.1, may read or append a kind file in 2.3.2, and may read file metadata in 2.3.3.

## Where to write

- A command, flag, error, walk, or match rule: the behavior file for that step, listed below.
- Types, cast, models, source labels, or `kind_schema`: [architecture/1-types.md](architecture/1-types.md). Cite it as architecture 1.7. Those numbers are not product steps.
- Packaged defaults: [architecture/2-defaults.md](architecture/2-defaults.md).
- The profile database: [architecture/3-database.md](architecture/3-database.md).
- Output drivers: [architecture/4-drivers.md](architecture/4-drivers.md).
- A profile or kind file a user would paste: [examples.md](examples.md). No section numbers. A comment may cite a product step. The rule itself stays in behavior or architecture.
- How any mrjk app is built: [../RULES.md](../RULES.md). Cite it as rules 2.1.
- An idea that is not accepted: [drafts/](drafts/). It does not move into behavior until it is accepted. `2.3.3` file metadata is in [behavior/2.3.3-file-metadata.md](behavior/2.3.3-file-metadata.md). The table is [architecture/3-database.md](architecture/3-database.md). Later builtins stay in [drafts/file-metadata.md](drafts/file-metadata.md).
- A decision that is accepted and blocked on another step stays in drafts until that step exists. `record_key` is [drafts/record-key.md](drafts/record-key.md). File metadata shipped as schema 2, so `record_key` takes the next schema version.
- `docs/v1/` is the old barbu accounting spec. Do not add to it.
- `docs/DRAFT.md` is empty. Do not use it.
- [behavior.md](behavior.md) and [architecture.md](architecture.md) are stubs. Do not add rules there.

## Numbers

Product steps live in `behavior/` only. `2` is profile load only. Scan, match, and vars are `2.1`, `2.2`, and `2.3`.

- `1` App initialization: [behavior/1-app.md](behavior/1-app.md)
- `2` Profile initialization: [behavior/2-profile.md](behavior/2-profile.md)
- `2.1` Scan files (`2.1.1` command, `2.1.2` walk): [behavior/2.1-scan.md](behavior/2.1-scan.md)
- `2.2` Matching (`2.2.1` commands, `2.2.2` algorithm): [behavior/2.2-match.md](behavior/2.2-match.md)
- `2.3` Vars. There is no `2.3` file.
  - `2.3.1` resolve: [behavior/2.3.1-resolve.md](behavior/2.3.1-resolve.md)
  - `2.3.2` kind files: [behavior/2.3.2-kind-files.md](behavior/2.3.2-kind-files.md)
  - `2.3.3` file metadata: [behavior/2.3.3-file-metadata.md](behavior/2.3.3-file-metadata.md)
- `3` Data (`3.1` shared rules, `3.2` feed, `3.3` prune, `3.4` show): [behavior/3-data.md](behavior/3-data.md)
- `4` Record (`4.1` commands, `4.2` link, `4.3` writes): [behavior/4-record.md](behavior/4-record.md)
- `5` Output (`5.1` commands, `5.2` selection, `5.3` file driver): [behavior/5-output.md](behavior/5-output.md)

The next command stage is `6`. Do not use `6` for the engine.

At most three dotted numbers. A section that is already `X.Y.Z` keeps word headings under it. Do not renumber a section to make room. Add the next free id.

Architecture starts again at `1`. `1.1` through `1.9` stay in one file. `3.1` through `3.5` stay in one file. RULES.md starts again at `1`.

- `1` Types and values (`1.7` cast, `1.9` kind_schema): [architecture/1-types.md](architecture/1-types.md)
- `2` Packaged defaults: [architecture/2-defaults.md](architecture/2-defaults.md)
- `3` Profile database: [architecture/3-database.md](architecture/3-database.md)
- `4` Output drivers: [architecture/4-drivers.md](architecture/4-drivers.md)

## Workflow

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
    - When something asked is too complicated or to complex, or it involve a lot of code, external plugins or so, mention you need to do it FIRST. Try to provide a solution that it simpler, with eventual drawbacks, before trying to over engeener things.

- Note: When the project is in POC phase, alternate between specs phases and implementation+test phase. Documentation and other steps can be skipped, in way to reduce prompt context size. So at some points, the developper will ask to "resync" the docs, and so on ...

When a decision is accepted, write it in the file named above before implementation.
