#!/usr/bin/env python3
"""Offline package/locale/reference checks; no user vault or memory is inspected."""
import json
from pathlib import Path
import re
import sys
import i18n
import profiles

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
    # Privacy checks are packaging guards, not a secret-scanner certification.
    print(json.dumps({'status':'failed' if errors else 'passed','errors':errors,'core_lines':len(core.splitlines()),'locale_packs':list(packs),'templates':len(i18n.SPECS)},ensure_ascii=False))
    return 1 if errors else 0

if __name__=='__main__':raise SystemExit(main())
