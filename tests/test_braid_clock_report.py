import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

builder = module('build_braid_clock_report')
installer = module('install_braid_clock')

class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'explorer.json'
        self.data = {'samples': [{'sample_id': 'TEST'}], 'trees': {}}
        self.source.write_text(json.dumps(self.data))
    def tearDown(self):
        self.temp.cleanup()
    def test_build_is_self_contained(self):
        out = self.root/'preview.html'
        builder.build(self.source, out, ROOT/'scripts/report')
        html = out.read_text()
        self.assertIn('WINGS_BRAID_CLOCK', html)
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn('<script src=', html)
        self.assertNotIn('<link ', html)
    def test_source_not_changed(self):
        old = self.source.read_bytes()
        builder.build(self.source, self.root/'preview.html', ROOT/'scripts/report')
        self.assertEqual(self.source.read_bytes(), old)
    def test_reject_overwrite_input(self):
        with self.assertRaisesRegex(ValueError,'overwrite'):
            builder.build(self.source, self.source, ROOT/'scripts/report')
    def test_no_script_injection(self):
        encoded = builder.safe_json({'label':'</script><script>alert(1)</script>'})
        self.assertNotIn('</script>', encoded)
        self.assertEqual(json.loads(encoded)['label'], '</script><script>alert(1)</script>')
    def test_duplicate_json_keys_rejected(self):
        self.source.write_text('{"samples": [], "samples": []}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            builder.load_json(self.source)
    def test_invalid_number_rejected(self):
        self.source.write_text('{"x": NaN}')
        with self.assertRaisesRegex(ValueError,'Invalid JSON number'):
            builder.load_json(self.source)
    def test_malformed_input_schema(self):
        self.source.write_text('{"not_explorer": true}')
        with self.assertRaisesRegex(ValueError,'samples'):
            builder.build(self.source, self.root/'preview.html', ROOT/'scripts/report')
    def test_missing_phenology_boolean_rejected(self):
        ph = self.root/'phenology.json'
        ph.write_text('{"schema_version":"wings.phenology.v1", "profiles": []}')
        with self.assertRaisesRegex(ValueError,'synthetic'):
            builder.build(self.source,self.root/'preview.html',ROOT/'scripts/report',ph)
    def test_optional_phenology_is_embedded(self):
        ph = self.root/'phenology.json'
        ph.write_text('{"schema_version":"wings.phenology.v1", "profiles": [], "synthetic": false}')
        out=self.root/'preview.html'
        builder.build(self.source,out,ROOT/'scripts/report',ph)
        self.assertIn('"ecological_clock"',out.read_text())
    def test_js_hook_installed_once(self):
        original='(() => {\n'+installer.ORIGINAL+'\n})();\n'
        once=installer.patch_js(original,'/* module fixture */')
        twice=installer.patch_js(once,'/* module fixture */')
        self.assertEqual(once,twice)
        self.assertEqual(once.count('mountExplorer(explorer)'),1)
    def test_unknown_upstream_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'upstream file differs'):
            installer.patch_js('new Explorer(other, payload);','module')
    def test_css_append_is_idempotent(self):
        once=installer.replace_bundle('old {}\n','.wbc {}','TEST',False)
        self.assertEqual(once,installer.replace_bundle(once,'.wbc {}','TEST',False))
    def test_plan_never_touches_scientific_inputs(self):
        (self.root/'Snakefile').write_text('# fixture')
        d=self.root/'scripts/report';d.mkdir(parents=True)
        (d/'surveillance-explorer.js').write_text(installer.ORIGINAL+'\n')
        (d/'surveillance-explorer.css').write_text('body {}\n')
        changes=installer.plan(self.root)
        self.assertNotIn('Snakefile',changes)
        self.assertNotIn('config.yaml',changes)
        self.assertNotIn('README.md',changes)
        self.assertFalse(any(k.startswith('results/') for k in changes))
    def test_apply_creates_backup_and_can_repeat(self):
        p=self.root/'file.txt';p.write_text('old')
        backup=installer.apply(self.root,{'file.txt':b'new','new.txt':b'added'})
        self.assertEqual(p.read_text(),'new')
        self.assertEqual((backup/'file.txt').read_text(),'old')
        import shutil
        shutil.rmtree(backup)

if __name__=='__main__':
    unittest.main()
