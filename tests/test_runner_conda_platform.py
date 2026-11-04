"""Conda's platform field and legacy subdir compatibility."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class CondaPlatformTests(unittest.TestCase):
    def check(self, fields, system='Darwin', machine='arm64', rosetta=False):
        spec = importlib.util.spec_from_file_location('platform_runner',
            Path(__file__).resolve().parents[1] / 'scripts/wings_local_runner.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        root = Path('/tools/conda').resolve()
        prefix = root / 'envs/runner'
        data = {'root_prefix': str(root), **fields}
        replies = [SimpleNamespace(returncode=0, stdout=json.dumps(data))]
        if system == 'Darwin' and machine == 'x86_64':
            replies.insert(0, SimpleNamespace(returncode=0, stdout='1' if rosetta else '0'))
        with patch.object(runner.platform, 'system', return_value=system), \
             patch.object(runner.platform, 'machine', return_value=machine), \
             patch.object(runner.sys, 'prefix', str(prefix)), \
             patch.object(runner.sys, 'executable', str(prefix / 'bin/python')), \
             patch.object(runner.shutil, 'which', side_effect=lambda name: str((prefix if name == 'snakemake' else root) / 'bin' / name)), \
             patch.object(runner.subprocess, 'run', side_effect=replies):
            return runner.runtime_preflight()

    def test_current_platform_without_subdir(self):
        for system, machine, target in [('Darwin', 'arm64', 'osx-arm64'),
                                       ('Darwin', 'x86_64', 'osx-64'),
                                       ('Linux', 'aarch64', 'linux-aarch64'),
                                       ('Linux', 'x86_64', 'linux-64')]:
            with self.subTest(target=target):
                self.assertTrue(self.check({'platform': target}, system, machine).endswith('snakemake'))

    def test_legacy_subdir_fallback(self):
        for fields in ({'subdir': 'osx-arm64'}, {'platform': None, 'subdir': 'osx-arm64'}):
            self.check(fields)

    def test_platform_takes_precedence(self):
        self.check({'platform': 'osx-arm64', 'subdir': 'osx-64'})
        with self.assertRaisesRegex(ValueError, 'reports osx-64'):
            self.check({'platform': 'osx-64', 'subdir': 'osx-arm64'})

    def test_wrong_and_missing_platform_rejected(self):
        for fields in ({'platform': 'osx-64'}, {}):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'must be osx-arm64'):
                self.check(fields)

    def test_rosetta_guard_remains(self):
        with self.assertRaisesRegex(ValueError, 'Intel Python'):
            self.check({'platform': 'osx-64'}, machine='x86_64', rosetta=True)


if __name__ == '__main__':
    unittest.main()
