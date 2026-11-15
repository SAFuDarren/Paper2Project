"""From PDFs and a results repository to a finished workspace, and the checks behind each step."""

import hashlib
import http.server
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE/'tests'))
from pdf_fixture import make_pdf  # noqa: E402

CS = 'Computer Science'
ML = 'Library/Computer Science/Machine Learning/'
TCS = 'Library/Computer Science/Theoretical Computer Science/'
PAPER_KEYS = ('summary', 'reading_scope', 'question', 'setup', 'method', 'results', 'argument', 'connection')
COMMIT = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'


def both(text_en, text_zh=None):
    return {'en': text_en, 'zh': text_zh or text_en}


class PipelineBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2p-pipe-')
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base/'Academic'
        self.profile = self.base/'profile.json'
        taxonomy = [{'discipline': CS, 'field': 'Machine Learning', 'direction': d, 'basis': 'ACM CCS (fixture)'}
                    for d in ('Sequence Models', 'Attention Mechanisms')]
        taxonomy.append({'discipline': CS, 'field': 'Theoretical Computer Science', 'direction': 'Formal Methods',
                         'basis': 'ACM CCS (fixture)'})
        self.profile.write_text(json.dumps({'language': 'en-zh', 'taxonomy': taxonomy}))
        self.n = 0

    def tearDown(self):
        self.tmp.cleanup()

    def run_py(self, script, *args, expected=0):
        r = subprocess.run([sys.executable, str(PACKAGE/'scripts'/script), *map(str, args)], encoding='utf-8',
                           capture_output=True)
        self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
        return json.loads(r.stdout if r.stdout else r.stderr)

    def cli(self, *args, expected=0):
        return self.run_py('p2p.py', *args, expected=expected)

    def write_json(self, value):
        self.n += 1
        path = self.base/('input-%d.json' % self.n)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return path

    def render(self, kind, card, expected=0):
        return self.cli('render', '--root', self.root, '--kind', kind, '--input', self.write_json(card), '--apply',
                        expected=expected)

    def paper_card(self, title, short, url, pdf=None, field='Machine Learning', subfield='Sequence Models', extra=''):
        content = {}
        for lang in ('en', 'zh'):
            content[lang] = {k: ('Fixture %s for %s.%s' % (k, short, extra)) for k in PAPER_KEYS}
            content[lang]['locations'] = 'Sec. 3.2, p. 4'
        card = {'title': title, 'discipline': CS, 'field': field, 'subfield': subfield, 'short_title': short,
                'metadata': {'paper': url, 'version': 'v1', 'field': field}, 'content': content}
        if pdf:
            card['pdf'] = str(pdf)
        return card

    def init(self):
        self.cli('init', '--root', self.root, '--profile', self.profile, '--non-interactive', '--apply')

    def pdf_folder(self):
        folder = self.base/'my pdfs'
        folder.mkdir()
        attention = make_pdf([['Attention Is All You Need', 'doi:10.48550/arXiv.1706.03762'],
                              ['Scaled dot-product attention divides by the square root of the key dimension.']],
                             title='Attention Is All You Need')
        (folder/'vaswani2017.pdf').write_bytes(attention)
        (folder/'copy of vaswani.pdf').write_bytes(attention)
        (folder/'Linear attention 2006.16236v3.pdf').write_bytes(
            make_pdf([['Transformers are RNNs'], ['Kernel feature maps give linear attention.']]))
        (folder/'broken.pdf').write_bytes(b'<html>not a pdf</html>')
        return folder

    def results_repo(self, remote='https://user:secret-token@github.com/lab/long-context.git'):
        repo = self.base/'long-context-results'
        (repo/'.git/refs/heads').mkdir(parents=True)
        (repo/'.git/HEAD').write_text('ref: refs/heads/main\n')
        (repo/'.git/refs/heads/main').write_text(COMMIT + '\n')
        (repo/'.git/config').write_text('[remote "origin"]\n\turl = ' + remote + '\n')
        (repo/'README.md').write_text('# Long-context retrieval\n\nRecall improves with retrieval.\n')
        (repo/'results').mkdir()
        (repo/'results/metrics.csv').write_text('setting,recall\nbaseline,0.61\nretrieval,0.74\n')
        (repo/'notebooks').mkdir()
        (repo/'notebooks/analysis.ipynb').write_text('{}')
        return repo


