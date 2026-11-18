"""The sensitivity rule must create every report it declares, even when blocked."""
import json
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from phylodynamic_selection import write_json


class ReportOutputs(unittest.TestCase):
    def test_blocked_primary_still_produces_all_declared_reports(self):
        rules = (REPO / 'rules/phylodynamics.smk').read_text()
        rule = rules.split('    rule phylodynamic_sensitivity:', 1)[1]
        body = []
        for line in rule.split('        run:\n', 1)[1].splitlines():
            if line and not line.startswith('            '):
                break
            body.append(line)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            key = 'HA/balanced/replicate_1'
            write_json(root / 'selection/selection_summary.json', dict(
                config=dict(segments=['HA'], strategies=['balanced']), replicates=[dict(id=key)]))
            write_json(root / 'inference' / key / 'result.json', dict(id=key, segment='HA',
                strategy='balanced', replicate=1, study=2, references=0,
                status='blocked', reasons=['temporal_screen_failed'], introductions={}))
            scope = dict(Path=Path, PHYLODYNAMIC_SELECTION=str(root / 'selection'), PHYLODYNAMIC_DIR=str(root))
            exec(compile(textwrap.dedent('\n'.join(body)), 'sensitivity_rule', 'exec'), scope)
            for name in ('summary.json', 'sensitivity.html', 'primary_movie.json', 'comparison.html'):
                self.assertTrue((root / name).is_file(), name)
            self.assertTrue((root / 'comparison_assets/phylodynamic-comparison.css').is_file())
            self.assertIsNone(json.loads((root / 'primary_movie.json').read_text()))
            self.assertEqual(json.loads((root / 'summary.json').read_text())['analyses'][0]['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
