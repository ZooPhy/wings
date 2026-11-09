"""Regression tests for the WINGS report-bundle container format.

The contract these tests defend is that schema version 2 is a storage change
only.  Every rendered report must come back out of a packed bundle character
for character, and every other section of the bundle must be untouched.

Run with::

    python -m unittest discover -s tests -p test_bundle_format.py -v

A real bundle can also be checked directly::

    WINGS_TEST_BUNDLE=results/wings_report_bundle.wings \\
        python -m unittest tests.test_bundle_format -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# The module under test ships in scripts/, which is not an installed package.
# Put it on the path so this test runs from the repo root without any pytest
# configuration change.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from wings_bundle_format import (
    BundleFormatError,
    MIN_SHARED_BYTES,
    pack_bundle,
    read_bundle,
    sample_html,
    unpack_bundle,
    verify_roundtrip,
    write_bundle,
)

# A realistic report shape: a long shared head, a unique body, a shared tail.
PREFIX = "<!DOCTYPE html><html><head>" + ("<style>.q{}</style>" * 400) + "</head><body>"
SUFFIX = "</body>" + ("<script>void 0;</script>" * 200) + "</html>"


def make_report(sample_id: str, body: str = "") -> str:
    return f"{PREFIX}<h1>{sample_id}</h1>{body}{SUFFIX}"


def make_bundle(sample_ids, **overrides):
    bundle = {
        "format": "WINGS_REPORT_BUNDLE",
        "version": 1,
        "generated_at": "2026-10-29T04:18:08.859086+00:00",
        "sample_count": len(sample_ids),
        "run_summary": {"filename": "run_summary.html", "html": "<html>run</html>"},
        "provenance": {
            "filename": "run_provenance.json",
            "data": {"workflow": {"git_commit": "eac19fd", "sample_count": len(sample_ids)}},
        },
        "samples": {
            sample_id: {
                "filename": f"{sample_id}.sample_summary.html",
                "html": make_report(sample_id),
            }
            for sample_id in sample_ids
        },
    }
    bundle.update(overrides)
    return bundle


class PackRoundTrip(unittest.TestCase):
    def setUp(self):
        self.sample_ids = [f"12-11-2025_barcode{n:02d}" for n in range(3, 13)]
        self.bundle = make_bundle(self.sample_ids)

    def test_every_report_reconstructs_exactly(self):
        packed = pack_bundle(self.bundle)
        for sample_id in self.sample_ids:
            self.assertEqual(
                sample_html(packed, sample_id),
                self.bundle["samples"][sample_id]["html"],
                f"{sample_id} did not reconstruct character for character",
            )

    def test_packing_declares_version_two_and_shared_chunks(self):
        packed = pack_bundle(self.bundle)
        self.assertEqual(packed["version"], 2)
        self.assertIn("shared", packed)
        self.assertTrue(packed["shared"]["report_prefix"])
        self.assertTrue(packed["shared"]["report_suffix"])

    def test_packed_bundle_is_smaller(self):
        before = len(json.dumps(self.bundle))
        after = len(json.dumps(pack_bundle(self.bundle)))
        self.assertLess(after, before)

    def test_other_sections_are_untouched(self):
        packed = pack_bundle(self.bundle)
        for key in ("format", "generated_at", "sample_count", "run_summary", "provenance"):
            self.assertEqual(packed[key], self.bundle[key])

    def test_sample_filenames_survive_packing(self):
        packed = pack_bundle(self.bundle)
        for sample_id in self.sample_ids:
            self.assertEqual(
                packed["samples"][sample_id]["filename"],
                f"{sample_id}.sample_summary.html",
            )

    def test_unpack_restores_the_original_bundle(self):
        restored = unpack_bundle(pack_bundle(self.bundle))
        self.assertEqual(restored, self.bundle)

    def test_packing_is_idempotent(self):
        once = pack_bundle(self.bundle)
        self.assertEqual(pack_bundle(once), once)

    def test_verify_roundtrip_reports_savings(self):
        result = verify_roundtrip(self.bundle)
        self.assertTrue(result["all_reports_exact"])
        self.assertEqual(result["samples"], len(self.sample_ids))
        self.assertGreater(result["saved_bytes"], 0)


class BackwardCompatibility(unittest.TestCase):
    def test_v1_bundles_still_read(self):
        bundle = make_bundle(["a", "b"])
        self.assertNotIn("shared", bundle)
        self.assertEqual(sample_html(bundle, "a"), bundle["samples"]["a"]["html"])

    def test_reader_does_not_branch_on_version(self):
        bundle = make_bundle(["a", "b"])
        packed = pack_bundle(bundle)
        for sample_id in ("a", "b"):
            self.assertEqual(sample_html(bundle, sample_id), sample_html(packed, sample_id))

    def test_missing_sample_raises_key_error(self):
        with self.assertRaises(KeyError):
            sample_html(make_bundle(["a"]), "absent")


class EdgeCases(unittest.TestCase):
    def test_single_sample_bundle_is_left_at_v1(self):
        bundle = make_bundle(["only"])
        packed = pack_bundle(bundle)
        self.assertNotIn("shared", packed)
        self.assertEqual(sample_html(packed, "only"), bundle["samples"]["only"]["html"])

    def test_reports_with_no_meaningful_overlap_are_left_at_v1(self):
        bundle = make_bundle(["a", "b"])
        bundle["samples"]["a"]["html"] = "<html>alpha</html>"
        bundle["samples"]["b"]["html"] = "?different entirely?"
        packed = pack_bundle(bundle)
        self.assertNotIn("shared", packed)

    def test_prefix_and_suffix_never_overlap_on_the_shortest_report(self):
        # One report is a strict prefix of the others.  A naive implementation
        # double-counts the shared region here and corrupts the short report.
        shared = "X" * (MIN_SHARED_BYTES * 2)
        bundle = make_bundle(["short", "long"])
        bundle["samples"]["short"]["html"] = shared
        bundle["samples"]["long"]["html"] = shared + "tail"
        packed = pack_bundle(bundle)
        self.assertEqual(sample_html(packed, "short"), shared)
        self.assertEqual(sample_html(packed, "long"), shared + "tail")

    def test_identical_reports_pack_to_empty_middles(self):
        bundle = make_bundle(["a", "b"])
        same = make_report("same")
        bundle["samples"]["a"]["html"] = same
        bundle["samples"]["b"]["html"] = same
        packed = pack_bundle(bundle)
        self.assertEqual(packed["samples"]["a"]["html_mid"], "")
        self.assertEqual(sample_html(packed, "a"), same)
        self.assertEqual(sample_html(packed, "b"), same)

    def test_non_ascii_report_content_survives(self):
        bundle = make_bundle(["a", "b"])
        bundle["samples"]["a"]["html"] = make_report("a", "Ardea herodias \u2014 \u00b15 d\u00e9tections")
        packed = pack_bundle(bundle)
        self.assertEqual(sample_html(packed, "a"), bundle["samples"]["a"]["html"])

    def test_empty_sample_set(self):
        bundle = make_bundle([])
        self.assertEqual(pack_bundle(bundle)["samples"], {})

    def test_sample_without_html_is_rejected(self):
        bundle = make_bundle(["a", "b"])
        del bundle["samples"]["a"]["html"]
        with self.assertRaises(BundleFormatError):
            pack_bundle(bundle)


class FileIO(unittest.TestCase):
    def test_write_then_read_plain_and_gzipped(self):
        bundle = pack_bundle(make_bundle(["a", "b", "c"]))
        with tempfile.TemporaryDirectory() as workdir:
            for name, compress in (("plain.wings", False), ("compressed.wings", True)):
                path = Path(workdir) / name
                write_bundle(bundle, path, compress=compress)
                self.assertEqual(read_bundle(path), bundle)

    def test_non_bundle_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as workdir:
            path = Path(workdir) / "other.json"
            path.write_text(json.dumps({"format": "SOMETHING_ELSE"}))
            with self.assertRaises(BundleFormatError):
                read_bundle(path)


@unittest.skipUnless(
    os.environ.get("WINGS_TEST_BUNDLE"),
    "set WINGS_TEST_BUNDLE to a .wings path to check a real bundle",
)
class RealBundle(unittest.TestCase):
    def test_real_bundle_roundtrips_exactly(self):
        bundle = read_bundle(os.environ["WINGS_TEST_BUNDLE"])
        result = verify_roundtrip(bundle)
        self.assertTrue(result["all_reports_exact"])
        print(
            f"\n  {result['samples']} samples, "
            f"{result['v1_bytes']:,} -> {result['v2_bytes']:,} bytes "
            f"({result['saved_bytes']:,} saved)"
        )


if __name__ == "__main__":
    unittest.main()
