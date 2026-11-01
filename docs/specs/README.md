# Specs

Working notes for this repository. The public site is `docs/content/` and is not numbered.

## Where to write

- A command, flag, error, walk, match, kind file, or `data` rule: [behavior.md](behavior.md).
- Types, cast, models, source labels, `kind_schema`, or packaged defaults: [architecture.md](architecture.md). Cite it as architecture 1.7. Those numbers are not product steps.
- A profile or kind file a user would paste: [examples.md](examples.md). No section numbers. A comment may cite a product step. The rule itself stays in behavior or architecture.
- How any mrjk app is built: [../RULES.md](../RULES.md). Cite it as rules 2.1.
- An idea that is not accepted: [drafts/](drafts/). It does not move into behavior until it is accepted. `2.3.3` is [drafts/file-metadata.md](drafts/file-metadata.md).
- A decision that is accepted and blocked on another step stays in drafts until that step exists. `record_key` is [drafts/record-key.md](drafts/record-key.md). It waits on file metadata and schema version 2.
- `docs/v1/` is the old barbu accounting spec. Do not add to it.
- `docs/DRAFT.md` is empty. Do not use it.

## Numbers

Product steps live in behavior.md only.

- `1` App initialization
- `2` Profile initialization
- `2.1` Scan files (`2.1.1` command, `2.1.2` walk)
- `2.2` Matching (`2.2.1` commands, `2.2.2` algorithm)
- `2.3` Vars (`2.3.1` resolve, `2.3.2` kind files)
- `2.3.3` is reserved for the parked metadata draft
- `3` Data (`3.1` shared rules, `3.2` feed, `3.3` prune, `3.4` show)
- `4` Record (`4.1` commands, `4.2` link, `4.3` writes)

The next command stage is `5`. Do not use `5` for the engine.

At most three dotted numbers. A section that is already `X.Y.Z` keeps word headings under it. Do not renumber a section to make room. Add the next free id.

architecture.md starts again at `1`. RULES.md starts again at `1`.

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

When a decision is accepted, write it in the file named above before implementation.
