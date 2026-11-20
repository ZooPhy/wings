"""Run the real launcher with a fake native Docker CLI; no registry access.

These tests check orchestration, cache identity/platform and error propagation.
They do not validate Docker Desktop or emulation on a Mac.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_launcher

IRMA = 'ghcr.io/cdcgov/irma:v1.3.5'
PIN = 'docker.io/cdcgov/irma@sha256:96357063a678fd5887598b093a53373ae286a2eb0155520feae8b72904bcdda8'
INDEX = 'sha256:cda47ea17971ee02195160fccbc76b4b97a8a0115c3f0c322b00d195b29e4785'
VADR = 'staphb/vadr:1.7'
GOOD_IRMA = 'linux/amd64|sha256:fixture-irma|ghcr.io/cdcgov/irma@' + INDEX + ' '
GOOD_VADR = 'linux/amd64|sha256:fixture-vadr|staphb/vadr@sha256:fixture-vadr-manifest '


class StartupImagesTests(unittest.TestCase):
    def setUp(self):
        self.launcher = test_launcher.LauncherTests()
        self.launcher.setUp()
        self.addCleanup(self.launcher.tearDown)
        self.state = self.launcher.root / 'docker-state.json'

    def seed(self, tools):
        self.state.write_text(json.dumps({'calls': [], 'tools': tools}))

    def calls(self, command):
        calls = json.loads(self.state.read_text())['calls']
        calls = [c[2:] if c[:2] == ['--context', 'desktop-linux'] else c for c in calls]
        return [c for c in calls if c[0] == command]

    def test_fresh_launch_uses_host_cli_and_pinned_publisher_image(self):
        r = self.launcher.command()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls('pull'), [
            ['pull', '--platform', 'linux/amd64', PIN],
            ['pull', '--platform', 'linux/amd64', VADR]])
        self.assertEqual(self.calls('tag'), [['tag', 'sha256:fixture-irma', IRMA]])
        self.assertTrue(all('docker' not in c[1:] for c in self.calls('run')))
        self.assertEqual(len([c for c in self.calls('run') if '-d' in c]), 1)

    def test_verified_amd64_cache_works_offline_without_retagging(self):
        self.seed({IRMA: GOOD_IRMA, VADR: GOOD_VADR})
        self.launcher.env['MOCK_PULL_FAIL'] = '1'
        r = self.launcher.command()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls('pull'), [])
        self.assertEqual(self.calls('tag'), [])

    def test_dockerhub_cache_restores_workflow_alias_without_download(self):
        self.seed({PIN: GOOD_IRMA.replace('ghcr.io/cdcgov/irma@' + INDEX, PIN), VADR: GOOD_VADR})
        self.launcher.env['MOCK_PULL_FAIL'] = '1'
        r = self.launcher.command()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls('pull'), [])
        self.assertEqual(self.calls('tag'), [['tag', 'sha256:fixture-irma', IRMA]])

    def test_arm64_cache_does_not_satisfy_amd64_request(self):
        self.seed({IRMA: GOOD_IRMA.replace('amd64', 'arm64').replace('fixture-irma', 'fixture-arm'),
                   VADR: GOOD_VADR.replace('amd64', 'arm64')})
        r = self.launcher.command()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([c[-1] for c in self.calls('pull')], [PIN, VADR])

    def test_unrelated_digest_under_irma_tag_is_not_reused(self):
        self.seed({IRMA: GOOD_IRMA.replace(INDEX, 'sha256:unrelated').replace('fixture-irma', 'fixture-other'), VADR: GOOD_VADR})
        r = self.launcher.command()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([c[-1] for c in self.calls('pull')], [PIN])

    def assert_failed_without_service(self, variable, seed=None):
        if seed:
            self.seed(seed)
        self.launcher.env[variable] = '1'
        r = self.launcher.command()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual([c for c in self.calls('run') if '-d' in c], [])
        self.assertFalse((self.launcher.workspace / '.desktop/session').exists())
        return r

    def test_download_failure_stops_before_service(self):
        r = self.assert_failed_without_service('MOCK_PULL_FAIL')
        self.assertIn('registry unavailable', r.stderr)

    def test_wrong_platform_after_pull_stops_before_alias_or_service(self):
        self.assert_failed_without_service('MOCK_PULL_ARM64')
        self.assertEqual(self.calls('tag'), [])

    def test_alias_failure_stops_before_service(self):
        self.assert_failed_without_service('MOCK_TAG_FAIL')

    def test_vadr_failure_stops_before_service(self):
        self.assert_failed_without_service('MOCK_PULL_FAIL', {IRMA: GOOD_IRMA})
        self.assertEqual([c[-1] for c in self.calls('pull')], [VADR])

    def test_controller_prepare_never_invokes_emulated_docker(self):
        runtime = test_launcher.ROOT / 'runtime'
        sys.path.insert(0, str(runtime))
        self.addCleanup(sys.path.remove, str(runtime))
        spec = importlib.util.spec_from_file_location('startup_controller', runtime / 'controller.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp).resolve()
            repo = workspace / 'release'; repo.mkdir()
            with patch.object(sys, 'argv', ['controller', 'prepare', '--repo', str(repo), '--workspace', str(workspace)]), \
                 patch.object(module, 'verify'), patch.object(module.os, 'chdir'), \
                 patch.dict(module.os.environ), patch.object(module.subprocess, 'run') as run:
                module.main()
            self.assertEqual([c.args[0] for c in run.call_args_list], [
                ['bash', 'scripts/build_blast_db.sh'], ['bash', 'scripts/install_vadr_models.sh']])


if __name__ == '__main__':
    unittest.main()
