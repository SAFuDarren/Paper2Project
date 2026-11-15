# Updating the skill without losing customizations

Users extend Paper2Project: embedding or RAG adapters, database or knowledge-store connections, custom checkers, locale packs, rules of their own. An update fixes and improves the package. It never removes, resets or reshapes those customizations. The agent follows this page; the user does not need to.

## Where customizations live

| Customization | Its home | What an update does |
|---|---|---|
| Extension settings (embedding, rag, agent, knowledge_store, extra slots such as `database`) and any extra profile keys | `.paper2project.json` in the workspace | Kept verbatim. Commands read and rewrite the profile without dropping or resetting them. The core never activates them. |
| Adapter code, scripts, private templates | `local/` in the skill folder, or the user's own repository | Never touched (the package ships nothing there). |
| Edits to a shipped package file | That file | Kept; the new release is written beside it as `<file>.new` for review. |
| Workspace rules of the user's own | `AGENTS.md` outside the `<!-- p2p:rules -->` markers | Kept; only the marked block is refreshed. |
| Notes, hand-written index text, bookmarks | Workspace and `.obsidian` | Kept; only `<!-- p2p:index -->` lists and the `Paper2Project` bookmark group are regenerated. |

Credentials never go in the profile. Store a reference such as `"api_key_env": "MY_PROVIDER_KEY"` and read the secret in the adapter; the profile loader refuses credential-like keys.

## Updating an installed skill

Never delete the installed folder or copy a new download over it. Download the new release to a separate folder, then run its updater against the installed copy:

```sh
python <new-download>/scripts/update_skill.py --target <installed-skill>
python <new-download>/scripts/update_skill.py --target <installed-skill> --apply
```

`MANIFEST.json` records every file the package has shipped with the hash of each released version. A file that still matches a shipped version is replaced; a file that matches none was edited locally, so it is kept and the new version is written as `<file>.new`; files the package never shipped are not read or changed. Files removed upstream are deleted only if unmodified. Report the `kept_custom` list to the user and merge each `.new` file with them; do not resolve it by overwriting their version.

Then bring each workspace up to date:

```sh
python scripts/p2p.py upgrade --root /chosen/Academic
python scripts/p2p.py upgrade --root /chosen/Academic --apply
```

`upgrade` normalizes the profile (new defaults added, every existing key and extension setting kept, previous file backed up in `.paper2project-history/`), refreshes the marked rules block in `AGENTS.md` (a never-edited old copy is replaced; an edited copy without markers is kept and the current block is appended), then refreshes the bookmarks and index lists. Finish with `check` and report the `navigation` block.

## Rules for every change to the skill

A bug fix changes the faulty behavior only. These contracts hold across releases, and the tests in `tests/test_updates.py` enforce them:

1. **Profile compatibility.** New keys are optional with defaults. Existing keys are never removed, renamed or reinterpreted without a migration in `upgrade` that carries their values over. Unknown keys and every extension slot are preserved verbatim.
2. **Extensions stay the user's.** The core neither activates nor rewrites extension configuration; onboarding and preference signals cannot switch a slot on. Validation is limited to shape and the credential guard.
3. **Commands and outputs.** Existing commands, flags and JSON result keys keep their meaning; additions are new flags or keys. `export` keeps `schema_version` 1 until a versioned successor exists beside it.
4. **Registers keep their schema.** `.maintenance/pdf_attachments.json`, `relations.json` and the derived `retrieval.sqlite` keep `schema_version` 1 formats; a change ships a reader for the old format.
5. **Marked regions only.** Generated content lives between `p2p:` markers (`index`, `rules`, `pdf`, `evidence`, `relation`) or in the `Paper2Project` bookmark group. The marker formats are stable. Text outside them, notes, user bookmarks and `.maintenance` records are never rewritten.
6. **Ship a manifest.** Every release runs `python scripts/package_check.py --write-manifest`; CI (`--release`) fails if the manifest is stale. Never edit or drop history entries: the updater recognizes old versions by them.
7. **Prove it.** A change that touches profile handling, generated regions or the updater adds or keeps a test with a customized workspace (enabled extensions, extra slots, extra profile keys, edited rules, local files) showing they survive.
