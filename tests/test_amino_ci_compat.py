import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
compression=load('demo_compression',ROOT/'scripts/compress_demo_bundle.py')
integration=load('missing_segments',ROOT/'tests/integration_missing_segments.py')
class CompatibilityTests(unittest.TestCase):
    def bundle(self):
        return {'format':'WINGS_REPORT_BUNDLE','version':1,'sample_count':1,'samples':{'synthetic':{'html':'<html>sample</html>'}},'run_summary':{'html':'<html>run</html>'}}
    def test_rule_stops_before_include(self):
        rule='rule wings_report_bundle:\n    output: "bundle"\n    shell: "echo done"\n\n'
        text=rule+'# amino acid extension\ninclude: "scripts/amino_acids.smk"\n'
        result=integration.rule_text(text,'wings_report_bundle')
        self.assertNotIn('include:',result);self.assertIn('shell: "echo done"',result)
    def test_rule_stops_before_other_top_level_code(self):
        for tail in ['rule next:\n    output: "x"','checkpoint next:\n    output: "x"','VALUE = 1','def helper():\n    pass']:
            with self.subTest(tail=tail):
                result=integration.rule_text('rule first:\n    output: "x"\n'+tail,'first')
                self.assertEqual(result,'rule first:\n    output: "x"\n')
    def test_compressed_only_valid_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'demo.wings';packed=Path(temp)/'demo.wings.gz'
            packed.write_bytes(gzip.compress(json.dumps(self.bundle()).encode()))
            self.assertIn('local source absent',compression.verify(source,packed));self.assertFalse(source.exists())
    def test_matching_source_and_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'demo.wings';packed=Path(temp)/'demo.wings.gz';raw=json.dumps(self.bundle()).encode()
            source.write_bytes(raw);packed.write_bytes(gzip.compress(raw))
            self.assertEqual(compression.verify(source,packed),'identical decompressed bytes')
            source.write_bytes(raw+b' ')
            with self.assertRaises(ValueError):compression.verify(source,packed)
    def test_corrupt_gzip_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            packed=Path(temp)/'demo.wings.gz';packed.write_bytes(gzip.compress(json.dumps(self.bundle()).encode())[:-5])
            with self.assertRaises((EOFError,OSError)):compression.verify(Path(temp)/'absent',packed)
    def test_invalid_bundles_are_rejected(self):
        invalid=[{},[],{**self.bundle(),'sample_count':2},{**self.bundle(),'samples':{'x':{}}},{**self.bundle(),'run_summary':{}}]
        for bundle in invalid:
            with tempfile.TemporaryDirectory() as temp:
                packed=Path(temp)/'demo.wings.gz';packed.write_bytes(gzip.compress(json.dumps(bundle).encode()))
                with self.assertRaises(ValueError):compression.verify(Path(temp)/'absent',packed)
if __name__=='__main__':unittest.main()
