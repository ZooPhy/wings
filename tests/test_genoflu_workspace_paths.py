import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("safe_genoflu", ROOT / "scripts/run_genoflu_safe.py")
safe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safe)

# Reproduce upstream shell interpolation; testing only Python argument quoting
# would miss the original failure inside GenoFLU.
PROGRAM = '''import argparse, os, pathlib, sys
p = argparse.ArgumentParser()
for option in ("-f", "-i", "-c"):
    p.add_argument(option)
a = p.parse_args()
assert pathlib.Path(a.c).read_text() == "reference key"
assert os.system(f"cat {a.i}/*.fasta > refs.txt") == 0
assert pathlib.Path("refs.txt").read_text() == ">reference\\nACGT\\n"
assert os.system(f"cat {os.path.abspath(a.f)} > query.txt") == 0
assert pathlib.Path("query.txt").read_text() == ">input\\nACGT\\n"
print("diagnostic only", file=sys.stderr)
if os.environ.get("GENOFLU_TEST_FAIL"):
    sys.exit(7)
if not os.environ.get("GENOFLU_TEST_EMPTY"):
    print("consensus Genotype --> TEST: HA:fixture")
'''


class GenofluWorkspacePaths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "WINGS Workspace's é"
        self.root.mkdir()
        self.script = self.root / "environment/bin/genoflu.py"
        self.script.parent.mkdir(parents=True)
        self.script.write_text(PROGRAM)
        self.script.chmod(0o755)
        self.deps = self.script.parent.parent / "dependencies"
        (self.deps / "fastas").mkdir(parents=True)
        (self.deps / "fastas/reference.fasta").write_text(">reference\nACGT\n")
        (self.deps / "genotype_key.xlsx").write_text("reference key")
        self.fasta = self.root / "input with spaces.fasta"
        self.fasta.write_text(">input\nACGT\n")
        self.output = self.root / "results/GenoFLU.tsv"
        self.log = self.root / "results/genoflu.log"

    def execute(self):
        safe.run(self.fasta, self.output, self.log, str(self.script))

    def test_spaces_quotes_unicode_and_custom_tmpdir(self):
        with patch.dict(os.environ, {"TMPDIR": str(self.root)}):
            self.execute()
        self.assertIn("Genotype --> TEST", self.output.read_text())
        self.assertNotIn("diagnostic only", self.output.read_text())
        self.assertIn("diagnostic only", self.log.read_text())
        self.assertEqual(self.script.read_text(), PROGRAM)
        self.assertEqual(self.fasta.read_text(), ">input\nACGT\n")
        self.assertEqual((self.deps / "fastas/reference.fasta").read_text(), ">reference\nACGT\n")

    def test_failure_logged_without_publishing_output(self):
        with patch.dict(os.environ, {"GENOFLU_TEST_FAIL": "1"}):
            with self.assertRaisesRegex(RuntimeError, "status 7"):
                self.execute()
        self.assertFalse(self.output.exists())
        self.assertIn("diagnostic only", self.log.read_text())

    def test_silent_exit_is_not_success(self):
        with patch.dict(os.environ, {"GENOFLU_TEST_EMPTY": "1"}):
            with self.assertRaisesRegex(RuntimeError, "without a genotype"):
                self.execute()
        self.assertFalse(self.output.exists())

    def test_missing_references(self):
        (self.deps / "genotype_key.xlsx").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "reference files"):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_empty_input(self):
        self.fasta.write_text("")
        with self.assertRaisesRegex(ValueError, "empty input"):
            self.execute()

    def test_repeat_uses_isolated_working_directory(self):
        self.execute()
        first = self.output.read_text()
        self.execute()
        self.assertEqual(self.output.read_text(), first)
        self.assertFalse((self.fasta.parent / "refs.txt").exists())

    def test_rule_preserves_gating(self):
        text = (ROOT / "Snakefile").read_text().split("rule genoflu:", 1)[1]
        text = text.split("# Run-level provenance", 1)[0]
        self.assertIn('runner="scripts/run_genoflu_safe.py"', text)
        self.assertIn("python {input.runner:q}", text)
        self.assertIn('"$h5_status" == "DETECTED"', text)
        self.assertIn("H5_NOT_DETECTED", text)
        self.assertIn("H5_OR_NA_INDETERMINATE", text)


if __name__ == "__main__":
    unittest.main()
