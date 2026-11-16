"""Regression checks for isolated workflows that reuse the production Explorer rule."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class IsolatedExplorerDependencies(unittest.TestCase):
    def test_disabled_phylodynamics_inputs_evaluate_in_isolated_harness(self):
        tree=ast.parse((ROOT/'tests/integration_ebird_context.py').read_text())
        constants=next(ast.literal_eval(n.value) for n in ast.walk(tree)
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='constants' for t in n.targets))
        namespace={}
        exec(constants.split('rule all:')[0],namespace)
        rule=(ROOT/'Snakefile').read_text().split('rule surveillance_explorer_data:',1)[1].split('output:',1)[0]
        for field in ('phylodynamics','phylodynamics_results'):
            line=next(line.strip() for line in rule.splitlines() if line.strip().startswith(field+'='))
            self.assertEqual(eval(line.split('=',1)[1].rstrip(','),namespace),[])

    def test_isolated_harness_copies_the_required_loader(self):
        tree=ast.parse((ROOT/'tests/integration_ebird_context.py').read_text())
        copied=next(ast.literal_eval(n.iter) for n in ast.walk(tree)
            if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='name' and isinstance(n.iter,ast.Tuple))
        self.assertIn('explorer_phylodynamics.py',copied)
        for filename in copied:
            self.assertTrue((ROOT/'scripts'/filename).is_file(),filename)


if __name__=='__main__':unittest.main()
