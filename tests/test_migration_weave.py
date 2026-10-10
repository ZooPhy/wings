"""Seasonal ingestion tests use synthetic, public-format fixtures only."""
import copy
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


bird, eco = module('birdcast_data'), module('build_ecological_context')


def component(night='2025-10-02', total=60):
    return {'night': night, 'region': {'code': 'US-KY'}, 'hasNightlyData': True, 'live': False,
            'migrationLiveDataFromApi': {'regionCode': 'US-KY', 'timezoneName': 'America/New_York',
                'cumulativeBirds': total, 'nightSeries': [{'localTime': night + 'T20:00:00', 'numAloft': 300}],
                'season': {'code': 'FA', 'startDate': '20251001', 'endDate': '20251004'}},
            'migrationHistDataFromApi': {'regionCode': 'US-KY', 'generatedDt': '2025-10-05T12:00:00Z',
                'season': {'currentSeasonSeries': [
                    {'dateTime': f'2025-10-0{i}T00:00:00', 'totalBirds': n, 'numAloft': 200+i}
                    for i, n in enumerate([40, 100, 100, 200], 1)]}}}


def raw(data):
    return ('<script>window.__NUXT__=(function(a){return ' + json.dumps({'fetch': {'Region:0': data}})
            + '}(null));</script>').encode()


class SeasonalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.meta = self.root / 'metadata.tsv'
        self.meta.write_text('sample_id\tcountry\tstate\tcollection_date\n'
                             'a\tUS\tKY\t2025-10-03\nb\tUS\tKY\t2025-10-03\n')
        self.calls = []

    def build(self, data=None, **kwargs):
        def opener(url, timeout):
            self.calls.append(url)
            return io.BytesIO(raw(component() if data is None else data))
        return eco.build_snapshot(self.meta, self.root / 'cache', opener=opener, **kwargs)

    def test_cumulative_semantics_and_aloft_separation(self):
        season = bird.normalize_season(component(), 'KY', '2025-10-02', 60)
        self.assertEqual([r['cumulative_birds'] for r in season['rows']], [40, 100, 100, 200])
        self.assertEqual(season['rows'][1]['mean_birds_aloft'], 202)
        self.assertEqual(season['metric'], 'cumulative_birds_crossed')

    def test_source_metric_drift_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            bird.normalize_season(component(), 'KY', '2025-10-02', 6000)

    def test_rounding_and_zero_night(self):
        bird.normalize_season(component(), 'KY', '2025-10-02', 59)
        bird.normalize_season(component('2025-10-03', 0), 'KY', '2025-10-03', 0)

    def test_gaps_retained_without_interpolation(self):
        data = component()
        del data['migrationHistDataFromApi']['season']['currentSeasonSeries'][1]
        season = bird.normalize_season(data, 'KY', '2025-10-02', 60)
        self.assertEqual([r['date'] for r in season['rows']], ['2025-10-01', '2025-10-03', '2025-10-04'])

    def test_invalid_region_dates_and_counts(self):
        mutations = [
            lambda d: d['migrationHistDataFromApi'].update(regionCode='US-AZ'),
            lambda d: d['migrationHistDataFromApi']['season']['currentSeasonSeries'][1].update(dateTime='2025-10-01T00:00:00'),
            lambda d: d['migrationHistDataFromApi']['season']['currentSeasonSeries'][1].update(totalBirds=39),
            lambda d: d['migrationHistDataFromApi']['season']['currentSeasonSeries'][1].update(totalBirds=True),
            lambda d: d['migrationHistDataFromApi']['season']['currentSeasonSeries'][1].update(totalBirds=float('nan')),
            lambda d: d['migrationHistDataFromApi']['season']['currentSeasonSeries'][1].update(dateTime='2025-10-02T05:00:00'),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                data = component(); mutation(data)
                with self.assertRaises(ValueError):
                    bird.normalize_season(data, 'KY', '2025-10-02', 60)

    def test_fetch_dedup_and_offline_snapshot_round_trip(self):
        result = self.build(fetch_birdcast=True)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(result['birdcast']['seasons']), 1)
        self.assertNotIn('seasonal_context', result['birdcast']['records'][0])
        self.calls.clear()
        offline = self.build(birdcast_cache=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(result['birdcast'], offline['birdcast'])
        p = self.root / 'snapshot.json'; eco.write_json(p, result)
        self.assertEqual(eco.load_snapshot(p, eco.read_metadata(self.meta))['birdcast']['seasons'], result['birdcast']['seasons'])
        result['birdcast']['seasons'][0]['rows'][1]['cumulative_birds'] = -1
        eco.write_json(p, result)
        with self.assertRaises(ValueError):
            eco.load_snapshot(p, eco.read_metadata(self.meta))

    def test_legacy_cache_upgraded_once_and_retained_offline(self):
        self.build(fetch_birdcast=True)
        target = next((self.root / 'cache/birdcast').glob('*.json'))
        legacy = json.loads(target.read_text()); legacy.pop('seasonal_schema')
        legacy['record'].pop('seasonal_context');legacy['record'].pop('seasonal_reason')
        legacy['record_sha256'] = eco.digest(json.dumps(legacy['record'], sort_keys=True, allow_nan=False).encode())
        eco.write_json(target, legacy)
        self.calls.clear()
        offline = self.build(birdcast_cache=True)
        self.assertEqual(offline['birdcast']['seasons'], [])
        self.assertEqual(offline['birdcast']['records'][0]['birds_crossed'], 60)
        self.assertEqual(self.calls, [])
        upgraded = self.build(fetch_birdcast=True)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(upgraded['birdcast']['seasons']), 1)
        self.build(fetch_birdcast=True)
        self.assertEqual(len(self.calls), 1)

    def test_failed_upgrade_keeps_valid_nightly_cache(self):
        self.build(fetch_birdcast=True)
        target = next((self.root / 'cache/birdcast').glob('*.json'))
        legacy = json.loads(target.read_text());legacy.pop('seasonal_schema')
        legacy['record'].pop('seasonal_context')
        legacy['record_sha256'] = eco.digest(json.dumps(legacy['record'], sort_keys=True, allow_nan=False).encode())
        eco.write_json(target, legacy)
        def failed(url, timeout):
            raise OSError('No connection')
        result = eco.build_snapshot(self.meta, self.root / 'cache', fetch_birdcast=True, opener=failed)
        self.assertEqual(result['birdcast']['records'][0]['status'], 'AVAILABLE')
        self.assertEqual(result['birdcast']['records'][0]['birds_crossed'], 60)
        self.assertIn('upgrade failed', result['birdcast']['records'][0]['seasonal_reason'])

    def test_season_failure_keeps_nightly_total(self):
        data = component();data['migrationHistDataFromApi']['regionCode'] = 'US-AZ'
        result = self.build(data, fetch_birdcast=True)
        self.assertEqual(result['birdcast']['records'][0]['birds_crossed'], 60)
        self.assertEqual(result['birdcast']['seasons'], [])

    def test_empty_winter_payload_stays_unavailable(self):
        data = component();data['hasNightlyData'] = False
        data['migrationLiveDataFromApi'].update(timezoneName=None, nightSeries=[], cumulativeBirds=0, season=None)
        result = self.build(data, fetch_birdcast=True)
        r = result['birdcast']['records'][0]
        self.assertEqual(r['status'], 'UNAVAILABLE');self.assertIsNone(r['birds_crossed'])
        self.assertIn('no nightly observations', r['reason'])

    def test_one_coherent_season_chosen_without_splicing_revisions(self):
        season = bird.normalize_season(component(), 'KY', '2025-10-02', 60)
        a = {'seasonal_context': season, 'retrieved_at': '2025-10-05T00:00:00Z', 'source_url': 'first'}
        b = copy.deepcopy(a); b['retrieved_at'] = '2025-10-06T00:00:00Z';b['source_url'] = 'second'
        b['seasonal_context']['rows'][0]['cumulative_birds'] = 42
        chosen = bird.collect_seasons([a,b])
        self.assertEqual(len(chosen), 1);self.assertEqual(chosen[0]['source_url'], 'second')
        self.assertEqual(chosen[0]['rows'][0]['cumulative_birds'], 42)


if __name__ == '__main__':
    unittest.main()
