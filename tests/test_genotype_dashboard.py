import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("genotype_dashboard", ROOT / "scripts/build_genotype_dashboard.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.page = self.directory / "page.html"
        self.css = self.directory / "page.css"
        self.js = self.directory / "page.js"
        self.snapshot = self.directory / "snapshot.json"
        self.page.write_text('<html><head><script src="page.js"></script></head><body><header>Portal</header><main><h1>Genotypes</h1></main></body></html>')
        self.css.write_text('body {color:#000000;background:#FFFFFF}')
        self.js.write_text('const embedded = "wings-genotype-frequency-data"; const example = "</script>";')
        self.data = {"schema_version":"wings.genotype-frequencies.v1", "groups":[], "unit":"SRA run", "has_metadata":True,
                     "audit":{"included_runs":0,"assigned_runs":0}, "label":"</script><img src=x onerror=alert(1)>"}
        self.snapshot.write_text(json.dumps(self.data))

    def build(self):
        return builder.build_dashboard(self.page, [self.css], self.js, self.snapshot)

    def test_snapshot_round_trip_and_source_hash(self):
        raw = self.snapshot.read_bytes()
        html = self.build()
        embedded = re.search(r'id="wings-genotype-frequency-data">(.*?)</script>', html, re.S)[1]
        data = json.loads(embedded)
        self.assertEqual(data["label"], self.data["label"])
        self.assertEqual(data["report_snapshot"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.snapshot.read_bytes(), raw)

    def test_snapshot_cannot_end_the_json_script(self):
        html = self.build()
        self.assertNotIn('</script><img', html)
        self.assertIn(r'<\/script>', html)
        self.assertEqual(html.count('<script'), 3)
        self.assertEqual(html.count('</script>'), 3)

    def test_embeds_page_assets_without_navigation_or_external_asset_loads(self):
        html = self.build()
        self.assertIn('<main><h1>Genotypes</h1></main>', html)
        self.assertIn(self.css.read_text(), html)
        self.assertNotIn('<header', html)
        self.assertNotRegex(html, r'<script[^>]+src=|<link[^>]+href=')
        self.assertIn('wings-genotype-height', html)

    def test_fails_for_wrong_snapshot_or_missing_embed_support(self):
        self.snapshot.write_text('{"schema_version":"other"}')
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            self.build()
        self.snapshot.write_text(json.dumps(self.data))
        self.js.write_text('fetch("data.json")')
        with self.assertRaisesRegex(ValueError, 'embedded-snapshot'):
            self.build()

    def write_explorer(self, samples):
        path = self.directory / 'explorer.json'
        path.write_text(json.dumps({'samples': samples, 'ebird_contexts': [
            {'host': 'BLVU', 'species': 'Black Vulture'}]}))
        return path

    def sample(self, sample_id='s1', status='RECORDED', call='D1.1', date='2025-04-15'):
        return {'sample_id': sample_id, 'host': 'BLVU', 'collection_date': date,
                'country': 'USA', 'state': 'Kentucky', 'genotype': {'status': status, 'call': call}}

    def test_wings_counts_use_samples_and_preserve_unavailable_assignments(self):
        samples = [self.sample(), self.sample('s2', 'NOT_ASSIGNED', None),
                   self.sample('s3', 'H5_OR_NA_INDETERMINATE', None, '2025'),
                   self.sample('s4', 'DISABLED_BY_CONFIG', None), self.sample('s5', 'FAILED', None)]
        path = self.write_explorer(samples)
        data = builder.wings_snapshot(path)
        self.assertEqual(data['unit'], 'WINGS sample')
        self.assertEqual(data['audit']['included_samples'], 5)
        self.assertEqual(data['audit']['assigned_samples'], 1)
        self.assertEqual(data['audit']['status_counts'], {'assigned': 1, 'unassigned': 1, 'not_eligible': 1, 'disabled': 1, 'failed': 1})
        self.assertEqual({g['host'] for g in data['groups']}, {'Black Vulture'})
        self.assertEqual({g['location'] for g in data['groups']}, {'USA / Kentucky'})
        self.assertIsNone(next(g for g in data['groups'] if g['status']=='not_eligible')['month'])
        self.assertEqual(data['sources'][0]['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_duplicates_do_not_inflate_counts_and_conflicting_rows_fail(self):
        sample = self.sample()
        path = self.write_explorer([sample, dict(sample)])
        data = builder.wings_snapshot(path)
        self.assertEqual(data['audit']['included_samples'], 1)
        self.assertEqual(data['audit']['duplicate_records_collapsed'], 1)
        path = self.write_explorer([sample, self.sample(call='B3.13')])
        with self.assertRaisesRegex(ValueError, 'Conflicting WINGS records'):
            builder.wings_snapshot(path)

    def test_missing_dates_and_labels_are_not_invented(self):
        sample = self.sample(date='2025-02-29', status='NOT_RECORDED', call='D1.1')
        sample['host'] = 'UNKNOWN-CODE'
        path = self.write_explorer([sample])
        data = builder.wings_snapshot(path)
        self.assertEqual(data['audit']['assigned_samples'], 0)
        self.assertEqual(data['groups'][0]['host'], 'UNKNOWN-CODE')
        self.assertIsNone(data['groups'][0]['month'])
        self.assertIsNone(data['groups'][0]['genotype'])

    def test_public_and_local_payloads_are_separate_and_html_safe(self):
        sample = self.sample()
        sample['host_common_name'] = '</script><img src=x>'
        path = self.write_explorer([sample])
        html = builder.build_dashboard(self.page, [self.css], self.js, self.snapshot, path)
        local = json.loads(re.search(r'id="wings-genotype-local-data">(.*?)</script>', html, re.S)[1])
        public = json.loads(re.search(r'id="wings-genotype-frequency-data">(.*?)</script>', html, re.S)[1])
        self.assertEqual(local['audit']['included_samples'], 1)
        self.assertEqual(public['audit']['included_runs'], 0)
        self.assertEqual(local['groups'][0]['host'], sample['host_common_name'])
        self.assertNotIn('</script><img', html)
        self.assertNotIn('sample_id', json.dumps(local['groups']))

    def test_local_status_parser_keeps_skips_and_failures_out_of_assigned_counts(self):
        for value, expected in [('SKIPPED_QC','not_run'),('FAILED_TOOL','failed'),('DISABLED_BY_CONFIG','disabled'),('NOT_ASSIGNED','unassigned')]:
            self.assertEqual(builder.recorded_call({'status': value, 'call': 'D1.1'})[0], expected)
        self.assertEqual(builder.recorded_call({'status': 'RECORDED', 'call': 'Minor114'})[:2], ('assigned', 'Minor114'))


if __name__ == '__main__':
    unittest.main()
