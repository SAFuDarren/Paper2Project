# First run

Two common starts. In both, the agent reads only context that is actually available, asks for missing consequential choices, and finishes when `check` reports `navigation.status: complete`. No memory API, API key or background service is required. All example files here are fictional and contain no real reading or results.

## From papers and results

> Use Paper2Project to build my research workspace in `<folder>`. My papers are in `<folder of PDFs>`; my results are in `<repository>`.

The agent follows [pdfs-and-results](../references/pdfs-and-results.md): `init`, `pdfs scan` (intake queue), `pdfs text` (reading), one card per paper rendered with `render` (add `"pdf": "<file>"`, and `"pdf_mode": "link"` to keep the original where it is), `repo scan`, project and record cards with `"evidence"`, `relate` for connections, `retrieve.py sync`, then `check`.

## From existing notes

> Use Paper2Project for this selected research folder. Reuse my known language and reading preferences, ask only missing design choices, and keep existing files intact.

The agent follows [onboarding](../references/onboarding.md): `init --adopt`, then `migrate`, `tag` and `index` with your approval at each step.

## Example inputs

| File | Used with |
| --- | --- |
| [signals.json](signals.json) | `preferences --signals` (normalized language and detail choices) |
| [paper-card.json](paper-card.json) | `render --kind paper`; the path is derived from `discipline`, `field`, `subfield` and `short_title` |
| [project-record-card.json](project-record-card.json) | `render --kind project-record`; `evidence` becomes commit permalinks |
| [relations.json](relations.json) | `relate --plan`; written into both endpoints and `.maintenance/relations.json` |
