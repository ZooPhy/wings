"""Interactive input attachment and preservation of saved report evidence."""
import copy
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from attach_genomic_ecological_concordance import compact_concordance
from refresh_concordance_inputs import enrich_report
from build_genomic_ecological_concordance import _fit, BASELINE, HOST
import refresh_demo_ui as ui
import refresh_demo_navigation as demo
import wings_bundle_format as codec
import refresh_report_model_explorer as saved_report


class InteractiveInputsTests(unittest.TestCase):
    def test_browser_permutation_matches_independent_python_reference(self):
        repo = Path(__file__).resolve().parents[1]
        fixture = json.loads((repo / 'tests/fixtures/concordance_model_explorer.json').read_text())
        rows = fixture['pairs']
        reduced, full = _fit(rows, BASELINE), _fit(rows, HOST)
        observed = full['r2'] - reduced['r2']
        ids = sorted({r[k] for r in rows for k in ('sample_a', 'sample_b')})
        residuals = {tuple(sorted((r['sample_a'], r['sample_b']))): v
                     for r, v in zip(rows, reduced['_residuals'])}
        state = 17
        extreme = valid = 0
        for _ in range(19):
            shuffled = ids[:]
            for i in range(len(shuffled) - 1, 0, -1):
                state ^= (state << 13) & 0xffffffff
                state ^= state >> 17
                state ^= (state << 5) & 0xffffffff
                state &= 0xffffffff
                j = int(state / 4294967296 * (i + 1))
                shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
            mapping = dict(zip(ids, shuffled))
            y = [fitted + residuals[tuple(sorted((mapping[r['sample_a']], mapping[r['sample_b']])))]
                 for r, fitted in zip(rows, reduced['_fitted'])]
            delta = _fit(rows, HOST, y)['r2'] - _fit(rows, BASELINE, y)['r2']
            valid += 1
            extreme += delta >= observed - 1e-12
        script = """const api=require('./scripts/report/concordance-model-explorer.js');
const f=require('./tests/fixtures/concordance_model_explorer.json');
api.analyze(f,{factors:['host'],permutations:19,seed:17}).then(r=>console.log(JSON.stringify(r.results.find(x=>x.segment==='HA'&&x.code==='host'))));"""
        result = json.loads(subprocess.check_output(['node', '-e', script], cwd=repo, text=True))
        self.assertEqual(result['permutations_valid'], valid)
        self.assertEqual(result['permutation_p'], (int(extreme) + 1) / (valid + 1))

    def data(self):
        return {'schema_version': 'wings.genomic_ecological_concordance.v3',
                'models': [{'segment': 'HA', 'full_r2': .3}], 'readiness': {'total_samples': 2},
                'sample_features': [{'sample_id': 'A', 'migration_context_key': 'US-AZ|2025-10-01'},
                                    {'sample_id': 'B', 'migration_context_key': None}],
                'pairs': [{'segment': 'HA', 'sample_a': 'A', 'sample_b': 'B',
                           'patristic_distance': .1, 'temporal_days': 3, 'geographic_km': None}]}

    def test_attachment_preserves_missing_values_and_saved_models(self):
        raw = self.data()
        before = copy.deepcopy(raw)
        compact = compact_concordance(raw)
        self.assertEqual(compact['models'], raw['models'])
        self.assertIsNone(compact['interactive_inputs']['pairs'][0]['geographic_km'])
        self.assertEqual(compact['interactive_inputs']['sample_features'][1]['migration_context_key'], None)
        self.assertEqual(raw, before)

    def test_saved_html_enrichment_preserves_all_prior_payload_fields(self):
        data = self.data()
        del data['pairs']
        del data['sample_features']
        payload = {'samples': [{'sample_id': 'A', 'host': '<test>', 'collection_date': '2025-10-01', 'latitude': 1, 'longitude': 2},
                               {'sample_id': 'B', 'host': 'other', 'collection_date': '2025-10-04', 'latitude': 2, 'longitude': 3}],
                   'trees': {'HA': {'root': {'children': [{'sample_id': 'A', 'name': 'A', 'length': .1},
                                                          {'sample_id': 'B', 'name': 'B', 'length': .2}]}}},
                   'genomic_ecological_concordance': data}
        source = '<script type="application/json" id="wings-surveillance-data-0">' + json.dumps(payload) + '</script>'
        updated = enrich_report(source)
        parsed = ui.ReportHTML(updated)
        after = json.loads(parsed.body(parsed.blocks[0]))
        inputs = after['genomic_ecological_concordance'].pop('interactive_inputs')
        self.assertEqual(after, payload)
        self.assertEqual(len(inputs['pairs']), 1)
        self.assertAlmostEqual(inputs['pairs'][0]['patristic_distance'], .3)
        self.assertNotIn('<test>', updated)
        self.assertEqual(enrich_report(updated), updated)

    def test_demo_bundle_refresh_is_idempotent_and_preserves_saved_analysis(self):
        payload = {'samples': [{'sample_id': 'A'}, {'sample_id': 'B'}], 'trees': {},
                   'genomic_ecological_concordance': {'schema_version': 'wings.genomic_ecological_concordance.v3',
                                                      'models': [], 'readiness': {'total_samples': 2}}}
        summary = ('<html><head><script>class Explorer {} /* WINGS_MIGRATION_WEAVE_JS_BEGIN */</script>'
                   '<style>.wings-surveillance-explorer {} .wse-genome-controls {}</style>'
                   '<style>:root {--escape-maroon: red} .report-header {}</style></head><body>'
                   '<div class="report-brand-logo">logo</div><p><strong>Segment PASS criteria:</strong></p>'
                   '<script type="application/json" id="wings-surveillance-data-0">' + json.dumps(payload) + '</script></body></html>')
        assets = {'explorer script': b'class Explorer {} /* WINGS_MIGRATION_WEAVE_JS_BEGIN; WINGS_MODEL_EXPLORER */',
                  'explorer stylesheet': b'.wings-surveillance-explorer {} .wse-genome-controls {color:green}',
                  'report stylesheet': b':root {--escape-maroon: red} .report-header {}', 'WINGS logo': b'synthetic-logo'}
        bundle = {'format': codec.BUNDLE_FORMAT, 'version': 1, 'sample_count': 2,
                  'run_summary': {'html': summary}, 'samples': {s: {'html': '<html><body>sample ' + s + '</body></html>', 'calls': [s]}
                                                             for s in ('A', 'B')}, 'provenance': {'keep': 'exact'}}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temporary:
            repo = Path(temporary)
            (repo / 'demo').mkdir()
            (repo / 'scripts/report').mkdir(parents=True)
            (repo / 'scripts/report/sample-navigation.css').write_text('/* sample css */')
            (repo / 'scripts/report/sample-navigation.js').write_text('/* sample js */')
            raw, compressed = repo / 'demo/wings_demo.wings', repo / 'demo/wings_demo.wings.gz'
            codec.write_bundle(bundle, raw)
            codec.write_bundle(bundle, compressed, compress=True)
            with patch.object(ui, 'asset_bytes', return_value=assets), patch.object(ui.Path, 'home', return_value=repo / 'test-home'):
                self.assertEqual(demo.refresh(repo, 'apply'), 0)
                a, b = codec.read_bundle(raw), codec.read_bundle(compressed)
                self.assertEqual(a, b)
                self.assertEqual(a['provenance'], bundle['provenance'])
                self.assertEqual(a['samples']['A']['calls'], ['A'])
                self.assertIn('WINGS_MODEL_EXPLORER', a['run_summary']['html'])
                self.assertIn('interactive_inputs', a['run_summary']['html'])
                snapshot = compressed.read_bytes()
                self.assertEqual(demo.refresh(repo, 'check'), 0)
                self.assertEqual(compressed.read_bytes(), snapshot)
                with patch.object(ui, 'asset_bytes', return_value=assets):
                    output = repo / 'updated.wings'
                    saved_report.refresh(repo, raw, output)
                    refreshed = codec.read_bundle(output)
                    self.assertEqual(refreshed['samples'], a['samples'])
                    self.assertEqual(refreshed['provenance'], a['provenance'])
                    self.assertEqual(codec.read_bundle(raw), a)
                    with self.assertRaisesRegex(ValueError, 'new output'):
                        saved_report.refresh(repo, raw, output)


if __name__ == '__main__':
    unittest.main()
