import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import phylodynamic_selection as selection
import phylodynamic_mapping as mapping
from phylodynamic_inference import infer
from phylodynamic_summary import summarize


def nodes():
    return [dict(id='r',parent=None,date='2020-01-01'),
            dict(id='a',parent='r',date='2021-01-01',observed_state='A'),
            dict(id='b',parent='r',date='2022-01-01',observed_state='B')]


def candidate(i,loc='USA:KY',month='2024-01',seq='ACGT'*30):
    return dict(id=str(i),location=loc,month=month,date=month+'-01',host='bird',sequence=seq)


class SamplingTests(unittest.TestCase):
    def test_strict_dates_and_configuration(self):
        for value in ('2024','2024-03','2025-02-29','unknown'):
            self.assertIsNone(selection.exact_date(value))
        self.assertIsNotNone(selection.exact_date('2024-02-29'))
        for cfg in ({'replicates':0},{'segments':['BAD']},{'typo':1},{'strategies':['balanced','balanced']}, {'enabled':'true'}):
            with self.assertRaises(ValueError):selection.configuration(cfg)

    def test_balance_accounts_for_study_and_does_not_mutate_input(self):
        cfg=selection.configuration(dict(max_references=4,max_per_location=4))
        pool=[candidate(i,'USA:KY') for i in range(10)]+[candidate(10+i,'USA:OH') for i in range(10)]
        study=[candidate('s'+str(i),'USA:KY') for i in range(5)]
        before=json.dumps(pool)
        chosen=selection.select(pool,study,cfg,'balanced',3)
        self.assertEqual({r['location'] for r in chosen},{'USA:OH'})
        self.assertEqual(json.dumps(pool),before)
        self.assertEqual(chosen,selection.select(list(reversed(pool)),study,cfg,'balanced',3))

    def test_caps_strata_and_replicates(self):
        pool=[candidate(i,'USA:KY' if i<12 else 'USA:OH',f'2024-0{i%3+1}') for i in range(24)]
        cfg=selection.configuration(dict(max_references=12,max_per_location=3))
        chosen=selection.select(pool,[],cfg,'balanced',3)
        self.assertEqual(len(chosen),6)
        self.assertEqual(len({(r['location'],r['month']) for r in chosen}),6)
        self.assertNotEqual(chosen,selection.select(pool,[],cfg,'balanced',5))
        self.assertEqual(len(selection.select(pool,[],cfg,'available',5)),12)

    def test_diversity_prefers_different_sequence(self):
        cfg=selection.configuration(dict(max_references=1))
        study=[candidate('study',seq='A'*120)]
        pool=[candidate('same',seq='A'*120),candidate('different',seq='C'*120)]
        self.assertEqual(selection.select(pool,study,cfg,'diversity',4)[0]['id'],'different')

    def test_geography_normalizes_state_codes_without_guessing(self):
        aliases,locs=selection.geography()
        cfg=selection.configuration({})
        row=dict(collection_date='2024-03-02',country='United States',state='KY')
        r=selection.prepare_row(row,'ACGT'*30,'reference','r',aliases,cfg,120)
        self.assertEqual(r['location'],'USA:KY')
        self.assertEqual(r['reasons'],[])
        row['state']='Atlantis'
        self.assertIn('unresolved_state_or_province',selection.prepare_row(row,'ACGT'*30,'reference','r',aliases,cfg,120)['reasons'])

    @patch('phylodynamic_lineages.screen')
    def test_full_selection_audit_and_blocking(self, screening):
        def screened(study,candidates,segment,output,*args):
            audit=dict(status='ready',reasons=[],target_clade='fixture-clade',study_clades=['fixture-clade'],anchor_ids=[])
            selection.write_json(output/'lineage.json',audit)
            return candidates,[],audit
        screening.side_effect=screened
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); results=root/'results'; meta=root/'metadata.tsv'
            selection.write_tsv(meta,['sample_id','collection_date','country','state','host'],
                [dict(sample_id='s',collection_date='2024-06-01',country='USA',state='KY',host='bird')])
            (results/'s/genoflu').mkdir(parents=True)
            (results/'s/genoflu/GenoFLU.tsv').write_text('consensus Genotype --> D1.1: HA:ea3, NA:am4N1 at percent identity at 98.0')
            selection.write_tsv(results/'s/coverage/coverage.tsv',['segment','overall_status','contig'],
                [dict(segment='HA',overall_status='PASS',contig='A_HA')])
            (results/'s/merged').mkdir()
            (results/'s/merged/consensus_all_segments.fasta').write_text('>A_HA\n'+'ACGT'*30+'\n')
            public=[]
            for i in range(8):
                public.append(dict(HA_accession=f'R{i}',HA_type='ea3',run_status='OK',
                    collection_date=f'2024-0{i%5+1}-01',country='USA',state='OH',host='bird'))
            public[1]['collection_date']='2024'
            public[2]['HA_type']='other'
            public[3].update(public[0],HA_accession='R3')  # same date/place/host/sequence
            table=root/'public.tsv'; fasta=root/'public.fasta'
            selection.write_tsv(table,list(public[0]),public)
            fasta.write_text(''.join(f'>R{i}\n'+('ACGT'*30)+'\n' for i in range(8)))
            cfg=dict(strategies=['balanced'],replicates=2,min_tips=3,min_date_span_days=1)
            out=root/'selection'
            summary=selection.build(results,meta,table,fasta,out,cfg)
            exclusions=summary['segments']['HA']['exclusions']
            self.assertGreater(exclusions['missing_or_partial_date'],0)
            self.assertGreater(exclusions['different_or_missing_segment_type'],0)
            self.assertNotIn('redundant_sequence_date_location_host',exclusions)
            self.assertEqual(summary['segments']['HA']['eligible_references'],6)
            self.assertEqual(len(summary['replicates']),2)
            self.assertEqual(summary['replicates'][0]['status'],'ready')
            snapshot=(out/'selection_summary.json').read_bytes()
            selection.build(results,meta,table,fasta,out,cfg)
            self.assertEqual(snapshot,(out/'selection_summary.json').read_bytes())
            blocked=selection.build(results,meta,table,fasta,root/'blocked',dict(cfg,requested_locations=['USA:CA']))
            self.assertEqual(blocked['replicates'][0]['status'],'blocked')
            destination=root/'inference'
            destination.mkdir();(destination/'movie.json').write_text('{"stale":true}')
            result=infer(root/'blocked/HA/balanced/replicate_1',destination,1)
            self.assertEqual(result['status'],'blocked')
            self.assertIsNone(json.loads((destination/'movie.json').read_text()))


