"""Native CLI selection and transactional live repair (no real Docker daemon)."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_launcher

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_docker_repair', ROOT / 'repairs/native_docker_cli.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class NativeDockerLauncherTests(unittest.TestCase):
    def setUp(self):
        self.launcher = test_launcher.LauncherTests()
        self.launcher.setUp()
        self.addCleanup(self.launcher.tearDown)

    def calls(self):
        calls = json.loads((self.launcher.root / 'docker-state.json').read_text())['calls']
        return [c[2:] if c[:2] == ['--context', 'desktop-linux'] else c for c in calls]

    def test_engine_architecture_selects_client_and_keeps_analysis_amd64(self):
        for engine, selected in [('arm64', 'arm64'), ('aarch64', 'arm64'),
                                 ('x86_64', 'amd64'), ('amd64', 'amd64')]:
            with self.subTest(engine=engine):
                self.launcher.env['MOCK_ENGINE_ARCH'] = engine
                r = self.launcher.command()
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                runs = [c for c in self.calls() if c[0] == 'run']
                start = [c for c in runs if '-d' in c][-1]
                self.assertIn('WINGS_DOCKER_CLI_ARCH=' + selected, start)
                self.assertEqual(start[start.index('--platform') + 1], 'linux/amd64')
                check = [c for c in runs if 'docker-check' in c][-1]
                self.assertIn('WINGS_DOCKER_CLI_ARCH=' + selected, check)
                self.assertLess(self.calls().index(check), self.calls().index(start))
                self.assertEqual(self.launcher.command('stop').returncode, 0)

    def test_unknown_engine_architecture_stops_before_runtime(self):
        self.launcher.env['MOCK_ENGINE_ARCH'] = 'unsupported'
        r = self.launcher.command()
        self.assertEqual(r.returncode, 14)
        self.assertFalse(any(c[0] in ('build', 'run') for c in self.calls()))

    def test_controller_cli_failure_stops_before_service_or_reference_preparation(self):
        self.launcher.env['MOCK_CONTROLLER_DOCKER_FAIL'] = '1'
        r = self.launcher.command()
        self.assertNotEqual(r.returncode, 0)
        runs = [c for c in self.calls() if c[0] == 'run']
        self.assertTrue(any('docker-check' in c for c in runs))
        self.assertFalse(any('-d' in c or 'prepare' in c for c in runs))

    def test_controller_checks_version_and_info_with_timeouts(self):
        runtime = ROOT / 'runtime'
        sys.path.insert(0, str(runtime))
        self.addCleanup(sys.path.remove, str(runtime))
        spec = importlib.util.spec_from_file_location('native_cli_controller', runtime / 'controller.py')
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp).resolve(); repo = workspace / 'release'; repo.mkdir()
            with patch.object(sys, 'argv', ['controller', 'docker-check', '--repo', str(repo), '--workspace', str(workspace)]), \
                 patch.object(controller, 'verify'), patch.object(controller.os, 'chdir'), \
                 patch.dict(controller.os.environ), patch.object(controller.subprocess, 'run') as run:
                controller.main()
            self.assertEqual([c.args[0] for c in run.call_args_list], [
                ['docker', 'version'], ['docker', 'info', '--format', '{{.OSType}}/{{.Architecture}}']])
            self.assertTrue(all(c.kwargs['check'] and c.kwargs['timeout'] == 30 for c in run.call_args_list))


class DockerDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wings CLI dispatch ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.wrapper = self.root / 'docker'
        self.wrapper.write_text((ROOT / 'runtime/docker-cli.sh').read_text().replace(
            '/opt/wings-desktop/bin/', str(self.root) + '/'))
        for arch in ['arm64', 'amd64']:
            binary = self.root / ('docker-' + arch)
            binary.write_text('#!' + sys.executable + '\nimport os,sys,json\n'
                'print(json.dumps([sys.argv,os.environ.get("DOCKER_DEFAULT_PLATFORM")]))\n'
                'sys.exit(int(os.environ.get("FAKE_CLI_EXIT","0")))\n')
            binary.chmod(0o755)

    def execute(self, arch=None, status='0'):
        env = dict(os.environ, DOCKER_DEFAULT_PLATFORM='linux/amd64', FAKE_CLI_EXIT=status)
        env.pop('WINGS_DOCKER_CLI_ARCH', None)
        if arch is not None: env['WINGS_DOCKER_CLI_ARCH'] = arch
        return subprocess.run(['sh', str(self.wrapper), 'run', '--platform', 'linux/amd64',
                               "path with spaces, 'quotes' and ü"],
                              env=env, text=True, capture_output=True)

    def test_selected_binary_receives_exact_arguments_and_platform(self):
        for arch in [None, 'amd64', 'arm64']:
            with self.subTest(arch=arch):
                r = self.execute(arch)
                self.assertEqual(r.returncode, 0, r.stderr)
                argv, default = json.loads(r.stdout)
                self.assertEqual(Path(argv[0]).name, 'docker-' + (arch or 'amd64'))
                self.assertEqual(argv[1:], ['run', '--platform', 'linux/amd64', "path with spaces, 'quotes' and ü"])
                self.assertEqual(default, 'linux/amd64')

    def test_failure_propagates_without_falling_back_to_emulation(self):
        self.assertEqual(self.execute('arm64', '2').returncode, 2)

    def test_invalid_selection_is_rejected(self):
        r = self.execute('../../anything')
        self.assertEqual(r.returncode, 64)
        self.assertEqual(r.stdout, '')


class NativeDockerRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / 'docker'
        self.original = b'original AMD64 executable fixture'
        self.target.write_bytes(self.original); self.target.chmod(0o751)
        header = bytearray(64); header[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', header, 18, 183)
        self.candidate = self.root / 'candidate'
        self.candidate.write_bytes(header); self.candidate.chmod(0o755)

    def test_success_backs_up_original_and_tests_installed_path(self):
        calls = []
        backup = repair.install(self.candidate, self.target, self.root, check=calls.append)
        self.assertEqual(calls, [self.candidate, self.target])
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o755)

    def test_failing_candidate_never_changes_existing_cli(self):
        def fail(_): raise RuntimeError('candidate failed')
        with self.assertRaisesRegex(RuntimeError, 'candidate failed'):
            repair.install(self.candidate, self.target, self.root, check=fail)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob('docker-cli-*')), [])

    def test_failed_post_install_check_restores_original_bytes_and_mode(self):
        def check(path):
            if path == self.target: raise RuntimeError('post-install failed')
        with self.assertRaisesRegex(RuntimeError, 'post-install failed'):
            repair.install(self.candidate, self.target, self.root, check=check)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o751)

    def test_wrong_binary_architecture_is_rejected_before_execution(self):
        data = bytearray(self.candidate.read_bytes()); struct.pack_into('<H', data, 18, 62)
        self.candidate.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'ARM64'):
            repair.install(self.candidate, self.target, self.root, check=lambda _: self.fail('executed'))
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_symlink_target_is_not_overwritten(self):
        self.target.unlink(); self.target.symlink_to(self.candidate)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            repair.install(self.candidate, self.target, self.root, check=lambda _: self.fail('executed'))
        self.assertTrue(self.target.is_symlink())

    def test_probe_checks_both_client_and_server_and_bounds_wait(self):
        responses = [subprocess.CompletedProcess([], 0, 'linux/arm64 linux/arm64\n', ''),
                     subprocess.CompletedProcess([], 0, 'linux/aarch64\n', '')]
        with patch.object(repair.subprocess, 'run', side_effect=responses) as run:
            repair.probe(self.candidate)
        self.assertEqual([c.args[0][1] for c in run.call_args_list], ['version', 'info'])
        self.assertTrue(all(c.kwargs['timeout'] == 30 for c in run.call_args_list))

    def test_probe_rejects_crash_or_unexpected_server_architecture(self):
        for result in [subprocess.CompletedProcess([], 2, '', 'SIGSEGV'),
                       subprocess.CompletedProcess([], 0, 'linux/arm64 linux/amd64', '')]:
            with self.subTest(result=result):
                with patch.object(repair.subprocess, 'run', return_value=result):
                    with self.assertRaises(RuntimeError): repair.probe(self.candidate)


if __name__ == '__main__':
    unittest.main()
