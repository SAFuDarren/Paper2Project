# Meaningful links and readable graphs

## Links have different meanings

| Link | Meaning and evidence |
|---|---|
| Field→direction | Classification only; not a scientific implication |
| Paper→concept | The paper defines, uses or compares that concept |
| Concept↔concept | Explained definition/use/implication/contrast, with supporting paper(s) at both endpoints |
| Direction↔direction or project | A concrete shared task, method, resource, bottleneck or transfer interface; cite the literature fact, our relevance and missing step |
| Home→internal record | Navigation; does not make each record a separate project |

Do not infer edges from shared words, proximity in a folder, an embedding score, or a desire for a connected graph. Backlinks provide reverse navigation but do not add an unsupported interpretation.

## Link format

Use complete vault-relative wikilinks with readable labels:

```text
[[Academic/Library/Computer Science/Machine Learning/Concepts/Hidden Markov Model|Hidden Markov model]]
[[Academic/Projects/Computer Science/Machine Learning/Sequence Models/Project Name/Project Name|Project Name]]
```

`Academic/` is an example prefix. The profile's `vault_prefix` determines the actual prefix; it is empty when the academic root is itself the vault. Links omit `.md` by convention. The checker also handles relative Markdown links (including quoted link titles), headings and Obsidian block IDs. Embedded media/HTML links and external web URLs still require separate checks.

Link the first substantive core term in each language. Do not repeat links at every occurrence. For a multilingual note, preserve the semantic link set across declared blocks; labels can differ. Matching translated heading positions is a structural check, not semantic proof. A concept's source list is useful navigation even though backlinks already exist.

## Two views, one underlying network

Roles use tags at the end of a note. An existing tag-only line such as `#paper #selected` is accepted without rewriting it; an extra organizational tag does not become a second graph role:

| Role | Tag | Color |
|---|---|---|
| Field / knowledge index | `#research-field` | Blue `#5B9FE6` |
| Potential research direction | `#research-direction` | Warm gold `#E3B34F` |
| Concrete project home | `#research-project` | Coral `#E57D86` |
| Paper | `#paper` | Teal `#5AB8A0` |
| Shared concept | `#concept` | Purple `#AE8CDB` |

Only the main home gets the project tag. Internal records, broad discipline indexes, Academic Home, rules and maintenance logs are outside these graph roles. An internal note can be exported to an agent without becoming a graph node.

For an example academic prefix `Academic`, Research Map uses:

```text
path:"Academic/" (tag:#research-field OR tag:#research-direction OR tag:#research-project)
```

Full Network uses:

```text
path:"Academic/" (tag:#research-field OR tag:#research-direction OR tag:#research-project OR tag:#paper OR tag:#concept)
```

If the academic root is the whole vault, omit the path clause. Adapt the path, not the role vocabulary. Both filters and role/color groups are generated as guidance in the workspace's scoped AGENTS. Configure/save them through Obsidian's supported interface; the local utility does not edit `.obsidian`.

The Research Map retains real direction/project connections, not just a tree of classification. If several internal questions support one displayed project edge, preserve their individual facts and source locations inside the project; visual aggregation is not new evidence.

## Verify the saved views

Open Research Map, check the query, role groups and distinct colors, then save and restore it. Repeat for Full Network. Editing a bookmark title alone may not update the saved graph state; use the application's supported save/replacement flow and verify restoration before removing any temporary predecessor.

Color denotes role, not importance, proof or completion. Use clear labels and written status; graph scope should remain understandable in monochrome. Avoid dense edge-label clutter and forcing every record into the direction view.

`p2p.py check` covers local paths, anchors, role placement, paper filename/prefix consistency, required paper sections/metadata and PDF placement for provenance review. It reports unregistered naming bases as `needs_review`, even though exit 0 indicates no structural errors. It does not inspect native graph settings, translation meaning or whether a cited paper supports an edge. Those remain source/UI checks.