class MappingTests(unittest.TestCase):
    def test_likelihood_against_explicit_state_sum(self):
        tree=mapping.TraitTree(nodes(),['A','B'])
        for q in (.001,.1,1,10):
            p=lambda t,i,j: .5+((1 if i==j else 0)-.5)*math.exp(-2*q*t)
            expected=sum(.5*p(1,r,0)*p(2,r,1) for r in (0,1))
            self.assertAlmostEqual(math.exp(tree.prune([q])[0]),expected,places=12)

    def test_quadrature_matches_independent_integration(self):
        tree=mapping.TraitTree(nodes(),['A','B'])
        q,w,diag=mapping.posterior_grid(tree)
        # For this two-tip tree P(A,B)=(1-exp(-6q))/4; Exp(1) prior.
        z=quad(lambda x:(1-math.exp(-6*x))*math.exp(-x)/4,0,np.inf)[0]
        mean=quad(lambda x:x*(1-math.exp(-6*x))*math.exp(-x)/4,0,np.inf)[0]/z
        self.assertAlmostEqual(float(q@w),mean,places=5)
        self.assertLess(diag['cdf_error'],.001)

    def test_bridge_counts_match_two_state_analytic_result(self):
        rng=np.random.default_rng(6);q=.7
        for end in (0,1):
            counts=[len(mapping.bridge(0,end,1,q,2,rng)) for _ in range(10000)]
            self.assertTrue(all(n%2==end for n in counts))
            expected=q*(math.tanh(q) if end==0 else 1/math.tanh(q))
            self.assertAlmostEqual(np.mean(counts),expected,delta=.035)
        self.assertEqual(mapping.bridge(0,0,0,1,2,rng),[])
        with self.assertRaises(ValueError):mapping.bridge(0,1,0,1,2,rng)

    def test_three_state_bridges_have_correct_expected_jump_counts(self):
        rng=np.random.default_rng(61); q=.4; k=3; t=1.5
        decay=math.exp(-k*q*t)
        for end in (0,1):
            p=(1+(k-1)*decay)/k if end==0 else (1-decay)/k
            derivative=-(k-1)*t*decay if end==0 else t*decay
            expected=(k-1)*q*t+q*derivative/p
            histories=[mapping.bridge(0,end,t,q,k,rng) for _ in range(6000)]
            self.assertAlmostEqual(np.mean([len(h) for h in histories]),expected,delta=.045)
            for history in histories:
                state=0;last=0
                for fraction,src,dst in history:
                    self.assertGreater(fraction,last);last=fraction
                    self.assertEqual(src,state);state=dst
                self.assertEqual(state,end)

    def test_zero_histories_and_endpoint_consistency(self):
        ns=nodes();ns[2]['observed_state']='A'
        # The model state space can include other observed tips in production.
        histories,diagnostics=mapping.sample_histories(ns,['A','B'],200,44)
        self.assertTrue(any(not h['jumps'] for h in histories))
        for h in histories:
            for tip in ns[1:]:
                state=h['root_state']
                for jump in [j for j in h['jumps'] if j['branch']==tip['id']]:
                    self.assertEqual(jump['from'],state);state=jump['to']
                self.assertEqual(state,tip['observed_state'])
        self.assertEqual(histories,mapping.sample_histories(ns,['A','B'],200,44)[0])

    def test_leap_year_roundtrip_and_tree_errors(self):
        for dt in ('2024-02-29T12:00:00Z','2025-01-01T00:00:00Z'):
            self.assertAlmostEqual(mapping.numeric_date(dt),mapping.numeric_date(mapping.calendar_date(mapping.numeric_date(dt))),places=9)
        bad=nodes();bad[1]['date']='2019-01-01'
        with self.assertRaises(ValueError):mapping.TraitTree(bad,['A','B'])
        bad=nodes();bad[1]['parent']='b';bad[2]['parent']='a';bad[1]['date']=bad[2]['date']
        with self.assertRaises(ValueError):mapping.TraitTree(bad,['A','B'])

    def test_movie_schema_accepts_generated_histories(self):
        from build_phylogeography_movie import validate
        histories,_=mapping.sample_histories(nodes(),['A','B'],30,3)
        movie=dict(schema='wings.phylogeography-movie.v1',title='Synthetic test',synthetic=True,
                   provenance=dict(method='Synthetic test',inference='synthetic',uncertainty='conditional-on-fixed-tree'),
                   locations=[dict(id='A',label='A',lat=35,lon=-85),dict(id='B',label='B',lat=38,lon=-80)],
                   segments=[dict(id='HA',nodes=nodes(),histories=histories)])
        validate(movie)


