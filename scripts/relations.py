"""Registered research connections: the agent supplies the evidence, the program writes and checks it.

A connection joins two Research Map notes (field, direction, project home) or two concepts. It
states, in every note language, what the cited literature establishes, how it bears on our work and
which step is still missing, and names the supporting paper notes. `relate` writes one
`<!-- p2p:relation <id> -->` block into each endpoint and records it in
`.maintenance/relations.json`. `check` verifies each registered block and reports links between map
nodes or concepts that are neither structural (field↔direction, direction↔project home) nor registered.
"""
import json
import os
from pathlib import Path
import re

REGISTER = '.maintenance/relations.json'
MAP = ('field', 'direction', 'project')
FIELDS = ('literature', 'connection', 'missing_step')


def marks(rid):
    return ('<!-- p2p:relation ' + rid + ' -->', '<!-- /p2p:relation ' + rid + ' -->')


def load(root):
    path = root / REGISTER
    if path.is_symlink():
        raise ValueError('Relation register must not be a symlink.')
    if not path.is_file():
        return {'schema_version': 1, 'relations': {}}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('relations'), dict):
        raise ValueError('Unrecognized ' + REGISTER)
    return data


def save(root, data):
    path = root / REGISTER
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.p2p-tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temp, path)


def block_lines(core, p, vault, root, relation, other, language, titles):
    loc = core.i18n.locale(language, p)
    colon = '：' if language.startswith('zh') else ':'
    text = relation['text'][language]
    link = lambda rel: core.wikilink(vault, root / rel, titles.get(rel) or Path(rel).stem)
    lines = ['**' + link(other) + '**  ']
    lines += ['**' + loc['labels'][key] + colon + '** ' + ' '.join(text[key].split()) + '  ' for key in FIELDS]
    lines.append('**' + loc['labels']['sources'] + colon + '** ' + ', '.join(link(x) for x in relation['papers']))
    return lines


