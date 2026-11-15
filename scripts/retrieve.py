#!/usr/bin/env python3
"""Search existing research: notes and registered original PDFs, with exact source locators.

The index is derived and rebuildable (`<root>/.maintenance/retrieval.sqlite`); notes, PDFs and the
PDF register stay primary. Lexical search (BM25 with CJK bigrams) needs nothing else. Semantic
search is used only when the user enabled `extensions.embedding` in the workspace profile with an
`endpoint` and `model` (Ollama `/api/embed` or an OpenAI-compatible `/v1/embeddings`; a key, if
any, is read from the environment variable named by `api_key_env`). Retrieval never writes notes,
links or graph edges; a hit is a pointer to read, not evidence.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2p  # noqa: E402
import pdfs  # noqa: E402

INDEX = '.maintenance/retrieval.sqlite'
CHUNK = 1200
SCHEMA = 1


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def tokens(text):
    text = unicodedata.normalize('NFKC', text).lower()
    found = re.findall(r'[a-z0-9]+', text)
    for word in re.findall(r'[\u3400-\u9fff]+', text):
        if len(word) == 1:
            found.append(word)
        else:
            found.extend(word[i:i + 2] for i in range(len(word) - 1))
    return found


def split(text, limit=CHUNK):
    """Cut text into pieces of at most `limit` characters at paragraph or line boundaries; keep offsets."""
    cursor, out = 0, []
    while cursor < len(text):
        end = min(cursor + limit, len(text))
        if end < len(text):
            cut = text.rfind('\n\n', cursor + limit // 2, end)
            cut = cut if cut >= 0 else text.rfind('\n', cursor + limit // 2, end)
            end = cut + 1 if cut >= 0 else end
        if text[cursor:end].strip():
            out.append((cursor, end))
        cursor = end
    return out


def note_chunks(path, root, text):
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    rows = []
    for section in p2p.sections(text):
        begin, stop = starts[section['start_line'] - 1], starts[section['end_line']]
        body = text[begin:stop]
        for a, b in split(body):
            piece = body[a:b]
            meaningful = re.sub(r'<!--.*?-->|\[\[[^\]]*\]\]|^\s*#[\w/-]+\s*$|^---\s*$', '', piece, flags=re.M | re.S)
            if len(re.sub(r'\W', '', meaningful)) < 8:
                continue
            first = sum(1 for s in starts[1:] if s <= begin + a) + 1
            last = sum(1 for s in starts[1:] if s < begin + b)
            rows.append({'source': 'notes', 'heading': section['heading'], 'start_line': first,
                         'end_line': max(first, last), 'text': piece})
    return rows


def profile_embedding(p):
    slot = p.get('extensions', {}).get('embedding', {})
    if not slot.get('enabled'):
        return None
    if not slot.get('endpoint') or not slot.get('model'):
        raise ValueError('extensions.embedding is enabled but needs "endpoint" and "model".')
    return slot


def embed(slot, inputs):
    """Call the user's configured embedding endpoint; returns one vector per input."""
    endpoint = slot['endpoint'].rstrip('/')
    headers = {'Content-Type': 'application/json'}
    if slot.get('api_key_env'):
        key = os.environ.get(slot['api_key_env'])
        if not key:
            raise ValueError('Environment variable ' + slot['api_key_env'] + ' (api_key_env) is not set.')
        headers['Authorization'] = 'Bearer ' + key
    openai = slot.get('provider') in ('openai', 'openai-compatible') or endpoint.endswith('/v1')
    url = endpoint + ('/embeddings' if openai else '/api/embed')
    vectors = []
    for start in range(0, len(inputs), int(slot.get('batch_size', 16))):
        batch = inputs[start:start + int(slot.get('batch_size', 16))]
        body = json.dumps({'model': slot['model'], 'input': batch}).encode('utf-8')
        request = urllib.request.Request(url, data=body, headers=headers, method='POST')
        with urllib.request.urlopen(request, timeout=float(slot.get('timeout_seconds', 120))) as response:
            data = json.loads(response.read().decode('utf-8'))
        got = [x['embedding'] for x in data['data']] if openai else data['embeddings']
        if len(got) != len(batch):
            raise ValueError('Embedding endpoint returned a different number of vectors.')
        vectors.extend(got)
    dims = {len(v) for v in vectors}
    if len(dims) > 1 or (slot.get('dimensions') and dims != {int(slot['dimensions'])}):
        raise ValueError('Embedding dimensions differ from the configured model: ' + str(sorted(dims)))
    return vectors


def connect(root):
    path = root / INDEX
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)')
    db.execute('''CREATE TABLE IF NOT EXISTS docs(path TEXT PRIMARY KEY, source TEXT, kind TEXT, title TEXT,
                  sha256 TEXT, canonical TEXT, info TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, path TEXT, source TEXT, heading TEXT,
                  page INTEGER, start_line INTEGER, end_line INTEGER, start_offset INTEGER, end_offset INTEGER,
                  text TEXT, tokens TEXT, vector TEXT, visual_check INTEGER)''')
    db.execute('CREATE INDEX IF NOT EXISTS chunk_path ON chunks(path)')
    return db


