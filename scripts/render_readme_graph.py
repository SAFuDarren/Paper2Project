#!/usr/bin/env python3
"""Rebuild the README's synthetic SVG illustrations (Python standard library)."""
from pathlib import Path
from html import escape
import json
import hashlib
import re
import math
import random

ROOT = Path(__file__).resolve().parents[1]
PALETTE = json.loads((ROOT / 'assets/default-profile.json').read_text(encoding='utf-8'))['palette']
COPY = {
    'en': {
        'title': 'A growing network for your research.',
        'sub': 'Keep the sources. Connect the ideas. Develop your contribution.',
        'sample': 'ILLUSTRATIVE WORKSPACE',
        'map': 'Research Map', 'map_sub': 'Follow the branches.',
        'full': 'Full Network', 'full_sub': 'Explore the papers and concepts behind them.',
        'field_a': 'Your field', 'field_b': 'Related field',
        'direction_a': 'Direction A', 'direction_b': 'Direction B', 'direction_c': 'Direction C',
        'pa': 'Project A', 'pb': 'Project B',
        'paper_a': 'Paper A', 'paper_b': 'Paper B', 'shared': 'Shared concept',
        'field': 'Fields', 'direction': 'Potential directions', 'project': 'Projects',
        'paper': 'Papers', 'concept': 'Concepts',
        'bridge': 'candidate connection', 'same': 'Two views. The same connected notes.',
        'foot': 'Synthetic notes and links · Example colors are customizable',
        'knowledge': 'LIBRARY', 'create': 'PROJECTS',
        'left_note': 'Papers & shared concepts', 'right_note': 'Questions & your contribution',
    },
    'zh-CN': {
        'title': '让读过的论文，长成可以发展的研究。',
        'sub': '保留来源，连接概念，找到方向，积累自己的贡献。',
        'sample': '模拟工作区',
        'map': 'Research Map', 'map_sub': '先看清研究的枝干。',
        'full': 'Full Network', 'full_sub': '再展开背后的论文与概念。',
        'field_a': '你的领域', 'field_b': '相关领域',
        'direction_a': '研究方向 A', 'direction_b': '研究方向 B', 'direction_c': '研究方向 C',
        'pa': '项目 A', 'pb': '项目 B',
        'paper_a': '论文 A', 'paper_b': '论文 B', 'shared': '共享概念',
        'field': '领域', 'direction': '潜在研究方向', 'project': '具体项目',
        'paper': '论文', 'concept': '概念',
        'bridge': '候选联系', 'same': '两个视图，同一套相互连接的笔记。',
        'foot': '节点与连线均为模拟 · 各类颜色可按偏好调整',
        'knowledge': 'LIBRARY', 'create': 'PROJECTS',
        'left_note': '已有论文与共享概念', 'right_note': '研究问题与我们的增量',
    },
}


