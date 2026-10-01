import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("builder", ROOT / "scripts/build_surveillance_explorer.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CoverageContextTests(unittest.TestCase):
    def samples(self):
        return [
            {"sample_id":"a","segments_pass":8,"potential_subtype":"H5N1"},
            {"sample_id":"b","segments_pass":3,"potential_subtype":"Unknown"},
            {"sample_id":"c","segments_pass":0,"potential_subtype":"Undetermined"},
        ]

    def write(self, text):
        td = tempfile.TemporaryDirectory()
        p = Path(td.name) / "effort.tsv"
        p.write_text(text)
        return td, p

    def test_not_configured_retains_wings_genomic_summary(self):
        ctx = mod.build_coverage_context(None, self.samples())
        self.assertEqual(ctx["status"], "NOT_CONFIGURED")
        self.assertEqual(ctx["genomic_summary"]["wings_records"], 3)
        self.assertEqual(ctx["genomic_summary"]["at_least_one_qc_segment"], 2)
        self.assertEqual(ctx["genomic_summary"]["complete_8_segment_genomes"], 1)
        self.assertEqual(ctx["genomic_summary"]["subtype_resolved"], 1)

    def test_ready_context_preserves_missing_vs_zero_and_aggregates_periods(self):
        td, p = self.write(
            "period_start\tperiod_end\tstate\thost\tsampled\ttested\tpositive\tsequenced\n"
            "2025-01-01\t2025-01-31\tKY\tBLVU\t100\t90\t0\t5\n"
            "2025-02-01\t2025-02-28\tKY\tBLVU\t120\t100\t10\tNA\n"
        )
        try:
            ctx = mod.build_coverage_context(p, self.samples())
        finally:
            td.cleanup()
        self.assertEqual(ctx["status"], "READY")
        self.assertEqual(ctx["record_count"], 2)
        self.assertEqual(ctx["records"][0]["positive"], 0)
        self.assertIsNone(ctx["records"][1]["sequenced"])
        self.assertEqual(ctx["periods"][1]["tested"], 100)
        self.assertEqual(ctx["comparison"]["prior"]["positive"], 0)
        self.assertEqual(ctx["comparison"]["recent"]["positive"], 10)

    def test_invalid_hierarchy_is_rejected(self):
        td, p = self.write(
            "period_start\tperiod_end\tsampled\ttested\tpositive\n"
            "2025-01-01\t2025-01-31\t10\t12\t3\n"
        )
        try:
            with self.assertRaisesRegex(ValueError, "tested cannot exceed sampled"):
                mod.build_coverage_context(p, self.samples())
        finally:
            td.cleanup()

    def test_non_integer_counts_are_rejected(self):
        td, p = self.write(
            "period_start\tperiod_end\ttested\tpositive\n"
            "2025-01-01\t2025-01-31\t10.5\t2\n"
        )
        try:
            with self.assertRaisesRegex(ValueError, "non-negative integer"):
                mod.build_coverage_context(p, self.samples())
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
