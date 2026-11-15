#!/usr/bin/env python3
"""Paper2Project local setup, validation and inert retrieval handoff. No network."""

import argparse
import hashlib
import uuid
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

# ASCII-only POSIX hosts decode non-ASCII paths with surrogate escapes. Restart
# the file-based CLI in UTF-8 mode before paths enter note content or JSON.
# Preserve the caller's interpreter flags, including -S (no site packages).
if __name__ == '__main__' and sys.getfilesystemencoding().lower() in ('ascii', 'ansi_x3.4-1968'):
    original_argv = list(sys.orig_argv)
    original_argv[0] = sys.executable
    script_index = original_argv.index(sys.argv[0], 1)
    original_argv[script_index:script_index] = ['-X', 'utf8']
    os.execv(sys.executable, original_argv)

import profiles
import i18n
import discovery

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")
from urllib.parse import unquote, urlparse

PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = '.paper2project.json'
TAGS = {'field': 'research-field', 'direction': 'research-direction',
        'project': 'research-project', 'paper': 'paper', 'concept': 'concept'}
GROUPS = {'Problem', 'Methods', 'Results', 'Extensions'}
KINDS = tuple(TAGS) + ('project-record',)
PAPER_SECTIONS = (
    ('Research question', 'Setup and assumptions', 'Method', 'Results and evidence',
     'Argument chain', 'Relation to our work'),
    ('研究问题', '设定与基本假设', '方法', '结果与证据', '论证链路', '与我们工作的关系'),
)


class InputError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def load_profile(path=None):
    return profiles.load(path)


def profile_at(root):
    if (root / CONFIG).is_symlink():
        raise InputError('Workspace profile must not be a symlink.')
    return load_profile(root / CONFIG if (root / CONFIG).exists() else None)


def no_symlink_root(root):
    root = root.expanduser().absolute()
    if any(p.is_symlink() for p in [root, *root.parents]):
        raise InputError('Choose a real directory path, without symlinked ancestors.')
    return root


def vault_base(root, prefix):
    parts = PurePosixPath(prefix).parts if prefix else ()
    if parts and tuple(root.parts[-len(parts):]) != parts:
        raise InputError('Root does not end with the configured vault_prefix.')
    return root.parents[len(parts)-1] if parts else root


def regular_files(root):
    if not root.exists():
        return []
    found = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(directory)/d).is_symlink())
        for name in sorted(files):
            p = Path(directory) / name
            if not name.startswith('.') and not p.is_symlink():
                found.append(p)
    return found


def markdown_files(root):
    return [p for p in regular_files(root) if p.suffix.lower() == '.md']


def split_front(text):
    opening = re.match(r'\A---\r?\n', text)
    if opening:
        start = opening.end()
        end = re.search(r'^---[ \t]*\r?$', text[start:], re.M)
        if end:
            stop = start + end.end()
            return text[start:start+end.start()], text[stop:].lstrip('\r\n')
    return '', text


def scalar(front, key):
    m = re.search(r'^' + re.escape(key) + r':\s*(.*?)\s*$', front, re.M)
    if not m:
        return None
    return m[1].strip().strip('"\'') or None


def visible_text(text):
    """Strip fences and inline code, retaining line positions for headings."""
    lines, fence = [], None
    for line in text.splitlines(keepends=True):
        mark = re.match(r'^\s*(`{3,}|~{3,})', line)
        if mark:
            token = mark[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            lines.append('\n' if line.endswith('\n') else '')
        elif fence:
            lines.append('\n' if line.endswith('\n') else '')
        else:
            lines.append(re.sub(r'`+[^`]*`+', '', line))
    return ''.join(lines)


def front_tags(front):
    """Tags declared in YAML frontmatter (`tags:`/`tag:`), as Obsidian reads them."""
    found = []
    lines = front.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r'^(?:tags|tag)\s*:\s*(.*?)\s*$', line)
        if not m:
            continue
        value = m[1]
        if value:
            found += re.split(r'[,\s]+', value.strip('[]'))
        else:
            for item in lines[i+1:]:
                entry = re.match(r'^\s+-\s*(.+?)\s*$', item)
                if not entry:
                    break
                found.append(entry[1])
    return {x.strip('\'"').lstrip('#') for x in found if x.strip('\'"').lstrip('#')}


def note_tags(text):
    """Frontmatter tags plus body tags outside code, matching Obsidian's `tag:` search."""
    front, body = split_front(text)
    tags = front_tags(front)
    tags.update(re.findall(r'(?:(?<=\s)|^)#([\w/-]*[^\W\d][\w/-]*)', visible_text(body), re.M))
    return {x.casefold() for x in tags}


def role_kinds(tags):
    # Obsidian's tag:#paper also matches nested tags such as #paper/selected.
    return [k for k, tag in TAGS.items() if any(t == tag or t.startswith(tag + '/') for t in tags)]


def role(text, path, root):
    # Adopt existing tags (tag-only lines, inline or frontmatter) without rewriting notes;
    # an extra organizational tag such as #selected does not become a second role.
    kinds = role_kinds(note_tags(text))
    if len(kinds) > 1:
        return 'multiple'
    if kinds:
        return kinds[0]
    rel = path.relative_to(root).parts
    if len(rel) >= 7 and rel[0] in layout_values(profile_at(root),'projects') and rel[5] in group_values(profile_at(root)):
        return 'project-record'
    return None


def links(text):
    body = visible_text(split_front(text)[1])
    out = []
    for m in re.finditer(r'(?<!!)\[\[([^\]\n]+)\]\]', body):
        # Inside Markdown tables Obsidian requires the alias pipe escaped as `\|`.
        destination, _, label = m[1].partition('|')
        destination = destination[:-1] if destination.endswith('\\') else destination
        target, _, anchor = destination.partition('#')
        out.append({'target': target, 'anchor': anchor, 'label': label or None, 'format': 'wiki'})
    # Conventional local Markdown links; remote URLs are handled as citations.
    pattern = r'''(?<!!)\[([^\]\n]*)\]\((<[^>\n]+>|[^\s)]+)(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'|\([^\)\n]*\)))?[ \t]*\)'''
    for m in re.finditer(pattern, body):
        raw = m[2].strip('<>')
        if urlparse(raw).scheme or raw.startswith('//'):
            continue
        target, _, anchor = unquote(raw).partition('#')
        out.append({'target': target, 'anchor': anchor, 'label': m[1] or None, 'format': 'markdown'})
    return out


SHORT_LINKS = {}
BASENAMES = {}


def basename_index(vault):
    key = vault.resolve()
    if key not in BASENAMES:
        names = {}
        for path in regular_files(vault):
            name = path.stem if path.suffix.lower() == '.md' else path.name
            names.setdefault(name.casefold(), []).append(path)
        BASENAMES[key] = names
    return BASENAMES[key]


def resolve_link(link, source, vault):
    target = unquote(link['target'])
    if target.startswith('/'):
        raise InputError('Absolute local links are not portable: ' + target)
    if not target:
        p = source
    else:
        p = (vault if link['format'] == 'wiki' else source.parent) / target
        if not p.exists() and p.suffix.lower() != '.md':
            p = Path(str(p) + '.md')
        if not p.exists() and link['format'] == 'wiki' and '/' not in target:
            # Obsidian resolves a bare [[Name]] by file name anywhere in the vault.
            matches = basename_index(vault).get(target.casefold(), [])
            if len(matches) > 1:
                raise InputError('Ambiguous short link (several notes share this name): ' + target)
            if matches:
                SHORT_LINKS[vault.resolve()] = SHORT_LINKS.get(vault.resolve(), 0) + 1
                p = matches[0]
    resolved = p.resolve()
    if not resolved.is_relative_to(vault.resolve()):
        raise InputError('Link escapes the vault: ' + target)
    # Links may reference sources elsewhere in the vault, but not through symlinks.
    if any(x.is_symlink() for x in [p, *p.parents] if x.is_relative_to(vault)):
        raise InputError('Symlinked link target: ' + target)
    return p


def heading_slug(title):
    return re.sub(r'[^\w\s-]', '', title.lower()).strip().replace(' ', '-')


def anchor_exists(path, anchor):
    if not anchor or path.suffix.lower() != '.md':
        return True
    text = visible_text(path.read_text(encoding='utf-8'))
    anchor = unquote(anchor)
    if anchor.startswith('^'):
        return bool(re.search(r'\^' + re.escape(anchor[1:]) + r'\s*$', text, re.M))
    headings = re.findall(r'^#{1,6}\s+(.+?)\s*#*\s*$', text, re.M)
    return anchor in headings or anchor in {heading_slug(h) for h in headings}


def source_value(text):
    front, body = split_front(text)
    explicit = scalar(front, 'source_id')
    if explicit:
        return explicit
    m = re.search(r'^\*\*Paper:\*\*\s*(.+)', body, re.M)
    line = m[1] if m else ''
    url = re.search(r'https?://[^\s<>)]+', line)
    return url[0] if url else line


def source_identity(text):
    value = source_value(text)
    return discovery.source_reference(value)[0] or value.strip('<>').rstrip('/').casefold() or None


def query(prefix, full=False):
    chosen = list(TAGS.values()) if full else [TAGS[x] for x in ('field', 'direction', 'project')]
    clause = '(' + ' OR '.join('tag:#' + t for t in chosen) + ')'
    return ('path:"' + prefix + '/" ' if prefix else '') + clause