class PipelineTests(PipelineBase):
    def test_pdfs_and_a_results_repository_become_a_finished_workspace(self):
        self.init()
        folder = self.pdf_folder()
        # 1. Intake queue: identity, duplicates and non-PDFs are found by the program.
        queue = self.cli('pdfs', 'scan', '--root', self.root, '--from', folder)
        self.assertEqual(queue['counts'], {'new': 2, 'duplicate_file': 1, 'not_pdf': 1})
        attention = next(x for x in queue['pdfs'] if x['file'].endswith('vaswani2017.pdf'))
        self.assertEqual(attention['pages'], 2)
        self.assertEqual(attention['dois'], ['10.48550/arXiv.1706.03762'])
        self.assertIn('2006.16236v3', next(x for x in queue['pdfs'] if 'Linear' in x['file'])['arxiv'])
        # 2. A text-only model reads the PDF through the extractor.
        text = self.cli('pdfs', 'text', '--root', self.root, '--file', folder/'vaswani2017.pdf', '--engine', 'builtin')
        self.assertIn('square root of the key dimension', text['pages'][1]['text'])
        # 3. Notes: concepts first, then papers that use them and carry their originals.
        concept = {'title': 'Attention', 'discipline': CS, 'field': 'Machine Learning', 'short_title': 'Attention',
                   'metadata': {'from_papers': 'Vaswani et al.'},
                   'content': {l: {'definition': 'Weighted aggregation of values by query-key similarity.',
                                   'related_concepts': 'Kernel methods.'} for l in ('en', 'zh')}}
        self.render('concept', concept)
        kernel = dict(concept, title='Kernel Feature Map', short_title='Kernel Feature Map')
        self.render('concept', kernel)
        link = '[[' + ML + 'Concepts/Attention|attention]]'
        first = self.render('paper', self.paper_card('Attention Is All You Need', 'Transformer',
                                                     'https://arxiv.org/abs/1706.03762', folder/'vaswani2017.pdf', extra=' Uses ' + link + '.'))
        self.assertEqual(first['original']['status'], 'attached')
        note = (self.root/ML/'Papers/Sequence Models - Transformer.md').read_text(encoding='utf-8')
        self.assertEqual(note.count('[[' + ML + 'PDFs/Sequence Models - Transformer.pdf|'), 2)
        self.assertIn('<summary>Sources and reading locations</summary>', note)
        self.assertEqual((self.root/ML/'PDFs/Sequence Models - Transformer.pdf').read_bytes(),
                         (folder/'vaswani2017.pdf').read_bytes())
        self.render('paper', self.paper_card('Transformers are RNNs', 'Linear Attention', 'https://arxiv.org/abs/2006.16236',
                                             folder/'Linear attention 2006.16236v3.pdf', subfield='Attention Mechanisms',
                                             extra=' Uses ' + link + '.'))
        self.assertEqual(self.cli('pdfs', 'scan', '--root', self.root, '--from', folder)['counts'],
                         {'attached': 2, 'duplicate_file': 1, 'not_pdf': 1})
        # 4. Results repository: provenance comes from the repository itself, without credentials.
        repo = self.results_repo()
        scan = self.cli('repo', 'scan', '--path', repo)
        self.assertEqual((scan['commit'], scan['branch']), (COMMIT, 'main'))
        self.assertEqual(scan['remote'], 'https://github.com/lab/long-context.git')
        self.assertEqual(scan['counts']['results'], 1)
        direction = {'title': 'Sequence Models', 'discipline': CS, 'field': 'Machine Learning', 'direction': 'Sequence Models',
                     'metadata': {'field': 'Machine Learning', 'naming_basis': 'ACM CCS (fixture)'},
                     'content': {l: {'scope': 'Sequence modelling.', 'papers_concepts': 'Transformer papers.',
                                     'opportunities': 'Longer contexts.', 'projects': 'Long context.'} for l in ('en', 'zh')}}
        self.render('direction', direction)
        evidence = [{'path': 'results/metrics.csv', 'repo': str(repo), 'note': 'recall table'}]
        project = {'title': 'Long Context Retrieval', 'discipline': CS, 'field': 'Machine Learning', 'direction': 'Sequence Models',
                   'metadata': {'status': 'active'}, 'evidence': evidence,
                   'content': {l: {k: 'Fixture ' + k for k in ('scope', 'problem', 'methods', 'results', 'extensions',
                                                               'research_connections', 'knowledge_basis')} for l in ('en', 'zh')}}
        self.render('project', project)
        record = {'title': 'Retrieval improves recall', 'discipline': CS, 'field': 'Machine Learning', 'direction': 'Sequence Models',
                  'project': 'Long Context Retrieval', 'group': 'results', 'evidence': evidence,
                  'metadata': {'project': 'Long Context Retrieval', 'record': 'result', 'status': 'measured'},
                  'content': {l: {'body': 'Recall 0.61 → 0.74.', 'basis_scope': 'One benchmark.', 'evidence': 'metrics.csv',
                                  'remaining': 'Other benchmarks.'} for l in ('en', 'zh')}}
        self.render('project-record', record)
        home = 'Projects/Computer Science/Machine Learning/Sequence Models/Long Context Retrieval/'
        record_text = (self.root/home/'Results/Retrieval improves recall.md').read_text(encoding='utf-8')
        permalink = 'https://github.com/lab/long-context/blob/' + COMMIT + '/results/metrics.csv'
        self.assertEqual(record_text.count(permalink), 2)
        self.assertNotIn('secret-token', record_text)
        self.assertIn('Retrieval improves recall|Retrieval improves recall]]',
                      (self.root/home/'Long Context Retrieval.md').read_text(encoding='utf-8'))
        # 5. A concept relation recorded with its evidence in both notes.
        relation = {'id': 'C1', 'kind': 'concept', 'a': ML + 'Concepts/Attention.md', 'b': ML + 'Concepts/Kernel Feature Map.md',
                    'papers': [ML + 'Papers/Attention Mechanisms - Linear Attention.md'],
                    'text': {l: {'literature': 'Softmax attention can be written with kernel feature maps.',
                                 'connection': 'Lets us reuse kernel bounds.', 'missing_step': 'Error bound for our maps.'}
                             for l in ('en', 'zh')}}
        self.cli('relate', '--root', self.root, '--plan', self.write_json({'relations': [relation]}), '--apply')
        self.assertIn('Kernel Feature Map|Kernel Feature Map]]', (self.root/ML/'Concepts/Attention.md').read_text(encoding='utf-8'))
        # 6. Retrieval over notes and originals, with page locators.
        self.assertEqual(self.run_py('retrieve.py', 'sync', '--root', self.root)['status'], 'synced')
        hits = self.run_py('retrieve.py', 'search', '--root', self.root, 'square root of the key dimension', '--source', 'pdf')
        top = hits['results'][0]
        self.assertEqual(top['canonical_note'], ML + 'Papers/Sequence Models - Transformer.md')
        self.assertEqual(top['passages'][0]['locator']['page'], 2)
        self.assertTrue(top['passages'][0]['locator']['open'].endswith('Sequence Models - Transformer.pdf#page=2]]'))
        self.assertEqual(hits['evidence_status'], 'not_inferred_from_retrieval')
        notes = self.run_py('retrieve.py', 'search', '--root', self.root, 'recall benchmark', '--source', 'notes')
        self.assertTrue(any('Retrieval improves recall' in r['canonical_note'] for r in notes['results']))
        # 7. The program decides that the workspace is finished.
        result = self.cli('check', '--root', self.root)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['warnings'], [])
        self.assertEqual(result['navigation']['status'], 'complete')
        self.assertEqual(result['pdfs'], {'papers_with_original': 2, 'registered_files': 2})
        self.assertEqual(result['relations'], {'registered_relations': 1})
        brief = self.cli('brief', '--root', self.root)
        self.assertEqual(brief['navigation']['status'], 'complete')
        self.assertFalse(brief['retrieval']['needs_sync'])
        self.assertTrue(brief['next'][0].startswith('Workspace is navigable'))

    def test_snapshot_and_diff_show_changed_links(self):
        self.init()
        self.render('paper', self.paper_card('A Paper', 'A Paper', 'https://example.org/a'))
        snap = self.cli('snapshot', '--root', self.root, '--out', self.root/'.maintenance/snapshots/before')
        self.assertGreater(snap['files'], 3)
        self.cli('snapshot', '--root', self.root, '--out', self.root/'Library/x', expected=2)
        note = self.root/ML/'Papers/Sequence Models - A Paper.md'
        note.write_text(note.read_text(encoding='utf-8').replace('Fixture question for A Paper.',
                        'Fixture question for A Paper. [[Academic Home]]'), encoding='utf-8')
        diff = self.cli('diff', '--root', self.root, '--baseline', self.root/'.maintenance/snapshots/before')
        self.assertEqual(diff['changed'], [ML + 'Papers/Sequence Models - A Paper.md'])
        self.assertIn([ML + 'Papers/Sequence Models - A Paper.md', 'Academic Home'], diff['links_added'])
        self.assertTrue(diff['content_review_required'])

    def test_original_follows_its_note_when_migrated(self):
        self.init()
        folder = self.pdf_folder()
        self.render('paper', self.paper_card('Attention Is All You Need', 'Transformer', 'https://arxiv.org/abs/1706.03762',
                                             folder/'vaswani2017.pdf'))
        plan = self.write_json({'moves': {ML + 'Papers/Sequence Models - Transformer.md': TCS + 'Papers/Formal Methods - Transformer.md'}})
        result = self.cli('migrate', '--root', self.root, '--map', plan, '--apply')
        self.assertIn({'from': ML + 'PDFs/Sequence Models - Transformer.pdf', 'to': TCS + 'PDFs/Formal Methods - Transformer.pdf'},
                      result['moves'])
        register = json.loads((self.root/'.maintenance/pdf_attachments.json').read_text(encoding='utf-8'))
        self.assertEqual(list(register['papers']), [TCS + 'Papers/Formal Methods - Transformer.md'])
        check = self.cli('check', '--root', self.root)
        self.assertEqual(check['errors'], [])
        self.assertEqual(check['pdfs']['registered_files'], 1)


