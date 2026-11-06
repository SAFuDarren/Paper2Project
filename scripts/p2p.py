#!/usr/bin/env python3
"""Paper2Project local setup, validation and inert retrieval handoff. No network."""

import argparse
import hashlib
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


def role(text, path, root):
    body = visible_text(split_front(text)[1])
    # Adopt existing tag-only lines such as '#paper #selected' without rewriting notes.
    tag_names = set()
    for line in body.splitlines():
        if re.fullmatch(r'\s*#[\w/-]+(?:\s+#[\w/-]+)*\s*', line):
            tag_names.update(re.findall(r'#([\w/-]+)', line))
    kinds = [k for k, tag in TAGS.items() if tag in tag_names]
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
        destination, _, label = m[1].partition('|')
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


def source_identity(text):
    front, body = split_front(text)
    explicit = scalar(front, 'source_id')
    if explicit:
        value = explicit
    else:
        m = re.search(r'^\*\*Paper:\*\*\s*(.+)', body, re.M)
        line = m[1] if m else ''
        url = re.search(r'https?://[^\s<>)]+', line)
        value = url[0] if url else line
    value = value.strip('<>').rstrip('/').lower()
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', 'doi:', value)
    value = re.sub(r'^https?://arxiv\.org/(?:abs|pdf)/', 'arxiv:', value)
    if value.startswith('arxiv:'):
        value = re.sub(r'(?:v\d+)?(?:\.pdf)?$', '', value)
    return value or None


def query(prefix, full=False):
    chosen = list(TAGS.values()) if full else [TAGS[x] for x in ('field', 'direction', 'project')]
    clause = '(' + ' OR '.join('tag:#' + t for t in chosen) + ')'
    return ('path:"' + prefix + '/" ' if prefix else '') + clause


def init_workspace(args):
    root = no_symlink_root(Path(args.root))
    p = load_profile(args.profile)
    supplied = json.loads(Path(args.profile).read_text(encoding='utf-8')) if args.profile else {}
    if (root/CONFIG).exists():
        print(dump({'status':'already_initialized','root':str(root),'written':[]}));return 0
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise InputError('Target is nonempty. Use agent-guided adoption; init never migrates or overwrites.')
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
        if 'vault_prefix' not in supplied:p['vault_prefix']=ask('Vault-relative academic prefix (empty for vault root)',p['vault_prefix'])
        p=profiles.normalize(p)
    vault_base(root,p['vault_prefix'])
    for origin in p['preference_sources'].values():origin['scope']='workspace'
    planned=i18n.scaffold(p,query)
    # Agent rules reference the live profile; changing language/color preferences
    # does not leave duplicated literal rules stale.
    planned['AGENTS.md']=(PACKAGE/'assets/workspace-rules.md').read_text(encoding='utf-8')
    planned[CONFIG]=dump(p)+'\n'
    if not args.apply:
        print(dump({'status':'design_only','root':str(root),'profile':p,'planned_files':list(planned),'next':'Add --apply to create this fresh workspace.'}));return 0
    if root.exists() and any(root.iterdir()):raise InputError('Target changed during onboarding; no files written.')
    root.mkdir(parents=True,exist_ok=True)
    for relative,content in planned.items():
        dest=root/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('x',encoding='utf-8',newline='') as out:out.write(content)
    print(dump({'status':'created','root':str(root),'written':list(planned)}));return 0


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
    for path in files:
        text=path.read_text(encoding='utf-8');front,body=split_front(text);parts=path.relative_to(root).parts;rel=path.relative_to(root).as_posix();kind=role(text,path,root)
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
            except InputError as exc:errors.append(rel+': '+str(exc))
    for path in files:
        parts=path.relative_to(root).parts
        if parts[0] not in projects or len(parts)<6:continue
        home_dir=root.joinpath(*parts[:5]);expected=home_dir/(home_dir.name+'.md')
        if expected not in homes:errors.append('Project records lack a unique tagged home: '+str(path.relative_to(root)))
        if len(parts)>6 and parts[5] not in groups:errors.append('Record outside the four project groups: '+str(path.relative_to(root)))
    for name in projects:
        for raw in regular_files(root/name):
            if raw.suffix.lower()=='.pdf':warnings.append('PDF in Projects needs provenance review; source papers stay in Library/original archive, own result artifacts need evidence: '+str(raw.relative_to(root)))
    report={'status':'failed' if errors else ('needs_review' if warnings else 'passed'),'structural_status':'failed' if errors else 'passed','files':len(files),'roles':counts,'errors':sorted(set(errors)),'warnings':sorted(set(warnings)),
            'scope':'Structure, naming, locale-aware section/metadata presence, IDs/source duplicates, links/anchors and declared language shape. Not translation quality, source support or scientific verification.'}
    print(dump(report));return 1 if errors else 0


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
    card=json.loads(Path(args.input).read_text(encoding='utf-8'));text=i18n.render(args.kind,card,profile)
    dest=Path(args.output)
    if not dest.is_absolute():dest=root/dest
    no_symlink_root(dest.parent)
    if not dest.resolve().is_relative_to(root.resolve()) or dest.suffix.lower()!='.md':raise InputError('Note destination must be a Markdown file inside the selected root.')
    if dest.exists() or dest.is_symlink():raise InputError('Note exists; render never replaces a canonical note.')
    identity=source_identity(text) if args.kind=='paper' else None
    for path in markdown_files(root):
        old=path.read_text(encoding='utf-8');front,_=split_front(old)
        if scalar(front,'p2p_id')==card['id']:raise InputError('Stable note ID already exists: '+str(path.relative_to(root)))
        if identity and role(old,path,root)=='paper' and source_identity(old)==identity:raise InputError('Paper source already has a canonical note: '+str(path.relative_to(root)))
    result={'status':'preview','path':str(dest),'languages':profile['note_languages'],'markdown':text}
    if args.apply:
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('x',encoding='utf-8',newline='') as out:out.write(text)
        if dest.read_text(encoding='utf-8')!=text:raise InputError('Note readback failed.')
        result={'status':'rendered','path':str(dest),'languages':profile['note_languages'],'content_sha256':digest(text.encode('utf-8'))}
    print(dump(result));return 0


