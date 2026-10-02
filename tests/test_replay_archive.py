from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "archive_replay_inputs.py"
READINESS_SCRIPT = (
    REPO_ROOT / "scripts" / "check_historical_reexecution.py"
)


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
    # One unique replay-input object plus the provenance document.
    assert "New objects: 2" in first_run.stdout
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
    assert len(objects) == 2

    replay_object = (
        archive
        / snapshot["inputs"]["first"]["object_path"]
    )
    assert replay_object.read_bytes() == content

    provenance_object = (
        archive
        / snapshot["provenance"]["object_path"]
    )
    assert provenance_object.read_bytes() == provenance.read_bytes()
    assert (
        sha256_bytes(provenance_object.read_bytes())
        == snapshot["provenance"]["sha256"]
    )

    second_run = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "New objects: 0" in second_run.stdout
    # Provenance plus both replay-input records reuse existing objects.
    assert "Existing objects reused: 3" in second_run.stdout
    assert len(
        list((archive / "objects" / "sha256").glob("*/*"))
    ) == 2


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
            "--current-provenance",
            str(provenance),
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

    aphis = repo / "hpai-wild-birds.csv"
    aphis.write_text(
        "case_id,state\n"
        "historical-case,AZ\n",
        encoding="utf-8",
    )
    historical_aphis_sha = sha256_bytes(aphis.read_bytes())

    provenance = repo / "run_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "replay_inputs": {
                    "metadata": {
                        "path": "metadata.tsv",
                        "sha256": metadata_sha,
                    },
                    "aphis_snapshot": {
                        "path": "hpai-wild-birds.csv",
                        "sha256": historical_aphis_sha,
                    },
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

    # Simulate an updated APHIS surveillance snapshot while leaving all
    # genomic outputs byte-for-byte unchanged.
    aphis.write_text(
        "case_id,state\n"
        "historical-case,AZ\n"
        "new-case,CA\n",
        encoding="utf-8",
    )
    current_aphis_sha = sha256_bytes(aphis.read_bytes())

    current_provenance = repo / "current_run_provenance.json"
    current_provenance.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "replay_inputs": {
                    "metadata": {
                        "path": "metadata.tsv",
                        "sha256": metadata_sha,
                    },
                    "aphis_snapshot": {
                        "path": "hpai-wild-birds.csv",
                        "sha256": current_aphis_sha,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    # The derived surveillance/context output changes accordingly.
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
            "--current-provenance",
            str(current_provenance),
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

    assert comparison["schema_version"] == 3
    assert (
        comparison["attribution_summary"]
        == "Changed replay input: APHIS outbreak snapshot."
    )

    attribution = comparison["replay_input_attribution"]

    assert attribution["changed_count"] == 1
    assert attribution["changed_labels"] == ["aphis_snapshot"]

    attribution_by_label = {
        row["label"]: row
        for row in attribution["inputs"]
    }

    assert attribution_by_label["metadata"]["status"] == "MATCH"

    aphis_change = attribution_by_label["aphis_snapshot"]
    assert aphis_change["status"] == "CHANGED"
    assert aphis_change["group"] == "outbreak_context"
    assert (
        aphis_change["historical_sha256"]
        == historical_aphis_sha
    )
    assert (
        aphis_change["current_sha256"]
        == current_aphis_sha
    )

    layer_attribution = comparison["layer_attribution"]

    context_attribution = layer_attribution[
        "surveillance_context"
    ]
    assert context_attribution["layer_status"] == "CHANGED"
    assert (
        context_attribution["relationship"]
        == "COINCIDENT_INPUT_CHANGE"
    )
    assert context_attribution["changed_replay_inputs"] == [
        "aphis_snapshot"
    ]
    assert context_attribution["changed_replay_groups"] == [
        "outbreak_context"
    ]

    integrated_attribution = layer_attribution[
        "integrated_concordance"
    ]
    assert (
        integrated_attribution["relationship"]
        == "NOT_ASSESSABLE"
    )
    assert integrated_attribution["changed_replay_inputs"] == []

    assert (
        comparison["layer_attribution_summary"]
        == (
            "The surveillance/context change occurred alongside "
            "updated outbreak context input."
        )
    )



def test_schema3_archive_preserves_execution_spec_without_raw_reads(
    tmp_path,
):
    repo = tmp_path / "repo"
    repo.mkdir()

    raw_reads = repo / "sample1.fastq.gz"
    raw_reads.write_bytes(b"historical raw reads\n")
    raw_sha = sha256_bytes(raw_reads.read_bytes())

    context = repo / "metadata.tsv"
    context.write_bytes(b"sample_id\tstate\nsample1\tAZ\n")
    context_sha = sha256_bytes(context.read_bytes())

    effective_config = repo / "effective_config.json"
    effective_config.write_text(
        json.dumps(
            {
                "reads_dir": "data",
                "results_dir": "results",
                "metadata_file": "metadata.tsv",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    config_sha = sha256_bytes(effective_config.read_bytes())

    provenance = repo / "run_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "workflow": {
                    "config_file": "effective_config.json",
                    "config_sha256": config_sha,
                },
                "primary_inputs": {
                    "sample1": {
                        "path": "sample1.fastq.gz",
                        "sha256": raw_sha,
                        "size_bytes": raw_reads.stat().st_size,
                    }
                },
                "replay_inputs": {
                    "metadata": {
                        "path": "metadata.tsv",
                        "sha256": context_sha,
                    }
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    provenance_sha = sha256_bytes(provenance.read_bytes())
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

    snapshot = json.loads(
        (
            archive
            / "snapshots"
            / f"{provenance_sha}.json"
        ).read_text(encoding="utf-8")
    )

    assert snapshot["schema_version"] == 2
    assert snapshot["snapshot_id"] == provenance_sha

    provenance_record = snapshot["provenance"]
    assert provenance_record["sha256"] == provenance_sha
    provenance_object = archive / provenance_record["object_path"]
    assert provenance_object.read_bytes() == provenance.read_bytes()

    execution = snapshot["execution_spec"]["effective_config"]
    assert execution["sha256"] == config_sha
    config_object = archive / execution["object_path"]
    assert config_object.read_bytes() == effective_config.read_bytes()

    assert snapshot["inputs"]["metadata"]["sha256"] == context_sha

    # Primary FASTQ identity is preserved in historical provenance, but
    # potentially large raw-read files are not copied into the replay archive.
    raw_object = (
        archive
        / "objects"
        / "sha256"
        / raw_sha[:2]
        / raw_sha
    )
    assert not raw_object.exists()


def test_historical_reexecution_readiness_detects_primary_input_drift(
    tmp_path,
):
    repo = tmp_path / "repo"
    repo.mkdir()

    reads = repo / "sample1.fastq.gz"
    reads.write_bytes(b"historical raw reads\n")
    reads_sha = sha256_bytes(reads.read_bytes())

    metadata = repo / "metadata.tsv"
    metadata.write_bytes(
        b"sample_id\tstate\nsample1\tAZ\n"
    )
    metadata_sha = sha256_bytes(metadata.read_bytes())

    effective_config = repo / "effective_config.json"
    effective_config.write_text(
        json.dumps(
            {
                "reads_dir": ".",
                "results_dir": "results",
                "metadata_file": "metadata.tsv",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    config_sha = sha256_bytes(
        effective_config.read_bytes()
    )

    provenance = repo / "run_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "workflow": {
                    "git_commit": "historical-commit",
                    "config_file": "effective_config.json",
                    "config_sha256": config_sha,
                },
                "conda_environment_files": {
                    "py-tools": {
                        "path": "envs/py-tools.yaml",
                        "sha256": "a" * 64,
                    }
                },
                "primary_inputs": {
                    "sample1": {
                        "path": "sample1.fastq.gz",
                        "sha256": reads_sha,
                        "size_bytes": reads.stat().st_size,
                    }
                },
                "replay_inputs": {
                    "metadata": {
                        "path": "metadata.tsv",
                        "sha256": metadata_sha,
                    }
                },
            },
            sort_keys=True,
        )
        + "\n",
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

    readiness_json = repo / "readiness.json"

    ready_run = subprocess.run(
        [
            sys.executable,
            str(READINESS_SCRIPT),
            "--archive-root",
            str(archive),
            "--snapshot",
            "current",
            "--repo-root",
            str(repo),
            "--output-json",
            str(readiness_json),
        ],
        capture_output=True,
        text=True,
    )

    assert ready_run.returncode == 0
    assert "Re-execution ready: YES" in ready_run.stdout

    readiness = json.loads(
        readiness_json.read_text(encoding="utf-8")
    )

    assert readiness["ready"] is True
    assert readiness["primary_inputs"]["status"] == "MATCH"
    assert (
        readiness["effective_config"]["status"]
        == "AVAILABLE"
    )
    assert (
        readiness["replay_inputs"]["status"]
        == "AVAILABLE"
    )

    # Historical raw reads drift after archival.
    reads.write_bytes(b"changed raw reads\n")

    changed_run = subprocess.run(
        [
            sys.executable,
            str(READINESS_SCRIPT),
            "--archive-root",
            str(archive),
            "--snapshot",
            "current",
            "--repo-root",
            str(repo),
            "--output-json",
            str(readiness_json),
        ],
        capture_output=True,
        text=True,
    )

    assert changed_run.returncode == 1
    assert "Re-execution ready: NO" in changed_run.stdout

    changed = json.loads(
        readiness_json.read_text(encoding="utf-8")
    )

    assert changed["ready"] is False
    assert (
        changed["primary_inputs"]["status"]
        == "NOT_READY"
    )
    assert (
        changed["primary_inputs"]["inputs"][0]["status"]
        == "CHANGED"
    )
