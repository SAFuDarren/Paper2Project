"""Deterministic discovery intake and review. No network or workspace writes."""

import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

LABEL_KEYS = (
    'academic', 'industry', 'new', 'pending', 'library', 'verify', 'overview',
    'field', 'status', 'question', 'method', 'contribution', 'project', 'potential',
    'problem', 'implementation', 'impact', 'value', 'source', 'registered', 'proposed',
    'version', 'identity', 'candidate', 'application_field',
)
FULL_FIELDS = ('overview', 'field', 'question', 'method', 'conditions', 'contribution', 'connection', 'potential')


def source_reference(value):
    """Separate a work identity from an explicit source version."""
    if not isinstance(value, str) or not value.strip():
        return None, None
    raw = unquote(value.strip().strip('<>'))
    path = urlsplit(raw)
    host = (path.hostname or '').casefold()
    if host in {'arxiv.org', 'www.arxiv.org', 'export.arxiv.org'}:
        raw = re.sub(r'^/(?:abs|html|pdf)/', '', path.path).removesuffix('.pdf')
    elif host in {'doi.org', 'dx.doi.org'}:
        raw = path.path.lstrip('/')
    else:
        publisher_doi = re.search(r'/(?:doi(?:/abs|/full|/pdf)?|article|abstract)/(10\.\d{4,9}/[^/?#]+)$',
                                  path.path, re.I)
        if publisher_doi:
            raw = publisher_doi[1]
    raw = raw.casefold().removeprefix('doi:').removeprefix('10.48550/arxiv.').removeprefix('arxiv:')
    match = re.fullmatch(r'(\d{4}\.\d{4,5}|[a-z][a-z.\-]*/\d{7})(v[1-9]\d*)?', raw)
    if match:
        work = 'arxiv:' + match[1]
        return work, work + match[2] if match[2] else None
    if re.fullmatch(r'10\.\d{4,9}/[^\s<>]+', raw):
        work = 'doi:' + raw
        return work, work
    if path.scheme in {'http', 'https'} and host:
        return 'url:' + host + path.path.rstrip('/') + ('?' + path.query if path.query else ''), None
    return None, None


def title_key(title):
    return ''.join(c for c in unicodedata.normalize('NFKC', title).casefold() if c.isalnum())


def line(item, key):
    value = item.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.splitlines()) != 1 or value.endswith(('\r', '\n')):
        raise ValueError(f"{item.get('id', 'Item')}: supply single-line {key}.")
    return value.strip()


def source_keys(item):
    if item['lane'] == 'industry':
        return {'case:' + line(item, 'case_key').casefold()}, set()
    ids = item.get('identifiers', [])
    if not isinstance(ids, list) or not all(isinstance(value, str) for value in ids):
        raise ValueError('identifiers must be a list of source strings.')
    pairs = [source_reference(value) for value in [item.get('source'), *ids]]
    keys = {key for key, _ in pairs if key}
    if len({key for key in keys if not key.startswith('url:')}) > 1:
        line(item, 'identity_evidence')
    versions = {version for _, version in pairs if version}
    for key in keys:
        if len({version for work, version in pairs if work == key and version}) > 1:
            raise ValueError(f"{item['id']}: choose one version of this work per item.")
    return keys, versions


def valid_source(item):
    url = line(item, 'source')
    source = urlsplit(url)
    if source.scheme != 'https' or not source.hostname or source.username or source.password or re.search(r'[\s<>]', url):
        raise ValueError(f"{item['id']}: supply a public HTTPS primary source.")
    line(item, 'locator')
    return url


def cover(item, keys, versions, local, pending):
    exact = [note for note in local if keys.intersection(note['keys'])]
    if len(exact) > 1:
        return 'identity', None
    if exact and (not versions or versions <= set(exact[0]['versions'])):
        return 'library', exact[0]
    prior = [row for row in pending if row['lane'] == item['lane'] and keys.intersection(row['keys'])]
    same = [row for row in prior if not versions or versions <= set(row['versions'])]
    if same:
        return 'pending', same[0]
    if exact or prior:
        return 'version', (exact or prior)[0]
    if not keys or any(title_key(item['title']) == title_key(row['title'])
                       for row in [*local, *pending] if row.get('lane', 'academic') == item['lane']):
        return 'identity', None
    return 'new', None


