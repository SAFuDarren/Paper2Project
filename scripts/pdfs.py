"""Original PDFs: scan a folder, read text, attach approved copies to paper notes, audit.

Conventions: an original is either copied byte-for-byte to `Library/<D>/<F>/PDFs/<stem>.pdf`
beside the paper note `Library/<D>/<F>/Papers/<stem>.md` (mode "copy", the default) or linked where
it already is (mode "link"). The user's original files are never moved, renamed, modified or
deleted, and migrate refuses to move PDFs. `.maintenance/pdf_attachments.json` registers each copy with its hashes and provenance.
Every language block of the note links the copy inside a `<!-- p2p:pdf -->` block. PDFs are
sources, not graph nodes. Standard library only; PyMuPDF or `pdftotext` are used when present.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zlib

REGISTER = '.maintenance/pdf_attachments.json'
TEXT_CACHE = '.maintenance/pdf_text'
MARK = ('<!-- p2p:pdf -->', '<!-- /p2p:pdf -->')
DOI = re.compile(rb'\b(10\.\d{4,9}/[^\s"<>()\[\]{}]+)', re.I)
ARXIV_NEW = re.compile(r'(?<![\d.])(\d{4}\.\d{4,5})(v\d+)?(?![\d])')
ARXIV_TEXT = re.compile(rb'arXiv:\s*(\d{4}\.\d{4,5})(v\d+)?', re.I)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# --- minimal PDF object reader (enough for page counts, metadata and simple text) ----------

def _objects(raw):
    """Map object number -> (dictionary bytes, decoded stream or None), including object streams."""
    objects = {}
    for m in re.finditer(rb'(?<![\d])(\d+)\s+(\d+)\s+obj\b', raw):
        start = m.end()
        end = raw.find(b'endobj', start)
        if end < 0:
            continue
        body = raw[start:end]
        objects[int(m[1])] = _split_stream(body)
    for number, (head, data) in list(objects.items()):
        if data is not None and re.search(rb'/Type\s*/ObjStm', head):
            n = re.search(rb'/N\s+(\d+)', head)
            first = re.search(rb'/First\s+(\d+)', head)
            if not n or not first:
                continue
            pairs = data[:int(first[1])].split()
            offsets = [(int(pairs[i]), int(pairs[i + 1])) for i in range(0, min(len(pairs), 2 * int(n[1])) - 1, 2)]
            for i, (obj, offset) in enumerate(offsets):
                begin = int(first[1]) + offset
                stop = int(first[1]) + offsets[i + 1][1] if i + 1 < len(offsets) else len(data)
                objects.setdefault(obj, (data[begin:stop], None))
    return objects


def _split_stream(body):
    m = re.search(rb'stream\r?\n', body)
    if not m:
        return body, None
    head = body[:m.start()]
    if re.search(rb'/Subtype\s*/(Image|Type1C|CIDFontType0C|OpenType)|/Length[123]\s|/FontFile|/ICCBased|/Type\s*/XRef', head):
        return head, None  # images, embedded fonts and colour profiles hold no text or identifiers
    data = body[m.end():]
    data = data[:data.rfind(b'endstream')] if b'endstream' in data else data
    if re.search(rb'/FlateDecode', head):
        try:
            data = zlib.decompressobj().decompress(data)
        except zlib.error:
            return head, None
    elif re.search(rb'/Filter', head):
        return head, None  # other filters (images, LZW, ...) are not text we can read
    return head, data


def _literal(data, i):
    """Read a PDF literal string starting after '('; return (bytes, next index)."""
    out, depth = bytearray(), 1
    while i < len(data) and depth:
        c = data[i]
        if c == 0x5C and i + 1 < len(data):  # backslash
            nxt = data[i + 1]
            table = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12, 0x28: 0x28, 0x29: 0x29, 0x5C: 0x5C}
            if nxt in table:
                out.append(table[nxt]); i += 2
            elif 0x30 <= nxt <= 0x37:
                digits = re.match(rb'[0-7]{1,3}', data[i + 1:i + 4])[0]
                out.append(int(digits, 8) & 0xFF); i += 1 + len(digits)
            else:
                i += 2  # line continuation or unknown escape
            continue
        if c == 0x28:
            depth += 1
        elif c == 0x29:
            depth -= 1
            if not depth:
                return bytes(out), i + 1
        out.append(c); i += 1
    return bytes(out), i


def _decode(text):
    if text.startswith(b'\xfe\xff'):
        return text[2:].decode('utf-16-be', 'replace')
    return text.decode('latin-1')


LIGATURES = str.maketrans({'\x0b': 'ff', '\x0c': 'fi', '\x0d': 'fl', '\x0e': 'ffi', '\x0f': 'ffl'})


def _content_text(stream):
    """Text shown by Tj/TJ/'/" operators, with line breaks at text positioning operators.
    Inside TJ arrays a large negative kerning offset stands for a word space."""
    parts, i, pending, in_array = [], 0, [], False
    while i < len(stream):
        c = stream[i:i + 1]
        if in_array:
            number = re.match(rb'-?\d*\.?\d+', stream[i:])
            if number and stream[i:i + 1] in b'-.0123456789':
                if float(number[0]) < -180 and pending and not pending[-1].endswith(' '):
                    pending.append(' ')
                i += len(number[0])
                continue
            if c == b']':
                in_array = False
                i += 1
                continue
        if c == b'(':
            value, i = _literal(stream, i + 1)
            pending.append(_decode(value))
            continue
        if c == b'<' and stream[i:i + 2] != b'<<':
            end = stream.find(b'>', i)
            hexed = re.sub(rb'\s', b'', stream[i + 1:end])
            try:
                pending.append(_decode(bytes.fromhex((hexed + b'0' * (len(hexed) % 2)).decode('ascii'))))
            except ValueError:
                pass
            i = end + 1
            continue
        m = re.match(rb'(TJ|Tj|\'|"|T\*|Td|TD|Tm|ET)(?![A-Za-z])', stream[i:])
        if m:
            op = m[1]
            if op in (b'TJ', b'Tj', b"'", b'"'):
                if op in (b"'", b'"'):
                    parts.append('\n')
                parts.append(''.join(pending))
            elif parts and not parts[-1].endswith('\n'):
                parts.append('\n')
            pending = [] if op in (b'TJ', b'Tj', b"'", b'"') else pending
            i += len(op)
            continue
        if c == b'[':
            pending, in_array = [], True
        i += 1
    return re.sub(r'[ \t]+\n', '\n', ''.join(parts)).translate(LIGATURES)


def _refs(value):
    return [int(x) for x in re.findall(rb'(\d+)\s+\d+\s+R', value)]


def inspect_pdf(raw):
    """Page count, title, DOI/arXiv identifiers found in the file bytes (metadata or plain text)."""
    if not raw.startswith(b'%PDF-'):
        return {'is_pdf': False}
    objects = _objects(raw)
    pages = [n for n, (head, _) in sorted(objects.items()) if re.search(rb'/Type\s*/Page(?![a-zA-Z])', head)]
    title = None
    m = re.search(rb'/Title\s*\(', raw)
    if m:
        value, _ = _literal(raw, m.end())
        title = _decode(value).strip() or None
    blob = raw + b''.join(d for _, d in objects.values() if d)
    dois = sorted({x.decode('latin-1').rstrip('.,;') for x in DOI.findall(blob)})
    arxiv = sorted({(a + v).decode() if v else a.decode() for a, v in ARXIV_TEXT.findall(blob)})
    return {'is_pdf': True, 'pages': len(pages) or None, 'title': title, 'dois': dois[:5], 'arxiv': arxiv[:5],
            'encrypted': bool(re.search(rb'/Encrypt\b', raw))}


def builtin_pages(raw):
    objects = _objects(raw)
    result = []
    for number, (head, _) in sorted(objects.items()):
        if not re.search(rb'/Type\s*/Page(?![a-zA-Z])', head):
            continue
        contents = re.search(rb'/Contents\s*(\[[^\]]*\]|\d+\s+\d+\s+R)', head)
        text = ''
        for ref in _refs(contents[1]) if contents else []:
            data = objects.get(ref, (b'', None))[1]
            if data is None and ref in objects:  # an array object holding further references
                for inner in _refs(objects[ref][0]):
                    data = (data or b'') + (objects.get(inner, (b'', None))[1] or b'')
            text += _content_text(data or b'')
        result.append(text)
    return result


def extract_text(raw, engine='auto'):
    """Return {'engine', 'pages': [{'page', 'text', 'needs_visual_check'}]} using the best engine available."""
    order = ['pymupdf', 'pdftotext', 'builtin'] if engine == 'auto' else [engine]
    errors = []
    for name in order:
        try:
            if name == 'pymupdf':
                import pymupdf  # optional
                with pymupdf.open(stream=raw, filetype='pdf') as doc:
                    if doc.needs_pass:
                        raise ValueError('Encrypted PDF needs explicit access.')
                    texts = [page.get_text() for page in doc]
                version = getattr(pymupdf, 'VersionBind', 'unknown')
            elif name == 'pdftotext':
                exe = shutil.which('pdftotext')
                if not exe:
                    raise ValueError('pdftotext is not installed.')
                out = subprocess.run([exe, '-enc', 'UTF-8', '-', '-'], input=raw, capture_output=True, timeout=300)
                if out.returncode:
                    raise ValueError(out.stderr.decode('utf-8', 'replace')[:200])
                texts = out.stdout.decode('utf-8', 'replace').split('\f')
                if texts and not texts[-1].strip():
                    texts = texts[:-1]
                version = 'poppler'
            elif name == 'builtin':
                texts = builtin_pages(raw)
                version = '1'
            else:
                raise ValueError('Unknown engine: ' + name)
        except (ImportError, ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            errors.append(name + ': ' + str(exc)[:200])
            continue
        pages = []
        for i, text in enumerate(texts):
            text = text.replace('\0', '�')
            letters = sum(ch.isalnum() for ch in text)
            odd = sum(ch == '�' or (not ch.isprintable() and ch not in '\n\t') for ch in text)
            pages.append({'page': i + 1, 'text': text,
                          'needs_visual_check': not text.strip() or odd > max(3, letters // 20)})
        if name == 'builtin' and (not pages or all(p['needs_visual_check'] for p in pages)):
            errors.append('builtin: no readable text (fonts without a standard encoding, scanned pages or unsupported filters)')
            continue
        return {'engine': name, 'engine_version': version, 'pages': pages,
                'note': 'Selectable text only; no OCR, formula or figure understanding. Check flagged pages against the original.'}
    raise ValueError('No PDF text engine could read this file. Install PyMuPDF (pip install pymupdf) or poppler (pdftotext) '
                     'and retry; meanwhile record the reading scope as metadata only. Details: ' + '; '.join(errors))


# --- workspace integration ------------------------------------------------------------------

def register_path(root):
    return root / REGISTER


def load_register(root):
    path = register_path(root)
    if path.is_symlink():
        raise ValueError('PDF register must not be a symlink.')
    if not path.is_file():
        return {'schema_version': 1, 'papers': {}}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('papers'), dict):
        raise ValueError('Unrecognized ' + REGISTER)
    return data


def save_register(root, data):
    path = register_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.p2p-tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temp, path)


def note_identities(core, root):
    """Paper notes by DOI/arXiv/source identity, for matching scanned PDFs."""
    found = {}
    for path in core.markdown_files(root):
        text = core.raw_text(path)
        if core.role(text, path, root) != 'paper':
            continue
        rel = path.relative_to(root).as_posix()
        value = core.source_value(text) or ''
        for doi in re.findall(r'10\.\d{4,9}/[^\s"<>()\[\]{}]+', value + ' ' + text[:2000]):
            found.setdefault('doi:' + doi.rstrip('.,;').lower(), rel)
        for a in ARXIV_NEW.findall(value):
            found.setdefault('arxiv:' + a[0], rel)
    return found


def scan(core, root, folder):
    """Read-only intake queue for a folder of PDFs."""
    folder = Path(folder).expanduser().absolute()
    if not folder.is_dir():
        raise ValueError('PDF folder does not exist: ' + str(folder))
    register = load_register(root)
    attached = {f['sha256']: note for note, row in register['papers'].items() for f in row.get('files', [])}
    attached.update({f.get('original_sha256'): note for note, row in register['papers'].items()
                     for f in row.get('files', []) if f.get('original_sha256')})
    identities = note_identities(core, root)
    rows, seen = [], {}
    # Sort by the POSIX string so the same files are judged the same way on every OS (Windows sorts Paths case-insensitively).
    for path in sorted((p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() == '.pdf' and not p.is_symlink()), key=lambda x: x.as_posix()):
        raw = path.read_bytes()
        digest = sha256(raw)
        info = inspect_pdf(raw)
        name_ids = ARXIV_NEW.findall(path.stem)
        arxiv = sorted(set(info.get('arxiv', [])) | {a + v for a, v in name_ids})
        row = {'file': str(path), 'sha256': digest, 'bytes': len(raw), **{k: v for k, v in info.items() if k != 'arxiv'},
               'arxiv': arxiv}
        match = None
        for key in ['doi:' + d.lower() for d in info.get('dois', [])] + ['arxiv:' + a.split('v')[0] for a in arxiv]:
            match = match or identities.get(key)
        if not info['is_pdf']:
            row['status'] = 'not_pdf'
        elif digest in attached:
            row.update(status='attached', note=attached[digest])
        elif digest in seen:
            row.update(status='duplicate_file', same_as=seen[digest])
        elif match:
            row.update(status='note_exists_without_this_pdf', note=match)
        else:
            row['status'] = 'new'
        seen.setdefault(digest, str(path))
        rows.append(row)
    counts = {}
    for row in rows:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    return {'status': 'scanned', 'folder': str(folder), 'counts': counts, 'pdfs': rows,
            'next': 'For each new PDF: read it (pdfs text), write a paper card with "pdf" set to its file, render --apply. '
                    'For note_exists_without_this_pdf: verify identity and version, then pdfs attach.'}


def text_command(core, root, file, engine, pages=None):
    raw = Path(file).expanduser().read_bytes()
    digest = sha256(raw)
    cache = root / TEXT_CACHE / (digest + '.json')
    if cache.is_file() and engine == 'auto':
        result = json.loads(cache.read_text(encoding='utf-8'))
    else:
        result = {'sha256': digest, **extract_text(raw, engine)}
        if (root / core.CONFIG).is_file():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(result, ensure_ascii=False) + '\n', encoding='utf-8')
    if pages:
        wanted = set(pages)
        result = {**result, 'pages': [p for p in result['pages'] if p['page'] in wanted]}
    return {'status': 'text', 'file': str(file), **result}


def locate(root, vault, item):
    """File of a register entry: a managed copy (root-relative `path`) or a linked original (`target`)."""
    if item.get('mode') == 'link':
        return (vault / item['target']) if item.get('inside_vault') else Path(item['target'])
    return root / item['path']


def entry_key(item):
    return item['target'] if item.get('mode') == 'link' else item['path']


def entry_link(core, vault, item, file):
    """Wikilink inside the vault; a file:// link for an original that lives outside it."""
    if item.get('mode') == 'link' and not item.get('inside_vault'):
        return '[' + file.name.replace('[', '(').replace(']', ')') + '](' + file.as_uri() + ')'
    return core.wikilink(vault, file, file.name)


