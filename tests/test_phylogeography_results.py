#!/usr/bin/env python3
import copy
import csv
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_phylogeography_results as r
import geographic_rate_prior as gp
from phylodynamic_mapping import sample_histories
from phylodynamic_estimands import focal_branches,entry_count
KEY='HA/balanced/replicate_1'


def fixture(root):
    inf=root/'inference'/KEY;sel=root/'selection'/KEY;inf.mkdir(parents=True);sel.mkdir(parents=True)
    nodes=[dict(id='root',parent=None,date='2022-01-01'),dict(id='mrca',parent='root',date='2024-01-01'),
       dict(id='a',parent='mrca',date='2025-04-01',sample_id='WINGS_A',label='WINGS_A',observed_state='KY'),
       dict(id='b',parent='mrca',date='2025-10-01',sample_id='WINGS_B',label='WINGS_B',observed_state='KY'),
       dict(id='ref',parent='root',date='2026-01-01',observed_state='MI')]
    locations=[dict(id='KY',label='Kentucky',lat=37.5,lon=-85),dict(id='MI',label='Michigan',lat=44,lon=-85)]
    selection=dict(id=KEY,location_metadata=locations);r.write(sel/'selection.json',selection)
    with (sel/'tips.tsv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['id','date','location','sample_id'],delimiter='\t');w.writeheader()
        for n in nodes:
            if 'observed_state' in n:w.writerow(dict(id=n['id'],date=n['date'],location=n['observed_state'],sample_id=n.get('sample_id','')))
    (inf/'ml.treefile').write_text('((a:.1,b:.1):.1,ref:.2);');(inf/'alignment.fasta').write_text('>a\nACGT\n>b\nACGA\n>ref\nATGA\n')
    r.write(inf/'dated_nodes.json',nodes);temporal=dict(status='passed',observed=dict(r2=.4),tree_sha256=r.sha(inf/'ml.treefile'));r.write(inf/'temporal_diagnostics.json',temporal)
    hs,quad=sample_histories(nodes,['KY','MI'],600,42)
    branches,mrca=focal_branches(nodes,['a','b']);counts={s:dict(mean=float(np.mean([entry_count(h,s,branches) for h in hs]))) for s in ['KY','MI']}
    record=dict(id=KEY,status='complete',reasons=[],selection_sha256=r.sha(sel/'selection.json'),temporal_diagnostics=temporal,
       focal_sample_ids=['WINGS_A','WINGS_B'],focal_mrca=mrca,quadrature=quad,introductions=counts)
    movie=dict(schema='wings.phylogeography-movie.v1',provenance=dict(analysis=KEY,selection_sha256=r.sha(sel/'selection.json'),uncertainty='conditional-on-fixed-tree',inference='bayesian',prior={'shape':1,'rate':1}),locations=locations,segments=[dict(id='HA',nodes=nodes,histories=hs)])
    r.write(inf/'result.json',record);r.write(inf/'movie.json',movie)
    r.write(root/'selection/selection_summary.json',dict(replicates=[dict(id=KEY,status='ready')]))
    return nodes,hs,record


class SavedInputTests(unittest.TestCase):
    def test_saved_cohort_overrides_new_configuration_without_filtering_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            saved=[f'HA/{s}/replicate_{i}' for s in ('balanced','available') for i in (1,2,3)]
            configured=saved+[f'HA/diversity/replicate_{i}' for i in (1,2,3)]
            r.write(root/'selection/selection_summary.json',dict(replicates=[dict(id=k,status='blocked' if i==0 else 'ready') for i,k in enumerate(saved)]))
            c=r.config(dict(saved_inputs_only=True))
            self.assertEqual(r.analysis_ids(root,c,configured),saved)
            self.assertEqual(r.analysis_ids(root,r.config(),configured),configured)
            for key in configured:
                self.assertEqual(r.fast_rule_inputs(root,key,c),[])
            self.assertEqual(r.beast_rule_inputs(root,configured,c),[])

    def test_saved_inputs_have_no_upstream_edges_even_when_files_exist(self):
        c=r.config(dict(saved_inputs_only=True))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            self.assertEqual(r.fast_rule_inputs(root,KEY,c),[])
            r.write(r.beast_sources(root,KEY,c)[0],dict(status='passed'))
            self.assertEqual(r.beast_rule_inputs(root,[KEY],c),[])
            self.assertTrue(r.fast_rule_inputs(root,KEY,r.config()))

    def test_missing_saved_cohort_is_not_replaced_by_current_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=r.config(dict(saved_inputs_only=True))
            with self.assertRaisesRegex(ValueError,'Saved-input mode requires'):
                r.analysis_ids(tmp,c,[KEY])
            r.write(Path(tmp)/'selection/selection_summary.json',dict(replicates=[dict(id=KEY),dict(id=KEY)]))
            with self.assertRaisesRegex(ValueError,'duplicate'):
                r.analysis_ids(tmp,c,[KEY])

    def test_explicit_missing_analysis_stays_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            key='HA/diversity/replicate_2';c=r.config(dict(saved_inputs_only=True,analyses=[key]))
            self.assertEqual(r.analysis_ids(tmp,c,[KEY]),[key])
            out=r.build_fast(tmp,key,Path(tmp)/'out.json',c)
            self.assertEqual(out['status'],'blocked')
            self.assertNotIn('dataset',out)

    def test_saved_content_changes_are_tracked_without_producer_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);c=r.config(dict(saved_inputs_only=True))
            before=r.fast_rule_signature(root,KEY,c)
            path=r.fast_sources(root,KEY)[0];r.write(path,dict(status='complete'))
            after=r.fast_rule_signature(root,KEY,c)
            self.assertNotEqual(before,after)
            r.write(path,dict(status='blocked'))
            self.assertNotEqual(after,r.fast_rule_signature(root,KEY,c))
            before=r.beast_rule_signature(root,[KEY],c)
            r.write(r.beast_sources(root,KEY,c)[0],dict(status='passed'))
            self.assertNotEqual(before,r.beast_rule_signature(root,[KEY],c))


