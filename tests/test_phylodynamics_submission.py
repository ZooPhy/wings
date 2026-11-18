"""Submission configuration and dependency contracts; no biological analyses."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from phylodynamics_job_options import apply_options, validate_options, supported_methods, BEAST_REQUIRED
from phylodynamics_submission import live_beast, beast_publications, posterior_inputs, dating_sidecar


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        for name in BEAST_REQUIRED:
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
        (self.repo / 'config/phylodynamics-beast-job.yaml').write_bytes(
            (REPO / 'config/phylodynamics-beast-job.yaml').read_bytes())
        fixture = {'phylodynamics': {'enabled': False, 'references': {'cache_dir': 'cache/ref'},
                                    'lineage': {'cache_dir': 'cache/lineage'}},
                   'phylogeography_results': {'enabled': False, 'run_id': 'fast_v1'}}
        for key, name in [('phylodynamics', 'phylodynamics.example.yaml'),
                          ('phylogeography_results', 'phylogeography-results.example.yaml')]:
            (self.repo / 'config' / name).write_text(yaml.safe_dump({key: fixture[key]}))
        env = patch.dict(os.environ, {'NCBI_EMAIL': 'tests@example.org'})
        env.start(); self.addCleanup(env.stop)

    def config(self, method=None, enabled=True, phylogeny=False):
        c = {'phylogeny': {'enabled': phylogeny}}
        options = {'phylodynamics': enabled}
        if method is not None:
            options['phylodynamics_method'] = method
        apply_options(c, options, self.repo)
        return c

    def test_legacy_and_fast_default(self):
        for method in (None, 'fast'):
            c = self.config(method)
            self.assertEqual(c['phylogeography_results']['method'], 'fast')
            self.assertFalse(c['bayesian_dating']['enabled'])
            self.assertFalse(c['posterior_phylogeography']['enabled'])
            self.assertFalse(live_beast(c))
            self.assertEqual(beast_publications(c, 'results'), [])

    def test_beast_configuration_and_checks(self):
        c = self.config('beast')
        self.assertTrue(live_beast(c))
        b, p = c['bayesian_dating'], c['posterior_phylogeography']
        self.assertEqual(b['chains'], 2)
        self.assertEqual(b['chain_length'], 20_000_000)
        self.assertFalse(b['prior_only'])
        self.assertEqual(b['analyses'], ['HA/balanced/replicate_1'])
        for v in (b, p):
            self.assertLessEqual(v['max_rhat'], 1.01)
            self.assertGreaterEqual(v['min_bulk_ess'], 400)
            self.assertGreaterEqual(v['min_tail_ess'], 400)
            self.assertGreaterEqual(v['min_chain_ess'], 100)
        self.assertLessEqual(p['max_date_mcse_days'], 7)
        self.assertLessEqual(p['max_hpd_endpoint_mcse_days'], 14)
        self.assertLessEqual(p['max_mean_mcse'], .15)
        self.assertLessEqual(p['max_probability_mcse'], .025)
        self.assertEqual(c['phylogeography_results']['analyses'], [])
        self.assertNotIn('tests@example.org', yaml.safe_dump(c))

    def test_phylogenetics_independent_and_explorer_required(self):
        for method in ('fast', 'beast'):
            for phylogeny in (False, True):
                c = self.config(method, phylogeny=phylogeny)
                self.assertEqual(c['phylogeny']['enabled'], phylogeny)
                self.assertTrue(c['run_surveillance_explorer'])

    def test_disabled_and_method_switch_clear_previous_beast(self):
        c = self.config('beast')
        apply_options(c, {'phylodynamics': True, 'phylodynamics_method': 'fast'}, self.repo)
        self.assertFalse(c['bayesian_dating']['enabled'])
        self.assertFalse(c['posterior_phylogeography']['enabled'])
        apply_options(c, {'phylodynamics': False, 'phylodynamics_method': 'beast'}, self.repo)
        for key in ('bayesian_dating', 'posterior_phylogeography', 'phylodynamics', 'phylogeography_results'):
            self.assertFalse(c[key]['enabled'])

    def test_reject_invalid_method_and_missing_contact(self):
        for method in ('BEAST', '', None, [], True):
            with self.assertRaises(ValueError):
                validate_options({'phylodynamics': True, 'phylodynamics_method': method})
        with patch.dict(os.environ, {'NCBI_EMAIL': ''}):
            with self.assertRaises(ValueError):
                self.config('beast')

    def test_capabilities_fail_closed(self):
        self.assertIn('beast', supported_methods(self.repo))
        (self.repo / 'scripts/WingsBeast.java').unlink()
        self.assertEqual(supported_methods(self.repo), ['fast'])
        with self.assertRaises(ValueError):
            self.config('beast')

    def test_live_dependencies_require_publication_not_existing_files(self):
        c = self.config('beast')
        paths = beast_publications(c, 'results/run_summary/phylodynamics')
        self.assertEqual(len(paths), 2)
        self.assertTrue(paths[0].endswith('/publication/publication.json'))
        self.assertTrue(paths[1].endswith('/publication/movie.json'))
        def no_dag_read(*args):
            raise AssertionError('New job must not read nonexistent summary during DAG creation')
        self.assertEqual(posterior_inputs(c, 'run', 'inference', 'selection', no_dag_read), ['run/summary.json'])
        self.assertEqual(dating_sidecar(c, 'missing/alignment.fasta'), [])

    def test_saved_reporting_preserves_isolation(self):
        c = self.config('beast')
        c['phylogeography_results']['saved_inputs_only'] = True
        self.assertEqual(beast_publications(c, 'results'), [])
        self.assertEqual(dating_sidecar(c, 'saved/alignment.fasta'), ['saved/alignment.fasta'])
        self.assertEqual(posterior_inputs(c, 'run', 'inf', 'sel', lambda *a: ['saved.json']), ['saved.json'])

    def test_mismatched_run_ids_and_disabled_gate_fail(self):
        base = self.config('beast')
        for key, field, value in [('posterior_phylogeography', 'enabled', False),
                                  ('posterior_phylogeography', 'dating_run', 'wrong'),
                                  ('phylogeography_results', 'posterior_run', 'wrong'),
                                  ('posterior_phylogeography', 'analyses', ['HA/balanced/replicate_2'])]:
            c = copy.deepcopy(base); c[key][field] = value
            with self.assertRaises(ValueError):
                live_beast(c)


if __name__ == '__main__':
    unittest.main()
