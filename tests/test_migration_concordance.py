import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from test_genomic_ecological_concordance import fixture, gec, leaf
ROOT=Path(__file__).parents[1]

def migration_fixture():
    data=fixture(12)
    data['ecological_context']['states']={'KY':'Kentucky','AZ':'Arizona'}
    start=date(2025,3,1)
    rows=[]
    total=0
    for i in range(107):
        total+=0 if i==0 else ((i*37)%53)**2+10
        rows.append({'date':(start+timedelta(days=i)).isoformat(),'cumulative_birds':total})
    season={'schema_version':1,'key':'US-KY_2025-03-01_2025-06-15','state_code':'KY','label':'Spring 2025','metric':'cumulative_birds_crossed','start_date':'2025-03-01','end_date':'2025-06-15','rows':rows}
    bird={'status':'READY','night_offset_days':-1,'seasons':[season],'bindings':{},'records':[]}
    seen=set()
    for sample,profile in zip(data['samples'],data['ecological_clock']['profiles']):
        old=date.fromisoformat(sample['collection_date'])
        sample.update(country='US',state='Kentucky',collection_date=(date(2025,3,2)+(old-date(2025,1,1))).isoformat())
        profile['collection']['date']=sample['collection_date']
        night=(date.fromisoformat(sample['collection_date'])-timedelta(days=1)).isoformat()
        binding={'status':'AVAILABLE' if night<=season['end_date'] else 'UNAVAILABLE','state_code':'KY','night':night,'metadata':{'country':'US','state':'KY','collection_date':sample['collection_date']}}
        bird['bindings'][sample['sample_id']]=binding
        if binding['status']=='AVAILABLE' and night not in seen:
            bird['records'].append({'state_code':'KY','date':night,'status':'AVAILABLE','birds_crossed':0 if night=='2025-03-01' else 200})
            seen.add(night)
    data['ecological_context']['birdcast']=bird
    return data

