"""Preference normalization/resolution. Host context is supplied, never crawled."""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import i18n

ASSETS=Path(__file__).resolve().parents[1]/'assets'
SOURCES=('default','context','memory','saved','explicit')
SOFT={'note_languages','language','response_language','filename_language','preferences','palette','research_scope','current_aim','locale_overrides'}


def merge(base,values):
    result=copy.deepcopy(base)
    for key,value in values.items():
        if isinstance(value,dict) and isinstance(result.get(key),dict):result[key]=merge(result[key],value)
        else:result[key]=copy.deepcopy(value)
    return result


def safe_name(value):
    if not isinstance(value,str) or not value.strip() or value in ('.','..') or value.rstrip(' .')!=value or any(c in value for c in '/\\\n\r<>:"|?*'):
        raise ValueError('Names must be portable single directory names: '+str(value))
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        raise ValueError('Reserved Windows filename: '+value)


def normalize(raw):
    if not isinstance(raw,dict):raise ValueError('Profile must be a JSON object.')
    p=merge(json.loads((ASSETS/'default-profile.json').read_text(encoding='utf-8')),raw)
    if p['schema_version'] not in (1,2):raise ValueError('Unsupported profile schema_version.')
    legacy=raw.get('language')
    if 'note_languages' not in raw or p['schema_version']==1:
        p['note_languages']=['en','zh'] if legacy=='en-zh' else [legacy or 'en']
    # In schema v2, explicit note_languages is canonical. The legacy alias must
    # never silently undo a manual edit to the new field.
    languages=p['note_languages']
    if not isinstance(languages,list) or not languages or len(languages)!=len(set(languages)) or not all(isinstance(x,str) and re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*',x) for x in languages):raise ValueError('note_languages needs unique language tags in presentation order.')
    p['language']='en-zh' if languages==['en','zh'] else (languages[0] if len(languages)==1 else 'multilingual')
    if not isinstance(p['locale_overrides'],dict):raise ValueError('locale_overrides must be a mapping.')
    for code,pack in p['locale_overrides'].items():
        if not isinstance(code,str) or not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*',code):raise ValueError('Custom locale keys must be language tags.')
        i18n.validate_pack(pack)
    for language in languages:i18n.locale(language,p)
    for key in ('response_language','filename_language'):
        if not isinstance(p[key],str) or not (p[key] in ('auto','original') or re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*',p[key])):raise ValueError(key+' must use a language tag, auto or original.')
    for key in ('research_scope','current_aim','vault_prefix'):
        if not isinstance(p[key],str):raise ValueError(key+' must be a string.')
    prefix=p['vault_prefix']
    if prefix.startswith('/') or '\\' in prefix or any(c in prefix for c in '\n\r[]|"') or any(x in ('.','..') for x in prefix.split('/')):raise ValueError('Invalid vault_prefix.')
    p['vault_prefix']=prefix.strip('/')
    context=p['context']
    if not isinstance(context,dict) or not all(isinstance(context.get(k),list) and all(isinstance(x,str) for x in context[k]) for k in ('materials','project_overviews')):raise ValueError('context materials/project_overviews need selected pointer lists.')
    for key in ('management_entry','maintenance_entry','task_template','maintenance_directory'):
        if context.get(key) is not None and not isinstance(context[key],str):raise ValueError('Context pointers must be strings or null.')
    prefs=p['preferences']
    if not isinstance(prefs,dict) or not isinstance(prefs.get('preserve_existing'),bool):raise ValueError('preferences needs preserve_existing.')
    for key in ('filename_style','note_detail','navigation_style'):
        if prefs.get(key) is not None and not isinstance(prefs[key],str):raise ValueError('Preference '+key+' must be a string or null.')
    if not isinstance(p['taxonomy'],list):raise ValueError('taxonomy must be a list.')
    for item in p['taxonomy']:
        if not isinstance(item,dict) or not all(isinstance(item.get(k),str) and item[k].strip() for k in ('discipline','field','direction','basis')):raise ValueError('Taxonomy needs discipline, field, direction and naming basis.')
        for key in ('discipline','field','direction'):safe_name(item[key])
    colors=p['palette']
    if set(colors)!={'field','direction','project','paper','concept'} or not all(isinstance(x,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',x) for x in colors.values()) or len({x.casefold() for x in colors.values()})!=5:raise ValueError('palette needs five distinct role colors as #RRGGBB.')
    for layout in [p['layout'],*p.get('previous_layouts',[])]:
        expected={'home','library','projects','papers','concepts','direction_suffix','groups'}
        if not isinstance(layout,dict) or set(layout)!=expected or set(layout['groups'])!={'problem','methods','results','extensions'}:raise ValueError('Layout needs canonical role mappings and four typed groups.')
        for name in [v for k,v in layout.items() if k!='groups']+list(layout['groups'].values()):safe_name(name)
        if layout['library']==layout['projects'] or layout['papers']==layout['concepts'] or len(set(layout['groups'].values()))!=4:raise ValueError('Layout roles must stay distinct.')
    slots=p['extensions']
    if set(slots)!={'embedding','rag','agent','knowledge_store'} or not all(isinstance(v,dict) and set(v)=={'enabled','provider'} and v.get('enabled') is False and v.get('provider') is None for v in slots.values()):raise ValueError('Extensions are contracts only; keep enabled=false, provider=null, with no credential fields.')
    return p


def load(path=None):
    return normalize(json.loads(Path(path).read_text(encoding='utf-8')) if path else {})


def flatten(obj,prefix=''):
    result={}
    for k,v in obj.items():
        name=(prefix+'.' if prefix else '')+k
        if isinstance(v,dict) and v:result.update(flatten(v,name))
        else:result[name]=v
    return result


def resolve(saved,signals,scope='workspace'):
    if not isinstance(signals,dict) or set(signals)-{'explicit','memory','context'}:raise ValueError('Signals accepts only normalized explicit/memory/context preference objects, not raw memory.')
    defaults=json.loads((ASSETS/'default-profile.json').read_text(encoding='utf-8'))
    allowed=set(defaults)-{'schema_version','preference_sources','previous_layouts','previous_note_languages'}
    result=copy.deepcopy(defaults);origins={};ignored=[]
    for source,values in [('context',signals.get('context',{})),('memory',signals.get('memory',{})),('saved',saved or {}),('explicit',signals.get('explicit',{}))]:
        if not isinstance(values,dict):raise ValueError('Preference signals must be objects.')
        if source!='saved' and set(values)-allowed:raise ValueError('Unknown preference keys: '+str(sorted(set(values)-allowed)))
        values=copy.deepcopy(values)
        for key in ('preferences','context','palette','layout','extensions'):
            if key in values and source!='saved':
                if not isinstance(values[key],dict) or set(values[key])-set(defaults[key]):raise ValueError('Unknown or malformed normalized '+key+' keys.')
        if source in ('memory','context'):
            for key in list(values):
                if key not in SOFT:ignored.append({'source':source,'key':key,'reason':'Paths, taxonomy and external actions need explicit selection.'});values.pop(key)
        if 'language' in values and 'note_languages' not in values:
            values['note_languages']=['en','zh'] if values['language']=='en-zh' else [values['language']]
        if 'note_languages' in values:
            # Prevent a stale legacy alias from undoing a new explicit choice.
            ls=values['note_languages'];values['language']='en-zh' if ls==['en','zh'] else (ls[0] if len(ls)==1 else 'multilingual')
        result=merge(result,values)
        for key in flatten(values):
            if key not in ('preference_sources','schema_version') and not key.startswith(('previous_','preference_sources.')):
                if source=='saved' and key in values.get('preference_sources',{}):
                    origins[key]=copy.deepcopy(values['preference_sources'][key])
                else:origins[key]={'source':source,'scope':scope}
    result['schema_version']=2
    result['preference_sources']=merge((saved or {}).get('preference_sources',{}),origins)
    return normalize(result),ignored


def save_update(path,profile,expected_hash):
    old=path.read_bytes()
    if hashlib.sha256(old).hexdigest()!=expected_hash:raise ValueError('Profile changed; reread before applying.')
    before=normalize(json.loads(old))
    if before['layout']!=profile['layout']:
        profile['previous_layouts']=before.get('previous_layouts',[])+[before['layout']]
    if before['note_languages']!=profile['note_languages']:
        profile['previous_note_languages']=before.get('previous_note_languages',[])+[before['note_languages']]
    for origin in profile['preference_sources'].values():origin['scope']='workspace'
    data=(json.dumps(normalize(profile),ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    folder=path.parent/'.paper2project-history'
    if folder.is_symlink():raise ValueError('Preference backup directory must not be a symlink.')
    folder.mkdir(exist_ok=True)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=folder/(stamp+'.json')
    with backup.open('xb') as f:f.write(old)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.p2p-',delete=False) as f:
            temp=Path(f.name);f.write(data);f.flush();os.fsync(f.fileno())
        if path.read_bytes()!=old:raise ValueError('Concurrent profile edit; replacement refused.')
        os.replace(temp,path)
        if path.read_bytes()!=data:raise ValueError('Profile readback failed.')
    finally:
        if temp and temp.exists():temp.unlink()
    return {'backup':str(backup),'sha256':hashlib.sha256(data).hexdigest()}
