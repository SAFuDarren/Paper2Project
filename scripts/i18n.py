"""Locale labels and deterministic note frames; supplied prose is never translated."""
import json
from pathlib import Path
import re

ASSETS = Path(__file__).resolve().parents[1]/'assets'
SECTIONS = ('question','setup','method','results','argument','connection','scope','papers',
            'related_research','definition','related_concepts','papers_concepts','opportunities',
            'problem','methods','extensions','research_connections','knowledge_basis','body',
            'basis_scope','evidence','remaining')
LABELS = ('paper','version','field','summary','reading_scope','from_papers','project','record',
          'status','naming_basis','literature','connection','missing_step','next_check','sources')
UI = ('home','library','projects','context','research_scope','current_aim','as_provided','next_step',
      'home_library','home_projects','map_intro','next_action','library_intro','projects_intro')
SPECS = {
    'paper': (('paper','version','field','summary','reading_scope'),SECTIONS[:6]),
    'concept': (('from_papers',),('definition','related_concepts')),
    'field': ((),('scope','papers','related_research')),
    'direction': (('field','naming_basis'),('scope','papers_concepts','opportunities','projects')),
    'project': (('status',),('scope','problem','methods','results','extensions','research_connections','knowledge_basis')),
    'project-record': (('project','record','status'),('body','basis_scope','evidence','remaining')),
}


def validate_pack(pack):
    if isinstance(pack,dict) and set(pack)!={'name','sections','labels','ui'}:raise ValueError('Locale packs contain only name, sections, labels and ui.')
    if not isinstance(pack,dict) or not isinstance(pack.get('name'),str) or not pack['name'].strip():
        raise ValueError('Locale pack needs a display name.')
    for group,keys in [('sections',SECTIONS),('labels',LABELS),('ui',UI)]:
        if not isinstance(pack.get(group),dict) or set(pack[group])!=set(keys):
            raise ValueError('Locale pack needs the complete '+group+' key set.')
        if not all(isinstance(v,str) and v.strip() and '\n' not in v and '\r' not in v for v in pack[group].values()):
            raise ValueError('Locale labels must be nonempty single-line strings.')
        if group in ('sections','labels') and len({v.casefold() for v in pack[group].values()})!=len(keys):
            raise ValueError('Locale '+group+' labels must be distinguishable.')
    return pack


def locale(code,profile):
    packs=json.loads((ASSETS/'locales.json').read_text(encoding='utf-8'))
    packs.update(profile.get('locale_overrides',{}))
    if code in packs:return validate_pack(packs[code])
    # Region variants may share base labels; script variants need their own pack.
    base=code.split('-')[0]
    if re.fullmatch(r'[a-z]{2,3}-[A-Z]{2}',code) and base in packs:
        return validate_pack(packs[base])
    raise ValueError('No locale pack for '+code+'. Supply a complete locale_overrides entry; English is not substituted.')


def join_blocks(blocks):
    return '\n\n---\n\n'.join(block.strip() for block in blocks)+'\n'


def render(kind,card,profile):
    meta_keys,section_keys=SPECS[kind]
    title=card.get('title')
    if not isinstance(title,str) or not title.strip() or '\n' in title:raise ValueError('Card needs a single-line original title.')
    if not isinstance(card.get('id'),str) or not card['id'].strip() or any(c in card['id'] for c in '\n\r'):raise ValueError('Card needs its single-line stable id; preserve it across renders/moves.')
    blocks=[]
    for language in profile['note_languages']:
        loc=locale(language,profile)
        content=card.get('content',{}).get(language)
        if not isinstance(content,dict):raise ValueError('Missing actual supplied content for '+language)
        values={}
        for key in meta_keys:
            value=content.get(key,card.get('metadata',{}).get(key))
            if key in ('summary','reading_scope'):value=content.get(key)
            if not isinstance(value,str) or not value.strip():raise ValueError('Missing '+language+' metadata: '+key)
            if '\n' in value or '\r' in value:raise ValueError('Metadata values must be single-line text.')
            values[key]=value
        for key in section_keys:
            if not isinstance(content.get(key),str) or not content[key].strip():raise ValueError('Missing '+language+' section: '+key)
        colon='：' if language.startswith('zh') else ':'
        metadata='\n'.join('**'+loc['labels'][key]+colon+'** '+values[key]+'  ' for key in meta_keys)
        sections='\n\n'.join('## '+loc['sections'].get(key,loc['ui'].get(key,key))+'\n\n'+content[key] for key in section_keys)
        template=(ASSETS/'templates'/ (kind+'.md')).read_text(encoding='utf-8')
        body=template.replace('{{TITLE}}',title).replace('{{METADATA}}',metadata).replace('{{SECTIONS}}',sections)
        blocks.append(body.strip())
    fields={'p2p_id':card['id'],'p2p_languages':profile['note_languages']}
    if card.get('source_id'):fields['source_id']=card['source_id']
    elif kind=='paper':fields['source_id']=card['content'][profile['note_languages'][0]].get('paper',card.get('metadata',{}).get('paper'))
    if card.get('subfield'):fields['p2p_subfield']=card['subfield']
    front='---\n'+''.join(k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in fields.items())+'---\n\n'
    tag={'field':'research-field','direction':'research-direction','project':'research-project','paper':'paper','concept':'concept'}.get(kind)
    return front+join_blocks(blocks)+(('\n#'+tag+'\n') if tag else '')


def scaffold(profile,query):
    layout=profile['layout'];prefix=profile['vault_prefix'];base=(prefix+'/') if prefix else ''
    link=lambda x:'[['+base+x+']]'
    homes,libraries,projects=[],[],[]
    for language in profile['note_languages']:
        loc=locale(language,profile)['ui']
        colon='：' if language.startswith('zh') else ':'
        context=''
        if profile['research_scope'] or profile['current_aim']:
            context='## '+loc['context']+'\n\n'
            for key in ('research_scope','current_aim'):
                if profile[key]:
                    # Literal user text, explicitly labelled; no translation claim.
                    text=' '.join(profile[key].splitlines());ticks='`'*(max([len(x) for x in re.findall(r'`+',text)] or [0])+1)
                    context+='**'+loc[key]+' ('+loc['as_provided']+'):** '+ticks+' '+text+' '+ticks+'  \n'
            context+='\n'
        homes.append('# '+loc['home']+'\n\n'+context+'- '+link(layout['library']+'/'+layout['library'])+' — '+loc['home_library']+'\n- '+link(layout['projects']+'/'+layout['projects'])+' — '+loc['home_projects']+'\n\n'+loc['map_intro']+'\n\n**'+loc['next_step']+colon+'** '+loc['next_action'])
        libraries.append('# '+loc['library']+'\n\n'+loc['library_intro'])
        projects.append('# '+loc['projects']+'\n\n'+loc['projects_intro'])
    return {layout['home']+'.md':join_blocks(homes),
            layout['library']+'/'+layout['library']+'.md':join_blocks(libraries),
            layout['projects']+'/'+layout['projects']+'.md':join_blocks(projects)}
