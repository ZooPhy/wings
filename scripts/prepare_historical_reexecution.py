#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ARCHIVE_FORMAT = "WINGS_REPLAY_ARCHIVE"
WORKSPACE_FORMAT = "WINGS_REEXECUTION_WORKSPACE"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def resolve_archive_object(
    archive_root: Path,
    relative_text: str,
) -> Path:
    relative = Path(relative_text)

    if relative.is_absolute():
        raise ValueError(
            f"Archive object path must be relative: {relative_text}"
        )

    resolved = (archive_root / relative).resolve()

    try:
        resolved.relative_to(archive_root)
    except ValueError as error:
        raise ValueError(
            f"Archive object escapes archive root: {relative_text}"
        ) from error

    return resolved


def copy_verified(
    source: Path,
    destination: Path,
    expected_sha256: str,
) -> None:
    if not source.is_file():
        raise FileNotFoundError(
            f"Archived object is unavailable: {source}"
        )

    observed = sha256_file(source)
    if observed != expected_sha256:
        raise ValueError(
            f"Archived object failed SHA-256 verification: {source}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)

    restored = sha256_file(destination)
    if restored != expected_sha256:
        raise ValueError(
            f"Workspace copy failed SHA-256 verification: {destination}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare an isolated WINGS historical re-execution "
            "workspace after readiness validation."
        )
    )
    parser.add_argument(
        "--archive-root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--snapshot",
        default="current",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
    )
    args = parser.parse_args()

    archive_root = args.archive_root.expanduser().resolve()
    repo_root = args.repo_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    readiness_script = Path(__file__).with_name(
        "check_historical_reexecution.py"
    )
    restore_script = Path(__file__).with_name(
        "restore_replay_snapshot.py"
    )

    temporary_readiness: Path | None = None

    try:
        if output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError(
                "Re-execution output directory is not empty: "
                f"{output_dir}"
            )

        output_dir.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with tempfile.NamedTemporaryFile(
            prefix="wings-reexecution-readiness-",
            suffix=".json",
            delete=False,
        ) as handle:
            temporary_readiness = Path(handle.name)

        readiness_run = subprocess.run(
            [
                sys.executable,
                str(readiness_script),
                "--archive-root",
                str(archive_root),
                "--snapshot",
                args.snapshot,
                "--repo-root",
                str(repo_root),
                "--output-json",
                str(temporary_readiness),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if readiness_run.returncode != 0:
            if readiness_run.stdout:
                print(
                    readiness_run.stdout.rstrip(),
                    file=sys.stderr,
                )
            if readiness_run.stderr:
                print(
                    readiness_run.stderr.rstrip(),
                    file=sys.stderr,
                )
            raise ValueError(
                "Historical snapshot is not re-execution ready."
            )

        readiness = read_json(temporary_readiness)

        if not readiness.get("ready", False):
            raise ValueError(
                "Readiness report did not mark snapshot as ready."
            )

        snapshot_id = str(
            readiness.get("snapshot_id", "")
        ).strip()

        if not re.fullmatch(r"[0-9a-f]{64}", snapshot_id):
            raise ValueError(
                f"Invalid snapshot ID: {snapshot_id!r}"
            )

        # Restore replay/context inputs using the existing tested restoration
        # pathway. This creates output_dir/inputs and replay_workspace.json.
        restore_run = subprocess.run(
            [
                sys.executable,
                str(restore_script),
                "--archive-root",
                str(archive_root),
                "--snapshot",
                snapshot_id,
                "--output-dir",
                str(output_dir),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if restore_run.returncode != 0:
            if restore_run.stdout:
                print(
                    restore_run.stdout.rstrip(),
                    file=sys.stderr,
                )
            if restore_run.stderr:
                print(
                    restore_run.stderr.rstrip(),
                    file=sys.stderr,
                )
            raise ValueError(
                "Historical replay-input restoration failed."
            )

        snapshot_path = (
            archive_root
            / "snapshots"
            / f"{snapshot_id}.json"
        )
        snapshot = read_json(snapshot_path)

        if snapshot.get("archive_format") != ARCHIVE_FORMAT:
            raise ValueError(
                f"Invalid replay snapshot: {snapshot_path}"
            )

        provenance_record = snapshot.get("provenance")
        if not isinstance(provenance_record, dict):
            raise ValueError(
                "Replay snapshot has no provenance record."
            )

        provenance_sha = str(
            provenance_record.get("sha256", "")
        ).strip().lower()
        provenance_object_rel = str(
            provenance_record.get("object_path", "")
        ).strip()

        if not re.fullmatch(r"[0-9a-f]{64}", provenance_sha):
            raise ValueError(
                "Historical provenance has invalid SHA-256."
            )

        provenance_object = resolve_archive_object(
            archive_root,
            provenance_object_rel,
        )

        historical_provenance = (
            output_dir / "historical_provenance.json"
        )

        copy_verified(
            provenance_object,
            historical_provenance,
            provenance_sha,
        )

        provenance = read_json(historical_provenance)

        execution_spec = snapshot.get("execution_spec")
        if not isinstance(execution_spec, dict):
            raise ValueError(
                "Replay snapshot has no execution specification."
            )

        config_record = execution_spec.get(
            "effective_config"
        )
        if not isinstance(config_record, dict):
            raise ValueError(
                "Replay snapshot has no historical effective config."
            )

        config_sha = str(
            config_record.get("sha256", "")
        ).strip().lower()
        config_object_rel = str(
            config_record.get("object_path", "")
        ).strip()

        if not re.fullmatch(r"[0-9a-f]{64}", config_sha):
            raise ValueError(
                "Historical effective config has invalid SHA-256."
            )

        config_object = resolve_archive_object(
            archive_root,
            config_object_rel,
        )

        historical_config = (
            output_dir / "historical_effective_config.json"
        )

        copy_verified(
            config_object,
            historical_config,
            config_sha,
        )

        # Preserve the successful readiness assessment inside the workspace.
        workspace_readiness = output_dir / "readiness.json"
        shutil.copyfile(
            temporary_readiness,
            workspace_readiness,
        )

        replay_workspace = read_json(
            output_dir / "replay_workspace.json"
        )

        primary_inputs: dict[str, dict[str, object]] = {}

        for row in readiness[
            "primary_inputs"
        ].get("inputs", []):
            label = str(row.get("label", "")).strip()
            recorded_path = str(
                row.get("path", "")
            ).strip()

            if not label or not recorded_path:
                raise ValueError(
                    "Readiness report contains invalid primary input."
                )

            source = Path(recorded_path).expanduser()
            if not source.is_absolute():
                source = repo_root / source
            source = source.resolve()

            if not source.is_file():
                raise FileNotFoundError(
                    f"Verified primary input disappeared: {source}"
                )

            expected_sha = str(
                row.get("expected_sha256", "")
            ).strip().lower()

            if sha256_file(source) != expected_sha:
                raise ValueError(
                    "Primary input changed after readiness check: "
                    f"{label}"
                )

            primary_inputs[label] = {
                "original_path": recorded_path,
                "verified_source_path": str(source),
                "sha256": expected_sha,
                "size_bytes": source.stat().st_size,
                "status": "MATCH",
                "copied_into_workspace": False,
            }

        workflow = provenance.get("workflow")
        if not isinstance(workflow, dict):
            workflow = {}

        manifest = {
            "format": WORKSPACE_FORMAT,
            "schema_version": 1,
            "created_at_utc": datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "mode": "current_code_historical_inputs",
            "snapshot_id": snapshot_id,
            "historical_provenance_sha256": provenance_sha,
            "historical_workflow_commit": workflow.get(
                "git_commit"
            ),
            "executing_workflow_commit": readiness.get(
                "workflow_commit",
                {},
            ).get("current"),
            "historical_effective_config": {
                "path": (
                    historical_config.relative_to(
                        output_dir
                    ).as_posix()
                ),
                "sha256": config_sha,
            },
            "primary_inputs": primary_inputs,
            "replay_inputs": replay_workspace.get(
                "inputs",
                {},
            ),
            "readiness_report": (
                workspace_readiness.relative_to(
                    output_dir
                ).as_posix()
            ),
            "replay_workspace": "replay_workspace.json",
            # Historical config is preserved verbatim. A later step must
            # rewrite results/input paths before execution is permitted.
            "execution_config_generated": False,
            "launch_ready": False,
        }

        manifest_path = (
            output_dir / "reexecution_manifest.json"
        )
        manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        if (
            temporary_readiness is not None
            and temporary_readiness.exists()
        ):
            temporary_readiness.unlink()

    print(
        "Re-execution workspace prepared: "
        f"{output_dir}"
    )
    print(f"Historical snapshot: {snapshot_id}")
    print(
        "Primary sequencing inputs verified: "
        f"{len(primary_inputs)}"
    )
    print(
        "Replay/context inputs restored: "
        f"{len(replay_workspace.get('inputs', {}))}"
    )
    print(
        "Launch ready: NO "
        "(execution-specific config has not been generated)"
    )
    print(
        "Manifest: "
        f"{output_dir / 'reexecution_manifest.json'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
