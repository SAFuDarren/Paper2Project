"""The files in examples/ must keep working with the commands the docs pair them with."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
EXAMPLES = PACKAGE/'examples'


class ExampleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2p-examples-')
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base/'Academic'

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, expected=0):
        r = subprocess.run([sys.executable, str(PACKAGE/'scripts/p2p.py'), *map(str, args)], encoding='utf-8', capture_output=True)
        self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
        return json.loads(r.stdout if r.stdout else r.stderr)

    def card(self, value):
        path = self.base/('card-%d.json' % len(list(self.base.glob('card-*.json'))))
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return path

    def test_examples_render_and_relate(self):
        profile = self.base/'profile.json'
        self.cli('preferences', '--root', self.root, '--signals', EXAMPLES/'signals.json', '--output', profile, '--apply')
        self.cli('init', '--root', self.root, '--profile', profile, '--non-interactive', '--apply')
        paper = self.cli('render', '--root', self.root, '--kind', 'paper', '--input', EXAMPLES/'paper-card.json', '--apply')
        self.assertTrue(Path(paper['path']).as_posix().endswith(
            'Library/Computer Science/Machine Learning/Papers/Sequence Models - Synthetic Workflow.md'))
        relations = json.loads((EXAMPLES/'relations.json').read_text(encoding='utf-8'))['relations'][0]
        for path in (relations['a'], relations['b']):
            _, discipline, field, direction, _ = Path(path).parts
            self.cli('render', '--root', self.root, '--kind', 'direction', '--apply', '--input', self.card({
                'title': direction, 'discipline': discipline, 'field': field, 'direction': direction,
                'metadata': {'field': field, 'naming_basis': 'fictional example'},
                'content': {'fr': {'scope': 'Exemple.', 'papers_concepts': 'Exemple.', 'opportunities': 'Exemple.', 'projects': 'Exemple.'}}}))
        record = json.loads((EXAMPLES/'project-record-card.json').read_text(encoding='utf-8'))
        self.cli('render', '--root', self.root, '--kind', 'project', '--apply', '--input', self.card({
            'title': record['project'], 'discipline': record['discipline'], 'field': record['field'], 'direction': record['direction'],
            'metadata': {'status': 'fictional'}, 'content': {'fr': {k: 'Exemple.' for k in (
                'scope', 'problem', 'methods', 'results', 'extensions', 'research_connections', 'knowledge_basis')}}}))
        rendered = self.cli('render', '--root', self.root, '--kind', 'project-record', '--input', EXAMPLES/'project-record-card.json', '--apply')
        text = Path(rendered['path']).read_text(encoding='utf-8')
        self.assertIn('https://github.com/example/synthetic-results/blob/0123456789abcdef0123456789abcdef01234567/results/metrics.csv', text)
        self.assertEqual(self.cli('relate', '--root', self.root, '--plan', EXAMPLES/'relations.json', '--apply')['status'], 'related')
        result = self.cli('check', '--root', self.root)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['navigation']['status'], 'complete')


if __name__ == '__main__':
    unittest.main()
