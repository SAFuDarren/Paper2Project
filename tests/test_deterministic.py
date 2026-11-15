"""Deterministic steps run by the program: vault detection, fixed structure, indexes, tags, render paths, migration."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE/'scripts/p2p.py'
FIELD = 'Library/Computer Science/Machine Learning/'
SECTIONS = ('summary', 'reading_scope', 'question', 'setup', 'method', 'results', 'argument', 'connection')


class DeterministicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2p-det-')
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base/'Academic'
        self.profile = self.base/'profile.json'
        self.profile.write_text(json.dumps({'language': 'en'}))

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, expected=0):
        r = subprocess.run([sys.executable, str(SCRIPT), *args], encoding='utf-8', capture_output=True)
        self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
        return json.loads(r.stdout if r.stdout else r.stderr)

    def init(self, *extra, root=None, expected=0):
        return self.cli('init', '--root', str(root or self.root), '--profile', str(self.profile),
                        '--non-interactive', '--apply', *extra, expected=expected)

    def put(self, relative, content, root=None):
        p = (root or self.root)/relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return p

    def card(self, name='card.json', languages=('en',), **values):
        card = {'title': 'Attention Is All You Need', 'discipline': 'Computer Science', 'field': 'Machine Learning',
                'subfield': 'Sequence Models', 'short_title': 'Transformer',
                'metadata': {'paper': 'https://arxiv.org/abs/1706.03762', 'version': 'v7', 'field': 'Machine Learning'},
                'content': {x: {k: 'Fixture ' + k for k in SECTIONS} for x in languages}}
        card.update(values)
        path = self.base/name
        path.write_text(json.dumps(card))
        return path

    def render(self, kind='paper', card=None, *extra, expected=0):
        return self.cli('render', '--root', str(self.root), '--kind', kind, '--input', str(card or self.card()),
                        '--apply', *extra, expected=expected)

    def check(self, expected=0):
        return self.cli('check', '--root', str(self.root), expected=expected)

    # --- the user chooses the folder; the vault prefix is derived ------------------------

    def test_vault_prefix_is_derived_from_the_enclosing_vault(self):
        vault = self.base/'Vault'
        (vault/'.obsidian').mkdir(parents=True)
        root = vault/'research'
        result = self.init(root=root)
        self.assertEqual(json.loads((root/'.paper2project.json').read_text(encoding='utf-8'))['vault_prefix'], 'research')
        self.assertTrue((vault/'.obsidian/bookmarks.json').is_file())
        self.assertTrue(result['views']['views']['Full Network'].startswith('path:"research/" '))

    def test_several_enclosing_vaults_need_an_explicit_choice(self):
        outer = self.base/'Vault'
        (outer/'.obsidian').mkdir(parents=True)
        (outer/'Notes/.obsidian').mkdir(parents=True)
        root = outer/'Notes/academic'
        self.assertIn('--vault', self.init(root=root, expected=2)['message'])
        self.assertFalse(root.exists())
        self.init('--vault', str(outer), root=root)
        self.assertEqual(json.loads((root/'.paper2project.json').read_text(encoding='utf-8'))['vault_prefix'], 'Notes/academic')
        self.assertIn('parent folders', self.cli('init', '--root', str(self.base/'elsewhere'), '--profile', str(self.profile),
                                      '--non-interactive', '--vault', str(outer), expected=2)['message'])

    # --- the structure under the folder is fixed ------------------------------------------

    def test_notes_outside_the_designed_structure_are_reported(self):
        self.init()
        self.put('Scratch.md', '# Scratch\n')
        self.put('notes/Idea.md', '# Idea\n')
        self.put(FIELD + 'Loose note.md', '# Loose\n')
        result = self.check()
        self.assertEqual(result['navigation']['outside_structure'], 2)
        self.assertEqual(result['navigation']['untagged'], 1)
        self.assertEqual(result['navigation']['status'], 'incomplete')
        # Declared management pointers are allowed inside the root.
        cfg = json.loads((self.root/'.paper2project.json').read_text(encoding='utf-8'))
        cfg['context']['management_entry'] = 'notes/Idea.md'
        (self.root/'.paper2project.json').write_text(json.dumps(cfg))
        self.assertEqual(self.check()['navigation']['outside_structure'], 1)

    def test_fresh_workspace_reports_complete_navigation(self):
        self.init()
        nav = self.check()['navigation']
        self.assertEqual(nav, {'initialized': True, 'views': 'present', 'untagged': 0, 'unconnected': 0,
                               'missing_field_indexes': 0, 'outside_structure': 0, 'status': 'complete'})
        (self.root/'.obsidian/bookmarks.json').write_text('{"items": []}')
        result = self.check()
        self.assertEqual(result['navigation']['views'], 'missing')
        self.assertTrue(any('views --apply' in x for x in result['warnings']))

    # --- render: identity, path and navigation are program-made ---------------------------

    def test_render_derives_path_id_and_links_the_field_index(self):
        self.profile.write_text(json.dumps({'language': 'en-zh'}))
        self.init()
        result = self.render(card=self.card(languages=('en', 'zh')))
        self.assertTrue(result['path'].endswith(FIELD + 'Papers/Sequence Models - Transformer.md'))
        self.assertRegex(result['id'], r'^[0-9a-f-]{36}$')
        self.assertIn({'path': FIELD + 'Machine Learning.md', 'action': 'create'}, result['navigation']['changes'])
        index = (self.root/FIELD/'Machine Learning.md').read_text(encoding='utf-8')
        self.assertEqual(index.count('[[' + FIELD + 'Papers/Sequence Models - Transformer|Attention Is All You Need]]'), 2)
        self.assertIn('**论文：**', index)
        self.assertTrue(index.rstrip().endswith('#research-field'))
        self.assertIn('[[' + FIELD + 'Machine Learning|Machine Learning]]', (self.root/'Library/Library.md').read_text(encoding='utf-8'))
        self.assertEqual(self.check()['navigation']['status'], 'complete')
        self.assertEqual(self.cli('index', '--root', str(self.root), '--apply')['status'], 'unchanged')

    def test_render_rejects_unportable_names_and_missing_classification(self):
        self.init()
        self.assertIn('portable', self.render(card=self.card(short_title='A/B: C'), expected=2)['message'])
        self.assertIn('discipline', self.render(card=self.card(discipline=None), expected=2)['message'])
        self.assertFalse((self.root/'Library/Computer Science').exists())

    def test_field_note_replaces_the_generated_index_and_keeps_its_id_and_links(self):
        self.init()
        self.render()
        generated = (self.root/FIELD/'Machine Learning.md').read_text(encoding='utf-8')
        field_card = self.card('field.json', title='Machine Learning',
                               content={'en': {'scope': 'Learning from data.', 'papers': 'Sequence models.',
                                               'related_research': 'None yet.'}})
        self.render('field', field_card)
        text = (self.root/FIELD/'Machine Learning.md').read_text(encoding='utf-8')
        self.assertIn('Learning from data.', text)
        self.assertEqual(generated.split('\n')[1], text.split('\n')[1])  # same p2p_id line
        self.assertIn('Sequence Models - Transformer|Attention Is All You Need]]', text)
        self.assertTrue(text.rstrip().endswith('#research-field'))
        self.assertIn('exists', self.render('field', field_card, expected=2)['message'])

    def test_index_links_directions_and_project_homes(self):
        self.init()
        projects = 'Projects/Computer Science/Machine Learning/Sequence Models/'
        self.put(projects + 'Sequence Models.md', '# Sequence Models\n\nOpportunities.\n\n#research-direction\n')
        self.put(projects + 'Long Context/Long Context.md', '# Long Context\n\n#research-project\n')
        self.cli('index', '--root', str(self.root), '--apply')
        direction = (self.root/projects/'Sequence Models.md').read_text(encoding='utf-8')
        self.assertIn('[[' + projects + 'Long Context/Long Context|Long Context]]', direction)
        self.assertTrue(direction.rstrip().endswith('#research-direction'))
        self.assertIn('Sequence Models|Sequence Models]]', (self.root/FIELD/'Machine Learning.md').read_text(encoding='utf-8'))
        self.assertIn('Sequence Models|Sequence Models]]', (self.root/'Projects/Projects.md').read_text(encoding='utf-8'))
        self.put(projects + 'Long Context/Results/Recall gain.md', '# Recall gain\n\nMeasured.\n')
        self.cli('index', '--root', str(self.root), '--apply')
        home = (self.root/projects/'Long Context/Long Context.md').read_text(encoding='utf-8')
        self.assertIn('**Results:**\n- [[' + projects + 'Long Context/Results/Recall gain|Recall gain]]', home)
        self.assertTrue(home.rstrip().endswith('#research-project'))

    def test_index_never_rewrites_an_untagged_note_at_the_index_path(self):
        self.init()
        self.render()
        index = self.root/FIELD/'Machine Learning.md'
        index.write_text('# My own page\n')
        changes = self.cli('index', '--root', str(self.root), '--apply')['changes']
        self.assertNotIn(FIELD + 'Machine Learning.md', [x['path'] for x in changes])
        self.assertNotIn('Machine Learning', (self.root/'Library/Library.md').read_text(encoding='utf-8').split('p2p:index')[1])
        self.assertEqual(self.check()['navigation']['missing_field_indexes'], 1)
        self.assertEqual(index.read_text(encoding='utf-8'), '# My own page\n')

    # --- tag: the user approves a plan, the program writes it -----------------------------

    def test_tag_appends_only_approved_roles_and_refuses_conflicts(self):
        self.init()
        note = self.put(FIELD + 'Papers/Sequence Models - Old.md', '# Old\r\n\r\nBody kept.\r\n')
        concept = self.put(FIELD + 'Concepts/Attention.md', '# Attention\n\n#concept\n')
        plan = self.base/'roles.json'
        plan.write_text(json.dumps({'roles': {FIELD + 'Papers/Sequence Models - Old.md': 'paper',
                                              FIELD + 'Concepts/Attention.md': 'paper'}}))
        self.assertIn('already has role concept', self.cli('tag', '--root', str(self.root), '--plan', str(plan), '--apply', expected=2)['message'])
        self.assertEqual(note.read_bytes(), b'# Old\r\n\r\nBody kept.\r\n')
        plan.write_text(json.dumps({'roles': {FIELD + 'Papers/Sequence Models - Old.md': 'paper'}}))
        self.assertEqual(self.cli('tag', '--root', str(self.root), '--plan', str(plan))['changes'][0]['action'], 'tag')
        self.assertEqual(note.read_bytes(), b'# Old\r\n\r\nBody kept.\r\n')
        result = self.cli('tag', '--root', str(self.root), '--plan', str(plan), '--apply')
        self.assertEqual(note.read_bytes(), b'# Old\r\n\r\nBody kept.\r\n\r\n#paper\r\n')
        self.assertTrue(result['navigation']['changes'])
        self.assertEqual(self.cli('tag', '--root', str(self.root), '--plan', str(plan), '--apply')['status'], 'unchanged')
        self.assertEqual(concept.read_text(encoding='utf-8'), '# Attention\n\n#concept\n')
        plan.write_text(json.dumps({'roles': {'../outside.md': 'paper'}}))
        self.cli('tag', '--root', str(self.root), '--plan', str(plan), expected=2)

    # --- migrate: moves and link rewriting are exact and recorded -------------------------

    def adopted_vault(self):
        self.put('research/paper_notes/P001.md', '# P001\n\nSee [[P002]] and [[research/paper_notes/P002#Method|method]].\n'
                 '![[figure.png]] [relative](P002.md) `[[P002]]` stays code.\n')
        self.put('research/paper_notes/P002.md', '# P002\n\n## Method\n\nBack to [[P001|first]].\n')
        self.put('research/paper_notes/figure.png', 'png-bytes')
        self.put('Home notes.md', '| a | [[research/paper_notes/P001\\|P1]] |\n')
        self.cli('init', '--root', str(self.root), '--profile', str(self.profile), '--non-interactive', '--adopt', '--apply')

    def test_migrate_moves_files_rewrites_links_and_keeps_a_record(self):
        self.adopted_vault()
        papers = FIELD + 'Papers/'
        moves = {'research/paper_notes/P001.md': papers + 'Sequence Models - P001.md',
                 'research/paper_notes/P002.md': papers + 'Sequence Models - P002.md',
                 'research/paper_notes/figure.png': papers + 'figure.png'}
        plan = self.base/'map.json'
        plan.write_text(json.dumps({'moves': moves}))
        preview = self.cli('migrate', '--root', str(self.root), '--map', str(plan))
        self.assertEqual(preview['status'], 'preview')
        self.assertTrue((self.root/'research/paper_notes/P001.md').exists())
        before = (self.root/'research/paper_notes/P001.md').read_text(encoding='utf-8')
        result = self.cli('migrate', '--root', str(self.root), '--map', str(plan), '--apply')
        self.assertEqual(result['status'], 'migrated')
        self.assertFalse((self.root/'research').exists())  # emptied folders removed
        one = (self.root/papers/'Sequence Models - P001.md').read_text(encoding='utf-8')
        self.assertIn('[[' + papers + 'Sequence Models - P002]]', one)
        self.assertIn('[[' + papers + 'Sequence Models - P002#Method|method]]', one)
        self.assertIn('![[' + papers + 'figure.png]]', one)
        self.assertIn('[relative](Sequence%20Models%20-%20P002.md)', one)
        self.assertIn('`[[P002]]`', one)
        self.assertIn('[[' + papers + 'Sequence Models - P001|first]]', (self.root/papers/'Sequence Models - P002.md').read_text(encoding='utf-8'))
        self.assertIn('[[' + papers + 'Sequence Models - P001\\|P1]]', (self.root/'Home notes.md').read_text(encoding='utf-8'))
        record = Path(result['record'])
        self.assertEqual((record/'before/research/paper_notes/P001.md').read_text(encoding='utf-8'), before)
        self.assertEqual(json.loads((record/'map.json').read_text(encoding='utf-8'))['moves']['research/paper_notes/P001.md'],
                         papers + 'Sequence Models - P001.md')
        self.assertFalse([x for x in self.check(expected=1)['errors'] if 'Missing link' in x])

    def test_migrate_refuses_collisions_and_changes_nothing(self):
        self.adopted_vault()
        plan = self.base/'map.json'
        plan.write_text(json.dumps({'moves': {'research/paper_notes/P001.md': 'research/paper_notes/P002.md'}}))
        self.cli('migrate', '--root', str(self.root), '--map', str(plan), '--apply', expected=2)
        plan.write_text(json.dumps({'moves': {'research/paper_notes/P001.md': 'research/paper_notes/P001.txt'}}))
        self.cli('migrate', '--root', str(self.root), '--map', str(plan), '--apply', expected=2)
        self.assertTrue((self.root/'research/paper_notes/P001.md').exists())
        self.assertFalse((self.root/'.maintenance').exists())

    def test_moving_a_paper_to_another_field_refreshes_both_indexes(self):
        self.init()
        self.render()
        new = 'Library/Computer Science/Information Retrieval/Papers/Sequence Models - Transformer.md'
        plan = self.base/'map.json'
        plan.write_text(json.dumps({'moves': {FIELD + 'Papers/Sequence Models - Transformer.md': new}}))
        self.cli('migrate', '--root', str(self.root), '--map', str(plan), '--apply')
        old_index = (self.root/FIELD/'Machine Learning.md').read_text(encoding='utf-8')
        self.assertNotIn('Transformer', old_index)
        self.assertIn('Transformer|Attention', (self.root/'Library/Computer Science/Information Retrieval/Information Retrieval.md').read_text(encoding='utf-8'))
        result = self.check()
        self.assertFalse([x for x in result['errors'] if 'Missing link' in x])
        self.assertEqual(result['navigation']['unconnected'], 0)

    def test_short_wikilinks_resolve_like_obsidian(self):
        self.adopted_vault()
        result = self.check()
        self.assertFalse([x for x in result['errors'] if 'Missing link' in x])
        self.assertTrue(any('resolve by file name only' in x for x in result['warnings']))
        self.put('elsewhere/P002.md', '# Duplicate name\n')
        self.assertTrue(any('Ambiguous short link' in x for x in self.check(expected=1)['errors']))


if __name__ == '__main__':
    unittest.main()
