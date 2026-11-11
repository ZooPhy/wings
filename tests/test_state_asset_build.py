import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('state_builder', ROOT / 'scripts/build_state_assets.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class StateAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.folder = self.repo / 'assets/states'
        self.folder.mkdir(parents=True)
        self.svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 100"><metadata>retained</metadata><path d="M0 0h10v10z"/></svg>'

    def test_name_code_and_original_svg_bytes_are_preserved(self):
        (self.folder / 'New_York_NY.svg').write_bytes(self.svg)
        source = builder.build(self.repo)
        catalog = json.loads(source.split(' = ', 1)[1].rstrip(';\n'))
        self.assertEqual(catalog[0]['name'], 'New York')
        self.assertEqual(catalog[0]['code'], 'NY')
        self.assertEqual(base64.b64decode(catalog[0]['src'].split(',')[1]), self.svg)
        self.assertEqual((self.folder / 'New_York_NY.svg').read_bytes(), self.svg)

    def test_catalog_order_is_stable(self):
        for name in ['New_York_NY.svg', 'Kentucky_KY.svg']:
            (self.folder / name).write_bytes(self.svg)
        one = builder.build(self.repo)
        self.assertEqual(one, builder.build(self.repo))
        self.assertLess(one.index('Kentucky'), one.index('New York'))

    def test_empty_folder_reports_missing_drawings(self):
        with self.assertRaisesRegex(ValueError, 'No drawings found'):
            builder.build(self.repo)

    def test_invalid_filename_is_reported(self):
        (self.folder / 'unknown.svg').write_bytes(self.svg)
        with self.assertRaisesRegex(ValueError, 'State_Name_AB.svg'):
            builder.build(self.repo)

    def test_duplicate_codes_are_rejected(self):
        for name in ['Kentucky_KY.svg', 'Other_KY.svg']:
            (self.folder / name).write_bytes(self.svg)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            builder.build(self.repo)

    def test_active_svg_is_rejected(self):
        (self.folder / 'Kentucky_KY.svg').write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        with self.assertRaisesRegex(ValueError, 'Active content'):
            builder.build(self.repo)


if __name__ == '__main__':
    unittest.main()
