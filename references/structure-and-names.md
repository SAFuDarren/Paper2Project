# Structure, names and migration

## One taxonomy, two purposes

Library and Projects share discipline and field spellings. Library fields are knowledge indexes; Projects directions are research opportunities. The same academic term can serve both roles without making two copies of a paper or project.

```text
<root>/
  Academic Home.md
  AGENTS.md
  .paper2project.json
  Library/
    Library.md
    <Discipline>/<Field>/
      <Field>.md
      Papers/<Recognized subfield> - <Short paper title>.md
      Concepts/<Concept name>.md
  Projects/
    Projects.md
    <Discipline>/<Field>/<Recognized direction>/
      <Direction>.md
      <Project title>/
        <Project title>.md
        Problem/<Specific question or scope>.md
        Methods/<Actual approach>.md
        Results/<Specific result>.md
        Extensions/<Potential extension>.md
```

Intermediate discipline/field indexes are optional navigation aids and are not extra graph nodes. Create only populated directions and records; the fresh initializer deliberately creates only the reading entry and two broad indexes.

## Academic names

- Prefer an established discipline/field/subfield name supported by formal classifications, a mainstream conference, university teaching or peer-reviewed usage. No single universal hierarchy is assumed.
- Register the name, parent discipline/field and basis in the profile's `taxonomy` list. An entry has `discipline`, `field`, `direction`, `basis` and optional `basis_url` keys. All populated hierarchy branches must use the same spelling in both sides. A source's own terminology can be documented without adopting it as a new official subfield.
- Use the paper's primary research object for its home, not the application we hope to build. A cross-field project has one primary home selected by its actual question/contribution; other directions link there.
- Do not transplant a fixed list of quantum-information categories into other users' work. Empty taxonomy means classification has not yet been chosen, not permission to invent one.

## Reading names

- Keep original/descriptive filenames unless the user chooses another filename language/style. The standard pattern is Paper: `<Recognized subfield> - <Short title>.md`. Keep full original title in the note; a short title must preserve the object and claim.
- Concept: the established concept name. Project: the actual question/activity, not `Project 01`, a paper title copied into a new project, or a generic `Overview`.
- Main project file matches its directory name. Cross-reference that exact path; no second home or active redirect mirror. Status changes do not move a project to a separate duplicate tree.
- Internal records use recognizable titles within Problem/Methods/Results/Extensions. Their titles are specific research descriptions, not new academic directions.
- If a direction name equals its Library field, a ` - Research Directions` suffix may disambiguate its entry filename. The academic term and directory remain the canonical name.
- Resolve actual filename collisions with first author/year or a meaningful qualifier. Do not add opaque numbering to every name.

## Stable identity and source identity

New templates include a persistent `p2p_id` (generate a UUID; keep it when moved). It is technical metadata, not a displayed title. Canonical DOI/arXiv IDs identify source papers, independently of their note UUID. Treat arXiv versions as versions of one source unless the user explicitly needs a version comparison.

Legacy notes can remain metadata-free. Export labels path-derived fallback IDs as such; they change on a move. Before building a persistent external index, adopt stable IDs or send an explicit old/new migration map. Never silently reassign a note's identity.

## Migration checklist

1. Capture scoped originals, file hashes, canonical IDs, primary source identities and semantic relation/coverage inventory. Keep snapshots outside the reading interface and graph query.
2. Prepare old→new paths, role-specific routes for combined field/direction pages, and heading/block-anchor redirects where needed. Count alone is insufficient to preserve relationships.
3. Recheck original hashes before applying. Preserve concurrent user edits; do not overwrite them to complete a migration. Carry out only the authorized scope.
4. Move once; rewrite active full-path wikilinks, Markdown links, project sources and current manifests. Preserve historical provenance instead of pretending to reread sources.
5. Compare source text, all declared language blocks, citations and explained relations. Remove only empty retired directories; retain original PDFs and unrelated configuration.
6. Check links, anchors, one project home and typed records. Inspect real reading jumps. If graph settings changed, save and restore both views through the supported Obsidian interface.
7. Update the existing maintenance entry and give the new reading entry. Do not leave duplicate redirect homes or build another task system.

This skill carries no permission to publish a repository, modify manuscripts, contact authors, change database/sync settings or install extensions. Those follow the user's actual task and chosen tools.

Role folder display names are configured in `layout`; English tree names above denote roles. Preserve accepted paths on adoption. Preference updates may retain prior layout mappings for checking old notes, but do not perform a migration or justify a second home.
