"""MAFFT path regression tests; no scientific dependencies or network required."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


def load_inference():
    def write_json(path, value):
        path.write_text(json.dumps(value))
    modules = {
        'phylodynamic_selection': types.SimpleNamespace(
            read_tsv=lambda path: [dict(id='tip1')], write_json=write_json,
            digest=lambda path: 'fixture-digest'),
        'phylodynamic_mapping': types.SimpleNamespace(
            numeric_date=None, calendar_date=None, sample_histories=None),
        'phylodynamic_estimands': types.SimpleNamespace(focal_branches=None, entry_count=None),
    }
    spec = importlib.util.spec_from_file_location('mafft_paths_under_test',
        Path(__file__).resolve().parents[1] / 'scripts/phylodynamic_inference.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


inference = load_inference()


class ReachedTreeRead(Exception):
    pass


class MafftPathTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.prefix = self.root / 'WINGS Workspace' / 'current release' / 'env'
        self.bin = self.prefix / 'bin'
        self.binaries = self.prefix / 'libexec' / 'mafft'
        self.bin.mkdir(parents=True)
        self.binaries.mkdir(parents=True)
        self.executable(self.binaries / 'version', '#!/bin/bash\necho 7.526\n')
        # Mimics the installed launcher's broken embedded prefix and supported override.
        self.executable(self.bin / 'mafft', '''#!/bin/bash
if [ "$MAFFT_BINARIES" ]; then
    prefix="$MAFFT_BINARIES"
else
    prefix=/missing/WINGS Workspace/old-release/libexec/mafft
fi
versionbin=$("$prefix/version") || exit 1
[ "$versionbin" = "7.526" ] || exit 1
if [ "$1" = "--version" ]; then
    [ "${TEST_MAFFT_FAIL:-}" != version ] || exit 7
    echo 'v7.526 (fixture)'
else
    [ "${TEST_MAFFT_FAIL:-}" != alignment ] || exit 9
    printf 'MAFFT_BINARIES=%s\\n' "$MAFFT_BINARIES" >&2
    cat "${!#}"
fi
''')
        self.executable(self.bin / 'iqtree2', '''#!/bin/bash
printf 'IQTREE_MAFFT_BINARIES=%s\\n' "${MAFFT_BINARIES-unset}"
exit 0
''')
        self.enterContext(patch.dict(os.environ, {
            'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', ''),
            'MAFFT_BINARIES': '/stale/binaries', 'TEST_MAFFT_FAIL': ''}))
        self.selection = self.root / 'selection with spaces'
        self.selection.mkdir()
        self.output = self.root / 'output with spaces'
        self.fasta = '>tip1\nACGT\n'
        (self.selection / 'input.fasta').write_text(self.fasta)
        data = dict(id='fixture', segment='HA', strategy='balanced', replicate=1,
                    seed=1729, study=[], references=[], locations=[], reasons=[],
                    config={}, status='ready', selected_sha256='fixture-digest',
                    lineage=dict(status='ready', target_clade='fixture'))
        (self.selection / 'selection.json').write_text(json.dumps(data))
        self.enterContext(patch.dict(sys.modules, {
            'treetime': types.SimpleNamespace(TreeTime=object),
            'Bio': types.SimpleNamespace(Phylo=types.SimpleNamespace(read=self.tree_read)),
        }))

    @staticmethod
    def executable(path, contents):
        path.write_text(contents)
        path.chmod(0o755)

    @staticmethod
    def tree_read(*args):
        raise ReachedTreeRead()

    def test_uses_current_launcher_prefix_and_preserves_parent_environment(self):
        executable, env = inference.mafft_runtime()
        self.assertEqual(executable, str(self.bin / 'mafft'))
        self.assertEqual(env['MAFFT_BINARIES'], str(self.binaries))
        self.assertEqual(os.environ['MAFFT_BINARIES'], '/stale/binaries')
        self.assertEqual(env['PATH'], os.environ['PATH'])

    def test_real_subprocess_version_and_alignment_succeed_with_spaces(self):
        with self.assertRaises(ReachedTreeRead):
            inference.infer(self.selection, self.output, 2)
        self.assertEqual((self.output / 'alignment.fasta').read_text(), self.fasta)
        log = (self.output / 'tools.log').read_text()
        self.assertIn('v7.526', log)
        self.assertIn('MAFFT_BINARIES=' + str(self.binaries), log)
        self.assertEqual(log.count('IQTREE_MAFFT_BINARIES=/stale/binaries'), 2)

    def test_fixture_reproduces_failure_without_override(self):
        env = os.environ.copy()
        env.pop('MAFFT_BINARIES', None)
        result = subprocess.run([str(self.bin / 'mafft'), '--version'],
                                env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Workspace/old-release', result.stderr)

    def test_version_failure_still_stops_inference(self):
        with patch.dict(os.environ, {'TEST_MAFFT_FAIL': 'version'}):
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                inference.infer(self.selection, self.output, 1)
        self.assertEqual(caught.exception.returncode, 7)
        self.assertFalse((self.output / 'alignment.fasta').exists())
        self.assertEqual(json.loads((self.output / 'result.json').read_text())['status'], 'incomplete')

    def test_alignment_failure_still_stops_inference(self):
        with patch.dict(os.environ, {'TEST_MAFFT_FAIL': 'alignment'}):
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                inference.infer(self.selection, self.output, 1)
        self.assertEqual(caught.exception.returncode, 9)
        self.assertEqual((self.output / 'tools.log').read_text().count('IQTREE_MAFFT_BINARIES='), 1)

    def test_mismatched_binaries_are_not_accepted(self):
        self.executable(self.binaries / 'version', '#!/bin/bash\necho 0.000\n')
        with self.assertRaises(subprocess.CalledProcessError):
            inference.infer(self.selection, self.output, 1)

    def test_missing_launcher_is_explicit(self):
        with patch.object(inference.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, 'MAFFT executable not found'):
                inference.mafft_runtime()

    def test_other_installation_layout_preserves_explicit_configuration(self):
        launcher = self.root / 'custom' / 'bin' / 'mafft'
        launcher.parent.mkdir(parents=True)
        self.executable(launcher, '#!/bin/bash\nexit 0\n')
        with patch.object(inference.shutil, 'which', return_value=str(launcher)):
            executable, env = inference.mafft_runtime()
        self.assertEqual(executable, str(launcher))
        self.assertEqual(env['MAFFT_BINARIES'], '/stale/binaries')

    def test_blocked_selection_does_not_require_mafft(self):
        path = self.selection / 'selection.json'
        data = json.loads(path.read_text())
        data['status'] = 'blocked'
        path.write_text(json.dumps(data))
        with patch.object(inference.shutil, 'which', side_effect=AssertionError('must not resolve')):
            self.assertEqual(inference.infer(self.selection, self.output, 1)['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
