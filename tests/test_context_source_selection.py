"""Selected source cards must control actual preparation and saved evidence."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import context_setup as c
import context_runner as routes
from test_context_setup import METADATA, public
import test_context_runner as runner_tests

class SourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.metadata=self.root/'metadata.tsv';self.metadata.write_text(METADATA)
        env=patch.dict(os.environ,{'WINGS_CONTEXT_CACHE':str(self.root/'cache'),'WINGS_EBIRDST_CACHE':str(self.root/'rasters')});env.start();self.addCleanup(env.stop)
        self.calls=[]
    def executor(self,args,log,**kwargs):
        self.calls.append(args);Path(log).write_text('fixture only')
        if '--snakefile' in args:
            request=json.loads(Path(args[-1]).read_text());c.write(Path(request['output']),{'summary':{'ready_profile_count':2}});return
        output=Path(args[args.index('--output')+1])
        if 'build_ecological_context.py' in args[1]:c.write(output,{'bindings':{'A':{'status':'READY'}},'birdcast':{'bindings':{'A':{'status':'AVAILABLE'},'B':{'status':'AVAILABLE'}}}})
        else:c.write(output,public())
    def prepare(self,sources,**kwargs):
        return c.prepare(self.metadata,self.root/'context',{'selected_sources':sources,'network':False,**kwargs},executor=self.executor)
    def test_all_off_skips_providers_and_pins_empty_public_comparison(self):
        with patch.object(c,'find_ebird',side_effect=AssertionError('No cache inspection')),patch.object(c,'import_ebird',side_effect=AssertionError('No import')):
            data=self.prepare([],ebird_source='/ignored/source',outbreak_file='/ignored.csv')
        self.assertEqual(self.calls,[]);self.assertEqual(data['status'],'READY')
        self.assertTrue(all(r['status']=='DISABLED' for r in data['providers'].values()))
        folder,_=c.selected(self.root/'context',self.metadata)
        self.assertEqual(set(data['artifacts']),{'validated_metadata','genotypes'})
        public_data=json.loads((folder/'genotypes.json').read_text());self.assertEqual(public_data['audit']['included_runs'],0)
        self.assertEqual(public_data['context_scope']['reason'],'Not selected')
        config=c.configure({},self.root/'context',self.metadata)
        self.assertFalse(config['ecological_context']['enabled']);self.assertFalse(config['outbreak_context']['enabled']);self.assertEqual(config['ebird']['mode'],'off')
        self.assertFalse(config['genotype_frequencies']['auto_refresh']);self.assertTrue(config['genotype_frequencies']['prepared_snapshot'])
        self.assertEqual(config['phenology']['snapshot'],'');c.validate_config(config,self.metadata,['A','B'])
    def test_weather_only_calls_one_provider_and_supplies_structured_counts(self):
        data=self.prepare(['ecology']);self.assertEqual(len(self.calls),1);self.assertIn('build_ecological_context.py',self.calls[0][1])
        self.assertEqual(data['providers']['ecology']['weather_ready'],1);self.assertEqual(data['providers']['ecology']['migration_ready'],2)
        self.assertEqual(data['providers']['ecology']['status'],'PARTIAL');self.assertEqual(data['providers']['public_genotypes']['status'],'DISABLED')
    def test_public_only_has_no_ecology_or_imports(self):
        data=self.prepare(['public_genotypes']);self.assertEqual(len(self.calls),1);self.assertIn('refresh_genotype_frequencies.py',self.calls[0][1])
        self.assertEqual(data['providers']['public_genotypes']['included_runs'],2);self.assertNotIn('ecology',data['artifacts'])
    def test_phenology_only_skips_other_commands(self):
        with patch.dict(os.environ,{'EBIRDST_ACCESS_KEY':'fixture'}),patch.object(c.shutil,'which',return_value='/fake/snakemake'):
            data=self.prepare(['phenology'],network=True)
        self.assertEqual(len(self.calls),1);self.assertIn('--snakefile',self.calls[0]);self.assertEqual(data['providers']['phenology']['ready_profiles'],2)
    def test_ebird_only_uses_selected_cache_without_other_providers(self):
        with patch.object(c,'find_ebird',return_value={'status':'NEEDS_IMPORT','reason':'fixture'}) as find:
            data=self.prepare(['ebird'])
        self.assertEqual(find.call_count,2);self.assertEqual(self.calls,[]);self.assertEqual(data['providers']['ebird']['status'],'NEEDS_IMPORT');self.assertEqual(data['status'],'READY')
    def test_aphis_only_has_no_executor_calls(self):
        data=self.prepare(['outbreak'],outbreak_file=str(self.root/'missing.csv'))
        self.assertEqual(self.calls,[]);self.assertEqual(data['providers']['outbreak']['status'],'NEEDS_IMPORT')
    def test_selection_validation_and_legacy_defaults(self):
        for value in ['ecology',['bad'],['ecology','ecology'],[{}],None]:
            with self.subTest(value=value),self.assertRaises(ValueError):c.options({'selected_sources':value})
        with self.assertRaisesRegex(ValueError,'must also be selected'):c.options({'selected_sources':[],'required':['ecology']})
        self.assertTrue(c.source_enabled(c.options(),'ecology'))
        self.assertFalse(c.source_enabled(c.options({'phenology':False}),'phenology'))
        self.assertTrue(c.options({'selected_sources':['phenology'],'phenology':False})['phenology'])
        self.assertEqual(c.options({'selected_sources':['outbreak','ecology']})['selected_sources'],['ecology','outbreak'])
    def test_plan_marks_deselected_sources_off_without_reading_cache(self):
        with patch.object(c,'find_ebird',side_effect=AssertionError('Disabled eBird lookup')):
            data=c.plan(self.metadata,{'selected_sources':['ecology']})
        self.assertEqual(data['providers']['ecology']['status'],'PLANNED')
        for source in set(c.PROVIDERS)-{'ecology'}:self.assertEqual(data['providers'][source]['status'],'DISABLED')
    def test_reprepare_cannot_carry_previously_selected_artifacts(self):
        self.prepare(['ecology','public_genotypes']);data=self.prepare([])
        self.assertNotIn('ecology',data['artifacts']);folder,_=c.selected(self.root/'context',self.metadata)
        self.assertEqual(json.loads((folder/'genotypes.json').read_text())['audit']['included_runs'],0)

class SourceAttachmentTests(unittest.TestCase):
    setUp=runner_tests.RunnerContextTests.setUp
    run_directory=runner_tests.RunnerContextTests.run_directory
    def test_explicit_selection_must_match_before_attachment(self):
        source=self.run_directory();settings={'network':False,'selected_sources':[]}
        c.prepare(source/'inputs/metadata.tsv',source/'context',settings,executor=lambda *a,**k:self.fail('Unexpected provider'))
        target=self.run_directory('target')
        with self.assertRaisesRegex(ValueError,'settings differ'):
            routes.start('target',{'reuse_run_id':'source','options':{**settings,'selected_sources':['ecology']}},vars(self.runner))
        self.assertFalse((target/'context/selection.json').exists());self.assertFalse(routes.busy('target'))
        result=routes.start('target',{'reuse_run_id':'source','options':settings},vars(self.runner))
        self.assertEqual(result['status'],'READY');self.assertEqual(self.runner.read_state('target')['status'],'created')

if __name__=='__main__':unittest.main()
