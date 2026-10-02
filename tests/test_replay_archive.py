from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "archive_replay_inputs.py"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_replay_archive_is_content_addressed_and_deduplicated(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    content = b"same historical WINGS input\n"
    digest = sha256_bytes(content)

    first = repo / "first.tsv"
    second = repo / "second.tsv"
    first.write_bytes(content)
    second.write_bytes(content)

    provenance = repo / "run_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "replay_inputs": {
                    "first": {
                        "path": "first.tsv",
                        "sha256": digest,
                    },
                    "second": {
                        "path": "second.tsv",
                        "sha256": digest,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    archive = repo / "replay_archive"

    command = [
        sys.executable,
        str(SCRIPT),
        "--manifest",
        str(provenance),
        "--repo-root",
        str(repo),
        "--archive-root",
        str(archive),
    ]

    first_run = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Inputs archived: 2" in first_run.stdout
    assert "New objects: 1" in first_run.stdout
    assert "Existing objects reused: 1" in first_run.stdout

    current = json.loads(
        (archive / "current.json").read_text(encoding="utf-8")
    )
    snapshot = json.loads(
        (archive / current["snapshot"]).read_text(encoding="utf-8")
    )

    assert snapshot["archive_format"] == "WINGS_REPLAY_ARCHIVE"
    assert snapshot["inputs"]["first"]["sha256"] == digest
    assert snapshot["inputs"]["second"]["sha256"] == digest
    assert (
        snapshot["inputs"]["first"]["object_path"]
        == snapshot["inputs"]["second"]["object_path"]
    )

    objects = list((archive / "objects" / "sha256").glob("*/*"))
    assert len(objects) == 1
    assert objects[0].read_bytes() == content

    second_run = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "New objects: 0" in second_run.stdout
    assert "Existing objects reused: 2" in second_run.stdout
    assert len(list((archive / "objects" / "sha256").glob("*/*"))) == 1


def test_replay_snapshot_restores_historical_bytes_after_inputs_change(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    historical = b"historical WINGS context\n"
    historical_sha = sha256_bytes(historical)

    source = repo / "context.tsv"
    source.write_bytes(historical)

    provenance = repo / "run_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "replay_inputs": {
                    "context": {
                        "path": "context.tsv",
                        "sha256": historical_sha,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    archive = repo / "replay_archive"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(provenance),
            "--repo-root",
            str(repo),
            "--archive-root",
            str(archive),
        ],
        check=True,
    )

    # Simulate the live input changing after the historical run.
    source.write_bytes(b"new context that should not replace history\n")

    restore_script = (
        REPO_ROOT / "scripts" / "restore_replay_snapshot.py"
    )
    workspace = repo / "historical_replay"

    subprocess.run(
        [
            sys.executable,
            str(restore_script),
            "--archive-root",
            str(archive),
            "--snapshot",
            "current",
            "--output-dir",
            str(workspace),
        ],
        check=True,
    )

    workspace_manifest = json.loads(
        (workspace / "replay_workspace.json").read_text(
            encoding="utf-8"
        )
    )

    restored_rel = workspace_manifest["inputs"]["context"][
        "restored_path"
    ]
    restored = workspace / restored_rel

    assert restored.read_bytes() == historical
    assert sha256_bytes(restored.read_bytes()) == historical_sha

    # The current project input remains changed and untouched.
    assert source.read_bytes() != historical


def test_interpretation_archive_is_immutable_for_snapshot(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    historical_input = b"historical input\n"
    input_sha = sha256_bytes(historical_input)

    source = repo / "metadata.tsv"
    source.write_bytes(historical_input)

    provenance = repo / "run_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "replay_inputs": {
                    "metadata": {
                        "path": "metadata.tsv",
                        "sha256": input_sha,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    results = repo / "results"
    summary_dir = results / "sample1" / "summary"
    medaka_dir = results / "sample1" / "medaka" / "HA"
    summary_dir.mkdir(parents=True)
    medaka_dir.mkdir(parents=True)

    sample_summary = summary_dir / "sample1.sample_summary.tsv"
    sample_summary.write_text(
        "sample_id\tstatus\nsample1\tPASS\n",
        encoding="utf-8",
    )

    vcf = medaka_dir / "variants.vcf"
    vcf.write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "HA\t10\t.\tA\tG\t60\tPASS\t.\n",
        encoding="utf-8",
    )

    variant_status = medaka_dir / "variants.status.tsv"
    variant_status.write_text(
        "status\treason\nSUCCESS\tvcf_generated\n",
        encoding="utf-8",
    )

    archive = results / "replay_archive"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(provenance),
            "--repo-root",
            str(repo),
            "--archive-root",
            str(archive),
        ],
        check=True,
    )

    interpretation_script = (
        REPO_ROOT / "scripts" / "archive_interpretation_outputs.py"
    )

    command = [
        sys.executable,
        str(interpretation_script),
        "--provenance",
        str(provenance),
        "--results-root",
        str(results),
        "--archive-root",
        str(archive),
    ]

    subprocess.run(
        command,
        check=True,
    )

    current = json.loads(
        (
            archive
            / "interpretations"
            / "current.json"
        ).read_text(encoding="utf-8")
    )

    interpretation = json.loads(
        (
            archive
            / current["interpretation"]
        ).read_text(encoding="utf-8")
    )

    categories = {
        record["category"]
        for record in interpretation["artifacts"].values()
    }

    assert "sample_summary" in categories
    assert "variant_vcf" in categories
    assert "variant_status" in categories

    # Changing an analytical result without changing the provenance must not
    # silently rewrite the historical interpretation snapshot.
    sample_summary.write_text(
        "sample_id\tstatus\nsample1\tCHANGED\n",
        encoding="utf-8",
    )

    changed = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    assert changed.returncode != 0
    assert "immutable" in changed.stderr.lower()


def test_historical_comparison_detects_added_variant(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    # Minimal replay-sensitive input.
    metadata = repo / "metadata.tsv"
    metadata.write_text(
        "sample_id\nsample1\n",
        encoding="utf-8",
    )
    metadata_sha = sha256_bytes(metadata.read_bytes())

    provenance = repo / "run_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "replay_inputs": {
                    "metadata": {
                        "path": "metadata.tsv",
                        "sha256": metadata_sha,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    results = repo / "results"
    vcf_dir = results / "sample1" / "medaka" / "HA"
    vcf_dir.mkdir(parents=True)

    vcf = vcf_dir / "variants.vcf"
    vcf.write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "HA\t10\t.\tA\tG\t60\tPASS\t.\n",
        encoding="utf-8",
    )

    status = vcf_dir / "variants.status.tsv"
    status.write_text(
        "status\treason\nSUCCESS\tvcf_generated\n",
        encoding="utf-8",
    )

    archive = results / "replay_archive"

    # Archive replay inputs.
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(provenance),
            "--repo-root",
            str(repo),
            "--archive-root",
            str(archive),
        ],
        check=True,
    )

    # Archive the historical interpretation.
    interpretation_script = (
        REPO_ROOT / "scripts" / "archive_interpretation_outputs.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(interpretation_script),
            "--provenance",
            str(provenance),
            "--results-root",
            str(results),
            "--archive-root",
            str(archive),
        ],
        check=True,
    )

    current = json.loads(
        (
            archive
            / "interpretations"
            / "current.json"
        ).read_text(encoding="utf-8")
    )
    historical_interpretation = (
        archive / current["interpretation"]
    )

    # Simulate a later analysis finding one additional HA variant.
    vcf.write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "HA\t10\t.\tA\tG\t60\tPASS\t.\n"
        "HA\t25\t.\tC\tT\t60\tPASS\t.\n",
        encoding="utf-8",
    )

    comparison_json = results / "comparison.json"
    variant_tsv = results / "variant_stability.tsv"

    compare_script = (
        REPO_ROOT / "scripts" / "compare_historical_interpretation.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(compare_script),
            "--interpretation",
            str(historical_interpretation),
            "--archive-root",
            str(archive),
            "--results-root",
            str(results),
            "--output-json",
            str(comparison_json),
            "--variant-tsv",
            str(variant_tsv),
        ],
        check=True,
    )

    comparison = json.loads(
        comparison_json.read_text(encoding="utf-8")
    )

    assert comparison["variant_counts"] == {"CHANGED": 1}
    assert comparison["layers"]["variant_calls"]["status"] == "CHANGED"
    assert comparison["layers"]["genomic_overall"]["status"] == "CHANGED"
    assert (
        "primary genomic interpretation changed"
        in comparison["interpretation"].lower()
    )

    rows = comparison["variants"]
    assert len(rows) == 1

    row = rows[0]
    assert row["sample"] == "sample1"
    assert row["segment"] == "HA"
    assert row["status"] == "CHANGED"
    assert row["historical_variant_count"] == 1
    assert row["current_variant_count"] == 2
    assert row["added_count"] == 1
    assert row["removed_count"] == 0
    assert row["added_variants"] == "HA:25:C>T"
    assert row["removed_variants"] == ""


