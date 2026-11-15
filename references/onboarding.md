# Context-aware setup and preference changes

The first invocation activates onboarding; a download does not run anything. Read the current request, applicable rules, existing profile and selected project context. Follow an existing management/task entry. Inspect only the chosen scope.

## Let the host LLM resolve intent

Use relevant host-provided or explicitly authorized memory when available. Never claim access to a memory API that the host did not provide; never scan a home directory or persist a raw conversation. With no memory, current context and saved settings are sufficient.

Priority is current explicit choice > saved workspace > supplied memory > conversation inference > fallback. Language of conversation is evidence for response language, not automatically note language, filename language, nationality or research results. Existing bilingual notes/accepted rules outrank a casual new-language message.

Distinguish task-only requests ("this answer in Japanese") from enduring ones ("from now on, notes in French"). A temporary profile may be used by render without changing defaults. Enduring choices update the same workspace profile. Do not translate/move old notes automatically; existing declared languages and prior legacy layouts remain recognized. A real migration still needs the normal before/path-map/link procedure.

Ask only missing consequential inputs: research purpose, selected root/materials, and unresolved reading/design preferences. Group at most three short questions. Do not ask again for clear context or ask for API keys.

## Supply normalized signals, not raw memory

```json
{
  "memory": {"response_language": "fr", "note_languages": ["fr"], "preferences": {"note_detail": "Concise, with the actual method and argument chain."}},
  "explicit": {"filename_language": "original"}
}
```

Allowed soft memory/context settings cover language, reading detail/navigation, palette and known scope/aim. Path/context pointers, taxonomy changes and extension activation are not inferred permissions; non-explicit candidates for them are ignored and reported. Research classification still needs a recognized naming basis. Saved source tags describe the caller-supplied signal, not authenticated facts about a user.

First use, after the LLM has prepared a small concrete design and selected root:

```sh
python scripts/p2p.py preferences --root /chosen/Academic --signals /chosen/signals.json --output /chosen/profile.json --apply
python scripts/p2p.py init --root /chosen/Academic --profile /chosen/profile.json --non-interactive --apply
# add --vault /chosen/Vault when several Obsidian vaults enclose the root
```

The initializer only accepts an empty root. It creates localized home/index text, the profile and short agent rules, then adds the Research Map and Full Network graph bookmarks plus a reading-entry bookmark to the vault's Obsidian bookmarks (see [links-and-graphs.md](links-and-graphs.md); `--no-views` skips this). It does not invent disciplines/projects/results, migrate old files or translate scope/aim text. Scope/aim are shown literally as supplied until the LLM writes the corresponding explanation from real context.

`render --apply` places each note at the path derived from its card, adds a UUID when the card has none, and runs `index`, which links the paper from its field index (creating a missing one) and the field from the Library index. The agent adds only the concept links its sources support.

When the user hands over PDFs and/or a results repository, continue with [pdfs-and-results.md](pdfs-and-results.md) right after `init`.

## Existing workspace: adopt, then connect

When the chosen root already has notes, do not stop at a map or summary. Each step below is one command; the agent supplies the judgments as JSON and the program writes the files.

1. **Register.** `init --adopt`, then `init --adopt --apply`. The user may pick any folder as the academic root; the vault prefix comes from the enclosing `.obsidian` (pass `--vault` when several enclose it). Only the profile and a missing `AGENTS.md` are written, then the graph bookmarks. The result lists notes without a graph role.
2. **Place.** Propose, per note, its canonical destination under `Library/<Discipline>/<Field>/<Papers|Concepts>/` or `Projects/...`, using recognized classification names. After the user approves, run `migrate --map moves.json` (preview), then `--apply`. It moves the files, rewrites every wiki/Markdown/embed link to them (including short `[[Name]]` links) across the vault, keeps before-copies and the map under `.maintenance/migrations/`, and removes emptied folders. Notes that should stay outside the academic structure are moved out of the root, not kept as exceptions; management/task pointers declared in the profile are the only allowed extras.
3. **Tag.** Propose a role per note (`paper`, `concept`, `field`, `direction`, `project`). A user's own chapters, headings or project parts are never `field`. After approval, run `tag --plan roles.json --apply`; it appends tag lines only and refuses conflicting roles.
4. **Connect.** `index --apply` (also run by `migrate`, `tag` and `render`) writes every path-derived link. Add concept links only from source-supported definitions/uses. A paper without a reading note stays a plain-text pending item, not an empty node.
5. **Verify.** Run `check` and report its `navigation` block. Repeat steps 2–4 for each open count until it is `complete`, or report what is left and why. Mention that the bookmarks load when the vault is reopened if Obsidian was running.

Later, resolve a task-only change with no writes:

```sh
python scripts/p2p.py preferences --root /chosen/Academic --signals /chosen/signals.json
```

For an explicit enduring change, preview and then apply using the returned expected hash:

```sh
python scripts/p2p.py preferences --root /chosen/Academic --signals /chosen/signals.json --scope workspace
python scripts/p2p.py preferences --root /chosen/Academic --signals /chosen/signals.json --scope workspace --expect-sha <preview-hash> --apply
```

`response_language`, ordered `note_languages` and `filename_language` are separate. `preferences` stores detail/filename/navigation choices; `layout` maps semantic folder roles to actual names; `palette` maps the same five roles across views. Preserve the user's main project/knowledge distinction and unique project identities. An output snapshot is not a second editable preference master.

## Other languages and real note content

`locales` lists built-in packs. `locales --template el` gives all label keys plus English references for the LLM to translate. Save a complete pack in `locale_overrides`; incomplete packs are rejected, not replaced by English. Region tags may reuse base labels; script variants require their own pack. Review language meaning; code cannot certify translation.

Have the LLM supply the content card described in [workflow.md](workflow.md). `render` fills all six templates using the selected labels/order. Every requested language needs supplied prose. The program does not translate, hallucinate reading or infer a contribution. New notes retain their own language metadata so later defaults do not relabel old content.

For an existing workspace, preserve its content, names and rule bodies, and follow the adoption steps above. For entry/task/maintenance paths use [preferences-and-handoff.md](preferences-and-handoff.md). Stop after a concrete usable entry, working graph views and a first real reading path; setup success is not a research assessment.
