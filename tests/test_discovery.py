"""Public discovery regression tests using fictional workspace records."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / 'scripts'))
import discovery

PROJECT = 'Projects/Computer Science/Machine Learning/Sequence Models/Project A/Project A.md'


def candidate(key='a', title='Fictional paper A', version='1'):
    return {'id': key, 'title': title, 'authors': 'Fictional author', 'source': f'https://arxiv.org/html/9999.10001v{version}',
            'locator': 'Section 2, fictional example', 'direction': 'Sequence Models',
            'overview': 'Read one record and answer a later question.',
            'field': 'Sequence modelling', 'publication': 'Fictional proceedings',
            'question': 'What must be remembered?',
            'method': 'Compare two histories and report the full output.',
            'conditions': 'The input set and horizon are fixed.',
            'contribution': 'A bounded example with a stated comparison.',
            'connection': 'The input and query match Project A.',
            'potential': 'Compare all outputs under a matched budget.'}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'Workspace 研究 café'
        self.root.mkdir()
        self.profile = self.root / '.paper2project.json'
        self.profile.write_text(json.dumps({'response_language': 'zh',
                                            'taxonomy': [{'discipline': 'Computer Science', 'field': 'Machine Learning',
                                                          'direction': 'Sequence Models', 'basis': 'Fictional fixture'}]}),
                                encoding='utf-8')
        self.project = self.root / PROJECT
        self.project.parent.mkdir(parents=True)
        self.project.write_text('# Project A\n\n#research-project\n', encoding='utf-8')
        self.paper = self.root / 'Library/Computer Science/Machine Learning/Papers/Sequence Models - Existing.md'
        self.paper.parent.mkdir(parents=True)
        pdf = self.paper.parent.parent / 'PDFs' / 'Original.pdf'
        pdf.parent.mkdir()
        pdf.write_bytes(b'%PDF-1.0\nFictional presence fixture only')
        self.paper.write_text(
            '---\nsource_id: https://arxiv.org/html/9999.10002v1\n---\n'
            '# Existing reference\n\n[Original](../PDFs/Original.pdf)\n\n#paper\n', encoding='utf-8')
        self.request = self.base / 'Discovery input.json'
        self.stage = self.base / 'Pending review.json'
        self.decision = self.base / 'Decisions.json'

    def run_cli(self, command, *args, expected=0):
        env = dict(os.environ, PYTHONUTF8='0', PYTHONIOENCODING='ascii', LC_ALL='C', LANG='C')
        proc = subprocess.run([sys.executable, '-B', '-S', str(PACKAGE / 'scripts' / 'p2p.py'),
                               command, '--root', str(self.root), *map(str, args)],
                              cwd=self.base, env=env, capture_output=True, encoding='utf-8', timeout=20)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return json.loads(proc.stdout if not expected else proc.stderr)

    def run_discovery(self, rows, *args, expected=0, **options):
        data = {'project': PROJECT, 'items': rows, **options}
        self.request.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return self.run_cli('discover', '--input', self.request, *args, expected=expected)

    def run_review(self, result, *, materials=None, connections=None, expected=0):
        self.decision.write_text(json.dumps({'packet_sha256': result['packet_sha256'],
                                             'approval_reference': 'Fictional user choice',
                                             'materials': materials or {}, 'connections': connections or {}}),
                                 encoding='utf-8')
        return self.run_cli('review-discovery', '--packet', self.stage, '--decisions', self.decision,
                            expected=expected)

    def test_identity_versions_and_attachment_presence(self):
        rows = [
            {'id': 'known', 'title': 'Existing reference', 'identifiers': ['arxiv:9999.10002v1'],
             'direction': 'Sequence Models'},
            {'id': 'version', 'title': 'Existing reference', 'source': 'https://arxiv.org/pdf/9999.10002v2'},
            {'id': 'unknown', 'title': 'Existing reference'},
            {'id': 'different', 'title': 'Separate paper', 'source': 'https://doi.org/10.1234/example'},
        ]
        result = self.run_discovery(rows)['items']
        self.assertEqual([row['status'] for row in result.values()], ['library', 'version', 'identity', 'new'])
        self.assertEqual(result['known']['match']['pdfs'], ['Library/Computer Science/Machine Learning/PDFs/Original.pdf'])
        self.assertTrue(result['known']['direction_registered'])
        self.assertFalse(self.stage.exists())
        self.assertEqual(discovery.source_reference('https://doi.org/10.48550/arxiv.9999.10002v2'),
                         ('arxiv:9999.10002', 'arxiv:9999.10002v2'))

    def test_complete_cards_separate_lanes_and_existing_material_is_brief(self):
        known = {'id': 'known', 'title': 'Existing reference', 'source': 'https://arxiv.org/abs/9999.10002v1',
                 'overview': 'A previous study explains a baseline.', 'connection': 'It is the comparison.'}
        first = candidate()
        second = {**candidate('b', 'Fictional paper B'), 'source': 'https://example.org/proceedings/paper-b'}
        industry = {**candidate('i', 'Event service'), 'lane': 'industry', 'organization': 'Fictional organization',
                    'case_key': 'example-service', 'source': 'https://example.org/report'}
        result = self.run_discovery([known, first, second, industry], '--stage', self.stage)
        self.assertEqual(result['language'], 'zh')
        md = result['markdown']
        self.assertEqual(md.count('**研究问题**'), 2)
        self.assertEqual(md.count('**业务问题**'), 1)
        self.assertEqual(md.count('**一句话概览**'), 4)
        self.assertEqual(md.count('#### Fictional author | Fictional paper'), 2)
        self.assertLess(md.index('## 学术论文'), md.index('## 工业案例'))
        self.assertIn('### 已入库', md)
        self.assertIn('未收录 · 待审', md)
        packet = json.loads(self.stage.read_bytes())
        self.assertEqual(set(packet['materials']), {'a', 'b', 'i'})
        self.assertEqual(set(packet['connections']), {'a', 'b', 'i'})
        self.assertEqual(len(list(self.root.rglob('*.md'))), 2)

    def test_prior_reuse_default_full_card_and_explicit_recap(self):
        first = self.run_discovery([candidate()], '--stage', self.stage)
        stored = self.stage.read_bytes()
        other = self.base / 'No duplicate.json'
        thin = {'id': 'seen', 'title': 'Fictional paper A', 'identifiers': ['arxiv:9999.10001v1']}
        full = self.run_discovery([thin], '--prior', self.stage, '--stage', other)
        self.assertEqual(full['status'], 'no_new_candidates')
        self.assertIn('**研究问题**', full['markdown'])
        recap = self.run_discovery([{**thin, 'recap': True}], '--prior', self.stage, '--stage', other)
        self.assertIn('### 前轮待审', recap['markdown'])
        self.assertNotIn('**研究问题**', recap['markdown'])
        self.assertFalse(other.exists())
        self.assertEqual(self.stage.read_bytes(), stored)
        self.assertEqual(first['status'], 'staged')

    def test_validation_precedes_writes_and_does_not_replace_packets(self):
        missing = candidate()
        del missing['method']
        self.assertIn('method', self.run_discovery([missing], '--stage', self.stage, expected=2)['message'])
        self.assertFalse(self.stage.exists())
        target = self.paper.parent / 'review.json'
        self.run_discovery([candidate()], '--stage', target, expected=2)
        self.assertFalse(target.exists())
        self.run_discovery([candidate()], '--stage', self.stage)
        original = self.stage.read_bytes()
        self.run_discovery([candidate()], '--stage', self.stage, expected=2)
        self.assertEqual(self.stage.read_bytes(), original)

    def test_review_choices_are_independent_and_workspace_hash_is_checked(self):
        result = self.run_discovery([candidate()], '--stage', self.stage)
        plan = self.run_review(result, materials={'a': 'approve'})
        self.assertEqual(plan['connections'], {})
        self.assertEqual(plan['materials']['a']['choice'], 'approve')
        self.assertEqual(plan['packet_sha256'], result['packet_sha256'])
        error = self.run_review(result, connections={'a': 'approve'}, expected=2)
        self.assertIn('separately', error['message'])
        plan = self.run_review(result, materials={'a': 'approve'}, connections={'a': 'approve'})
        self.assertEqual(plan['connections']['a']['choice'], 'approve')
        self.project.write_text('# Project A\n\nChanged scope.\n\n#research-project\n', encoding='utf-8')
        self.assertIn('inventory changed', self.run_review(result, materials={'a': 'approve'}, expected=2)['message'])

    def test_prior_link_to_admitted_source_is_not_staged_twice(self):
        known = {**candidate('known', 'Existing reference'),
                 'source': 'https://arxiv.org/html/9999.10002v1', 'propose_connection': True}
        result = self.run_discovery([known], '--stage', self.stage)
        self.assertFalse(json.loads(self.stage.read_bytes())['materials'])
        self.assertEqual(self.run_review(result, connections={'known': 'approve'})
                         ['connections']['known']['choice'], 'approve')
        other = self.base / 'Repeated link.json'
        repeat = self.run_discovery([known], '--stage', other, '--prior', self.stage)
        self.assertEqual(repeat['status'], 'no_new_candidates')
        self.assertFalse(other.exists())

    def test_explicit_response_language_and_custom_labels(self):
        tags = ('en', 'zh', 'zh-Hant', 'es', 'fr', 'de', 'ja', 'ar')
        for tag in tags:
            self.assertEqual(set(discovery.labels_for(tag)), set(discovery.LABEL_KEYS))
        self.run_discovery([candidate()], '--stage', self.stage, language='it', expected=2)
        self.assertFalse(self.stage.exists())
        custom = {key: f'Etichetta {i}' for i, key in enumerate(discovery.LABEL_KEYS)}
        result = self.run_discovery([candidate()], '--stage', self.stage, language='it', labels=custom)
        self.assertIn(custom['question'], result['markdown'])


if __name__ == '__main__':
    unittest.main()