VIEW_GROUP = 'Paper2Project'
VIEWS = (('Research Map', False), ('Full Network', True))
# Obsidian's own defaults for a saved graph view; only search and colorGroups are ours.
GRAPH_DISPLAY = {'collapse-filter': False, 'showTags': False, 'showAttachments': False,
                 'hideUnresolved': True, 'showOrphans': True, 'collapse-color-groups': False,
                 'collapse-display': True, 'showArrow': False, 'textFadeMultiplier': 0,
                 'nodeSizeMultiplier': 1, 'lineSizeMultiplier': 1, 'collapse-forces': True,
                 'centerStrength': 0.518713248970312, 'repelStrength': 10, 'linkStrength': 1,
                 'linkDistance': 250, 'scale': 1, 'close': False}


def color_groups(p, full):
    roles = list(TAGS) if full else ['field', 'direction', 'project']
    return [{'query': 'tag:#' + TAGS[r], 'color': {'a': 1, 'rgb': int(p['palette'][r][1:], 16)}} for r in roles]


def walk_bookmarks(items):
    for item in items:
        yield item
        if isinstance(item, dict) and item.get('type') == 'group' and isinstance(item.get('items'), list):
            yield from walk_bookmarks(item['items'])


def plan_views(root, p, now):
    """Merge the two graph views and the reading entry into the vault's bookmarks."""
    vault = vault_base(root, p['vault_prefix'])
    config = vault / '.obsidian'
    if config.is_symlink() or (config / 'bookmarks.json').is_symlink():
        raise InputError('Obsidian configuration must not be a symlink.')
    path = config / 'bookmarks.json'
    raw = path.read_bytes() if path.is_file() else None
    data = json.loads(raw.decode('utf-8')) if raw else {'items': []}
    if (not isinstance(data, dict) or not isinstance(data.get('items'), list)
            or not all(isinstance(x, dict) for x in walk_bookmarks(data['items']))):
        raise InputError('Unrecognized bookmarks.json; left unchanged: ' + str(path))
    wanted = [{'type': 'graph', 'title': title, 'search': query(p['vault_prefix'], full),
               'colorGroups': color_groups(p, full)} for title, full in VIEWS]
    home = ((p['vault_prefix'] + '/') if p['vault_prefix'] else '') + p['layout']['home'] + '.md'
    group = next((x for x in data['items'] if x.get('type') == 'group' and x.get('title') == VIEW_GROUP), None)
    inside = {id(x) for x in walk_bookmarks([group])} if group else set()
    outside = [x for x in walk_bookmarks(data['items']) if id(x) not in inside]
    actions = []
    if group is None:
        group = {'type': 'group', 'ctime': now, 'items': [], 'title': VIEW_GROUP}
        data['items'].append(group)
    for view in wanted:
        same = [x for x in outside if x.get('type') == 'graph' and isinstance(x.get('options'), dict)
                and x['options'].get('search') == view['search']]
        mine = next((x for x in group['items'] if x.get('type') == 'graph' and x.get('title') == view['title']), None)
        if same and mine is None:
            actions.append({'view': view['title'], 'action': 'kept_existing', 'title': same[0].get('title')})
            continue
        if mine is None:
            mine = {'type': 'graph', 'ctime': now, 'title': view['title'], 'options': dict(GRAPH_DISPLAY)}
            group['items'].append(mine)
            actions.append({'view': view['title'], 'action': 'added'})
        else:
            options = mine.setdefault('options', dict(GRAPH_DISPLAY))
            if options.get('search') == view['search'] and options.get('colorGroups') == view['colorGroups']:
                actions.append({'view': view['title'], 'action': 'unchanged'})
                continue
            actions.append({'view': view['title'], 'action': 'updated'})
        # Keep the user's layout/forces; refresh only the scope and role colors.
        mine['options'].update(search=view['search'], colorGroups=view['colorGroups'])
    if (root / (p['layout']['home'] + '.md')).is_file():
        known = [x for x in walk_bookmarks(data['items']) if x.get('type') == 'file' and x.get('path') == home]
        if not known:
            group['items'].append({'type': 'file', 'ctime': now, 'path': home})
            actions.append({'view': home, 'action': 'added'})
    if not group['items']:
        data['items'].remove(group)
    nested = [str(x.relative_to(vault)) for x in [root, *root.parents] if x != vault and x.is_relative_to(vault) and (x / '.obsidian').is_dir()]
    return path, raw, data, actions, nested, wanted


def apply_views(root, p, apply):
    import time
    path, raw, data, actions, nested, wanted = plan_views(root, p, int(time.time() * 1000))
    changed = any(x['action'] in ('added', 'updated') for x in actions)
    result = {'status': 'preview', 'bookmarks': str(path), 'actions': actions,
              'views': {x['title']: x['search'] for x in wanted}}
    if nested:
        result['warning'] = ('Nested Obsidian vault(s) inside this vault: ' + ', '.join(nested) +
                             '. Bookmarks go to the vault that contains vault_prefix; if you open the nested folder as its own vault, set vault_prefix to match it.')
    if not apply or not changed:
        result['status'] = 'unchanged' if apply else 'preview'
        return result
    path.parent.mkdir(exist_ok=True)
    current = path.read_bytes() if path.is_file() else None
    if current != raw:
        raise InputError('bookmarks.json changed while planning; nothing written. Run views again.')
    if raw is not None:
        backup = path.with_name('bookmarks.json.p2p-backup-' + digest(raw)[:12])
        if not backup.exists():
            backup.write_bytes(raw)
        result['backup'] = str(backup)
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    temp = path.with_name('bookmarks.json.p2p-tmp')
    temp.write_bytes(payload)
    os.replace(temp, path)
    if path.read_bytes() != payload:
        raise InputError('bookmarks.json readback failed.')
    result.update(status='written', next='If Obsidian already has this vault open, reopen the vault (or restart Obsidian) to load the bookmarks. If they are missing afterwards, close Obsidian and run views --apply again.')
    return result


def views_command(args):
    root = no_symlink_root(Path(args.root))
    if not (root / CONFIG).is_file():
        raise InputError('Initialize or adopt the selected workspace before creating views.')
    print(dump(apply_views(root, profile_at(root), args.apply)))
    return 0


MANAGED = ('<!-- p2p:index -->', '<!-- /p2p:index -->')
TAG_LINE = r'\s*#[\w/-]+(?:\s+#[\w/-]+)*\s*'


def raw_text(path):
    """Exact file text, keeping CRLF line endings that read_text() would translate."""
    return path.read_bytes().decode('utf-8')


def wikilink(vault, path, label):
    rel = path.relative_to(vault).as_posix()
    rel = rel[:-3] if rel.lower().endswith('.md') else rel
    return '[[' + rel + '|' + (' '.join(re.sub(r'[\[\]|#^]', ' ', label).split()) or path.stem) + ']]'


def note_title(text, path):
    m = re.search(r'^#\s+(.+?)\s*$', visible_text(split_front(text)[1]), re.M)
    return m[1] if m else path.stem


def put_managed(text, contents):
    """Replace, or insert before the closing tag line, one managed block per language block."""
    newline = '\r\n' if '\r\n' in text else '\n'
    text = text.replace('\r\n', '\n')
    body = split_front(text)[1]
    head = text[:len(text) - len(body)]
    seps = list(re.finditer(r'^---[ \t]*$', body, re.M))
    cuts = [0, *[x for m in seps for x in (m.start(), m.end())], len(body)]
    segments = [body[cuts[i]:cuts[i+1]] for i in range(0, len(cuts), 2)]
    pattern = re.escape(MANAGED[0]) + r'.*?' + re.escape(MANAGED[1])
    out = []
    for i, segment in enumerate(segments):
        lines = contents[i] if i < len(contents) else contents[0]
        block = MANAGED[0] + '\n' + '\n'.join(lines) + ('\n' if lines else '') + MANAGED[1]
        if re.search(pattern, segment, re.S):
            segment = re.sub(pattern, lambda _: block, segment, count=1, flags=re.S)
        else:
            stripped = segment.rstrip('\n')
            kept = stripped.split('\n')
            tags = []
            while kept and (not kept[-1].strip() or re.fullmatch(TAG_LINE, kept[-1])):
                line = kept.pop()
                if line.strip():
                    tags.insert(0, line)
            segment = ('\n'.join(kept).rstrip('\n') + '\n\n' + block + ('\n\n' + '\n'.join(tags) if tags else '')
                       + (segment[len(stripped):] or '\n'))
        out.append(segment)
    joined = out[0] + ''.join(body[m.start():m.end()] + out[i+1] for i, m in enumerate(seps))
    return (head + joined).replace('\n', newline)


def generated_note(title, p, contents, tag):
    fields = {'p2p_id': str(uuid.uuid4()), 'p2p_languages': p['note_languages'], 'p2p_generated': True}
    front = '---\n' + ''.join(k + ': ' + json.dumps(v, ensure_ascii=False) + '\n' for k, v in fields.items()) + '---\n\n'
    titles = title if isinstance(title, list) else [title] * len(contents)
    blocks = ['# ' + t + '\n\n' + MANAGED[0] + '\n' + '\n'.join(lines) + '\n' + MANAGED[1] for t, lines in zip(titles, contents)]
    return front + i18n.join_blocks(blocks) + ('\n#' + tag + '\n' if tag else '')


