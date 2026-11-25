"""Storage contract tests; real Docker Desktop extraction remains a release check."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).parent))
import test_launcher
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'desktop/runtime'))
spec = importlib.util.spec_from_file_location('volume_controller', ROOT / 'desktop/runtime/controller.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def runner_functions():
    tree = ast.parse((ROOT / 'scripts/wings_local_runner.py').read_text())
    names = {'managed_conda_cache', 'prepare_conda_cache', 'apply_run_conda_cache'}
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = dict(os=os, Path=Path, tempfile=tempfile, prepare_storage_directory=lambda value: Path(value))
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<actual runner cache functions>', 'exec'), scope)
    return scope


class VolumeLauncherTests(unittest.TestCase):
    def setUp(self):
        self.launcher = test_launcher.LauncherTests()
        self.launcher.setUp()
        self.addCleanup(self.launcher.tearDown)
        self.state = self.launcher.root / 'docker-state.json'
        self.wid = hashlib.sha256(str(self.launcher.workspace.resolve()).encode()).hexdigest()[:16]

    def data(self):
        return json.loads(self.state.read_text())

    def test_fresh_launch_uses_two_volumes_and_keeps_legacy_cache(self):
        old = self.launcher.workspace / 'cache/conda-envs-v2/existing'
        old.parent.mkdir(parents=True); old.write_text('preserve')
        result = self.launcher.command()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.data()['volumes']), 2)
        for command in self.data()['calls']:
            if 'run' not in command: continue
            for kind, target in [('envs', 'envs'), ('pkgs', 'pkgs')]:
                self.assertIn(f'type=volume,source=wings-conda-{kind}-v3-{self.wid},target=/opt/wings-conda-{target},volume-nocopy', command)
            self.assertFalse(any('type=bind,source=' in a and 'target=/opt/wings-conda' in a for a in command))
        self.assertEqual(old.read_text(), 'preserve')
        self.assertEqual(self.launcher.command('stop').returncode, 0)
        self.assertEqual(self.launcher.command().returncode, 0)
        creates = [c for c in self.data()['calls'] if 'volume' in c and 'create' in c]
        self.assertEqual(len(creates), 2)

    def test_foreign_volume_stops_before_controller_or_deletion(self):
        self.state.write_text(json.dumps({'calls': [], 'volumes': {
            'wings-conda-envs-v3-' + self.wid: 'local|null|other-workspace|envs-v3'}}))
        result = self.launcher.command()
        self.assertEqual(result.returncode, 22)
        self.assertNotIn('container', self.data())
        self.assertFalse(any('rm' in c for c in self.data()['calls']))

    def test_volume_failure_and_case_check_failure_prevent_service(self):
        for key in ['MOCK_VOLUME_CREATE_FAIL', 'MOCK_CONDA_CHECK_FAIL']:
            with self.subTest(key=key):
                self.launcher.env[key] = '1'
                result = self.launcher.command()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('container', self.data())
                self.launcher.env.pop(key)


class SymlinkWorkspaceLauncherTests(VolumeLauncherTests):
    """Exercise path normalization even on hosts without macOS /var aliases."""
    def setUp(self):
        super().setUp()
        physical = self.launcher.root / 'physical workspace'
        physical.mkdir()
        self.launcher.workspace.symlink_to(physical, target_is_directory=True)
        self.wid = hashlib.sha256(str(self.launcher.workspace.resolve()).encode()).hexdigest()[:16]


class CaseCheckTests(unittest.TestCase):
    def test_native_filesystem_probe_preserves_files_and_enforces_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'keep'; marker.write_text('data')
            # Determine the host's semantics independently of the controller.
            lower, upper = Path(tmp) / 'host-test-a', Path(tmp) / 'HOST-TEST-A'
            lower.write_bytes(b'host')
            aliases = upper.exists() and lower.samefile(upper)
            lower.unlink()
            if aliases:
                with self.assertRaisesRegex(RuntimeError, 'case-insensitive'):
                    controller.check_case_sensitive_directory(tmp)
            else:
                controller.check_case_sensitive_directory(tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [marker])
            self.assertEqual(marker.read_text(), 'data')

    def test_distinct_case_names_are_accepted_and_probe_cleaned(self):
        # Model a case-sensitive directory on either Linux or the default Mac FS.
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'keep'; marker.write_text('data')
            original = Path.open
            def distinct(path, *args, **kwargs):
                names = {'probea': 'distinct-lower', 'probeA': 'distinct-upper'}
                if path.name in names: path = path.with_name(names[path.name])
                return original(path, *args, **kwargs)
            with patch.object(Path, 'open', distinct):
                controller.check_case_sensitive_directory(tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [marker])

    def test_aliasing_filesystem_is_rejected_and_probe_cleaned(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path.open
            def alias(path, *args, **kwargs):
                if path.name == 'probeA': path = path.with_name('probea')
                return original(path, *args, **kwargs)
            with patch.object(Path, 'open', alias), self.assertRaisesRegex(RuntimeError, 'case-insensitive'):
                controller.check_case_sensitive_directory(tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_controller_checks_both_destinations_and_sets_package_cache(self):
        # This tests orchestration; the filesystem probe is covered separately.
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'WINGS_DESKTOP_CONDA_PREFIX': tmp + '/envs', 'WINGS_DESKTOP_CONDA_PKGS_DIR': tmp + '/pkgs'}), \
                patch.object(controller, 'check_case_sensitive_directory') as check:
            self.assertEqual(controller.prepare_conda_storage(), tmp + '/pkgs')
            self.assertEqual(check.call_args_list, [call(tmp + '/envs'), call(tmp + '/pkgs')])
            self.assertEqual(os.environ['CONDA_PKGS_DIRS'], tmp + '/pkgs')

    def test_controller_does_not_publish_cache_after_either_probe_fails(self):
        for failure in [0, 1]:
            with self.subTest(failure=failure), patch.dict(os.environ, {
                'WINGS_DESKTOP_CONDA_PREFIX': '/fixture/envs',
                'WINGS_DESKTOP_CONDA_PKGS_DIR': '/fixture/pkgs',
                'CONDA_PKGS_DIRS': '/previous-cache'}), \
                    patch.object(controller, 'check_case_sensitive_directory',
                                 side_effect=[None] * failure + [RuntimeError('case-insensitive')]) as check:
                with self.assertRaisesRegex(RuntimeError, 'case-insensitive'):
                    controller.prepare_conda_storage()
                self.assertEqual(check.call_count, failure + 1)
                self.assertEqual(os.environ['CONDA_PKGS_DIRS'], '/previous-cache')


class RunnerCacheTests(unittest.TestCase):
    def test_resumed_legacy_cache_cannot_override_managed_volume(self):
        api = runner_functions()
        with patch.dict(os.environ, {'WINGS_DESKTOP_WORKSPACE': '/work', 'WINGS_DESKTOP_CONDA_PKGS_DIR': '/opt/wings-conda-pkgs'}):
            for saved in ['/Users/mike/cache', '', None]:
                env = {}
                api['apply_run_conda_cache'](env, {'conda_pkgs_dirs': saved})
                self.assertEqual(env['CONDA_PKGS_DIRS'], '/opt/wings-conda-pkgs')
            with self.assertRaisesRegex(ValueError, 'automatically'):
                api['prepare_conda_cache']('/work/new-mac-cache')

    def test_native_saved_cache_and_explicit_clear_preserved(self):
        api = runner_functions()
        with patch.dict(os.environ, {}, clear=True):
            env = {}
            api['apply_run_conda_cache'](env, {'conda_pkgs_dirs': '/project/cache'})
            self.assertEqual(env['CONDA_PKGS_DIRS'], '/project/cache')
            api['apply_run_conda_cache'](env, {'conda_pkgs_dirs': ''})
            self.assertNotIn('CONDA_PKGS_DIRS', env)

    def test_context_preparation_uses_managed_cache_and_environment_prefix(self):
        tree = ast.parse((ROOT / 'scripts/context_runner.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'provider_executor')
        calls = []
        from types import SimpleNamespace
        scope = dict(context_setup=SimpleNamespace(command=lambda *a, **kw: calls.append((a,kw))))
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual provider executor>', 'exec'), scope)
        api = {'managed_conda_cache': lambda:'/opt/wings-conda-pkgs', 'runtime_preflight':lambda:'snakemake',
               'conda_environment_prefix':lambda:Path('/opt/wings-conda-envs/linux-x86_64')}
        original = ['old-snakemake', '--snakefile', 'context.smk', '--conda-prefix', '/Users/mike/old']
        scope['provider_executor']({'conda_pkgs_dirs':'/Users/mike/pkgs'},api,{ })(original, 'test.log')
        args, kwargs = calls[0]
        self.assertEqual(args[0][-1], '/opt/wings-conda-envs/linux-x86_64')
        self.assertEqual(kwargs['env']['CONDA_PKGS_DIRS'], '/opt/wings-conda-pkgs')
        self.assertEqual(original[-1], '/Users/mike/old')


if __name__ == '__main__':
    unittest.main()
