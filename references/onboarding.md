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
```

The initializer only accepts an empty root. It creates localized home/index text, the profile and short agent rules. It does not invent disciplines/projects/results, migrate old files, translate scope/aim text or save native app settings. Scope/aim are shown literally as supplied until the LLM writes the corresponding explanation from real context.

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

For an existing workspace, preserve its content, names and rule bodies. Adopt a tailored profile without moving anything when sufficient. For entry/task/maintenance paths use [preferences-and-handoff.md](preferences-and-handoff.md). Stop after a concrete usable entry and first real reading path; setup success is not a research assessment.
