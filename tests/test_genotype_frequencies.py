import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("frequencies", Path(__file__).parents[1] / "scripts/build_genotype_frequencies.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrequenciesTest(unittest.TestCase):
    def test_uploaded_schema_and_unassigned_labels(self):
        rows = module.read_table(b'sample\tGenotype\nSRR1\tD1.1\nSRR2\tNot assigned: Only 7 segments\n', ("sample", "Genotype"))
        result = module.build_snapshot(rows)
        self.assertEqual(result["audit"]["included_runs"], 2)
        self.assertEqual(result["audit"]["assigned_runs"], 1)
        self.assertFalse(result["has_metadata"])
        self.assertTrue(all(row["month"] is None for row in result["groups"]))

    def test_left_join_counts_metadata_runs_once(self):
        g = [{"sample": "SRR1", "Genotype": "D1.1"}, {"sample": "SRR1", "Genotype": "D1.1"}, {"sample": "SRR3", "Genotype": "B3.13"}]
        m = [{"Run": "SRR1", "Collection_Date": "2025-03-05", "Host": "Bird"}, {"Run": "SRR2", "Collection_Date": "2025-03"}]
        result = module.build_snapshot(g, m + [dict(m[0])])
        self.assertEqual(result["audit"]["included_runs"], 2)
        self.assertEqual(result["audit"]["duplicate_genotype_rows_collapsed"], 1)
        self.assertEqual(result["audit"]["duplicate_metadata_rows_collapsed"], 1)
        self.assertEqual(result["audit"]["metadata_runs_without_genotype_result"], 1)
        self.assertEqual(result["audit"]["genotype_runs_outside_metadata"], 1)
        self.assertEqual({row["month"] for row in result["groups"]}, {"2025-03"})
        self.assertEqual(sum(row["n"] for row in result["groups"]), 2)

    def test_conflicting_calls_are_not_resolved_using_analysis_date(self):
        g = [{"sample": "SRR1", "Genotype": "D1.1", "date": "2025-01-01"}, {"sample": "SRR1", "Genotype": "B3.13", "date": "2026-01-01"}]
        result = module.build_snapshot(g)
        self.assertEqual(result["groups"][0]["status"], "conflicting_calls")
        self.assertEqual(result["audit"]["assigned_runs"], 0)

    def test_different_failure_messages_do_not_create_fake_genotypes(self):
        g = [{"sample": "SRR1", "Genotype": "Not assigned: only 2"}, {"sample": "SRR1", "Genotype": "Not assigned: only 3"}]
        result = module.build_snapshot(g)
        self.assertEqual(result["groups"][0]["status"], "unassigned")

    def test_ambiguous_metadata_does_not_silently_duplicate_a_run(self):
        g = [{"sample": "SRR1", "Genotype": "D1.1"}]
        m = [{"Run": "SRR1", "Collection_Date": "2025-02"}, {"Run": "SRR1", "Collection_Date": "2025-03"}]
        with self.assertRaisesRegex(ValueError, "Conflicting collection metadata"):
            module.build_snapshot(g, m)

    def test_month_precision_preserved_and_year_only_not_imputed(self):
        for raw, expected in [("2025-01-31", "2025-01"), ("2025-02", "2025-02"), ("2024-02-29", "2024-02"), ("2025-02-29", None), ("2025", None), ("2025-13", None), ("", None), ("2025-05-09_10-49-10", None), ("not collected", None)]:
            self.assertEqual(module.collection_month(raw), expected, raw)

    def test_unknown_date_retained_in_overall_counts(self):
        g = [{"sample": "SRR1", "Genotype": "D1.1"}]
        m = [{"Run": "SRR1", "Collection_Date": "2025"}]
        result = module.build_snapshot(g, m)
        self.assertEqual(result["audit"]["assigned_runs"], 1)
        self.assertEqual(result["audit"]["assigned_runs_without_collection_month"], 1)

    def test_unknown_calls_and_missing_calls_are_explicit(self):
        for value, status in [("", "missing_call"), ("NA", "missing_call"), ("Not assigned", "unassigned"), ("error", "unrecognized_call"), ("D1.1 / B3.13", "unrecognized_call"), ("Minor114", "assigned")]:
            self.assertEqual(module.call_status(value)[0], status)

    def test_invalid_headers_and_rows_fail(self):
        for text in [b'sample\tGenotype\tGenotype\nA\tB\tC\n', b'sample\tgenotype\nA\tD1.1\n', b'sample\tGenotype\nA\tD1.1\textra\n', b'sample\tGenotype\n']:
            with self.assertRaises(ValueError):
                module.read_table(text, ("sample", "Genotype"))

    def test_empty_key_fails(self):
        with self.assertRaises(ValueError):
            module.build_snapshot([{"sample": "", "Genotype": "D1.1"}])


if __name__ == "__main__":
    unittest.main()
