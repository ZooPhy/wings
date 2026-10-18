"""Test the report's actual Python functions without running genomic analyses."""
import ast
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / 'scripts/sample_summary.qmd').read_text()
FUNCTIONS = {}
for cell in re.findall(r'```\{python\}\n(.*?)\n```', TEXT, re.DOTALL):
    tree = ast.parse(cell)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {'parse_genoflu_report', 'genoflu_report_presentation'}:
            FUNCTIONS[node.name] = node
namespace = {'re': re}
exec(compile(ast.Module(body=list(FUNCTIONS.values()), type_ignores=[]), '<report-functions>', 'exec'), namespace)
parse = namespace['parse_genoflu_report']
present = namespace['genoflu_report_presentation']


class GenofluReportStatesTests(unittest.TestCase):
    def parse_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'output.txt'
            path.write_bytes(text if isinstance(text, bytes) else text.encode())
            return parse(path)

    def test_assigned_example(self):
        result = parse(ROOT / 'tests/fixtures/genoflu_reporting/assigned.txt')
        self.assertEqual(result['output_state'], 'assigned')
        self.assertEqual(result['status'], 'D1.1')
        self.assertEqual(present(result)[0], 'download-status-pass')

    def test_unassigned_preserves_existing_segment_evidence(self):
        result = parse(ROOT / 'tests/fixtures/genoflu_reporting/unassigned.txt')
        self.assertEqual(result['output_state'], 'unassigned')
        self.assertEqual(result['status'], 'Not assigned')
        self.assertEqual(result['matched_segments'], 5)
        self.assertEqual(len(result['calls']), 5)
        self.assertEqual(present(result)[0], 'download-status-review')
        self.assertIn('explicitly reports no genotype assignment', present(result)[2])

    def test_missing_output_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in (None, Path(directory) / 'absent.txt'):
                with self.subTest(path=path):
                    result = parse(path)
                    self.assertEqual(result['output_state'], 'missing')
                    self.assertIn('whether GenoFLU ran', present(result)[2])

    def test_empty_and_invalid_encoding(self):
        for text in ('', ' \n\t', b'\xff\xfe'):
            with self.subTest(text=text):
                result = self.parse_text(text)
                self.assertEqual(result['output_state'], 'invalid')
                self.assertEqual(present(result)[0], 'download-status-review')
                self.assertIn('not established', present(result)[2])

    def test_unrecognized_or_incomplete_output(self):
        for text in ('arbitrary text', 'genoflu.py set arguements:\nFASTA: example',
                     'consensus Genotype --> Not assigned:',
                     'sample\tstatus\nexample\tUNKNOWN_STATUS\n'):
            with self.subTest(text=text):
                result = self.parse_text(text)
                self.assertEqual(result['output_state'], 'unrecognized')
                self.assertEqual(present(result)[0], 'download-status-review')
                self.assertIn('not established', present(result)[2])

    def test_explicit_skip_codes_are_preserved(self):
        for status in ('H5_NOT_DETECTED', 'H5_OR_NA_INDETERMINATE',
                       'H5N1_NOT_DETECTED', 'H5N1_INDETERMINATE'):
            with self.subTest(status=status):
                result = self.parse_text(f'sample\tstatus\nexample\t{status}\n')
                self.assertEqual(result['output_state'], 'skipped')
                self.assertEqual(result['status'], 'Not run')
                self.assertIn(status, result['reason'])
                self.assertEqual(present(result)[0], 'download-status-review')


if __name__ == '__main__':
    unittest.main()
