"""Report refresh must not substitute incomplete inputs for saved analyses."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from attach_genomic_ecological_concordance import compact_concordance
from refresh_concordance_inputs import enrich_report
from refresh_demo_ui import ReportHTML
from test_genomic_ecological_concordance import fixture, gec


def html(payload):
    return '<script type="application/json">' + json.dumps(payload) + '</script>'


def payload(source):
    parsed = ReportHTML(source)
    return json.loads(parsed.body(parsed.blocks[0]))


class VerifiedRefreshTests(unittest.TestCase):
    def setUp(self):
        self.complete = fixture()
        self.raw = gec.build(self.complete, permutations=0)
        self.saved = compact_concordance(self.raw)
        self.saved.pop('interactive_inputs')
        self.old = copy.deepcopy(self.complete)
        self.old.pop('ecological_clock')
        self.old.pop('ecological_context')
        self.old['genomic_ecological_concordance'] = self.saved

    def test_missing_external_context_keeps_saved_results_without_enabling_refit(self):
        source = html(self.old)
        self.assertEqual(enrich_report(source), source)
        self.assertEqual(self.saved['models'][0]['n_samples'], 12)
        self.assertNotIn('interactive_inputs', payload(enrich_report(source))['genomic_ecological_concordance'])

    def test_original_concordance_restores_all_pairs_and_preserves_saved_results(self):
        updated = payload(enrich_report(html(self.old), self.raw))
        inputs = updated['genomic_ecological_concordance'].pop('interactive_inputs')
        self.assertEqual(updated, self.old)
        self.assertEqual(inputs['pairs'], self.raw['pairs'])
        self.assertEqual(inputs['sample_features'], self.raw['sample_features'])
        self.assertEqual(sum(p['environmental_distance'] is not None for p in inputs['pairs']), 66)
        self.assertEqual(sum(p['seasonal_profile_distance'] is not None for p in inputs['pairs']), 66)

    def test_embedded_context_is_accepted_only_when_it_reproduces_saved_fits(self):
        complete = {**self.complete, 'genomic_ecological_concordance': self.saved}
        updated = enrich_report(html(complete))
        inputs = payload(updated)['genomic_ecological_concordance']['interactive_inputs']
        self.assertEqual(inputs['pairs'], self.raw['pairs'])
        self.assertEqual(enrich_report(updated), updated)
        # Same sample counts are insufficient: changed tree lengths change fits.
        altered = copy.deepcopy(complete)
        altered['trees']['HA']['root']['children'][0]['length'] += 1
        self.assertNotIn('interactive_inputs', payload(enrich_report(html(altered)))['genomic_ecological_concordance'])

    def test_previously_reconstructed_incomplete_inputs_are_removed(self):
        pairs, features, _ = gec.build_pairs(self.old)
        old = copy.deepcopy(self.old)
        old['genomic_ecological_concordance']['interactive_inputs'] = {
            'pairs': pairs, 'sample_features': features,
            'derived_from': 'Existing embedded trees, sample metadata and ecological context; no new trees or observations.'}
        self.assertEqual(payload(enrich_report(html(old))), self.old)

    def test_wrong_run_or_modified_pair_inputs_are_rejected(self):
        wrong = copy.deepcopy(self.raw)
        wrong['models'][0]['n_samples'] += 1
        with self.assertRaisesRegex(ValueError, 'does not match'):
            enrich_report(html(self.old), wrong)
        wrong = copy.deepcopy(self.raw)
        wrong['pairs'][0]['patristic_distance'] += 1
        with self.assertRaisesRegex(ValueError, 'do not reproduce'):
            enrich_report(html(self.old), wrong)


if __name__ == '__main__':
    unittest.main()