class PdfRuleTests(PipelineBase):
    def setUp(self):
        super().setUp()
        self.init()
        self.folder = self.pdf_folder()
        self.render('paper', self.paper_card('Attention Is All You Need', 'Transformer', 'https://arxiv.org/abs/1706.03762',
                                             self.folder/'vaswani2017.pdf'))
        self.render('paper', self.paper_card('Other Paper', 'Other', 'https://example.org/other'))
        self.note = ML + 'Papers/Sequence Models - Transformer.md'

    def attach(self, pdf, note, expected=0, apply=True):
        args = ['pdfs', 'attach', '--root', self.root, '--plan', self.write_json({'attach': [{'pdf': str(pdf), 'note': note}]})]
        return self.cli(*args, *(['--apply'] if apply else []), expected=expected)

    def test_attach_refuses_non_pdfs_reused_bytes_and_conflicting_copies(self):
        self.assertIn('Not a PDF', self.attach(self.folder/'broken.pdf', ML + 'Papers/Sequence Models - Other.md', 2)['message'])
        self.assertIn('another note', self.attach(self.folder/'vaswani2017.pdf', ML + 'Papers/Sequence Models - Other.md', 2)['message'])
        self.assertIn('different PDF', self.attach(self.folder/'Linear attention 2006.16236v3.pdf', self.note, 2)['message'])
        self.assertIn('existing #paper', self.attach(self.folder/'vaswani2017.pdf', ML + 'Missing.md', 2)['message'])
        preview = self.attach(self.folder/'Linear attention 2006.16236v3.pdf', ML + 'Papers/Sequence Models - Other.md', apply=False)
        self.assertEqual(preview['status'], 'preview')
        self.assertFalse((self.root/ML/'PDFs/Sequence Models - Other.pdf').exists())

    def test_check_audits_bytes_links_and_stray_files(self):
        self.assertEqual(self.cli('check', '--root', self.root)['errors'], [])
        copy = self.root/ML/'PDFs/Sequence Models - Transformer.pdf'
        copy.write_bytes(copy.read_bytes() + b'\n% edited')
        self.assertTrue(any('differ from the register' in x for x in self.cli('check', '--root', self.root, expected=1)['errors']))
        copy.write_bytes((self.folder/'vaswani2017.pdf').read_bytes())
        note = self.root/self.note
        text = note.read_text(encoding='utf-8')
        zh = text.rindex('<!-- p2p:pdf -->')
        note.write_text(text[:zh] + text[zh:].replace('[[', '[ [', 1), encoding='utf-8')
        self.assertTrue(any('every language block' in x for x in self.cli('check', '--root', self.root, expected=1)['errors']))
        note.write_text(text, encoding='utf-8')
        (self.root/ML/'PDFs/stray.pdf').write_bytes((self.folder/'Linear attention 2006.16236v3.pdf').read_bytes())
        self.assertTrue(any('Unregistered PDF' in x for x in self.cli('check', '--root', self.root)['warnings']))

    def test_unreadable_pdf_explains_how_to_read_it(self):
        empty = self.base/'scan.pdf'
        empty.write_bytes(make_pdf([[]]))
        message = self.cli('pdfs', 'text', '--root', self.root, '--file', empty, '--engine', 'builtin', expected=2)['message']
        self.assertIn('PyMuPDF', message)
        self.assertIn('metadata only', message)


