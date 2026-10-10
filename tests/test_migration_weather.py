"""Weather layer ingestion and backwards-compatibility checks; no network."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('weather_ecology', ROOT / 'scripts/build_ecological_context.py')
eco = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eco)


def response(extended=True):
    value = {'latitude': 38.5, 'longitude': -84.5, 'timezone': 'America/New_York',
             'daily_units': dict(eco.WEATHER_FIELDS), 'daily': {
                 'time': ['2025-10-26', '2025-10-27', '2025-10-28'],
                 'temperature_2m_mean': [-2, None, 12], 'precipitation_sum': [0, None, 3],
                 'wind_speed_10m_max': [10, None, 20]}}
    if extended:
        value['daily_units'].update(eco.WEATHER_EXTRA_FIELDS)
        value['daily'].update(temperature_2m_min=[-5, None, 9], temperature_2m_max=[1, None, 16], weather_code=[0, None, 63])
    return value


class WeatherLayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.cache = self.root / 'cache'
        self.meta = self.root / 'meta.tsv'
        self.meta.write_text('sample_id\tcountry\tstate\tcollection_date\tlatitude\tlongitude\n'
                             'a\tUS\tKY\t2025-10-27\t38.49\t-84.58\n'
                             'b\tUS\tKY\t2025-10-27\t38.49\t-84.58\n')
        self.row = eco.sample_metadata(eco.read_metadata(self.meta)[0])
        self.calls = []

    def opener(self, url, timeout):
        self.calls.append(url)
        return io.BytesIO(json.dumps(response()).encode())

    def legacy_cache(self):
        url, _, _ = eco.weather_request(self.row, 7, extended=False)
        raw = json.dumps(response(False)).encode()
        path = self.cache / 'weather' / (eco.digest(url.encode()) + '.json')
        eco.write_json(path, {'request_url': url, 'raw': raw.decode(), 'raw_sha256': eco.digest(raw), 'retrieved_at': 'fixture'})
        return path

    def test_request_extended_fields_units_and_cache_identity(self):
        rich = eco.weather_request(self.row, 30)[0]
        old = eco.weather_request(self.row, 30, extended=False)[0]
        query = parse_qs(urlsplit(rich).query)
        self.assertEqual(set(query['daily'][0].split(',')), set(eco.ALL_WEATHER_FIELDS))
        self.assertEqual(query['models'], ['era5']);self.assertNotEqual(eco.digest(rich.encode()), eco.digest(old.encode()))
        self.assertNotIn('sample_id', query)

    def test_extended_values_zero_and_missing_round_trip(self):
        result = eco.build_snapshot(self.meta, self.cache, fetch_weather=True, opener=self.opener)
        self.assertEqual(len(self.calls), 1)
        context = next(iter(result['weather'].values()))
        self.assertEqual(context['rows'][0]['weather_code'], 0)
        self.assertEqual(context['rows'][0]['temperature_2m_min'], -5)
        self.assertIsNone(context['rows'][1]['weather_code'])
        self.assertEqual(context['units']['weather_code'], 'wmo code')
        self.calls.clear()
        self.assertEqual(eco.build_snapshot(self.meta, self.cache, opener=self.opener)['weather'], result['weather'])
        self.assertEqual(self.calls, [])
        p = self.root / 'snapshot.json';eco.write_json(p, result)
        self.assertEqual(eco.load_snapshot(p, eco.read_metadata(self.meta))['weather'], result['weather'])

    def test_old_cache_and_snapshot_remain_usable_offline_at_wider_window(self):
        self.legacy_cache()
        result = eco.build_snapshot(self.meta, self.cache, days=90, opener=self.opener)
        self.assertEqual(self.calls, []);self.assertEqual(result['bindings']['a']['status'], 'READY')
        context = next(iter(result['weather'].values()))
        self.assertEqual(context['units'], eco.WEATHER_FIELDS)
        self.assertNotIn('weather_code', context['rows'][0])
        p = self.root / 'old.json';eco.write_json(p, result)
        self.assertEqual(eco.load_snapshot(p, eco.read_metadata(self.meta))['bindings']['a']['status'], 'READY')

    def test_online_upgrade_keeps_original_cache_and_is_reused(self):
        old = self.legacy_cache();before = old.read_bytes()
        result = eco.build_snapshot(self.meta, self.cache, fetch_weather=True, opener=self.opener)
        self.assertEqual(len(self.calls), 1);self.assertEqual(old.read_bytes(), before)
        self.assertEqual(len(list((self.cache / 'weather').glob('*.json'))), 2)
        self.assertIn('weather_code', next(iter(result['weather'].values()))['units'])
        eco.build_snapshot(self.meta, self.cache, fetch_weather=True, opener=self.opener)
        self.assertEqual(len(self.calls), 1)

    def test_failed_upgrade_deduplicates_request_and_keeps_legacy_values(self):
        self.legacy_cache()
        def failed(url, timeout):
            self.calls.append(url);raise OSError('network unavailable')
        result = eco.build_snapshot(self.meta, self.cache, fetch_weather=True, opener=failed)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(all(b['status'] == 'READY' for b in result['bindings'].values()))
        self.assertEqual(next(iter(result['weather'].values()))['rows'][0]['temperature_2m_mean'], -2)

    def test_other_coordinates_and_corrupted_fallback_are_never_borrowed(self):
        p = self.legacy_cache()
        other = {**self.row, 'latitude': 33.45}
        self.assertIsNone(eco.fallback_weather(self.cache, eco.weather_request(other, 30)[0]))
        payload = json.loads(p.read_text());payload['raw'] += ' ';eco.write_json(p, payload)
        self.assertIsNone(eco.fallback_weather(self.cache, eco.weather_request(self.row, 30)[0]))

    def test_bad_extended_fields_fail_validation(self):
        url = eco.weather_request(self.row, 30)[0]
        mutations = [lambda d:d['daily_units'].update(temperature_2m_min='°F'),
                     lambda d:d['daily']['temperature_2m_max'].pop(),
                     lambda d:d['daily']['temperature_2m_min'].__setitem__(0, 8),
                     lambda d:d['daily']['weather_code'].__setitem__(0, True),
                     lambda d:d['daily']['weather_code'].__setitem__(0, 1.5),
                     lambda d:d['daily']['weather_code'].__setitem__(0, 100),
                     lambda d:d['daily']['time'].__setitem__(0, '2020-01-01')]
        for mutate in mutations:
            value = response();mutate(value)
            with self.assertRaises(ValueError):eco.normalize_weather(json.dumps(value).encode(), url, 'fixture')
        with self.assertRaises(ValueError):eco.normalize_weather(json.dumps(response(False)).encode(), url, 'fixture')

    def test_snapshot_validation_rejects_bad_minmax_and_undeclared_codes(self):
        result = eco.build_snapshot(self.meta, self.cache, fetch_weather=True, opener=self.opener)
        p = self.root / 'snapshot.json'
        for mutate in [lambda c:c['rows'][0].update(temperature_2m_max=-20),lambda c:c['units'].pop('weather_code')]:
            value = copy.deepcopy(result);mutate(next(iter(value['weather'].values())));eco.write_json(p, value)
            with self.assertRaises(ValueError):eco.load_snapshot(p, eco.read_metadata(self.meta))


if __name__ == '__main__':unittest.main()