def grouped_lines(p, language, groups):
    """Localized label + link list per group; identical link sets in every language."""
    loc = i18n.locale(language, p)
    colon = '：' if language.startswith('zh') else ':'
    lines = []
    for label, items in groups:
        if items:
            lines += ([''] if lines else []) + ['**' + label(loc) + colon + '**'] + ['- ' + x for x in items]
    return lines


def index_plan(root, p):
    """Navigation links that follow from paths alone: field → papers/concepts/directions,
    direction → project homes, Library → fields, Projects → directions. Returns {path: text}."""
    layout, vault = p['layout'], vault_base(root, p['vault_prefix'])
    texts = {f: raw_text(f) for f in markdown_files(root)}
    kinds = {f: role(t, f, root) for f, t in texts.items()}
    title = lambda f: note_title(texts[f], f)
    fields, directions = {}, {}
    for f, kind in sorted(kinds.items()):
        parts = f.relative_to(root).parts
        area = {'paper': ('library', 'papers'), 'concept': ('library', 'concepts')}.get(kind)
        if area and len(parts) == 5 and parts[0] == layout['library'] and parts[3] == layout[area[1]]:
            fields.setdefault(parts[1:3], {'paper': [], 'concept': [], 'direction': []})[kind].append(f)
        if kind == 'direction' and len(parts) == 5 and parts[0] == layout['projects']:
            fields.setdefault(parts[1:3], {'paper': [], 'concept': [], 'direction': []})['direction'].append(f)
            directions.setdefault(f.parent, [f, []])
        if kind == 'field' and len(parts) == 4 and parts[0] == layout['library'] and f.stem == parts[2]:
            fields.setdefault(parts[1:3], {'paper': [], 'concept': [], 'direction': []})
    for f, kind in sorted(kinds.items()):
        if kind == 'project' and f.parent.parent in directions:
            directions[f.parent.parent][1].append(f)
    plan, base = {}, root

    def languages(f):
        if f not in texts:
            return p['note_languages']
        front, body = split_front(texts[f])
        return note_languages(front, body, p, kinds[f])

    def update(f, groups, kind, heading):
        contents = [grouped_lines(p, lang, groups) for lang in languages(f)]
        if f in texts:
            if kinds[f] != kind or not (any(contents) or MANAGED[0] in texts[f]):
                return  # never rewrite an untagged/other note; never add an empty list
            new = put_managed(texts[f], contents)
            if new != texts[f]:
                plan[f] = new
        elif any(lines for lines in contents):
            plan[f] = generated_note(heading, p, contents, TAGS.get(kind) if kind else None)

    link = lambda f: wikilink(vault, f, title(f) if f in texts else f.stem)
    for (discipline, field), members in sorted(fields.items()):
        index = base / layout['library'] / discipline / field / (field + '.md')
        update(index, [(lambda loc: loc['sections']['papers'], [link(x) for x in members['paper']]),
                       (lambda loc: loc['sections']['related_concepts'], [link(x) for x in members['concept']]),
                       (lambda loc: loc['sections']['opportunities'], [link(x) for x in members['direction']])],
               'field', field)
    for folder, (note, homes) in sorted(directions.items()):
        update(note, [(lambda loc: loc['ui']['projects'], [link(x) for x in homes])], 'direction', note.stem)
    # A project home lists its internal records by typed group (navigation, not graph edges).
    for home in sorted(f for f, kind in kinds.items() if kind == 'project'):
        records = {g: sorted(r for r, kind in kinds.items() if kind == 'project-record' and r.parent == home.parent / name)
                   for g, name in layout['groups'].items()}
        update(home, [((lambda n: lambda loc: n)(layout['groups'][g]), [link(x) for x in records[g]])
                      for g in ('problem', 'methods', 'results', 'extensions')], 'project', home.stem)
    for area, label in (('library', 'library'), ('projects', 'projects')):
        entries = {}
        for (discipline, field), members in fields.items():
            if area == 'library':
                index = base / layout['library'] / discipline / field / (field + '.md')
                if kinds.get(index) == 'field' or index in plan:
                    entries.setdefault(discipline, []).append(index)
            else:
                entries.setdefault(discipline, []).extend(members['direction'])
        groups = [((lambda d: lambda loc: d)(d), [link(x) for x in sorted(entries[d])]) for d in sorted(entries) if entries[d]]
        note = base / layout[area] / (layout[area] + '.md')
        contents = [grouped_lines(p, lang, groups) for lang in languages(note)]
        if note in texts and kinds[note] is None and (groups or MANAGED[0] in texts[note]):
            new = put_managed(texts[note], contents)
            if new != texts[note]:
                plan[note] = new
        elif note not in texts and groups:
            plan[note] = generated_note([i18n.locale(x, p)['ui'][label] for x in p['note_languages']], p, contents, None)
    return plan


def write_texts(plan, before):
    """Write planned texts after confirming nothing changed since planning; read each back."""
    for path in plan:
        if (raw_text(path) if path.exists() else None) != before.get(path):
            raise InputError('Changed while planning; nothing written. Run again: ' + str(path))
    for path, text in plan.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.p2p-tmp')
        with temp.open('w', encoding='utf-8', newline='') as out:
            out.write(text)
        os.replace(temp, path)
        if raw_text(path) != text:
            raise InputError('Readback failed: ' + str(path))


def apply_index(root, p, apply):
    plan = index_plan(root, p)
    before = {x: (raw_text(x) if x.exists() else None) for x in plan}
    changes = [{'path': x.relative_to(root).as_posix(), 'action': 'update' if before[x] is not None else 'create'}
               for x in sorted(plan)]
    if apply:
        write_texts(plan, before)
    return {'status': ('written' if plan else 'unchanged') if apply else 'preview', 'changes': changes}


def index_command(args):
    root = no_symlink_root(Path(args.root))
    if not (root / CONFIG).is_file():
        raise InputError('Initialize or adopt the selected workspace before building indexes.')
    print(dump(apply_index(root, profile_at(root), args.apply)))
    return 0


def inside(root, relative, label):
    path = root / relative
    if Path(relative).is_absolute() or '\\' in relative or not path.resolve().is_relative_to(root.resolve()):
        raise InputError(label + ' must be a root-relative path with forward slashes: ' + relative)
    if any(x.is_symlink() for x in [path, *path.parents] if x.is_relative_to(root)):
        raise InputError(label + ' must not go through a symlink: ' + relative)
    return path


def tag_command(args):
    """Append the role tags the user approved; never rewrites note bodies."""
    root = no_symlink_root(Path(args.root))
    if not (root / CONFIG).is_file():
        raise InputError('Initialize or adopt the selected workspace before tagging notes.')
    p = profile_at(root)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    roles = plan.get('roles') if isinstance(plan, dict) else None
    if not isinstance(roles, dict) or not roles:
        raise InputError('Plan needs {"roles": {"relative/path.md": "paper|concept|field|direction|project"}}.')
    changes, before, rows = {}, {}, []
    for relative, kind in sorted(roles.items()):
        if kind not in TAGS:
            raise InputError('Unknown role for ' + relative + ': ' + str(kind))
        path = inside(root, relative, 'Tag target')
        if not path.is_file() or path.suffix.lower() != '.md':
            raise InputError('Tag target must be an existing Markdown note: ' + relative)
        text = raw_text(path)
        current = role(text, path, root)
        if current == kind:
            rows.append({'path': relative, 'role': kind, 'action': 'unchanged'})
            continue
        if current is not None:
            raise InputError('Note already has role ' + current + ', not ' + kind + '; nothing written: ' + relative)
        newline = '\r\n' if '\r\n' in text else '\n'
        changes[path] = text.rstrip('\r\n') + newline + newline + '#' + TAGS[kind] + newline
        before[path] = text
        rows.append({'path': relative, 'role': kind, 'action': 'tag'})
    result = {'status': 'preview', 'changes': rows}
    if args.apply:
        write_texts(changes, before)
        result.update(status='written' if changes else 'unchanged', navigation=apply_index(root, p, True))
    print(dump(result))
    return 0


def outside_code(text, fn):
    """Apply fn to body text outside fenced and inline code (the same spans links() reads)."""
    body = split_front(text)[1]
    out, fence = [text[:len(text) - len(body)]], None
    for line in body.splitlines(keepends=True):
        mark = re.match(r'^\s*(`{3,}|~{3,})', line)
        if mark:
            token = mark[1]
            fence = token if fence is None else (None if token[0] == fence[0] and len(token) >= len(fence) else fence)
            out.append(line)
        elif fence:
            out.append(line)
        else:
            pieces = re.split(r'(`+[^`]*`+)', line)
            out.append(''.join(x if i % 2 else fn(x) for i, x in enumerate(pieces)))
    return ''.join(out)