def validate(core, root, p, relation):
    rid = relation.get('id')
    if not isinstance(rid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', rid):
        raise ValueError('Each relation needs an id of letters, digits, ".", "_" or "-".')
    kinds = {}
    for key in ('a', 'b'):
        path = core.inside(root, relation.get(key, ''), 'Relation endpoint')
        if not path.is_file():
            raise ValueError('Relation endpoint does not exist: ' + str(relation.get(key)))
        kinds[key] = core.role(core.raw_text(path), path, root)
    kind = relation.get('kind', 'research')
    allowed = MAP if kind == 'research' else ('concept',) if kind == 'concept' else ()
    if not allowed or any(k not in allowed for k in kinds.values()) or relation['a'] == relation['b']:
        raise ValueError(rid + ': a research relation joins two field/direction/project notes; a concept relation joins two concepts.')
    papers = relation.get('papers')
    if not isinstance(papers, list) or not papers:
        raise ValueError(rid + ': name at least one supporting paper note; a relation without sources is not recorded.')
    for paper in papers:
        path = core.inside(root, paper, 'Supporting paper')
        if not path.is_file() or core.role(core.raw_text(path), path, root) != 'paper':
            raise ValueError(rid + ': supporting source is not a #paper note: ' + paper)
    text = relation.get('text')
    for language in p['note_languages']:
        values = (text or {}).get(language)
        if not isinstance(values, dict) or not all(isinstance(values.get(k), str) and values[k].strip() for k in FIELDS):
            raise ValueError(rid + ': supply literature, connection and missing_step text for ' + language + '.')


def relate(core, root, p, items, apply):
    vault = core.vault_base(root, p['vault_prefix'])
    register = load(root)
    for relation in items:
        validate(core, root, p, relation)
    titles = {}
    plan, before = {}, {}
    for relation in items:
        for rel in [relation['a'], relation['b'], *relation['papers']]:
            path = root / rel
            titles[rel] = core.note_title(core.raw_text(path), path)
    for relation in items:
        for here, other in ((relation['a'], relation['b']), (relation['b'], relation['a'])):
            path = root / here
            text = plan.get(path, core.raw_text(path))
            before.setdefault(path, core.raw_text(path))
            front, body = core.split_front(text)
            languages = core.note_languages(front, body, p, core.role(text, path, root))
            contents = [block_lines(core, p, vault, root, relation, other, lang, titles) for lang in languages]
            plan[path] = core.put_managed(text, contents, marks(relation['id']))
        register['relations'][relation['id']] = {k: relation[k] for k in ('a', 'b', 'papers', 'text')} | {'kind': relation.get('kind', 'research')}
    changes = {k: v for k, v in plan.items() if v != before[k]}
    result = {'status': 'preview', 'relations': [x['id'] for x in items],
              'notes': sorted(x.relative_to(root).as_posix() for x in changes)}
    if apply:
        core.write_texts(changes, before)
        save(root, register)
        result['status'] = 'related'
    return result


def structural(core, root, p, a, b, kinds):
    """field↔direction of the same discipline/field; direction↔project home inside it."""
    layout = p['layout']
    ra, rb = a.relative_to(root.resolve()).parts, b.relative_to(root.resolve()).parts
    for x, rx, y, ry in ((a, ra, b, rb), (b, rb, a, ra)):
        if kinds.get(x) == 'field' and kinds.get(y) == 'direction' and rx[1:3] == ry[1:3]:
            return True
        if kinds.get(x) == 'direction' and kinds.get(y) == 'project' and y.parent.parent == x.parent:
            return True
    return False


def audit(core, root, p, kinds, edges):
    """kinds: resolved path -> role. edges: (resolved source, resolved target)."""
    errors, warnings = [], []
    try:
        register = load(root)
    except (ValueError, OSError) as exc:
        return [str(exc)], [], {}
    base = root.resolve()
    registered = set()
    for rid, relation in sorted(register['relations'].items()):
        ends = [root / relation.get('a', ''), root / relation.get('b', '')]
        if not all(x.is_file() for x in ends):
            errors.append('Registered relation endpoint is missing: ' + rid)
            continue
        registered.add(frozenset(x.resolve() for x in ends))
        for here, other in ((ends[0], relation['b']), (ends[1], relation['a'])):
            text = core.raw_text(here).replace('\r\n', '\n')
            pattern = re.escape(marks(rid)[0]) + r'(.*?)' + re.escape(marks(rid)[1])
            body = core.split_front(text)[1]
            blocks = re.split(r'^---\s*$', body, flags=re.M)
            found = [re.search(pattern, b, re.S) for b in blocks]
            if not all(found):
                errors.append('Registered relation is missing from a language block: ' + rid + ' / ' + here.relative_to(root).as_posix())
                continue
            front = core.split_front(text)[0]
            languages = core.note_languages(front, body, p, core.role(text, here, root))
            for language, m in zip(languages, found):
                wanted = relation['text'].get(language)
                inside = ' '.join(m[1].split())
                if not wanted or any(' '.join(wanted[k].split()) not in inside for k in FIELDS):
                    errors.append('Relation text differs from its register entry: ' + rid + ' / ' +
                                  here.relative_to(root).as_posix() + ' (' + language + ')')
            for target in [other, *relation['papers']]:
                stem = (target[:-3] if target.endswith('.md') else target)
                if not all(stem in m[1] for m in found):
                    errors.append('Relation block lost a link: ' + rid + ' → ' + target)
    seen = set()
    for source, target in edges:
        pair = frozenset((source, target))
        if source == target or pair in seen:
            continue
        seen.add(pair)
        ka, kb = kinds.get(source), kinds.get(target)
        research = ka in MAP and kb in MAP
        concepts = ka == 'concept' and kb == 'concept'
        if (research or concepts) and pair not in registered and not structural(core, root, p, source, target, kinds):
            names = ' ↔ '.join(sorted(x.relative_to(base).as_posix() for x in pair))
            warnings.append('Unregistered research connection (record its evidence with relate, or remove the link): ' + names)
    return errors, warnings, {'registered_relations': len(register['relations'])}