def inventory(data, snapshot, prior):
    items = data.get('items') if isinstance(data, dict) else None
    if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
        raise ValueError('Supply a nonempty items list.')
    if data.get('project') and data['project'] not in snapshot['projects']:
        raise ValueError('Choose an existing project home from this workspace.')
    pending = [item for packet in prior for item in packet['materials'].values()]
    rows = {}
    seen = []
    for item in items:
        key = line(item, 'id')
        title = line(item, 'title')
        if key in rows:
            raise ValueError(f'Repeated item ID: {key}')
        lane = item.get('lane', 'academic')
        if lane not in {'academic', 'industry'}:
            raise ValueError('Use academic or industry as the lane.')
        item = {**item, 'id': key, 'title': title, 'lane': lane}
        keys, versions = source_keys(item)
        local = snapshot['papers'] if lane == 'academic' else []
        status, match = cover(item, keys, versions, local, pending)
        for prior_keys, prior_versions in seen:
            if keys & prior_keys and (not versions or versions <= prior_versions):
                status, match = 'duplicate', None
                break
        seen.append((keys, versions))
        rows[key] = {**item, 'status': status, 'keys': sorted(keys), 'versions': sorted(versions),
                     'direction_registered': item.get('direction') in snapshot['directions'],
                     'match': match}
    return rows


def labels_for(language, supplied=None):
    if supplied is None:
        packs = json.loads((Path(__file__).resolve().parents[1] / 'assets' / 'discovery-labels.json').read_bytes())
        supplied = packs.get(language)
        if supplied is None and re.fullmatch(r'[a-z]{2,3}-[A-Z]{2}', language):
            supplied = packs.get(language.split('-')[0])
    if not isinstance(supplied, dict) or set(supplied) != set(LABEL_KEYS):
        raise ValueError(f'No complete discovery labels for {language}. Supply labels for this language.')
    for key in LABEL_KEYS:
        line(supplied, key)
    return supplied


def full_text(row, labels, project):
    line(row, 'locator')
    fields = {key: line(row, key) for key in FULL_FIELDS}
    academic = row['lane'] == 'academic'
    field = fields['field'] + (' · ' + line(row, 'publication') if academic else '')
    direction = row.get('direction')
    coverage = labels['registered'] if row['direction_registered'] else labels['proposed']
    if direction:
        coverage += ' · ' + line(row, 'direction')
    status = labels['candidate'] if row['status'] == 'new' else labels[row['status']]
    if row.get('versions'):
        status += ' · ' + ', '.join(row['versions'])
    details = [
        ('field' if academic else 'application_field', field), ('status', coverage + ' / ' + status),
        ('question' if academic else 'problem', fields['question']),
        ('method' if academic else 'implementation', fields['method'] + ' · ' + fields['conditions']),
        ('contribution' if academic else 'impact', fields['contribution']),
        ('project', (project + ' · ' if project else '') + fields['connection']),
        ('potential' if academic else 'value', fields['potential']),
    ]
    return f"**{labels['overview']}**  {fields['overview']}\n\n" + '\n'.join(f'- **{labels[key]}**  {value}' for key, value in details)