def rewrite_links(text, old_source, new_source, vault, moved):
    """Point links at moved files: wiki links become full vault-relative paths, Markdown links stay relative."""
    def find(target, base, wiki):
        p = base / target
        if not p.exists() and p.suffix.lower() != '.md':
            p = Path(str(p) + '.md')
        if not p.exists() and wiki and '/' not in target:
            matches = basename_index(vault).get(target.casefold(), [])
            p = matches[0] if len(matches) == 1 else p
        return p.resolve() if p.exists() else None

    def wiki(m):
        destination, bar, label = m[2].partition('|')
        escaped = destination.endswith('\\')
        target, hashmark, anchor = (destination[:-1] if escaped else destination).partition('#')
        found = find(target, vault, True) if target else None
        if found is None or found not in moved:
            return m[0]
        new = moved[found].relative_to(vault.resolve()).as_posix()
        if not target.lower().endswith('.md') and new.lower().endswith('.md'):
            new = new[:-3]
        return m[1] + '[[' + new + hashmark + anchor + (('\\' if escaped else '') + '|' + label if bar else '') + ']]'

    def markdown(m):
        raw = m[2].strip('<>')
        if urlparse(raw).scheme or raw.startswith('//'):
            return m[0]
        target, hashmark, anchor = unquote(raw).partition('#')
        found = find(target, old_source.parent, False) if target else None
        if found is None or (found not in moved and old_source.resolve() == new_source.resolve()):
            return m[0]
        new = Path(os.path.relpath(moved.get(found, found), new_source.resolve().parent)).as_posix()
        if not target.lower().endswith('.md') and new.lower().endswith('.md'):
            new = new[:-3]
        encoded = '<' + new + hashmark + anchor + '>' if m[2].startswith('<') else new.replace(' ', '%20').replace('(', '%28').replace(')', '%29') + hashmark + anchor
        return m[0][:m.start(2) - m.start()] + encoded + m[0][m.end(2) - m.start():]

    md_pattern = r'''(?<!!)\[([^\]\n]*)\]\((<[^>\n]+>|[^\s)]+)(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'|\([^\)\n]*\)))?[ \t]*\)'''
    return outside_code(text, lambda s: re.sub(md_pattern, markdown, re.sub(r'(!?)\[\[([^\]\n]+)\]\]', wiki, s)))


def migrate_command(args):
    """Move notes by an explicit map, rewrite every link to them, keep before-copies and the path map."""
    root = no_symlink_root(Path(args.root))
    if not (root / CONFIG).is_file():
        raise InputError('Initialize or adopt the selected workspace before migrating.')
    p = profile_at(root)
    vault = vault_base(root, p['vault_prefix'])
    data = json.loads(Path(args.map).read_text(encoding='utf-8'))
    moves = data.get('moves') if isinstance(data, dict) else None
    if not isinstance(moves, dict) or not moves:
        raise InputError('Map needs {"moves": {"old/relative/path.md": "new/relative/path.md"}}.')
    moved, pairs = {}, []
    for old, new in moves.items():
        if not isinstance(new, str):
            raise InputError('Destination must be a path string: ' + old)
        src, dst = inside(root, old, 'Source'), inside(root, new, 'Destination')
        if not src.is_file() or any(part.startswith('.') for part in Path(old).parts):
            raise InputError('Source must be an existing visible file: ' + old)
        if dst.exists() or dst.resolve() in moved.values():
            raise InputError('Destination exists or is used twice: ' + new)
        if dst.suffix.lower() != src.suffix.lower():
            raise InputError('A move keeps the file extension: ' + old + ' → ' + new)
        for part in Path(new).parts:
            profiles.safe_name(part)
        moved[src.resolve()] = dst.resolve()
        pairs.append((src, dst))
    occupied = {x.resolve() for x in regular_files(root)} - set(moved)
    if any(x in occupied for x in moved.values()):
        raise InputError('A destination collides with an existing file.')
    before, rewritten = {}, {}
    for path in markdown_files(vault):
        text = raw_text(path)
        new_text = rewrite_links(text, path, moved.get(path.resolve(), path.resolve()), vault, moved)
        before[path.resolve()] = text
        if new_text != text:
            rewritten[path.resolve()] = new_text
    rows = [{'from': s.relative_to(root).as_posix(), 'to': d.relative_to(root).as_posix()} for s, d in pairs]
    result = {'status': 'preview', 'moves': rows,
              'links_rewritten_in': sorted(x.relative_to(vault.resolve()).as_posix() for x in rewritten)}
    pointers = [k for k, v in p['context'].items() if isinstance(v, str) and (vault / v).resolve() in moved]
    if pointers:
        result['profile_pointers_to_update'] = pointers
    if not args.apply:
        print(dump(result))
        return 0
    hashes = {x: digest(x.read_bytes()) for x in moved}
    for path, text in before.items():
        if raw_text(path) != text:
            raise InputError('Changed while planning; nothing written. Run again: ' + str(path))
    run = uuid.uuid4().hex[:12]
    record = root / '.maintenance' / 'migrations' / run
    for path in sorted(set(moved) | set(rewritten)):
        copy = record / 'before' / path.relative_to(vault.resolve())
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(path.read_bytes())
    (record / 'map.json').write_text(dump({'moves': {s.relative_to(vault.resolve()).as_posix(): d.relative_to(vault.resolve()).as_posix()
                                                     for s, d in moved.items()}, 'source_sha256': {s.relative_to(vault.resolve()).as_posix(): h for s, h in hashes.items()},
                                           'links_rewritten_in': result['links_rewritten_in']}) + '\n', encoding='utf-8')
    write_texts({x: t for x, t in rewritten.items() if x not in moved}, before)
    for src, dst in moved.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src in rewritten:
            with dst.open('x', encoding='utf-8', newline='') as out:
                out.write(rewritten[src])
            if raw_text(dst) != rewritten[src]:
                raise InputError('Readback failed: ' + str(dst))
            src.unlink()
        else:
            os.replace(src, dst)
        folder = src.parent
        while folder != root.resolve() and folder.is_relative_to(root.resolve()) and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    BASENAMES.clear()
    result.update(status='migrated', record=str(record), navigation=apply_index(root, p, True))
    print(dump(result))
    return 0


RULES = ('<!-- p2p:rules -->', '<!-- /p2p:rules -->')


def rules_file():
    """Workspace rules inside markers: upgrades refresh only the marked part, user text around it stays."""
    return RULES[0] + '\n' + (PACKAGE/'assets/workspace-rules.md').read_text(encoding='utf-8').strip() + '\n' + RULES[1] + '\n'


def upgrade_rules(text):
    """Return (new_text, action) for an existing AGENTS.md."""
    fresh = rules_file()
    if RULES[0] in text and RULES[1] in text:
        start, end = text.index(RULES[0]), text.index(RULES[1]) + len(RULES[1])
        return text[:start] + fresh.rstrip('\n') + text[end:], 'refreshed'
    normalized = hashlib.sha256(text.replace('\r\n', '\n').encode('utf-8')).hexdigest()
    manifest = json.loads((PACKAGE/'MANIFEST.json').read_text(encoding='utf-8'))
    if normalized in manifest['files'].get('assets/workspace-rules.md', []):
        return fresh, 'replaced_shipped_copy'
    return text.rstrip('\r\n') + '\n\n' + fresh, 'appended_kept_custom'


def upgrade_command(args):
    """Bring a workspace up to this skill version; never touches user content outside p2p markers."""
    root = no_symlink_root(Path(args.root))
    path = root / CONFIG
    if not path.is_file():
        raise InputError('Initialize or adopt the selected workspace before upgrading it.')
    old_raw = path.read_bytes()
    saved = json.loads(old_raw.decode('utf-8'))
    p = profiles.normalize(saved)
    result = {'status': 'preview', 'profile': 'unchanged', 'rules': 'unchanged'}
    new_profile = dump(p) + '\n'
    if json.loads(new_profile) != saved:
        result['profile'] = 'normalized (new defaults added; your keys and extension settings kept)'
    agents = root / 'AGENTS.md'
    old_rules = raw_text(agents) if agents.is_file() else None
    new_rules, action = upgrade_rules(old_rules) if old_rules is not None else (rules_file(), 'created')
    if new_rules != old_rules:
        result['rules'] = action
    if args.apply:
        if result['profile'] != 'unchanged':
            result['profile_backup'] = profiles.save_update(path, p, digest(old_raw))['backup']
        if result['rules'] != 'unchanged':
            write_texts({agents: new_rules}, {agents: old_rules})
        result.update(status='upgraded', views=apply_views(root, profile_at(root), True),
                      navigation=apply_index(root, profile_at(root), True))
    print(dump(result))
    return 0


def obsidian_vaults(root):
    return [x for x in [root, *root.parents] if (x / '.obsidian').is_dir()]


def with_vault_prefix(root, p, supplied, vault):
    """Derive vault_prefix from where the Obsidian vault actually is, never from a guess."""
    if vault:
        base = no_symlink_root(Path(vault))
        if root != base and not root.is_relative_to(base):
            raise InputError('--vault must be the academic root or one of its parent folders.')
        prefix = root.relative_to(base).as_posix() if root != base else ''
        if 'vault_prefix' in supplied and supplied['vault_prefix'].strip('/') != prefix:
            raise InputError('Profile vault_prefix differs from --vault: ' + supplied['vault_prefix'] + ' / ' + prefix)
    elif 'vault_prefix' in supplied:
        prefix = p['vault_prefix']
    else:
        found = obsidian_vaults(root)
        if len(found) > 1:
            raise InputError('Several Obsidian vaults contain this folder: ' + ', '.join(str(x) for x in found) +
                             '. Pass --vault with the one you open in Obsidian.')
        prefix = root.relative_to(found[0]).as_posix() if found and found[0] != root else ''
    p = profiles.normalize({**p, 'vault_prefix': prefix})
    vault_base(root, p['vault_prefix'])
    return p


