import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('genotype_refresh', ROOT / 'scripts/refresh_genotype_frequencies.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / 'seed.json'
        self.cache = self.root / 'cache'
        self.now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        self.data = module.build_snapshot([{'sample': 'SRR1', 'Genotype': 'D1.1'}],
                                         [{'Run': 'SRR1', 'Collection_Date': '2025-04-15', 'Host': 'Bird'}])
        self.data.update(built_at=(self.now-timedelta(days=1)).isoformat(), source_commit='a'*40)
        module.atomic_json(self.seed, self.data)
        self.tables = {'genoflu_results.tsv': b'sample\tGenotype\nSRR1\tD1.1\nSRR2\tNot assigned\n',
                       'SraRunTable_automated_normalized.tsv': b'Run\tCollection_Date\tHost\tgeo_loc_name\nSRR1\t2025-04-15\tBird\tUSA\nSRR2\t2025-05\tBird\tUSA\n'}

    def refresh(self, **kwargs):
        return module.refresh(self.seed, self.cache, now=self.now, **kwargs)

    def test_recent_snapshot_does_not_fetch(self):
        with patch.object(module, 'fetch_sources') as fetch:
            data = self.refresh()
        fetch.assert_not_called()
        self.assertEqual(data['report_refresh']['status'], 'cached')

    def test_stale_refresh_validates_both_tables_and_reuses_the_cache(self):
        self.data['built_at'] = (self.now-timedelta(days=10)).isoformat()
        module.atomic_json(self.seed, self.data)
        seed_before = self.seed.read_bytes()
        with patch.object(module, 'fetch_sources', return_value=(self.tables, 'b'*40)) as fetch:
            data = self.refresh()
        fetch.assert_called_once_with('master', timeout=20)
        self.assertEqual(data['source_commit'], 'b'*40)
        self.assertEqual(data['audit']['included_runs'], 2)
        self.assertEqual(data['report_refresh']['status'], 'updated')
        self.assertEqual(self.seed.read_bytes(), seed_before)
        with patch.object(module, 'fetch_sources') as fetch:
            cached = self.refresh()
        fetch.assert_not_called()
        self.assertEqual(cached['source_commit'], 'b'*40)
        self.assertEqual(cached['report_refresh']['status'], 'cached')

    def test_failed_refresh_retains_saved_counts_and_timestamp(self):
        before = self.seed.read_bytes()
        with patch.object(module, 'fetch_sources', side_effect=TimeoutError('timed out')):
            data = self.refresh(force=True)
        self.assertEqual(data['report_refresh']['status'], 'fallback')
        self.assertEqual(data['audit'], self.data['audit'])
        self.assertEqual(data['built_at'], self.data['built_at'])
        self.assertEqual(self.seed.read_bytes(), before)
        self.assertFalse(self.cache.exists())

    def test_malformed_download_does_not_replace_good_cache(self):
        with patch.object(module, 'fetch_sources', return_value=(self.tables, 'b'*40)):
            self.refresh(force=True)
        cached_file = next(self.cache.glob('*.json'))
        before = cached_file.read_bytes()
        bad = dict(self.tables, genoflu_results='bad')
        bad['genoflu_results.tsv'] = b'wrong\tcolumns\n'
        with patch.object(module, 'fetch_sources', return_value=(bad, 'c'*40)):
            data = self.refresh(force=True)
        self.assertEqual(data['report_refresh']['status'], 'fallback')
        self.assertEqual(data['source_commit'], 'b'*40)
        self.assertEqual(cached_file.read_bytes(), before)

    def test_offline_prefers_explicit_seed_over_newer_cache(self):
        with patch.object(module, 'fetch_sources', return_value=(self.tables, 'b'*40)):
            self.refresh(force=True)
        with patch.object(module, 'fetch_sources') as fetch:
            data = self.refresh(offline=True)
        fetch.assert_not_called()
        self.assertEqual(data['source_commit'], 'a'*40)
        self.assertEqual(data['report_refresh']['status'], 'offline')

    def test_pin_never_silently_uses_another_commit(self):
        with patch.object(module, 'fetch_sources') as fetch:
            data = self.refresh(ref='a'*40)
            with self.assertRaisesRegex(ValueError, 'matching the requested ref'):
                self.refresh(ref='c'*40, offline=True)
        fetch.assert_not_called()
        self.assertEqual(data['report_refresh']['status'], 'pinned')
        with patch.object(module, 'fetch_sources', side_effect=TimeoutError('offline')):
            with self.assertRaisesRegex(ValueError, 'no valid saved snapshot'):
                self.refresh(ref='c'*40)

    def test_invalid_seed_cannot_be_used_as_a_fallback(self):
        self.data['audit']['assigned_runs'] = 99
        module.atomic_json(self.seed, self.data)
        with patch.object(module, 'fetch_sources', side_effect=TimeoutError('offline')):
            with self.assertRaisesRegex(ValueError, 'no valid saved snapshot'):
                self.refresh()

    def test_cli_writes_report_snapshot_without_modifying_seed(self):
        before = self.seed.read_bytes()
        output = self.root/'report.json'
        self.assertEqual(module.main(['--seed', str(self.seed), '--output', str(output), '--cache-dir', str(self.cache), '--offline']), 0)
        self.assertEqual(self.seed.read_bytes(), before)
        self.assertEqual(json.loads(output.read_text())['report_refresh']['status'], 'offline')


if __name__ == '__main__':
    unittest.main()
