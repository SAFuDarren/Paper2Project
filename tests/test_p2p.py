"""Isolated behavioral tests; no real vault, network, service or model is used."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE/'scripts/p2p.py'


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2p-test-')
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base/'Academic'
        self.profile = self.base/'profile.json'
        self.profile.write_text(json.dumps({'language': 'en', 'research_scope': 'Synthetic workflow test',
                                           'current_aim': 'Check local organization only'}))

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, expected=0):
        r = subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)
        self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
        return json.loads(r.stdout if r.stdout else r.stderr)

    def initialize(self, root=None, profile=None):
        return self.cli('init', '--root', str(root or self.root), '--profile', str(profile or self.profile),
                        '--non-interactive', '--apply')

    def put(self, relative, content):
        p = self.root/relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return p

    def paper(self, name='Example Paper', note_id='p-one', source='https://arxiv.org/abs/1234.56789v1'):
        return self.put('Library/Computer Science/Machine Learning/Papers/Sequence Models - '+name+'.md',
                        '---\np2p_id: "'+note_id+'"\n---\n\n# '+name+'\n\n**Paper:** '+source+
                        '\n**Version:** synthetic fixture\n**Reading scope:** synthetic test, not source reading.\n\n'
                        '## Research question\n\nSynthetic question.\n\n## Setup and assumptions\n\nFixture only.\n\n'
                        '## Method\n\nFixture passage.\n\n## Results and evidence\n\nNo scientific claim.\n\n'
                        '## Argument chain\n\nFixture steps.\n\n## Relation to our work\n\nTest fixture only.\n\n#paper\n')

    def test_home_shows_known_context_and_preserves_pointers(self):
        values = {'language':'en-zh','research_scope':'Sequence models','current_aim':'A proposal',
                  'context':{'materials':['../papers'],'project_overviews':['../overview.md'],
                             'maintenance_entry':'../existing-task.json'}}
        self.profile.write_text(json.dumps(values))
        self.initialize()
        home=(self.root/'Academic Home.md').read_text()
        self.assertEqual(home.count('Sequence models'),2)
        self.assertEqual(home.count('A proposal'),2)
        cfg=json.loads((self.root/'.paper2project.json').read_text())
        for key,value in values['context'].items():
            self.assertEqual(cfg['context'][key],value)
        self.assertIn('**Next step:**',home)
        self.assertIn('**下一步：**',home)

    def test_malformed_paper_name_metadata_and_sections_are_rejected(self):
        self.initialize()
        p=self.paper()
        renamed=p.with_name('Unprefixed.md')
        p.rename(renamed)
        renamed.write_text(renamed.read_text().replace('## Method','## Wrong heading').replace('**Reading scope:**','**Other:**'))
        errors=self.cli('check','--root',str(self.root),expected=1)['errors']
        self.assertTrue(any('Paper filename needs' in x for x in errors))
        self.assertTrue(any('Paper section missing: Method' in x for x in errors))
        self.assertTrue(any('Paper metadata missing: Reading scope' in x for x in errors))

    def test_paper_prefix_reuses_registered_direction(self):
        self.initialize()
        cfg=json.loads((self.root/'.paper2project.json').read_text())
        cfg['taxonomy']=[{'discipline':'Computer Science','field':'Machine Learning',
                          'direction':'Sequence Models','basis':'Supplied synthetic classification fixture, not evidence verification.'}]
        (self.root/'.paper2project.json').write_text(json.dumps(cfg))
        p=self.paper()
        self.assertEqual(self.cli('check','--root',str(self.root))['warnings'],[])
        p.rename(p.with_name('Invented Direction - Example.md'))
        errors=self.cli('check','--root',str(self.root),expected=1)['errors']
        self.assertTrue(any('prefix differs from registered' in x for x in errors))

    def test_pdf_inside_project_group_requires_provenance_review(self):
        self.initialize()
        prefix='Projects/Computer Science/Machine Learning/Sequence Models/Example Project/'
        self.put(prefix+'Example Project.md','# Example Project\n\n#research-project\n')
        self.put(prefix+'Methods/source.pdf','Synthetic source placeholder only.\n')
        response=self.cli('check','--root',str(self.root))
        self.assertEqual(response['status'],'needs_review')
        self.assertTrue(any('PDF in Projects needs provenance review' in x for x in response['warnings']))

    def test_direction_entry_is_named_and_unique(self):
        self.initialize()
        folder='Projects/Computer Science/Machine Learning/Sequence Models/'
        self.put(folder+'Other.md','# Example\n\n#research-direction\n')
        errors=self.cli('check','--root',str(self.root),expected=1)['errors']
        self.assertTrue(any('Direction entry name' in x for x in errors))
        (self.root/(folder+'Other.md')).unlink()
        self.put(folder+'Sequence Models.md','# Example\n\n#research-direction\n')
        self.put(folder+'Sequence Models - Research Directions.md','# Example\n\n#research-direction\n')
        errors=self.cli('check','--root',str(self.root),expected=1)['errors']
        self.assertTrue(any('Duplicate direction entries' in x for x in errors))

    def test_markdown_links_with_titles_are_checked(self):
        self.initialize()
        self.put('Reading.md','[valid](Library/Library.md "Title")\n[missing](Missing.md \'Title\')\n')
        errors=self.cli('check','--root',str(self.root),expected=1)['errors']
        self.assertEqual(len([x for x in errors if 'Missing link' in x]),1)
        self.assertTrue(any('Missing.md' in x for x in errors))

    def test_ambiguous_role_cannot_be_silently_omitted_from_export(self):
        self.initialize()
        p=self.paper()
        p.write_text(p.read_text()+'\n#concept\n')
        output=self.base/'ambiguous.jsonl'
        response=self.cli('export','--root',str(self.root),'--kind','paper','--output',str(output),expected=2)
        self.assertIn('Ambiguous graph roles',response['message'])
        self.assertFalse(output.exists())

    def test_unregistered_naming_basis_is_needs_review(self):
        self.initialize()
        self.paper()
        result=self.cli('check','--root',str(self.root))
        self.assertEqual(result['structural_status'],'passed')
        self.assertEqual(result['status'],'needs_review')
        self.assertTrue(result['warnings'])

    def test_existing_management_choices_are_saved_without_migration(self):
        values={'language':'en','research_scope':'Synthetic fixture','current_aim':'Handoff design',
                'context':{'management_entry':'Operations/START_HERE.md',
                           'maintenance_entry':'Operations/tasks/existing.json',
                           'task_template':'Operations/specs/task-template.json',
                           'maintenance_directory':'Academic/.maintenance'},
                'preferences':{'preserve_existing':True,'filename_style':'Keep existing descriptive names',
                               'note_detail':'Concise complete methods','navigation_style':'Keep current reading entry'}}
        self.profile.write_text(json.dumps(values))
        self.initialize()
        cfg=json.loads((self.root/'.paper2project.json').read_text())
        for key,value in values['context'].items():
            self.assertEqual(cfg['context'][key],value)
        self.assertEqual(cfg['preferences'],values['preferences'])
        self.assertFalse((self.root/'.maintenance').exists())
        self.assertFalse((self.base/'Operations').exists())

    def test_optional_bilingual_preset_preserves_approved_role_colors(self):
        preset=PACKAGE/'assets/profiles/bilingual-research.json'
        self.initialize(profile=preset)
        cfg=json.loads((self.root/'.paper2project.json').read_text())
        self.assertEqual(cfg['language'],'en-zh')
        self.assertTrue(cfg['preferences']['preserve_existing'])
        self.assertEqual(cfg['palette'],{'field':'#5B9FE6','direction':'#E3B34F','project':'#E57D86','paper':'#5AB8A0','concept':'#AE8CDB'})

    def test_existing_extra_tags_do_not_require_note_rewrites(self):
        self.initialize()
        p=self.paper()
        p.write_text(p.read_text().replace('#paper\n','#paper #selected\n'))
        before=p.read_bytes()
        result=self.cli('check','--root',str(self.root))
        self.assertEqual(result['roles']['paper'],1)
        output=self.base/'extra-tag.jsonl'
        self.cli('export','--root',str(self.root),'--kind','paper','--output',str(output))
        self.assertEqual(json.loads(output.read_text().splitlines()[0])['document_count'],1)
        self.assertEqual(p.read_bytes(),before)

    def test_bilingual_cross_field_project_and_link_preserving_move(self):
        # Entirely synthetic organization, not a source/translation/scientific audit.
        self.profile.write_text(json.dumps({'language':'en-zh','taxonomy':[
            {'discipline':'Computer Science','field':'Machine Learning','direction':'Sequence Models',
             'basis':'User-supplied illustrative classification; validity is not tested here.'},
            {'discipline':'Computer Science','field':'Theoretical Computer Science','direction':'Formal Methods',
             'basis':'User-supplied illustrative classification; validity is not tested here.'}]}))
        self.initialize()
        library='Library/Computer Science/'
        papers=library+'Machine Learning/Papers/'
        concepts=library+'Machine Learning/Concepts/'
        first='Projects/Computer Science/Machine Learning/Sequence Models/'
        second='Projects/Computer Science/Theoretical Computer Science/Formal Methods/'
        project=first+'Synthetic Project/'
        home=project+'Synthetic Project'
        paper=papers+'Sequence Models - Synthetic Paper'
        concept=concepts+'Synthetic Concept'
        other=concepts+'Related Concept'
        one=first+'Sequence Models'
        two=second+'Formal Methods'
        field_one=library+'Machine Learning/Machine Learning'
        field_two=library+'Theoretical Computer Science/Theoretical Computer Science'
        link=lambda value:'[['+value+']]'
        def bilingual(title,body,tag=None,note_id=None):
            header=('---\np2p_id: "'+note_id+'"\n---\n\n') if note_id else ''
            text=header+'# '+title+'\n\nSynthetic organization only. '+body+'\n\n---\n\n# '+title+'\n\n仅为组织结构测试。 '+body+'\n'
            return text+('\n#'+tag+'\n' if tag else '')
        self.put(field_one+'.md',bilingual('Machine Learning',link(paper)+' '+link(one),'research-field'))
        self.put(field_two+'.md',bilingual('Theoretical Computer Science',link(paper)+' '+link(two),'research-field'))
        self.put(concept+'.md',bilingual('Synthetic Concept',link(paper)+' '+link(other),'concept','concept-stable'))
        self.put(other+'.md',bilingual('Related Concept',link(paper)+' '+link(concept),'concept'))
        self.put(one+'.md',bilingual('Sequence Models',link(field_one)+' Literature: '+link(paper)+'; illustrative connection: '+link(two)+'; project: '+link(home),'research-direction'))
        self.put(two+'.md',bilingual('Formal Methods',link(field_two)+' Literature: '+link(paper)+'; illustrative connection: '+link(one)+'; project: '+link(home),'research-direction'))
        records=[]
        for group in ('Problem','Methods','Results','Extensions'):
            record=project+group+'/Record'
            records.append(record)
            self.put(record+'.md',bilingual(group,link(home)+' '+link(paper)+'; synthetic scope only.'))
        self.put(home+'.md',bilingual('Synthetic Project',' '.join(map(link,records+[one,two,paper,concept])),'research-project','project-stable'))
        en_sections=('Research question','Setup and assumptions','Method','Results and evidence','Argument chain','Relation to our work')
        zh_sections=('研究问题','设定与基本假设','方法','结果与证据','论证链路','与我们工作的关系')
        paper_text='---\np2p_id: "paper-stable"\n---\n\n# Synthetic Paper\n\n**Paper:** https://example.org/synthetic-source\n**Reading scope:** Synthetic fixture only.\n'
        for heading in en_sections:
            paper_text+='\n## '+heading+'\n\nNo scientific claim. '+link(concept)+' '+link(home)+'\n'
        paper_text+='\n---\n\n# Synthetic Paper\n\n**论文：** https://example.org/synthetic-source\n**阅读范围：** 仅测试样例。\n'
        for heading in zh_sections:
            paper_text+='\n## '+heading+'\n\n不作科学主张。 '+link(concept)+' '+link(home)+'\n'
        self.put(paper+'.md',paper_text+'\n#paper\n')
        result=self.cli('check','--root',str(self.root))
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['roles'],{'field':2,'paper':1,'concept':2,'direction':2,'project':1,'project-record':4})
        self.assertEqual(result['warnings'],[])
        output=self.base/'complete.jsonl'
        self.cli('export','--root',str(self.root),'--output',str(output))
        docs=[json.loads(x) for x in output.read_text().splitlines()[1:]]
        self.assertEqual(len(docs),12)
        self.assertEqual(len([d for d in docs if d['kind']=='project']),1)
        self.assertEqual(len([d for d in docs if d['kind'] in ('field','direction','project')]),5)
        self.assertEqual(len([d for d in docs if d['kind'] in ('field','direction','project','paper','concept')]),8)
        old=self.root/(concept+'.md');new=self.root/(concept+' Renamed.md')
        old.rename(new)
        for p in self.root.rglob('*.md'):
            p.write_text(p.read_text().replace(link(concept),link(concept+' Renamed')))
        self.assertEqual(self.cli('check','--root',str(self.root))['status'],'passed')
        after=self.base/'moved.jsonl'
        self.cli('export','--root',str(self.root),'--output',str(after))
        moved=[json.loads(x) for x in after.read_text().splitlines()[1:] if json.loads(x)['id']=='concept-stable'][0]
        self.assertTrue(moved['path'].endswith('Synthetic Concept Renamed.md'))

    def test_design_is_read_only_and_creation_is_idempotent(self):
        r = self.cli('init', '--root', str(self.root), '--profile', str(self.profile), '--non-interactive')
        self.assertEqual(r['status'], 'design_only')
        self.assertFalse(self.root.exists())
        self.assertEqual(len(self.initialize()['written']), 5)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.initialize()['status'], 'already_initialized')
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(self.cli('check', '--root', str(self.root))['status'], 'passed')

    def test_existing_user_content_is_preserved(self):
        note = self.put('Important.md', '# Existing user content\n')
        self.cli('init', '--root', str(self.root), '--profile', str(self.profile), '--non-interactive', '--apply', expected=2)
        self.assertEqual(note.read_text(), '# Existing user content\n')
        self.assertEqual(list(self.root.iterdir()), [note])

    def test_nested_vault_prefix_and_bilingual_start(self):
        nested = self.base/'Vault'/'Brain'/'academic'
        self.profile.write_text(json.dumps({'vault_prefix': 'Brain/academic','language':'en-zh'}))
        self.initialize(nested)
        report = self.cli('check', '--root', str(nested))
        self.assertEqual(report['errors'], [])
        home = (nested/'Academic Home.md').read_text()
        self.assertIn('[[Brain/academic/Library/Library]]', home)
        self.assertIn('已有论文与概念', home)

    def test_links_anchors_unicode_periods_and_code_examples(self):
        self.initialize()
        concept = self.put('Library/Computer Science/Machine Learning/Concepts/概念 v1.2.md',
                           '# Example\n\n## Real Heading\n\nBody ^block-one\n\n#concept\n')
        self.put('Reading.md', '[[Library/Computer Science/Machine Learning/Concepts/概念 v1.2#Real Heading]]\n'
                 '[[Library/Computer Science/Machine Learning/Concepts/概念 v1.2#^block-one]]\n'
                 '[relative](<Library/Computer Science/Machine Learning/Concepts/概念%20v1.2.md#real-heading>)\n'
                 '`[[Not a link]]`\n\n```text\n[[Also not a link]]\n```\n')
        self.assertEqual(self.cli('check', '--root', str(self.root))['errors'], [])
        with (self.root/'Reading.md').open('a') as f:
            f.write('[[Missing note]]\n[[Library/Computer Science/Machine Learning/Concepts/概念 v1.2#Absent]]\n')
        errors = self.cli('check', '--root', str(self.root), expected=1)['errors']
        self.assertTrue(any('Missing link' in x for x in errors))
        self.assertTrue(any('Missing anchor' in x for x in errors))

    def test_duplicate_note_ids_and_arxiv_versions(self):
        self.initialize()
        self.paper()
        self.paper('Second', source='https://arxiv.org/abs/1234.56789v2')
        errors = self.cli('check', '--root', str(self.root), expected=1)['errors']
        self.assertTrue(any('Duplicate p2p_id' in x for x in errors))
        self.assertTrue(any('Duplicate paper source' in x for x in errors))

    def test_project_has_one_home_and_typed_records(self):
        self.initialize()
        directory = 'Projects/Computer Science/Machine Learning/Sequence Models/Example Project/'
        self.put(directory+'Example Project.md', '# Example Project\n\n#research-project\n')
        self.put(directory+'Problem/Question.md', '# Question\n\nSynthetic record.\n')
        self.assertEqual(self.cli('check', '--root', str(self.root))['roles']['project-record'], 1)
        self.put(directory+'Another Home.md', '# Another Home\n\n#research-project\n')
        errors = self.cli('check', '--root', str(self.root), expected=1)['errors']
        self.assertTrue(any('Loose file' in x or 'must match' in x for x in errors))

    def test_bilingual_links_must_match(self):
        self.initialize()
        cfg = json.loads((self.root/'.paper2project.json').read_text())
        cfg['language'] = 'en-zh'
        (self.root/'.paper2project.json').write_text(json.dumps(cfg))
        self.put('Library/Computer Science/Machine Learning/Concepts/One.md',
                 '# One\n\n[[Library/Library]]\n\n---\n\n# One\n\n概念。\n\n#concept\n')
        errors = self.cli('check', '--root', str(self.root), expected=1)['errors']
        self.assertTrue(any('Different bilingual link sets' in x for x in errors))

    def test_export_selection_provenance_staleness_and_identity_on_move(self):
        self.initialize()
        p = self.paper()
        out = self.base/'one.jsonl'
        self.cli('export', '--root', str(self.root), '--kind', 'paper', '--output', str(out))
        records = [json.loads(x) for x in out.read_text().splitlines()]
        self.assertEqual(records[0]['document_count'], 1)
        doc = records[1]
        self.assertEqual(doc['id_origin'], 'metadata')
        self.assertFalse(doc['path'].startswith('/'))
        method = next(s for s in doc['sections'] if s['heading'] == 'Method')
        lines = p.read_text().splitlines()
        self.assertEqual(method['text'], '\n'.join(lines[method['start_line']-1:method['end_line']]))
        self.cli('export', '--root', str(self.root), '--output', str(out), expected=2)
        moved = p.with_name('Sequence Models - Renamed.md')
        p.rename(moved)
        moved.write_text(moved.read_text()+'\nAn actual update.\n')
        second = self.base/'two.jsonl'
        self.cli('export', '--root', str(self.root), '--kind', 'paper', '--output', str(second))
        newer = json.loads(second.read_text().splitlines()[1])
        self.assertEqual(newer['id'], doc['id'])
        self.assertNotEqual(newer['path'], doc['path'])
        self.assertNotEqual(newer['content_sha256'], doc['content_sha256'])

    def test_extensions_remain_inert(self):
        self.profile.write_text(json.dumps({'extensions': {'embedding': {'enabled': True, 'provider': 'unselected'}}}))
        self.initialize_error = self.cli('init', '--root', str(self.root), '--profile', str(self.profile),
                                         '--non-interactive', '--apply', expected=2)
        self.assertFalse(self.root.exists())

    def test_windows_line_endings_preserve_export_identity(self):
        self.initialize()
        p = self.paper()
        p.write_bytes(p.read_bytes().replace(b'\n', b'\r\n'))
        out = self.base/'windows.jsonl'
        self.cli('export', '--root', str(self.root), '--kind', 'paper', '--output', str(out))
        doc = json.loads(out.read_text().splitlines()[1])
        self.assertEqual(doc['id'], 'p-one')
        self.assertEqual(doc['id_origin'], 'metadata')

    def test_bad_profile_is_a_structured_error(self):
        self.profile.write_text('[]')
        result = self.cli('init', '--root', str(self.root), '--profile', str(self.profile), '--non-interactive', expected=2)
        self.assertIn('JSON object', result['message'])

    def test_traversal_and_symlinked_sources_are_not_read(self):
        self.initialize()
        outside = self.base/'Private.md'
        outside.write_text('PRIVATE FIXTURE\n#paper\n')
        try:
            (self.root/'Link.md').symlink_to(outside)
        except OSError as exc:
            self.skipTest('Symlink privilege unavailable: '+str(exc))
        self.cli('export', '--root', str(self.root), '--output', str(self.base/'safe.jsonl'))
        self.assertNotIn('PRIVATE FIXTURE', (self.base/'safe.jsonl').read_text())
        self.put('Reading.md', '[[../Private]]\n')
        errors = self.cli('check', '--root', str(self.root), expected=1)['errors']
        self.assertTrue(any('escapes the vault' in x for x in errors))


if __name__ == '__main__':
    unittest.main()
