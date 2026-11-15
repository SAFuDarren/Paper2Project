"""First-use graph views, graph connectivity warnings and Obsidian-compatible tags/links."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE/'scripts/p2p.py'
FIELD = 'Library/Computer Science/Machine Learning/'
FULL = ('(tag:#research-field OR tag:#research-direction OR tag:#research-project '
        'OR tag:#paper OR tag:#concept)')


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2p-views-')
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

    def init(self, *extra, root=None):
        return self.cli('init', '--root', str(root or self.root), '--profile', str(self.profile),
                        '--non-interactive', '--apply', *extra)

    def put(self, relative, content, root=None):
        p = (root or self.root)/relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return p

    def paper(self, name='Example', tags='\n#paper\n', extra=''):
        return self.put(FIELD+'Papers/Sequence Models - '+name+'.md',
                        '# '+name+'\n\n**Paper:** https://example.org/'+name+'\n**Reading scope:** fixture.\n\n'
                        '## Research question\n\nQ.'+extra+'\n\n## Setup and assumptions\n\nS.\n\n## Method\n\nM.\n\n'
                        '## Results and evidence\n\nR.\n\n## Argument chain\n\nA.\n\n## Relation to our work\n\nN.\n'+tags)

    def bookmarks(self, vault=None):
        return json.loads(((vault or self.root)/'.obsidian/bookmarks.json').read_text(encoding='utf-8'))

    def group(self, data):
        return [x for x in data['items'] if x.get('title') == 'Paper2Project'][0]

    def check(self):
        return self.cli('check', '--root', str(self.root))

    # --- first use creates bookmarks and views -------------------------------------------

    def test_init_creates_both_graph_views_and_home_bookmark(self):
        result = self.init()
        self.assertEqual(result['views']['status'], 'written')
        items = {x.get('title') or x.get('path'): x for x in self.group(self.bookmarks())['items']}
        self.assertEqual(items['Full Network']['options']['search'], FULL)
        self.assertEqual(items['Research Map']['options']['search'],
                         '(tag:#research-field OR tag:#research-direction OR tag:#research-project)')
        colors = {g['query']: g['color']['rgb'] for g in items['Full Network']['options']['colorGroups']}
        self.assertEqual(colors['tag:#research-field'], 0x5B9FE6)
        self.assertEqual(colors['tag:#paper'], 0x5AB8A0)
        self.assertEqual(len(colors), 5)
        self.assertEqual(len(items['Research Map']['options']['colorGroups']), 3)
        self.assertEqual(items['Academic Home.md']['type'], 'file')

    def test_views_are_idempotent_and_keep_user_bookmarks_and_layout(self):
        self.init('--no-views')
        before = self.put('.obsidian/bookmarks.json', json.dumps({'items': [
            {'type': 'file', 'ctime': 1, 'path': 'Mine.md'},
            {'type': 'group', 'ctime': 2, 'title': 'Other', 'items': [{'type': 'search', 'ctime': 3, 'query': 'x'}]}]})).read_bytes()
        self.cli('views', '--root', str(self.root), '--apply')
        data = self.bookmarks()
        self.assertEqual(data['items'][0], {'type': 'file', 'ctime': 1, 'path': 'Mine.md'})
        self.assertEqual(data['items'][1]['title'], 'Other')
        backups = list((self.root/'.obsidian').glob('bookmarks.json.p2p-backup-*'))
        self.assertEqual([x.read_bytes() for x in backups], [before])
        # The user moves the graph around; a rerun keeps that and writes nothing.
        full = [x for x in self.group(data)['items'] if x.get('title') == 'Full Network'][0]
        full['options']['scale'] = 0.4
        (self.root/'.obsidian/bookmarks.json').write_text(json.dumps(data))
        again = self.cli('views', '--root', str(self.root), '--apply')
        self.assertEqual(again['status'], 'unchanged')
        self.assertEqual({x['action'] for x in again['actions']}, {'unchanged'})
        # A palette change refreshes only colors and scope, not the user's layout.
        cfg = json.loads((self.root/'.paper2project.json').read_text(encoding='utf-8'))
        cfg['palette']['paper'] = '#112233'
        (self.root/'.paper2project.json').write_text(json.dumps(cfg))
        self.assertEqual(self.cli('views', '--root', str(self.root), '--apply')['status'], 'written')
        full = [x for x in self.group(self.bookmarks())['items'] if x.get('title') == 'Full Network'][0]
        self.assertEqual(full['options']['scale'], 0.4)
        self.assertIn({'query': 'tag:#paper', 'color': {'a': 1, 'rgb': 0x112233}}, full['options']['colorGroups'])

    def test_equivalent_user_view_is_not_duplicated(self):
        self.init('--no-views')
        self.put('.obsidian/bookmarks.json', json.dumps({'items': [{'type': 'group', 'ctime': 1, 'title': 'Academic', 'items': [
            {'type': 'graph', 'ctime': 2, 'title': 'My network', 'options': {'search': FULL}}]}]}))
        result = self.cli('views', '--root', str(self.root), '--apply')
        self.assertIn({'view': 'Full Network', 'action': 'kept_existing', 'title': 'My network'}, result['actions'])
        titles = [x.get('title') for x in self.group(self.bookmarks())['items']]
        self.assertNotIn('Full Network', titles)
        self.assertIn('Research Map', titles)

    def test_preview_writes_nothing_and_malformed_bookmarks_are_left_alone(self):
        self.init('--no-views')
        self.assertEqual(self.cli('views', '--root', str(self.root))['status'], 'preview')
        self.assertFalse((self.root/'.obsidian').exists())
        for content in ('[1, 2]', '{"items": [1]}', '{"items": [{"type": "group", "items": ["x"]}]}'):
            bad = self.put('.obsidian/bookmarks.json', content)
            self.assertIn('Unrecognized', self.cli('views', '--root', str(self.root), '--apply', expected=2)['message'])
            self.assertEqual(bad.read_text(encoding='utf-8'), content)

    def test_bookmarks_go_to_the_vault_that_contains_vault_prefix(self):
        vault = self.base/'Vault'
        root = vault/'Notes/academic'
        self.profile.write_text(json.dumps({'language': 'en', 'vault_prefix': 'Notes/academic'}))
        self.init(root=root)
        group = self.group(self.bookmarks(vault))
        full = [x for x in group['items'] if x.get('title') == 'Full Network'][0]
        self.assertEqual(full['options']['search'], 'path:"Notes/academic/" ' + FULL)
        self.assertIn('Notes/academic/Academic Home.md', [x.get('path') for x in group['items']])
        self.assertFalse((root/'.obsidian').exists())
        # A nested vault on the path is reported, since bookmarks there would not be seen.
        (vault/'Notes/.obsidian').mkdir()
        self.assertIn('warning', self.cli('views', '--root', str(root)))

    # --- adopting an existing workspace ---------------------------------------------------

    def test_adopt_registers_existing_notes_without_changing_them(self):
        note = self.put('research/paper_notes/P001.md', '# P001\n\nExisting reading note.\n')
        design = self.init('--adopt')
        self.assertEqual(design['status'], 'adopted')
        self.assertEqual(sorted(design['written']), ['.paper2project.json', 'AGENTS.md'])
        self.assertEqual(design['notes_without_graph_role'], 1)
        self.assertEqual(note.read_text(encoding='utf-8'), '# P001\n\nExisting reading note.\n')
        self.assertTrue(self.group(self.bookmarks())['items'])
        warnings = self.check()['warnings']
        self.assertTrue(any('no graph-role tags' in x for x in warnings))

    def test_adopt_preview_is_read_only(self):
        self.put('notes/A.md', '# A\n')
        design = self.cli('init', '--root', str(self.root), '--profile', str(self.profile), '--non-interactive', '--adopt')
        self.assertEqual(design['status'], 'adoption_design')
        self.assertEqual(sorted(p.name for p in self.root.rglob('*')), ['A.md', 'notes'])

    # --- check reports what the graph will actually show ----------------------------------

    def test_uninitialized_untagged_vault_is_not_reported_as_clean(self):
        self.put('research/paper_notes/P001.md', '# P001\n')
        result = self.check()
        self.assertEqual(result['status'], 'needs_review')
        self.assertTrue(any('not initialized' in x for x in result['warnings']))
        self.assertTrue(any('no graph-role tags' in x for x in result['warnings']))

    def test_orphan_paper_and_missing_field_index_are_reported_until_linked(self):
        self.init()
        self.paper()
        warnings = self.check()['warnings']
        self.assertTrue(any(x.startswith('Unconnected paper') for x in warnings))
        self.assertTrue(any('Field index missing' in x for x in warnings))
        self.put(FIELD+'Machine Learning.md', '# Machine Learning\n\n- [['+FIELD+'Papers/Sequence Models - Example|Example]]\n\n#research-field\n')
        warnings = self.check()['warnings']
        self.assertFalse([x for x in warnings if 'Unconnected' in x or 'Field index' in x])

    def test_links_from_untagged_navigation_pages_do_not_count_as_graph_edges(self):
        self.init()
        self.paper()
        self.put('Reading list.md', '[['+FIELD+'Papers/Sequence Models - Example]]\n')
        self.assertTrue(any(x.startswith('Unconnected paper') for x in self.check()['warnings']))

    def test_escaped_alias_pipe_inside_a_table_resolves(self):
        self.init()
        self.paper()
        self.put(FIELD+'Machine Learning.md', '# Machine Learning\n\n| Paper | Note |\n|---|---|\n'
                 '| [['+FIELD+'Papers/Sequence Models - Example\\|Example]] | fixture |\n\n#research-field\n')
        result = self.check()
        self.assertFalse([x for x in result['errors'] if 'Missing link' in x], result['errors'])
        self.assertFalse([x for x in result['warnings'] if 'Unconnected' in x])

    def test_frontmatter_nested_and_inline_tags_match_obsidian_roles(self):
        self.init()
        front = self.paper('Front', tags='')
        front.write_text('---\ntags:\n  - paper\n  - selected\n---\n\n' + front.read_text(encoding='utf-8'), encoding='utf-8')
        self.paper('Inline', tags='\nRead later #paper/selected\n')
        self.paper('Code', tags='\n`#concept` is only a code sample.\n\n#paper\n')
        roles = self.check()['roles']
        self.assertEqual(roles.get('paper'), 3)
        self.assertNotIn('multiple', roles)
        self.paper('Both', tags='\n#paper\n', extra=' Mentions #concept in prose.')
        self.assertTrue(any('Multiple graph roles' in x for x in self.cli('check', '--root', str(self.root), expected=1)['errors']))


if __name__ == '__main__':
    unittest.main()