def init_workspace(args):
    root = no_symlink_root(Path(args.root))
    p = load_profile(args.profile)
    supplied = json.loads(Path(args.profile).read_text(encoding='utf-8')) if args.profile else {}
    if not profiles.inert_extensions(supplied):
        raise InputError('Onboarding never switches extensions on; configure them later in the workspace profile.')
    if (root/CONFIG).exists():
        print(dump({'status':'already_initialized','root':str(root),'written':[]}));return 0
    if args.adopt:
        return adopt_workspace(args,root,p)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise InputError('Target is nonempty. Use init --adopt for an existing workspace; init never migrates or overwrites.')
    if not args.non_interactive:
        if not sys.stdin.isatty():
            raise InputError('No terminal. Supply --profile ... --non-interactive, or invoke the skill for onboarding.')
        def ask(label,default):
            return input(label+(' ['+default+']' if default else '')+': ').strip() or default
        for key,label in [('research_scope','Research scope'),('current_aim','Immediate aim')]:
            if not p[key].strip():p[key]=ask(label,p[key])
        if not any(k in supplied for k in ('language','note_languages')):
            p['note_languages']=[x.strip() for x in ask('Note language tags in order (comma separated)',','.join(p['note_languages'])).split(',')]
            p.pop('language',None)
        p=profiles.normalize(p)
    p=with_vault_prefix(root,p,supplied,args.vault)
    for origin in p['preference_sources'].values():origin['scope']='workspace'
    planned=i18n.scaffold(p)
    # Agent rules reference the live profile; changing language/color preferences
    # does not leave duplicated literal rules stale.
    planned['AGENTS.md']=rules_file()
    planned[CONFIG]=dump(p)+'\n'
    if not args.apply:
        print(dump({'status':'design_only','root':str(root),'profile':p,'planned_files':list(planned),'planned_views':None if args.no_views else {t:query(p['vault_prefix'],f) for t,f in VIEWS},'next':'Add --apply to create this fresh workspace and its Obsidian views.'}));return 0
    if root.exists() and any(root.iterdir()):raise InputError('Target changed during onboarding; no files written.')
    root.mkdir(parents=True,exist_ok=True)
    for relative,content in planned.items():
        dest=root/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('x',encoding='utf-8',newline='') as out:out.write(content)
    result={'status':'created','root':str(root),'written':list(planned)}
    if not args.no_views:result['views']=apply_views(root,p,True)
    print(dump(result));return 0


def adopt_workspace(args,root,p):
    """Register an existing workspace: add only the profile (and rules if absent), then views."""
    if not root.is_dir():raise InputError('Adoption needs an existing workspace folder.')
    supplied=json.loads(Path(args.profile).read_text(encoding='utf-8')) if args.profile else {}
    p=with_vault_prefix(root,p,supplied,args.vault)
    for origin in p['preference_sources'].values():origin['scope']='workspace'
    planned={CONFIG:dump(p)+'\n'}
    if not (root/'AGENTS.md').exists():planned['AGENTS.md']=rules_file()
    files=markdown_files(root);untagged=[x for x in files if role(x.read_text(encoding='utf-8'),x,root) is None and x.name!='AGENTS.md']
    result={'status':'adoption_design','root':str(root),'planned_files':list(planned),'existing_notes':len(files),
            'notes_without_graph_role':len(untagged),'sample_untagged':[x.relative_to(root).as_posix() for x in untagged[:20]],
            'planned_views':None if args.no_views else {t:query(p['vault_prefix'],f) for t,f in VIEWS},
            'next':'Add --apply to register the workspace and create its Obsidian views. Existing notes are not changed; propose role tags, field indexes and supported links next (see onboarding).'}
    if not args.apply:print(dump(result));return 0
    for relative,content in planned.items():
        with (root/relative).open('x',encoding='utf-8',newline='') as out:out.write(content)
    result.update(status='adopted',written=list(planned))
    if not args.no_views:result['views']=apply_views(root,p,True)
    print(dump(result));return 0


def validate_profile_values(p):
    result=profiles.normalize(p);p.clear();p.update(result)


def layout_values(p,key):
    return {x[key] for x in [p['layout'],*p.get('previous_layouts',[])]}


def group_values(p):
    return {v for x in [p['layout'],*p.get('previous_layouts',[])] for v in x['groups'].values()}


def note_languages(front,body,p,kind):
    declared=scalar(front,'p2p_languages')
    if declared:
        values=json.loads(declared)
        if not isinstance(values,list) or not values or not all(isinstance(x,str) for x in values):raise InputError('Invalid p2p_languages metadata.')
        for language in values:i18n.locale(language,p)
        return values
    blocks=re.split(r'^---\s*$',body,flags=re.M)
    # Old notes have no language metadata. Recognize actual section labels first.
    packs=json.loads((PACKAGE/'assets/locales.json').read_text(encoding='utf-8'));packs.update(p['locale_overrides'])
    keys=i18n.SPECS.get(kind,((),()))[1]
    detected=[]
    for block in blocks:
        scores={code:sum(bool(re.search(r'^##\s+'+re.escape(pack['sections'].get(k,pack['ui'].get(k,k)))+r'\s*$',block,re.M)) for k in keys) for code,pack in packs.items()}
        best=max(scores.values(),default=0)
        choices=[k for k,v in scores.items() if v==best and v>0]
        detected.append(choices[0] if len(choices)==1 else None)
    if all(detected):return detected
    # A stored prior layout/language is retained for old untagged notes.
    for languages in [*reversed(p.get('previous_note_languages',[])),p['note_languages']]:
        if len(languages)==len(blocks):return languages
    return p['note_languages']


def link_key(link,source,vault):
    try:target=resolve_link(link,source,vault)
    except InputError:return (link['target'],link['anchor'])
    anchor=unquote(link['anchor']);key=(str(target.resolve()),anchor)
    if not anchor or anchor.startswith('^') or not target.is_file() or target.suffix.lower()!='.md':return key
    body=visible_text(split_front(target.read_text(encoding='utf-8'))[1])
    blocks=re.split(r'^---\s*$',body,flags=re.M)
    headings=[re.findall(r'^(#{1,6})\s+(.+?)\s*#*\s*$',block,re.M) for block in blocks]
    if len(headings)<2 or not headings[0] or any([len(a[0]) for a in x]!=[len(a[0]) for a in headings[0]] for x in headings[1:]):return key
    matches={i for group in headings for i,(_,title) in enumerate(group) if anchor in (title,heading_slug(title))}
    return (key[0],('paired-heading',matches.pop())) if len(matches)==1 else key


def inspect_workspace(args):
    root = no_symlink_root(Path(args.root))
    if root.exists() and not root.is_dir():
        raise InputError('Workspace root must be a directory.')
    files = markdown_files(root)
    result = {'root': str(root), 'exists': root.exists(), 'initialized': (root/CONFIG).is_file(),
              'markdown_files': len(files), 'sample_paths': [str(x.relative_to(root)) for x in files[:20]],
              'note': 'Filename inventory only. Hidden paths and symlinks excluded; source bodies were not ingested.'}
    print(dump(result))
    return 0


