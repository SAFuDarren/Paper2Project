# From PDFs and existing results to a working map

Use this route when the user hands over papers (a folder of PDFs) and their own results (a repository or folder) and expects the finished workspace. Every rule-based step is a command; the agent's work is reading and judging. Do not stop at a summary or a partial map: finish when `check` reports `navigation.status: complete`, or report exactly what is left.

## 1. Workspace

`init` (empty folder) or `init --adopt` (existing notes), as in [onboarding.md](onboarding.md). Register the recognized discipline/field/direction names you will use in the profile `taxonomy` (explicit `preferences` signal) so classification is checked against them.

## 2. Papers

```sh
python scripts/p2p.py pdfs scan --root /chosen/Academic --from "/path/to/pdfs"
python scripts/p2p.py pdfs text --root /chosen/Academic --file "/path/to/pdfs/paper.pdf"
```

`scan` is read-only: hash, page count, title metadata, DOI/arXiv identifiers, duplicates, files that are not PDFs, and whether a note or attached copy already exists. Work through its `new` items; `note_exists_without_this_pdf` items need an identity/version check, then `pdfs attach`.

`text` returns the selectable text page by page, so a text-only model can read the paper. It uses PyMuPDF when installed, else poppler's `pdftotext`, else a built-in reader for common PDFs. Pages flagged `needs_visual_check` (formulas, unusual fonts, scans) must be checked against the original. If no engine can read a file, the result says so: install PyMuPDF (`pip install pymupdf`) or poppler, or record the reading scope as metadata only. Never fill a note from the filename.

For each paper write a card (see [workflow.md](workflow.md)) with its classification, real six-part content, `locations` (section/page/figure per language) and `"pdf": "<file>"`. `render --apply` places the note and attaches the original in one of two ways, then runs `index`:

- `"pdf_mode": "copy"` (default): a byte-identical copy at the field's `PDFs/<note name>.pdf`, so the workspace is self-contained and portable.
- `"pdf_mode": "link"`: no copy; the original is registered where it is and linked (a wikilink inside the vault, a `file://` link outside it). Use it when the user keeps a curated PDF library or other tools point at those files.

Either way the user's original files are never moved, renamed, modified or deleted, and `migrate` refuses to move any PDF; only a managed copy follows its note. `.maintenance/pdf_attachments.json` records each copy or link with its hash, page count and original path. If a linked original later changes or disappears, `check` reports it and the agent asks the user; nothing is repaired automatically. One PDF belongs to one paper note; a second authentic revision gets an explicit name such as ` - arXiv v2`.

Render concepts before the papers whose text links them. Link a concept only where the paper defines or uses it.

## 3. Our results

```sh
python scripts/p2p.py repo scan --path "/path/to/results-repo"
```

Read-only: current commit and branch from `.git` (no git binary needed), the origin URL without credentials, uncommitted changes when git is available, and the documents, notebooks, results, figures and code to cite. Read the README and documents. Then write, per concrete question, one project card and only the Problem/Methods/Results/Extensions records the repository actually supports. Each project or record card may carry `"evidence": [{"path": "results/metrics.csv", "repo": "/path/to/results-repo", "note": "..."}]`; the program pins the commit and writes permalinks (GitHub, GitLab, Bitbucket) or `path @ commit`. Uncommitted work is cited only after it is committed. Keep established results, our evidence, limited demonstrations and candidate extensions distinct.

## 4. Connections

Directions and project homes are linked to their field and to each other by `index`. A substantive connection (direction↔direction, a cross-field project, concept↔concept) is recorded with `relate` and its evidence: what the literature establishes, how it bears on our work, the missing step, and the supporting paper notes, in every note language. See [links-and-graphs.md](links-and-graphs.md). `check` reports hand-written connections that were not recorded.

## 5. Search and verify

```sh
python scripts/retrieve.py sync --root /chosen/Academic
python scripts/p2p.py check --root /chosen/Academic
python scripts/p2p.py brief --root /chosen/Academic
```

[retrieval.md](retrieval.md) covers search. `check` audits the originals (placement, bytes, hashes, links in every language block, unregistered PDFs), the registered connections, the structure and links; `brief` lists what is left and the next commands. Report the `navigation` block, the number of papers with originals, registered connections and any flagged pages that still need visual checking.
