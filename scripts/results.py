"""Read-only inventory of a results repository and program-formatted evidence links.

`scan` reads the repository's own files (no git binary or network needed): current commit and
branch from `.git`, the origin URL without credentials, and the documents, notebooks, results,
figures and code that a project note may cite. `evidence_lines` turns `{"path", "commit", "repo"}`
references into stable links: a commit permalink for GitHub/GitLab/Bitbucket remotes, otherwise
`path @ commit` with the repository location.
"""
import configparser
import hashlib
from pathlib import Path
import re
import subprocess
import shutil

SKIP = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.mypy_cache', '.pytest_cache', '.ipynb_checkpoints', 'dist', 'build'}
GROUPS = (
    ('documents', ('.md', '.rst', '.tex', '.txt', '.org')),
    ('notebooks', ('.ipynb',)),
    ('results', ('.csv', '.tsv', '.json', '.jsonl', '.parquet', '.npz', '.npy', '.h5', '.hdf5', '.log')),
    ('figures', ('.png', '.jpg', '.jpeg', '.svg', '.pdf', '.eps')),
    ('code', ('.py', '.jl', '.r', '.m', '.cpp', '.c', '.h', '.rs', '.go', '.js', '.ts', '.java', '.sh')),
)
LIMIT = 200


def git_state(repo):
    git = repo / '.git'
    if git.is_file():  # worktree or submodule: "gitdir: <path>"
        target = git.read_text(encoding='utf-8').split(':', 1)[1].strip()
        git = (repo / target).resolve()
    if not git.is_dir():
        return {'git': False}
    head = (git / 'HEAD').read_text(encoding='utf-8').strip()
    branch, commit = None, None
    if head.startswith('ref:'):
        ref = head.split(':', 1)[1].strip()
        branch = ref[len('refs/heads/'):] if ref.startswith('refs/heads/') else ref
        loose = git / ref
        if loose.is_file():
            commit = loose.read_text(encoding='utf-8').strip()
        elif (git / 'packed-refs').is_file():
            for line in (git / 'packed-refs').read_text(encoding='utf-8').splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    commit = parts[0]
    else:
        commit = head
    remote = None
    config = git / 'config'
    if config.is_file():
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            parser.read(config, encoding='utf-8')
            remote = parser.get('remote "origin"', 'url', fallback=None)
        except configparser.Error:
            remote = None
    if remote:
        remote = re.sub(r'(?<=://)[^/@]+@', '', remote)  # never carry credentials in a URL
    dirty = None
    exe = shutil.which('git')
    if exe:
        try:
            out = subprocess.run([exe, '-C', str(repo), 'status', '--porcelain'], capture_output=True, text=True, timeout=60)
            dirty = bool(out.stdout.strip()) if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            dirty = None
    return {'git': True, 'branch': branch, 'commit': commit, 'remote': remote, 'uncommitted_changes': dirty}


def web_base(remote, commit):
    """Commit permalink prefix for well-known hosts, else None."""
    if not remote or not commit:
        return None
    m = re.match(r'^(?:https?://|ssh://)?(?:git@)?([^/:]+)[:/](.+?)(?:\.git)?/?$', remote)
    if not m:
        return None
    host, path = m[1].lower(), m[2]
    if host in ('github.com', 'gitlab.com') or host.startswith('gitlab.'):
        return 'https://' + host + '/' + path + ('/blob/' if 'github' in host else '/-/blob/') + commit + '/'
    if host == 'bitbucket.org':
        return 'https://bitbucket.org/' + path + '/src/' + commit + '/'
    return None


def scan(repo):
    repo = Path(repo).expanduser().absolute()
    if not repo.is_dir():
        raise ValueError('Results repository folder does not exist: ' + str(repo))
    state = git_state(repo)
    groups = {name: [] for name, _ in GROUPS}
    other = 0
    for path in sorted(repo.rglob('*')):
        rel = path.relative_to(repo)
        if any(part in SKIP or part.startswith('.') for part in rel.parts) or not path.is_file() or path.is_symlink():
            continue
        suffix = path.suffix.lower()
        group = next((name for name, suffixes in GROUPS if suffix in suffixes), None)
        if group is None:
            other += 1
            continue
        entry = {'path': rel.as_posix(), 'bytes': path.stat().st_size}
        if group in ('documents', 'notebooks') and entry['bytes'] <= 5_000_000:
            entry['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        groups[group].append(entry)
    readme = next((x['path'] for x in groups['documents'] if re.fullmatch(r'readme(\.\w+)?', x['path'].lower())), None)
    counts = {k: len(v) for k, v in groups.items()}
    return {'status': 'scanned', 'repository': str(repo), **state,
            'permalink_base': web_base(state.get('remote'), state.get('commit')),
            'readme': readme, 'counts': {**counts, 'other': other},
            'files': {k: v[:LIMIT] for k, v in groups.items()},
            'truncated': {k: v for k, v in counts.items() if v > LIMIT},
            'next': 'Read the README and documents first. Write one project card per concrete question, and Problem/Methods/'
                    'Results/Extensions record cards whose "evidence" lists {"path", "commit"} from this scan. Keep claims to '
                    'what the repository actually shows; uncommitted work is cited only after it is committed.'}


def evidence_lines(items, cache):
    """Format evidence references; `cache` memoizes repository scans by location."""
    lines = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not item['path'].strip():
            raise ValueError('Each evidence item needs a "path" inside the results repository.')
        repo = item.get('repo')
        commit = item.get('commit')
        remote = item.get('remote')
        if repo and not remote and Path(repo).expanduser().is_dir():
            state = cache.setdefault(repo, git_state(Path(repo).expanduser().absolute()))
            remote, commit = state.get('remote'), commit or state.get('commit')
            if not (Path(repo).expanduser() / item['path']).exists():
                raise ValueError('Evidence file does not exist in the repository: ' + item['path'])
        if not commit or not re.fullmatch(r'[0-9a-fA-F]{7,64}', commit):
            raise ValueError('Evidence needs the commit it refers to (from repo scan): ' + item['path'])
        base = web_base(remote, commit)
        label = item['path'] + ' @ ' + commit[:10]
        line = '[' + label + '](' + base + item['path'] + ')' if base else '`' + item['path'] + '` @ `' + commit[:10] + '`' + (
            ' (' + (remote or str(repo)) + ')' if (remote or repo) else '')
        if item.get('note'):
            line += ' — ' + ' '.join(str(item['note']).split())
        lines.append('- ' + line)
    return lines