def check_workspace(args):
    root=no_symlink_root(Path(args.root))
    if not root.is_dir():raise InputError('Workspace root does not exist.')
    p=profile_at(root);vault=vault_base(root,p['vault_prefix'])
    errors,warnings,ids,sources,titles,counts,homes=[],[],{},{},{},{},[]
    directions={};files=markdown_files(root)
    registered={(x['discipline'],x['field'],x['direction']) for x in p['taxonomy']}
    library=layout_values(p,'library');projects=layout_values(p,'projects')
    papers=layout_values(p,'papers');concepts=layout_values(p,'concepts');groups=group_values(p)
    kinds,edges={},[]
    for path in files:
        text=path.read_text(encoding='utf-8');front,body=split_front(text);parts=path.relative_to(root).parts;rel=path.relative_to(root).as_posix();kind=role(text,path,root)
        kinds[path.resolve()]=kind
        note_id=scalar(front,'p2p_id')
        if note_id:
            if note_id in ids:errors.append('Duplicate p2p_id: '+rel+' / '+ids[note_id])
            ids[note_id]=rel
        if kind:counts[kind]=counts.get(kind,0)+1
        if kind=='multiple':errors.append('Multiple graph roles: '+rel)
        if parts[0] in library and any(x in papers for x in parts[:-1]) and kind!='paper':errors.append('Paper-folder note needs its paper role: '+rel)
        if parts[0] in library and any(x in concepts for x in parts[:-1]) and kind!='concept':errors.append('Concept-folder note needs its concept role: '+rel)
        if kind in ('paper','concept'):
            folders=papers if kind=='paper' else concepts
            if parts[0] not in library or len(parts)!=5 or parts[-2] not in folders:errors.append('Knowledge note outside Library/<Discipline>/<Field> role folders: '+rel)
        if kind=='field':
            if parts[0] not in library or len(parts)!=4:errors.append('Field outside Library/<Discipline>/<Field>: '+rel)
            if path.stem!=path.parent.name:errors.append('Field entry name must reuse its canonical directory name: '+rel)
        if kind=='direction':
            if parts[0] not in projects or len(parts)!=5:errors.append('Direction outside Projects/<Discipline>/<Field>/<Direction>: '+rel)
            else:
                allowed={path.parent.name}|{path.parent.name+' - '+x for x in layout_values(p,'direction_suffix')}
                if path.stem not in allowed:errors.append('Direction entry name must reuse its canonical directory name: '+rel)
                if path.parent in directions:errors.append('Duplicate direction entries: '+rel+' / '+directions[path.parent])
                directions[path.parent]=rel
                if tuple(parts[1:4]) not in registered:warnings.append('Direction has no registered naming basis: '+'/'.join(parts[1:4]))
        if kind=='project':
            homes.append(path)
            if parts[0] not in projects or len(parts)!=6 or path.stem!=path.parent.name:errors.append('Project home must match its canonical project directory: '+rel)
            for sibling in path.parent.iterdir():
                if sibling.is_dir() and sibling.name not in groups:errors.append('Untyped project folder: '+str(sibling.relative_to(root)))
                elif sibling!=path and sibling.is_file():errors.append('Loose file beside project home: '+str(sibling.relative_to(root)))
        languages=note_languages(front,body,p,kind) if kind else []
        blocks=re.split(r'^---\s*$',body,flags=re.M)
        if kind and (len(blocks)!=len(languages) or any(not x.strip() for x in blocks)):errors.append('Missing declared language blocks: '+rel)
        if kind=='paper':
            prefix,separator,title=path.stem.partition(' - ');subfield=scalar(front,'p2p_subfield') or prefix
            if p['preferences']['filename_style'] in (None,'subfield-title'):
                if not separator or not prefix.strip() or not title.strip():errors.append('Paper filename needs <Recognized subfield> - <Short title>: '+rel)
                elif scalar(front,'p2p_subfield') and prefix!=subfield:errors.append('Filename prefix differs from p2p_subfield: '+rel)
            elif not scalar(front,'p2p_subfield') and not separator:warnings.append('Custom paper name needs p2p_subfield for classification checks: '+rel)
            if len(parts)>=3:
                approved={d for a,b,d in registered if a==parts[1] and b==parts[2]}
                if approved and subfield not in approved:errors.append('Paper prefix differs from registered direction names: '+rel)
                elif not approved:warnings.append('Paper prefix has no registered naming basis: '+subfield+' / '+rel)
            for index,language in enumerate(languages):
                loc=i18n.locale(language,p);block=visible_text(blocks[index]) if index<len(blocks) else ''
                for key in i18n.SECTIONS[:6]:
                    label=loc['sections'][key]
                    if not re.search(r'^##\s+'+re.escape(label)+r'\s*$',block,re.M|re.I):errors.append('Paper section missing: '+label+' / '+rel)
                for key in ('paper','reading_scope'):
                    label=loc['labels'][key]
                    # Version 1 bilingual notes stored shared metadata only in block one.
                    if index and not scalar(front,'p2p_languages'):continue
                    if not re.search(r'^\*\*'+re.escape(label)+r'[:：]\*\*\s*\S',block,re.M):errors.append('Paper metadata missing: '+label+' / '+rel)
            identity=source_identity(text)
            if not identity:warnings.append('No recognizable primary source identity: '+rel)
            elif identity in sources:errors.append('Duplicate paper source: '+rel+' / '+sources[identity])
            else:sources[identity]=rel
            heading=re.search(r'^#\s+(.+?)\s*$',visible_text(body),re.M)
            if heading:
                key=' '.join(heading[1].casefold().split())
                if key in titles:errors.append('Duplicate paper title: '+rel+' / '+titles[key])
                titles[key]=rel
        if kind and len(blocks)>1:
            signatures=[{link_key(x,path,vault) for x in links(block)} for block in blocks]
            if any(x!=signatures[0] for x in signatures[1:]):errors.append('Different bilingual link sets / multilingual link sets: '+rel)
            if re.search(r'^#{1,6}\s+(English|中文)\s*$',body,re.M):errors.append('Unnecessary language label: '+rel)
        for link in links(text):
            try:
                target=resolve_link(link,path,vault)
                if not target.exists():errors.append('Missing link: '+rel+' → '+link['target'])
                elif not anchor_exists(target,link['anchor']):errors.append('Missing anchor: '+rel+' → '+link['target']+'#'+link['anchor'])
                else:edges.append((path.resolve(),target.resolve()))
            except InputError as exc:errors.append(rel+': '+str(exc))
    extra,tally=graph_warnings(root,p,files,kinds,edges,counts);warnings+=extra
    navigation=navigation_status(root,p,tally,warnings)
    if SHORT_LINKS.get(vault.resolve()):warnings.append(str(SHORT_LINKS[vault.resolve()])+' wikilinks resolve by file name only; full vault-relative paths survive moves (migrate rewrites them).')
    for path in files:
        parts=path.relative_to(root).parts
        if parts[0] not in projects or len(parts)<6:continue
        home_dir=root.joinpath(*parts[:5]);expected=home_dir/(home_dir.name+'.md')
        if expected not in homes:errors.append('Project records lack a unique tagged home: '+str(path.relative_to(root)))
        if len(parts)>6 and parts[5] not in groups:errors.append('Record outside the four project groups: '+str(path.relative_to(root)))
    for name in projects:
        for raw in regular_files(root/name):
            if raw.suffix.lower()=='.pdf':warnings.append('PDF in Projects needs provenance review; source papers stay in Library/original archive, own result artifacts need evidence: '+str(raw.relative_to(root)))
    report={'status':'failed' if errors else ('needs_review' if warnings else 'passed'),'structural_status':'failed' if errors else 'passed','navigation':navigation,'files':len(files),'roles':counts,'errors':sorted(set(errors)),'warnings':sorted(set(warnings)),
            'scope':'Structure, naming, locale-aware section/metadata presence, IDs/source duplicates, links/anchors and declared language shape. Not translation quality, source support or scientific verification.'}
    print(dump(report));return 1 if errors else 0


SCAFFOLD_FILES = {'AGENTS.md'}


def exempt_paths(root, p):
    """Profile-declared management/task pointers may live inside the root."""
    vault = vault_base(root, p['vault_prefix'])
    return [(vault / v).resolve() for k, v in p['context'].items()
            if k in ('management_entry', 'maintenance_entry', 'task_template', 'maintenance_directory') and v]


def graph_warnings(root, p, files, kinds, edges, counts):
    """Warnings for the fixed structure and for what the native graph views will show."""
    warnings, tally = [], dict.fromkeys(('untagged', 'unconnected', 'missing_field_indexes', 'outside_structure'), 0)
    if not (root/CONFIG).is_file():
        warnings.append('Workspace is not initialized or adopted (no '+CONFIG+'); checks used package defaults. Run init (empty folder) or init --adopt (existing notes).')
    library, projects = layout_values(p, 'library'), layout_values(p, 'projects')
    homes = {x['home'] + '.md' for x in [p['layout'], *p.get('previous_layouts', [])]} | SCAFFOLD_FILES
    exempt = exempt_paths(root, p)
    content = 0
    for path in files:
        rel, resolved = path.relative_to(root), path.resolve()
        parts, kind = rel.parts, kinds.get(resolved)
        if any(resolved == x or resolved.is_relative_to(x) for x in exempt) or (len(parts) == 1 and parts[0] in homes):
            continue
        if not (len(parts) > 1 and parts[0] in library | projects and path.stem == path.parent.name and len(parts) <= 3):
            content += 1  # Library/Projects and discipline indexes are navigation scaffolding
        if parts[0] not in library | projects or len(parts) == 1:
            tally['outside_structure'] += 1
            warnings.append('Outside the Paper2Project structure (move it under Library/Projects with migrate, or keep it outside the academic root): '+rel.as_posix())
        elif not kind and path.stem != path.parent.name:
            tally['untagged'] += 1
            warnings.append('Untagged note inside the structure (assign its role with tag, or move it): '+rel.as_posix())
    if content and not counts:
        warnings.append(str(content)+' Markdown notes but no graph-role tags (#paper, #concept, #research-field, #research-direction, #research-project); Research Map and Full Network will be empty.')
    nodes = {x for x, k in kinds.items() if k in TAGS}
    linked = set()
    for source, target in edges:
        if source != target and source in nodes and target in nodes:
            linked.update((source, target))
    folders = layout_values(p, 'papers') | layout_values(p, 'concepts')
    for path in files:
        kind = kinds.get(path.resolve())
        if kind not in ('paper', 'concept'):
            continue
        rel = path.relative_to(root)
        if path.resolve() not in linked:
            tally['unconnected'] += 1
            warnings.append('Unconnected '+kind+' in Full Network (no links to or from another role note; run index --apply, then link supported concepts): '+rel.as_posix())
        parts = rel.parts
        if len(parts) == 5 and parts[0] in library and parts[3] in folders:
            index = root.joinpath(*parts[:3], parts[2]+'.md')
            if kinds.get(index.resolve()) != 'field':
                tally['missing_field_indexes'] += 1
                warnings.append('Field index missing or untagged (#research-field; index --apply creates it): '+index.relative_to(root).as_posix())
    return warnings, tally