def build(locale):
    t = COPY[locale]
    rng = random.Random(427)
    out = []
    def add(s): out.append(s)
    def text(x, y, value, size=24, color='#c4cbd6', weight=400, anchor='start', extra=''):
        add(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" {extra}>{escape(value)}</text>')
    def line(x1, y1, x2, y2, color='#6e7b8f', opacity=.3, width=1.2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" opacity="{opacity}" stroke-width="{width}"{d}/>')
    def circle(x, y, radius, role, halo=False):
        c = PALETTE[role]
        if halo:
            add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius+9}" fill="{c}" opacity=".07"/>')
        add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{c}"/>')
    def label(x, y, value, size=22, anchor='start'):
        text(x, y, value, size, '#d6dce6', 500, anchor,
             'paint-order="stroke" stroke="#171c24" stroke-width="7" stroke-linejoin="round"')

    add('<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000" role="img" aria-labelledby="title desc">')
    add(f'<title id="title">{escape(t["title"])}</title>')
    add('<desc id="desc">Synthetic Paper2Project illustration. Left: fields, potential research directions and unique project homes. Right: the same branches expanded into fictional papers and shared concepts. No actual research findings or application interface are depicted.</desc>')
    add('<defs><radialGradient id="ambient"><stop stop-color="#243446" stop-opacity=".35"/><stop offset="1" stop-color="#11151c" stop-opacity="0"/></radialGradient></defs>')
    add('<g font-family="Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Arial, PingFang SC, Microsoft YaHei, sans-serif">')
    add('<rect width="1600" height="1000" rx="24" fill="#11151c"/>')
    add('<ellipse cx="1055" cy="460" rx="600" ry="440" fill="url(#ambient)"/>')
    text(48, 58, 'Paper2Project', 24, '#a5b2c4', 600)
    text(1552, 58, t['sample'], 18, '#8c99ac', 500, 'end', 'letter-spacing="2"')
    text(48, 127, t['title'], 44, '#f0f2f6', 650)
    text(48, 170, t['sub'], 24, '#9ca9bc')
    add('<rect x="40" y="208" width="440" height="606" rx="18" fill="#171c24" stroke="#29313d"/>')
    add('<rect x="500" y="208" width="1060" height="606" rx="18" fill="#171c24" stroke="#29313d"/>')
    text(68, 252, t['map'], 29, '#f0f2f6', 600)
    text(68, 287, t['map_sub'], 22, '#9ba9bc')
    text(528, 252, t['full'], 29, '#f0f2f6', 600)
    text(528, 287, t['full_sub'], 22, '#9ba9bc')
    # One model, two views. Left view suppresses papers/concepts rather than
    # inventing another taxonomy. All nodes and relationships are fictional.
    macro = [
        (170, 366, 'field', 'field_a'), (380, 366, 'field', 'field_b'),
        (154, 505, 'direction', 'direction_a'), (278, 505, 'direction', 'direction_b'),
        (355, 625, 'direction', 'direction_c'),
        (166, 711, 'project', 'pa'), (301, 758, 'project', 'pb'),
    ]
    edges = [(0, 2), (1, 3), (1, 4), (2, 5), (3, 5), (3, 6), (4, 6)]
    for a,b in edges:
        line(*macro[a][:2], *macro[b][:2], opacity=.5, width=2)
    line(*macro[2][:2], *macro[3][:2], color=PALETTE['direction'], opacity=.6, width=1.7, dash='5 6')
    text(197, 464, t['bridge'], 17, '#c7a65d', anchor='middle')
    for x,y,role,key in macro:
        circle(x,y,11 if role=='field' else 9,role,True)
        offset = -23 if role=='field' else 36
        # The three direction labels are staggered to preserve readable gaps.
        if key=='direction_b':
            label(x+6,y-25,t[key],20,'middle')
        else:
            label(x,y+offset,t[key],20,'middle')

    # Pinned macro nodes preserve the branch identity across both views.
    full_macro = [
        (725,354,'field','field_a'), (1345,371,'field','field_b'),
        (810,486,'direction','direction_a'), (1087,544,'direction','direction_b'),
        (1300,648,'direction','direction_c'),
        (875,688,'project','pa'), (1136,726,'project','pb'),
    ]
    nodes = [{'x':x,'y':y,'role':role,'r':12 if role=='field' else 10,'key':key}
             for x,y,role,key in full_macro]
    links = [(a,b,'macro') for a,b in edges]
    centers = [(775,508),(1095,497),(1283,615)]
    concept_ids = []
    paper_ids = []
    for group,(cx,cy) in enumerate(centers):
        local_concepts = []
        for j in range(7):
            angle = j*math.tau/7 + group*.65
            x = cx + math.cos(angle)*(76+rng.random()*72)
            y = cy + math.sin(angle)*(68+rng.random()*48)
            idx = len(nodes)
            nodes.append({'x':x,'y':y,'role':'concept','r':rng.choice([5,6,8,10]),'group':group})
            local_concepts.append(idx)
            concept_ids.append(idx)
            links.append((group+2,idx,'normal'))
        for j in range(34):
            angle = rng.random()*math.tau
            radius = math.sqrt(rng.random())
            x = cx + math.cos(angle)*radius*195
            y = cy + math.sin(angle)*radius*174
            # Keep the graph within the panel and below its heading.
            x = min(1513,max(552,x)); y = min(772,max(330,y))
            # A small deterministic collision pass keeps individual dots legible.
            for _ in range(25):
                close = next((n for n in nodes if math.hypot(x-n['x'],y-n['y']) < n['r']+8),None)
                if close is None: break
                angle += .54
                x = min(1513,max(552,cx+math.cos(angle)*radius*205))
                y = min(772,max(330,cy+math.sin(angle)*radius*184))
                radius = min(1,radius+.02)
            idx = len(nodes)
            nodes.append({'x':x,'y':y,'role':'paper','r':rng.choice([3,3.6,4.2]),'group':group})
            paper_ids.append(idx)
            for c in rng.sample(local_concepts,2): links.append((idx,c,'normal'))
            if j%4==0: links.append((idx,group+2,'normal'))
    for group in range(3):
        c = concept_ids[group*7:(group+1)*7]
        for j in range(7): links.append((c[j],c[(j+2)%7],'normal'))
    for a,b in [(0,8),(2,16),(5,19),(9,18),(12,20),(4,14)]:
        links.append((concept_ids[a],concept_ids[b],'normal'))
    for p,cs in [(5,[2,5,8]),(6,[9,14,19])]:
        for c in cs: links.append((p,concept_ids[c],'normal'))
    example_ids = []
    for x,y,role,key in [(842,350,'paper','paper_a'), (1183,344,'paper','paper_b'),
                         (1000,630,'concept','shared')]:
        example_ids.append(len(nodes))
        nodes.append({'x':x,'y':y,'role':role,'r':6 if role=='paper' else 9})
    for a,b in [(example_ids[0],example_ids[2]),(example_ids[1],example_ids[2]),(example_ids[2],5)]:
        links.append((a,b,'example'))
    for a,b,kind in links:
        n,m = nodes[a],nodes[b]
        line(n['x'],n['y'],m['x'],m['y'],opacity=.55 if kind=='example' else (.4 if kind=='macro' else .23),
             width=1.5 if kind in ('macro','example') else .9)
    # Dashed sample opportunity; it is deliberately not a proved transfer.
    line(*full_macro[2][:2],*full_macro[3][:2],color=PALETTE['direction'],opacity=.65,width=1.7,dash='5 6')
    for n in sorted(nodes,key=lambda n: n['r']):
        circle(n['x'],n['y'],n['r'],n['role'],n.get('key') is not None)
    for x,y,role,key in full_macro:
        if key in ('field_a','field_b'):
            label(x,y-24,t[key],22,'middle')
        elif key in ('pa','pb'):
            label(x+18,y+7,t[key],21)
        elif key=='direction_a': label(x-18,y-23,t[key],21,'end')
        elif key=='direction_b': label(x+21,y+7,t[key],21)
        else: label(x+19,y+8,t[key],21)
    label(842,329,t['paper_a'],20,'middle')
    label(1183,323,t['paper_b'],20,'middle')
    label(1000,609,t['shared'],20,'middle')
    line(48,850,1552,850,opacity=.35)
    legend = [('field',76),('direction',290),('project',640),('paper',882),('concept',1097)]
    for role,x in legend:
        circle(x,887,7,role)
        text(x+19,895,t[role],23,'#c6cfdb')
    text(48,949,t['same'],24,'#d8dfe9',500)
    text(1552,949,t['foot'],19,'#8290a4',anchor='end')
    add('</g></svg>')
    return '\n'.join(out)+'\n'


def main():
    dest = ROOT / 'assets/readme'
    # The filename changes with the image bytes, so README updates never reuse
    # an older image URL. Each language has one active generated illustration.
    pattern = re.compile(r'\]\((assets/readme/research-network(?:\.[A-Za-z0-9-]+)*\.svg)\)')
    plans = []
    for locale in COPY:
        content = build(locale)
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]
        name = f'research-network.{locale}.{digest}.svg'
        readme = ROOT / ('README.md' if locale == 'en' else 'README.zh-CN.md')
        body = readme.read_text(encoding='utf-8')
        matches = pattern.findall(body)
        if len(matches) != 1:
            raise ValueError(f'{readme.name}: expected one generated illustration link')
        old_path = ROOT / matches[0]
        new_path = dest / name
        updated = pattern.sub(f'](assets/readme/{name})', body, count=1)
        plans.append((new_path, content, readme, updated, old_path))
    dest.mkdir(parents=True, exist_ok=True)
    active = {p[0] for p in plans}
    for new_path, content, readme, updated, old_path in plans:
        new_path.write_text(content, encoding='utf-8', newline='')
        readme.write_text(updated, encoding='utf-8', newline='')
        if old_path not in active and old_path.is_file():
            old_path.unlink()
        print(new_path.relative_to(ROOT))


if __name__ == '__main__':
    main()