def attach(core, root, p, pairs, apply):
    """pairs: [(pdf file, paper note path, mode)] with mode "copy" (default) or "link".
    copy: byte-identical copy in the field's PDFs/; link: the original is registered where it is.
    Either way the original file is never moved, renamed or modified."""
    vault = core.vault_base(root, p['vault_prefix'])
    register = load_register(root)
    library, papers_folder = p['layout']['library'], p['layout']['papers']
    plan, rows, writes = {}, [], {}
    owner = {f['sha256']: note for note, r in register['papers'].items() for f in r.get('files', [])}
    for source, note, *rest in pairs:
        mode = rest[0] if rest and rest[0] else 'copy'
        if mode not in ('copy', 'link'):
            raise ValueError('mode is "copy" or "link": ' + str(mode))
        source = Path(source).expanduser().absolute()
        note_path = core.inside(root, note, 'Paper note')
        parts = Path(note).parts
        if not note_path.is_file() or core.role(core.raw_text(note_path), note_path, root) != 'paper':
            raise ValueError('Attach to an existing #paper note: ' + note)
        if len(parts) != 5 or parts[0] != library or parts[3] != papers_folder:
            raise ValueError('Paper note must sit at Library/<Discipline>/<Field>/Papers/: ' + note)
        if not source.is_file() or source.is_symlink():
            raise ValueError('PDF source must be an existing regular file: ' + str(source))
        raw = source.read_bytes()
        info = inspect_pdf(raw)
        if not info['is_pdf']:
            raise ValueError('Not a PDF (missing %PDF- signature): ' + str(source))
        digest = sha256(raw)
        if owner.get(digest) not in (None, note):
            raise ValueError('These PDF bytes are already the original of another note: ' + owner[digest])
        if mode == 'link':
            inside_vault = source.resolve().is_relative_to(vault.resolve())
            target_text = source.resolve().relative_to(vault.resolve()).as_posix() if inside_vault else source.as_posix()
            row = register['papers'].setdefault(note, {'status': 'available', 'files': [], 'preferred_pdf': target_text})
            if not any(f.get('mode') == 'link' and f['target'] == target_text for f in row['files']):
                row['files'].append({'mode': 'link', 'target': target_text, 'inside_vault': inside_vault, 'sha256': digest,
                                     'pages': info.get('pages'), 'added': datetime.date.today().isoformat()})
            row['status'] = 'available'
            owner[digest] = note
            rows.append({'pdf': str(source), 'note': note, 'link': target_text, 'action': 'link'})
            continue
        target = root.joinpath(*parts[:3], 'PDFs', Path(note).stem + '.pdf')
        if target.exists() and sha256(target.read_bytes()) != digest:
            raise ValueError('A different PDF already occupies ' + target.relative_to(root).as_posix() +
                             '; keep both only as an explicit version (e.g. " - arXiv v2").')
        rel_pdf = target.relative_to(root).as_posix()
        row = register['papers'].setdefault(note, {'status': 'available', 'files': [], 'preferred_pdf': rel_pdf})
        entry = next((f for f in row['files'] if f['path'] == rel_pdf), None)
        if entry is None:
            entry = {'path': rel_pdf, 'sha256': digest, 'pages': info.get('pages'), 'original_path': str(source),
                     'original_sha256': digest, 'added': datetime.date.today().isoformat()}
            row['files'].append(entry)
        row['status'] = 'available'
        row.setdefault('preferred_pdf', rel_pdf)
        owner[digest] = note
        writes[target] = raw
        rows.append({'pdf': str(source), 'note': note, 'copy': rel_pdf, 'action': 'unchanged' if target.exists() else 'copy'})
    texts = {}
    for note in sorted({pair[1] for pair in pairs}):
        path = root / note
        text = core.raw_text(path)
        items = register['papers'][note]['files']
        new = put_pdf_block(text, [entry_link(core, vault, f, locate(root, vault, f)) for f in items])
        if new != text:
            plan[path] = new
            texts[path] = text
    result = {'status': 'preview', 'attachments': rows, 'notes_linked': sorted(x.relative_to(root).as_posix() for x in plan)}
    if not apply:
        return result
    for target, raw in writes.items():
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + '.p2p-tmp')
            temp.write_bytes(raw)
            os.replace(temp, target)
        if sha256(target.read_bytes()) != sha256(raw):
            raise ValueError('Copied PDF does not match its source bytes: ' + str(target))
    core.write_texts(plan, texts)
    save_register(root, register)
    result['status'] = 'attached'
    return result


