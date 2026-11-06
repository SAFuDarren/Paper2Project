"""Preference precedence, durable changes and localized note lifecycle tests."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE=Path(__file__).resolve().parents[1]
SCRIPT=PACKAGE/'scripts/p2p.py'
sys.path.insert(0,str(PACKAGE/'scripts'))
import i18n


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='p2p-i18n-')
        self.base=Path(self.temp.name).resolve()
        self.root=self.base/'Research space 研究'
        self.profile=self.base/'profile.json'

    def tearDown(self):self.temp.cleanup()

    def put_json(self,path,obj):
        path.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8');return path

    def cli(self,*args,expected=0):
        p=subprocess.run([sys.executable,str(SCRIPT),*map(str,args)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(p.returncode,expected,p.stdout+p.stderr)
        return json.loads(p.stdout or p.stderr)

    def init(self,languages=('en',),**values):
        self.put_json(self.profile,{'note_languages':list(languages),'taxonomy':[{'discipline':'Computer Science','field':'Machine Learning','direction':'Sequence Models','basis':'Synthetic test naming basis; not verified literature.'}],**values})
        return self.cli('init','--root',self.root,'--profile',self.profile,'--non-interactive','--apply')

    def config(self):return json.loads((self.root/'.paper2project.json').read_text(encoding='utf-8'))

    def prefs(self,signals,scope='task',apply=False,expected=0,sha=None):
        path=self.put_json(self.base/'signals.json',signals)
        args=['preferences','--root',self.root,'--signals',path,'--scope',scope]
        if apply:args+=['--apply','--expect-sha',sha or hashlib.sha256((self.root/'.paper2project.json').read_bytes()).hexdigest()]
        return self.cli(*args,expected=expected)

    def card(self,kind='paper',languages=('en',),identifier='test-one'):
        samples={'en':'Test fixture only.','zh':'仅为测试。','zh-Hant':'僅為測試。','es':'Solo es una prueba.','fr':'Exemple de test uniquement.','de':'Nur ein Testbeispiel.','ja':'テスト専用です。','ar':'مثال للاختبار فقط。','el':'Μόνο παράδειγμα δοκιμής.'}
        metadata={key:'Fixture' for key in i18n.SPECS[kind][0]}
        metadata.update({'paper':'https://arxiv.org/abs/1234.56789v1','version':'synthetic fixture','field':'Machine Learning','from_papers':'https://example.org/fixture','project':'Fixture Project','record':'Methods','status':'Fixture only','naming_basis':'Synthetic fixture only'})
        content={language:{**{k:samples.get(language,'Fixture only') for k in i18n.SPECS[kind][1]},'summary':samples.get(language,'Fixture only'),'reading_scope':samples.get(language,'Fixture only')} for language in languages}
        return {'id':identifier,'title':'Original Fixture '+identifier,'subfield':'Sequence Models','metadata':metadata,'content':content}

    def render(self,kind,card,path,**kwargs):
        data=self.put_json(self.base/'card.json',card)
        result=self.cli('render','--root',self.root,'--kind',kind,'--input',data,'--output',path,'--apply',**kwargs)
        if result.get('status')=='rendered':
            self.assertEqual(result['content_sha256'],hashlib.sha256(Path(result['path']).read_bytes()).hexdigest())
        return result

    def test_memory_beats_conversation_but_saved_and_explicit_win(self):
        fresh=self.prefs({'context':{'note_languages':['ar']},'memory':{'note_languages':['ja'],'response_language':'fr'}})
        self.assertEqual(fresh['profile']['note_languages'],['ja'])
        self.assertEqual(fresh['profile']['preference_sources']['note_languages']['source'],'memory')
        self.init(('en',))
        saved=self.prefs({'memory':{'note_languages':['ja']}})
        self.assertEqual(saved['profile']['note_languages'],['en'])
        explicit=self.prefs({'memory':{'note_languages':['ja']},'explicit':{'note_languages':['fr']}})
        self.assertEqual(explicit['profile']['note_languages'],['fr'])

    def test_memory_cannot_pick_paths_taxonomy_or_enable_external_tools(self):
        result=self.prefs({'memory':{'context':{'materials':['/not-authorized']},'taxonomy':[{'unsafe':'value'}],'extensions':{'rag':{'enabled':True}}}})
        self.assertEqual(len(result['ignored_signals']),3)
        self.assertEqual(result['profile']['context']['materials'],[])
        self.assertFalse(result['profile']['extensions']['rag']['enabled'])
        self.prefs({'raw_memory':'Do not persist a full personal conversation.'},expected=2)

    def test_task_override_is_transient_and_languages_are_separate(self):
        self.init(('en',),response_language='zh',filename_language='original')
        path=self.root/'.paper2project.json';original=path.read_bytes()
        result=self.prefs({'explicit':{'note_languages':['fr'],'response_language':'ja'}})
        self.assertEqual(result['profile']['note_languages'],['fr'])
        self.assertEqual(result['profile']['response_language'],'ja')
        self.assertEqual(result['profile']['filename_language'],'original')
        self.assertEqual(path.read_bytes(),original)
        self.prefs({'explicit':{'note_languages':['fr']}},apply=True,expected=2)
        self.assertEqual(path.read_bytes(),original)

    def test_durable_update_backups_and_does_not_rewrite_old_notes(self):
        self.init(('en',));name='Library/Computer Science/Machine Learning/Papers/Sequence Models - First.md'
        self.render('paper',self.card(identifier='old'),name)
        note=self.root/name;before=note.read_bytes();cfg=self.root/'.paper2project.json';old_cfg=cfg.read_bytes()
        saved=self.prefs({'explicit':{'note_languages':['fr'],'response_language':'zh'}},scope='workspace',apply=True)
        self.assertEqual(saved['status'],'preferences_saved')
        self.assertEqual(Path(saved['backup']).read_bytes(),old_cfg)
        self.assertEqual(note.read_bytes(),before)
        card=self.card(languages=('fr',),identifier='new');card['metadata']['paper']='https://arxiv.org/abs/9999.00001'
        self.render('paper',card,'Library/Computer Science/Machine Learning/Papers/Sequence Models - Deuxième.md')
        self.assertEqual(self.cli('check','--root',self.root)['errors'],[])
        self.prefs({'explicit':{'response_language':'ar'}},scope='workspace',apply=True,sha=hashlib.sha256(old_cfg).hexdigest(),expected=2)

    def test_all_bundled_languages_render_and_validate(self):
        codes=json.loads((PACKAGE/'assets/locales.json').read_text(encoding='utf-8'))
        original_root=self.root
        for language in codes:
            with self.subTest(language=language):
                self.root=original_root/language;self.init((language,))
                card=self.card(languages=(language,));path='Library/Computer Science/Machine Learning/Papers/Sequence Models - Note.md'
                self.render('paper',card,path)
                text=(self.root/path).read_text(encoding='utf-8');label=i18n.locale(language,self.config())['sections']['question']
                self.assertIn('## '+label,text)
                self.assertIn(card['content'][language]['question'],text)
                self.assertEqual(self.cli('check','--root',self.root)['errors'],[])

    def test_multilingual_order_and_all_six_note_templates(self):
        languages=('fr','ar','en');self.init(languages)
        paths={'field':'Library/Computer Science/Machine Learning/Machine Learning.md',
               'paper':'Library/Computer Science/Machine Learning/Papers/Sequence Models - Note.md',
               'concept':'Library/Computer Science/Machine Learning/Concepts/Concept.md',
               'direction':'Projects/Computer Science/Machine Learning/Sequence Models/Sequence Models.md',
               'project':'Projects/Computer Science/Machine Learning/Sequence Models/Fixture Project/Fixture Project.md',
               'project-record':'Projects/Computer Science/Machine Learning/Sequence Models/Fixture Project/Methods/Method.md'}
        for kind,path in paths.items():self.render(kind,self.card(kind,languages,kind),path)
        text=(self.root/paths['paper']).read_text(encoding='utf-8')
        self.assertLess(text.index('## Question de recherche'),text.index('## سؤال البحث'))
        self.assertLess(text.index('## سؤال البحث'),text.index('## Research question'))
        report=self.cli('check','--root',self.root)
        self.assertEqual(report['errors'],[])
        for kind in paths:self.assertEqual(report['roles'][kind],1)

    def test_custom_locale_pack_and_missing_pack_are_real_checks(self):
        self.put_json(self.profile,{'note_languages':['el']})
        self.cli('init','--root',self.root,'--profile',self.profile,'--non-interactive','--apply',expected=2)
        self.assertFalse(self.root.exists())
        pack=copy.deepcopy(json.loads((PACKAGE/'assets/locales.json').read_text(encoding='utf-8'))['en']);pack['name']='Ελληνικά (synthetic test labels)'
        for group in ('sections','labels','ui'):pack[group]={key:'Δοκιμή '+key for key in pack[group]}
        self.init(('el',),locale_overrides={'el':pack})
        self.render('paper',self.card(languages=('el',)),'Library/Computer Science/Machine Learning/Papers/Sequence Models - Ελληνικά.md')
        self.assertEqual(self.cli('check','--root',self.root)['errors'],[])
        pack['labels']['paper']=''
        self.prefs({'explicit':{'locale_overrides':{'el':pack}}},expected=2)

    def test_custom_role_folder_names_and_filename_style(self):
        layout={'home':'Accueil','library':'Bibliothèque','projects':'Projets','papers':'Articles','concepts':'Concepts','direction_suffix':'Pistes de recherche','groups':{'problem':'Problème','methods':'Méthodes','results':'Résultats','extensions':'Prolongements'}}
        self.init(('fr',),layout=layout,preferences={'filename_style':'original-title'})
        self.render('paper',self.card(languages=('fr',)),'Bibliothèque/Computer Science/Machine Learning/Articles/Titre original.md')
        self.assertTrue((self.root/'Accueil.md').exists())
        self.assertEqual(self.cli('check','--root',self.root)['errors'],[])

    def test_missing_translation_and_duplicate_source_do_not_write(self):
        self.init(('en','ja'));card=self.card(languages=('en',))
        self.render('paper',card,'Library/Computer Science/Machine Learning/Papers/Sequence Models - Missing.md',expected=2)
        self.assertFalse((self.root/'Library/Computer Science').exists())
        card=self.card(languages=('en','ja'));self.render('paper',card,'Library/Computer Science/Machine Learning/Papers/Sequence Models - First.md')
        card['id']='second'
        self.render('paper',card,'Library/Computer Science/Machine Learning/Papers/Sequence Models - Duplicate.md',expected=2)

    def test_profile_snapshot_first_run_and_custom_pack_template(self):
        signals=self.put_json(self.base/'signals.json',{'memory':{'note_languages':['es'],'note_detail':'ignored?'}})
        # Unknown normalized preference keys are rejected rather than persisted.
        self.cli('preferences','--root',self.root,'--signals',signals,expected=2)
        self.put_json(signals,{'memory':{'note_languages':['es'],'preferences':{'note_detail':'Concise, complete method chain.'}}})
        snapshot=self.base/'resolved.json'
        self.cli('preferences','--root',self.root,'--signals',signals,'--output',snapshot,'--apply')
        self.assertFalse(self.root.exists())
        self.cli('init','--root',self.root,'--profile',snapshot,'--non-interactive','--apply')
        self.assertEqual(self.config()['note_languages'],['es'])
        template=self.cli('locales','--template','el')
        self.assertEqual(set(template['locale_overrides']['el']['sections']),set(i18n.SECTIONS))

    def test_portable_names_and_outside_writes_are_rejected(self):
        self.put_json(self.profile,{'layout':{'library':'CON'}})
        self.cli('init','--root',self.root,'--profile',self.profile,'--non-interactive','--apply',expected=2)
        self.init(('en',))
        self.render('paper',self.card(),'../outside.md',expected=2)
        self.assertFalse((self.base/'outside.md').exists())

    def test_preference_backup_symlink_is_not_followed(self):
        self.init(('en',));outside=self.base/'outside';outside.mkdir()
        try:(self.root/'.paper2project-history').symlink_to(outside,target_is_directory=True)
        except OSError as exc:self.skipTest('Symlink privilege unavailable: '+str(exc))
        self.prefs({'explicit':{'response_language':'fr'}},scope='workspace',apply=True,expected=2)
        self.assertEqual(list(outside.iterdir()),[])

    def test_saved_origin_and_task_scope_are_preserved(self):
        signals=self.put_json(self.base/'signals.json',{'memory':{'note_languages':['fr']}})
        snapshot=self.base/'chosen.json'
        self.cli('preferences','--root',self.root,'--signals',signals,'--output',snapshot,'--apply')
        self.cli('init','--root',self.root,'--profile',snapshot,'--non-interactive','--apply')
        result=self.prefs({'explicit':{'response_language':'ja'}})
        self.assertEqual(result['profile']['preference_sources']['response_language']['scope'],'task')
        self.assertEqual(result['profile']['preference_sources']['note_languages']['source'],'memory')
        self.assertEqual(self.config()['preference_sources']['note_languages']['scope'],'workspace')

    def test_translated_heading_routes_match_without_accepting_wrong_section(self):
        languages=('en','fr');self.init(languages)
        concept_path='Library/Computer Science/Machine Learning/Concepts/Concept.md'
        self.render('concept',self.card('concept',languages,'concept-route'),concept_path)
        target=concept_path.removesuffix('.md')
        card=self.card(languages=languages)
        card['content']['en']['question']+=' [['+target+'#Definition]]'
        card['content']['fr']['question']+=' [['+target+'#Définition]]'
        path='Library/Computer Science/Machine Learning/Papers/Sequence Models - Routes.md'
        self.render('paper',card,path)
        self.assertEqual(self.cli('check','--root',self.root)['errors'],[])
        note=self.root/path;note.write_text(note.read_text(encoding='utf-8').replace('#Définition]]','#Concepts connexes]]'),encoding='utf-8')
        errors=self.cli('check','--root',self.root,expected=1)['errors']
        self.assertTrue(any('multilingual link sets' in x for x in errors))

    def test_legacy_untagged_note_survives_new_language_default(self):
        self.init(('en',))
        card=self.card();path='Library/Computer Science/Machine Learning/Papers/Sequence Models - Legacy.md'
        self.render('paper',card,path)
        note=self.root/path;text=note.read_text(encoding='utf-8');text='\n'.join(x for x in text.splitlines() if not x.startswith('p2p_languages:'))+'\n';note.write_text(text,encoding='utf-8')
        self.prefs({'explicit':{'note_languages':['ja']}},scope='workspace',apply=True)
        self.assertEqual(note.read_text(encoding='utf-8'),text)
        self.assertEqual(self.cli('check','--root',self.root)['errors'],[])

    def test_unknown_nested_signals_are_not_persisted(self):
        self.prefs({'memory':{'preferences':{'unexpected_field':'fixture'}}},expected=2)
        self.prefs({'explicit':{'extensions':{'rag':{'unexpected_field':'fixture'}}}},expected=2)


if __name__=='__main__':unittest.main()