def test_context_change_does_not_imply_genomic_instability(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    metadata = repo / "metadata.tsv"
    metadata.write_text(
        "sample_id\nsample1\n",
        encoding="utf-8",
    )
    metadata_sha = sha256_bytes(metadata.read_bytes())

    provenance = repo / "run_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "replay_inputs": {
                    "metadata": {
                        "path": "metadata.tsv",
                        "sha256": metadata_sha,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    results = repo / "results"

    summary_dir = results / "sample1" / "summary"
    summary_dir.mkdir(parents=True)

    (summary_dir / "sample1.sample_summary.tsv").write_text(
        "sample_id\tstatus\n"
        "sample1\tPASS\n",
        encoding="utf-8",
    )

    medaka_dir = results / "sample1" / "medaka" / "HA"
    medaka_dir.mkdir(parents=True)

    (medaka_dir / "variants.vcf").write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "HA\t10\t.\tA\tG\t60\tPASS\t.\n",
        encoding="utf-8",
    )

    (medaka_dir / "variants.status.tsv").write_text(
        "status\treason\n"
        "SUCCESS\tvcf_generated\n",
        encoding="utf-8",
    )

    run_summary = results / "run_summary"
    run_summary.mkdir(parents=True)

    explorer = run_summary / "surveillance_explorer.json"
    explorer.write_text(
        json.dumps(
            {
                "samples": ["sample1"],
                "context_version": "historical",
            }
        ),
        encoding="utf-8",
    )

    archive = results / "replay_archive"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(provenance),
            "--repo-root",
            str(repo),
            "--archive-root",
            str(archive),
        ],
        check=True,
    )

    interpretation_script = (
        REPO_ROOT / "scripts" / "archive_interpretation_outputs.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(interpretation_script),
            "--provenance",
            str(provenance),
            "--results-root",
            str(results),
            "--archive-root",
            str(archive),
        ],
        check=True,
    )

    current = json.loads(
        (
            archive
            / "interpretations"
            / "current.json"
        ).read_text(encoding="utf-8")
    )

    historical_interpretation = (
        archive / current["interpretation"]
    )

    # Simulate new external surveillance context while leaving all genomic
    # outputs byte-for-byte unchanged.
    explorer.write_text(
        json.dumps(
            {
                "samples": ["sample1"],
                "context_version": "updated",
                "new_reference": "REF_NEW",
            }
        ),
        encoding="utf-8",
    )

    comparison_json = results / "comparison.json"
    variant_tsv = results / "variant_stability.tsv"

    compare_script = (
        REPO_ROOT / "scripts" / "compare_historical_interpretation.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(compare_script),
            "--interpretation",
            str(historical_interpretation),
            "--archive-root",
            str(archive),
            "--results-root",
            str(results),
            "--output-json",
            str(comparison_json),
            "--variant-tsv",
            str(variant_tsv),
        ],
        check=True,
    )

    comparison = json.loads(
        comparison_json.read_text(encoding="utf-8")
    )

    assert comparison["layers"]["primary_genomic"]["status"] == "STABLE"
    assert comparison["layers"]["variant_calls"]["status"] == "STABLE"
    assert comparison["layers"]["genomic_overall"]["status"] == "STABLE"

    assert (
        comparison["layers"]["surveillance_context"]["status"]
        == "CHANGED"
    )

    assert (
        comparison["layers"]["integrated_concordance"]["status"]
        == "NOT_AVAILABLE"
    )

    assert (
        "underlying genomic result is stable"
        in comparison["interpretation"].lower()
    )
    assert (
        "surveillance/context outputs changed"
        in comparison["interpretation"].lower()
    )


