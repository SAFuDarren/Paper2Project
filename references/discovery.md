# Project discovery and review

Use this route for related work, new directions, and academic or industrial applications. Read the project's current question, result and open step. Check existing Library coverage before expanding. Search in target-field vocabulary and verify the original paper or official engineering source. Use public terms and sources for external queries.

## Inventory and first pass

Run inventory with the active packet paths from the existing task handoff. It checks the selected workspace's canonical directions, paper identity and explicit version, local PDF links, and previously staged items. It reports ambiguous titles for verification. A registered field alone does not prove an existing project connection.

```sh
python scripts/p2p.py discover --root "/chosen/Academic" --input inventory.json --prior previous.json
python scripts/p2p.py discover --root "/chosen/Academic" --input findings.json --prior previous.json --stage pending.json
```

Repeat `--prior` for unresolved batches. Omit it on the first run. Keep packets outside Library and Projects. Stage only in a new path. When all items are already known or pending, the command returns a chat report without creating an empty packet.

Use the returned `markdown` directly in chat. One complete card per unadmitted source or new version, even if several support the same research direction. Existing sources get a brief item. Previously introduced pending items can be short for a status-only recap. Academic papers and industry cases stay in separate sections. A source link is available for verification, and the first pass is readable without opening it.

### Input contract

Inventory needs an `items` list. Each item supplies `id`, `title`, and `source` (original URL) or `identifiers` (DOI/arXiv strings). An optional `direction` is a canonical name. Use `lane: "industry"` and a stable `case_key` for industrial candidates; this checks pending case duplicates without creating an industry registry. An optional top-level `project` is the path of a registered project note relative to the academic root. The program checks that path. Supply `identity_evidence` when combining distinct DOI/arXiv identifiers verified to be the same work.

For staging, the agent supplies these concise, single-line fields for each new paper:

| Field | What to provide |
|---|---|
| `authors`, `overview` | Author names and one plain-language sentence |
| `field`, `publication` | Recognized area and verified venue/year or preprint status |
| `question`, `method`, `conditions` | The specific question, actual method and result, and conditions or reading limits |
| `contribution` | The paper's contribution and its scope |
| `connection`, `potential` | Which project step it bears on, the evidence, and what a future check or result would contribute |
| `source`, `locator` | Public HTTPS primary source and section, theorem, page or figure checked |

For an industry case, supply `organization` in place of `authors`. The same fields render as application field, operational problem, implementation, demonstrated value and potential application value. `publication` is optional. Separate published deployment measurements from a documented capability, and report the scope of any benefit.

An admitted source needs only `overview` and `connection` for a brief item. A same-language pending card is reused. Set `recap: true` only when the item was already introduced in full and the user needs a status recap. If the response language differs, supply actual prose in the requested language. The response label pack follows the task's `language` or saved response language. If the profile uses `auto`, supply the resolved task language. Eight built-in packs are available. To use another language, supply a complete `labels` object with the keys from [discovery-labels.json](../assets/discovery-labels.json). Notes still follow their own saved language preferences.

## Review and admission

Choose by the paper or case name in the chat. Map the user's actual choices to packet IDs. A verified new source can have a proposed connection to the selected project. To propose a connection for an already admitted paper, set `propose_connection: true` and supply `source`, `locator`, `connection` and `potential`. A source on the same topic does not establish a connection.

```sh
python scripts/p2p.py review-discovery --root "/chosen/Academic" --packet pending.json --decisions choices.json
```

`choices.json` contains `packet_sha256` (returned by staging), `approval_reference` (the relevant user decision or pointer), and independent `materials` and `connections` maps from item ID to `approve`, `hold`, or `skip`. Omitted IDs remain pending. The command validates an explicit plan against the current workspace and packet; only the host can verify that the choices came from the user. After a Library change, run discovery again against the current inventory before applying a later connection decision.

For authorized additions, follow the existing note and link workflow. Reconcile a new version with the canonical paper entry, keep separate proposals separate, and update the existing task handoff. The discovery commands never apply the plan. Leave semantic judgments to source reading; code handles exact status, duplicate checks, required fields, layout and packet validation.