class RelationRuleTests(PipelineBase):
    def setUp(self):
        super().setUp()
        self.init()
        self.render('paper', self.paper_card('Source Paper', 'Source', 'https://example.org/source'))
        for field, name in (('Machine Learning', 'Sequence Models'), ('Theoretical Computer Science', 'Formal Methods')):
            self.render('direction', {'title': name, 'discipline': CS, 'field': field, 'direction': name,
                                      'metadata': {'field': field, 'naming_basis': 'ACM CCS (fixture)'},
                                      'content': {l: {'scope': 's', 'papers_concepts': 'p', 'opportunities': 'o', 'projects': 'none'}
                                                  for l in ('en', 'zh')}})
        self.a = 'Projects/Computer Science/Machine Learning/Sequence Models/Sequence Models.md'
        self.b = 'Projects/Computer Science/Theoretical Computer Science/Formal Methods/Formal Methods.md'

    def relation(self, **changes):
        value = {'id': 'R1', 'a': self.a, 'b': self.b, 'papers': [ML + 'Papers/Sequence Models - Source.md'],
                 'text': {l: {'literature': 'Fact.', 'connection': 'Relevance.', 'missing_step': 'Gap.'} for l in ('en', 'zh')}}
        value.update(changes)
        return self.write_json({'relations': [value]})

    def test_relations_need_sources_and_every_language(self):
        self.assertIn('supporting paper', self.cli('relate', '--root', self.root, '--plan', self.relation(papers=[]), expected=2)['message'])
        self.assertIn('for zh', self.cli('relate', '--root', self.root, '--plan',
                                         self.relation(text={'en': {'literature': 'F', 'connection': 'R', 'missing_step': 'G'}}),
                                         expected=2)['message'])
        self.assertIn('#paper', self.cli('relate', '--root', self.root, '--plan', self.relation(papers=[self.a]), expected=2)['message'])
        self.assertIn('two field/direction/project', self.cli('relate', '--root', self.root, '--plan',
                                                              self.relation(b=ML + 'Papers/Sequence Models - Source.md'), expected=2)['message'])

    def test_unregistered_links_are_reported_and_registered_ones_are_checked(self):
        note = self.root/self.a
        original = note.read_text(encoding='utf-8')
        note.write_text(original.replace('\nnone\n', '\nnone [[' + self.b[:-3] + ']]\n'), encoding='utf-8')
        self.assertTrue(any('Unregistered research connection' in w for w in self.cli('check', '--root', self.root)['warnings']))
        note.write_text(original, encoding='utf-8')
        self.cli('relate', '--root', self.root, '--plan', self.relation(), '--apply')
        result = self.cli('check', '--root', self.root)
        self.assertEqual((result['errors'], result['warnings']), ([], []))
        text = note.read_text(encoding='utf-8')
        note.write_text(text.replace('Relevance.', 'Something else.', 1), encoding='utf-8')
        self.assertTrue(any('differs from its register' in x for x in self.cli('check', '--root', self.root, expected=1)['errors']))


