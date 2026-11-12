import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('refresh_ui', ROOT / 'scripts/refresh_demo_ui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class DepthLabelTests(unittest.TestCase):
    def test_only_the_coverage_label_and_description_change(self):
        body = ("const metric='subtype_min_median_depth'; const cls='wco-depth';"
                "const title='" + ui.DEPTH_TITLE_OLD + "';const note='" + ui.DEPTH_NOTE_OLD + "';"
                "const value=321687; const scale=Math.log10(value+1);")
        data = '<script type="application/json">{"value":321687,"label":"' + ui.DEPTH_TITLE_OLD + '"}</script>'
        source = '<html><body><script>' + body + '</script>' + data + '</body></html>'
        updated = ui.clarify_coverage_depth_label(source)
        self.assertEqual(updated, source.replace(body, body.replace(ui.DEPTH_TITLE_OLD, ui.DEPTH_TITLE).replace(ui.DEPTH_NOTE_OLD, ui.DEPTH_NOTE)))
        self.assertIn(data, updated)
        self.assertIn('const value=321687; const scale=Math.log10(value+1);', updated)
        self.assertEqual(ui.data_scripts(ui.ReportHTML(source)), ui.data_scripts(ui.ReportHTML(updated)))
        self.assertEqual(ui.clarify_coverage_depth_label(updated), updated)

    def test_unrelated_scripts_and_json_are_preserved(self):
        source = ('<html><body><script>const title="' + ui.DEPTH_TITLE_OLD + '";</script>'
                  '<script type="application/json">{"class":"wco-depth","metric":"subtype_min_median_depth","label":"' + ui.DEPTH_TITLE_OLD + '"}</script></body></html>')
        self.assertEqual(ui.clarify_coverage_depth_label(source), source)


if __name__ == '__main__':
    unittest.main()
