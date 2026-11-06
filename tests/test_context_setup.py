"""Offline behavioral checks for metadata-driven context and local runner integration."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import context_setup as c
import context_runner as routes
import prepare_public_genotype_snapshot as genotype

METADATA='sample_id\thost\tcollection_date\tcountry\tstate\tlatitude\tlongitude\nB\tCAGO\t2024-09-15\tUS\tArizona\t33.4\t-112.1\nA\tCAGO\t2024-09-15\tUS\tAZ\t33.4\t-112.1\n'

def public():
    return {'schema_version':'wings.genotype-frequencies.v1','unit':'SRA run','has_metadata':True,
            'groups':[{'host':'canada goose','location':'United States/Arizona/','month':'2024-09','status':'assigned','genotype':'B3.13','n':2},
                      {'host':'canada goose','location':'United States/California/','month':'2024-09','status':'assigned','genotype':'B3.13','n':5}],
            'audit':{'included_runs':7,'assigned_runs':7},'source_commit':'fixture','report_refresh':{'status':'offline'}}

class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.metadata=self.root/'metadata.tsv';self.metadata.write_text(METADATA)
        self.env=patch.dict(os.environ,{'WINGS_CONTEXT_CACHE':str(self.root/'cache'),'WINGS_EBIRDST_CACHE':str(self.root/'rasters')})
        self.env.start();self.addCleanup(self.env.stop)
        self.options={'network':False,'phenology':False}
        self.calls=[]
    def executor(self,args,log,timeout=900):
        self.calls.append(args);Path(log).write_text('fixture provider\n')
        output=Path(args[args.index('--output')+1])
        if 'build_ecological_context.py' in args[1]:
            metadata=Path(args[args.index('--metadata')+1])
            data=c.load('build_ecological_context.py')['build_snapshot'](metadata,self.root/'cache'/'ecology',birdcast_cache=True)
        else:data=public()
        c.write(output,data)
    def prepare(self,**settings):
        return c.prepare(self.metadata,self.root/'context',{**self.options,**settings},executor=self.executor)
    def test_unpaired_metadata_and_request_deduplication(self):
        proposal=c.plan(self.metadata,self.options)
        self.assertEqual(proposal['sample_count'],2)
        self.assertEqual(len(proposal['weather_queries']),1)
        self.assertEqual(len(proposal['birdcast_queries']),1)
        self.assertEqual(len(proposal['ebird_request']['windows']),1)
        self.assertEqual(proposal['species'],['Canada Goose'])
        self.assertEqual(proposal['ebird_request']['species'],'All species')
        self.assertTrue(proposal['ebird_request']['include_sampling_event_data'])
    def test_missing_metadata_is_not_imputed(self):
        self.metadata.write_text('sample_id\nA\n')
        plan=c.plan(self.metadata,self.options)
        self.assertEqual(plan['weather_queries'],[]);self.assertEqual(plan['scopes'],[])
        self.assertGreater(len(plan['issues']),0)
        self.assertEqual(c.scoped_genotypes(public(),plan)['audit']['included_runs'],0)
    def test_duplicate_ids_fail_before_provider_commands(self):
        self.metadata.write_text('sample_id\nA\nA\n')
        with self.assertRaisesRegex(ValueError,'unique'):self.prepare()
        self.assertEqual(self.calls,[])
    def test_invalid_dates_fail_production_validation_before_download(self):
        self.metadata.write_text(METADATA.replace('2024-09-15','2024-02-31'))
        with self.assertRaisesRegex(ValueError,'validation failed'):self.prepare()
        self.assertEqual(self.calls,[])
    def test_scope_filters_host_region_month_without_double_counting(self):
        data=public();data['groups'] += [dict(data['groups'][0],month=None,n=3),dict(data['groups'][0],host='mallard',n=4)]
        data['audit']={'included_runs':14,'assigned_runs':14}
        result=c.scoped_genotypes(data,c.plan(self.metadata,self.options))
        self.assertEqual(result['audit']['included_runs'],2)
        self.assertEqual(result['source_audit']['included_runs'],14)
        self.assertEqual(result['context_scope']['excluded_runs'],12)
    def test_empty_scope_does_not_fall_back_to_global(self):
        self.metadata.write_text(METADATA.replace('CAGO','MALL'))
        result=self.prepare();folder,_=c.selected(self.root/'context',self.metadata)
        self.assertEqual(result['providers']['public_genotypes']['status'],'UNAVAILABLE')
        self.assertEqual(json.loads((folder/'genotypes.json').read_text())['audit']['included_runs'],0)
    def test_global_comparison_requires_explicit_option(self):
        self.prepare(global_genotypes=True);folder,_=c.selected(self.root/'context',self.metadata)
        self.assertEqual(json.loads((folder/'genotypes.json').read_text())['audit']['included_runs'],7)
    def test_offline_commands_do_not_request_downloads(self):
        self.prepare()
        self.assertIn('--birdcast-cache',self.calls[0]);self.assertIn('--offline',self.calls[1])
        self.assertNotIn('--fetch-weather',self.calls[0]);self.assertNotIn('--fetch-birdcast',self.calls[0])
    def test_optional_unavailable_sources_allow_analysis_but_required_block(self):
        result=self.prepare();self.assertEqual(result['status'],'READY');self.assertNotEqual(result['providers']['ebird']['status'],'READY')
        result=self.prepare(required=['ebird']);self.assertEqual(result['status'],'BLOCKED')
        with self.assertRaisesRegex(ValueError,'Required context'):c.selected(self.root/'context',self.metadata)
    def test_metadata_change_invalidates_selection(self):
        self.prepare();self.metadata.write_text(METADATA.replace('33.4','33.5'))
        with self.assertRaisesRegex(ValueError,'metadata'):c.selected(self.root/'context',self.metadata)
    def test_snapshot_content_change_invalidates_selection(self):
        self.prepare();folder,_=c.selected(self.root/'context',self.metadata)
        (folder/'genotypes.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):c.selected(self.root/'context',self.metadata)
    def test_pointer_tampering_is_rejected(self):
        self.prepare();pointer=self.root/'context'/'selection.json'
        c.write(pointer,{'snapshot_id':'../outside'})
        with self.assertRaisesRegex(ValueError,'identity'):c.selected(self.root/'context',self.metadata)
    def test_reprepare_keeps_previous_snapshot(self):
        first=self.prepare();second=self.prepare()
        self.assertNotEqual(first['snapshot_id'],second['snapshot_id'])
        self.assertTrue((self.root/'context'/'snapshots'/first['snapshot_id']/'genotypes.json').exists())
    def test_configuration_pins_sources_and_disables_background_downloads(self):
        self.prepare();config=c.configure({},self.root/'context',self.metadata)
        self.assertFalse(config['ecological_context']['auto_birdcast'])
        self.assertFalse(config['genomic_ecological_concordance']['auto_weather'])
        self.assertFalse(config['genomic_ecological_concordance']['auto_phenology'])
        self.assertTrue(config['genotype_frequencies']['prepared_snapshot'])
        self.assertFalse(config['phenology']['enabled'])
    def test_production_metadata_normalization_is_byte_identical(self):
        self.prepare();folder,_=c.selected(self.root/'context',self.metadata)
        target=self.root/'second.tsv';c.normalized_metadata(self.metadata,target)
        self.assertEqual(target.read_bytes(),(folder/'validated_metadata.tsv').read_bytes())
        self.assertEqual(target.read_text().splitlines()[1].split('\t')[0],'A')
    def test_provider_failure_is_visible_and_empty_genotype_is_valid(self):
        def fail(*a,**k):raise ValueError('simulated provider failure')
        result=c.prepare(self.metadata,self.root/'context',self.options,executor=fail)
        self.assertEqual(result['status'],'READY')
        self.assertIn('simulated',result['providers']['public_genotypes']['reason'])
        folder,_=c.selected(self.root/'context',self.metadata)
        c.load('refresh_genotype_frequencies.py')['validate_snapshot'](json.loads((folder/'genotypes.json').read_text()))
    def test_prepared_genotype_copy_never_refreshes(self):
        source=self.root/'seed.json';c.write(source,public());out=self.root/'out.json'
        with patch.object(genotype,'refresh',side_effect=AssertionError('network')):
            genotype.prepare(source,out,prepared=True)
        self.assertEqual(source.read_bytes(),out.read_bytes())
    def test_report_embeds_availability_without_machine_paths(self):
        result=self.prepare();folder,_=c.selected(self.root/'context',self.metadata)
        build=c.load('build_surveillance_explorer.py')['build_payload']
        payload=build(folder/'validated_metadata.tsv',[],[],context_setup=folder/'selection.json',ecological_context=folder/'ecology.json')
        self.assertEqual(payload['context_setup']['snapshot_id'],result['snapshot_id'])
        self.assertTrue(any('ebird context' in w for w in payload['warnings']))
        self.assertNotIn(str(self.root),json.dumps(payload['context_setup']))
    def test_options_validate_types_and_unknown_keys(self):
        for options in ({'network':'false'},{'days':True},{'days':0},{'required':['bogus']},{'api_key':'secret'}):
            with self.subTest(options=options),self.assertRaises(ValueError):c.options(options)
    def test_import_requires_coverage_confirmation(self):
        with self.assertRaisesRegex(ValueError,'Confirm'):c.import_ebird(self.metadata,c.options({'ebird_source':str(self.root)}))
    def test_import_rejects_mixed_releases_before_processing(self):
        for name in ['ebd_US_relAug-2026.txt','ebd_sampling_relSep-2026.txt','terms_of_use.txt','recommended_citation.txt']:(self.root/name).write_text('fixture')
        with self.assertRaisesRegex(ValueError,'same release'):c.import_ebird(self.metadata,c.options({'ebird_source':str(self.root),'all_species_confirmed':True}))
    def test_source_commands_are_shell_free(self):
        with patch.object(c.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
            c.command(['python','a path;$(x)'],self.root/'log')
        self.assertEqual(run.call_args.args[0],['python','a path;$(x)'])
        self.assertNotIn('shell',run.call_args.kwargs)
    def test_phenology_uses_normalized_metadata(self):
        def executor(args,log,timeout=900):
            if '--snakefile' not in args:return self.executor(args,log,timeout)
            request=json.loads(Path(args[-1]).read_text());meta=Path(request['metadata'])
            prefix=Path(args[args.index('--conda-prefix')+1])
            self.assertFalse(prefix.is_relative_to(Path(request['output']).parent))
            self.assertIn('conda-platforms',prefix.parts)
            self.assertIn('metadata_status',meta.read_text())
            c.write(Path(request['output']),{'schema_version':'wings.phenology.v1','synthetic':True,
                'inputs':{'metadata_sha256':c.sha(meta)},'profiles':[], 'sample_status':[], 'summary':{'ready_profile_count':0}})
        with patch.dict(os.environ,{'EBIRDST_ACCESS_KEY':'fixture'}),patch.object(c.shutil,'which',return_value='/fake/snakemake'):
            c.prepare(self.metadata,self.root/'context',{'phenology':True},executor=executor)
        folder,_=c.selected(self.root/'context',self.metadata)
        payload=c.load('build_surveillance_explorer.py')['build_payload'](folder/'validated_metadata.tsv',[],[],phenology=folder/'phenology.json')
        self.assertIsNotNone(payload['ecological_clock'])

    def test_terminal_configuration_detects_changed_selection_and_wrong_read_set(self):
        self.prepare();config=c.configure({},self.root/'context',self.metadata)
        c.validate_config(config,self.metadata,['A','B'])
        with self.assertRaisesRegex(ValueError,'FASTQ'):c.validate_config(config,self.metadata,['A'])
        config['context_setup']['selection_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'selection changed'):c.validate_config(config,self.metadata)
    def test_terminal_configuration_rejects_untracked_snapshot_override(self):
        self.prepare();config=c.configure({},self.root/'context',self.metadata)
        config['genotype_frequencies']['snapshot']=str(self.root/'untracked.json')
        with self.assertRaisesRegex(ValueError,'path differs'):c.validate_config(config,self.metadata)
    def test_empty_public_snapshot_can_be_rendered_without_invented_counts(self):
        self.metadata.write_text(METADATA.replace('CAGO','MALL'));self.prepare()
        folder,_=c.selected(self.root/'context',self.metadata)
        from build_genotype_dashboard import build_dashboard
        # The production dashboard must accept the schema-valid explicit empty comparison.
        html=build_dashboard(ROOT/'genotypes.html',[ROOT/'assets/wings-genotypes.css'],ROOT/'assets/wings-genotypes.js',folder/'genotypes.json')
        self.assertIn('wings.genotype-frequencies.v1',html)

if __name__=='__main__':unittest.main()