class StubEmbeddings(http.server.BaseHTTPRequestHandler):
    """Deterministic bag-of-words vectors, standing in for a local Ollama."""
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        vectors = []
        for text in body['input']:
            v = [0.0] * 16
            for word in text.lower().split():
                v[int(hashlib.md5(word.strip('.,').encode()).hexdigest(), 16) % 16] += 1
            vectors.append(v)
        data = json.dumps({'embeddings': vectors}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

    def log_message(self, *args):
        pass


class RetrievalTests(PipelineBase):
    def setUp(self):
        super().setUp()
        self.init()
        self.render('paper', self.paper_card('Graph Paper', 'Graph', 'https://example.org/graph', extra=' Spectral clustering of graphs.'))
        self.render('paper', self.paper_card('Vision Paper', 'Vision', 'https://example.org/vision', extra=' Convolution on images.'))

    def test_semantic_search_uses_only_the_users_configured_endpoint(self):
        server = http.server.HTTPServer(('127.0.0.1', 0), StubEmbeddings)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            cfg_path = self.root/'.paper2project.json'
            cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
            cfg['extensions']['embedding'] = {'enabled': True, 'provider': 'ollama', 'model': 'stub',
                                              'endpoint': 'http://127.0.0.1:%d' % server.server_port, 'dimensions': 16}
            cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
            self.assertTrue(self.run_py('retrieve.py', 'sync', '--root', self.root)['semantic'])
            hits = self.run_py('retrieve.py', 'search', '--root', self.root, 'spectral clustering graphs', '--mode', 'semantic')
            self.assertEqual(hits['mode'], 'semantic')
            self.assertIn('Graph', hits['results'][0]['canonical_note'])
            cfg['extensions']['embedding']['api_key_env'] = 'P2P_TEST_MISSING_KEY'
            cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
            self.assertIn('P2P_TEST_MISSING_KEY', self.run_py('retrieve.py', 'sync', '--root', self.root, '--rebuild', expected=2)['message'])
        finally:
            server.shutdown()

    def test_lexical_search_reports_and_excludes_stale_notes(self):
        self.run_py('retrieve.py', 'sync', '--root', self.root)
        self.assertIn('Graph', self.run_py('retrieve.py', 'search', '--root', self.root, 'spectral')['results'][0]['canonical_note'])
        note = self.root/ML/'Papers/Sequence Models - Graph.md'
        note.write_text(note.read_text(encoding='utf-8').replace('Spectral', 'Changed'), encoding='utf-8')
        result = self.run_py('retrieve.py', 'search', '--root', self.root, 'spectral')
        self.assertTrue(result['freshness']['needs_sync'])
        self.assertFalse([r for r in result['results'] if 'Graph' in r['canonical_note']])


class ResultsTests(PipelineBase):
    def test_evidence_needs_a_commit_and_never_carries_credentials(self):
        repo = self.results_repo(remote='https://user:pw@git.example.org/lab/results.git')
        scan = self.cli('repo', 'scan', '--path', repo)
        self.assertEqual(scan['remote'], 'https://git.example.org/lab/results.git')
        self.assertIsNone(scan['permalink_base'])
        sys.path.insert(0, str(PACKAGE/'scripts'))
        import results
        line = results.evidence_lines([{'path': 'results/metrics.csv', 'repo': str(repo)}], {})[0]
        self.assertEqual(line, '- `results/metrics.csv` @ `' + COMMIT[:10] + '` (https://git.example.org/lab/results.git)')
        with self.assertRaises(ValueError):
            results.evidence_lines([{'path': 'results/metrics.csv'}], {})
        with self.assertRaises(ValueError):
            results.evidence_lines([{'path': 'missing.csv', 'repo': str(repo)}], {})


if __name__ == '__main__':
    unittest.main()
