#!/usr/bin/env python3
"""Offline package/locale/reference checks; no user vault or memory is inspected."""
import json
from pathlib import Path
import re
import sys
import i18n
import profiles
import update_skill

ROOT=Path(__file__).resolve().parents[1]
def main():
    errors=[]
    core=(ROOT/'SKILL.md').read_text(encoding='utf-8')
    if not re.search(r'^name: paper2project$',core,re.M):errors.append('Skill name missing')
    if len(core.splitlines())>120:errors.append('Core entry is unexpectedly long')
    for folder in ('scripts','assets','references','examples','tests','.github'):
        for path in (ROOT/folder).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:continue
            text=path.read_text(encoding='utf-8')
            if path.suffix=='.json':json.loads(text)
            absolute_home=r'/(?:Users|home)/[A-Za-z0-9_.-]+/'
            windows_home=r'[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+\\'
            if re.search(absolute_home,text) or re.search(windows_home,text):errors.append('Machine-specific home path in '+str(path.relative_to(ROOT)))
    for path in [ROOT/'SKILL.md',*sorted(ROOT.glob('README*.md')),*(ROOT/'references').glob('*.md'),*(ROOT/'examples').glob('*.md')]:
        text=path.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if '://' in target or target.startswith('#'):continue
            target=target.split('#',1)[0]
            if not (path.parent/target).exists():errors.append('Missing package reference: '+str(path.relative_to(ROOT))+' -> '+target)
    profiles.load()
    packs=json.loads((ROOT/'assets/locales.json').read_text(encoding='utf-8'))
    for pack in packs.values():i18n.validate_pack(pack)
    for kind in i18n.SPECS:
        text=(ROOT/'assets/templates'/(kind+'.md')).read_text(encoding='utf-8')
        if any('{{'+key+'}}' not in text for key in ('TITLE','METADATA','SECTIONS')):errors.append('Incomplete template: '+kind)
    # Every shipped file must be in the release manifest so updates can tell it from a local edit.
    manifest=build_manifest()
    if '--write-manifest' in sys.argv[1:]:
        (ROOT/update_skill.MANIFEST).write_text(json.dumps(manifest,indent=1,sort_keys=True)+'\n',encoding='utf-8')
    elif '--release' in sys.argv[1:]:
        shipped=ROOT/update_skill.MANIFEST
        if not shipped.is_file() or json.loads(shipped.read_text(encoding='utf-8'))!=manifest:
            errors.append('MANIFEST.json is out of date; run python scripts/package_check.py --write-manifest')
    # Privacy checks are packaging guards, not a secret-scanner certification.
    print(json.dumps({'status':'failed' if errors else 'passed','errors':errors,'core_lines':len(core.splitlines()),'locale_packs':list(packs),'templates':len(i18n.SPECS)},ensure_ascii=False))
    return 1 if errors else 0

def build_manifest():
    """Append the current hash of each package file to its release history; keep removed files' history."""
    path=ROOT/update_skill.MANIFEST
    old=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'files':{},'removed':{}}
    files,removed={},{k:list(v) for k,v in old.get('removed',{}).items()}
    current=set(update_skill.package_files(ROOT))
    for relative in sorted(current):
        history=list(old['files'].get(relative,removed.pop(relative,[])))
        digest=update_skill.file_hash(ROOT/relative)
        if not history or history[-1]!=digest:history.append(digest)
        files[relative]=history
    for relative,history in old['files'].items():
        if relative not in current:removed[relative]=history
    return {'files':files,'removed':dict(sorted(removed.items()))}

if __name__=='__main__':raise SystemExit(main())
