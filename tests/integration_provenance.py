#!/usr/bin/env python3
"""Execute production provenance rules in isolation, including changed-config reruns.

Usage: python tests/integration_provenance.py --repo .
Requires Snakemake on PATH; no Conda solving, databases, or real samples needed.
All outputs are retained in a new temporary directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def rule(source, name):
    match = re.search(r"^rule " + name + r":\s*$", source, re.M)
    require(match is not None, "Missing production rule: " + name)
    next_rule = re.search(r"^(?:rule|checkpoint) \w+:", source[match.end():], re.M)
    return source[match.start():match.end() + next_rule.start() if next_rule else len(source)]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(repo, root):
    source = (repo / "Snakefile").read_text()
    begin = source.index("# WINGS_PROVENANCE_ACCURACY_V1_BEGIN")
    end = source.index("# WINGS_PROVENANCE_ACCURACY_V1_END", begin) + len("# WINGS_PROVENANCE_ACCURACY_V1_END")
    definitions = source[begin:end]
    function = re.search(r"^def blast_db_files\(.*?(?=^\S|\Z)", source, re.M | re.S)
    require(function is not None, "BLAST input helper missing.")
    header = '''import json, os, shlex
from pathlib import Path
configfile: "fixture.json"
shell.executable("/bin/bash")
RESULTS = "results"
EFFECTIVE_CONFIG_JSON = "results/run_summary/effective_config.json"
BLAST_DB = config["blast_db"]
REPORTING_ENV = "envs/reporting.yaml"
SAMPLES = []
PRIMARY_INPUT_SPECS = []
REPLAY_INPUT_SPECS = []
SNAKEMAKE_VERSION = "synthetic-integration"
IRMA_IMAGE = VADR_IMAGE = "fixture"
IRMA_MODULE = "FLU-minion"
IRMA_RUNTIME = VADR_RUNTIME = "local"
VADR_MKEY = "flu"
MEDAKA_MODEL = None
MEDAKA_MODEL_RECORDS = 100
MEDAKA_FAIL_SOFT = False
COVERAGE_MIN = 50
COVERAGE_MIN_BREADTH = 0.95
SEGMENT_MAX_N_FRACTION = 0.01
BLAST_MIN_IDENTITY = 95
BLAST_MIN_QUERY_COVERAGE = 90
BLAST_MAX_TARGET_SEQS = 10
BLAST_MAX_HSPS = 1
'''
    (root / "Snakefile").write_text(header + "\n" + definitions + "\n" + function.group() + "\n" + rule(source, "effective_run_config") + rule(source, "run_provenance"))
    shutil.copytree(repo / "envs", root / "envs")
    (root / "scripts").mkdir()
    shutil.copy2(repo / "scripts/write_run_provenance.py", root / "scripts/write_run_provenance.py")
    database = root / "references/custom db"
    database.mkdir(parents=True)
    (database / "avian.nin").write_bytes(b"index-v1")
    (database / "avian.nsq").write_bytes(b"sequence-index-fixture")
    (database / "unrelated.nin").write_bytes(b"do not capture")
    (database / "database_manifest.tsv").write_text("database_name\ncustom_fixture\n")
    config = {"blast_db": "references/custom db/avian", "nested": {"audience": "wildlife"},
              "phylogeny": {"tree_pattern": "{segment}_Tree.newick"}}
    (root / "fixture.json").write_text(json.dumps(config, indent=2))
    return config


def execute(root, executable, label):
    command = [executable, "--snakefile", "Snakefile", "--cores", "1", "--profile", "none",
               "--workflow-profile", "none", "results/run_summary/run_provenance.json"]
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("SNAKEMAKE_") or key == "WINGS_ATTEMPT_PROVENANCE":
            env.pop(key)
    path = root / ("snakemake-" + label + ".log")
    with path.open("w") as handle:
        result = subprocess.run(command, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        print(path.read_text(errors="replace")[-6000:])
        raise RuntimeError("Provenance workflow failed; see " + str(path))
    return json.loads((root / "results/run_summary/run_provenance.json").read_text())


def negative_control(root, executable):
    """Demonstrate that the original scalar parameter rejects literal braces."""
    directory = root / "literal-negative-control"
    directory.mkdir()
    source = (root / "Snakefile").read_text()
    production = rule(source, "effective_run_config")
    expected = "serialized=lambda wildcards: json.dumps(dict(config), indent=2, sort_keys=True)"
    require(expected in production, "Literal-config correction missing from production rule")
    broken = production.replace(expected, "serialized=json.dumps(dict(config), indent=2, sort_keys=True)", 1)
    header = 'import json\nfrom pathlib import Path\nconfigfile: "fixture.json"\nEFFECTIVE_CONFIG_JSON = "effective.json"\n'
    (directory / "Snakefile").write_text(header + broken)
    shutil.copyfile(root / "fixture.json", directory / "fixture.json")
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("SNAKEMAKE_"):
            env.pop(key)
    process = subprocess.run([executable, "--cores", "1", "--profile", "none",
                              "--workflow-profile", "none", "--dry-run", "effective.json"],
                             cwd=directory, env=env, capture_output=True, text=True)
    log = process.stdout + "\n" + process.stderr
    (directory / "snakemake-negative.log").write_text(log)
    require(process.returncode != 0 and "WildcardError" in log,
            "Old scalar parameter did not reproduce WildcardError; inspect " + str(directory))
    print("PASS: old scalar parameter reproduces the literal-brace WildcardError.", flush=True)


def refresh_input(path, content, root):
    path.write_text(content)
    # Ensure timestamp ordering on coarse-resolution filesystems without sleeping.
    provenance = root / "results/run_summary/run_provenance.json"
    old_time = max(0, path.stat().st_mtime - 5)
    os.utime(provenance, (old_time, old_time))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    executable = shutil.which("snakemake")
    require(executable is not None, "Activate an environment containing Snakemake.")
    repo = args.repo.resolve()
    root = Path(tempfile.mkdtemp(prefix="wings-provenance-integration-")).resolve()
    print("Test directory: " + str(root), flush=True)
    config = prepare(repo, root)
    negative_control(root, executable)
    record = execute(root, executable, "initial")
    effective = root / "results/run_summary/effective_config.json"
    require(json.loads(effective.read_text()) == config, "Literal-brace configuration was not preserved.")
    print("PASS: literal {segment} is preserved in effective configuration and provenance.", flush=True)
    require(record["blast"]["database"]["database_name"] == "custom_fixture", "Custom manifest not used.")
    require(record["blast"]["database_prefix"] == config["blast_db"], "Wrong database prefix.")
    expected_files = {"references/custom db/avian.nin", "references/custom db/avian.nsq"}
    require(set(record["blast"]["database_files"]) == expected_files, "Wrong database inventory.")
    require({"phylogeny", "phenology"} <= record["conda_environment_files"].keys(), "Missing environment hashes.")
    print("PASS: custom database, index hashes, and all environment definitions recorded.", flush=True)

    config_path = root / "fixture.json"
    before = config_path.stat()
    config["nested"]["audience"] = "public_health"
    config["phylogeny"]["tree_pattern"] = "{segment}_updated.newick"
    config_path.write_text(json.dumps(config, indent=2))
    os.utime(config_path, ns=(before.st_atime_ns, before.st_mtime_ns))
    previous_hash = record["workflow"]["config_sha256"]
    record = execute(root, executable, "changed-config")
    effective = root / "results/run_summary/effective_config.json"
    require(json.loads(effective.read_text()) == config, "Effective config remained stale after a nested config change.")
    require(record["workflow"]["config_sha256"] == digest(effective) != previous_hash, "Config provenance hash did not refresh.")
    print("PASS: changed configuration refreshes provenance without relying on config-file mtime.", flush=True)

    for label in ("phenology", "phylogeny"):
        path = root / "envs" / (label + ".yaml")
        refresh_input(path, path.read_text() + "\n# synthetic provenance regression\n", root)
    record = execute(root, executable, "changed-environments")
    for label in ("phenology", "phylogeny"):
        require(record["conda_environment_files"][label]["sha256"] == digest(root / "envs" / (label + ".yaml")), "Environment hash did not refresh: " + label)
    print("PASS: environment changes refresh recorded hashes.", flush=True)

    index = root / "references/custom db/avian.nin"
    refresh_input(index, "index-v2", root)
    record = execute(root, executable, "changed-database")
    require(record["blast"]["database_files"]["references/custom db/avian.nin"]["sha256"] == digest(index), "Database hash remained stale.")
    print("PASS: changed database files refresh provenance.", flush=True)

    manifest = root / "explicit-manifest.tsv"
    manifest.write_text("database_name\nexplicit_override\n")
    config["blast_db_manifest"] = "explicit-manifest.tsv"
    config_path.write_text(json.dumps(config, indent=2))
    record = execute(root, executable, "explicit-manifest")
    require(record["blast"]["database"]["database_name"] == "explicit_override", "Explicit manifest override ignored.")
    require(record["blast"]["database_manifest_sha256"] == digest(manifest), "Explicit manifest hash wrong.")
    print("PASS: explicit manifest override recorded.", flush=True)
    summary = {"passed": True, "checks": 7, "source_snakefile_sha256": digest(repo / "Snakefile"),
               "scope": "isolated production provenance rules; synthetic input files"}
    (root / "test_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("PASS: provenance integration test.\nSummary: " + str(root / "test_summary.json"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        sys.exit(1)
