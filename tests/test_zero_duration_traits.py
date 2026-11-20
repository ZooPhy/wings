"""Zero-time conflicts and fail-closed report propagation.

Scientific executables and unavailable rendering helpers are isolated in the
inference/report tests; trait-tree likelihood calculations use real NumPy/SciPy.
"""
import copy
from contextlib import contextmanager
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'

@contextmanager
def module_overrides(replacements):
    """Restore only substituted modules, preserving newly imported extensions.

    patch.dict(sys.modules, ...) restores the entire module dictionary and can
    evict lazy NumPy/SciPy imports, which may not support a second initialization.
    """
    absent = object()
    originals = {name: sys.modules.get(name, absent) for name in replacements}
    sys.modules.update(replacements)
    try:
        yield
    finally:
        for name, original in originals.items():
            if original is absent:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def load(name, filename, deps=None):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    with module_overrides(deps or {}):
        spec.loader.exec_module(module)
    return module

mapping = load('zero_time_mapping', 'phylodynamic_mapping.py')
estimands = load('zero_time_estimands', 'phylodynamic_estimands.py')

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))

selection_helper = types.SimpleNamespace(write_json=write, digest=lambda p: 'hash', read_tsv=lambda p: [])
base_deps = {'phylodynamic_mapping': mapping, 'phylodynamic_selection': selection_helper,
             'phylodynamic_estimands': estimands}
inference = load('zero_time_inference', 'phylodynamic_inference.py', base_deps)
comparison = types.SimpleNamespace(scoped_movie=Mock(), write_comparison=Mock())
summary = load('zero_time_summary', 'phylodynamic_summary.py', dict(base_deps, build_phylodynamic_comparison=comparison))
results = load('zero_time_results', 'build_phylogeography_results.py', dict(base_deps,
    geographic_rate_prior=types.SimpleNamespace(prior_config=Mock(), histories=Mock()),
    phylodynamic_posterior=types.SimpleNamespace(scope_history=Mock())))


def tree(zero=True, same=False):
    return [dict(id='root', parent=None, date='2024-04-29T00:00:00.000Z'),
            dict(id='a', parent='root', date='2024-04-29T00:00:00.000Z', observed_state='WY'),
            dict(id='b', parent='root', date='2024-04-29T00:00:00.000Z' if zero else '2025-04-29T00:00:00.000Z',
                 observed_state='WY' if same else 'KS')]


class TraitTests(unittest.TestCase):
    def test_scipy_modules_remain_cached_after_source_imports(self):
        self.assertIn('scipy', sys.modules)
        self.assertIn('scipy.special', sys.modules)
        self.assertIs(mapping.logsumexp, sys.modules['scipy.special'].logsumexp)
        self.assertAlmostEqual(float(mapping.logsumexp([0., 0.])), math.log(2))

    def test_module_overrides_restore_only_named_entries_even_on_error(self):
        replaced = '_wings_override_fixture'
        newly_loaded = '_wings_lazy_import_fixture'
        original = object(); substitute = object(); loaded = object()
        self.assertNotIn(replaced, sys.modules)
        self.assertNotIn(newly_loaded, sys.modules)
        sys.modules[replaced] = original
        try:
            with self.assertRaisesRegex(RuntimeError, 'fixture'):
                with module_overrides({replaced: substitute}):
                    self.assertIs(sys.modules[replaced], substitute)
                    sys.modules[newly_loaded] = loaded
                    raise RuntimeError('fixture')
            self.assertIs(sys.modules[replaced], original)
            self.assertIs(sys.modules[newly_loaded], loaded)
        finally:
            sys.modules.pop(replaced, None)
            sys.modules.pop(newly_loaded, None)

    def test_conflicting_siblings_fail_before_quadrature(self):
        nodes = tree(); before = copy.deepcopy(nodes)
        with patch.object(mapping, 'posterior_grid', side_effect=AssertionError('must not integrate')):
            with self.assertRaises(mapping.ZeroDurationTraitConflict) as caught:
                mapping.sample_histories(nodes, ['WY', 'KS'], 10, 1)
        self.assertEqual(nodes, before)
        self.assertEqual(caught.exception.conflicts[0]['component_root'], 'root')
        self.assertEqual({t['id'] for t in caught.exception.conflicts[0]['observations']}, {'a', 'b'})

    def test_conflict_across_internal_zero_edges_and_unsorted_nodes(self):
        nodes = tree()
        nodes[1]['parent'] = 'inner'
        nodes.append(dict(id='inner', parent='root', date=nodes[0]['date']))
        with self.assertRaises(mapping.ZeroDurationTraitConflict):
            mapping.TraitTree(list(reversed(nodes)), ['WY', 'KS'])

    def test_same_state_zero_branches_are_valid(self):
        t = mapping.TraitTree(tree(same=True), ['WY', 'KS'])
        np.testing.assert_allclose(t.prune([.01, 1, 100]), -math.log(2))
        histories, _ = mapping.sample_histories(tree(same=True), ['WY', 'KS'], 5, 1)
        self.assertTrue(all(not h['jumps'] and h['root_state']=='WY' for h in histories))

    def test_positive_branch_allows_state_change_and_matches_closed_form(self):
        t = mapping.TraitTree(tree(zero=False), ['WY', 'KS'])
        rates = np.array([.01, 1., 10.])
        expected = np.log(-np.expm1(-2*rates*t.lengths[2])/4)
        np.testing.assert_allclose(t.prune(rates), expected)
        histories, _ = mapping.sample_histories(tree(zero=False), ['WY', 'KS'], 5, 1)
        self.assertTrue(all(h['jumps'] for h in histories))

    def test_small_positive_branch_is_not_classified_as_zero(self):
        nodes=tree();nodes[2]['date']='2024-04-29T00:00:00.001Z'
        t=mapping.TraitTree(nodes,['WY','KS'])
        self.assertGreater(t.lengths[2],0)

    def test_invalid_tree_errors_are_not_reclassified(self):
        nodes=tree(); nodes[2]['date']='2023-04-29T00:00:00.000Z'
        with self.assertRaisesRegex(ValueError, 'Negative time branch') as caught:
            mapping.TraitTree(nodes,['WY','KS'])
        self.assertNotIsInstance(caught.exception,mapping.ZeroDurationTraitConflict)


class InferenceTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.selection=self.root/'selection';self.output=self.root/'output'
        record=dict(id='HA/available/replicate_1',segment='HA',strategy='available',replicate=1,
            seed=1,study=2,references=0,locations=['WY','KS'],reasons=[],status='ready',
            selected_sha256='hash',lineage=dict(status='ready',target_clade='test'),
            config=dict(temporal={}, min_clock_r2=.1,histories=5,rate_prior_shape=1,rate_prior_rate=1))
        write(self.selection/'selection.json',record)
        (self.selection/'input.fasta').write_text('>a\nACGT\n>b\nACGT\n')
        def clade(name, children):
            return types.SimpleNamespace(name=name,clades=children,numdate=mapping.numeric_date('2024-04-29T00:00:00Z'),is_terminal=lambda:not children)
        a=clade('a',[]); b=clade('b',[]); root=clade(None,[a,b])
        phylo_tree=types.SimpleNamespace(get_terminals=lambda:[a,b],find_clades=lambda **kwargs:[root,a,b])
        tt=types.SimpleNamespace(tree=phylo_tree,date2dist=types.SimpleNamespace(clock_rate=.001,r_val=.8),run=Mock())
        diag=dict(status='passed',reasons=[],observed=dict(rate=.001,r2=.64),
                  permutations={'tips':dict(p_value=.01),'same_date_clades':dict(p_value=.01)})
        self.enterContext(module_overrides({
            'treetime':types.SimpleNamespace(TreeTime=Mock(return_value=tt)),
            'Bio':types.SimpleNamespace(Phylo=types.SimpleNamespace(read=Mock(return_value=phylo_tree))),
            'phylodynamic_temporal':types.SimpleNamespace(diagnose=Mock(return_value=diag))}))
        self.enterContext(patch.object(inference,'read_tsv',return_value=[dict(id='a',location='WY',sample_id='a',date='2024-04-29'),dict(id='b',location='KS',sample_id='b',date='2024-04-29')]))
        self.enterContext(patch.object(inference,'mafft_runtime',return_value=('mafft',{})))
        self.enterContext(patch.object(inference.subprocess,'run'))
        self.enterContext(patch.object(inference.importlib.metadata,'version',return_value='test'))
        write(self.output/'movie.json',{'stale':True})
        write(self.output/'result.json',{'status':'complete','introductions':{'WY':{'mean':999}}})

    def test_conflict_writes_blocked_record_and_null_movie(self):
        record=inference.infer(self.selection,self.output,1)
        self.assertEqual(record['status'],'blocked')
        self.assertIn('zero_duration_trait_conflict',record['reasons'][0])
        self.assertEqual(len(record['trait_diagnostics']['conflicts']),1)
        self.assertNotIn('introductions',record)
        self.assertIsNone(json.loads((self.output/'movie.json').read_text()))
        self.assertEqual(json.loads((self.output/'result.json').read_text()),record)
        self.assertTrue((self.output/'dated_nodes.json').exists())

    def test_unrelated_mapping_failure_remains_an_error(self):
        with patch.object(inference,'sample_histories',side_effect=ValueError('quadrature failed')):
            with self.assertRaisesRegex(ValueError,'quadrature failed'):
                inference.infer(self.selection,self.output,1)
        self.assertEqual(json.loads((self.output/'result.json').read_text())['status'],'incomplete')
        self.assertIsNone(json.loads((self.output/'movie.json').read_text()))


class DownstreamTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.key='HA/available/replicate_1'
        self.blocked=dict(id=self.key,status='blocked',reasons=['zero_duration_trait_conflict'],
                         segment='HA',strategy='available',replicate=1,study=2,references=180)

    def test_fast_result_preserves_blocked_reason_without_reading_movie(self):
        write(self.root/'inference'/self.key/'result.json',self.blocked)
        out=self.root/'results/fast_v1/fast'/self.key/'result.json'
        with patch.object(results,'fast_sources',side_effect=AssertionError('must not read movie')):
            record=results.build_fast(self.root,self.key,out,{'include_beast':False})
        self.assertEqual(record['status'],'blocked')
        self.assertIn('zero_duration_trait_conflict',record['reasons'][0])
        self.assertNotIn('dataset',record)

    def test_final_results_list_blocked_analysis_as_unavailable(self):
        write(self.root/'results/fast_v1/fast'/self.key/'result.json',self.blocked)
        assets=self.root/'assets';assets.mkdir()
        for name in ('phylogeography-results.css','map-boundaries.js','phylogeography-results.js'):
            (assets/name).write_text('')
        with patch.object(results,'assets',return_value=assets):
            record=results.report(self.root,[self.key],self.root/'report',{'include_beast':False})
        analysis=record['analyses'][0]
        self.assertEqual(analysis['methods'],{})
        self.assertIn('zero_duration_trait_conflict',analysis['unavailable']['fast'])

    def run_summary(self,records):
        selection=self.root/'selection';output=self.root/'summary'
        output.mkdir(exist_ok=True)
        write(selection/'selection_summary.json',dict(replicates=[{'id':r['id']} for r in records],
            config=dict(segments=['HA'],strategies=['balanced','available'])))
        for record in records:
            write(self.root/'inference'/record['id']/'result.json',record)
            write(self.root/'inference'/record['id']/'movie.json',{'segments':[],'locations':[],'provenance':{}} if record['status']=='complete' else None)
        comparison.scoped_movie.reset_mock();comparison.scoped_movie.side_effect=lambda movie,record:(movie,None)
        return summary.summarize(selection,self.root/'inference',output)

    def test_sensitivity_counts_and_ranges_exclude_blocked_replicates(self):
        complete=dict(self.blocked,id='HA/balanced/replicate_1',strategy='balanced',status='complete',reasons=[],
                      introductions={'WY':dict(mean=2,lower=1,upper=3)})
        record=self.run_summary([complete,self.blocked])
        self.assertEqual(record['replicate_counts'],dict(total=2,complete=1,blocked=1,incomplete=0))
        self.assertEqual(record['sensitivity'][0]['completed_replicates'],1)
        self.assertEqual(record['sensitivity'][0]['mean_range'],[2,2])
        comparison.scoped_movie.assert_called_once()
        html=(self.root/'summary/sensitivity.html').read_text()
        self.assertIn('1 complete of 2 requested; 1 blocked',html)
        self.assertIn('zero_duration_trait_conflict',html)

    def test_blocked_primary_is_not_replaced_by_other_replicate(self):
        primary=dict(self.blocked,id='HA/balanced/replicate_1',strategy='balanced')
        complete=dict(self.blocked,id='HA/available/replicate_2',replicate=2,status='complete',reasons=[],introductions={})
        record=self.run_summary([primary,complete])
        self.assertIsNone(record['phylogeography'])

    def test_all_blocked_has_no_estimates_or_movie(self):
        record=self.run_summary([self.blocked])
        self.assertEqual(record['sensitivity'],[])
        self.assertIsNone(record['phylogeography'])
        comparison.scoped_movie.assert_not_called()
        self.assertEqual(record['replicate_counts']['complete'],0)


if __name__=='__main__':
    unittest.main()
