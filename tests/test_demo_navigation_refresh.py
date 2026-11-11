import copy
import gzip
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import refresh_demo_navigation as demo


class DemoNavigationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'demo').mkdir()
        for relative in list(demo.ui.ASSETS.values()) + [Path('scripts/report/sample-navigation.css'), Path('scripts/report/sample-navigation.js')]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        summary = ('<html><head><style>.wings-surveillance-explorer .wse-genome-controls{}</style>'
                   '<style>:root{--escape-maroon:red}.report-header{}</style></head><body>'
                   '<div class="report-brand-logo">old logo</div>'
                   '<script>class Explorer {} /* WINGS_MIGRATION_WEAVE_JS_BEGIN */</script>'
                   '<script type="application/json">{"original_data":true}</script></body></html>')
        sample = ('<html><body><aside id="wings-ebird-refresh-notice">Old notice</aside>'
                  '<main>Recorded sample</main><script type="application/json">{"original_call":"retained"}</script></body></html>')
        self.bundle = {'format': 'WINGS_REPORT_BUNDLE', 'version': 1, 'sample_count': 1,
                       'run_summary': {'filename': 'run_summary.html', 'html': summary},
                       'samples': {'s1': {'filename': 's1.sample_summary.html', 'html': sample}},
                       'provenance': {'generated_at': 'original date'}, 'custom': {'retained': True}}
        self.compressed = self.root / 'demo/wings_demo.wings.gz'
        self.compressed.write_bytes(gzip.compress(json.dumps(self.bundle).encode()))
        self.home_patch = patch.object(Path, 'home', return_value=self.root)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def test_gzip_only_refresh_updates_summary_and_sample_and_preserves_data(self):
        original = self.compressed.read_bytes()
        self.assertEqual(demo.refresh(self.root, 'apply'), 0)
        result = demo.codec.unpack_bundle(demo.codec.read_bundle(self.compressed))
        self.assertEqual(result['provenance'], self.bundle['provenance'])
        self.assertEqual(result['custom'], self.bundle['custom'])
        self.assertIn('WINGS_PIPELINE_NAVIGATION_V1', result['run_summary']['html'])
        html = result['samples']['s1']['html']
        self.assertIn('id="wings-sample-navigation-js"', html)
        self.assertIn('.wsp-specimen,.wsp-location', html)
        self.assertIn('font-size:23px', html)
        self.assertIn('"original_call":"retained"', html)
        self.assertIn('Recorded sample', html)
        self.assertNotIn('<aside id="wings-ebird-refresh-notice">', html)
        self.assertFalse((self.root / 'demo/wings_demo.wings').exists())
        backups = list((self.root / '.wings/ui-backups').glob('*/demo/wings_demo.wings.gz'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_preview_and_stale_check_do_not_write(self):
        original = self.compressed.read_bytes()
        self.assertEqual(demo.refresh(self.root), 0)
        self.assertEqual(demo.refresh(self.root, 'check'), 1)
        self.assertEqual(self.compressed.read_bytes(), original)
        self.assertFalse((self.root / '.wings').exists())

    def test_repeat_apply_and_check_are_idempotent(self):
        demo.refresh(self.root, 'apply')
        first = self.compressed.read_bytes()
        self.assertEqual(demo.refresh(self.root, 'check'), 0)
        self.assertEqual(demo.refresh(self.root, 'apply'), 0)
        self.assertEqual(self.compressed.read_bytes(), first)

    def test_existing_raw_copy_is_updated_together_with_gzip(self):
        raw = self.root / 'demo/wings_demo.wings'
        raw.write_text(json.dumps(self.bundle))
        demo.refresh(self.root, 'apply')
        self.assertEqual(gzip.decompress(self.compressed.read_bytes()), raw.read_bytes())

    def test_disagreeing_copies_are_rejected_without_writing(self):
        raw = self.root / 'demo/wings_demo.wings'
        other = copy.deepcopy(self.bundle)
        other['provenance']['generated_at'] = 'different run'
        raw.write_text(json.dumps(other))
        before = self.compressed.read_bytes()
        with self.assertRaisesRegex(ValueError, 'disagree'):
            demo.refresh(self.root, 'apply')
        self.assertEqual(self.compressed.read_bytes(), before)

    def test_compact_bundle_remains_compact_and_reconstructs_samples(self):
        source = copy.deepcopy(self.bundle)
        source['samples']['s2'] = copy.deepcopy(source['samples']['s1'])
        source['samples']['s2']['html'] = source['samples']['s2']['html'].replace('Recorded sample', 'Second sample')
        source['sample_count'] = 2
        for sample in source['samples'].values():
            sample['html'] = sample['html'].replace('<body>', '<body><!--' + 'shared header ' * 400 + '-->')
        packed = demo.codec.pack_bundle(source)
        self.assertTrue('shared' in packed, 'fixture must use compact encoding')
        assets = demo.ui.asset_bytes(self.root)
        css = (self.root / 'scripts/report/sample-navigation.css').read_text()
        js = (self.root / 'scripts/report/sample-navigation.js').read_text()
        result, changed, count = demo.build_refresh(packed, assets, css, js)
        self.assertTrue(changed)
        self.assertEqual(count, 2)
        self.assertTrue('shared' in result, 'compact encoding retained')
        self.assertIn('Recorded sample', demo.codec.unpack_bundle(result)['samples']['s1']['html'])
        demo.codec.verify_roundtrip(result)

    def test_missing_sample_body_rejects_update_without_writing(self):
        self.bundle['samples']['s1']['html'] = 'invalid HTML'
        self.compressed.write_bytes(gzip.compress(json.dumps(self.bundle).encode()))
        before = self.compressed.read_bytes()
        with self.assertRaisesRegex(ValueError, 'closing body'):
            demo.refresh(self.root, 'apply')
        self.assertEqual(self.compressed.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
