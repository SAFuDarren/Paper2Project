# From literature to maintained research

Start from the user's research question or uncertainty. The workflow can enter at any stage and revisit earlier stages; it is a network, not a requirement to move every paper through a pipeline.

## 1. Understand the present research

Record the actual question, research object, task, assumptions, comparator, available evidence and unresolved steps. Use the user's records to distinguish completed work from future ideas. A scoped source reading, experiment or theorem retains that scope.

If the user wants positioning or proposal preparation, keep this separate from the manuscript. Organizing literature does not authorize modifying a paper. Avoid generating a large document when a concise direction page and a few papers answer the need.

## 2. Discover and register papers

Use available connected libraries and supplied materials first. For an explicit literature search, use current primary sources and report the actual search boundary: queries, sources/date, citation chains checked and unresolved leads. Expand along cited work, citing work, shared technical objects and competing approaches when they address the user's uncertainty. Do not claim an open-ended search is exhaustive.

For project discovery, use the [discovery workflow](discovery.md) to check known and pending work and render the first pass in chat. Deduplicate DOI/arXiv IDs and versions before creating a note. Preserve the full title and original landing page. Use the main research object to classify a paper, not its potential application to our project. Reading notes stay in Library even when multiple projects use them.

## 3. Read with enough method detail

Use `assets/templates/paper.md`. Keep a short summary and actual selected-reading scope above six sections:

1. **Research question:** What specific problem is addressed? What comparator or gap matters?
2. **Setup and assumptions:** What object, data, task, model class, constraints and access are assumed? Which conditions limit the result?
3. **Method:** What construction, representation, algorithm, estimator, optimization or proof device is used? Describe enough mechanics to recover what was done.
4. **Results and evidence:** What is proved or demonstrated, under which conditions, against what baseline? Distinguish theory, simulation, trained benchmark and hardware evidence.
5. **Argument chain:** How do assumptions lead through the method and intermediate steps to the result? This is a reconstruction, not a claim to have checked all proofs.
6. **Relation to our work:** What is reusable, what is only nearby, and which exact bridge remains missing?

Attach source locations (section/theorem/page/figure) in a compact expandable block. If only an abstract was available, say so and leave unverified method/proof details unknown. Never fill a template by inventing facts.

Use the profile’s ordered note languages, with corresponding structure, quantities, conditions and links. New rendered notes declare their languages in metadata. Do not invent translated paper titles or scientific prose; language section labels are unnecessary unless requested.

## 4. Consolidate concepts

Create a shared concept when it is actually used/defined and improves retrieval. One concept may have several source papers, but one canonical note. Give a concise definition, context/conditions, source papers and explained related concepts.

Link the first substantive occurrence in each language. Do not link repeated terms everywhere or generate nodes from keywords alone. Paper→concept links plus backlinks provide navigation; direct concept–concept edges need source-supported definitions, implications, uses or contrasts at both endpoints.

## 5. Map opportunities and real interfaces

Potential directions live under Projects using the same discipline/field names as Library. Each direction page links to papers and any actual project home. A research connection answers:

- What does the cited literature establish?
- What object, method, bottleneck or task connects it to our work?
- What still must be proved, implemented, measured or compared?

For an application transfer align target task, allowed inputs, output object, all persistent/computational resources, metric, baseline and practical overhead. A guarantee in one metric need not improve another; a trained baseline is not an optimum over all admissible models. Record the smallest discriminating next check, not a speculative benefit.

Mark candidates as candidates. Maintain nearby/remote leads without manufacturing an edge for a connected-looking graph. Prefer a broad recognized direction until a finer established term improves retrieval.

When the user already has a list/map of known connections, reconcile it item by item with the new direction/project paths. Retain each source, evidence status, missing step and actual destination, including remote or currently unconnected leads. Report unplaced items explicitly. A larger file count or a visually fuller graph does not demonstrate that the known connections were preserved.

## 6. Develop a concrete project

Create one project home when there is a specific question and planned or actual activity. Select its primary direction by the principal object/contribution. Link the same home from cross-disciplinary directions.

| Folder | What belongs here | Useful contents |
|---|---|---|
| Problem | Our question and scope | Goal, assumptions, fixed task, comparator, success criteria, unresolved gap |
| Methods | Our actual use/adaptation/construction | Why this approach, proof/implementation strategy, source dependence, cost |
| Results | Our evidenced increment | Claim/experiment, exact conditions, artifact/version, validation, limits, negative results |
| Extensions | Potential research | Missing bridge, relation to present work, candidate status, smallest next check |

Keep each substantial question/method/result in a named record when needed. Do not bundle all types into one long file or create empty files for every possible subtype. The home is a concise index: aim/status, grouped internal links, relevant directions and Library sources. Only this page gets the project graph tag.

Preserve an existing evidence ledger/task system by linking it. A result source block can reference external code/data/records; experimental data and code need not move into the vault.

## 7. Maintain incrementally

After a meaningful update, deduplicate sources, preserve reading scopes, check canonical paths, update explained relations in all selected languages, and run the local checker. For moves compare the source/relationship inventory, not just total file counts.

In Obsidian verify actual display/navigation and restored graph settings when those changed. If the native app is unavailable, report structural checks separately; do not claim a visual check. Readability does not require every internal record or folder index to become a node.

Return a concise result with the reading entry, additions, remaining evidence gaps and next useful action. Detailed check logs should not dominate the reading interface.

## Deterministic card rendering

Supply a JSON card with `id` (stable), `title` (original), optional `source_id`/`subfield`, shared `metadata`, and `content` keyed by each selected language tag. For a paper, shared metadata supplies `paper` (primary URL), `version`, `field`; each language supplies `summary`, `reading_scope`, `question`, `setup`, `method`, `results`, `argument`, `connection`. Use real source-grounded text, or state the actual unknown/limited reading explicitly.

```sh
python scripts/p2p.py render --root /chosen/Academic --kind paper --input /chosen/card.json --output "Library/Computer Science/Machine Learning/Papers/Sequence Models - Short title.md"
```

Preview includes Markdown. Add `--apply` for exclusive new-note creation with readback; it does not replace existing notes or duplicate IDs/sources. `--profile` may select a task-only profile snapshot. Custom locale packs used by durable notes must already be saved in the workspace.

The six templates share semantic keys (see `i18n.SPECS` for exact required keys): field (`scope`, `papers`, `related_research`); concept (`definition`, `related_concepts`, metadata `from_papers`); direction (`scope`, `papers_concepts`, `opportunities`, `projects`, metadata `field`/`naming_basis`); project (`scope`, `problem`, `methods`, `results`, `extensions`, `research_connections`, `knowledge_basis`, metadata `status`); project-record (`body`, `basis_scope`, `evidence`, `remaining`, metadata `project`/`record`/`status`). Relationships inside these fields still need explained source support. Customize filename wording in the selected language; nonstandard paper names retain `p2p_subfield` for classification checks.
