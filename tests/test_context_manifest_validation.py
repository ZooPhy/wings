"""Synthetic tabular-metadata checks; no sequence data or analytical tools."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts' / 'finalize_contextual_references.py'))
HEADER = 'tip_label\ttip_kind\tsegment\n'


class ContextManifestValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = self.root / 'context'
        self.context.mkdir()
        self.source = self.context / 'contextual_tip_manifest.tsv'
        self.output = self.root / 'output'

    def finalize(self):
        with contextlib.redirect_stderr(io.StringIO()):
            return MODULE['main']([
                '--context-dir', str(self.context), '--output-dir', str(self.output),
                '--retrieved-on', '2026-10-17',
            ])

    def test_missing_manifest_is_error(self):
        with self.assertRaises(FileNotFoundError):
            self.finalize()
        self.assertFalse(self.output.exists())

    def test_malformed_manifests_are_errors_not_skips(self):
        cases = {
            'empty_file': '',
            'wrong_delimiter': 'tip_label,tip_kind,segment\n',
            'missing_column': 'tip_label\tsegment\n',
            'duplicate_column': HEADER.rstrip('\n') + '\ttip_kind\n',
            'blank_column': HEADER.rstrip('\n') + '\t\n',
            'short_row': HEADER + 'example\twings_sample\n',
            'long_row': HEADER + 'example\twings_sample\tHA\textra\n',
            'empty_kind': HEADER + 'example\t\tHA\n',
            'unknown_kind': HEADER + 'example\tunknown\tHA\n',
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                self.source.write_text(text)
                with self.assertRaises(ValueError):
                    self.finalize()
                self.assertFalse(self.output.exists())

    def test_valid_header_only_preserves_documented_absence(self):
        self.source.write_text(HEADER)
        self.assertEqual(self.finalize(), 0)
        self.assertEqual(json.loads((self.output / 'provenance.json').read_text()),
                         {'skipped': True, 'reason': 'no_public_reference_rows'})

    def test_valid_sample_only_preserves_documented_absence(self):
        self.source.write_text(HEADER + 'example\twings_sample\tHA\n')
        self.assertEqual(self.finalize(), 0)
        self.assertEqual(json.loads((self.output / 'finalize_summary.json').read_text())['reason'],
                         'no_public_reference_rows')

    def test_valid_reference_row_is_preserved(self):
        self.source.write_text(HEADER + 'example\tpublic_reference\tHA\n')
        self.assertEqual(MODULE['read_tsv'](self.source),
                         [{'tip_label': 'example', 'tip_kind': 'public_reference', 'segment': 'HA'}])


if __name__ == '__main__':
    unittest.main()
