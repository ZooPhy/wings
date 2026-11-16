import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from explorer_phylodynamics import attach_results
from phylodynamics_job_options import apply_options, validate_options


class JobOptions(unittest.TestCase):
    def test_default_does_not_launch_optional_analyses(self):
        config = {k: {'enabled': True} for k in ('phylodynamics', 'phylogeography_results', 'bayesian_dating', 'posterior_phylogeography')}
        with patch.dict(os.environ, {}, clear=True):
            apply_options(config, {}, ROOT)
        self.assertTrue(all(not v['enabled'] for v in config.values()))

    def test_fast_new_job_builds_inputs_and_never_launches_beast(self):
        config = {}
        with patch.dict(os.environ, {'NCBI_EMAIL': 'test@example.org'}):
            apply_options(config, {'phylodynamics': True, 'explorer': False}, ROOT)
        self.assertTrue(config['run_surveillance_explorer'])
        self.assertFalse(config['phylogeography_results']['saved_inputs_only'])
        self.assertFalse(config['phylogeography_results']['include_beast'])
        self.assertFalse(config['bayesian_dating']['enabled'])
        self.assertFalse(config['posterior_phylogeography']['enabled'])
        self.assertEqual(config['phylodynamics']['references']['source'], 'ncbi')
        self.assertTrue(Path(config['phylodynamics']['references']['cache_dir']).is_absolute())
        self.assertEqual(config['phylodynamics']['strategies'], ['balanced', 'available'])
        self.assertEqual(config['phylodynamics']['replicates'], 3)

    def test_invalid_request_rejected_before_execution(self):
        for value in ('false', 1, None):
            with self.assertRaises(ValueError):
                validate_options({'phylodynamics': value})
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'NCBI_EMAIL'):
            validate_options({'phylodynamics': True})


class CohortAttachment(unittest.TestCase):
    def setUp(self):
        self.model = {'schema': 'wings.phylogeography-results.v1', 'default_method': 'fast', 'default_analysis': 'HA/balanced/replicate_1', 'analyses': [{'id': 'HA/balanced/replicate_1', 'methods': {'fast': {'method': 'fast', 'status': 'passed', 'focal_sample_ids': ['sample1']}}, 'unavailable': {}}]}

    def attach(self, model):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'results.json'; path.write_text(json.dumps(model))
            return attach_results({'samples': [{'sample_id': 'sample1'}, {'sample_id': 'sample2'}]}, path)

    def test_qc_subset_allowed(self):
        self.assertEqual(self.attach(self.model)['phylodynamics_results'], self.model)

    def test_other_cohort_rejected(self):
        self.model['analyses'][0]['methods']['fast']['focal_sample_ids'] = ['unrelated']
        with self.assertRaisesRegex(ValueError, 'cohort'):
            self.attach(self.model)

    def test_demo_and_failed_results_rejected(self):
        self.model['demo'] = True
        with self.assertRaises(ValueError): self.attach(self.model)
        self.model.pop('demo'); self.model['analyses'][0]['methods']['fast']['status'] = 'failed'
        with self.assertRaises(ValueError): self.attach(self.model)

    def test_unavailable_primary_is_preserved_without_fallback(self):
        row = self.model['analyses'][0]; row['methods'] = {}; row['unavailable'] = {'fast': 'temporal screen failed'}
        self.assertEqual(self.attach(self.model)['phylodynamics_results'], self.model)


if __name__ == '__main__':
    unittest.main()
