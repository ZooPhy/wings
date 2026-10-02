from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = REPO_ROOT / "tests" / "integration12"
WORK = HERE / "work"
RESULTS = WORK / "results"
BUNDLE = RESULTS / "wings_report_bundle.wings"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def test_production_wings_bundle_release_artifact():
    subprocess.run(
        [sys.executable, str(HERE / "prepare_fixtures.py")],
        cwd=REPO_ROOT,
        check=True,
    )

    provenance_target = (
        "tests/integration12/work/results/"
        "run_summary/run_provenance.json"
    )

    # Execute the production provenance rule against deterministic upstream
    # fixtures. Keep this target narrow so the report fixture test does not
    # traverse the complete sequencing/checkpoint DAG.
    subprocess.run(
        [
            "snakemake",
            "--snakefile",
            "Snakefile",
            provenance_target,
            "--configfile",
            str(HERE / "config.yaml"),
            "--cores",
            "1",
            "--sdm",
            "conda",
            "--allowed-rules",
            "effective_run_config",
            "run_provenance",
            "--rerun-incomplete",
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    # Build the portable artifact with the same production builder invoked by
    # the wings_report_bundle rule. The HTML inputs here intentionally remain
    # completed fixtures rather than triggering their analytical producers.
    sample_reports = [
        RESULTS
        / sample
        / "summary"
        / f"{sample}.sample_summary.html"
        for sample in ("bundle_alpha", "bundle_beta")
    ]

    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_report_bundle.py"),
            "--run-summary",
            str(RESULTS / "run_summary" / "run_summary.html"),
            "--provenance",
            str(
                RESULTS
                / "run_summary"
                / "run_provenance.json"
            ),
            "--output",
            str(BUNDLE),
            *[str(path) for path in sample_reports],
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    assert BUNDLE.is_file()
    assert BUNDLE.stat().st_size > 0

    provenance_json = RESULTS / "run_summary" / "run_provenance.json"
    provenance_tsv = RESULTS / "run_summary" / "run_provenance.tsv"
    assert provenance_json.stat().st_size > 0
    assert provenance_tsv.stat().st_size > 0

    # A .wings release artifact is JSON and must be readable without any
    # repository-specific parser.
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))

    assert bundle["format"] == "WINGS_REPORT_BUNDLE"
    assert bundle["version"] == 1
    assert bundle["sample_count"] == 2
    assert set(bundle) == {
        "format",
        "version",
        "generated_at",
        "sample_count",
        "run_summary",
        "provenance",
        "samples",
    }

    generated_at = datetime.fromisoformat(bundle["generated_at"])
    assert generated_at.tzinfo is not None

    assert bundle["run_summary"]["filename"] == "run_summary.html"
    assert "PHASE12_RUN_SUMMARY" in bundle["run_summary"]["html"]
    assert "Wild-bird Influenza Genomics and Surveillance" in bundle["run_summary"]["html"]

    assert set(bundle["samples"]) == {"bundle_alpha", "bundle_beta"}

    alpha = bundle["samples"]["bundle_alpha"]
    beta = bundle["samples"]["bundle_beta"]

    assert alpha["filename"] == "bundle_alpha.sample_summary.html"
    assert beta["filename"] == "bundle_beta.sample_summary.html"
    assert "PHASE12_BUNDLE_ALPHA" in alpha["html"]
    assert "PHASE12_BUNDLE_BETA" in beta["html"]
    assert "Sample bundle_alpha" in alpha["html"]
    assert "Sample bundle_beta" in beta["html"]

    # Production provenance must be embedded, not merely referenced.
    embedded_provenance = bundle["provenance"]["data"]
    disk_provenance = json.loads(provenance_json.read_text(encoding="utf-8"))

    assert bundle["provenance"]["filename"] == "run_provenance.json"
    assert embedded_provenance == disk_provenance
    assert embedded_provenance["schema_version"] == 3
    assert embedded_provenance["workflow"]["name"] == "WINGS"
    assert embedded_provenance["workflow"]["sample_count"] == 2
    assert embedded_provenance["workflow"]["snakefile"] == "Snakefile"

    effective_config_path = (
        RESULTS / "run_summary" / "effective_config.json"
    )
    assert effective_config_path.is_file()
    assert (
        embedded_provenance["workflow"]["config_file"]
        == "tests/integration12/work/results/run_summary/effective_config.json"
    )
    assert (
        embedded_provenance["workflow"]["config_sha256"]
        == sha256(effective_config_path)
    )

    effective_config = json.loads(
        effective_config_path.read_text(encoding="utf-8")
    )
    assert (
        effective_config["results_dir"]
        == "tests/integration12/work/results"
    )
    assert effective_config["run_genoflu"] is False
    assert effective_config["run_summary"] is True

    assert embedded_provenance["runtime"]["snakemake_version"]
    assert embedded_provenance["runtime"]["python_version"]

    primary_inputs = embedded_provenance["primary_inputs"]

    assert set(primary_inputs) == {
        "bundle_alpha",
        "bundle_beta",
    }

    for sample in ("bundle_alpha", "bundle_beta"):
        record = primary_inputs[sample]
        assert record["path"].endswith(
            f"{sample}.fastq.gz"
        )
        assert len(record["sha256"]) == 64
        assert record["size_bytes"] > 0

    replay_inputs = embedded_provenance["replay_inputs"]
    assert "metadata" in replay_inputs
    assert replay_inputs["metadata"]["path"].endswith(
        "tests/integration12/work/metadata.tsv"
    )
    assert len(replay_inputs["metadata"]["sha256"]) == 64

    assert "validated_metadata" in replay_inputs
    assert replay_inputs["validated_metadata"]["path"].endswith(
        "tests/integration12/work/results/metadata/validated_metadata.tsv"
    )
    assert len(replay_inputs["validated_metadata"]["sha256"]) == 64

    assert embedded_provenance["qc"]["coverage_min_depth"] == "50.0"
    assert embedded_provenance["qc"]["coverage_min_breadth"] == "0.95"
    assert embedded_provenance["qc"]["segment_max_n_fraction"] == "0.01"

    blast = embedded_provenance["blast"]
    assert blast["min_identity"] == "95.0"
    assert blast["min_query_coverage"] == "90.0"
    assert blast["max_target_seqs"] == "10"
    assert blast["max_hsps"] == "1"
    assert blast["database_manifest"] == "resources/flu_db/database_manifest.tsv"
    assert blast["database"]["database_name"] == "fluA_db"

    envs = embedded_provenance["conda_environment_files"]
    for required in (
        "blast",
        "coverage",
        "fastplong",
        "genoflu",
        "medaka",
        "nanoplot",
        "porechop",
        "py-tools",
        "pysam",
        "reporting",
        "seqtk",
    ):
        assert required in envs
        assert envs[required]["sha256"] != "MISSING"
        assert len(envs[required]["sha256"]) == 64

    # Simulate distribution: copy only the single .wings artifact outside the
    # results tree, parse it again, and recover all embedded reports/provenance.
    release_dir = WORK / "standalone_release_check"
    release_dir.mkdir(parents=True, exist_ok=True)
    distributed = release_dir / "wings_report_bundle.wings"
    shutil.copy2(BUNDLE, distributed)

    original_hash = sha256(BUNDLE)
    distributed_hash = sha256(distributed)
    assert distributed_hash == original_hash

    standalone = json.loads(distributed.read_text(encoding="utf-8"))
    assert standalone["run_summary"]["html"] == bundle["run_summary"]["html"]
    assert standalone["provenance"]["data"] == embedded_provenance
    assert standalone["samples"] == bundle["samples"]

    # Rehydrate the embedded HTML into an otherwise empty directory. This
    # verifies that the bundle carries the report payloads rather than paths.
    rehydrated = release_dir / "rehydrated"
    rehydrated.mkdir()
    (rehydrated / standalone["run_summary"]["filename"]).write_text(
        standalone["run_summary"]["html"],
        encoding="utf-8",
    )
    for sample_id, report in standalone["samples"].items():
        (rehydrated / report["filename"]).write_text(
            report["html"],
            encoding="utf-8",
        )

    assert (rehydrated / "run_summary.html").stat().st_size > 0
    assert (rehydrated / "bundle_alpha.sample_summary.html").stat().st_size > 0
    assert (rehydrated / "bundle_beta.sample_summary.html").stat().st_size > 0
