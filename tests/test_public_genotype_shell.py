"""Exercise the production shell template and argument parser without networking."""
import ast
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicGenotypeShellTests(unittest.TestCase):
    def test_optional_flags_survive_shell_trimming(self):
        source = (ROOT / 'Snakefile').read_text()
        start = re.search(r'^rule public_genotype_snapshot:\s*$', source, re.M)
        self.assertIsNotNone(start)
        tail = source[start.end():]
        end = re.search(r'^\S', tail, re.M)
        rule = tail[:end.start()] if end else tail
        match = re.search(r'    shell:\s*\n\s*(r?""".*?""")', rule, re.S)
        self.assertIsNotNone(match)
        template = ast.literal_eval(match[1])
        cli = (ROOT / 'scripts/prepare_public_genotype_snapshot.py').read_text()
        main = next(node for node in ast.parse(cli).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'main')
        main_source = ast.get_source_segment(cli, main)
        with tempfile.TemporaryDirectory(prefix='wings genotype spaces ') as folder:
            root = Path(folder)
            recorder = root / 'CLI parser.py'
            # Execute the real argument parser, replacing only its network/data
            # operation with an argument recorder. No modules are imported from
            # the project's refresh implementation and no snapshots are changed.
            recorder.write_text(
                'import argparse, json\nfrom pathlib import Path\n'
                'def prepare(*args):\n    print(json.dumps([str(v) if isinstance(v, Path) else v for v in args]))\n'
                + main_source + '\nmain()\n')
            for offline in (False, True):
                for prepared in (False, True):
                    with self.subTest(offline=offline, prepared=prepared):
                        # Quotes, spaces and shell punctuation must remain literal.
                        seed = str(root / "seed's data;$(false).json")
                        output = str(root / 'output data.json')
                        cache = str(root / 'cache directory')
                        values = {
                            'input.script:q': shlex.quote(str(recorder)),
                            'input.seed:q': shlex.quote(seed),
                            'output.json:q': shlex.quote(output),
                            'params.cache:q': shlex.quote(cache),
                            'params.ref:q': shlex.quote('master'),
                            'params.age': '7.0',
                            'params.offline': '--offline' if offline else '',
                            'params.prepared': '--prepared' if prepared else '',
                        }
                        command = template
                        for name, value in values.items():
                            command = command.replace('{' + name + '}', value)
                        command = command.strip()
                        command = re.sub(r'^python\b', shlex.quote(sys.executable), command, count=1)
                        result = subprocess.run(['bash', '-c', 'set -euo pipefail; ' + command],
                                                text=True, capture_output=True, timeout=10)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        import json
                        actual = json.loads(result.stdout)
                        self.assertEqual(actual, [seed, output, prepared, cache, 'master', 7.0, offline])


if __name__ == '__main__':
    unittest.main()