def navigation_status(root, p, tally, warnings):
    """One deterministic answer to 'is the workspace navigable yet?'."""
    views = 'missing'
    if (root/CONFIG).is_file():
        try:
            actions = plan_views(root, p, 0)[3]
            graph = [x for x in actions if x['view'] in dict(VIEWS)]
            views = 'present' if all(x['action'] in ('unchanged', 'kept_existing') for x in graph) else 'missing'
        except (InputError, ValueError) as exc:
            views = 'unreadable'
            warnings.append('Obsidian bookmarks could not be read: ' + str(exc))
        if views == 'missing':
            warnings.append('Research Map / Full Network bookmarks are missing or outdated; run views --apply.')
    status = {'initialized': (root/CONFIG).is_file(), 'views': views, **tally}
    status['status'] = 'complete' if status['initialized'] and views == 'present' and not any(tally.values()) else 'incomplete'
    return status


def sections(text):
    raw = text.splitlines()
    visible = visible_text(text).splitlines()
    starts = [(i, re.sub(r'\s+#+\s*$', '', m[1])) for i, line in enumerate(visible)
              if (m := re.match(r'^#{1,6}\s+(.+?)\s*$', line))]
    if not starts:
        starts = [(0, '')]
    elif starts[0][0] > 0:
        # Frontmatter is metadata; include meaningful pre-heading body only.
        preamble = '\n'.join(raw[:starts[0][0]])
        if split_front(preamble)[1].strip():
            starts.insert(0, (0, ''))
    result = []
    for n, (start, heading) in enumerate(starts):
        end = starts[n+1][0] if n+1 < len(starts) else len(raw)
        passage = '\n'.join(raw[start:end])
        result.append({'heading': heading, 'anchor': heading, 'start_line': start+1,
                       'end_line': end, 'text': passage, 'text_sha256': digest(passage.encode())})
    return result


def export_workspace(args):
    root = no_symlink_root(Path(args.root))
    if not root.is_dir():
        raise InputError('Workspace root does not exist.')
    p = profile_at(root)
    vault = vault_base(root, p['vault_prefix'])
    selected = sorted(set(args.kind or KINDS))
    documents = []
    seen = set()
    for path in markdown_files(root):
        data = path.read_bytes()
        text = data.decode('utf-8')
        kind = role(text, path, root)
        if kind == 'multiple':
            raise InputError('Ambiguous graph roles; fix before exporting a complete snapshot: ' + str(path.relative_to(root)))
        if kind not in selected:
            continue
        front, body = split_front(text)
        relative = path.relative_to(vault).as_posix()
        supplied_id = scalar(front, 'p2p_id')
        note_id = supplied_id or 'path:' + relative
        if note_id in seen:
            raise InputError('Duplicate exported note ID: ' + note_id)
        seen.add(note_id)
        title_match = re.search(r'^#\s+(.+?)\s*$', body, re.M)
        documents.append({'record_type': 'document', 'id': note_id,
            'id_origin': 'metadata' if supplied_id else 'path', 'path': relative, 'kind': kind,
            'title': title_match[1] if title_match else path.stem,
            'content_sha256': digest(data),
            'source_urls': sorted(set(re.findall(r'https?://[^\s<>\])]+', visible_text(body)))),
            'links': links(text), 'sections': sections(text)})
    seed = {'scope': {'vault_prefix': p['vault_prefix'], 'kinds': selected},
            'versions': [(d['id'], d['content_sha256']) for d in documents]}
    header = {'record_type': 'snapshot', 'schema_version': 1,
              'snapshot_id': digest(json.dumps(seed, sort_keys=True).encode()),
              'scope': seed['scope'], 'document_count': len(documents),
              'completeness': 'Complete for the declared selected Markdown kinds only; replace derived records only in this scope.'}
    output = '\n'.join(json.dumps(x, ensure_ascii=False) for x in [header, *documents]) + '\n'
    if args.output == '-':
        sys.stdout.write(output)
    else:
        dest = Path(args.output).expanduser()
        if dest.exists() or dest.is_symlink():
            raise InputError('Output exists; choose a new snapshot path.')
        if dest.suffix.lower() != '.jsonl':
            raise InputError('Output must be a .jsonl file, or - for stdout.')
        with dest.open('x', encoding='utf-8') as out:
            out.write(output)
        print(dump({'status': 'exported', 'documents': len(documents), 'output': str(dest), 'network_calls': 0}))
    return 0


def preferences_command(args):
    root=no_symlink_root(Path(args.root));path=root/CONFIG
    if path.is_symlink():raise InputError('Workspace profile must not be a symlink.')
    saved=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    signals=json.loads(Path(args.signals).read_text(encoding='utf-8')) if args.signals else {}
    profile,ignored=profiles.resolve(saved,signals,args.scope)
    before=digest(path.read_bytes()) if path.exists() else None
    result={'status':'preview','scope':args.scope,'profile':profile,'ignored_signals':ignored,
            'expected_sha256':before,'note':'Only normalized preferences were supplied; no host memory was fetched. Existing notes are not rewritten.'}
    if not args.apply:print(dump(result));return 0
    if args.output:
        dest=Path(args.output).expanduser().absolute();no_symlink_root(dest.parent)
        if dest==path or dest.exists() or dest.is_symlink():raise InputError('Choose a new profile snapshot path outside the live configuration.')
        with dest.open('x',encoding='utf-8',newline='') as out:out.write(dump(profile)+'\n')
        result.update(status='profile_snapshot_saved',output=str(dest))
    elif args.scope=='task':
        raise InputError('Task overrides are read-only; use preview or an explicit --output snapshot.')
    elif not path.exists():
        raise InputError('For first use, save --output profile.json --apply, then init --profile profile.json.')
    else:
        if not args.expect_sha:raise InputError('Persistent updates need --expect-sha from the preview.')
        result.update(profiles.save_update(path,profile,args.expect_sha));result['status']='preferences_saved'
    print(dump(result));return 0


def render_command(args):
    root=no_symlink_root(Path(args.root))
    if not (root/CONFIG).is_file():raise InputError('Initialize or adopt the selected workspace before rendering notes.')
    profile=load_profile(args.profile) if args.profile else profile_at(root)
    saved=profile_at(root)
    for code in profile['note_languages']:
        # A durable note needs a durable custom pack, even for task-only language.
        i18n.locale(code,saved)
    card=json.loads(Path(args.input).read_text(encoding='utf-8'))
    dest=Path(args.output) if args.output else derived_path(args.kind,card,saved)
    if not dest.is_absolute():dest=root/dest
    no_symlink_root(dest.parent)
    if not dest.resolve().is_relative_to(root.resolve()) or dest.suffix.lower()!='.md':raise InputError('Note destination must be a Markdown file inside the selected root.')
    replacing=None
    if dest.exists() or dest.is_symlink():
        old=dest.read_text(encoding='utf-8') if dest.is_file() and not dest.is_symlink() else ''
        # Only a program-generated field index may be replaced by the real field note; it keeps its ID.
        if not (args.kind=='field' and scalar(split_front(old)[0],'p2p_generated')=='true' and role(old,dest,root)=='field'):
            raise InputError('Note exists; render never replaces a canonical note.')
        replacing=old;card['id']=scalar(split_front(old)[0],'p2p_id') or card.get('id')
    if not card.get('id'):card['id']=str(uuid.uuid4())
    text=i18n.render(args.kind,card,profile)
    identity=source_identity(text) if args.kind=='paper' else None
    for path in markdown_files(root):
        if replacing is not None and path.resolve()==dest.resolve():continue
        old=path.read_text(encoding='utf-8');front,_=split_front(old)
        if scalar(front,'p2p_id')==card['id']:raise InputError('Stable note ID already exists: '+str(path.relative_to(root)))
        if identity and role(old,path,root)=='paper' and source_identity(old)==identity:raise InputError('Paper source already has a canonical note: '+str(path.relative_to(root)))
    result={'status':'preview','path':str(dest),'id':card['id'],'languages':profile['note_languages'],'markdown':text}
    if args.apply:
        dest.parent.mkdir(parents=True,exist_ok=True)
        if replacing is None:
            with dest.open('x',encoding='utf-8',newline='') as out:out.write(text)
        else:write_texts({dest:text},{dest:replacing})
        if dest.read_text(encoding='utf-8')!=text:raise InputError('Note readback failed.')
        result={'status':'rendered','path':str(dest),'id':card['id'],'languages':profile['note_languages'],'content_sha256':digest(text.encode('utf-8'))}
        # Path-derived navigation (field/direction/Library indexes) is written by the program, not the agent.
        result['navigation']=apply_index(root,saved,True)
    print(dump(result));return 0


