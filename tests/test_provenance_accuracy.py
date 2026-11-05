"""Portable provenance regressions; no sequencing tools or Snakemake required."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "Snakefile").read_text(encoding="utf-8")
spec = importlib.util.spec_from_file_location("provenance_writer", ROOT / "scripts/write_run_provenance.py")
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)


def provenance_definitions(config, reporting="envs/reporting.yaml"):
    begin = SOURCE.index("# WINGS_PROVENANCE_ACCURACY_V1_BEGIN")
    end = SOURCE.index("# WINGS_PROVENANCE_ACCURACY_V1_END", begin)
    namespace = {"config": config, "Path": Path, "BLAST_DB": config["blast_db"], "REPORTING_ENV": reporting}
    exec(compile(SOURCE[begin:end], "Snakefile:provenance_definitions", "exec"), namespace)
    return namespace


def effective_rule_parts():
    rule = SOURCE.split("rule effective_run_config:\n", 1)[1].split("rule run_provenance:\n", 1)[0]
    params = rule.split("    params:\n", 1)[1].split("    run:\n", 1)[0]
    expression = re.search(r"serialized=(.*)", params).group(1)
    body = textwrap.dedent(rule.split("    run:\n", 1)[1])
    ast.parse(expression, mode="eval")
    ast.parse(body)
    return expression, body


class ProvenanceAccuracyTests(unittest.TestCase):
    def test_config_parameter_changes_with_nested_values(self):
        expression, _ = effective_rule_parts()
        a = {"public_health_interpretation": {"audience": "wildlife"}}
        b = {"public_health_interpretation": {"audience": "public_health"}}
        render = lambda c: eval(expression, {"json": json, "config": c})
        self.assertNotEqual(render(a), render(b))
        self.assertEqual(render({"a": 1, "b": 2}), render({"b": 2, "a": 1}))

    def test_written_config_is_exact_tracked_parameter(self):
        expression, body = effective_rule_parts()
        config = {"coverage_min_depth": 75, "nested": {"enabled": False}}
        serialized = eval(expression, {"json": json, "config": config})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested/config.json"
            exec(compile(body, "Snakefile:effective_run_config", "exec"), {
                "Path": Path, "json": json, "config": {"unexpected": "later mutation"},
                "output": SimpleNamespace(json=str(path)), "params": SimpleNamespace(serialized=serialized),
            })
            self.assertEqual(path.read_text(), serialized + "\n")
            self.assertEqual(json.loads(path.read_text()), config)

    def test_manifest_follows_selected_prefix(self):
        result = provenance_definitions({"blast_db": "references/custom db/avian"})
        self.assertEqual(result["BLAST_DB_MANIFEST"], "references/custom db/database_manifest.tsv")

    def test_explicit_manifest_override_and_blank_default(self):
        self.assertEqual(provenance_definitions({"blast_db": "/data/avian", "blast_db_manifest": "/other/source.tsv"})["BLAST_DB_MANIFEST"], "/other/source.tsv")
        self.assertEqual(provenance_definitions({"blast_db": "db/avian", "blast_db_manifest": ""})["BLAST_DB_MANIFEST"], "db/database_manifest.tsv")

    def test_all_definitions_share_input_and_command_mapping(self):
        envs = provenance_definitions({"blast_db": "db/avian"})["PROVENANCE_ENVIRONMENTS"]
        self.assertIn("phenology", envs)
        self.assertIn("phylogeny", envs)
        self.assertEqual(len(envs), 13)
        for path in envs.values():
            self.assertTrue((ROOT / path).is_file(), path)
        rule = SOURCE.split("rule run_provenance:\n", 1)[1].split("rule archive_replay_inputs:\n", 1)[0]
        self.assertIn("envs=list(PROVENANCE_ENVIRONMENTS.values())", rule)
        self.assertIn("for label, path in PROVENANCE_ENVIRONMENTS.items()", rule)
        self.assertIn("blast_database=blast_db_files", rule)
        self.assertIn("blast_manifest=BLAST_DB_MANIFEST", rule)

    def test_arm_reporting_definition_is_preserved(self):
        envs = provenance_definitions({"blast_db": "db/avian"}, "envs/reporting-linux-arm64.yaml")["PROVENANCE_ENVIRONMENTS"]
        self.assertEqual(envs["reporting"], "envs/reporting-linux-arm64.yaml")

    def test_database_inventory_matches_prefix_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "db").mkdir()
            (root / "db/avian.nin").write_bytes(b"index one")
            (root / "db/avian.nsq").write_bytes(b"index two")
            (root / "db/other.nin").write_bytes(b"unrelated")
            (root / "db/avian.directory").mkdir()
            record = writer.capture_blast_database(Path("db/avian"), root)
            self.assertEqual(record["database_prefix"], "db/avian")
            self.assertEqual(set(record["database_files"]), {"db/avian.nin", "db/avian.nsq"})
            self.assertEqual(record["database_files"]["db/avian.nin"]["sha256"], hashlib.sha256(b"index one").hexdigest())
            self.assertEqual(record["database_files"]["db/avian.nsq"]["size_bytes"], 9)

    def test_database_hash_changes_when_index_content_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index = root / "avian.nin"
            index.write_bytes(b"first")
            a = writer.capture_blast_database(root / "avian", root)
            index.write_bytes(b"other")
            b = writer.capture_blast_database(root / "avian", root)
            self.assertNotEqual(a["database_files"]["avian.nin"]["sha256"], b["database_files"]["avian.nin"]["sha256"])

    def test_absent_database_is_not_silently_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "No BLAST database files"):
                writer.capture_blast_database(Path("missing"), Path(temp))

    def test_symlinked_repository_root_has_stable_relative_paths(self):
        # Reproduces macOS /var -> /private/var behavior on Linux as well.
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp).resolve()
            actual = parent / "actual"
            actual.mkdir()
            alias = parent / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            (actual / "db").mkdir()
            (actual / "db/avian.nin").write_bytes(b"fixture")
            expected = writer.capture_blast_database(actual / "db/avian", actual)
            for prefix in (Path("db/avian"), alias / "db/avian", actual / "db/avian"):
                with self.subTest(prefix=str(prefix)):
                    result = writer.capture_blast_database(prefix, alias)
                    self.assertEqual(result, expected)
                    self.assertEqual(result["database_prefix"], "db/avian")
                    self.assertEqual(set(result["database_files"]), {"db/avian.nin"})

    def test_symlinked_root_hashes_update_without_changing_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp).resolve()
            actual = parent / "actual"
            actual.mkdir()
            alias = parent / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            index = actual / "avian.nin"
            index.write_bytes(b"first")
            before = writer.capture_blast_database(alias / "avian", alias)
            index.write_bytes(b"other")
            after = writer.capture_blast_database(alias / "avian", alias)
            self.assertEqual(set(before["database_files"]), {"avian.nin"})
            self.assertEqual(set(after["database_files"]), {"avian.nin"})
            self.assertNotEqual(before["database_files"]["avian.nin"]["sha256"], after["database_files"]["avian.nin"]["sha256"])

    def test_production_writer_cli_and_legacy_compatibility(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config.json").write_text('{"purpose":"synthetic"}\n')
            (root / "Snakefile").write_text("# synthetic\n")
            (root / "manifest.tsv").write_text("database_name\tdb_prefix\navian\tavian\n")
            (root / "avian.nin").write_bytes(b"test index")
            (root / "phylogeny.yaml").write_text("dependencies: [mafft]\n")
            (root / "phenology.yaml").write_text("dependencies: [rasterio]\n")
            values = {
                "output-tsv": "result.tsv", "output-json": "result.json", "repo-root": ".",
                "config": "config.json", "snakefile": "Snakefile", "blast-manifest": "manifest.tsv",
                "sample-count": "0", "snakemake-version": "fixture", "irma-image": "fixture",
                "irma-module": "FLU-minion", "irma-runtime": "local", "vadr-image": "fixture",
                "vadr-mkey": "flu", "vadr-runtime": "local", "medaka-model-records": "100",
                "medaka-fail-soft": "false", "coverage-min-depth": "50", "coverage-min-breadth": "0.95",
                "segment-max-n-fraction": "0.01", "blast-min-identity": "95", "blast-min-query-coverage": "90",
                "blast-max-target-seqs": "10", "blast-max-hsps": "1",
            }
            command = [sys.executable, str(ROOT / "scripts/write_run_provenance.py")]
            for name, value in values.items():
                command += ["--" + name, value]
            command += ["--env", "phylogeny=phylogeny.yaml", "--env", "phenology=phenology.yaml"]
            env = os.environ.copy()
            env.pop("WINGS_ATTEMPT_PROVENANCE", None)
            for options in (["--blast-db-prefix", "avian"], []):
                result = subprocess.run(command + options, cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads((root / "result.json").read_text())
                self.assertEqual(data["schema_version"], 4)
                self.assertEqual(data["blast"]["database"]["database_name"], "avian")
                self.assertEqual(data["workflow"]["config_sha256"], writer.sha256_file(root / "config.json"))
                self.assertEqual(data["conda_environment_files"]["phenology"]["sha256"], writer.sha256_file(root / "phenology.yaml"))
                self.assertEqual("database_prefix" in data["blast"], bool(options))
                if options:
                    self.assertEqual(data["blast"]["database_files"]["avian.nin"]["sha256"], writer.sha256_file(root / "avian.nin"))


if __name__ == "__main__":
    unittest.main()