class MigrationConcordanceTests(unittest.TestCase):
    def test_zero_night_is_available_and_summer_is_missing(self):
        data=migration_fixture();rows=gec.migration_features(data)
        self.assertTrue(rows['s00']['migration_available'])
        self.assertEqual(rows['s00']['migration_birds_crossed'],0)
        self.assertEqual(rows['s00']['migration_progress'],0)
        self.assertEqual(rows['s11']['migration_status'],'OUTSIDE_COVERAGE')
        self.assertIsNone(rows['s11']['migration_progress'])
        self.assertEqual(rows['s00']['migration_season_label'],'Spring 2025')
        self.assertIsNone(gec.migration_distance(rows['s00'],rows['s11']))

    def test_august_uses_source_fall_season_and_june_boundary_uses_preceding_night(self):
        data=migration_fixture();bird=data['ecological_context']['birdcast'];shift=timedelta(days=153)
        season=bird['seasons'][0];season.update(key='fall',label='Fall 2025',start_date='2025-08-01',end_date='2025-11-15')
        for row in season['rows']: row['date']=(date.fromisoformat(row['date'])+shift).isoformat()
        for row in bird['records']: row['date']=(date.fromisoformat(row['date'])+shift).isoformat()
        for sample in data['samples']:
            sample['collection_date']=(date.fromisoformat(sample['collection_date'])+shift).isoformat()
            binding=bird['bindings'][sample['sample_id']]
            binding['night']=(date.fromisoformat(binding['night'])+shift).isoformat()
            binding['metadata']['collection_date']=sample['collection_date']
        self.assertEqual(gec.migration_features(data)['s00']['migration_season_label'],'Fall 2025')
        data=migration_fixture();sample=data['samples'][0];bird=data['ecological_context']['birdcast']
        sample['collection_date']='2025-06-16';binding=bird['bindings']['s00'];binding['night']='2025-06-15';binding['metadata']['collection_date']='2025-06-16'
        bird['records'].append({'state_code':'KY','date':'2025-06-15','status':'AVAILABLE','birds_crossed':100})
        result=gec.migration_features(data)['s00']
        self.assertTrue(result['migration_available']);self.assertEqual(result['migration_progress'],1)

    def test_minimum_context_gate_uses_actual_contexts_even_with_many_samples(self):
        data=migration_fixture()
        for sample in data['samples']:
            sample['collection_date']='2025-03-02'
            data['ecological_context']['birdcast']['bindings'][sample['sample_id']]=copy.deepcopy(data['ecological_context']['birdcast']['bindings']['s00'])
        result=gec.build(data,permutations=9)
        model=next(row for row in result['models'] if row['segment']=='HA' and row['comparison']=='migration_vs_ecology')
        self.assertEqual(model['n_migration_contexts'],1);self.assertEqual(model['n_samples'],12)
        self.assertEqual(model['status'],'INSUFFICIENT_MIGRATION_CONTEXTS');self.assertIsNone(model['delta_r2'])

    def test_stale_state_date_country_and_duplicate_records_cannot_bind(self):
        for change in ('state','date','country','duplicate'):
            data=migration_fixture()
            if change=='state': data['samples'][0]['state']='Arizona'
            if change=='date': data['samples'][0]['collection_date']='2025-03-03'
            if change=='country': data['samples'][0]['country']='Canada'
            if change=='duplicate': data['ecological_context']['birdcast']['records'].append(copy.deepcopy(data['ecological_context']['birdcast']['records'][0]))
            self.assertFalse(gec.migration_features(data)['s00']['migration_available'])

    def test_incomplete_gapped_decreasing_and_all_zero_seasons_withhold_normalization(self):
        for kind in ('tail','gap','decreasing','zero','duplicate'):
            data=migration_fixture();rows=data['ecological_context']['birdcast']['seasons'][0]['rows']
            if kind=='tail': rows.pop()
            if kind=='gap': rows.pop(20)
            if kind=='decreasing': rows[20]['cumulative_birds']=-1
            if kind=='zero':
                for row in rows: row['cumulative_birds']=0
            if kind=='duplicate': rows[20]['date']=rows[19]['date']
            result=gec.migration_features(data)['s00']
            self.assertFalse(result['migration_available']);self.assertIsNone(result['migration_progress'])
            self.assertEqual(result['migration_birds_crossed'],0)

    def test_scaling_raw_state_counts_does_not_change_context_distance(self):
        data=migration_fixture();original=gec.migration_features(data)
        for row in data['ecological_context']['birdcast']['seasons'][0]['rows']: row['cumulative_birds']*=100
        scaled=gec.migration_features(data)
        self.assertAlmostEqual(gec.migration_distance(original['s00'],original['s10']),gec.migration_distance(scaled['s00'],scaled['s10']))

    def test_missing_coordinates_keep_context_but_do_not_invent_geographic_pairs(self):
        data=migration_fixture();data['samples'][0]['latitude']=data['samples'][0]['longitude']=None
        pairs,samples,_=gec.build_pairs(data)
        self.assertTrue(samples[0]['migration_available'])
        self.assertTrue(all(row['geographic_km'] is None for row in pairs if row['sample_a']=='s00'))

    def test_fixed_input_addition_preserves_existing_results_and_uses_same_pair_set(self):
        data=migration_fixture();pairs,samples,_=gec.build_pairs(data)
        old=gec.compare_models(pairs,permutations=9,seed=7)
        result=gec.build(data,permutations=9,seed=7)
        self.assertEqual(result['models'][:len(old)],old)
        model=next(row for row in result['models'] if row['segment']=='HA' and row['comparison']=='migration_vs_ecology')
        self.assertEqual(model['status'],'READY');self.assertEqual(model['n_migration_contexts'],11)
        self.assertEqual(model['n_samples'],11);self.assertEqual(model['n_pairs'],55)
        self.assertGreaterEqual(model['delta_r2'],0)
        self.assertEqual(model['permutations_valid'],9)
        self.assertIsNotNone(model['fdr_q'])
        self.assertEqual(model['reduced_predictors'],','.join(gec.ECOLOGY))
        self.assertEqual(model['full_predictors'],','.join(gec.MIGRATION))

    def test_shared_contexts_do_not_inflate_context_count_or_claim_p_values(self):
        data=migration_fixture();sample=copy.deepcopy(data['samples'][0]);sample['sample_id']='replicate'
        data['samples'].append(sample)
        profile=copy.deepcopy(data['ecological_clock']['profiles'][0]);profile['sample_id']='replicate';data['ecological_clock']['profiles'].append(profile)
        data['ecological_context']['birdcast']['bindings']['replicate']=copy.deepcopy(data['ecological_context']['birdcast']['bindings']['s00'])
        data['trees']['HA']['root']['children'].append(leaf('replicate',.023))
        result=gec.build(data,permutations=9)
        model=next(row for row in result['models'] if row['segment']=='HA' and row['comparison']=='migration_vs_ecology')
        self.assertEqual(model['n_migration_contexts'],11);self.assertEqual(model['n_samples'],12)
        self.assertEqual(model['status'],'DESCRIPTIVE');self.assertIsNone(model['permutation_p']);self.assertIsNone(model['fdr_q'])
        self.assertIsNotNone(model['delta_r2'])

    def test_cli_and_compact_attachment_include_migration_fields_and_accept_older_reports(self):
        spec=importlib.util.spec_from_file_location('attach',ROOT/'scripts/attach_genomic_ecological_concordance.py');attach=importlib.util.module_from_spec(spec);spec.loader.exec_module(attach)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);input_file=path/'explorer.json';input_file.write_text(json.dumps(migration_fixture()))
            subprocess.run([sys.executable,str(ROOT/'scripts/build_genomic_ecological_concordance.py'),'--explorer',str(input_file),'--output-dir',str(path/'out'),'--permutations','0'],check=True,capture_output=True)
            result=json.loads((path/'out/concordance.json').read_text())
            compact=attach.compact_concordance(result)
            self.assertEqual(len(compact['migration_samples']),12)
            self.assertIn('migration_context_distance',(path/'out/pairs.tsv').read_text().splitlines()[0])
            self.assertIn('migration_progress',(path/'out/sample_features.tsv').read_text().splitlines()[0])
            result['schema_version']='wings.genomic_ecological_concordance.v2';self.assertTrue(attach.compact_concordance(result))

if __name__=='__main__': unittest.main()
