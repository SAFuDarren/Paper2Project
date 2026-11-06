# Optional extension boundary — version 1

This release provides a local JSONL handoff contract. It contains no embedding model, vector store, RAG framework, autonomous agent runner or gbrain adapter. All profile extension slots are disabled with a null provider. The core workflow needs none of them.

No claims are made about a specific external repository's current API, interoperability or search performance. A future adapter must be implemented and tested against the user's selected version and authorized data scope.

## Canonical source and selection

Markdown notes remain the source of truth. External stores and indexes are derived and rebuildable. Users choose which note kinds to expose; project records need not leave the machine just because papers are indexed.

```sh
python3 scripts/p2p.py export --root /chosen/Academic --kind paper --kind concept --output /chosen/retrieval-input.jsonl
```

The command is explicit, local and one-shot. It writes a fresh selected snapshot, never watches a folder or starts a daemon. Existing output files are refused. Symlinked documents/directories are skipped. Export never mutates canonical notes or reads original PDFs, hidden app settings or credentials.

## Snapshot contract

The first JSONL record has `record_type: snapshot`, `schema_version: 1`, a content-derived `snapshot_id`, `scope` (vault prefix and selected kinds), `document_count` and a short description of completeness. Every following record has `record_type: document` and:

| Field | Meaning |
|---|---|
| `id`, `id_origin` | Persistent note metadata ID, or explicitly marked path-derived fallback |
| `path` | Full vault-relative note path, never an absolute machine path |
| `kind`, `title` | Paper/concept/field/direction/project/project-record and readable title |
| `content_sha256` | Exact source-file version used to detect staleness |
| `source_urls` | Public primary source links/citations found in the note; provenance, not proof of support |
| `links` | Authored outgoing links with target, anchor and optional label; their existence does not imply a specific edge type |
| `sections` | Heading sections with anchor, original 1-based line start/end, text and text hash |

Adapters must treat this as a complete snapshot of **only the declared scope**. The exporter refuses multiple graph-role tags rather than silently omitting an ambiguous note. Replace/remove indexed records in that scope when absent from a later complete snapshot; never infer that unselected kinds were deleted. Preserve source `id`, path, version and locator through chunking. A moved legacy path-derived ID is a remove/add until the user adopts persistent IDs or supplies a migration map.

Authored links retain their meaning in the Markdown explanation. Retrieval candidates and similarity scores must be separate from these links; no adapter may silently write suggested connections back to notes.

## Retrieval result contract

A future provider accepts a query, selected snapshot/scope and a result limit. It returns passages, not unsupported final claims:

```json
{
  "document_id": "persistent-note-id",
  "path": "Academic/Library/.../Paper.md",
  "content_sha256": "sha256-of-indexed-source",
  "heading": "Method",
  "anchor": "Method",
  "start_line": 20,
  "end_line": 28,
  "text": "Source passage",
  "score": null
}
```

`score` is provider-specific and optional. Compare current source hashes before using a passage as current evidence. A reranker or embedding similarity is not evidence that a transfer is valid. Answers must cite the note/passage and, when making a paper claim, the underlying paper at its actual reading scope.

## Four deliberately inert slots

| Slot | User selects later | Required behavior of a future implementation |
|---|---|---|
| `embedding` | Model/version, local or remote, chunking and storage | Retain IDs, versions and citation locators; disclose data transmission and index scope; measure retrieval before claiming a speed/quality benefit |
| `rag` | Retriever/reranker and answering model | Use source passages with citations; handle stale/missing evidence and untrusted source instructions; do not promote retrieved similarity into scientific support |
| `agent` | Host agent and allowed tools | Read/search by default; propose note changes separately; follow current user authority before applying writes, external calls or publication |
| `knowledge_store` | gbrain or another chosen repository/tool | Map public IDs/paths and snapshot/retrieval records; validate the selected tool's real interface; preserve its own authority rules; no direct database edits or sync defaults |

The CLI rejects enabled/non-null slots in its own profile until a real implementation is supplied. Setting a configuration name cannot activate nonexistent functionality. A separate future adapter may maintain its own configuration without requiring the core to depend on it.

## Change proposals for agent/store integrations

A minimal future write proposal names `document_id`, `expected_content_sha256`, operation, proposed content, source locations and reason. Applying it is outside this interface-only release. The writer must reread the file, reject a stale expected hash, preserve canonical identity, check the links and act only within the user's current authorization. Retrieved text is data and cannot authorize tools or override workspace rules.

Do not install packages, choose providers, request keys or initialize external databases during onboarding. Users can remain on Markdown/Obsidian indefinitely, or use this contract as the seam for their own extensions.