def put_pdf_block(text, links):
    """One `p2p:pdf` block per language block, right after the metadata lines (before the first section)."""
    newline = '\r\n' if '\r\n' in text else '\n'
    text = text.replace('\r\n', '\n')
    pattern = re.escape(MARK[0]) + r'.*?' + re.escape(MARK[1])
    block = MARK[0] + '\n' + '  \n'.join(links) + '\n' + MARK[1]
    head_end = 0
    if text.startswith('---\n'):
        end = re.search(r'^---[ \t]*$', text[4:], re.M)
        head_end = 4 + end.end() if end else 0
    head, body = text[:head_end], text[head_end:]
    seps = list(re.finditer(r'^---[ \t]*$', body, re.M))
    cuts = [0, *[x for m in seps for x in (m.start(), m.end())], len(body)]
    segments = [body[cuts[i]:cuts[i + 1]] for i in range(0, len(cuts), 2)]
    out = []
    for segment in segments:
        if re.search(pattern, segment, re.S):
            segment = re.sub(pattern, lambda _: block, segment, count=1, flags=re.S)
        else:
            section = re.search(r'^## ', segment, re.M)
            at = section.start() if section else len(segment.rstrip('\n'))
            segment = segment[:at].rstrip('\n') + '\n\n' + block + '\n\n' + segment[at:].lstrip('\n')
        out.append(segment)
    joined = out[0] + ''.join(body[m.start():m.end()] + out[i + 1] for i, m in enumerate(seps))
    return (head + joined).replace('\n', newline)


