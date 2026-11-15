# Searching existing research

`scripts/retrieve.py` searches the workspace's role notes and project records together with the registered original PDFs. Use it before discovery ("what do we already have?") and when answering questions from the Library or Projects.

```sh
python scripts/retrieve.py sync --root /chosen/Academic
python scripts/retrieve.py search --root /chosen/Academic "How is attention scaled?"
python scripts/retrieve.py search --root /chosen/Academic "key dimension" --source pdf --paper "Library/.../Papers/Note.md"
python scripts/retrieve.py page --root /chosen/Academic --pdf "Library/.../PDFs/Note.pdf" --page 4
python scripts/retrieve.py status --root /chosen/Academic
```

## Index and freshness

The index is a derived SQLite file at `.maintenance/retrieval.sqlite`; delete it or run `sync --rebuild` to rebuild. Notes, PDFs and the PDF register stay primary. `sync` is explicit and incremental (changed hashes only). Search hashes the current files and leaves out changed or deleted ones, reporting them under `freshness.needs_sync`; run `sync` after authorized edits.

## Lexical and semantic search

Lexical search (BM25 over words and Chinese bigrams) always works and needs no model. Semantic search runs only when the user enabled the embedding extension in the workspace profile, for example:

```json
"extensions": {"embedding": {"enabled": true, "provider": "ollama", "endpoint": "http://127.0.0.1:11434",
                              "model": "bge-m3", "dimensions": 1024}}
```

`provider: "openai-compatible"` uses `/v1/embeddings`; a key is read from the environment variable named in `api_key_env`, never from the profile. With vectors present, `--mode auto` combines both scores; `lexical` and `semantic` force one. Changing the model rebuilds the index. Onboarding never enables this; text leaves the machine only if the user configured a remote endpoint.

## Reading results

Results are grouped by canonical note (a PDF passage belongs to its paper note). A note passage gives its heading and source lines; a PDF passage gives the physical page, character offsets within that page's extracted text, `needs_visual_check`, and an `open` link such as `[[...pdf#page=4]]`. `page` returns a registered original's page text directly. Text comes from the same extractor as `pdfs text`: selectable text only, no OCR or formula reconstruction.

A hit is a pointer, not support: `evidence_status` is always `not_inferred_from_retrieval`. Read the passage and the original, keep the recorded reading scope, and never turn similarity into a link or a connection. A miss does not show that the literature lacks something; rephrase with the source's own terms or restrict to a paper with `--paper`.

Users with their own store (PostgreSQL, a vector database, a knowledge graph) keep their adapter in `local/` and their settings in the profile; see [extensions.md](extensions.md) and [updates.md](updates.md).
