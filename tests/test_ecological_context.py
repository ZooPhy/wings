"""Ecological display/cache tests use synthetic data and no network."""
import csv
import importlib.util
import io
import json
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("ecology", ROOT / "scripts/build_ecological_context.py")
eco = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eco)
spec = importlib.util.spec_from_file_location("explorer", ROOT / "scripts/build_surveillance_explorer.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def weather(extended=False):
    result = {"latitude": 33.5, "longitude": -112.0, "timezone": "America/Phoenix",
            "daily_units": eco.WEATHER_FIELDS,
            "daily": {"time": ["2025-04-01", "2025-04-02", "2025-04-03"],
                      "temperature_2m_mean": [-2, None, 20], "precipitation_sum": [0, None, 3],
                      "wind_speed_10m_max": [12, None, 18]}}

    if extended:
        result["daily_units"] = dict(eco.ALL_WEATHER_FIELDS)
        result["daily"].update(temperature_2m_min=[-5, None, 16], temperature_2m_max=[1, None, 24], weather_code=[0, None, 63])
    return result


class EcologyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.meta = self.base / "metadata.tsv"
        self.meta.write_text("sample_id\tcountry\tstate\tcollection_date\tlatitude\tlongitude\n"
                             "a\tUS\tArizona\t2025-04-02\t33.45\t-112.07\n"
                             "b\tUS\tArizona\t2025-04-02\t33.45\t-112.07\n"
                             "state_only\tUS\tArizona\t2025-04-02\t\t\n")

    def fake_opener(self, url, timeout):
        self.calls.append(url)
        return io.BytesIO(json.dumps(weather(extended=True)).encode())

    def cached(self):
        self.calls = []
        return eco.build_snapshot(self.meta, self.base / "cache", 30, True, opener=self.fake_opener)

    def bird(self, rows):
        path = self.base / "bird.csv"
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["state", "night", "timezone", "birds_crossed", "status", "reason"])
            writer.writeheader(); writer.writerows(rows)
        prov = self.base / "bird.provenance.json"
        eco.write_json(prov, {"source_url":"https://dashboard.birdcast.org/region/US-AZ", "retrieved_on":"2025-04-04",
                              "citation":"Synthetic test", "reuse_basis":"Synthetic fixture; no BirdCast data", "sha256":eco.digest(path.read_bytes())})
        return path, prov

    def test_offline_by_default_and_state_only_has_no_weather(self):
        def forbidden(*args, **kwargs):
            self.fail("Offline build attempted a network request")
        result = eco.build_snapshot(self.meta, self.base, opener=forbidden)
        self.assertEqual(result["bindings"]["a"]["status"], "NOT_LOADED")
        self.assertEqual(result["bindings"]["state_only"]["status"], "MISSING_COORDINATES")
        self.assertEqual(result["birdcast"]["status"], "NOT_LOADED")

    def test_request_pins_model_units_and_deduplicates_locations(self):
        result = self.cached()
        self.assertEqual(len(self.calls), 1)
        query = parse_qs(urlsplit(self.calls[0]).query)
        self.assertEqual(query["models"], ["era5"])
        self.assertEqual(query["timezone"], ["auto"])
        self.assertEqual(query["elevation"], ["nan"])
        self.assertNotIn("sample_id", query)
        self.assertEqual(len(result["weather"]), 1)
        self.calls = []
        again = eco.build_snapshot(self.meta, self.base / "cache", opener=self.fake_opener)
        self.assertEqual(self.calls, [])
        self.assertEqual(result["weather"], again["weather"])

    def test_null_zero_negative_temperature_and_timezone_survive(self):
        result = self.cached()
        data = next(iter(result["weather"].values()))
        self.assertEqual(data["rows"][0]["precipitation_sum"], 0)
        self.assertIsNone(data["rows"][1]["precipitation_sum"])
        self.assertEqual(data["rows"][0]["temperature_2m_mean"], -2)
        self.assertEqual(data["timezone"], "America/Phoenix")
        self.assertEqual(data["grid_latitude"], 33.5)
        json.dumps(result, allow_nan=False)

    def test_weather_units_dates_nonfinite_and_cache_tampering_rejected(self):
        for mutate in (lambda d: d["daily_units"].update(precipitation_sum="inch"),
                       lambda d: d["daily"]["time"].__setitem__(1,"2025-04-01"),
                       lambda d: d["daily"]["precipitation_sum"].__setitem__(0,float("nan"))):
            data = weather(); data["daily_units"] = dict(eco.WEATHER_FIELDS); mutate(data)
            with self.assertRaises(ValueError):
                eco.normalize_weather(json.dumps(data).encode(), "https://example.org", "test")
        self.cached()
        cache = next((self.base / "cache/weather").glob("*.json"))
        data = json.loads(cache.read_text()); data["raw"] += " "
        eco.write_json(cache,data)
        with self.assertRaisesRegex(ValueError, "checksum"):
            eco.build_snapshot(self.meta,self.base / "cache")

    def test_stale_metadata_does_not_reuse_sample_weather(self):
        result = self.cached(); path = self.base / "context.json"; eco.write_json(path,result)
        samples = eco.read_metadata(self.meta)
        samples[0]["latitude"] = "34"
        loaded = eco.load_snapshot(path,samples)
        self.assertEqual(loaded["bindings"]["a"]["status"], "STALE_METADATA")
        self.assertIsNone(loaded["bindings"]["a"]["weather_key"])
        self.assertEqual(loaded["bindings"]["b"]["status"], "READY")

    def test_birdcast_zero_missing_duplicates_timezone_and_hash(self):
        rows = [{"state":"AZ", "night":"2025-04-01", "timezone":"America/Phoenix", "birds_crossed":"0", "status":"AVAILABLE", "reason":""},
                {"state":"Arizona", "night":"2025-04-02", "timezone":"America/Phoenix", "birds_crossed":"", "status":"UNAVAILABLE", "reason":"Synthetic radar gap"}]
        path,prov = self.bird(rows)
        data = eco.birdcast_snapshot(path,prov)
        self.assertEqual(data["records"][0]["birds_crossed"],0)
        self.assertIsNone(data["records"][1]["birds_crossed"])
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            eco.birdcast_snapshot(*self.bird(rows+[rows[0]]))
        rows[0]["timezone"] = "not-a-timezone"
        with self.assertRaisesRegex(ValueError,"timezone"):
            eco.birdcast_snapshot(*self.bird(rows))
        rows[0]["timezone"] = "America/Phoenix"
        path,prov = self.bird(rows); path.write_text(path.read_text()+"\n")
        with self.assertRaisesRegex(ValueError,"checksum"):
            eco.birdcast_snapshot(path,prov)

    def test_invalid_dates_coordinates_and_fetch_failures_are_explicit(self):
        meta = eco.sample_metadata(eco.read_metadata(self.meta)[0]); meta["collection_date"] = "2025-02-30"
        self.assertEqual(eco.weather_request(meta,30)[1],"MISSING_DATE")
        meta["latitude"] = 100
        self.assertEqual(eco.weather_request(meta,30)[1],"MISSING_COORDINATES")
        def failed(*args,**kwargs): raise OSError("offline")
        result = eco.build_snapshot(self.meta,self.base,fetch_weather=True,opener=failed)
        self.assertEqual(result["bindings"]["a"]["status"],"FETCH_FAILED")
        self.assertEqual(result["weather"],{})

    def test_builder_legacy_and_snakemake_load_offline_context(self):
        snapshot = self.base / "eco.json"; eco.write_json(snapshot,self.cached())
        payload = builder.build_payload(self.meta,[],[],ecological_context=snapshot)
        self.assertEqual(payload["ecological_context"]["bindings"]["a"]["status"],"READY")
        self.assertIsNone(builder.build_payload(self.meta,[],[])["ecological_context"])
        output=self.base / "explorer.json"
        snake=SimpleNamespace(input=SimpleNamespace(metadata=str(self.meta),summaries=[],trees=[],ecological_context=[str(snapshot)],ecological_loader=str(ROOT / "scripts/build_ecological_context.py")),output=SimpleNamespace(json=str(output)))
        runpy.run_path(str(ROOT / "scripts/build_surveillance_explorer.py"),run_name="__main__",init_globals={"snakemake":snake})
        self.assertEqual(json.loads(output.read_text())["ecological_context"]["bindings"]["a"]["status"],"READY")


if __name__ == "__main__": unittest.main()
