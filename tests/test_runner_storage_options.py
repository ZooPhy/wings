"""Storage launch options, without running workflows or requiring Conda."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


def load_runner():
    spec = importlib.util.spec_from_file_location(
        'storage_runner', Path(__file__).resolve().parents[1] / 'scripts/wings_local_runner.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StorageOptionsTests(unittest.TestCase):
    def start(self, runner, arguments):
        server = Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        with patch.object(sys, 'argv', ['runner', '--no-browser', *arguments]), \
             patch.object(runner, 'ThreadingHTTPServer', return_value=server), \
             patch('builtins.print'):
            runner.main()
        server.server_close.assert_called_once()

    def test_explicit_paths_override_environment_and_reach_subprocess(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            root = Path(directory).resolve()
            os.environ['WINGS_RUNS_DIR'] = str(root / 'old-runs')
            os.environ['CONDA_PKGS_DIRS'] = str(root / 'old-cache')
            runner = load_runner()
            self.start(runner, ['--runs-dir', str(root / 'run storage'),
                                '--conda-pkgs-dir', str(root / 'package cache')])
            self.assertEqual(runner.RUNS_ROOT, root / 'run storage')
            value = subprocess.check_output(
                [sys.executable, '-c', 'import os; print(os.environ["CONDA_PKGS_DIRS"])'], text=True).strip()
            self.assertEqual(value, str(root / 'package cache'))
            self.assertFalse((root / 'old-runs').exists())
            self.assertEqual(list((root / 'package cache').iterdir()), [])

    def test_environment_defaults_preserved_and_existing_runs_reconciled(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            root = Path(directory).resolve()
            os.environ['WINGS_RUNS_DIR'] = str(root / 'runs')
            os.environ['CONDA_PKGS_DIRS'] = str(root / 'existing-cache')
            saved = root / 'runs/saved/state.json'
            saved.parent.mkdir(parents=True)
            saved.write_text('{}')
            runner = load_runner()
            with patch.object(runner, 'reconcile_state') as reconcile:
                self.start(runner, [])
            reconcile.assert_called_once_with('saved')
            self.assertEqual(saved.read_text(), '{}')
            self.assertEqual(os.environ['CONDA_PKGS_DIRS'], str(root / 'existing-cache'))

    def test_no_options_preserve_local_defaults(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop('WINGS_RUNS_DIR', None)
            os.environ.pop('CONDA_PKGS_DIRS', None)
            runner = load_runner()
            expected = Path('~/.wings/runs').expanduser().resolve()
            self.assertEqual(runner.RUNS_ROOT, expected)
            with patch.object(runner, 'RUNS_ROOT', Path(directory) / 'runs'):
                self.start(runner, [])
            self.assertNotIn('CONDA_PKGS_DIRS', os.environ)

    def test_invalid_cache_stops_before_server_starts(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            root = Path(directory)
            bad = root / 'file'
            bad.write_text('keep me')
            runner = load_runner()
            with patch.object(sys, 'argv', ['runner', '--runs-dir', str(root / 'runs'),
                                          '--conda-pkgs-dir', str(bad)]), \
                 patch.object(runner, 'ThreadingHTTPServer') as server, \
                 patch('sys.stderr'):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
            self.assertEqual(error.exception.code, 2)
            server.assert_not_called()
            self.assertEqual(bad.read_text(), 'keep me')

    def test_write_failure_stops_before_server_starts(self):
        runner = load_runner()
        with patch.object(sys, 'argv', ['runner']), \
             patch.object(runner, 'prepare_storage_directory', side_effect=PermissionError('read-only storage')), \
             patch.object(runner, 'ThreadingHTTPServer') as server, patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                runner.main()
        server.assert_not_called()


if __name__ == '__main__':
    unittest.main()
