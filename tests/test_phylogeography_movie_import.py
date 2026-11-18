import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from build_phylogeography_movie import build, validate


class MovieImportTests(unittest.TestCase):
    def fixture(self, folder):
        tables = {
            'nodes': (['segment', 'id', 'parent', 'date', 'observed_state'],
                      [['HA', 'r', '', '2025-01-01', ''], ['HA', 't', 'r', '2025-04-01', 'B']]),
            'histories': (['segment', 'history', 'root_state'], [['HA', 'zero', 'B'], ['HA', 'one', 'A']]),
            'jumps': (['segment', 'history', 'branch', 'date', 'from', 'to'], [['HA', 'one', 't', '2025-02-01', 'A', 'B']]),
            'locations': (['id', 'label', 'lat', 'lon'], [['A', 'State A', 35, -80], ['B', 'State B', 40, -85]])}
        args = argparse.Namespace(method='Test posterior', inference='bayesian', title='Test')
        for key, (header, rows) in tables.items():
            p = folder/(key+'.tsv')
            with p.open('w', newline='') as f:
                w = csv.writer(f, delimiter='\t'); w.writerow(header); w.writerows(rows)
            setattr(args, key, p)
        return args

    def test_roundtrip_and_zero_history(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp)); data = build(args); validate(data)
            self.assertEqual(data['segments'][0]['histories'][0]['jumps'], [])
            self.assertEqual(len(data['segments'][0]['histories']), 2)
            self.assertIsNone(data['segments'][0]['nodes'][0]['parent'])

    def test_missing_history_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp))
            args.histories.write_text('segment\thistory\troot_state\nHA\tzero\tB\n')
            with self.assertRaisesRegex(ValueError, 'undeclared history'): build(args)

    def test_cli_validates_then_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp)); output = Path(temp)/'movie.json'
            command = [sys.executable, str(ROOT/'scripts/build_phylogeography_movie.py')]
            for key in ('nodes', 'histories', 'jumps', 'locations'): command += ['--'+key, str(getattr(args, key))]
            command += ['--method', 'Test', '--inference', 'bayesian', '--output', str(output)]
            subprocess.run(command, check=True, capture_output=True)
            first = output.read_bytes(); self.assertEqual(json.loads(first)['synthetic'], False)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(first, output.read_bytes())


if __name__ == '__main__': unittest.main()
