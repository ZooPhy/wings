"""Check browser preparation against the real runner/parser contracts."""
import ast
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MetadataWizardContractTests(unittest.TestCase):
    def test_export_is_accepted_by_the_python_metadata_reader(self):
        script = "const c=require('./assets/wings-metadata-core.js');process.stdout.write(c.toTSV(c.FIELDS.concat('notes'),[{sample_id:'run_barcode04',host:'SNGO',notes:'quoted \\\"note\\\"\\nnext line'}]));"
        result = subprocess.run(['node', '-e', script], cwd=ROOT, check=True, capture_output=True, text=True)
        import io
        rows = list(csv.DictReader(io.StringIO(result.stdout), delimiter='\t'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['sample_id'], 'run_barcode04')
        self.assertIn('\n', rows[0]['notes'])

    def test_sample_stems_match_the_runner_for_all_supported_suffixes(self):
        tree = ast.parse((ROOT / 'scripts/wings_local_runner.py').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'strip_fastq')
        scope = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<runner strip_fastq>', 'exec'), scope)
        names = ['sample.fastq.gz', 'sample.fq.gz', 'sample.fastq', 'sample.fq', 'sample_R1.FASTQ.GZ']
        script = "const c=require('./assets/wings-metadata-core.js');process.stdout.write(JSON.stringify(JSON.parse(process.argv[1]).map(c.stripFastq)));"
        result = subprocess.run(['node', '-e', script, json.dumps(names)], cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), [scope['strip_fastq'](name)[0] for name in names])

    def test_browser_required_field_matches_validator(self):
        spec = importlib.util.spec_from_file_location('metadata_validator', ROOT / 'scripts/validate_metadata.py')
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        self.assertEqual(validator.REQUIRED_COLUMNS, ('sample_id',))
        source = (ROOT / 'assets/wings-metadata-core.js').read_text()
        self.assertIn('sample_id', source)

    def test_host_dictionary_is_bundled_without_losing_codes_or_names(self):
        with (ROOT / 'resources/ebird_host_codes_2025.tsv').open(encoding='utf-8') as handle:
            expected = [(row['host'], row['ebird_species']) for row in csv.DictReader(handle, delimiter='\t') if row['host'].strip() and row['ebird_species'].strip()]
        reference = json.loads((ROOT / 'assets/wings-metadata-reference.json').read_text())
        self.assertEqual([(row['code'], row['name']) for row in reference['hosts']], expected)


if __name__ == '__main__':
    unittest.main()
