#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "attach_genomic_ecological_concordance.py"
spec = importlib.util.spec_from_file_location("attach_gec", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ConcordanceReportAttachmentTests(unittest.TestCase):
    def fixture(self):
        return {
            "schema_version": "wings.genomic_ecological_concordance.v2",
            "analysis_kind": "exploratory_dyadic_model_comparison",
            "response": "distance",
            "model_tiers": {"M0_spatiotemporal": ["temporal_days", "geographic_km"]},
            "comparisons": ["host_vs_baseline"],
            "readiness": {"total_samples": 10},
            "weather_summary": "7 day",
            "environmental_distance": {"method": "euclidean", "standardization_scope": "run", "scaling": {"large": True}},
            "seasonal_profile_metric": "1-r",
            "permutation_test": {"method": "permutation"},
            "models": [{"segment": "HA", "comparison": "host_vs_baseline", "display_status": "READY"}],
            "sample_features": [{"sample_id": "a"}],
            "pairs": [{"sample_a": "a", "sample_b": "b"}],
            "caveats": ["exploratory"],
        }

    def test_compact_payload_keeps_models_but_not_pair_table(self):
        compact = mod.compact_concordance(self.fixture())
        self.assertEqual(compact["models"][0]["segment"], "HA")
        self.assertNotIn("pairs", compact)
        self.assertNotIn("sample_features", compact)
        self.assertNotIn("scaling", compact["environmental_distance"])

    def test_attach_preserves_explorer_and_adds_module(self):
        explorer = {"title": "WINGS", "samples": [{"sample_id": "a"}]}
        out = mod.attach(explorer, self.fixture())
        self.assertEqual(out["title"], "WINGS")
        self.assertIn("genomic_ecological_concordance", out)

    def test_rejects_wrong_schema(self):
        data = self.fixture()
        data["schema_version"] = "wrong"
        with self.assertRaisesRegex(ValueError, "Unsupported concordance schema"):
            mod.compact_concordance(data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
