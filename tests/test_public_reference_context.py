"""Synthetic metadata and trees; no biological sequences or network requests."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import runpy
from types import SimpleNamespace
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_surveillance_explorer.py"
spec = importlib.util.spec_from_file_location("reference_builder", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def inputs(root):
    metadata = root / "samples.tsv"
    metadata.write_text("sample_id\thost\tcollection_date\tcountry\tstate\nlocal\tSynthetic host\t2025-01-01\tUS\tArizona\n")
    rows = [dict(reference_id="synthetic-linked", segment=seg, tip_label="public_" + seg,
                 accession_version=acc, isolate="Synthetic fixture", host="Example host",
                 collection_date="2024-12", country="US", state="", linkage_basis="Synthetic shared record ID")
            for seg, acc in [("HA", "ZZ999991.1"), ("NA", "ZZ999992.1")]]
    trees = []
    for seg in ("HA", "NA", "PB2"):
        tree = root / f"{seg}_Tree.newick"
        tree.write_text(f"((local__{seg}:0.1,public_{seg}:0.2)95/99:0.1,unannotated:0.3);")
        trees.append(tree)
    return metadata, rows, trees


def manifest(root, rows, **changes):
    path, provenance = root / "manifest.tsv", root / "provenance.json"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    meta = dict(manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                retrieved_on="2025-01-02", selection_notes="Synthetic test only", citation="Synthetic fixture")
    meta.update(changes)
    provenance.write_text(json.dumps(meta))
    return path, provenance


class PublicReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.metadata, self.rows, self.trees = inputs(self.root)

    def build(self, **changes):
        path, prov = manifest(self.root, self.rows, **changes)
        return builder.build_payload(self.metadata, [], self.trees,
                                     reference_manifest=path, reference_provenance=prov)

    def test_exact_mapping_keeps_sample_qc_and_support_separate(self):
        p = self.build()
        group = p["public_reference_context"]["references"][0]
        self.assertEqual(group["segments"]["HA"]["status"], "PRESENT")
        self.assertEqual(group["segments"]["HA"]["tips"][0]["parent_support"], "95/99")
        self.assertEqual(group["segments"]["PB2"]["status"], "NOT_IN_MANIFEST")
        self.assertEqual(group["segments"]["NS"]["status"], "NO_TREE")
        self.assertEqual(group["collection_date"], "2024-12")
        self.assertEqual(group["collection_date_precision"], "month")
        self.assertNotIn("coverage", group)
        self.assertEqual(p["trees"]["HA"]["public_reference_tip_count"], 1)
        self.assertEqual(p["trees"]["HA"]["unmatched_tip_count"], 1)
        self.assertEqual(p["samples"][0]["segments"]["HA"]["tree_status"], "PRESENT")
        self.assertEqual(p["trees"]["HA"]["source_sha256"], hashlib.sha256(self.trees[0].read_bytes()).hexdigest())

    def test_disabled_import_retains_unannotated_tree(self):
        p = builder.build_payload(self.metadata, [], self.trees)
        self.assertIsNone(p["public_reference_context"])
        self.assertEqual(p["trees"]["HA"]["unmatched_tip_count"], 2)

    def test_stale_manifest_rejected(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.build(manifest_sha256="bad")

    def test_unversioned_accession_allowed(self):
        self.rows[0]["accession_version"] = "ZZ999991"
        p = self.build()
        self.assertIsNotNone(p["public_reference_context"])

    def test_no_guessed_cross_segment_linkage(self):
        for row in self.rows:
            row["reference_id"] = row["linkage_basis"] = ""
        groups = self.build()["public_reference_context"]["references"]
        self.assertEqual(len(groups), 2)

    def test_linked_group_needs_evidence(self):
        self.rows[1]["linkage_basis"] = ""
        with self.assertRaisesRegex(ValueError, "linkage_basis"):
            self.build()

    def test_conflicting_host_rejected(self):
        self.rows[1]["host"] = "Other host"
        with self.assertRaisesRegex(ValueError, "conflicting host"):
            self.build()

    def test_duplicate_record_rejected(self):
        self.rows.append(self.rows[0].copy())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.build()

    def test_sample_id_prefix_collision_rejected(self):
        self.rows[0]["tip_label"] = "local__HA"
        with self.assertRaisesRegex(ValueError, "also maps to a WINGS sample"):
            self.build()

    def test_absent_tips_and_missing_tree_differ(self):
        self.rows[0]["tip_label"] = "not_in_tree"
        self.trees = self.trees[:1]
        p = self.build()["public_reference_context"]
        self.assertEqual(p["records_without_displayed_tips"], 2)
        segments = p["references"][0]["segments"]
        self.assertEqual(segments["HA"]["status"], "ABSENT_FROM_TREE")
        self.assertEqual(segments["NA"]["status"], "NO_TREE")

    def test_impossible_date_rejected(self):
        self.rows[0]["collection_date"] = "2025-02-30"
        with self.assertRaisesRegex(ValueError, "Invalid reference collection date"):
            self.build()

    def test_provenance_cannot_override_report_structure(self):
        p = self.build(status="FAKE", schema_version=100, references=[])
        self.assertEqual(p["public_reference_context"]["status"], "READY")
        self.assertEqual(len(p["public_reference_context"]["references"]), 1)

    def test_snakemake_entry_uses_explicit_helper_input(self):
        path, provenance = manifest(self.root, self.rows)
        output = self.root / "explorer.json"
        smk = SimpleNamespace(input=SimpleNamespace(
            metadata=str(self.metadata), summaries=[], trees=self.trees,
            reference_manifest=[path], reference_provenance=[provenance],
            reference_loader=str(SCRIPT.with_name("public_reference_context.py"))),
            output=SimpleNamespace(json=str(output)))
        runpy.run_path(str(SCRIPT), run_name="__main__", init_globals={"snakemake": smk})
        self.assertEqual(json.loads(output.read_text())["public_reference_context"]["record_count"], 2)

    def test_contextual_tree_directory_does_not_mix_analyses(self):
        source = SCRIPT.parents[1].joinpath("Snakefile").read_text()
        function = source.split("def surveillance_tree_inputs(", 1)[1].split("\ndef irma_segments_dir", 1)[0]
        scope = dict(Path=Path, RUN_SURVEILLANCE_EXPLORER=True, REFERENCE_ENABLED=True,
                     REFERENCE_BUILD_CONTEXTUAL=False,
                     REFERENCE_TREE_DIR=str(self.root), REFERENCE_TREE_PATTERN="{segment}_Tree.newick",
                     SEGMENT_SEQUENCE=builder.SEGMENT_ORDER, RUN_PHYLOGENY=True,
                     PHYLOGENY_DIR="other-analysis", PHYLOGENY_PATTERN="{segment}_Tree.newick")
        exec("def surveillance_tree_inputs(" + function, scope)
        paths = scope["surveillance_tree_inputs"](None)
        self.assertEqual(set(paths), {str(path) for path in self.trees})
        scope["REFERENCE_TREE_DIR"] = str(self.root / "empty")
        with self.assertRaisesRegex(ValueError, "No contextual trees"):
            scope["surveillance_tree_inputs"](None)


if __name__ == "__main__":
    unittest.main()
