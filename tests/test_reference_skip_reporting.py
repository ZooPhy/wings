"""Reporting-only checks using synthetic metadata; no sequence inputs."""
import json
import runpy
import tempfile
import unittest
from pathlib import Path

attach = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts' / 'public_reference_context.py'))['attach_reference_context']


class ReferenceSkipReportingTests(unittest.TestCase):
    def invoke(self, metadata):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'manifest.tsv'
            manifest.write_text('tip_label\ttip_kind\tsegment\n')
            provenance = root / 'provenance.json'
            provenance.write_text(json.dumps(metadata))
            warnings = []
            result = attach({}, [], manifest, provenance, warnings)
            return result, warnings

    def test_reason_survives_in_warnings(self):
        result, warnings = self.invoke({'skipped': True, 'reason': 'no_public_reference_rows'})
        self.assertIsNone(result)
        self.assertEqual(warnings, ['Public reference context skipped. Recorded reason: no_public_reference_rows'])

    def test_reason_is_required(self):
        for reason in (None, '', '  ', 123):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, 'requires a reason'):
                self.invoke({'skipped': True, 'reason': reason})

    def test_boolean_is_required(self):
        for skipped in ('false', 'true', 0, 1):
            with self.subTest(skipped=skipped), self.assertRaisesRegex(ValueError, 'must be a boolean'):
                self.invoke({'skipped': skipped, 'reason': 'example'})

    def test_not_configured_has_no_skip_warning(self):
        warnings = []
        self.assertIsNone(attach({}, [], None, None, warnings))
        self.assertEqual(warnings, [])

    def test_regular_validation_remains_active(self):
        with self.assertRaisesRegex(ValueError, 'manifest_sha256'):
            self.invoke({})


if __name__ == '__main__':
    unittest.main()