def test_context_change_does_not_imply_genomic_instability(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    metadata = repo / "metadata.tsv"
    metadata.write_text(
        "sample_id\nsample1\n",
        encoding="utf-8",
    )
    metadata_sha = sha256_bytes(metadata.read_bytes())

    provenance = repo / "run_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "replay_inputs": {
                    "metadata": {
                        "path": "metadata.tsv",
                        "sha256": metadata_sha,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    results = repo / "results"

    summary_dir = results / "sample1" / "summary"
    summary_dir.mkdir(parents=True)

    (summary_dir / "sample1.sample_summary.tsv").write_text(
        "sample_id\tstatus\n"
        "sample1\tPASS\n",
        encoding="utf-8",
    )

    medaka_dir = results / "sample1" / "medaka" / "HA"
    medaka_dir.mkdir(parents=True)

    (medaka_dir / "variants.vcf").write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "HA\t10\t.\tA\tG\t60\tPASS\t.\n",
        encoding="utf-8",
    )

    (medaka_dir / "variants.status.tsv").write_text(
        "status\treason\n"
        "SUCCESS\tvcf_generated\n",
        encoding="utf-8",
    )

    run_summary = results / "run_summary"
    run_summary.mkdir(parents=True)

    explorer = run_summary / "surveillance_explorer.json"
    explorer.write_text(
        json.dumps(
            {
                "samples": ["sample1"],
                "context_version": "historical",
            }
        ),
        encoding="utf-8",
    )

    archive = results / "replay_archive"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(provenance),
            "--repo-root",
            str(repo),
            "--archive-root",
            str(archive),
        ],
        check=True,
    )

    interpretation_script = (
        REPO_ROOT / "scripts" / "archive_interpretation_outputs.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(interpretation_script),
            "--provenance",
            str(provenance),
            "--results-root",
            str(results),
            "--archive-root",
            str(archive),
        ],
        check=True,
    )

    current = json.loads(
        (
            archive
            / "interpretations"
            / "current.json"
        ).read_text(encoding="utf-8")
    )

    historical_interpretation = (
        archive / current["interpretation"]
    )

    # Only the external surveillance context changes.
    explorer.write_text(
        json.dumps(
            {
                "samples": ["sample1"],
                "context_version": "updated",
                "new_reference": "REF_NEW",
            }
        ),
        encoding="utf-8",
    )

    comparison_json = results / "comparison.json"
    variant_tsv = results / "variant_stability.tsv"

    compare_script = (
        REPO_ROOT / "scripts" / "compare_historical_interpretation.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(compare_script),
            "--interpretation",
            str(historical_interpretation),
            "--archive-root",
            str(archive),
            "--results-root",
            str(results),
            "--output-json",
            str(comparison_json),
            "--variant-tsv",
            str(variant_tsv),
        ],
        check=True,
    )

    comparison = json.loads(
        comparison_json.read_text(encoding="utf-8")
    )

    assert comparison["layers"]["primary_genomic"]["status"] == "STABLE"
    assert comparison["layers"]["variant_calls"]["status"] == "STABLE"
    assert comparison["layers"]["genomic_overall"]["status"] == "STABLE"

    assert (
        comparison["layers"]["surveillance_context"]["status"]
        == "CHANGED"
    )

    assert (
        comparison["layers"]["integrated_concordance"]["status"]
        == "NOT_AVAILABLE"
    )

    assert (
        "underlying genomic result is stable"
        in comparison["interpretation"].lower()
    )
    assert (
        "surveillance/context outputs changed"
        in comparison["interpretation"].lower()
    )
