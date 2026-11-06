# Preferences, one entry and reliable handoff

Use for adopting an existing workspace or improving how another agent finds its rules and maintenance state. These changes improve execution without changing the user's research/management requirements. `init` does not perform this migration and does not install global hooks.

## Preserve before adapting

Read current user instructions, the accepted local rule files, management entry, current task and its template. Summarize the current constraints before proposing a change. Explicit choices override package defaults; inferred soft choices carry their source and remain overridable, not facts about the user. Do not infer language, naming or color preferences from nationality.

During entry/path/task-format work preserve the accepted content hierarchy, project identity, naming, language/order, palette, links, relation evidence and scientific definitions. Do not rewrite a user's rules to match the package. Do not change a manuscript or result status while tidying metadata.

Keep one effective profile. Do not create a second preference ledger or copy local rule bodies into several startup files. Rules remain authoritative in their existing files; the profile stores choices and pointers, not a competing paraphrase of every rule.

## User choices and actual tool support

| Choice | How to establish it | Saved location |
|---|---|---|
| Working/note language(s), order and labels | Explicit choice or accepted existing notes; ask only if missing | `note_languages`, `response_language`, `filename_language`; complete custom packs in `locale_overrides` |
| Filename style | Preserve accepted names; choose a style without changing established academic identity | `preferences.filename_style` |
| Note depth | Concise but enough assumptions/method/argument; user can request more detail | `preferences.note_detail` |
| Navigation / graph presentation | Reading entry, readable labels, graph scopes, extra tags | `preferences.navigation_style`; `palette` |
| Disciplines/fields/directions | Actual research plus a checked naming basis, not a nationality default | `taxonomy` |
| Workspace location | User-selected root and vault-relative prefix | Root argument and `vault_prefix` |
| Existing entry, task, template and maintenance location | Discover from authorized context, then preserve/reconcile | `context` pointers below |
| Optional knowledge/retrieval tools | User selects provider/version/data scope in a later task | Disabled extension slots; never auto-enable |

The v2 CLI supports ordered `note_languages`, separate `response_language`/`filename_language`, locale-aware rendering/checking and customizable folder-role names in `layout`. Built-in and complete custom locale packs use the same semantic template keys. The legacy `language: en` and `en-zh` values remain readable. Use `preferences` for previewed transient or guarded durable updates; it never rewrites notes. See [onboarding.md](onboarding.md) for context/memory precedence and commands.

The default five-color role scheme and English filename examples remain useful presets. User-selected alternatives need consistent role mapping and meaningful classification, not a second duplicate network. Preserve source provenance and one canonical project home regardless of presentation.

## Minimal context pointers

The normal `.paper2project.json` may contain:

```json
{
  "context": {
    "materials": [],
    "project_overviews": [],
    "management_entry": "Operations/START_HERE.md",
    "maintenance_entry": "Operations/tasks/existing-task.json",
    "task_template": "Operations/specs/task-template.json",
    "maintenance_directory": "Academic/.maintenance"
  },
  "preferences": {
    "preserve_existing": true,
    "filename_style": null,
    "note_detail": null,
    "navigation_style": null
  }
}
```

Paths above are examples, not a required local tree. Management/task/template/maintenance pointers are vault-relative for portable active operation. `maintenance_entry` retains its existing meaning: the current tracker/task record, not a second management entry. Source material pointers may refer to user-selected external research archives; keep that distinction explicit. The JSON stores pointers only and grants no new read/write permissions.

## 1. One management entry; original rule bodies stay in place

- Reuse an existing START_HERE or equivalent. Add one only if none exists and an entry is actually needed. Do not create a new master page beside an existing one.
- The entry gives a short reading order: applicable rules → current task/state → this task's source pointers/checks. It links to rule bodies instead of copying them.
- If the user authorizes host-level navigation, add only a short conditional pointer to the existing startup instructions: tasks involving this workspace first read its management entry. Do not silently edit global AGENTS or assume every platform discovers another directory's rules.
- Other agents receive the same entry path. An installed skill or saved profile alone is not proof that the next agent loaded the rules.

## 2. Active maintenance dependencies travel with the vault

- Put the current source/relationship inventories, active path map and reusable read-only checking tools in one chosen maintenance directory inside the vault. A hidden `.maintenance` directory is a suitable default for keeping technical material out of the reading graph; preserve an already accepted location when appropriate.
- Keep the existing task record in its established task directory. Point to it; do not create a second editable task under the maintenance directory.
- Use the declared vault-relative base for the profile's operational pointers. Existing task/source records may have their own accepted base (for example, a subdirectory inside the vault); preserve that contract and record its mapping in the entry. Do not mix bases within the same field family or silently reinterpret old paths. Normalize only with evidence of the correct target.
- Original papers, code and proofs stay in their research/source locations. A source archive reference can remain external; do not make routine local link/structure checks depend on a historical temporary run directory.
- Preserve old versions/backups and their original provenance. Identify which are historical references and which are required active dependencies. Do not relocate frozen history merely to make every string relative.
- Inspect existing checkers before reusing them: a one-off migration checker may contain frozen counts, old paths or assumptions about tag formatting. Keep its original scope as history. A day-to-day checker uses the current inventory and accepted rules; do not alter user notes or weaken scientific requirements just to make a test pass.

## 3. Normalize task records to the existing template

- Read the actual local task template/contract. It owns field names and status values; the skill does not impose a new universal task database/schema.
- Map old fields to that existing format with a before/after record. For example, if the accepted template uses `result: pass`, map an equivalent `status: passed` check to it; do not change what was checked or when.
- Preserve task ID, owner/reviewer, actual completion state, source/evidence, dates, checkpoint and history. Unknown stays unknown. Formatting does not grant a new pass, approval or permission.
- Back up the active record and update that same record. Do not batch-rewrite frozen history or replace an external project system with a new tracker.
- A template and an owner field are conventions, not runtime locks. Coordinate writers and reread before writing; do not promise enforced routing or concurrency protection unless implemented and tested.

## Acceptance: prove handoff with a small rehearsal

1. Give a fresh-context agent only the management-entry path and task purpose. It should identify the applicable rules, unchanged preferences, canonical task, state and next action without relying on the previous chat.
2. Resolve all active entry/task/template/checker pointers from the declared path base. Test a relocated copy of the scoped vault; only host-level root discovery may need remapping. Never use the original paths to make the relocation check pass unnoticed.
3. Compare rule bodies and research content before/after. Only authorized navigation, maintenance locations and record formatting should differ. No source loss, duplicated project home, changed preference or new scientific claim.
4. Repeat the read-only check and resume lookup. It should not create files, duplicate tasks or rewrite facts. Inspect actual source/UI behavior for claims outside structural checks.

Record observed results in the existing task's checkpoint. No daemon, database, platform migration or new orchestration framework is required by this procedure.