def current_documents(root, p):
    """What should be indexed now: role notes and project records, plus registered originals."""
    docs = {}
    for path in p2p.markdown_files(root):
        text = p2p.raw_text(path)
        kind = p2p.role(text, path, root)
        if kind and kind != 'multiple':
            rel = path.relative_to(root).as_posix()
            docs[rel] = {'source': 'notes', 'kind': kind, 'title': p2p.note_title(text, path),
                         'sha256': digest(text), 'canonical': rel, 'text': text}
    for note, row in pdfs.load_register(root)['papers'].items():
        for item in row.get('files', []):
            pdf = root / item['path']
            if pdf.is_file() and note in docs:
                docs[item['path']] = {'source': 'pdf', 'kind': 'original', 'title': docs[note]['title'],
                                      'sha256': item['sha256'], 'canonical': note, 'file': pdf}
    return docs


def sync(root, p, rebuild=False):
    slot = profile_embedding(p)
    signature = json.dumps({'schema': SCHEMA, 'chunk': CHUNK, 'model': slot and slot['model'],
                            'dimensions': slot and slot.get('dimensions')}, sort_keys=True)
    db = connect(root)
    old = dict(db.execute('SELECT key, value FROM meta'))
    if rebuild or old.get('signature') != signature:
        db.execute('DELETE FROM chunks'); db.execute('DELETE FROM docs')
    indexed = {row[0]: row[1] for row in db.execute('SELECT path, sha256 FROM docs')}
    docs = current_documents(root, p)
    added, removed, warnings = 0, 0, []
    for path in set(indexed) - set(docs):
        db.execute('DELETE FROM chunks WHERE path=?', (path,)); db.execute('DELETE FROM docs WHERE path=?', (path,))
        removed += 1
    pending = []
    for path, doc in sorted(docs.items()):
        if indexed.get(path) == doc['sha256']:
            continue
        rows = []
        info = {}
        if doc['source'] == 'notes':
            rows = note_chunks(root / path, root, doc['text'])
        else:
            try:
                extracted = pdfs.text_command(p2p, root, doc['file'], 'auto')
            except ValueError as exc:
                warnings.append(path + ': ' + str(exc)[:160])
                continue
            info = {'engine': extracted['engine']}
            for page in extracted['pages']:
                for a, b in split(page['text']):
                    rows.append({'source': 'pdf', 'heading': '', 'page': page['page'], 'start_offset': a,
                                 'end_offset': b, 'text': page['text'][a:b], 'visual_check': page['needs_visual_check']})
        db.execute('DELETE FROM chunks WHERE path=?', (path,))
        db.execute('INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?,?)',
                   (path, doc['source'], doc['kind'], doc['title'], doc['sha256'], doc['canonical'], json.dumps(info)))
        for row in rows:
            cursor = db.execute('INSERT INTO chunks(path, source, heading, page, start_line, end_line, start_offset, '
                                'end_offset, text, tokens, visual_check) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                                (path, row['source'], row.get('heading'), row.get('page'), row.get('start_line'),
                                 row.get('end_line'), row.get('start_offset'), row.get('end_offset'), row['text'],
                                 json.dumps(tokens(doc['title'] + ' ' + row['text'])), int(row.get('visual_check', False))))
            pending.append((cursor.lastrowid, doc['title'] + '\n' + row['text']))
        added += 1
    if slot and pending:
        try:
            vectors = embed(slot, [text for _, text in pending])
        except (OSError, ValueError, KeyError) as exc:
            db.rollback()
            raise ValueError('Embedding failed; the previous index is kept. ' + str(exc)[:200])
        for (chunk_id, _), vector in zip(pending, vectors):
            db.execute('UPDATE chunks SET vector=? WHERE id=?', (json.dumps(vector), chunk_id))
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('signature', signature))
    db.commit()
    total = db.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
    return {'status': 'synced', 'documents_updated': added, 'documents_removed': removed, 'chunks': total,
            'semantic': bool(slot), 'warnings': warnings, 'index': str(root / INDEX)}


def freshness(root, p, db):
    docs = current_documents(root, p)
    indexed = {row[0]: row[1] for row in db.execute('SELECT path, sha256 FROM docs')}
    stale = sorted(path for path, doc in docs.items() if indexed.get(path) != doc['sha256'])
    return {'stale_or_unindexed': stale, 'removed': sorted(set(indexed) - set(docs)), 'needs_sync': bool(stale or set(indexed) - set(docs))}, docs


