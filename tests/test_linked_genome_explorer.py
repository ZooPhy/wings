"""Synthetic report-evidence fixtures; no sequence analysis or external services."""
import csv
import importlib.util
import json
import runpy
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("linked_explorer", ROOT / "scripts/build_surveillance_explorer.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def write_tsv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def fixture(base):
    metadata = write_tsv(base / "metadata.tsv", [
        {"sample_id": "complete", "host": "Host A", "collection_date": "2025-01-01", "state": "Arizona", "country": "US", "latitude": "33.4", "longitude": "-112.1"},
        {"sample_id": "partial", "host": "Host B", "collection_date": "2025-01-02", "state": "Unknown", "country": "US", "latitude": "", "longitude": ""},
        {"sample_id": "no_evidence", "host": "Host B", "collection_date": "", "state": "Unknown", "country": "US", "latitude": "", "longitude": ""},
    ])
    coverage = []
    for sample in ("complete", "partial"):
        rows = []
        for segment in mod.SEGMENT_ORDER:
            if sample == "partial" and segment == "NS":
                continue
            missing = sample == "partial" and segment == "MP"
            failed = sample == "partial" and segment == "NA"
            rows.append({
                "sample": sample, "segment": segment, "contig": "" if missing else f"record_{segment}",
                "length": "0" if missing else "1000",
                "median_depth": "NA" if missing else "0" if failed else "120",
                "mean_depth": "NA" if missing else "140", "breadth_covered": "NA" if missing else "0" if failed else "0.98",
                "n_fraction": "NA" if missing else "0",
                "overall_status": "MISSING" if missing else "FAIL" if failed else "PASS",
                "coverage_status": "MISSING" if missing else "FAIL" if failed else "PASS",
                "length_status": "NOT_RECORDED" if missing else "PASS",
                "n_content_status": "NOT_RECORDED" if missing else "PASS",
                "assembly_status": "MISSING" if missing else "PRESENT",
                "selection_status": "MISSING" if missing else "UNIQUE",
                "selection_reason": "No sequence recorded" if missing else "",
                "qc_reason": "Recorded coverage failure" if failed else "",
            })
        coverage.append(write_tsv(base / sample / "coverage/coverage.tsv", rows))
    summaries = []
    genoflu = []
    for sample in ("complete", "partial"):
        summaries.append(write_tsv(base / sample / "summary" / f"{sample}.sample_summary.tsv", [{
            "sample": sample, "genoflu_status": "COMPLETED", "segments_pass": "8" if sample == "complete" else "5",
        }]))
        path = base / sample / "genoflu/GenoFLU.tsv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("consensus Genotype --> DEMO: Synthetic display fixture\n" if sample == "complete"
                        else "sample\tstatus\npartial\tH5_OR_NA_INDETERMINATE\n")
        genoflu.append(path)
    trees = []
    for segment in mod.SEGMENT_ORDER:
        path = base / f"{segment}.newick"
        partial = f",partial__{segment}:0.1" if segment not in ("NA", "MP", "NS") else ""
        path.write_text(f"((complete__{segment}:0.1{partial})95/99:0.1,reference:0.2);")
        trees.append(path)
    return metadata, summaries, trees, coverage, genoflu


def payload_from_fixture(base):
    metadata, summaries, trees, coverage, genoflu = fixture(base)
    return mod.build_payload(metadata, summaries, trees, coverage=coverage, genoflu=genoflu)


class LinkedGenomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.args = fixture(self.base)

    def build(self, trees=None, coverage=None, genoflu=None):
        meta, summaries, default_trees, default_coverage, default_genoflu = self.args
        return mod.build_payload(meta, summaries, default_trees if trees is None else trees,
                                 coverage=default_coverage if coverage is None else coverage,
                                 genoflu=default_genoflu if genoflu is None else genoflu)

    def test_complete_sample_has_all_evidence_and_raw_support(self):
        sample = self.build()["samples"][0]
        self.assertEqual(sample["genotype"]["call"], "DEMO")
        self.assertEqual(len(sample["segments"]), 8)
        for record in sample["segments"].values():
            self.assertEqual(record["overall_status"], "PASS")
            self.assertEqual(record["tree_status"], "PRESENT")
            self.assertEqual(record["tips"][0]["parent_support"], "95/99")
            self.assertEqual(record["median_depth"], 120)
            self.assertEqual(record["breadth_covered"], .98)

    def test_partial_sample_distinguishes_missing_failure_and_tree_absence(self):
        sample = self.build()["samples"][1]
        self.assertIsNone(sample["genotype"]["call"])
        segments = sample["segments"]
        self.assertEqual(segments["NA"]["overall_status"], "FAIL")
        self.assertEqual(segments["NA"]["median_depth"], 0)
        self.assertEqual(segments["NA"]["breadth_covered"], 0)
        self.assertEqual(segments["NA"]["tree_status"], "ABSENT_FROM_TREE")
        self.assertEqual(segments["MP"]["record_status"], "MISSING_SEQUENCE")
        self.assertIsNone(segments["MP"]["median_depth"])
        self.assertEqual(segments["NS"]["record_status"], "NOT_RECORDED")

    def test_no_tree_does_not_erase_qc(self):
        record = self.build(trees=[])["samples"][0]["segments"]["HA"]
        self.assertEqual(record["tree_status"], "NO_TREE")
        self.assertEqual(record["overall_status"], "PASS")

    def test_absent_evidence_does_not_become_zero_or_failure(self):
        sample = self.build()["samples"][2]
        for record in sample["segments"].values():
            self.assertEqual(record["record_status"], "NOT_RECORDED")
            self.assertIsNone(record["median_depth"])
            self.assertEqual(record["overall_status"], "NOT_RECORDED")

    def test_legacy_builder_call_still_works(self):
        meta, summaries, trees, _, _ = self.args
        payload = mod.build_payload(meta, summaries, trees)
        self.assertEqual(payload["samples"][0]["segments"]["NA"]["tree_status"], "PRESENT")
        self.assertIsNone(payload["samples"][0]["segments"]["NA"]["median_depth"])

    def test_duplicate_coverage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate coverage evidence"):
            self.build(coverage=self.args[3] * 2)

    def test_exact_and_longest_sample_id_mapping(self):
        ids = {"bird", "bird__one", "bird_two"}
        self.assertEqual(mod.map_tip_to_sample("bird__one", ids), "bird__one")
        self.assertEqual(mod.map_tip_to_sample("bird__one__NA", ids), "bird__one")
        self.assertEqual(mod.map_tip_to_sample("bird_two_A_NA", ids), "bird_two")
        self.assertIsNone(mod.map_tip_to_sample("birdhouse__NA", ids))

    def test_multiple_tips_keep_individual_support(self):
        tree = self.args[2][0]
        tree.write_text("((complete__a:0.1,ref:0.1)0.8:0.1,(complete__b:0.1,ref2:0.1)NamedClade:0.1);")
        tips = self.build()["samples"][0]["segments"]["HA"]["tips"]
        self.assertEqual([tip["parent_support"] for tip in tips], ["0.8", None])

    def test_disabled_genotype_ignores_stale_output(self):
        result = mod.read_recorded_genotype(self.args[4][0], "DISABLED_BY_CONFIG")
        self.assertIsNone(result["call"])
        self.assertEqual(result["status"], "DISABLED_BY_CONFIG")

    def test_nonfinite_metrics_are_missing_and_json_is_strict(self):
        self.assertIsNone(mod._number("NaN"))
        self.assertIsNone(mod._number("inf"))
        json.dumps(self.build(), allow_nan=False)

    def test_ebird_context_is_preserved(self):
        ebird = write_tsv(self.base / "ebird.tsv", [{
            "sample_id": "complete", "status": "READY", "host": "Host A",
            "collection_date": "2025-01-01", "state": "Arizona", "country": "US",
            "complete_checklists": "10", "reporting_checklists": "2",
            "ebird_species": "Fixture species", "date_from": "2024-12-01",
            "date_to": "2025-02-01", "release": "fixture", "radius_km": "",
        }])
        meta, summaries, trees, coverage, genoflu = self.args
        terms = self.base / "custom_terms.txt"
        citation = self.base / "custom_citation.txt"
        terms.write_text("Synthetic release terms.")
        citation.write_text("Synthetic release citation.")
        old_call = mod.build_payload(meta, summaries, trees, ebird, terms, citation)
        new_call = mod.build_payload(meta, summaries, trees, ebird, terms, citation,
                                     coverage=coverage, genoflu=genoflu)
        self.assertEqual(old_call["ebird_contexts"], new_call["ebird_contexts"])
        self.assertEqual(new_call["ebird_contexts"][0]["reporting_frequency"], .2)
        self.assertEqual(old_call["ebird_attribution"], new_call["ebird_attribution"])
        self.assertEqual(new_call["ebird_attribution"]["terms"], "Synthetic release terms.")
        self.assertEqual(new_call["ebird_attribution"]["citation"], "Synthetic release citation.")
        with self.assertRaisesRegex(ValueError, "eBird context requires"):
            mod.build_payload(meta, summaries, trees, ebird)
        terms.write_text("")
        with self.assertRaisesRegex(ValueError, "must be nonempty"):
            mod.build_payload(meta, summaries, trees, ebird, terms, citation,
                              coverage=coverage, genoflu=genoflu)

    def test_snakemake_entry_point_includes_evidence(self):
        meta, summaries, trees, coverage, genoflu = self.args
        output = self.base / "surveillance_explorer.json"
        snakemake = SimpleNamespace(
            input=SimpleNamespace(metadata=meta, summaries=summaries, trees=trees,
                                  coverage=coverage, genoflu=genoflu, ebird_samples=[]),
            output=SimpleNamespace(json=output),
        )
        runpy.run_path(str(ROOT / "scripts/build_surveillance_explorer.py"),
                       run_name="__main__", init_globals={"snakemake": snakemake})
        payload = json.loads(output.read_text())
        self.assertEqual(payload["samples"][0]["genotype"]["call"], "DEMO")
        self.assertEqual(payload["samples"][0]["segments"]["NA"]["median_depth"], 120)


if __name__ == "__main__":
    unittest.main()
