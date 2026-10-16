import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_publication_evidence.py"
spec = importlib.util.spec_from_file_location("publication_evidence", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = {"schema_version": module.SCHEMA,
                         "release_commit": "a" * 40, "artifacts": []}
        for role in sorted(module.ROLES):
            data = ("Test fixture only: " + role + "\n").encode()
            path = role + ".txt"
            (self.root / path).write_bytes(data)
            self.manifest["artifacts"].append({"id": role, "role": role,
                "path": path, "sha256": hashlib.sha256(data).hexdigest(),
                "description": "Synthetic inventory fixture, not validation evidence."})

    def check(self, manifest=None):
        return module.check_manifest(self.manifest if manifest is None else manifest, self.root)

    def test_complete_inventory_and_deterministic_output(self):
        result = self.check()
        self.assertEqual(result["inventory_status"], "PASS")
        self.assertIn("does not validate scientific claims", result["scope"])
        self.assertEqual(result, self.check())

    def test_modified_file_fails_integrity(self):
        (self.root / "comparison.txt").write_text("changed")
        result = self.check()
        self.assertEqual(result["inventory_status"], "FAIL")
        self.assertIn("comparison", result["missing_roles"])
        self.assertTrue(any("mismatch" in error for error in result["errors"]))

    def test_missing_and_empty_files_fail(self):
        (self.root / "comparison.txt").unlink()
        (self.root / "real_data.txt").write_bytes(b"")
        result = self.check()
        self.assertEqual(result["inventory_status"], "FAIL")
        self.assertIn("comparison", result["missing_roles"])
        self.assertIn("real_data", result["missing_roles"])

    def test_unsafe_paths_fail(self):
        for path in ("../outside", "/etc/passwd", "C:/outside", "..\\outside"):
            with self.subTest(path=path):
                manifest = copy.deepcopy(self.manifest)
                manifest["artifacts"][0]["path"] = path
                self.assertEqual(module.check_manifest(manifest, self.root)["inventory_status"], "FAIL")

    def test_symlink_escape_fails(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            outside = Path(elsewhere) / "evidence.txt"
            outside.write_text("outside")
            link = self.root / "link.txt"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("Symlink creation unavailable")
            self.manifest["artifacts"][0]["path"] = "link.txt"
            self.assertTrue(any("outside" in e for e in self.check()["errors"]))

    def test_duplicate_identifiers_and_paths_fail(self):
        for field in ("id", "path"):
            with self.subTest(field=field):
                manifest = copy.deepcopy(self.manifest)
                manifest["artifacts"][1][field] = manifest["artifacts"][0][field]
                self.assertEqual(self.check(manifest)["inventory_status"], "FAIL")

    def test_malformed_structures_fail_without_traceback(self):
        for manifest in (None, [], {}, {"artifacts": [None]},
                         {"artifacts": [{"role": [], "path": {}, "sha256": 3}]}):
            with self.subTest(manifest=manifest):
                self.assertEqual(module.check_manifest(manifest, self.root)["inventory_status"], "FAIL")

    def test_release_and_digest_formats_are_required(self):
        self.manifest["release_commit"] = "main"
        self.manifest["artifacts"][0]["sha256"] = "TODO"
        self.assertEqual(self.check()["inventory_status"], "FAIL")

    def test_cli_success_failure_and_default_root(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        result = subprocess.run([sys.executable, str(SCRIPT), str(manifest)],
                                capture_output=True, text=True, cwd=self.root.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["inventory_status"], "PASS")
        manifest.write_text("broken JSON")
        result = subprocess.run([sys.executable, str(SCRIPT), str(manifest)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["inventory_status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