class PriorTests(unittest.TestCase):
    def test_gamma_and_lognormal_quadrature_against_prior_means(self):
        class Flat:
            k=4
            def prune(self,q):return np.zeros(len(q))
        for prior,mean in [(dict(family='gamma',parameter='pair_rate',shape=2.,rate=4.),.5),
          (dict(family='gamma',parameter='exit_rate',shape=2.,rate=4.),1/6),
          (dict(family='lognormal',parameter='pair_rate',median=.4,log_sd=.8),.4*math.exp(.8**2/2)),
          (dict(family='lognormal',parameter='exit_rate',median=.4,log_sd=.8),.4*math.exp(.8**2/2)/3)]:
            q,w,d=gp.integrate(Flat(),prior);self.assertAlmostEqual(float(w.sum()),1);self.assertAlmostEqual(float(w@q),mean,delta=mean*.002);self.assertLess(d['cdf_error'],.001)

    def test_total_exit_prior_stable_across_number_of_locations(self):
        class Flat:
            def __init__(self,k):self.k=k
            def prune(self,q):return np.zeros(len(q))
        values=[]
        for k in [2,5,10]:
            q,w,_=gp.integrate(Flat(k),dict(family='lognormal',parameter='exit_rate',median=1.,log_sd=.5));values.append(float(w@q)*(k-1))
        self.assertLess(max(values)-min(values),1e-6)

    def test_reject_invalid_priors(self):
        for prior in [dict(family='normal'),dict(family='lognormal',median=0,log_sd=1),dict(family='gamma',shape=1,rate=float('inf')),dict(family='gamma',shape=1,rate=1,parameter='unknown')]:
            with self.assertRaises(ValueError):gp.prior_config(prior)


class ResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);fixture(cls.root)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_default_fast_reuses_histories_and_scopes_ancestry(self):
        c=r.config();out=self.root/'results/fast_v1/fast'/KEY/'result.json';result=r.build_fast(self.root,KEY,out,c)
        self.assertEqual(result['status'],'passed',result['reasons']);d=result['dataset'];self.assertTrue(d['reused_histories']);self.assertEqual(len(d['draws']),600)
        self.assertEqual({n['id'] for n in d['nodes']},{'mrca','a','b'});self.assertIsNone(d['tmrca']['hpd95'])
        for draw in d['draws']:self.assertTrue(all(j['branch'] in {'a','b'} for j in draw['history']['jumps']))
        model=r.report(self.root,[KEY],self.root/'results/fast_v1',c)
        self.assertEqual(model['default_method'],'fast');self.assertIn('fast',model['analyses'][0]['methods']);self.assertNotIn('beast',model['analyses'][0]['methods'])

    def test_lognormal_remaps_instead_of_relabeling_source(self):
        c=r.config(dict(geographic_prior=dict(family='lognormal',parameter='exit_rate',median=.3,log_sd=.5)))
        result=r.build_fast(self.root,KEY,self.root/'lognormal.json',c)
        self.assertEqual(result['status'],'passed',result['reasons']);self.assertFalse(result['dataset']['reused_histories']);self.assertEqual(result['dataset']['prior']['family'],'lognormal')

    def test_precision_failure_withholds_dataset(self):
        c=r.config(dict(max_mean_mcse=.000001));result=r.build_fast(self.root,KEY,self.root/'precision-failure.json',c)
        self.assertEqual(result['status'],'blocked');self.assertNotIn('dataset',result)

    def test_source_changes_block_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root);path=root/'inference'/KEY/'movie.json';m=r.read(path);m['segments'][0]['nodes'][0]['date']='1900-01-01';r.write(path,m)
            result=r.build_fast(root,KEY,root/'out.json',r.config());self.assertEqual(result['status'],'blocked')

    def test_temporal_failure_is_not_bypassed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root);path=root/'inference'/KEY/'result.json';m=r.read(path);m.update(status='blocked',reasons=['weak temporal signal']);r.write(path,m)
            result=r.build_fast(root,KEY,root/'out.json',r.config());self.assertEqual(result['status'],'blocked');self.assertIn('weak temporal signal',result['reasons'][0])

    def test_requested_beast_never_falls_back(self):
        c=r.config(dict(method='beast'));out=self.root/'results/fast_v1/fast'/KEY/'result.json';r.build_fast(self.root,KEY,out,c)
        model=r.report(self.root,[KEY],self.root/'report-beast',c)
        self.assertEqual(model['default_method'],'beast');self.assertNotIn('beast',model['analyses'][0]['methods']);self.assertIn('beast',model['analyses'][0]['unavailable'])

    def test_checked_beast_publication_loads_and_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);nodes,hs,_=fixture(root);c=r.config();folder=r.beast_folder(root,KEY,c)
            states=['KY','MI'];draws=[]
            for chain,h in enumerate(hs[:2],1):
                ns,history,mrca=r.scope_history(nodes,h,['a','b'])
                draws.append(dict(chain=chain,state=1000,nodes=ns,history=history,focal_mrca=mrca))
            thresholds=dict(max_rhat=1.01,min_bulk_ess=400,min_tail_ess=400,min_chain_ess=100)
            diag={'ancestor':dict(status='passed',rhat=1.,bulk_ess=900,tail_ess=900,per_chain_bulk_ess=[450,450])}
            gate=dict(status='passed',diagnostics=diag,selected_tree_diagnostics=diag)
            r.write(folder/'gate/diagnostics.json',gate);r.write(folder/'gate/trees.json',dict(draws=draws))
            proof=dict(status='passed',settings=thresholds,diagnostics_sha256=r.sha(folder/'gate/diagnostics.json'),trees_sha256=r.sha(folder/'gate/trees.json'),source_fingerprint=r.fingerprints([root/'inference'/KEY/'result.json']))
            r.write(folder/'gate/verified.json',proof);r.write(folder/'mapping/mapping.json',dict(draws=draws))
            data=dict(schema='wings.posterior-movie.v1',status='passed',analysis=KEY,settings=thresholds,gate_sha256=r.sha(folder/'gate/verified.json'),locations=[dict(id='KY',label='Kentucky',lat=37.5,lon=-85),dict(id='MI',label='Michigan',lat=44,lon=-85)],draws=draws,focal_sample_ids=['WINGS_A','WINGS_B'],tmrca=dict(median='2024-01-01',hpd95=['2023-10-01','2024-03-01']),prior=dict(rate_prior_shape=1,rate_prior_rate=1),entries={state:dict(mean=0,interval95=[0,0],zero_probability={'estimate':1},constant_sample=True) for state in states})
            r.write(folder/'publication/movie.json',data)
            r.write(folder/'publication/diagnostics.json',dict(status='passed',gate_sha256=r.sha(folder/'gate/verified.json'),mapping_sha256=r.sha(folder/'mapping/mapping.json')))
            r.write(folder/'publication/publication.json',dict(status='passed',movie_sha256=r.sha(folder/'publication/movie.json'),diagnostics_sha256=r.sha(folder/'publication/diagnostics.json')))
            loaded=r.build_beast(root,KEY,c);self.assertEqual(loaded['method'],'beast');self.assertEqual(len(loaded['draws']),2)
            data['tmrca']['median']='1900-01-01';r.write(folder/'publication/movie.json',data)
            with self.assertRaisesRegex(ValueError,'publication changed'):r.build_beast(root,KEY,c)

    def test_missing_locations_and_broken_history_rejected(self):
        nodes=[dict(id='r',parent=None,date='2020-01-01'),dict(id='a',parent='r',date='2024-01-01',observed_state='KY'),dict(id='b',parent='r',date='2024-01-01',observed_state='MI')]
        with self.assertRaises(ValueError):r.history_states(nodes,dict(root_state='KY',jumps=[]),['KY','MI'])

    def test_no_loosening_precision_thresholds(self):
        for raw in [dict(max_mean_mcse=1),dict(histories=100),dict(method='auto'),dict(run_id='../unsafe')]:
            with self.assertRaises(ValueError):r.config(raw)


def main():
    destination=None
    if '--preflight-output' in sys.argv:
        i=sys.argv.index('--preflight-output');destination=Path(sys.argv[i+1]);del sys.argv[i:i+2];destination.unlink(missing_ok=True)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not result.wasSuccessful() or result.skipped:return 1
    if destination:r.write(destination,dict(status='passed',tests=result.testsRun,code_sha256=r.sha(r.__file__)))
    return 0
if __name__=='__main__':raise SystemExit(main())