def build(data, snapshot, prior, language, catalog_digest):
    labels = labels_for(language, data.get('labels'))
    rows = inventory(data, snapshot, prior)
    project_path = data.get('project')
    project = snapshot['projects'].get(project_path, '')
    materials, connections = {}, {}
    prior_links = {(edge['project'], source_reference(edge['source'])[0], edge['relation'])
                   for previous in prior for edge in previous['connections'].values()}
    rendered = {}
    for key, row in rows.items():
        status = row['status']
        if status in {'duplicate', 'identity'}:
            continue
        brief = status == 'library' or (status == 'pending' and row.get('recap') is True)
        current = row
        if status == 'pending' and row['match'].get('language') == language:
            current = {**row['match'], **row}
        if brief:
            status_text = labels[status]
            if status == 'library':
                note = row['match']
                status_text += ' · ' + note['path']
                if note.get('pdfs'):
                    status_text += ' · ' + ', '.join(note['pdfs'])
            overview = line(current, 'overview')
            connection = (project + ' · ' if project else '') + line(current, 'connection')
            body = (f"**{labels['overview']}**  {overview}\n\n"
                    f"- **{labels['status']}**  {status_text}\n"
                    f"- **{labels['project']}**  {connection}")
        else:
            valid_source(current)
            body = full_text(current, labels, project)
        if not brief or (current.get('source') and current.get('locator')):
            source = valid_source(current)
            body += f"\n- **{labels['source']}**  {line(current, 'locator')} · <{source}>"
        byline = 'authors' if row['lane'] == 'academic' else 'organization'
        title = row['title']
        if not brief or current.get(byline):
            title = line(current, byline) + ' | ' + title
        group = 'new' if status == 'version' else status
        rendered.setdefault((row['lane'], group), []).append(f"#### {title}\n\n{body}")
        if status in {'new', 'version'}:
            materials[key] = {k: v for k, v in row.items() if k != 'match'}
            materials[key]['language'] = language
        if project_path and (key in materials or (status == 'library' and row.get('propose_connection') is True)):
            if status == 'library':
                valid_source(current)
            relation = line(current, 'connection')
            signature = (project_path, source_reference(current['source'])[0], relation)
            if signature not in prior_links:
                connections[key] = {'project': project_path, 'material': key, 'local': status == 'library',
                                    'source': current['source'], 'locator': current['locator'],
                                    'relation': relation, 'potential': line(current, 'potential')}
    markdown = []
    for lane in ('academic', 'industry'):
        groups = [(group, rendered[lane, group]) for group in ('library', 'pending', 'new') if (lane, group) in rendered]
        unresolved = [row for row in rows.values() if row['lane'] == lane and row['status'] == 'identity']
        if groups or unresolved:
            markdown.append('## ' + labels[lane])
        for group, entries in groups:
            markdown.extend(['### ' + labels[group], *entries])
        if unresolved:
            markdown.extend(['### ' + labels['verify'], *[
                '- ' + row['title'] + ' · ' + labels['identity'] for row in unresolved]])
    packet = {'schema_version': 1, 'catalog_sha256': catalog_digest,
              'materials': materials, 'connections': connections}
    return rows, '\n\n'.join(markdown) + ('\n' if markdown else ''), packet


def review(packet, decisions, packet_hash, catalog_hash):
    if packet['catalog_sha256'] != catalog_hash:
        raise ValueError('Workspace source inventory changed. Run discovery again before review.')
    if not isinstance(decisions, dict) or decisions.get('packet_sha256') != packet_hash:
        raise ValueError('Decisions refer to a different packet.')
    line(decisions, 'approval_reference')
    plan = {'packet_sha256': packet_hash, 'approval_reference': decisions['approval_reference']}
    admitted = set()
    for group in ('materials', 'connections'):
        plan[group] = {}
        choices = decisions.get(group, {})
        if not isinstance(choices, dict):
            raise ValueError(f'Use an object for {group} choices.')
        for key, choice in choices.items():
            if choice not in {'approve', 'hold', 'skip'} or key not in packet[group]:
                raise ValueError('Use a packet item ID and an explicit approve, hold or skip.')
            row = packet[group][key]
            if group == 'materials' and choice == 'approve':
                if admitted.intersection(row['keys']):
                    raise ValueError('Choose one source version per work for admission.')
                admitted.update(row['keys'])
            if group == 'connections' and choice == 'approve' and not row['local']:
                if decisions.get('materials', {}).get(row['material']) != 'approve':
                    raise ValueError('Approve the source material separately before approving its connection.')
            plan[group][key] = {'choice': choice, 'item': row}
    return plan
