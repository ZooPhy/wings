"""Storage API and saved-run isolation; no Conda, models or workflow execution."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch, Mock

from test_runner_storage_options import load_runner


class BrowserStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.runner = load_runner()
        self.runner.RUNS_ROOT = self.runner.prepare_storage_directory(str(self.root / 'original'))

    def settings(self, name='project'):
        return {'runs_dir': str(self.root / name), 'conda_pkgs_dir': str(self.root / 'packages'),
                'storage_revision': self.runner.STORAGE_REVISION}

    def test_switch_preserves_existing_state_and_rejects_stale_tab(self):
        runner = self.runner
        (runner.RUNS_ROOT / 'existing').mkdir()
        runner.write_state('existing', {'status': 'running'})
        old = runner.state_path('existing')
        request = self.settings()
        result = runner.update_storage(request)
        self.assertEqual(result['runs_root'], str(self.root / 'project'))
        self.assertEqual(runner.state_path('existing'), old)
        runner.write_state('existing', {'status': 'complete'})
        self.assertEqual(json.loads(old.read_text())['status'], 'complete')
        with self.assertRaisesRegex(ValueError, 'changed'):
            runner.update_storage(request)

    def test_invalid_path_does_not_change_settings(self):
        runner = self.runner
        before = runner.storage_settings()
        for value in ('relative/path', '', 22):
            request = self.settings()
            request['runs_dir'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.update_storage(request)
        file = self.root / 'not-a-directory'
        file.write_text('preserved')
        request = self.settings()
        request['conda_pkgs_dir'] = str(file)
        with self.assertRaises(OSError):
            runner.update_storage(request)
        self.assertEqual(runner.storage_settings()['storage_revision'], before['storage_revision'])
        self.assertEqual(runner.RUNS_ROOT, Path(before['runs_root']))

    def test_duplicate_saved_id_cannot_redirect_run(self):
        runner = self.runner
        (runner.RUNS_ROOT / 'same').mkdir()
        runner.write_state('same', {'status': 'failed'})
        duplicate = self.root / 'duplicate/same'
        duplicate.mkdir(parents=True)
        (duplicate / 'state.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'also exists'):
            runner.update_storage(self.settings('duplicate'))

    def test_api_new_run_snapshot_and_stale_start(self):
        runner = self.runner
        server = runner.ThreadingHTTPServer(('127.0.0.1', 0), runner.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def stop():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(stop)
        origin = f'http://127.0.0.1:{server.server_port}'
        def request(path, data=None, extra=None):
            headers = {'Content-Type': 'application/json', **(extra or {})}
            req = Request(origin + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
            with urlopen(req, timeout=5) as response:
                return json.load(response)
        with patch.object(runner.Handler, 'log_message'):
            first = request('/api/storage', self.settings())
            with self.assertRaises(HTTPError) as error:
                request('/api/storage', self.settings('evil'), {'Origin': 'https://other.example'})
            self.assertEqual(error.exception.code, 403)
            run = request('/api/runs', {'name': 'test', 'storage_revision': first['storage_revision']})
            saved = runner.read_state(run['run_id'])
            self.assertEqual(saved['conda_pkgs_dirs'], str(self.root / 'packages'))
            original_directory = runner.run_dir(run['run_id'])
            second_request = self.settings('another-project')
            second_request['conda_pkgs_dir'] = str(self.root / 'other-packages')
            request('/api/storage', second_request)
            self.assertEqual(runner.run_dir(run['run_id']), original_directory)
            self.assertEqual(request('/api/health')['conda_pkgs_dir'], str(self.root / 'other-packages'))
            with self.assertRaises(HTTPError):
                request('/api/runs', {'storage_revision': first['storage_revision']})
            # Capture the real launch environment, without starting any analysis.
            config = original_directory / 'execution_config.yaml'
            config.write_text('{}')
            process = Mock(pid=123)
            def wait(run_id, proc, handle):
                handle.close()
            with patch.object(runner, 'runtime_preflight', return_value='/tools/snakemake'), \
                 patch.object(runner, 'require_docker'), \
                 patch.object(runner, 'build_config', return_value=(config, 1)), \
                 patch.object(runner, 'capture_attempt_provenance'), \
                 patch.object(runner, 'wait_for_process', side_effect=wait), \
                 patch.object(runner.subprocess, 'Popen', return_value=process) as popen:
                runner.capture_attempt_provenance.side_effect = lambda d, *args: d / 'provenance.json'
                request(f"/api/runs/{run['run_id']}/start", {})
            self.assertEqual(popen.call_args.kwargs['env']['CONDA_PKGS_DIRS'], str(self.root / 'packages'))


if __name__ == '__main__':
    unittest.main()