class SummaryTests(unittest.TestCase):
    def test_no_posterior_pooling_or_replacement_of_blocked_primary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);selected=root/'selection';inferred=root/'inference'
            ids=['HA/balanced/replicate_1','HA/available/replicate_1']
            selection.write_json(selected/'selection_summary.json',dict(
                config=dict(segments=['HA'],strategies=['balanced','available']),
                replicates=[dict(id=x) for x in ids]))
            for i,key in enumerate(ids):
                record=dict(id=key,segment='HA',strategy=key.split('/')[1],replicate=1,
                    study=5,references=10,status='blocked' if i==0 else 'complete',
                    reasons=['temporal_screen_failed'] if i==0 else [],
                    introductions={} if i==0 else {'<unsafe>':dict(mean=2,lower=0,upper=5)})
                if i:
                    from test_phylodynamics_comparison import fixture
                    movie, scoped = fixture()
                    record.update(focal_sample_ids=scoped['focal_sample_ids'],focal_mrca=scoped['focal_mrca'])
                    record['introductions']={'<unsafe>':dict(mean=1,lower=1,upper=1,zero_probability=0)}
                    for loc in movie['locations']:
                        if loc['id']=='B':loc['id']='<unsafe>'
                    for node in movie['segments'][0]['nodes']:
                        if node.get('observed_state')=='B':node['observed_state']='<unsafe>'
                    for history in movie['segments'][0]['histories']:
                        for jump in history['jumps']:
                            for field in ('from','to'):
                                if jump[field]=='B':jump[field]='<unsafe>'
                    selection.write_json(inferred/key/'movie.json',movie)
                selection.write_json(inferred/key/'result.json',record)
            result=summarize(selected,inferred,root)
            self.assertIsNone(result['phylogeography'])
            self.assertEqual(result['sensitivity'][0]['mean_range'],[1,1])
            self.assertEqual(result['sensitivity'][0]['completed_replicates'],1)
            self.assertNotIn('<unsafe>',(root/'sensitivity.html').read_text())
            self.assertIn('&lt;unsafe&gt;',(root/'sensitivity.html').read_text())


if __name__ == '__main__':unittest.main()
