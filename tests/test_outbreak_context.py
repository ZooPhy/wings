import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('outbreak_builder', ROOT / 'scripts/build_surveillance_explorer.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class OutbreakTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.csv = self.root / 'aphis.csv'

    def tearDown(self):
        self.temp.cleanup()

    def write_rows(self, rows, headers=None):
        with self.csv.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(headers or builder.APHIS_COLUMNS)
            writer.writerows(rows)

    def row(self, collection='1/2/2025', detection='1/9/2025', state='Kentucky', county='Fayette'):
        return [state, county, collection, detection, 'EA H5', 'Mallard', 'Wild bird', 'Live bird', 'NWDP']

    def test_repeated_records_retained_with_unique_snapshot_row_references(self):
        self.write_rows([self.row(), self.row()])
        result = builder.build_outbreak_context(self.csv)
        self.assertEqual(result['record_count'], 2)
        self.assertEqual(result['repeated_rows_retained'], 1)
        self.assertEqual([r['source_row'] for r in result['records']], [1, 2])
        self.assertEqual(result['sha256'], hashlib.sha256(self.csv.read_bytes()).hexdigest())
        self.assertNotIn('latitude', result['records'][0])

    def test_dates_remain_distinct_and_unknown_collection_is_not_replaced(self):
        self.write_rows([self.row(), self.row(collection='Unknown'), self.row(collection='2/30/2025')])
        result = builder.build_outbreak_context(self.csv)
        self.assertEqual(result['records'][0]['collection_date'], '2025-01-02')
        self.assertEqual(result['records'][0]['detected_date'], '2025-01-09')
        self.assertIsNone(result['records'][1]['collection_date'])
        self.assertEqual(result['records'][1]['collection_date_raw'], 'Unknown')
        self.assertEqual(result['undated_counts'], {'collection_date': 2, 'detected_date': 0})

    def test_state_normalization_and_unmapped_rows_remain_visible(self):
        self.write_rows([self.row(state='KY'), self.row(state='US-KY'), self.row(state='DC', county='Unknown'), self.row(state='Not a state')])
        result = builder.build_outbreak_context(self.csv)
        self.assertEqual([r['state_code'] for r in result['records']], ['KY', 'KY', 'DC', None])
        self.assertEqual(result['records'][2]['geographic_precision'], 'state')
        self.assertEqual(result['unmapped_states'], ['Not a state'])

    def test_provenance_hash_mismatch_fails_instead_of_mislabeling_snapshot(self):
        self.write_rows([self.row()])
        provenance = self.root / 'provenance.json'
        provenance.write_text(json.dumps({'sha256': 'wrong'}))
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            builder.build_outbreak_context(self.csv, provenance)
        provenance.write_text(json.dumps({'sha256': hashlib.sha256(self.csv.read_bytes()).hexdigest(), 'snapshot_supplied_date': '2025-01-10', 'snapshot_date_basis': 'User-provided snapshot'}))
        self.assertEqual(builder.build_outbreak_context(self.csv, provenance)['snapshot_supplied_date'], '2025-01-10')

    def test_required_headers_and_malformed_rows_are_rejected(self):
        self.write_rows([self.row()[:-1]])
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            builder.build_outbreak_context(self.csv)
        self.write_rows([], headers=['State', 'County'])
        with self.assertRaisesRegex(ValueError, 'headers'):
            builder.build_outbreak_context(self.csv)

    def test_absent_empty_and_disabled_sources_are_distinct(self):
        self.assertEqual(builder.build_outbreak_context(None)['status'], 'NOT_CONFIGURED')
        self.write_rows([])
        result = builder.build_outbreak_context(self.csv)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['record_count'], 0)
        self.assertIsNone(result['date_ranges']['collection_date']['min'])
        with self.assertRaises(FileNotFoundError):
            builder.build_outbreak_context(self.root / 'missing.csv')

    def test_snakemake_entrypoint_loads_the_configured_snapshot(self):
        import runpy
        from types import SimpleNamespace
        self.write_rows([self.row()])
        metadata = self.root / 'metadata.tsv'
        metadata.write_text('sample_id\thost\tcollection_date\tstate\tcountry\nexample\tMallard\t2025-01-02\tKY\tUS\n')
        output = self.root / 'explorer.json'
        inputs = SimpleNamespace(metadata=str(metadata), summaries=[], trees=[], coverage=[], genoflu=[], aphis_csv=[str(self.csv)], aphis_provenance=[])
        runpy.run_path(str(ROOT / 'scripts/build_surveillance_explorer.py'), run_name='__main__', init_globals={'snakemake': SimpleNamespace(input=inputs, output=SimpleNamespace(json=str(output)))})
        payload = json.loads(output.read_text())
        self.assertEqual(payload['outbreak_context']['record_count'], 1)
        self.assertEqual(payload['outbreak_context']['records'][0]['state_code'], 'KY')

    def test_builder_includes_context_without_requiring_sample_coordinates(self):
        self.write_rows([self.row()])
        metadata = self.root / 'metadata.tsv'
        metadata.write_text('sample_id\thost\tcollection_date\tstate\tcountry\nexample\tMallard\t2025-01-02\tKY\tUS\n')
        payload = builder.build_payload(metadata, [], [], aphis_csv=self.csv)
        self.assertFalse(payload['samples'][0]['has_coordinates'])
        self.assertEqual(payload['outbreak_context']['record_count'], 1)
        self.assertEqual(builder.build_payload(metadata, [], [])['outbreak_context']['status'], 'NOT_CONFIGURED')

if __name__ == '__main__':
    unittest.main()