def derived_path(kind,card,p):
    """Canonical location from the card's classification; the structure is fixed, names are the user's."""
    layout=p['layout']
    def name(key,fallback=None):
        value=card.get(key) or (card.get(fallback) if fallback else None)
        if not isinstance(value,str):raise InputError('Supply "'+key+'" in the card (or --output) to place this '+kind+'.')
        try:profiles.safe_name(value)
        except ValueError as exc:raise InputError(str(exc)+' (card key "'+key+'")')
        return value
    discipline,field=name('discipline'),name('field')
    library,projects=Path(layout['library'],discipline,field),Path(layout['projects'],discipline,field)
    if kind=='paper':
        if p['preferences']['filename_style'] not in (None,'subfield-title'):raise InputError('Custom filename_style: pass --output.')
        return library/layout['papers']/(name('subfield')+' - '+name('short_title','title')+'.md')
    if kind=='concept':return library/layout['concepts']/(name('short_title','title')+'.md')
    if kind=='field':return library/(field+'.md')
    direction=name('direction','title' if kind=='direction' else None)
    if kind=='direction':return projects/direction/(direction+'.md')
    if kind=='project':
        title=name('short_title','title');return projects/direction/title/(title+'.md')
    group=card.get('group')
    if group not in layout['groups']:raise InputError('project-record cards need "group": problem, methods, results or extensions.')
    return projects/direction/name('project')/layout['groups'][group]/(name('short_title','title')+'.md')


def locales_command(args):
    packs=json.loads((PACKAGE/'assets/locales.json').read_text(encoding='utf-8'))
    result={'bundled_locales':{code:value['name'] for code,value in packs.items()},'custom':'Complete locale_overrides packs support additional language tags; no English substitution.'}
    if args.template:
        template={'name':'','sections':dict.fromkeys(i18n.SECTIONS,''),'labels':dict.fromkeys(i18n.LABELS,''),'ui':dict.fromkeys(i18n.UI,'')}
        result={'locale_overrides':{args.template:template},'reference_labels':packs['en'],'next':'Have the host LLM fill the labels in the requested language, then validate/save the pack before rendering.'}
    print(dump(result));return 0



def discovery_snapshot(root, profile):
    vault = vault_base(root, profile['vault_prefix'])
    papers, projects, directions = [], {}, {x['direction'] for x in profile['taxonomy']}
    note_hashes = {}
    for area in ('library', 'projects'):
        for folder in sorted(set(layout_values(profile, area))):
            base = root / folder
            if base.is_symlink():
                raise InputError('Discovery does not follow a symlinked role folder.')
            for path in markdown_files(base):
                text = path.read_text(encoding='utf-8')
                kind = role(text, path, root)
                rel = path.relative_to(root).as_posix()
                body = visible_text(split_front(text)[1])
                title_match = re.search(r'^#\s+(.+?)\s*$', body, re.M)
                title = title_match[1] if title_match else path.stem
                if area == 'projects' and kind == 'direction':
                    directions.add(path.parent.name)
                elif area == 'projects' and kind == 'project':
                    projects[rel] = title
                    note_hashes[rel] = digest(text.encode('utf-8'))
                elif area == 'library' and kind == 'paper':
                    note_hashes[rel] = digest(text.encode('utf-8'))
                    key, version = discovery.source_reference(source_value(text))
                    pdfs = set()
                    for link in links(text):
                        if not link['target'].lower().endswith('.pdf'):
                            continue
                        pdf = resolve_link(link, path, vault)
                        if pdf.is_file():
                            pdfs.add(pdf.resolve().relative_to(vault.resolve()).as_posix())
                    papers.append({'title': title, 'path': rel, 'keys': [key] if key else [],
                                   'versions': [version] if version else [], 'pdfs': sorted(pdfs)})
    return {'papers': papers, 'projects': projects, 'directions': sorted(directions), 'note_hashes': note_hashes}


def read_discovery_packet(path):
    raw = Path(path).read_bytes()
    packet = json.loads(raw)
    if not isinstance(packet, dict) or packet.get('schema_version') != 1:
        raise InputError('Expected a discovery review packet.')
    for key in ('materials', 'connections'):
        rows = packet.get(key)
        if not isinstance(rows, dict) or not all(isinstance(row, dict) for row in rows.values()):
            raise InputError(f'Invalid packet {key} records.')
    return raw, packet


def discovery_command(args):
    root = no_symlink_root(Path(args.root))
    if not root.is_dir():
        raise InputError('Workspace root does not exist.')
    profile = profile_at(root)
    snapshot = discovery_snapshot(root, profile)
    catalog_hash = digest(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode('utf-8'))
    if args.command == 'review-discovery':
        raw, packet = read_discovery_packet(args.packet)
        decisions = json.loads(Path(args.decisions).read_bytes())
        plan = discovery.review(packet, decisions, digest(raw), catalog_hash)
        print(dump({'status': 'review_plan', **plan}))
        return 0

    data = json.loads(Path(args.input).read_bytes())
    prior = [read_discovery_packet(path)[1] for path in dict.fromkeys(args.prior)]
    if not args.stage:
        print(dump({'status': 'inventory', 'items': discovery.inventory(data, snapshot, prior)}))
        return 0

    language = data.get('language', profile['response_language'])
    if language == 'auto':
        raise InputError('Supply the response language for this task when the profile uses auto.')
    rows, markdown, packet = discovery.build(data, snapshot, prior, language, catalog_hash)
    result = {'status': 'no_new_candidates', 'language': language, 'items': rows, 'markdown': markdown}
    if packet['materials'] or packet['connections']:
        dest = no_symlink_root(Path(args.stage))
        if dest.suffix.lower() != '.json' or dest == root / CONFIG:
            raise InputError('Choose a new JSON path for the review packet.')
        if dest.is_relative_to(root) and dest.relative_to(root).parts[0] in (
                layout_values(profile, 'library') | layout_values(profile, 'projects')):
            raise InputError('Keep review packets outside the Library and Projects.')
        payload = (dump(packet) + '\n').encode('utf-8')
        with dest.open('xb') as out:
            out.write(payload)
        if dest.read_bytes() != payload:
            raise InputError('Review packet readback failed.')
        result.update(status='staged', packet=str(dest), packet_sha256=digest(payload))
    print(dump(result))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'init', 'check', 'export'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--root', required=True, help='Academic workspace root; does not scan parent directories.')
        if name == 'init':
            cmd.add_argument('--profile', help='Selected JSON preferences; unspecified values use defaults.')
            cmd.add_argument('--non-interactive', action='store_true')
            cmd.add_argument('--apply', action='store_true', help='Create only within a fresh empty target.')
            cmd.add_argument('--adopt', action='store_true', help='Register an existing workspace; adds only the profile and missing rules.')
            cmd.add_argument('--no-views', action='store_true', help='Skip the Obsidian Research Map/Full Network bookmarks.')
            cmd.add_argument('--vault', help='Obsidian vault folder containing the root; detected when only one encloses it.')
        if name == 'export':
            cmd.add_argument('--kind', action='append', choices=KINDS, help='Repeat to restrict the snapshot; default all managed kinds.')
            cmd.add_argument('--output', required=True, help='New local .jsonl path, or - for stdout.')
    cmd=sub.add_parser('preferences',help='Resolve supplied context/memory signals and preview or save preferences.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--signals')
    cmd.add_argument('--scope',choices=('task','workspace'),default='task')
    cmd.add_argument('--apply',action='store_true');cmd.add_argument('--expect-sha');cmd.add_argument('--output')
    cmd=sub.add_parser('render',help='Render supplied source-grounded content with localized templates.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--kind',choices=tuple(i18n.SPECS),required=True)
    cmd.add_argument('--input',required=True);cmd.add_argument('--output',help='Optional; derived from the card classification when omitted.');cmd.add_argument('--profile');cmd.add_argument('--apply',action='store_true')
    cmd=sub.add_parser('discover',help='Inventory sources or stage a discovery review packet.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--input',required=True)
    cmd.add_argument('--prior',action='append',default=[]);cmd.add_argument('--stage',metavar='PACKET')
    cmd=sub.add_parser('review-discovery',help='Validate separate choices for material and connections.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--packet',required=True);cmd.add_argument('--decisions',required=True)
    cmd=sub.add_parser('upgrade',help='Preview or bring a workspace up to this skill version (profile defaults, marked rules, views, indexes).')
    cmd.add_argument('--root',required=True);cmd.add_argument('--apply',action='store_true')
    cmd=sub.add_parser('views',help='Preview or merge the Research Map/Full Network graph bookmarks into the Obsidian vault.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--apply',action='store_true')
    cmd=sub.add_parser('index',help='Preview or write the path-derived field/direction/Library/Projects link lists.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--apply',action='store_true')
    cmd=sub.add_parser('tag',help='Preview or append approved graph-role tags from a {"roles": {path: role}} plan.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--plan',required=True);cmd.add_argument('--apply',action='store_true')
    cmd=sub.add_parser('migrate',help='Preview or move notes by a {"moves": {old: new}} map, rewriting links vault-wide.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--map',required=True);cmd.add_argument('--apply',action='store_true')
    cmd=sub.add_parser('locales');cmd.add_argument('--template')
    args = parser.parse_args(argv)
    try:
        return {'inspect': inspect_workspace, 'init': init_workspace,
                'check': check_workspace, 'export': export_workspace,
                'preferences':preferences_command,'render':render_command,'locales':locales_command,'views':views_command,'index':index_command,'tag':tag_command,'migrate':migrate_command,'upgrade':upgrade_command,
                'discover':discovery_command,'review-discovery':discovery_command}[args.command](args)
    except (ValueError, OSError, TypeError, KeyError, UnicodeError) as ex:
        print(dump({'status': 'error', 'message': str(ex)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
