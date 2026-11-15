#!/usr/bin/env python3
"""Update an installed Paper2Project skill from a newer download without losing local changes.

Run the NEW download's copy:  python <new>/scripts/update_skill.py --target <installed skill> [--apply]

MANIFEST.json lists every file the package has ever shipped with the hash of each released
version. A file is replaced only when it still matches one of those shipped versions; a file the
user edited is kept and the new version is written beside it as <name>.new. Files the package
never shipped (local/, adapters, notes) are never touched. Standard library only; no network.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parents[1]
MANIFEST = 'MANIFEST.json'
SKIP_DIRS = {'.git', '__pycache__', 'local', '.venv'}
SKIP_FILES = {MANIFEST, '.DS_Store'}


def file_hash(path):
    # Line endings are normalized so a CRLF checkout of an unmodified file still matches.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def package_files(root):
    found = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(directory) / name
            if name not in SKIP_FILES and not name.endswith(('.pyc', '.new')) and not path.is_symlink():
                found.append(path.relative_to(root).as_posix())
    return found


def load_manifest(root):
    path = root / MANIFEST
    if not path.is_file():
        raise ValueError('No ' + MANIFEST + ' in ' + str(root))
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data.get('files'), dict) or not isinstance(data.get('removed', {}), dict):
        raise ValueError('Unrecognized ' + MANIFEST)
    return data


def is_skill(root):
    skill = root / 'SKILL.md'
    return skill.is_file() and 'name: paper2project' in skill.read_text(encoding='utf-8')


def plan_update(source, target):
    if not is_skill(source) or not is_skill(target):
        raise ValueError('Both --from and --target must be Paper2Project skill folders.')
    if source.resolve() == target.resolve():
        raise ValueError('--target is the folder being installed from.')
    manifest = load_manifest(source)
    rows = []
    for relative, history in sorted(manifest['files'].items()):
        dest = target / relative
        if dest.is_symlink():
            rows.append({'path': relative, 'action': 'kept_custom', 'reason': 'symlink'})
        elif not dest.exists():
            rows.append({'path': relative, 'action': 'add'})
        elif file_hash(dest) == history[-1]:
            rows.append({'path': relative, 'action': 'unchanged'})
        elif file_hash(dest) in history:
            rows.append({'path': relative, 'action': 'update'})
        else:
            rows.append({'path': relative, 'action': 'kept_custom', 'new_version': relative + '.new'})
    for relative, history in sorted(manifest.get('removed', {}).items()):
        dest = target / relative
        if dest.is_file() and not dest.is_symlink():
            rows.append({'path': relative, 'action': 'remove' if file_hash(dest) in history else 'kept_custom'})
    return rows


def apply_update(source, target, rows):
    for row in rows:
        src, dest = source / row['path'], target / row['path']
        if row['action'] in ('add', 'update') or (row['action'] == 'kept_custom' and 'new_version' in row):
            out = target / row.get('new_version', row['path'])
            out.parent.mkdir(parents=True, exist_ok=True)
            temp = out.with_name(out.name + '.p2p-tmp')
            temp.write_bytes(src.read_bytes())
            os.replace(temp, out)
        elif row['action'] == 'remove':
            dest.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--target', required=True, help='Installed skill folder to update.')
    parser.add_argument('--from', dest='source', default=str(PACKAGE), help='New download (default: this package).')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        source, target = Path(args.source).expanduser().absolute(), Path(args.target).expanduser().absolute()
        rows = plan_update(source, target)
        if args.apply:
            apply_update(source, target, rows)
        summary = {}
        for row in rows:
            summary[row['action']] = summary.get(row['action'], 0) + 1
        custom = [r for r in rows if r['action'] == 'kept_custom']
        print(json.dumps({'status': 'updated' if args.apply else 'preview', 'summary': summary, 'kept_custom': custom,
                          'changes': [r for r in rows if r['action'] in ('add', 'update', 'remove')],
                          'next': 'Review each <file>.new against your edited file; then run p2p.py upgrade --root <workspace> for each workspace.'},
                         ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
