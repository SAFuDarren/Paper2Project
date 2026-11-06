"""Cold-install, relocation, failure-recovery and documentation lifecycle checks.

All data are synthetic and all operations use temporary directories. No network,
real user memory, installed skill, vault or native application is accessed.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / 'scripts'))
import i18n
import profiles


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p2p-portable-')
        self.base = Path(self.temp.name).resolve()
        self.package = self.base / 'Downloaded skill 研究 café'
        shutil.copytree(PACKAGE, self.package,
                        ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc'))
        self.cwd = self.base / 'Unrelated working directory'
        self.cwd.mkdir()
        self.root = self.base / 'Academic workspace 研究'
        # Explicitly exercise a host whose default text streams are not UTF-8.
        self.env = dict(os.environ, PYTHONUTF8='0', PYTHONIOENCODING='ascii',
                        LC_ALL='C', LANG='C', PYTHONDONTWRITEBYTECODE='1')

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, name, *args, expected=0):
        result = subprocess.run(
            [sys.executable, '-S', str(self.package / 'scripts' / name), *map(str, args)],
            cwd=self.cwd, env=self.env, capture_output=True, encoding='utf-8', timeout=40)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout

    def cli(self, *args, expected=0):
        return json.loads(self.run_script('p2p.py', *args, expected=expected))

    def put_json(self, name, data):
        p = self.base / name
        p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return p

    def initialize(self, languages=('en', 'zh')):
        profile = self.put_json('profile.json', {
            'note_languages': list(languages),
            'research_scope': 'Synthetic portability fixture only.',
            'taxonomy': [{'discipline': 'Computer Science', 'field': 'Machine Learning',
                          'direction': 'Sequence Models', 'basis': 'Synthetic naming fixture.'}]})
        self.cli('init', '--root', self.root, '--profile', profile,
                 '--non-interactive', '--apply')

    def note(self, kind, languages, identifier, target, link=''):
        metadata = {key: 'Synthetic fixture only.' for key in i18n.SPECS[kind][0]}
        metadata.update(paper='https://example.org/fixture-paper',
                        version='synthetic', field='Machine Learning',
                        from_papers='https://example.org/fixture-paper')
        content = {}
        for language in languages:
            content[language] = {key: 'Synthetic fixture café 研究 ' + link
                                 for key in i18n.SPECS[kind][1]}
            content[language].update(summary='Synthetic fixture only. ' + link,
                                     reading_scope='Fixture; no paper was read.')
        card = self.put_json('card.json', {'id': identifier, 'title': 'Fixture café 研究',
                             'subfield': 'Sequence Models', 'metadata': metadata,
                             'content': content})
        return self.cli('render', '--root', self.root, '--kind', kind,
                        '--input', card, '--output', target, '--apply')

    def test_download_zip_runs_without_site_packages_from_foreign_cwd(self):
        archive = self.base / 'download.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in self.package.rglob('*'):
                if p.is_file():
                    z.write(p, 'paper2project/' + p.relative_to(self.package).as_posix())
        extracted = self.base / 'Extracted download 研究'
        with zipfile.ZipFile(archive) as z:
            z.extractall(extracted)
        self.package = extracted / 'paper2project'
        languages = ('fr', 'ar', 'en')
        self.initialize(languages)
        target = 'Library/Computer Science/Machine Learning/Papers/Sequence Models - Note 研究.md'
        result = self.note('paper', languages, 'portable-paper', target)
        self.assertEqual(result['content_sha256'],
                         hashlib.sha256((self.root / target).read_bytes()).hexdigest())
        self.assertEqual(self.cli('check', '--root', self.root)['errors'], [])
        self.assertEqual(json.loads(self.run_script('package_check.py'))['status'], 'passed')

    def test_moved_workspace_resumes_with_same_links_preferences_and_identity(self):
        languages = ('en', 'zh')
        self.initialize(languages)
        concept = 'Library/Computer Science/Machine Learning/Concepts/Shared 研究.md'
        paper = 'Library/Computer Science/Machine Learning/Papers/Sequence Models - Note.md'
        self.note('concept', languages, 'portable-concept', concept)
        self.note('paper', languages, 'portable-paper', paper, '[[' + concept[:-3] + ']]')
        before_note = (self.root / paper).read_bytes()
        before_config = (self.root / '.paper2project.json').read_bytes()
        first = self.base / 'before.jsonl'
        self.cli('export', '--root', self.root, '--kind', 'paper', '--output', first)
        original = json.loads(first.read_text(encoding='utf-8').splitlines()[1])
        relocated = self.base / 'New parent' / 'Relocated workspace 研究'
        relocated.parent.mkdir()
        shutil.move(str(self.root), str(relocated))
        self.root = relocated
        self.assertEqual(self.cli('check', '--root', self.root)['errors'], [])
        signals = self.put_json('signals.json', {})
        resumed = self.cli('preferences', '--root', self.root, '--signals', signals)
        self.assertEqual(resumed['profile']['note_languages'], list(languages))
        second = self.base / 'after.jsonl'
        self.cli('export', '--root', self.root, '--kind', 'paper', '--output', second)
        new = json.loads(second.read_text(encoding='utf-8').splitlines()[1])
        for key in ('id', 'path', 'content_sha256'):
            self.assertEqual(new[key], original[key])
        self.assertEqual((self.root / paper).read_bytes(), before_note)
        self.assertEqual((self.root / '.paper2project.json').read_bytes(), before_config)

    def test_failed_profile_replace_preserves_config_and_retry_recovers(self):
        self.root.mkdir()
        path = self.root / '.paper2project.json'
        original = profiles.normalize({'note_languages': ['en']})
        path.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
        note = self.root / 'Existing 研究.md'
        note.write_text('Existing note 研究\n', encoding='utf-8')
        before = path.read_bytes()
        before_note = note.read_bytes()
        updated = copy.deepcopy(original)
        updated['response_language'] = 'ja'
        expected_hash = hashlib.sha256(before).hexdigest()
        with mock.patch.object(profiles.os, 'replace', side_effect=PermissionError('Synthetic failure')):
            with self.assertRaises(PermissionError):
                profiles.save_update(path, copy.deepcopy(updated), expected_hash)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(note.read_bytes(), before_note)
        self.assertEqual(list(self.root.glob('.p2p-*')), [])
        backups = list((self.root / '.paper2project-history').glob('*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        saved = profiles.save_update(path, updated, expected_hash)
        self.assertEqual(profiles.load(path)['response_language'], 'ja')
        self.assertEqual(saved['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(note.read_bytes(), before_note)

    def image_refs(self):
        refs = {}
        for name in ('README.md', 'README.zh-CN.md'):
            text = (self.package / name).read_text(encoding='utf-8')
            match = re.search(r'\]\((assets/readme/[^)]+\.svg)\)', text)
            self.assertIsNotNone(match, name)
            path = self.package / match[1]
            data = path.read_bytes()
            self.assertIn(hashlib.sha256(data).hexdigest()[:12], path.name)
            refs[name] = (path, data)
        return refs

    def test_illustrations_regenerate_from_crlf_and_update_versioned_urls(self):
        for name in ('README.md', 'README.zh-CN.md'):
            p = self.package / name
            p.write_bytes(('\r\n'.join(p.read_text(encoding='utf-8').splitlines()) + '\r\n').encode('utf-8'))
        before = self.image_refs()
        sentinel = self.package / 'assets/readme/keep-user-file.txt'
        sentinel.write_text('Keep this file.\n', encoding='utf-8')
        self.run_script('render_readme_graph.py')
        self.assertEqual(self.image_refs(), before)
        profile = self.package / 'assets/default-profile.json'
        data = json.loads(profile.read_text(encoding='utf-8'))
        data['palette']['project'] = '#EF8759'
        profile.write_text(json.dumps(data), encoding='utf-8')
        self.run_script('render_readme_graph.py')
        after = self.image_refs()
        for name, (path, content) in after.items():
            self.assertNotEqual(path, before[name][0])
            self.assertFalse(before[name][0].exists())
            self.assertIn(b'#EF8759', content)
        self.run_script('render_readme_graph.py')
        self.assertEqual(self.image_refs(), after)
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'Keep this file.\n')
        self.assertEqual(json.loads(self.run_script('package_check.py'))['status'], 'passed')

    def test_package_checker_detects_broken_chinese_readme_reference(self):
        p = self.package / 'README.zh-CN.md'
        with p.open('a', encoding='utf-8') as f:
            f.write('\n[Fixture missing image](assets/readme/fixture-missing.svg)\n')
        result = json.loads(self.run_script('package_check.py', expected=1))
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('README.zh-CN.md' in error and 'fixture-missing.svg' in error
                            for error in result['errors']))


if __name__ == '__main__':
    unittest.main()
