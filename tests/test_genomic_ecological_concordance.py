#!/usr/bin/env python3
import importlib.util
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "build_genomic_ecological_concordance.py"
spec = importlib.util.spec_from_file_location("gec", SCRIPT)
gec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gec)


def leaf(sample_id, length):
    return {"name": sample_id, "sample_id": sample_id, "length": length}


def profile(sample_id, shift=0, day="2025-01-01"):
    values = [1 + np.sin((i + shift) * 2 * np.pi / 52) for i in range(52)]
    return {
        "sample_id": sample_id,
        "collection": {"date": day},
        "bins": [{"value": float(v)} for v in values],
    }


def weather_rows(center, temp, precip, wind):
    d = date.fromisoformat(center)
    rows = []
    for offset in range(-3, 4):
        rows.append({
            "date": (d + timedelta(days=offset)).isoformat(),
            "temperature_2m_mean": temp,
            "precipitation_sum": precip,
            "wind_speed_10m_max": wind,
        })
    return rows


def fixture(n=12):
    samples = []
    profiles = []
    bindings = {}
    weather = {}
    tips = []
    date_offsets = [0, 2, 7, 13, 22, 31, 45, 52, 68, 83, 97, 120]
    lats = [35.0, 35.4, 34.8, 36.1, 35.7, 34.5, 36.4, 35.2, 34.9, 36.0, 35.5, 34.6]
    lons = [-90.0, -89.2, -91.1, -90.7, -88.9, -91.5, -89.7, -90.3, -88.8, -91.0, -89.4, -90.6]
    temps = [10, 14, 9, 17, 12, 20, 8, 16, 13, 22, 11, 19]
    precips = [1, 3, 0.5, 5, 2, 7, 1.5, 4, 0.2, 6, 2.5, 8]
    winds = [10, 14, 9, 18, 12, 16, 11, 21, 13, 17, 8, 20]
    for i in range(n):
        sid = f"s{i:02d}"
        day = date(2025, 1, 1) + timedelta(days=date_offsets[i])
        host = "A" if i % 3 else "B"
        samples.append({
            "sample_id": sid,
            "host": host,
            "collection_date": day.isoformat(),
            "latitude": lats[i],
            "longitude": lons[i],
        })
        profiles.append(profile(sid, (0 if host == "A" else 8) + (i % 4), day.isoformat()))
        key = f"w{i}"
        bindings[sid] = {"status": "READY", "weather_key": key}
        weather[key] = {"rows": weather_rows(day.isoformat(), temps[i], precips[i], winds[i])}
        # Unequal topology/branch lengths create nontrivial dyadic response variation.
        tips.append(leaf(sid, 0.01 + (i * i + 3 * i) * 0.0001))
    tree = {"root": {"length": 0.0, "children": tips}}
    return {
        "samples": samples,
        "trees": {"HA": tree},
        "ecological_clock": {"profiles": profiles},
        "ecological_context": {"bindings": bindings, "weather": weather},
    }


