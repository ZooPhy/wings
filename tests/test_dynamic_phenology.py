#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

ph = load("ph", ROOT / "scripts/build_ebirdst_phenology.py")
val = load("val", ROOT / "scripts/validate_phenology.py")


class DynamicPhenologyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.tax = self.base / "taxonomy.csv"
        self.tax.write_text(
            "CATEGORY,SPECIES_CODE,PRIMARY_COM_NAME,SCI_NAME\n"
            "species,turvul,Turkey Vulture,Cathartes aura\n"
            "species,blkvul,Black Vulture,Coragyps atratus\n"
            "spuh,vulture1,vulture sp.,Cathartidae sp.\n",
            encoding="utf-8",
        )
        self.host = self.base / "hosts.tsv"
        self.host.write_text("host\tebird_species\nTUVU\tTurkey Vulture\nBLVU\tBlack Vulture\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ebirdst_model_reference_conversion(self):
        class FakeFrame:
            def to_dict(self, orient=None):
                self.orient = orient
                return [
                    {"species_code": "turvul", "common_name": "Turkey Vulture",
                     "scientific_name": "Cathartes aura", "status_version_year": 2023},
                    {"species_code": "yebsap-example", "common_name": "Example",
                     "scientific_name": "Example example", "status_version_year": 2023},
                    {"species_code": "future1", "common_name": "Future Bird",
                     "scientific_name": "Avis futura", "status_version_year": 2024},
                ]
        raw = ph._frame_to_taxonomy_csv(FakeFrame(), 2023).decode("utf-8")
        self.assertIn("turvul,Turkey Vulture,Cathartes aura,2023", raw)
        self.assertNotIn("yebsap-example", raw)
        self.assertNotIn("future1", raw)

    def test_exact_taxonomy_resolution_and_no_fuzzy_guessing(self):
        taxonomy = ph.load_taxonomy(self.tax)
        host_map = ph.load_host_map(self.host)
        taxon, how = ph.resolve_taxon({"host": "TUVU"}, host_map, taxonomy)
        self.assertEqual(taxon["species_code"], "turvul")
        self.assertEqual(how["source"], "WINGS host map")
        taxon2, _ = ph.resolve_taxon({"host": "Turkey Vult"}, {}, taxonomy)
        self.assertIsNone(taxon2)

    def test_status_week_and_bins_cover_full_year(self):
        self.assertEqual(ph.collection_status_week("2025-01-01"), 1)
        self.assertEqual(ph.collection_status_week("2025-01-07"), 1)
        self.assertEqual(ph.collection_status_week("2025-01-08"), 2)
        self.assertEqual(ph.collection_status_week("2025-12-31"), 52)
        bins = ph.projected_bins(2024, list(range(52)))
        self.assertEqual(bins[0]["start"], "2024-01-01")
        self.assertEqual(bins[-1]["end"], "2024-12-31")
        self.assertEqual(len(bins), 52)

    def test_peak_is_contiguous_and_wrap_is_detected(self):
        values = [1.0] * 52
        values[10:13] = [9.2, 10.0, 9.1]
        peak = ph.contiguous_peak(values)
        self.assertEqual((peak["left"], peak["right"]), (10, 12))
        wrap_values = [9.5] + [1.0] * 50 + [10.0]
        wrap = ph.contiguous_peak(wrap_values)
        self.assertTrue(wrap["wraps_year"])

    def test_synthetic_geotiff_produces_clock_compatible_profile(self):
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin

        tif = self.base / "turvul_abundance_median_27km_2023.tif"
        data = np.zeros((52, 2, 2), dtype="float32")
        for i in range(52):
            data[i, :, :] = i + 1
        with rasterio.open(
            tif, "w", driver="GTiff", width=2, height=2, count=52,
            dtype="float32", crs="EPSG:4326", transform=from_origin(-112, 34, 1, 1),
            nodata=-9999,
        ) as dst:
            dst.write(data)

        values = ph.load_raster_values(tif, [(-111.5, 33.5)])[0]
        sample = {
            "sample_id": "s1", "host": "TUVU", "country": "US", "state": "AZ",
            "collection_date": "2025-04-15", "ebird_species": "Turkey Vulture",
            "scientific_name": "Cathartes aura", "ebird_species_code": "turvul",
            "latitude": 33.5, "longitude": -111.5, "status": "PENDING",
        }
        profile = ph.profile_from_sample(sample, values, tif, 2023, "27km", "2026-09-30")
        self.assertEqual(sample["status"], "READY")
        self.assertEqual(profile["sample_id"], "s1")
        self.assertEqual(len(profile["bins"]), 52)
        self.assertEqual(profile["baseline_kind"], "reference_season")
        self.assertEqual(profile["spatial"]["method"], "POINT")

        payload = {
            "schema_version": "wings.phenology.v1", "synthetic": False,
            "inputs": {}, "sample_status": [sample], "profiles": [profile],
        }
        self.assertEqual(val.validate(payload), [])

    def test_missing_coordinates_use_explicit_us_state_fallback(self):
        taxonomy = ph.load_taxonomy(self.tax)
        host_map = ph.load_host_map(self.host)
        rows = [{"sample_id": "s1", "host": "TUVU", "country": "US", "state": "KY", "collection_date": "2025-04-15", "latitude": "", "longitude": ""}]
        samples = ph.resolve_samples(rows, host_map, taxonomy)
        self.assertEqual(samples[0]["status"], "PENDING_REGIONAL")
        self.assertEqual(samples[0]["state_code"], "KY")
        self.assertEqual(samples[0]["spatial_method"], "REGIONAL_STATE_MEAN")
        no_fallback = ph.resolve_samples(rows, host_map, taxonomy, regional_fallback="none")
        self.assertEqual(no_fallback[0]["status"], "MISSING_COORDINATES")

    def test_regional_mean_uses_cells_inside_polygon(self):
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin

        tif = self.base / "regional.tif"
        data = np.zeros((52, 2, 2), dtype="float32")
        for i in range(52):
            data[i] = np.array([[1+i, 10+i], [3+i, 30+i]], dtype="float32")
        with rasterio.open(
            tif, "w", driver="GTiff", width=2, height=2, count=52, dtype="float32",
            crs="EPSG:4326", transform=from_origin(0, 2, 1, 1), nodata=-9999,
        ) as dst:
            dst.write(data)
        polygon = {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,2],[0,2],[0,0]]]}
        values, counts = ph.regional_raster_mean(tif, polygon)
        self.assertEqual(counts[0], 2)
        self.assertAlmostEqual(values[0], 2.0)
        self.assertAlmostEqual(values[51], 53.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
