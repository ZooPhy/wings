#!/usr/bin/env python3
"""Numerical and fail-closed regressions. Real ArviZ is mandatory in preflight."""
import copy
import csv
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import phylodynamic_bayesian as b
import phylodynamic_posterior as p
HAS_ARVIZ=importlib.util.find_spec('arviz') is not None


def synthetic_run(root,n=1200):
    run=root/'long20m';inf=root/'inference';sel=root/'selection'
    for x in (run,inf,sel):x.mkdir(parents=True)
    dates={'study_a':'2025-04-01','study_b':'2025-10-01','reference':'2026-01-01'}
    nodes=[dict(id='root',parent=None,date='2022-01-01'),dict(id='ancestor',parent='root',date='2024-01-01'),
           dict(id='study_a',parent='ancestor',date=dates['study_a'],observed_state='KY',sample_id='WINGS_A'),
           dict(id='study_b',parent='ancestor',date=dates['study_b'],observed_state='KY',sample_id='WINGS_B'),
           dict(id='reference',parent='root',date=dates['reference'],observed_state='MI')]
    (inf/'alignment.fasta').write_text('>study_a\nACGT\n>study_b\nACGA\n>reference\nACGG\n')
    (inf/'ml.treefile').write_text('((study_a:.1,study_b:.1):.1,reference:.2);')
    p.write(inf/'dated_nodes.json',nodes)
    p.write(sel/'selection.json',dict(id='HA/balanced/replicate_1',config=dict(rate_prior_shape=1,rate_prior_rate=1),
      location_metadata=[dict(id='KY',label='Kentucky',lat=37.5,lon=-85),dict(id='MI',label='Michigan',lat=44,lon=-85)]))
    with (sel/'tips.tsv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['id','date','sample_id','accession','location'],delimiter='\t');w.writeheader()
        for k,v in dates.items():w.writerow(dict(id=k,date=v,sample_id={'study_a':'WINGS_A','study_b':'WINGS_B'}.get(k,''),accession='ref' if k=='reference' else '',location='MI' if k=='reference' else 'KY'))
    p.write(inf/'result.json',dict(id='HA/balanced/replicate_1',status='complete',focal_sample_ids=['WINGS_A','WINGS_B'],selection_sha256=p.sha(sel/'selection.json')))
    inp=b.load_inputs(inf,sel)
    c=b.configuration(dict(enabled=True,run_id='long20m',chain_length=n,log_every=1))
    hashes=[]
    for chain in (1,2):
        folder=run/f'chain_{chain}';folder.mkdir();rng=np.random.default_rng(42+chain)
        roots=2022+rng.normal(0,.07,n+1);anc=2024+rng.normal(0,.06,n+1)
        (folder/'input.xml').write_text('<beast/>')
        m=dict(schema='wings.bayesian-dating-chain.v1',analysis='HA/balanced/replicate_1',config=c,chain=chain,
          inputs=inp['input_sha256'],seed=chain,tip_dates=inp['dates'],focal_tip_ids=inp['focal'],
          focal_sample_ids=['WINGS_A','WINGS_B'],rooted_topology=b.starting_tree(inp),latest_tip=2026.,
          topology_audit=inp['topology_audit'],model='synthetic fixture',interval_scope='synthetic',xml_sha256=p.sha(folder/'input.xml'))
        p.write(folder/'manifest.json',m);hashes.append(p.sha(folder/'manifest.json'))
        with (folder/'chain.trees').open('w') as f:
            f.write('#NEXUS\nBegin trees;\nTranslate 1 study_a, 2 study_b, 3 reference;\n')
            for i in range(n+1):
                f.write(f'tree STATE_{i} = [&R] ((1:{inp["dates"]["study_a"]-anc[i]:.12f},2:{inp["dates"]["study_b"]-anc[i]:.12f}):{anc[i]-roots[i]:.12f},3:{2026-roots[i]:.12f});\n')
            f.write('End;\n')
        with (folder/'chain.log').open('w') as f:
            f.write('Sample posterior prior likelihood clockRate popSize kappa gammaShape rootHeight\n')
            for i in range(n+1):
                vals=[*rng.normal(size=3),*rng.lognormal(size=4),2026-roots[i]]
                f.write(str(i)+' '+' '.join(map(str,vals))+'\n')
        p.write(folder/'complete.json',dict(status='complete',manifest_sha256=p.sha(folder/'manifest.json'),output_sha256={k:p.sha(folder/k) for k in ('chain.log','chain.trees')}))
    p.write(run/'summary.json',dict(status='complete',prior_only=False,analysis='HA/balanced/replicate_1',config=c,input_sha256=inp['input_sha256'],chain_manifests=hashes))
    return run,inf,sel


def fake_diagnostics(arrays,c):
    return {k:dict(status='passed',bulk_ess=900,tail_ess=900,rhat=1.,per_chain_bulk_ess=[450,450]) for k in arrays},[]


class StructuralTests(unittest.TestCase):
    def test_no_threshold_relaxation(self):
        for kw in ({'max_rhat':1.02},{'min_bulk_ess':399},{'min_chain_ess':99},{'max_mean_mcse':1},{'trees_per_chain':399},{'run_id':'../bad'}):
            with self.assertRaises(ValueError):p.configuration(kw)

    def test_streaming_trees_translation_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'x';f.write_text('#NEXUS\nBegin trees;Translate 1 a,2 b;tree STATE_0 = [&R] (1:1,2:2);End;')
            rows=list(p.tree_records(f));self.assertEqual(rows[0][1]['children'][0]['name'],'a')
            f.write_text(f.read_text()+'tree STATE_1 = (1:1,2:2)')
            with self.assertRaisesRegex(ValueError,'Truncated'):list(p.tree_records(f))

    def test_scope_excludes_stem_reference_and_keeps_reentries(self):
        nodes=[dict(id='r',parent=None,date='2020-01-01'),dict(id='m',parent='r',date='2021-01-01'),
          dict(id='a',parent='m',date='2024-01-01',observed_state='KY'),dict(id='b',parent='m',date='2024-01-01',observed_state='KY'),
          dict(id='ref',parent='r',date='2024-01-01',observed_state='MI')]
        h=dict(root_state='MI',jumps=[dict(branch='m',date='2020-06-01',**{'from':'MI','to':'KY'}),
          dict(branch='a',date='2022-01-01',**{'from':'KY','to':'MI'}),dict(branch='a',date='2023-01-01',**{'from':'MI','to':'KY'})])
        scoped,history,m=p.scope_history(nodes,h,['a','b'])
        self.assertEqual(m,'m');self.assertEqual(history['root_state'],'KY');self.assertEqual(p.entry_count(history,'KY'),1)
        self.assertEqual({n['id'] for n in scoped},{'m','a','b'})
        bad=copy.deepcopy(h);bad['jumps'][2]['date']='2025-01-01'
        with self.assertRaisesRegex(ValueError,'outside'):p.scope_history(nodes,bad,['a','b'])

    def test_numerical_mapper_on_distinct_dated_trees(self):
        for year in (2020,2023):
            nodes=[dict(id='r',parent=None,date=f'{year}-01-01'),dict(id='a',parent='r',date='2024-01-01',observed_state='KY'),dict(id='b',parent='r',date='2025-01-01',observed_state='MI')]
            hs,diagnostic=p.sample_histories(nodes,['KY','MI'],12,year)
            self.assertEqual(len(hs),12);self.assertLessEqual(diagnostic['cdf_error'],.001)
            for h in hs:p.scope_history(nodes,h,['a','b'])

    def test_atomic_publication_withheld_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'publication';out.mkdir();(out/'movie.html').write_text('OLD MOVIE');(out/'movie.json').write_text('{}');(out/'publication.json').write_text('{}')
            with self.assertRaises(Exception):p.publish(Path(tmp)/'missing',Path(tmp)/'missing',out,p.configuration())
            self.assertFalse((out/'publication.json').exists());self.assertFalse((out/'movie.json').exists());self.assertIn('withheld',(out/'movie.html').read_text())

    def test_fingerprint_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'x';f.write_text('before');hashes=p.fingerprint([f]);f.write_text('after')
            with self.assertRaisesRegex(ValueError,'changed'):p.check_fingerprint(hashes)

    def test_gate_pipeline_structural_checks_and_all_node_monitoring(self):
        # This exercises provenance and streaming logic, not numerical convergence.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run,inf,sel=synthetic_run(root);out=root/'gate';c=p.configuration(dict(trees_per_chain=400))
            with patch.object(p,'versions',return_value={'test':'synthetic'}),patch.object(p,'monitored_diagnostics',side_effect=fake_diagnostics) as monitor,patch.object(p,'date_precision',return_value=({},[])):
                result=p.gate(run,inf,sel,out,c)
                self.assertEqual(result['status'],'passed')
                arrays=monitor.call_args_list[0].args[0]
                self.assertEqual(len([k for k in arrays if k.startswith('node_date:')]),2)
                self.assertEqual(len(arrays['wings_tmrca'][0]),1080)
                bundle=p.jread(out/'trees.json');self.assertEqual(len(bundle['draws']),800)
                self.assertEqual(len({(d['chain'],d['state']) for d in bundle['draws']}),800)
                p.checked_gate(out,c)
                (run/'chain_1/chain.log').write_text('changed')
                with self.assertRaises(ValueError):p.checked_gate(out,c)
                with self.assertRaises(ValueError):p.gate(run,inf,sel,out,c)
                self.assertFalse((out/'verified.json').exists());self.assertEqual(p.jread(out/'diagnostics.json')['status'],'blocked')

    def test_ess_failure_removes_success_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run,inf,sel=synthetic_run(root);out=root/'gate';out.mkdir();p.write(out/'verified.json',{'status':'passed'})
            with patch.object(p,'versions',return_value={}),patch.object(p,'monitored_diagnostics',return_value=({},['clockRate: convergence/ESS threshold failed'])),patch.object(p,'date_precision',return_value=({},[])):
                with self.assertRaisesRegex(ValueError,'gate failed'):p.gate(run,inf,sel,out,p.configuration(dict(trees_per_chain=400)))
            self.assertFalse((out/'verified.json').exists());self.assertFalse((out/'trees.json').exists())

    def test_end_to_end_publication_and_tampered_date_withholding(self):
        # Convergence is stubbed here; the numerical suite tests ArviZ separately.
        def history(nodes,states,count,seed,shape,rate):
            root=next(n for n in nodes if n['parent'] is None)
            ancestor=next(n for n in nodes if n['parent']==root['id'] and 'observed_state' not in n)
            t=(p.numeric_date(root['date'])+p.numeric_date(ancestor['date']))/2
            return [dict(root_state='MI',jumps=[dict(branch=ancestor['id'],date=p.calendar_date(t),**{'from':'MI','to':'KY'})])],dict(cdf_error=0.,rate_draw_mean=1.)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run,inf,sel=synthetic_run(root);out=root/'gate';c=p.configuration(dict(trees_per_chain=400))
            with patch.object(p,'versions',return_value={'test':'synthetic'}),patch.object(p,'monitored_diagnostics',side_effect=fake_diagnostics),patch.object(p,'date_precision',return_value=({},[])):
                p.gate(run,inf,sel,out,c)
                with patch.object(p,'sample_histories',side_effect=history):mapped=p.reconstruct(out,root/'mapping',c)
                self.assertEqual(len(mapped['draws']),800)
                self.assertTrue(all(d['history']['jumps']==[] and d['history']['root_state']=='KY' for d in mapped['draws']))
                report=dict(status='passed',reasons=[],entries={l['id']:dict(mean=0,interval95=[0,0],mean_mcse=None,constant_sample=True) for l in mapped['locations']})
                with patch.object(p,'mapping_diagnostics',return_value=report):
                    p.publish(out,root/'mapping',root/'publication',c)
                    self.assertTrue((root/'publication/publication.json').exists())
                    self.assertIn('posterior-data',(root/'publication/movie.html').read_text())
                    mapped['draws'][0]['nodes'][0]['date']='1900-01-01'
                    p.write(root/'mapping/mapping.json',mapped)
                    with self.assertRaisesRegex(ValueError,'dates or ancestry'):p.publish(out,root/'mapping',root/'publication',c)
                    self.assertFalse((root/'publication/publication.json').exists())
                    self.assertIn('withheld',(root/'publication/movie.html').read_text())

    def test_missing_diagnostic_library_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(p,'versions',side_effect=ImportError('ArviZ unavailable')):
                with self.assertRaises(ImportError):p.gate(tmp,tmp,tmp,Path(tmp)/'gate',p.configuration())
            self.assertEqual(p.jread(Path(tmp)/'gate/diagnostics.json')['status'],'blocked')


@unittest.skipUnless(HAS_ARVIZ,'ArviZ required; mandatory in actual workflow preflight')
class NumericalTests(unittest.TestCase):
    def test_iid_passes_and_shifted_chains_fail(self):
        rng=np.random.default_rng(82);a=rng.normal(size=(2,4000));c=p.configuration()
        d,reasons=p.monitored_diagnostics({'iid':a},c);self.assertFalse(reasons);self.assertGreater(d['iid']['bulk_ess'],400)
        shifted=a.copy();shifted[1]+=2
        d,reasons=p.monitored_diagnostics({'shifted':shifted},c);self.assertTrue(reasons);self.assertGreater(d['shifted']['rhat'],1.01)
        d,reasons=p.monitored_diagnostics({'constant':np.ones((2,4000))},c);self.assertTrue(reasons)

    def test_autocorrelation_fails_and_date_precision(self):
        rng=np.random.default_rng(18);a=np.zeros((2,4000))
        for i in range(1,4000):a[:,i]=.999*a[:,i-1]+rng.normal(size=2)
        _,reasons=p.monitored_diagnostics({'sticky':a},p.configuration());self.assertTrue(reasons)
        good=2024+rng.normal(0,.06,(2,4000));r=p.interval_precision(good,43)
        self.assertLess(max(r['endpoint_mcse_days']),14)
        self.assertLess(p.mcse_mean(good)*365.25,7)

    def test_zero_probability_is_bound_not_certainty(self):
        result=p.probability_precision(np.zeros((2,1000)),400)
        self.assertTrue(result['boundary']);self.assertGreater(result['bound95'],0);self.assertLess(result['bound95'],.025)

    def test_real_gate_and_selected_tree_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run,inf,sel=synthetic_run(root,n=4000)
            result=p.gate(run,inf,sel,root/'gate',p.configuration(dict(trees_per_chain=1000)))
            self.assertEqual(result['status'],'passed')
            self.assertTrue(result['selected_tree_diagnostics'])
            self.assertTrue(result['date_precision'])

    def test_discrete_mapping_counts_include_zero_draws(self):
        rng=np.random.default_rng(42);draws=[]
        for chain in (1,2):
            for state in range(1000):
                n=int(rng.poisson(2));draws.append(dict(chain=chain,state=state,rate=float(rng.gamma(2)),history=dict(jumps=[{'to':'KY'}]*n)))
        data=dict(draws=draws,locations=[dict(id='KY'),dict(id='MI')]);c=p.configuration()
        gate=dict(thresholds=c,selected_tree_diagnostics={'node':dict(bulk_ess=500)})
        r=p.mapping_diagnostics(data,gate,c)
        self.assertEqual(r['status'],'passed',r['reasons']);self.assertGreater(r['entries']['KY']['zero_probability']['estimate'],0)
        self.assertEqual(r['entries']['MI']['zero_probability']['estimate'],1)
        self.assertTrue(r['entries']['MI']['zero_probability']['boundary'])


def main():
    destination=None
    if '--preflight-output' in sys.argv:
        i=sys.argv.index('--preflight-output');destination=Path(sys.argv[i+1]);del sys.argv[i:i+2]
    if destination:destination.unlink(missing_ok=True)
    if os.environ.get('WINGS_REQUIRE_POSTERIOR_DIAGNOSTICS')=='1' and not HAS_ARVIZ:
        raise SystemExit('Preflight blocked: install the pinned ArviZ diagnostic environment; numerical checks cannot be skipped.')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not result.wasSuccessful():return 1
    if destination:
        if result.skipped:raise SystemExit('Preflight blocked: a required diagnostic test was skipped')
        p.write(destination,dict(status='passed',tests=result.testsRun,software=p.versions(),code_sha256=p.sha(p.__file__)))
    return 0

if __name__=='__main__':raise SystemExit(main())