class ConcordanceV2Tests(unittest.TestCase):
    def test_patristic_distance_on_star_tree(self):
        root = {"length": 0, "children": [leaf("a", .1), leaf("b", .2)]}
        paths = gec._tree_tip_paths(root)
        self.assertAlmostEqual(gec.patristic_distance(paths["a"], paths["b"]), .3)

    def test_profile_distance_is_zero_for_identical_shape(self):
        self.assertAlmostEqual(gec.seasonal_profile_distance(profile("a"), profile("b")), 0.0, places=10)
        self.assertGreater(gec.seasonal_profile_distance(profile("a"), profile("b", 13)), 0.5)

    def test_environmental_distance_uses_standardized_sample_vectors(self):
        data = fixture(12)
        pairs, samples, scaling = gec.build_pairs(data)
        self.assertEqual(scaling["complete_samples"], 12)
        self.assertFalse(scaling["constant_features"])
        pair = next(r for r in pairs if r["sample_a"] == "s00" and r["sample_b"] == "s01")
        self.assertIsNotNone(pair["environmental_distance"])
        self.assertGreater(pair["environmental_distance"], 0)
        sample = next(r for r in samples if r["sample_id"] == "s00")
        self.assertTrue(sample["environment_vector_available"])

    def test_constant_weather_dimension_contributes_zero_not_failure(self):
        data = fixture(12)
        for weather in data["ecological_context"]["weather"].values():
            for row in weather["rows"]:
                row["wind_speed_10m_max"] = 10.0
        pairs, _, scaling = gec.build_pairs(data)
        self.assertIn("wind_7d_mean_max_kmh", scaling["constant_features"])
        self.assertTrue(any(r["environmental_distance"] is not None for r in pairs))

    def test_nested_hierarchy_and_fdr_are_automatic(self):
        data = fixture(12)
        pairs, _, _ = gec.build_pairs(data)
        models = gec.compare_models(pairs, permutations=19, seed=7, min_unique_samples=8)
        ha = [r for r in models if r["segment"] == "HA"]
        self.assertEqual([r["comparison"] for r in ha], [
            "host_vs_baseline", "ecology_vs_host", "environment_vs_ecology"
        ])
        self.assertTrue(all(r["status"] == "READY" for r in ha))
        self.assertTrue(all(r["n_samples"] == 12 for r in ha))
        self.assertTrue(all(r["n_pairs"] == 66 for r in ha))
        self.assertTrue(all(0 <= r["permutation_p"] <= 1 for r in ha))
        self.assertTrue(all(0 <= r["fdr_q"] <= 1 for r in ha))

    def test_unique_sample_guardrail_blocks_small_segment(self):
        data = fixture(5)
        pairs, _, _ = gec.build_pairs(data)
        models = gec.compare_models(pairs, permutations=9, seed=7, min_unique_samples=8)
        ha = [r for r in models if r["segment"] == "HA"]
        self.assertTrue(all("INSUFFICIENT_SAMPLES" in r["status"] for r in ha))
        self.assertTrue(all(r["n_samples"] == 5 for r in ha))

    def test_missing_weather_preserves_ecology_and_blocks_environment_only(self):
        data = fixture(12)
        data["ecological_context"] = {"bindings": {}, "weather": {}}
        pairs, _, _ = gec.build_pairs(data)
        models = gec.compare_models(pairs, permutations=9, seed=7, min_unique_samples=8)
        eco = next(r for r in models if r["segment"] == "HA" and r["comparison"] == "ecology_vs_host")
        env = next(r for r in models if r["segment"] == "HA" and r["comparison"] == "environment_vs_ecology")
        self.assertEqual(eco["status"], "READY")
        self.assertIn("INSUFFICIENT_SAMPLES", env["status"])
        self.assertEqual(env["n_samples"], 0)

    def test_external_phenology_filters_stale_collection_date(self):
        data = fixture(8)
        data.pop("ecological_clock")
        good = profile("s00", day=data["samples"][0]["collection_date"])
        stale = profile("s01", day="1999-01-01")
        out = gec.overlay_external_context(data, phenology={"profiles": [good, stale]})
        ids = [p["sample_id"] for p in out["ecological_clock"]["profiles"]]
        self.assertEqual(ids, ["s00"])

    def test_external_ecology_rejects_stale_date_or_coordinates(self):
        data = fixture(8)
        sample = data["samples"][0]
        sid = sample["sample_id"]
        key = data["ecological_context"]["bindings"][sid]["weather_key"]
        external = {
            "bindings": {
                sid: {
                    "status": "READY",
                    "weather_key": key,
                    "metadata": {
                        "collection_date": "1999-01-01",
                        "latitude": sample["latitude"],
                        "longitude": sample["longitude"],
                    },
                }
            },
            "weather": {key: data["ecological_context"]["weather"][key]},
        }
        out = gec.overlay_external_context(data, ecological_context=external)
        binding = out["ecological_context"]["bindings"][sid]
        self.assertEqual(binding["status"], "STALE_METADATA")
        self.assertIsNone(binding["weather_key"])

    def test_duplicate_sample_tips_are_not_used(self):
        root = {"length": 0, "children": [leaf("a", .1), leaf("a", .2), leaf("b", .3)]}
        paths = gec._tree_tip_paths(root)
        self.assertNotIn("a", paths)
        self.assertIn("b", paths)

    def test_rank_deficiency_has_report_facing_status(self):
        status, diagnostic = gec._display_status(
            {"status": "READY", "n_samples": 10},
            {"status": "RANK_DEFICIENT", "n_samples": 10, "rank": 5, "columns": 6},
            8,
        )
        self.assertEqual(status, "INSUFFICIENT_INDEPENDENT_VARIATION")
        self.assertIn("rank 5 of 6", diagnostic)

    def test_readiness_counts_distinct_environment_profiles(self):
        result = gec.build(fixture(12), permutations=0, min_unique_samples=8)
        self.assertEqual(result["readiness"]["samples_with_complete_environment_vector"], 12)
        self.assertGreater(result["readiness"]["distinct_environment_profiles"], 1)
        self.assertEqual(result["readiness"]["distinct_weather_contexts"], 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