def audit(core, root, p, files, kinds):
    """(errors, warnings, counts) for registered originals and stray PDFs in Library."""
    errors, warnings = [], []
    try:
        register = load_register(root)
    except (ValueError, OSError) as exc:
        return [str(exc)], [], {}
    vault = core.vault_base(root, p['vault_prefix'])
    registered = set()
    available = 0
    for note, row in sorted(register['papers'].items()):
        path = root / note
        if not path.is_file() or kinds.get(path) != 'paper':
            errors.append('PDF register points at a missing or non-paper note: ' + note)
            continue
        if row.get('status') == 'missing':
            if row.get('files'):
                errors.append('A missing-original record must not list files: ' + note)
            continue
        if row.get('status') != 'available' or not row.get('files') or row.get('preferred_pdf') not in [entry_key(f) for f in row['files']]:
            errors.append('Invalid PDF register record: ' + note)
            continue
        available += 1
        text = core.raw_text(path).replace('\r\n', '\n')
        blocks = re.split(r'^---\s*$', core.split_front(text)[1], flags=re.M)
        for item in row['files']:
            linked = item.get('mode') == 'link'
            pdf = locate(root, vault, item)
            label = entry_key(item)
            registered.add(pdf.resolve())
            if not linked and (Path(label).parent != Path(note).parent.parent / 'PDFs' or Path(label).suffix.lower() != '.pdf'):
                errors.append('PDF copy is outside its paper field PDFs folder: ' + label)
            if not pdf.is_file() or pdf.is_symlink():
                errors.append(('Linked original is missing (it may have been moved or renamed outside Paper2Project; '
                               'check it, then attach again): ' if linked else 'Registered PDF copy is missing: ') + label)
                continue
            raw = pdf.read_bytes()
            if not raw.startswith(b'%PDF-') or sha256(raw) != item.get('sha256'):
                errors.append(('Linked original changed since it was registered (not modified by Paper2Project; check the version, '
                               'then attach again): ' if linked else 'PDF copy differs from the register (signature or hash): ') + label)
            target = entry_link(core, vault, item, pdf)
            target = target.split('|')[0] if target.startswith('[[') else target[target.index('](') + 2:-1]
            if any(target not in block for block in blocks):
                errors.append('Original PDF is not linked in every language block: ' + note)
    library = set(core.layout_values(p, 'library'))
    for pdf in sorted(x for x in core.regular_files(root) if x.suffix.lower() == '.pdf'):
        rel = pdf.relative_to(root)
        if rel.parts[0] in library and pdf.resolve() not in registered:
            warnings.append('Unregistered PDF in Library (attach it to its paper note with pdfs attach): ' + rel.as_posix())
    return errors, warnings, {'papers_with_original': available, 'registered_files': len(registered)}


def migrate_register(root, moved):
    """Rewrite register paths after a migration. `moved` maps resolved old -> new paths."""
    path = register_path(root)
    if not path.is_file():
        return False
    data = load_register(root)
    base = root.resolve()
    remap = {o.relative_to(base).as_posix(): n.relative_to(base).as_posix()
             for o, n in moved.items() if o.is_relative_to(base) and n.is_relative_to(base)}
    papers = {}
    for note, row in data['papers'].items():
        for item in row.get('files', []):
            if item.get('mode') != 'link':  # linked originals are never moved
                item['path'] = remap.get(item['path'], item['path'])
        if row.get('preferred_pdf'):
            row['preferred_pdf'] = remap.get(row['preferred_pdf'], row['preferred_pdf'])
        papers[remap.get(note, note)] = row
    if papers != data['papers'] or remap:
        data['papers'] = papers
        save_register(root, data)
        return True
    return False
