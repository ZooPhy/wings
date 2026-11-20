"""Offline regression tests for NCBI transport retries and snapshot integrity."""
import contextlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

SPEC = importlib.util.spec_from_file_location(
    'reference_retries_under_test',
    Path(__file__).resolve().parents[1] / 'scripts/phylodynamic_references.py')
refs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refs)


def response(body):
    result = Mock()
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    if isinstance(body, Exception):
        result.read.side_effect = body
    else:
        result.read.return_value = body
    return result


def genbank(accession):
    return (f'<GBSet><GBSeq><GBSeq_accession-version>{accession}'
            f'</GBSeq_accession-version><GBSeq_sequence>acgt</GBSeq_sequence>'
            f'</GBSeq></GBSet>').encode()


class ReferenceRetryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {'NCBI_EMAIL': 'private@example.org',
                                                  'NCBI_API_KEY': 'private-key'}))
        self.sleep = self.enterContext(patch.object(refs.time, 'sleep'))
        self.enterContext(patch.object(refs.time, 'monotonic', return_value=100.0))
        self.open = self.enterContext(patch.object(refs.urllib.request, 'urlopen'))
        self.stderr = self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.cfg = dict(refs.REFERENCE_DEFAULTS)
        self.client = refs.NCBI(self.cfg)

    def test_incomplete_read_restarts_request_and_discards_partial_bytes(self):
        broken = response(http.client.IncompleteRead(b'partial-secret', 500))
        complete = response(b'complete-response')
        self.open.side_effect = [broken, complete]
        self.assertEqual(self.client.request('efetch', {'id': 'AB123.1'}), b'complete-response')
        broken.__exit__.assert_called_once()
        complete.__exit__.assert_called_once()
        first, second = [c.args[0] for c in self.open.call_args_list]
        self.assertEqual(first.data, second.data)
        self.assertEqual(first.full_url, second.full_url)
        self.assertTrue(all(c.kwargs['timeout'] == 90 for c in self.open.call_args_list))
        self.assertIn('attempt 2/5', self.stderr.getvalue())
        for secret in ('private@example.org', 'private-key', 'partial-secret', 'AB123.1'):
            self.assertNotIn(secret, self.stderr.getvalue())

    def test_retry_budget_and_backoff_stop_after_five_attempts(self):
        self.open.side_effect = [response(http.client.IncompleteRead(b'partial')) for _ in range(5)]
        with self.assertRaisesRegex(RuntimeError, 'five attempts.*cached completed batches'):
            self.client.request('efetch', {})
        self.assertEqual(self.open.call_count, 5)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list if c.args[0] >= 1], [1, 2, 4, 8])
        self.assertEqual(len(self.stderr.getvalue().splitlines()), 4)

    def test_other_transient_transport_errors_retry(self):
        for error in (ConnectionResetError('reset'), BrokenPipeError('pipe'),
                      http.client.RemoteDisconnected('closed'), TimeoutError('timeout'),
                      urllib.error.URLError('temporary')):
            with self.subTest(error=type(error).__name__):
                self.open.reset_mock()
                self.open.side_effect = [error, response(b'ok')]
                self.assertEqual(self.client.request('efetch', {}), b'ok')
                self.assertEqual(self.open.call_count, 2)

    def test_retryable_http_statuses_preserve_retry_after_cap(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                self.sleep.reset_mock()
                self.open.side_effect = [urllib.error.HTTPError(
                    'https://example.org/?api_key=private-key', status, 'temporary',
                    {'Retry-After': '120'}, None), response(b'ok')]
                self.assertEqual(self.client.request('efetch', {}), b'ok')
                self.assertIn(unittest.mock.call(30), self.sleep.call_args_list)

    def test_permanent_http_error_fails_without_retry_or_credential_leak(self):
        self.open.side_effect = urllib.error.HTTPError(
            'https://example.org/?api_key=private-key', 400, 'private-key', {}, None)
        with self.assertRaisesRegex(RuntimeError, 'NCBI HTTP 400') as caught:
            self.client.request('efetch', {})
        self.assertEqual(self.open.call_count, 1)
        self.assertNotIn('private-key', str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(self.stderr.getvalue(), '')

    def test_offline_and_missing_email_never_attempt_network(self):
        for cfg, email in ((dict(self.cfg, offline=True), 'contact'), (self.cfg, '')):
            client = refs.NCBI(cfg)
            client.email = email
            with self.assertRaises(ValueError):
                client.request('efetch', {})
        self.open.assert_not_called()

    def test_nontransport_error_is_not_retried(self):
        self.open.side_effect = ValueError('programming error')
        with self.assertRaisesRegex(ValueError, 'programming error'):
            self.client.request('efetch', {})
        self.assertEqual(self.open.call_count, 1)

    def snapshot(self, root):
        cfg = dict(self.cfg, cache_dir=str(root), batch_size=1)
        scope = dict(subtypes=['H5'], segments=['HA'])
        query = refs.query_for(scope)
        folder = root / cfg['snapshot'] / refs.sha(query.encode())[:20]
        ids = ['AB123.1', 'AB124.1']
        refs.save(folder / 'accessions.json', dict(query=query, accessions=ids,
            count=len(ids), accessions_sha256=refs.sha('\n'.join(ids).encode())))
        key = refs.sha(ids[0].encode())
        data = genbank(ids[0])
        refs.atomic(folder / (key + '.xml'), data)
        refs.save(folder / (key + '.json'), dict(sha256=refs.sha(data), accessions=[ids[0]]))
        return cfg, scope, folder, ids

    def test_exhaustion_keeps_completed_cache_and_does_not_cache_partial_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, scope, folder, ids = self.snapshot(Path(tmp))
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            self.open.side_effect = [response(http.client.IncompleteRead(b'partial')) for _ in range(5)]
            records = refs.remote_records(scope, cfg)
            self.assertEqual(next(records)[0]['accession'], ids[0])
            with self.assertRaises(RuntimeError):
                list(records)
            self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)

    def test_recovered_batch_is_validated_cached_and_reusable_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, scope, folder, ids = self.snapshot(Path(tmp))
            data = genbank(ids[1])
            self.open.side_effect = [response(http.client.IncompleteRead(b'partial')), response(data)]
            records = list(refs.remote_records(scope, cfg))
            self.assertEqual([r['accession'] for r, seq in records], ids)
            key = refs.sha(ids[1].encode())
            self.assertEqual((folder / (key + '.xml')).read_bytes(), data)
            self.assertEqual(json.loads((folder / (key + '.json')).read_text())['sha256'], refs.sha(data))
            self.open.reset_mock()
            self.assertEqual(list(refs.remote_records(scope, dict(cfg, offline=True))), records)
            self.open.assert_not_called()

    def test_complete_but_invalid_response_is_not_cached_or_silently_retried(self):
        for data in (b'<truncated', genbank('WRONG999.1')):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as tmp:
                cfg, scope, folder, ids = self.snapshot(Path(tmp))
                before = {p.name: p.read_bytes() for p in folder.iterdir()}
                self.open.reset_mock()
                self.open.side_effect = [response(data)]
                with self.assertRaises((refs.ET.ParseError, ValueError)):
                    list(refs.remote_records(scope, cfg))
                self.assertEqual(self.open.call_count, 1)
                self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)


if __name__ == '__main__':
    unittest.main()
