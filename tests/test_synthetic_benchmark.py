"""Standard-library tests: python -m unittest discover -s tests -p test_synthetic_benchmark.py"""
import copy
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_synthetic.py"
SPEC = importlib.util.spec_from_file_location("benchmark_synthetic", SCRIPT)
BENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCH)


def report():
    row = {"wall_seconds": 2.0, "cpu_seconds": 1.5,
           "peak_rss_bytes": 1000, "output_sha256": "a" * 64}
    return {"format": BENCH.FORMAT, "label": "test", "script_sha256": "source",
            "settings": {"workload": BENCH.WORKLOAD, "items": 100, "seed": 1, "repeats": 2, "warmups": 0},
            "environment": {"system": "test", "machine": "test"},
            "runs": [row, copy.deepcopy(row)]}


class SyntheticBenchmarkTests(unittest.TestCase):
    def test_known_output(self):
        expected = hashlib.sha256(struct.pack("<III", 1015568748, 1586005467, 2165703038)).hexdigest()
        self.assertEqual(BENCH.synthetic_workload(3, 1), expected)

    def test_compare_uses_rows_and_records_environment_difference(self):
        baseline = report()
        candidate = copy.deepcopy(baseline)
        candidate["summary"] = {"wall_seconds": {"median": 999}}
        candidate["environment"]["machine"] = "other"
        for row in candidate["runs"]:
            row["wall_seconds"] = 1.0
        comparison = BENCH.compare(baseline, candidate)
        self.assertEqual(comparison["candidate_over_baseline_median"]["wall_seconds"], 0.5)
        self.assertIn("machine", comparison["environment_differences"])

    def test_mismatched_workload_rejected(self):
        baseline = report()
        candidate = copy.deepcopy(baseline)
        candidate["settings"]["items"] = 200
        with self.assertRaisesRegex(ValueError, "identical"):
            BENCH.compare(baseline, candidate)

    def test_inconsistent_repeats_rejected(self):
        baseline = report()
        baseline["runs"][1]["output_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "within a report"):
            BENCH.compare(baseline, report())

    def test_different_outputs_rejected(self):
        candidate = report()
        for row in candidate["runs"]:
            row["output_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "comparison rejected"):
            BENCH.compare(report(), candidate)

    def test_missing_memory_is_explicit(self):
        candidate = report()
        for row in candidate["runs"]:
            row["peak_rss_bytes"] = None
        result = BENCH.compare(report(), candidate)
        self.assertIsNone(result["candidate_over_baseline_median"]["peak_rss_bytes"])

    def test_invalid_measurement_rejected(self):
        candidate = report()
        candidate["runs"][0]["wall_seconds"] = float("nan")
        with self.assertRaisesRegex(ValueError, "Invalid measurement"):
            BENCH.compare(report(), candidate)

    def test_cli_records_repeats_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark.json"
            command = [sys.executable, str(SCRIPT), "run", "--items", "1000", "--repeats", "2",
                       "--warmups", "1", "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = output.read_bytes()
            recorded = json.loads(original)
            self.assertEqual(len(recorded["runs"]), 2)
            BENCH.validate_report(recorded)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_bytes(), original)
            result = subprocess.run([sys.executable, str(SCRIPT), "compare", str(output), str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["candidate_over_baseline_median"]["wall_seconds"], 1)


if __name__ == "__main__":
    unittest.main()
