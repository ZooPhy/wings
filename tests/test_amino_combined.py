import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('view',ROOT/'scripts/amino_acid_visual_report.py')
view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)

class CombinedLayoutTests(unittest.TestCase):
    def test_one_combined_canvas_and_no_detached_plot(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'report.html';view.render_visual({'samples':[],'rows':[]},'sample\tchange\n',p)
            text=p.read_text()
            self.assertEqual(text.count('id="browser-plot"'),1)
            self.assertNotIn('id="plot"',text)
            self.assertNotIn('id="tracks"',text)
            self.assertNotIn('class="panel segment-browser"',text)
            self.assertIn('Combined mutation and coding landscape',text)
            self.assertIn('Displayed sample',text)
            self.assertIn('function projectEvent',text)
            self.assertNotIn('Go to protein / reference',text)
            self.assertNotIn('id="protein"',text)
            self.assertNotIn('<aside',text)
            self.assertNotIn('Other selected samples only',text)
            self.assertNotIn('id="plot-footnote"',text)
            self.assertNotIn('A54T sits at position 54.',text)
            self.assertNotIn('Select a lollipop',text)
            self.assertIn('<dialog id="mutation-dialog"',text)
            self.assertNotIn('<dialog open',text)
            self.assertNotIn('What do the colors mean?',text)
            self.assertNotIn('Partial comparison',text)
            self.assertIn('From aa',text)
            self.assertNotIn('Each protein has an independent reference amino acid axis',text)
            self.assertNotIn('id="annotation-source"',text)
            self.assertNotIn('id="provenance"',text)
            self.assertNotIn('References, methods and data scope',text)
            self.assertNotIn('Annotation sources and numbering',text)
            self.assertIn('id="constellation-wheel"',text)
            self.assertIn('<details class="sample-picker">',text)
            self.assertNotIn('<details class="sample-picker" open',text)
            self.assertNotIn('class="chips"',text)
            self.assertNotIn('Assessment coverage',text)
            self.assertNotIn('id="coverage"',text)
            self.assertEqual(text.count('id="comparison-reference"'),1)

if __name__=='__main__':unittest.main()
