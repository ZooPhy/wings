import copy
import csv
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import phylodynamic_bayesian as b


def runtime_files(jar):
    package=jar.parent/'packages';package.mkdir(exist_ok=True)
    (package/'BEAST.base.jar').write_bytes(b'fixture only')
    (package/'BEAST.base.version.xml').write_text('<package name="BEAST.base" version="2.7.7"/>')


def inputs(root):
    inf=root/'inference';sel=root/'selection';inf.mkdir();sel.mkdir()
    nodes=[dict(id='root',parent=None,date='2020-01-01'),dict(id='mrca',parent='root',date='2022-01-01'),
        dict(id='a',parent='mrca',date='2024-01-01',sample_id='S1'),dict(id='b',parent='mrca',date='2025-01-01',sample_id='S2'),dict(id='ref',parent='root',date='2023-01-01')]
    record=dict(id='HA/balanced/replicate_1',status='complete',focal_sample_ids=['S1','S2'],focal_mrca='mrca')
    b.write(inf/'result.json',record);b.write(inf/'dated_nodes.json',nodes)
    (inf/'alignment.fasta').write_text('>a\nACGTACGTACGTACGT\n>b\nACGTACGTACGTACGA\n>ref\nACGTACGTACGAACGA\n')
    (sel/'tips.tsv').write_text('id\tdate\tsample_id\tsource\na\t2024-01-01\tS1\tstudy\nb\t2025-01-01\tS2\tstudy\nref\t2023-01-01\t\treference\n')
    return inf,sel



def polytomy_inputs(root):
    inf,sel=inputs(root)
    nodes=json.loads((inf/'dated_nodes.json').read_text())
    nodes.append(dict(id='c',parent='mrca',date='2024-06-01'))
    b.write(inf/'dated_nodes.json',nodes)
    with (inf/'alignment.fasta').open('a') as f:f.write('>c\nACGTACGTACGTACGG\n')
    with (sel/'tips.tsv').open('a') as f:f.write('c\t2024-06-01\t\treference\n')
    (inf/'ml.treefile').write_text('((a:1,b:1):0,c:1,ref:2);\n')
    return inf,sel


def complete_fixture(root,c,chain=1):
    base=root/f'input{chain}';base.mkdir();inf,sel=inputs(base);inp=b.load_inputs(inf,sel)
    folder=root/f'chain_{chain}';folder.mkdir()
    m=dict(schema='wings.bayesian-dating-chain.v1',analysis=inp['record']['id'],config=c,chain=chain,seed=c['seed']+chain*1009,
      inputs=inp['input_sha256'],focal_sample_ids=['S1','S2'],focal_tip_ids=['a','b'],tip_dates=inp['dates'],rooted_topology=b.starting_tree(inp),latest_tip=2025.)
    b.write(folder/'manifest.json',m)
    trace=['Sample\tposterior\tlikelihood\tprior\tclockRate\tpopSize\tkappa\tgammaShape\trootHeight']
    trees=['#NEXUS','Begin trees;','Translate 1 a, 2 b, 3 ref;'];rng=random.Random(100+chain)
    for state in range(0,c['chain_length']+1,c['log_every']):
        root_date=2020+rng.uniform(-.2,.2);mrca=2022+rng.uniform(-.2,.2);rh=2025-root_date
        trace.append(f'{state}\t{-100+rng.random()}\t{-95+rng.random()}\t{-5+rng.random()}\t{.003+rng.random()*.001}\t{1+rng.random()}\t{2+rng.random()}\t{1+rng.random()}\t{rh}')
        trees.append(f'tree STATE_{state} = [&R] ((1:{2024-mrca:.15g},2:{2025-mrca:.15g}):{mrca-root_date:.15g},3:{2023-root_date:.15g});')
    trees.append('End;')
    if c['prior_only']:
        trace=['\t'.join(line.split('\t')[:2]+line.split('\t')[3:]) for line in trace]
    (folder/'chain.log').write_text('\n'.join(trace)+'\n');(folder/'chain.trees').write_text('\n'.join(trees)+'\n')
    b.write(folder/'complete.json',dict(status='complete',manifest_sha256=b.digest(folder/'manifest.json'),output_sha256={k:b.digest(folder/k) for k in ('chain.log','chain.trees')}))
    return folder

