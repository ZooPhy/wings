import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('saved_ui_refresh', ROOT / 'scripts/refresh_saved_explorer_ui.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


@unittest.skipUnless(shutil.which('node'), 'Node.js is required for the script check')
class SavedUIRefreshTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        source = self.root / 'source'
        (source / 'run_summary').mkdir(parents=True)
        (source / 's1/summary').mkdir(parents=True)
        self.payload = {'samples': [{'sample_id': 's1'}], 'trees': {'HA': 'retained'}, 'ebird_status': {'status': 'READY'}}
        self.html = ('<html><head><style>.wings-surveillance-explorer .wse-genome-controls{}</style>'
                     '<style>:root{--escape-maroon:red}.report-header{}</style></head><body>'
                     '<div class="report-brand-logo">logo</div>'
                     '<script>class Explorer {} /* WINGS_MIGRATION_WEAVE_JS_BEGIN */</script>'
                     '<script id="wings-surveillance-data-0" type="application/json">' + json.dumps(self.payload) + '</script></body></html>')
        (source / 'run_summary/run_summary.html').write_text(self.html)
        self.sample_html = '<html><body>Retained sample report</body></html>'
        self.sample_path = Path('s1/summary/s1.sample_summary.html')
        (source / self.sample_path).write_text(self.sample_html)
        self.bundle = {'format': 'WINGS_REPORT_BUNDLE', 'version': 1, 'sample_count': 1,
                       'run_summary': {'filename': 'run_summary.html', 'html': self.html},
                       'samples': {'s1': {'filename': 's1.sample_summary.html', 'html': self.sample_html}},
                       'provenance': {'data': {'original_analysis': 'retained'}},
                       'report_refresh': {'release': 'Sep-2026', 'package_id': 'retained-package'}}
        (source / 'wings_report_bundle.wings').write_text(json.dumps(self.bundle))
        self.args = argparse.Namespace(repo=ROOT, input_dir=source, output_dir=self.root / 'updated')

    def test_update_preserves_data_samples_original_inputs_and_bundle_provenance(self):
        original_bundle = (self.args.input_dir / 'wings_report_bundle.wings').read_bytes()
        updater.update(self.args)
        codec = updater.module(ROOT, 'wings_bundle_format')
        result = codec.unpack_bundle(codec.read_bundle(self.args.output_dir / 'wings_report_bundle.wings'))
        self.assertEqual(result['samples'], self.bundle['samples'])
        self.assertEqual(result['provenance'], self.bundle['provenance'])
        self.assertEqual(result['report_refresh'], self.bundle['report_refresh'])
        self.assertEqual((self.args.output_dir / self.sample_path).read_text(), self.sample_html)
        self.assertEqual((self.args.input_dir / 'wings_report_bundle.wings').read_bytes(), original_bundle)
        self.assertEqual((self.args.input_dir / 'run_summary/run_summary.html').read_text(), self.html)
        output_html = (self.args.output_dir / 'run_summary/run_summary.html').read_text()
        self.assertEqual(result['run_summary']['html'], output_html)
        ui = updater.module(ROOT, 'refresh_demo_ui')
        parsed = ui.ReportHTML(output_html)
        blocks = [b for b in parsed.blocks if b['kind'] == 'script' and b['attrs'].get('id') == 'wings-surveillance-data-0']
        self.assertEqual(json.loads(parsed.body(blocks[0])), self.payload)
        self.assertIn('WINGS_VIEW_NAVIGATOR_V1', output_html)

    def test_existing_output_is_not_overwritten(self):
        self.args.output_dir.mkdir()
        keep = self.args.output_dir / 'keep'
        keep.write_text('retained')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            updater.update(self.args)
        self.assertEqual(keep.read_text(), 'retained')

    def test_mismatched_bundle_is_rejected_without_output(self):
        path = self.args.input_dir / 'run_summary/run_summary.html'
        path.write_text(self.html + 'changed')
        with self.assertRaisesRegex(ValueError, 'do not match'):
            updater.update(self.args)
        self.assertFalse(self.args.output_dir.exists())

    def test_nested_output_is_rejected(self):
        self.args.output_dir = self.args.input_dir / 'nested'
        with self.assertRaisesRegex(ValueError, 'separate directories'):
            updater.update(self.args)

    def test_sample_refresh_and_banner_removal_retain_evidence_and_provenance(self):
        notice = '<aside id="wings-ebird-refresh-notice">Report context refreshed old date</aside>'
        main = self.html.replace('<body>', '<body>' + notice)
        sample = '<html><body>' + notice + '<main class="content"><section id="sample-metadata"><h2>Sample metadata</h2><table><tr><td>original evidence</td></tr></table></section></main><script id="sample-evidence" type="application/json">{"retained":true}</script></body></html>'
        self.bundle['run_summary']['html'] = main
        self.bundle['samples']['s1']['html'] = sample
        (self.args.input_dir / 'run_summary/run_summary.html').write_text(main)
        (self.args.input_dir / self.sample_path).write_text(sample)
        (self.args.input_dir / 'wings_report_bundle.wings').write_text(json.dumps(self.bundle))
        self.args.refresh_samples = True
        self.args.remove_refresh_notice = True
        updater.update(self.args)
        codec = updater.module(ROOT, 'wings_bundle_format')
        result = codec.unpack_bundle(codec.read_bundle(self.args.output_dir / 'wings_report_bundle.wings'))
        self.assertNotIn(notice, result['run_summary']['html'])
        output = (self.args.output_dir / self.sample_path).read_text()
        self.assertNotIn(notice, output)
        self.assertIn('<td>original evidence</td>', output)
        self.assertIn('"retained":true', output)
        self.assertIn('Back to run summary', output)
        self.assertEqual(result['samples']['s1']['html'], output)
        self.assertEqual(result['provenance'], self.bundle['provenance'])
        self.assertEqual(result['report_refresh'], self.bundle['report_refresh'])
        self.assertEqual((self.args.input_dir / self.sample_path).read_text(), sample)

    def test_sample_asset_insertion_is_idempotent_and_ignores_popup_body(self):
        source = '<html><body><script>const popup = `<html><body></body></html>`;</script><main>retained</main></body></html>'
        ui = updater.module(ROOT, 'refresh_demo_ui')
        css = (ROOT / 'scripts/report/sample-navigation.css').read_text()
        js = (ROOT / 'scripts/report/sample-navigation.js').read_text()
        first = updater.refresh_sample_html(source, css, js, ui)
        self.assertEqual(updater.refresh_sample_html(first, css, js, ui), first)
        self.assertEqual(first.count('id="wings-sample-navigation-js"'), 1)
        self.assertIn('const popup = `<html><body></body></html>`;', first)

    def test_refresh_notice_matching_ignores_script_strings(self):
        script = '<script>const text = `<aside id="wings-ebird-refresh-notice">Keep this string</aside>`;</script>'
        source = '<html><body>' + script + '<aside id="wings-ebird-refresh-notice">Remove banner</aside></body></html>'
        result = updater.remove_refresh_notice(source)
        self.assertIn(script, result)
        self.assertNotIn('Remove banner', result)

    def test_sample_assets_replace_existing_embedded_resource_tags(self):
        source = '<html><body><main>retained</main><link id="wings-sample-navigation-css" rel="stylesheet" href="data:text/css,old"><script id="wings-sample-navigation-js" src="data:text/javascript,old"></script></body></html>'
        result = updater.refresh_sample_html(source, '/* new CSS */', 'const newAsset = true;', updater.module(ROOT, 'refresh_demo_ui'))
        self.assertNotIn('data:text/', result)
        self.assertIn('const newAsset = true;', result)
        self.assertEqual(result.count('id="wings-sample-navigation-js"'), 1)


if __name__ == '__main__':
    unittest.main()
