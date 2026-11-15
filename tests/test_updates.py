"""Updates keep user customizations: extension settings, extra profile keys, local files, edited rules."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
FIELD = 'Library/Computer Science/Machine Learning/'
SECTIONS = ('summary', 'reading_scope', 'question', 'setup', 'method', 'results', 'argument', 'connection')
CUSTOM_EXTENSIONS = {
    'embedding': {'enabled': True, 'provider': 'local-bge-m3', 'chunk_tokens': 512, 'index_path': '.index/vectors'},
    'rag': {'enabled': False, 'provider': None},
    'agent': {'enabled': False, 'provider': None},
    'knowledge_store': {'enabled': True, 'provider': 'gbrain', 'scope': ['paper', 'concept']},
    'database': {'enabled': True, 'provider': 'postgres', 'dsn_env': 'LAB_DB_DSN', 'tables': {'papers': 'p2p_papers'}},
}


def copy_package(dest):
    shutil.copytree(PACKAGE, dest, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc'))
    return dest


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2p-update-')
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base/'Academic'
        self.profile = self.base/'profile.json'
        self.profile.write_text(json.dumps({'language': 'en'}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_py(self, script, *args, expected=0, package=PACKAGE):
        r = subprocess.run([sys.executable, str(package/'scripts'/script), *map(str, args)],
                           encoding='utf-8', capture_output=True)
        self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
        return json.loads(r.stdout if r.stdout else r.stderr)

    def cli(self, *args, expected=0):
        return self.run_py('p2p.py', *args, expected=expected)

    def customize(self):
        self.cli('init', '--root', self.root, '--profile', self.profile, '--non-interactive', '--apply')
        cfg_path = self.root/'.paper2project.json'
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        cfg['extensions'] = CUSTOM_EXTENSIONS
        cfg['team_settings'] = {'review_owner': 'lab', 'weekly_digest': True}
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
        return cfg_path

    def assert_custom_kept(self, cfg_path):
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        self.assertEqual(cfg['extensions'], CUSTOM_EXTENSIONS)
        self.assertEqual(cfg['team_settings'], {'review_owner': 'lab', 'weekly_digest': True})

    # --- customized workspaces keep working and keep their settings ------------------------

    def test_every_command_keeps_extension_settings_and_extra_keys(self):
        cfg_path = self.customize()
        card = self.base/'card.json'
        card.write_text(json.dumps({'title': 'Attention', 'discipline': 'Computer Science', 'field': 'Machine Learning',
                                    'subfield': 'Sequence Models', 'short_title': 'Attention',
                                    'metadata': {'paper': 'https://arxiv.org/abs/1706.03762', 'version': 'v7', 'field': 'ML'},
                                    'content': {'en': {k: 'Fixture ' + k for k in SECTIONS}}}))
        self.cli('render', '--root', self.root, '--kind', 'paper', '--input', card, '--apply')
        self.cli('check', '--root', self.root)
        self.cli('index', '--root', self.root, '--apply')
        self.cli('views', '--root', self.root, '--apply')
        self.cli('export', '--root', self.root, '--output', self.base/'snapshot.jsonl')
        signals = self.base/'signals.json'
        signals.write_text(json.dumps({'explicit': {'note_languages': ['en', 'zh']}}))
        preview = self.cli('preferences', '--root', self.root, '--signals', signals, '--scope', 'workspace')
        self.cli('preferences', '--root', self.root, '--signals', signals, '--scope', 'workspace',
                 '--expect-sha', preview['expected_sha256'], '--apply')
        self.assert_custom_kept(cfg_path)
        self.cli('upgrade', '--root', self.root, '--apply')
        self.assert_custom_kept(cfg_path)

    def test_credentials_are_refused_but_references_are_allowed(self):
        cfg_path = self.customize()
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        cfg['extensions']['database']['password'] = 'hunter2'
        cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
        self.assertIn('database.password', self.cli('check', '--root', self.root, expected=2)['message'])

    def test_signals_and_onboarding_cannot_switch_extensions_on(self):
        self.customize()
        signals = self.base/'signals.json'
        signals.write_text(json.dumps({'explicit': {'extensions': {'rag': {'enabled': True, 'provider': 'x'}}}}))
        self.cli('preferences', '--root', self.root, '--signals', signals, '--scope', 'workspace', expected=2)
        self.profile.write_text(json.dumps({'extensions': {'database': {'enabled': True, 'provider': 'postgres'}}}))
        self.cli('init', '--root', self.base/'Other', '--profile', self.profile, '--non-interactive', '--apply', expected=2)

    # --- workspace upgrade refreshes only the marked rules ----------------------------------

    def test_upgrade_refreshes_marked_rules_and_keeps_user_text(self):
        self.customize()
        agents = self.root/'AGENTS.md'
        agents.write_text('# Lab rules\n\nAlways cite page numbers.\n\n' + agents.read_text(encoding='utf-8').replace(
            'Paper2Project workspace rules', 'Old rules title') + '\nTeam footer.\n', encoding='utf-8')
        result = self.cli('upgrade', '--root', self.root, '--apply')
        self.assertEqual(result['rules'], 'refreshed')
        text = agents.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('# Lab rules\n\nAlways cite page numbers.'))
        self.assertTrue(text.rstrip().endswith('Team footer.'))
        self.assertIn('Paper2Project workspace rules', text)
        self.assertNotIn('Old rules title', text)
        self.assertEqual(self.cli('upgrade', '--root', self.root, '--apply')['rules'], 'unchanged')

    def test_upgrade_replaces_an_unedited_old_copy_and_appends_to_an_edited_one(self):
        self.customize()
        agents = self.root/'AGENTS.md'
        shipped = (PACKAGE/'assets/workspace-rules.md').read_text(encoding='utf-8')
        agents.write_bytes(shipped.replace('\n', '\r\n').encode('utf-8'))  # pre-marker copy, CRLF checkout
        self.assertEqual(self.cli('upgrade', '--root', self.root, '--apply')['rules'], 'replaced_shipped_copy')
        self.assertTrue(agents.read_text(encoding='utf-8').startswith('<!-- p2p:rules -->'))
        agents.write_text(shipped + '\n- Our extra rule.\n', encoding='utf-8')
        self.assertEqual(self.cli('upgrade', '--root', self.root, '--apply')['rules'], 'appended_kept_custom')
        text = agents.read_text(encoding='utf-8')
        self.assertTrue(text.startswith(shipped.rstrip('\n') + '\n\n- Our extra rule.'))
        self.assertIn('<!-- p2p:rules -->', text)

    # --- skill folder update keeps local edits and local files ------------------------------

    def release(self, folder, change):
        """A newer release: one file changed and the manifest regenerated, as a maintainer would."""
        new = copy_package(folder)
        target = new/'references/workflow.md'
        target.write_text(target.read_text(encoding='utf-8') + change, encoding='utf-8')
        self.run_py('package_check.py', '--write-manifest', package=new)
        self.assertEqual(self.run_py('package_check.py', '--release', package=new)['status'], 'passed')
        return new

    def test_update_replaces_shipped_files_and_keeps_customized_and_local_ones(self):
        installed = copy_package(self.base/'installed')
        (installed/'local/adapters').mkdir(parents=True)
        (installed/'local/adapters/embedding.py').write_text('PROVIDER = "bge"\n', encoding='utf-8')
        (installed/'scripts/lab_hook.py').write_text('# user file\n', encoding='utf-8')
        template = installed/'assets/templates/paper.md'
        template.write_text(template.read_text(encoding='utf-8') + '\nLab footer\n', encoding='utf-8')
        onboarding = installed/'references/onboarding.md'
        onboarding.write_bytes(onboarding.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))  # unmodified, CRLF checkout
        new = self.release(self.base/'new', '\nRelease note line.\n')
        preview = self.run_py('update_skill.py', '--target', installed, package=new)
        self.assertEqual(preview['status'], 'preview')
        self.assertNotIn('Release note line.', (installed/'references/workflow.md').read_text(encoding='utf-8'))
        result = self.run_py('update_skill.py', '--target', installed, '--apply', package=new)
        self.assertIn('Release note line.', (installed/'references/workflow.md').read_text(encoding='utf-8'))
        self.assertIn('Lab footer', template.read_text(encoding='utf-8'))
        self.assertTrue((installed/'assets/templates/paper.md.new').is_file())
        self.assertEqual([x['path'] for x in result['kept_custom']], ['assets/templates/paper.md'])
        self.assertEqual((installed/'local/adapters/embedding.py').read_text(encoding='utf-8'), 'PROVIDER = "bge"\n')
        self.assertEqual((installed/'scripts/lab_hook.py').read_text(encoding='utf-8'), '# user file\n')
        self.assertNotIn('references/onboarding.md', [x['path'] for x in result['kept_custom']])
        again = self.run_py('update_skill.py', '--target', installed, '--apply', package=new)
        self.assertEqual(again['changes'], [])

    def test_update_refuses_non_skill_folders(self):
        (self.base/'empty').mkdir()
        self.run_py('update_skill.py', '--target', self.base/'empty', expected=2)
        self.run_py('update_skill.py', '--target', PACKAGE, expected=2)


if __name__ == '__main__':
    unittest.main()