class BayesianTests(unittest.TestCase):
    def test_conda_launcher_uses_native_java_and_inventory_jar(self):
        with tempfile.TemporaryDirectory(prefix='wings env with spaces ') as t:
            root=Path(t);(root/'conda-meta').mkdir();(root/'bin').mkdir()
            jar=root/'share/beast2-2.7.7/lib/launcher.jar';jar.parent.mkdir(parents=True);jar.write_bytes(b'fixture only');runtime_files(jar)
            java=root/'bin/java';java.write_text('#!/bin/sh\nprintf "native java fixture\\n"\n');java.chmod(0o755)
            b.write(root/'conda-meta/beast2-2.7.7-0.json',dict(name='beast2',version='2.7.7',files=[str(jar.relative_to(root))]))
            # macOS /var is an alias of /private/var. Exercise aliases on every OS.
            alias=root/'prefix alias';alias.symlink_to(root.resolve(),target_is_directory=True)
            for prefix in (root,alias):
                with self.subTest(prefix=str(prefix)):
                    cmd=b.resolve_beast_command(['beast'],prefix)
                    self.assertEqual(cmd,b.headless_beast_command(java,jar))
                    self.assertTrue(cmd[-1].endswith('WingsBeast.java'))
                    self.assertIn('BEAST.base.jar',cmd[-2])
                    self.assertNotIn('BEAST.app.jar',cmd[-2])
                    b.logged_beast(cmd+['-version'],prefix,'probe.log')
            self.assertIn('native java fixture',(root/'probe.log').read_text())
            self.assertEqual(b.resolve_beast_command(['custom-beast','-extra'],root),['custom-beast','-extra'])
            jar.unlink()
            with self.assertRaisesRegex(ValueError,'Expected one launcher.jar'):b.resolve_beast_command(['beast'],root)

    def test_openjdk_inventory_supports_nested_layouts_and_ignores_other_java(self):
        for relative in ('lib/jvm/bin/java','lib/jvm/Contents/Home/bin/java','Library/Java/JavaVirtualMachines/openjdk.jdk/Contents/Home/bin/java'):
            with self.subTest(layout=relative),tempfile.TemporaryDirectory(prefix='wings java ') as t:
                root=Path(t);(root/'conda-meta').mkdir();(root/'bin').mkdir()
                # A broken unrelated launcher must not mask the package-owned Java.
                (root/'bin/java').write_text('not the OpenJDK executable')
                jar=root/'lib/launcher.jar';jar.parent.mkdir(exist_ok=True);jar.write_bytes(b'fixture');runtime_files(jar)
                java=root/relative;java.parent.mkdir(parents=True,exist_ok=True)
                java.write_text('#!/bin/sh\nprintf "nested java fixture\\n"\n');java.chmod(0o755)
                b.write(root/'conda-meta/beast2-2.7.7-0.json',dict(name='beast2',version='2.7.7',files=['lib/launcher.jar']))
                b.write(root/'conda-meta/openjdk-17.0.1-0.json',dict(name='openjdk',version='17.0.1',files=[relative]))
                alias=root/'prefix alias';alias.symlink_to(root.resolve(),target_is_directory=True)
                cmd=b.resolve_beast_command(['beast'],alias)
                self.assertEqual(cmd[0],str(java.resolve()))
                b.logged_beast(cmd+['-version'],alias,'probe.log')
                self.assertIn('nested java fixture',(root/'probe.log').read_text())
                # Package inventories may list both a binary and its bin/java alias.
                (root/'bin/java').unlink();(root/'bin/java').symlink_to(java.resolve())
                b.write(root/'conda-meta/openjdk-17.0.1-0.json',dict(name='openjdk',version='17.0.1',
                    paths_data={'paths':[{'_path':relative},{'_path':'bin/java'}]}))
                self.assertEqual(b.resolve_beast_command(['beast'],alias),cmd)
                java.chmod(0o644)
                with self.assertRaisesRegex(ValueError,'Native Java discovery'):b.resolve_beast_command(['beast'],alias)

    def test_launcher_rejects_wrong_package_and_missing_java(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'conda-meta').mkdir()
            record=root/'conda-meta/beast2-2.7.7-0.json'
            b.write(record,dict(name='beast2',version='2.6.3',files=[]))
            with self.assertRaisesRegex(ValueError,'2.7.7'):b.resolve_beast_command(['beast'],root)
            jar=root/'lib/launcher.jar';jar.parent.mkdir();jar.write_bytes(b'fixture only');runtime_files(jar)
            b.write(record,dict(name='beast2',version='2.7.7',files=['lib/launcher.jar']))
            with self.assertRaisesRegex(ValueError,'Native Java'):b.resolve_beast_command(['beast'],root)

    def test_headless_launcher_requires_core_jar_and_version_file(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);jar=root/'launcher.jar';jar.write_bytes(b'fixture')
            runtime_files(jar)
            version=root/'packages/BEAST.base.version.xml';version.unlink()
            with self.assertRaisesRegex(ValueError,'Missing headless BEAST runtime file'):
                b.headless_beast_command('/usr/bin/java',jar)

    def test_launcher_failure_exposes_stderr_and_preserves_log(self):
        with tempfile.TemporaryDirectory() as t:
            command=[sys.executable,'-c',"import sys;print('synthetic launch failure',file=sys.stderr);sys.exit(126)"]
            with self.assertRaisesRegex(ValueError,'(?s)exit 126.*synthetic launch failure'):
                b.logged_beast(command,Path(t),'version.log')
            self.assertIn('synthetic launch failure',(Path(t)/'version.log').read_text())

    def test_existing_ml_refinement_preserves_all_dated_clades_root_and_tips(self):
        with tempfile.TemporaryDirectory() as t:
            inf,sel=polytomy_inputs(Path(t));original=(inf/'dated_nodes.json').read_bytes()
            x=b.load_inputs(inf,sel)
            self.assertEqual(len(x['nodes']),7)
            self.assertEqual(x['topology_audit']['restored_nodes'],1)
            self.assertEqual(x['topology_audit']['dated_multifurcations'],1)
            self.assertEqual(x['input_sha256']['ml.treefile'],b.digest(inf/'ml.treefile'))
            self.assertEqual(x['nodes']['root']['date'],'2020-01-01')
            self.assertEqual(x['nodes']['mrca']['date'],'2022-01-01')
            self.assertEqual((inf/'dated_nodes.json').read_bytes(),original)
            tree=b.parse_newick(b.starting_tree(x))
            _,_,clades=b.tree_stats(tree,x['dates'],x['focal'])
            self.assertIn(frozenset(['a','b']),clades)
            self.assertIn(frozenset(['a','b','c']),clades)
            self.assertEqual(x['nodes']['mrca']['parent'],'root')
            # A binary display root subdividing an edge must give the same clades.
            (inf/'ml.treefile').write_text('(((a:1,b:1):0,c:1):1,ref:1);')
            y=b.load_inputs(inf,sel)
            self.assertEqual(clades,b.tree_stats(b.parse_newick(b.starting_tree(y)),y['dates'],y['focal'])[2])

    def test_ml_recovery_rejects_missing_mismatched_or_unresolved_sources(self):
        for invalid in (None,'((a:1,b:1):1,wrong:1,ref:1);','(a:1,b:1,c:1,ref:1);'):
            with self.subTest(source=invalid),tempfile.TemporaryDirectory() as t:
                inf,sel=polytomy_inputs(Path(t))
                if invalid is None:(inf/'ml.treefile').unlink()
                else:(inf/'ml.treefile').write_text(invalid)
                with self.assertRaises(ValueError):b.load_inputs(inf,sel)

    def test_ml_recovery_rejects_root_split_and_retained_clade_conflicts(self):
        with tempfile.TemporaryDirectory() as t:
            inf,sel=polytomy_inputs(Path(t))
            nodes=json.loads((inf/'dated_nodes.json').read_text())
            # Retain an a,c clade; the supplied ML refinement instead groups a,b.
            nodes.append(dict(id='ac',parent='mrca',date='2023-01-01'))
            nodes.append(dict(id='d',parent='mrca',date='2024-01-01'))
            for node in nodes:
                if node['id'] in ('a','c'):node['parent']='ac'
            (inf/'ml.treefile').write_text('(((a:1,b:1):1,c:1):1,d:1,ref:1);')
            with self.assertRaisesRegex(ValueError,'conflicts with a retained dated clade'):
                b.dating_topology(nodes,inf/'ml.treefile')
            # Root grouping a,c,d against b,ref is absent from this ML tree.
            nodes=[dict(id='r',parent=None,date='2020-01-01'),
                   dict(id='p',parent='r',date='2021-01-01'),dict(id='q',parent='r',date='2021-01-01')]+[
                dict(id=k,parent='p' if k in ('a','c','d') else 'q',date='2024-01-01') for k in ('a','b','c','d','ref')]
            with self.assertRaisesRegex(ValueError,'root split'):
                b.dating_topology(nodes,inf/'ml.treefile')

    def test_unresolved_dated_root_is_not_arbitrarily_placed(self):
        with tempfile.TemporaryDirectory() as t:
            inf,sel=polytomy_inputs(Path(t));nodes=json.loads((inf/'dated_nodes.json').read_text())
            for n in nodes:
                if n['id']=='c':n['parent']='root'
            with self.assertRaisesRegex(ValueError,'dated root'):
                b.dating_topology(nodes,inf/'ml.treefile')

    def test_config_is_opt_in_and_strict(self):
        self.assertFalse(b.configuration()['enabled'])
        for bad in [dict(chains=1),dict(burnin=.8),dict(run_id='../x'),dict(analyses=['../x']),dict(chain_length=101),dict(max_rhat=2),dict(beast_command='beast'),dict(x=1)]:
            with self.assertRaises(ValueError):b.configuration(bad)

    def test_calendar_leap_year_and_hpd(self):
        for d in ['2024-02-29','2025-06-01','2026-01-01']:
            self.assertLess(abs(b.numeric_date(b.calendar(b.numeric_date(d)))-b.numeric_date(d)),1e-7)
        self.assertEqual(b.hpd(list(range(95))+[1000,2000,3000,4000,5000]),[0,94])
        self.assertEqual(b.hpd([5]*100),[5,5])
        with self.assertRaises(ValueError):b.hpd([float('nan')])

    def test_fixed_topology_xml_has_variable_heights_and_proper_priors(self):
        with tempfile.TemporaryDirectory() as t:
            inf,sel=inputs(Path(t));inp=b.load_inputs(inf,sel);c=b.configuration()
            root=ET.fromstring(b.xml_model(inp,c,1));ops=root.findall('.//operator')
            self.assertTrue(any(o.get('id')=='internalHeights' for o in ops))
            self.assertTrue(any(o.get('rootOnly')=='true' for o in ops))
            self.assertFalse(any(o.get('spec','').split('.')[-1] not in ('ScaleOperator','Uniform','DeltaExchangeOperator') for o in ops))
            self.assertFalse(root.findall('.//*[@spec="MRCAPrior"]'))
            self.assertEqual(len(root.findall('.//sequence')),3)
            self.assertTrue(all(n.get('name')=='stateNode' for n in root.find('.//state')))
            self.assertEqual(root.find('.//branchRateModel').get('clock.rate'),'@clockRate')
            prior=ET.fromstring(b.xml_model(inp,dict(c,prior_only=True),1))
            self.assertFalse(prior.findall(".//logger/log[@idref='likelihood']"))
            self.assertEqual(root.find('.//trait').get('traitname'),'date-forward')
            self.assertNotEqual(root.find('.//tree').get('newick'),ET.fromstring(b.xml_model(inp,c,2)).find('.//tree').get('newick'))
            self.assertEqual(b.tree_stats(b.parse_newick(root.find('.//tree').get('newick')),inp['dates'],inp['focal'])[2],b.tree_stats(b.parse_newick(b.starting_tree(inp)),inp['dates'],inp['focal'])[2])

    def test_input_mismatch_and_nonbinary_tree_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            inf,sel=inputs(Path(t));(inf/'alignment.fasta').write_text('>a\nAC\n>b\nAG\n>wrong\nAT\n')
            with self.assertRaises(ValueError):b.load_inputs(inf,sel)
        with self.assertRaises(ValueError):b.rooted_nodes([dict(id='r',parent=None,date='2020-01-01'),dict(id='a',parent='r',date='2021-01-01')])

    def test_tip_dates_and_mrca_not_whole_root(self):
        tree=b.parse_newick('((a:2,b:3):2,ref:3);')
        d,r,_=b.tree_stats(tree,dict(a=2024.,b=2025.,ref=2023.),['a','b'])
        self.assertEqual((d,r),(2022.,2020.))
        # The WINGS taxon set need not be an exclusive clade.
        d,r,_=b.tree_stats(tree,dict(a=2024.,b=2025.,ref=2023.),['a','ref'])
        self.assertEqual(d,r)
        with self.assertRaises(ValueError):b.tree_stats(tree,dict(a=2024.,b=2024.,ref=2023.),['a','b'])

    def test_logs_require_complete_matching_states_and_fixed_topology(self):
        c=b.configuration(dict(chain_length=1000,log_every=10))
        with tempfile.TemporaryDirectory() as t:
            p=complete_fixture(Path(t),c);m=json.loads((p/'manifest.json').read_text())
            values=b.sampled_dates(p/'chain.trees',m,c);self.assertEqual(len(values),101)
            (p/'chain.trees').write_text((p/'chain.trees').read_text().replace('STATE_1000','STATE_999'))
            with self.assertRaises(ValueError):b.sampled_dates(p/'chain.trees',m,c)
            text=(p/'chain.log').read_text();(p/'chain.log').write_text(text.rsplit('\n',2)[0]+'\n')
            with self.assertRaises(ValueError):b.read_trace(p/'chain.log',c)

    def test_changed_rooted_topology_is_detected(self):
        c=b.configuration(dict(chain_length=1000,log_every=10))
        with tempfile.TemporaryDirectory() as t:
            folder=complete_fixture(Path(t),c);m=json.loads((folder/'manifest.json').read_text())
            text=(folder/'chain.trees').read_text()
            import re
            text=re.sub(r'(tree STATE_0 = )[^;]+;',r'\1[&R] ((1:2,3:1):2,2:5);',text)
            (folder/'chain.trees').write_text(text)
            with self.assertRaisesRegex(ValueError,'Topology changed'):b.sampled_dates(folder/'chain.trees',m,c)

    def test_summary_withholds_interval_when_diagnostics_fail(self):
        c=b.configuration(dict(chain_length=1000,log_every=10))
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);chains=[complete_fixture(root,c,n) for n in (1,2)]
            with patch.object(b,'diagnostics',return_value=({'wings_tmrca':{'status':'failed'}},['insufficient ESS'])):
                r=b.summarize(chains,root/'report',c)
            self.assertEqual(r['status'],'not_converged');self.assertIsNone(r['tmrca'])
            self.assertIn('Withheld',(root/'report/tmrca.html').read_text())

    def test_summary_converts_conditional_hpd_and_preserves_prior_only_label(self):
        for prior in (False,True):
            c=b.configuration(dict(chain_length=1000,log_every=10,prior_only=prior))
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);chains=[complete_fixture(root,c,n) for n in (1,2)]
                with patch.object(b,'diagnostics',return_value=({},[])):
                    r=b.summarize(chains,root/'report',c)
                self.assertEqual(r['status'],'prior_only' if prior else 'complete')
                self.assertEqual(r['retained_per_chain'],[90,90]);self.assertTrue(2021<r['tmrca']['median_decimal_year']<2023)
                self.assertTrue(r['root_date']['hpd95_decimal_year'][1]<r['tmrca']['hpd95_decimal_year'][0])

    def test_tampering_and_cross_replicate_pooling_blocked(self):
        c=b.configuration(dict(chain_length=1000,log_every=10))
        for change in ('output','replicate','seed'):
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);chains=[complete_fixture(root,c,n) for n in (1,2)]
                if change=='output':(chains[1]/'chain.log').write_text('bad')
                else:
                    m=json.loads((chains[1]/'manifest.json').read_text())
                    if change=='replicate':m['analysis']='HA/available/replicate_1'
                    else:m['seed']=json.loads((chains[0]/'manifest.json').read_text())['seed']
                    b.write(chains[1]/'manifest.json',m);co=json.loads((chains[1]/'complete.json').read_text());co['manifest_sha256']=b.digest(chains[1]/'manifest.json');b.write(chains[1]/'complete.json',co)
                r=b.summarize(chains,root/'report',c);self.assertEqual(r['status'],'blocked');self.assertIsNone(r['tmrca'])

    @unittest.skipUnless(importlib.util.find_spec('arviz'),'ArviZ not installed; runs in dedicated dating environment / CI')
    def test_rank_diagnostics_accept_independent_and_reject_shifted_or_stuck(self):
        import numpy as np
        rng=np.random.default_rng(2244);a=rng.normal(size=(2,4000));c=b.configuration()
        self.assertFalse(b.diagnostics({'tmrca':a},c)[1])
        shifted=a.copy();shifted[1]+=2;self.assertTrue(b.diagnostics({'tmrca':shifted},c)[1])
        self.assertTrue(b.diagnostics({'tmrca':np.ones((2,4000))},c)[1])

    @unittest.skipUnless(os.environ.get('WINGS_TEST_BAYESIAN_TOOLS')=='1','BEAST 2.7.7 integration is opt-in')
    def test_real_beast_runs_two_tiny_chains_without_topology_changes(self):
        c=b.configuration(dict(chain_length=1000,log_every=10,beast_command=json.loads(os.environ.get('WINGS_BAYESIAN_COMMAND','["beast"]'))))
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);inf,sel=polytomy_inputs(root)
            probe=root/'validation_only'
            self.assertEqual(b.run_chain(inf,sel,probe,c,1,validate_only=True)['status'],'validated')
            self.assertFalse((probe/'chain.log').exists())
            self.assertFalse((probe/'chain.trees').exists())
            (probe/'invalid.xml').write_text('<beast version="2.7"><run spec="NotARealClass"/></beast>')
            with self.assertRaisesRegex(ValueError,'BEAST failed'):
                b.logged_beast(b.resolve_beast_command(c['beast_command'])+['-java','-validate','invalid.xml'],probe,'invalid.log')
            for n in (1,2):
                p=root/f'chain_{n}';r=b.run_chain(inf,sel,p,c,n);self.assertEqual(r['status'],'complete')
                m=json.loads((p/'manifest.json').read_text());self.assertEqual(len(b.sampled_dates(p/'chain.trees',m,c)),101)
                _,trace=b.read_trace(p/'chain.log',c)
                self.assertGreater(len(set(trace['rootHeight'])),1)
                self.assertIn('uses BeerLikelihoodCore',(p/'tools.log').read_text())
            self.assertEqual(b.run_chain(inf,sel,root/'prior_only',dict(c,prior_only=True),1)['status'],'complete')
            r=b.summarize([root/'chain_1',root/'chain_2'],root/'report',c)
            self.assertIn(r['status'],('not_converged','complete'))

if __name__=='__main__':unittest.main()
