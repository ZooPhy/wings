"""Synthetic fixtures only; no live service or authentication is required."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


bird = module('birdcast_data')
eco = module('build_ecological_context')


def page(total=42, night='2026-10-08', state='US-AZ', live=False):
    value = {'fetch': {'Region:0': {'night': night, 'region': {'code': state}, 'live': live,
             'hasNightlyData': True, 'migrationLiveDataFromApi': {
                 'regionCode': state, 'timezoneName': 'America/Phoenix', 'cumulativeBirds': total,
                 'nightSeries': [{'localTime': night + 'T20:00:00', 'numAloft': 100}]}}}}
    return ('<script>window.__NUXT__=(function(a){return ' + json.dumps(value) + '}(null));</script>').encode()


class BirdCastTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.meta = self.root / 'metadata.tsv'
        self.meta.write_text('sample_id\tcountry\tstate\tcollection_date\n'
                             'a\tUS\tArizona\t2026-10-09\n'
                             'b\tUS\tAZ\t2026-10-09\n'
                             'c\tUS\tAZ\tUnknown\n'
                             'd\tCA\tAZ\t2026-10-09\n')
        self.calls = []

    def opener(self, url, timeout):
        self.calls.append(url)
        return io.BytesIO(page())

    def build(self, **kwargs):
        return eco.build_snapshot(self.meta, self.root / 'cache', opener=self.opener, **kwargs)

    def test_metadata_deduplication_preceding_night_and_offline_replay(self):
        result = self.build(fetch_birdcast=True)
        self.assertEqual(self.calls, ['https://dashboard.birdcast.org/region/US-AZ?night=2026-10-08'])
        b = result['birdcast']
        self.assertEqual(b['records'][0]['birds_crossed'], 42)
        self.assertEqual(b['bindings']['a']['night'], '2026-10-08')
        self.assertEqual(b['bindings']['c']['status'], 'MISSING_DATE')
        self.assertEqual(b['bindings']['d']['status'], 'UNSUPPORTED_LOCATION')
        self.calls.clear()
        again = self.build(birdcast_cache=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(again['birdcast']['records'], b['records'])
        snapshot = self.root / 'snapshot.json'
        eco.write_json(snapshot, result)
        self.assertEqual(eco.load_snapshot(snapshot, eco.read_metadata(self.meta))['birdcast']['records'], b['records'])

    def test_zero_is_available_and_null_is_not(self):
        self.assertEqual(bird.normalize_page(page(0), 'AZ', '2026-10-08')['birds_crossed'], 0)
        for value in (None, -1, True):
            with self.assertRaises(ValueError):
                bird.normalize_page(page(value), 'AZ', '2026-10-08')

    def test_mismatched_dates_regions_and_live_nights_rejected(self):
        for raw in (page(night='2026-10-07'), page(state='US-CA'), page(live=True)):
            with self.assertRaises(ValueError):
                bird.normalize_page(raw, 'AZ', '2026-10-08')

    def test_no_execution_of_javascript(self):
        for expression in ('process.exit()', 'fetch("https://example.org")', 'new Function("return 1")()', '1+2'):
            with self.assertRaises(ValueError):
                bird.LiteralReader(expression).complete()

    def test_shared_literal_aliases(self):
        raw = page().decode().replace('function(a){return', 'function(a){a.x=42;return').replace('}(null)', '}({})')
        self.assertEqual(bird.normalize_page(raw.encode(), 'AZ', '2026-10-08')['birds_crossed'], 42)

    def test_fetch_failure_deduplicated_and_retryable(self):
        def failed(url, timeout):
            self.calls.append(url)
            raise OSError('offline')
        result = eco.build_snapshot(self.meta, self.root / 'cache', fetch_birdcast=True, opener=failed)
        self.assertEqual(len(self.calls), 1)
        record = result['birdcast']['records'][0]
        self.assertEqual(record['status'], 'UNAVAILABLE')
        self.assertIsNone(record['birds_crossed'])
        snapshot = self.root / 'snapshot.json'
        eco.write_json(snapshot, result)
        eco.load_snapshot(snapshot, eco.read_metadata(self.meta))
        self.assertEqual(self.build(fetch_birdcast=True)['birdcast']['records'][0]['status'], 'AVAILABLE')

    def test_cache_tampering_is_unavailable(self):
        self.build(fetch_birdcast=True)
        cache = next((self.root / 'cache/birdcast').glob('*.json'))
        value = json.loads(cache.read_text())
        value['record']['birds_crossed'] = 999
        cache.write_text(json.dumps(value))
        self.assertEqual(self.build(birdcast_cache=True)['birdcast']['records'][0]['status'], 'UNAVAILABLE')
        self.assertEqual(self.build(fetch_birdcast=True, refresh_birdcast=True)['birdcast']['records'][0]['status'], 'AVAILABLE')

    def test_stale_metadata_binding_is_rejected(self):
        result = self.build(fetch_birdcast=True)
        snapshot = self.root / 'snapshot.json'
        eco.write_json(snapshot, result)
        samples = eco.read_metadata(self.meta)
        samples[0]['collection_date'] = '2026-10-10'
        result = eco.load_snapshot(snapshot, samples)
        self.assertEqual(result['birdcast']['bindings']['a']['status'], 'STALE_METADATA')

    def test_same_evening_offset(self):
        def opened(url, timeout):
            self.assertIn('night=2026-10-09', url)
            return io.BytesIO(page(night='2026-10-09'))
        result = eco.build_snapshot(self.meta, self.root / 'cache', fetch_birdcast=True,
                                    birdcast_night_offset=0, opener=opened)
        self.assertEqual(result['birdcast']['bindings']['a']['night'], '2026-10-09')


if __name__ == '__main__':
    unittest.main()
