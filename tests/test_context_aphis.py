"""Offline APHIS acquisition tests using synthetic rows and HTTP fixtures."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import aphis_data as a
import context_setup as c
from build_surveillance_explorer import build_outbreak_context, build_payload
from test_context_setup import METADATA

HEADER = b'State,County,Collection Date,Date Detected,HPAI Strain,Bird Species,WOAH Classification,Sampling Method,Submitting Agency\n'
ROW = b'Arizona,Maricopa,09/15/2024,09/20/2024,EA H5,Canada goose,Wild bird,Found dead,Fixture agency\n'
DATA = HEADER + ROW + ROW


class Response(io.BytesIO):
    def __init__(self, data=DATA, status=200, headers=None, url=a.CSV_URL):
        super().__init__(data)
        self.status, self.url = status, url
        self.headers = headers or {'Content-Type': 'text/csv', 'Content-Length': str(len(data))}


class AphisTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.cache = self.root / 'cache'
        self.bundled = self.root / 'bundled.csv'
        self.bundled.write_bytes(DATA)
        self.old = {'sha256': a.digest(DATA), 'snapshot_supplied_date': '2024-10-01',
                    'snapshot_date_basis': 'Fixture import date'}
        a.atomic_json(self.bundled.with_suffix('.provenance.json'), self.old)
        self.network = patch.object(a, 'fetch_csv', return_value=(DATA, {'http_etag': 'fixture'})).start()
        self.addCleanup(patch.stopall)
        self.counter = 0

    def prepare(self, **kwargs):
        self.counter += 1
        self.out = self.root / ('run-' + str(self.counter))
        return a.prepare(self.out, self.cache, **{'network': True, 'bundled': self.bundled, **kwargs})

    def provenance(self):
        return json.loads((self.out / 'aphis.provenance.json').read_text())

    def test_download_retains_rows_and_records_acquisition(self):
        result = self.prepare()
        self.assertEqual(result['source_mode'], 'download')
        self.assertEqual(result['record_count'], 2)
        self.network.assert_called_once_with()
        provenance = self.provenance()
        self.assertEqual(provenance['download_url'], a.CSV_URL)
        self.assertEqual(provenance['sha256'], hashlib.sha256(DATA).hexdigest())
        self.assertEqual(provenance['snapshot_supplied_date'], provenance['retrieved_at'][:10])
        self.assertIn('not an APHIS release', provenance['snapshot_date_basis'])
        parsed = build_outbreak_context(self.out / 'aphis.csv', self.out / 'aphis.provenance.json')
        self.assertEqual(parsed['repeated_rows_retained'], 1)
        self.assertEqual(parsed['date_ranges']['collection_date']['max'], '2024-09-15')
        self.assertEqual(parsed['date_ranges']['detected_date']['max'], '2024-09-20')
        self.assertEqual(parsed['acquisition']['source_mode'], 'download')
        self.assertEqual(parsed['retrieved_at'], result['retrieved_at'])

    def test_http_403_uses_cache_and_does_not_advance_timestamp_or_pointer(self):
        first = self.prepare()
        pointer = (self.cache / 'latest.json').read_bytes()
        old_run = (self.out / 'aphis.provenance.json').read_bytes()
        old_folder = self.out
        self.network.side_effect = HTTPError(a.CSV_URL, 403, 'Forbidden', {}, None)
        result = self.prepare()
        self.assertEqual(result['source_mode'], 'cache')
        self.assertEqual(result['refresh_status'], 'failed')
        self.assertEqual(result['retrieved_at'], first['retrieved_at'])
        self.assertIn({'step': 'download', 'reason': 'http_403'}, result['issues'])
        self.assertEqual((self.cache / 'latest.json').read_bytes(), pointer)
        self.assertEqual((old_folder / 'aphis.provenance.json').read_bytes(), old_run)

    def test_offline_uses_cache_without_network(self):
        self.prepare()
        self.network.reset_mock()
        result = self.prepare(network=False)
        self.network.assert_not_called()
        self.assertEqual((result['source_mode'], result['refresh_status']), ('cache', 'offline'))

    def test_offline_uses_bundled_date_and_never_labels_it_as_retrieved(self):
        result = self.prepare(network=False)
        self.network.assert_not_called()
        self.assertEqual(result['source_mode'], 'bundled')
        self.assertEqual(result['snapshot_date'], '2024-10-01')
        self.assertIsNone(result['retrieved_at'])

    def test_failed_download_uses_bundled_then_unavailable(self):
        self.network.side_effect = TimeoutError('fixture')
        result = self.prepare()
        self.assertEqual(result['source_mode'], 'bundled')
        self.assertEqual(result['refresh_status'], 'failed')
        result = self.prepare(bundled=self.root / 'missing.csv')
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertFalse((self.out / 'aphis.csv').exists())

    def test_invalid_download_does_not_replace_valid_cache(self):
        self.prepare()
        pointer = (self.cache / 'latest.json').read_bytes()
        bad = [b'<html>Denied</html>', b'', HEADER, HEADER + b'bad,row\n',
               DATA.replace(b'State,', b'County,'), DATA.replace(b'09/15/2024', b'invalid').replace(b'09/20/2024', b'invalid')]
        for content in bad:
            with self.subTest(content=content):
                self.network.return_value = content, {}
                self.assertEqual(self.prepare()['source_mode'], 'cache')
                self.assertEqual((self.cache / 'latest.json').read_bytes(), pointer)

    def test_partial_http_read_uses_fallback(self):
        self.network.side_effect = http.client.IncompleteRead(b'partial')
        self.assertEqual(self.prepare()['source_mode'], 'bundled')

    def test_corrupt_cache_and_provenance_fall_back(self):
        for target in ('aphis.csv', 'aphis.provenance.json'):
            self.network.side_effect = None
            self.prepare()
            pointer = json.loads((self.cache / 'latest.json').read_text())
            (self.cache / pointer['snapshot_id'] / target).write_text('changed')
            self.assertEqual(self.prepare(network=False)['source_mode'], 'bundled')

    def test_cache_pointer_cannot_escape_or_follow_symlink(self):
        self.prepare()
        a.atomic_json(self.cache / 'latest.json', {'snapshot_id': '../outside'})
        self.assertEqual(self.prepare(network=False)['source_mode'], 'bundled')
        self.prepare()
        pointer = json.loads((self.cache / 'latest.json').read_text())
        path = self.cache / pointer['snapshot_id'] / 'aphis.csv'
        path.unlink(); path.symlink_to(self.bundled)
        self.assertEqual(self.prepare(network=False)['source_mode'], 'bundled')

    def test_bad_bundled_hash_is_unavailable(self):
        self.bundled.write_bytes(DATA + ROW)
        self.assertEqual(self.prepare(network=False)['status'], 'UNAVAILABLE')

    def test_manual_override_suppresses_network_and_preserves_its_provenance(self):
        result = self.prepare(override=self.bundled)
        self.network.assert_not_called()
        self.assertEqual(result['source_mode'], 'user')
        self.assertEqual(result['snapshot_date'], '2024-10-01')
        self.assertFalse(self.cache.exists())

    def test_manual_override_without_sidecar_keeps_unknown_date(self):
        self.bundled.with_suffix('.provenance.json').unlink()
        result = self.prepare(override=self.bundled)
        self.assertIsNone(result['snapshot_date'])
        self.assertIsNone(result['retrieved_at'])

    def test_invalid_explicit_override_never_falls_back(self):
        bad = self.root / 'bad.csv'; bad.write_bytes(b'bad')
        with self.assertRaises(ValueError):
            self.prepare(override=bad)
        self.network.assert_not_called()
        with self.assertRaises(OSError):
            self.prepare(override=self.root / 'missing.csv')

    def test_cache_write_failure_keeps_valid_download(self):
        with patch.object(a, 'save_cache', side_effect=PermissionError('read-only')):
            result = self.prepare()
        self.assertEqual(result['source_mode'], 'download')
        self.assertIn({'step': 'cache_write', 'reason': 'not_saved'}, result['issues'])
        self.assertEqual((self.out / 'aphis.csv').read_bytes(), DATA)

    def test_concurrent_cache_publications_remain_coherent(self):
        def prepare(index):
            return a.prepare(self.root / str(index), self.cache, network=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(prepare, (1, 2)))
        self.assertTrue(all(r['source_mode'] == 'download' for r in results))
        data, provenance, parsed = a.read_cache(self.cache)
        self.assertEqual(data, DATA)
        self.assertEqual(provenance['sha256'], a.digest(data))
        self.assertEqual(parsed['record_count'], 2)

    def test_missing_dates_retained_and_utf8_bom_supported(self):
        data = b'\xef\xbb\xbf' + DATA.replace(b'09/15/2024', b'', 1)
        self.network.return_value = data, {}
        self.prepare()
        parsed = build_outbreak_context(self.out / 'aphis.csv')
        self.assertEqual(parsed['undated_counts']['collection_date'], 1)
        self.assertEqual(parsed['record_count'], 2)

    def test_real_fetch_transport_uses_official_url_and_bounded_read(self):
        # Temporarily restore the function patched in setUp to exercise urllib.
        with patch.object(a.request, 'build_opener') as build:
            build.return_value.open.return_value = Response(headers={'Content-Type': 'text/csv', 'Last-Modified': 'fixture'})
            # Read function from a separate module namespace; no socket is opened.
            import runpy
            api = runpy.run_path(str(Path(a.__file__)))
            data, headers = api['fetch_csv']()
            req = build.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url, a.CSV_URL)
            self.assertIsNone(req.data)
            self.assertEqual(data, DATA)
            self.assertEqual(headers['http_last_modified'], 'fixture')
            self.assertEqual(build.return_value.open.call_args.kwargs['timeout'], 30)

    def test_http_errors_and_size_limits(self):
        import runpy
        api = runpy.run_path(str(Path(a.__file__)))
        for response in (Response(headers={'Content-Type': 'text/html'}), Response(status=403),
                         Response(headers={'Content-Length': str(a.MAX_BYTES + 1)}),
                         Response(headers={'Content-Length': str(len(DATA) + 1)}),
                         Response(url='https://example.com/data.csv')):
            with self.subTest(response=response), patch.object(a.request, 'build_opener') as build:
                build.return_value.open.return_value = response
                with self.assertRaises(ValueError):
                    api['fetch_csv']()

    def test_redirects_must_stay_on_official_https_host(self):
        for url in ('http://www.aphis.usda.gov/a', 'https://example.com/a', 'https://www.aphis.usda.gov@evil.test/a'):
            with self.assertRaises(ValueError):
                a.OfficialRedirect().redirect_request(None, None, 302, '', {}, url)

    def test_context_pins_artifacts_and_report_includes_mode(self):
        metadata = self.root / 'metadata.tsv'; metadata.write_text(METADATA)
        with patch.dict(os.environ, {'WINGS_CONTEXT_CACHE': str(self.cache)}):
            selection = c.prepare(metadata, self.root / 'context', {'selected_sources': ['outbreak'], 'network': True})
            self.assertEqual(selection['providers']['outbreak']['source_mode'], 'download')
            self.network.assert_called_once()
            config = c.configure({}, self.root / 'context', metadata)
            folder, _ = c.selected(self.root / 'context', metadata)
            self.assertEqual(config['outbreak_context']['csv'], str(folder / 'aphis.csv'))
            self.assertEqual(config['outbreak_context']['provenance'], str(folder / 'aphis.provenance.json'))
            payload = build_payload(folder / 'validated_metadata.tsv', [], [], context_setup=folder / 'selection.json')
            self.assertEqual(payload['context_setup']['providers']['outbreak']['source_mode'], 'download')
            self.assertNotIn(str(self.root), json.dumps(payload['context_setup']))
            (folder / 'aphis.csv').write_bytes(DATA + ROW)
            with self.assertRaisesRegex(ValueError, 'changed'):
                c.selected(self.root / 'context', metadata)

    def test_deselected_aphis_makes_no_network_request(self):
        metadata = self.root / 'metadata.tsv'; metadata.write_text(METADATA)
        selection = c.prepare(metadata, self.root / 'context', {'selected_sources': [], 'network': True})
        self.network.assert_not_called()
        self.assertEqual(selection['providers']['outbreak']['status'], 'DISABLED')


if __name__ == '__main__':
    unittest.main()
