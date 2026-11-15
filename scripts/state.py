"""Workspace brief, before-snapshots and diffs (read-only except the snapshot folder it creates).

`brief` gathers what an agent must read before working: rules and pointers with hashes, the
profile choices, navigation status, originals, relations and retrieval freshness, and the next
commands. `snapshot` stores exact copies of the workspace notes, rules and registers plus a link
inventory. `diff` compares the workspace with a snapshot so changed meaning and links are reviewed,
not only file counts.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path

REGISTERS = ('.maintenance/pdf_attachments.json', '.maintenance/relations.json')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tracked(core, root, p):
    """root-relative key -> path for notes, rules, profile, registers and the vault bookmarks."""
    files = {x.relative_to(root).as_posix(): x for x in core.markdown_files(root)}
    for name in (core.CONFIG, *REGISTERS):
        if (root / name).is_file():
            files[name] = root / name
    vault = core.vault_base(root, p['vault_prefix'])
    if (vault / '.obsidian/bookmarks.json').is_file():
        files['vault:.obsidian/bookmarks.json'] = vault / '.obsidian/bookmarks.json'
    for key in ('management_entry', 'maintenance_entry', 'task_template'):
        value = p['context'].get(key)
        if value and (vault / value).is_file():
            files.setdefault('vault:' + value, vault / value)
    return files


def links_inventory(core, root):
    result = {}
    for path in core.markdown_files(root):
        text = core.raw_text(path)
        result[path.relative_to(root).as_posix()] = {
            'role': core.role(text, path, root),
            'links': sorted({x['target'] + ('#' + x['anchor'] if x['anchor'] else '') for x in core.links(text)})}
    return result


def run_check(core, root):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        core.check_workspace(type('Args', (), {'root': str(root)})())
    return json.loads(stream.getvalue())


def brief(core, root, p):
    import retrieve  # local module; reading freshness never syncs or calls a model
    check = run_check(core, root)
    vault = core.vault_base(root, p['vault_prefix'])
    pointers = {}
    for key, value in [('rules', 'AGENTS.md'), *[(k, v) for k, v in p['context'].items() if isinstance(v, str) and v]]:
        path = (root / value) if key == 'rules' else (vault / value)
        pointers[key] = {'path': str(path), 'exists': path.is_file(),
                         'sha256': sha(path.read_bytes()) if path.is_file() else None}
    index = root / retrieve.INDEX
    retrieval = {'index': str(index), 'exists': index.is_file()}
    if index.is_file():
        retrieval.update(retrieve.freshness(root, p, retrieve.connect(root))[0])
    nav = check['navigation']
    steps = []
    if nav['views'] != 'present':
        steps.append('python scripts/p2p.py views --root <root> --apply')
    if nav['untagged'] or nav['outside_structure']:
        steps.append('Place notes with migrate and assign roles with tag (see onboarding: adopt, then connect).')
    if nav['unconnected'] or nav['missing_field_indexes']:
        steps.append('python scripts/p2p.py index --root <root> --apply')
    if any('Unregistered research connection' in w for w in check['warnings']):
        steps.append('Record the evidence of each hand-written connection with relate, or remove the link.')
    if retrieval.get('needs_sync') or not index.is_file():
        steps.append('python scripts/retrieve.py sync --root <root>')
    return {'status': 'context_ready', 'root': str(root), 'vault': str(vault), 'read_before_edit': pointers,
            'profile': {'note_languages': p['note_languages'], 'vault_prefix': p['vault_prefix'], 'layout': p['layout'],
                        'taxonomy_entries': len(p['taxonomy']),
                        'extensions_enabled': sorted(k for k, v in p['extensions'].items() if v.get('enabled'))},
            'navigation': nav, 'roles': check['roles'], 'originals': check.get('pdfs'), 'relations': check.get('relations'),
            'structural_status': check['structural_status'], 'errors': len(check['errors']), 'warnings': len(check['warnings']),
            'retrieval': retrieval, 'next': steps or ['Workspace is navigable; continue with the requested reading or project work.']}


def snapshot(core, root, p, out):
    out = Path(out).expanduser().absolute()
    if out.exists():
        raise ValueError('Snapshot destination exists; choose a new folder.')
    for area in core.layout_values(p, 'library') | core.layout_values(p, 'projects'):
        if out.is_relative_to((root / area).absolute()):
            raise ValueError('Keep snapshots outside Library and Projects (for example under .maintenance/).')
    files = tracked(core, root, p)
    digests = {k: sha(v.read_bytes()) for k, v in files.items()}
    inventory = links_inventory(core, root)
    out.mkdir(parents=True)
    stored = {}
    for i, (key, path) in enumerate(sorted(files.items())):
        data = path.read_bytes()
        if sha(data) != digests[key]:
            raise ValueError('A file changed during the snapshot; it is incomplete. Retry on a stable workspace.')
        name = 'data/' + str(i).zfill(5) + path.suffix
        (out / name).parent.mkdir(exist_ok=True)
        (out / name).write_bytes(data)
        stored[key] = name
    manifest = {'schema_version': 1, 'root': str(root), 'files': digests, 'stored': stored, 'inventory': inventory}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'status': 'snapshot_saved', 'directory': str(out), 'files': len(stored)}


def diff(core, root, p, baseline):
    manifest = json.loads((Path(baseline).expanduser() / 'manifest.json').read_text(encoding='utf-8'))
    before = manifest['files']
    now = {k: sha(v.read_bytes()) for k, v in tracked(core, root, p).items()}
    old_inv, new_inv = manifest['inventory'], links_inventory(core, root)
    edges = lambda inv: {(note, target) for note, row in inv.items() for target in row['links']}
    added_links, removed_links = sorted(edges(new_inv) - edges(old_inv)), sorted(edges(old_inv) - edges(new_inv))
    roles = sorted((k, old_inv[k]['role'], new_inv[k]['role']) for k in set(old_inv) & set(new_inv)
                   if old_inv[k]['role'] != new_inv[k]['role'])
    changed = sorted(k for k in set(before) & set(now) if before[k] != now[k])
    result = {'added': sorted(set(now) - set(before)), 'removed': sorted(set(before) - set(now)), 'changed': changed,
              'links_added': [list(x) for x in added_links], 'links_removed': [list(x) for x in removed_links],
              'roles_changed': [list(x) for x in roles],
              'views_changed': 'vault:.obsidian/bookmarks.json' in changed,
              'registers_changed': [k for k in changed if k in REGISTERS or k == core.CONFIG]}
    result['content_review_required'] = bool(result['added'] or result['removed'] or changed or added_links or removed_links)
    result['note'] = 'Review changed meaning and every added/removed link against its sources; a structural pass is not support.'
    return result