def locales_command(args):
    packs=json.loads((PACKAGE/'assets/locales.json').read_text(encoding='utf-8'))
    result={'bundled_locales':{code:value['name'] for code,value in packs.items()},'custom':'Complete locale_overrides packs support additional language tags; no English substitution.'}
    if args.template:
        template={'name':'','sections':dict.fromkeys(i18n.SECTIONS,''),'labels':dict.fromkeys(i18n.LABELS,''),'ui':dict.fromkeys(i18n.UI,'')}
        result={'locale_overrides':{args.template:template},'reference_labels':packs['en'],'next':'Have the host LLM fill the labels in the requested language, then validate/save the pack before rendering.'}
    print(dump(result));return 0


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
        if name == 'export':
            cmd.add_argument('--kind', action='append', choices=KINDS, help='Repeat to restrict the snapshot; default all managed kinds.')
            cmd.add_argument('--output', required=True, help='New local .jsonl path, or - for stdout.')
    cmd=sub.add_parser('preferences',help='Resolve supplied context/memory signals and preview or save preferences.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--signals')
    cmd.add_argument('--scope',choices=('task','workspace'),default='task')
    cmd.add_argument('--apply',action='store_true');cmd.add_argument('--expect-sha');cmd.add_argument('--output')
    cmd=sub.add_parser('render',help='Render supplied source-grounded content with localized templates.')
    cmd.add_argument('--root',required=True);cmd.add_argument('--kind',choices=tuple(i18n.SPECS),required=True)
    cmd.add_argument('--input',required=True);cmd.add_argument('--output',required=True);cmd.add_argument('--profile');cmd.add_argument('--apply',action='store_true')
    cmd=sub.add_parser('locales');cmd.add_argument('--template')
    args = parser.parse_args(argv)
    try:
        return {'inspect': inspect_workspace, 'init': init_workspace,
                'check': check_workspace, 'export': export_workspace,
                'preferences':preferences_command,'render':render_command,'locales':locales_command}[args.command](args)
    except (ValueError, OSError, TypeError, KeyError, UnicodeError) as ex:
        print(dump({'status': 'error', 'message': str(ex)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