def search(root, p, query, limit=8, source='all', mode='auto', papers=None, passages=3):
    db = connect(root)
    fresh, docs = freshness(root, p, db)
    stale = set(fresh['stale_or_unindexed'])
    rows = db.execute('SELECT c.id, c.path, c.source, c.heading, c.page, c.start_line, c.end_line, c.start_offset, '
                      'c.end_offset, c.text, c.tokens, c.vector, c.visual_check, d.canonical, d.title, d.kind FROM chunks c '
                      'JOIN docs d ON d.path = c.path').fetchall()
    rows = [r for r in rows if r[1] not in stale and r[1] in docs and (source == 'all' or r[2] == source)
            and (not papers or r[13] in papers)]
    if not rows:
        return {'status': 'no_results', 'query': query, 'freshness': fresh, 'results': []}
    terms = tokens(query)
    docs_tokens = [json.loads(r[10]) for r in rows]
    avg = sum(map(len, docs_tokens)) / len(docs_tokens)
    df = {t: sum(1 for d in docs_tokens if t in d) for t in set(terms)}
    lexical = []
    for d in docs_tokens:
        score = 0.0
        for t in set(terms):
            if df[t]:
                tf = d.count(t)
                idf = math.log(1 + (len(docs_tokens) - df[t] + .5) / (df[t] + .5))
                score += idf * tf * 2.2 / (tf + 1.2 * (.25 + .75 * len(d) / avg))
        lexical.append(score)
    slot = profile_embedding(p)
    use_vectors = mode in ('auto', 'semantic', 'hybrid') and slot and all(r[11] for r in rows)
    if mode == 'semantic' and not use_vectors:
        raise ValueError('Semantic search needs an enabled embedding extension and a synced index.')
    scores = lexical
    if use_vectors:
        q = embed(slot, [query])[0]
        qn = math.sqrt(sum(x * x for x in q)) or 1
        cos = []
        for r in rows:
            v = json.loads(r[11])
            cos.append(sum(a * b for a, b in zip(q, v)) / (qn * (math.sqrt(sum(x * x for x in v)) or 1)))
        top = max(lexical) or 1
        scores = cos if mode == 'semantic' else [.5 * (l / top) + .5 * c for l, c in zip(lexical, cos)]
    ranked = sorted(range(len(rows)), key=lambda i: -scores[i])
    vault = p2p.vault_base(root, p['vault_prefix'])
    grouped = {}
    for i in ranked:
        if scores[i] <= 0:
            break
        r = rows[i]
        entry = grouped.setdefault(r[13], {'canonical_note': r[13], 'title': r[14], 'passages': []})
        if len(entry['passages']) >= passages:
            continue
        locator = {'path': r[1], 'source': r[2]}
        if r[2] == 'notes':
            locator.update(heading=r[3], start_line=r[5], end_line=r[6])
        else:
            link = p2p.wikilink(vault, root / r[1], r[1]).split('|')[0][2:]
            locator.update(page=r[4], start_offset=r[7], end_offset=r[8], open='[[' + link + '#page=' + str(r[4]) + ']]',
                           needs_visual_check=bool(r[12]))
        entry['passages'].append({'score': round(scores[i], 4), 'locator': locator, 'text': r[9]})
    results = list(grouped.values())[:limit]
    return {'status': 'ok', 'query': query, 'mode': 'hybrid' if use_vectors and mode != 'semantic' else ('semantic' if use_vectors else 'lexical'),
            'freshness': fresh, 'results': results, 'evidence_status': 'not_inferred_from_retrieval',
            'note': 'Read the passage and its original before using it; similarity is not support and never becomes a link.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('sync', 'status', 'search', 'page'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--root', required=True)
        if name == 'sync':
            cmd.add_argument('--rebuild', action='store_true')
        if name == 'search':
            cmd.add_argument('query')
            cmd.add_argument('--limit', type=int, default=8)
            cmd.add_argument('--source', choices=('all', 'notes', 'pdf'), default='all')
            cmd.add_argument('--mode', choices=('auto', 'lexical', 'semantic', 'hybrid'), default='auto')
            cmd.add_argument('--paper', action='append', help='Restrict to a paper note (root-relative path); repeatable.')
            cmd.add_argument('--passages', type=int, default=3)
        if name == 'page':
            cmd.add_argument('--pdf', required=True, help='Registered original (root-relative path).')
            cmd.add_argument('--page', type=int, required=True)
    args = parser.parse_args(argv)
    try:
        root = p2p.no_symlink_root(Path(args.root))
        if not (root / p2p.CONFIG).is_file():
            raise ValueError('Initialize or adopt the selected workspace first.')
        p = p2p.profile_at(root)
        if args.command == 'sync':
            result = sync(root, p, args.rebuild)
        elif args.command == 'status':
            db = connect(root)
            result = {'status': 'ok', 'chunks': db.execute('SELECT COUNT(*) FROM chunks').fetchone()[0],
                      'documents': db.execute('SELECT COUNT(*) FROM docs').fetchone()[0],
                      'semantic': bool(profile_embedding(p)), 'freshness': freshness(root, p, db)[0]}
        elif args.command == 'search':
            result = search(root, p, args.query, max(1, min(args.limit, 50)), args.source, args.mode,
                            set(args.paper or []), max(1, min(args.passages, 5)))
        else:
            pdf = p2p.inside(root, args.pdf, 'PDF')
            text = pdfs.text_command(p2p, root, pdf, 'auto', [args.page])
            result = {'status': 'ok', 'pdf': args.pdf, 'engine': text['engine'], 'pages': text['pages']}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
