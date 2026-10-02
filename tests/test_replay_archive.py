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
