#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE_FORMAT = "WINGS_REEXECUTION_WORKSPACE"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


def atomic_write_json(path: Path, data: dict) -> None:
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def require_inside(path: Path, root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(
            f"{label} escapes re-execution workspace: {path}"
        ) from error


def workspace_entry(workspace: Path, relative_text: str) -> Path:
    relative = Path(relative_text)

    if relative.is_absolute():
        raise ValueError(
            f"Workspace path must be relative: {relative_text}"
        )

    candidate = workspace / relative

    # Check the containing directory rather than resolving the final path.
    # Primary FASTQs are deliberately symlinks to source data outside the
    # workspace.
    parent = candidate.parent.resolve()
    try:
        parent.relative_to(workspace.resolve())
    except ValueError as error:
        raise ValueError(
            f"Workspace path escapes workspace: {relative_text}"
        ) from error

    return candidate


def git_state(repo_root: Path) -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Could not determine current Git commit.")

    # Ignore untracked runtime artifacts but reject modifications to any
    # tracked workflow/code/configuration file.
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=no",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    return commit, not bool(status)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an isolated WINGS historical re-execution workspace "
            "with a Snakemake dry-run and mark it launch-ready."
        )
    )
    parser.add_argument(
        "--workspace",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
    )
    parser.add_argument(
        "--snakemake",
        default="snakemake",
        help="Snakemake executable to use",
    )
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    repo_root = args.repo_root.expanduser().resolve()
    manifest_path = workspace / "reexecution_manifest.json"

    manifest: dict | None = None

    try:
        manifest = read_json(manifest_path)

        if manifest.get("format") != WORKSPACE_FORMAT:
            raise ValueError(
                f"Invalid re-execution workspace: {workspace}"
            )

        if not manifest.get("execution_config_generated", False):
            raise ValueError(
                "Execution configuration has not been generated."
            )

        # Any new validation attempt first revokes launch readiness.
        manifest["dry_run_validated"] = False
        manifest["launch_ready"] = False
        manifest.pop("dry_run_validation", None)
        atomic_write_json(manifest_path, manifest)

        config_record = manifest.get("execution_config")
        if not isinstance(config_record, dict):
            raise ValueError(
                "Workspace manifest has no execution_config record."
            )

        config_rel = str(config_record.get("path", "")).strip()
        expected_config_sha = str(
            config_record.get("sha256", "")
        ).strip().lower()

        if not SHA256_RE.fullmatch(expected_config_sha):
            raise ValueError(
                "Execution configuration has invalid SHA-256."
            )

        config_path = workspace_entry(workspace, config_rel)

        if not config_path.is_file():
            raise FileNotFoundError(
                f"Execution configuration is missing: {config_path}"
            )

        observed_config_sha = sha256_file(config_path)
        if observed_config_sha != expected_config_sha:
            raise ValueError(
                "Execution configuration changed after generation."
            )

        config = read_json(config_path)

        historical = config.get("historical_reexecution")
        if not isinstance(historical, dict):
            raise ValueError(
                "Execution configuration has no historical_reexecution block."
            )

        if historical.get("enabled") is not True:
            raise ValueError(
                "Historical re-execution mode is not enabled."
            )

        if (
            historical.get("mode")
            != "current_code_historical_inputs"
        ):
            raise ValueError(
                "Unexpected historical re-execution mode."
            )

        snapshot_id = str(manifest.get("snapshot_id", "")).strip()
        if historical.get("snapshot_id") != snapshot_id:
            raise ValueError(
                "Execution configuration snapshot does not match workspace."
            )

        results_dir = Path(
            str(config.get("results_dir", ""))
        ).expanduser().resolve()
        reads_dir = Path(
            str(config.get("reads_dir", ""))
        ).expanduser().resolve()
        metadata_file = Path(
            str(config.get("metadata_file", ""))
        ).expanduser().resolve()
        phylogeny_dir = Path(
            str(config.get("phylogeny_dir", ""))
        ).expanduser().resolve()

        expected_results = workspace_entry(
            workspace,
            str(manifest.get("execution_results_dir", "")),
        ).resolve()

        if results_dir != expected_results:
            raise ValueError(
                "Execution results_dir does not match workspace manifest."
            )

        require_inside(results_dir, workspace, "results_dir")
        require_inside(reads_dir, workspace, "reads_dir")
        require_inside(metadata_file, workspace, "metadata_file")
        require_inside(
            phylogeny_dir,
            results_dir,
            "phylogeny_dir",
        )

        #
        # Verify the explicitly pinned historical interpretation baseline.
        # It must remain separate from this re-execution's output archive.
        #
        baseline_snapshot_id = str(
            historical.get("baseline_snapshot_id", "")
        ).strip()

        if baseline_snapshot_id != snapshot_id:
            raise ValueError(
                "Historical baseline snapshot is not the re-executed "
                "snapshot."
            )

        baseline_archive_text = str(
            historical.get("baseline_archive_root", "")
        ).strip()

        if not baseline_archive_text:
            raise ValueError(
                "Historical baseline archive is not configured."
            )

        baseline_archive_root = (
            Path(baseline_archive_text)
            .expanduser()
            .resolve()
        )

        if not baseline_archive_root.is_dir():
            raise FileNotFoundError(
                "Historical baseline archive is unavailable: "
                f"{baseline_archive_root}"
            )

        new_archive_root = (
            results_dir / "replay_archive"
        ).resolve()

        if baseline_archive_root == new_archive_root:
            raise ValueError(
                "Historical baseline archive and new output archive "
                "must be separate."
            )

        try:
            baseline_archive_root.relative_to(workspace)
        except ValueError:
            pass
        else:
            raise ValueError(
                "Historical baseline archive must be outside the "
                "re-execution workspace."
            )

        baseline_interpretation = (
            baseline_archive_root
            / "interpretations"
            / f"{snapshot_id}.json"
        )

        if not baseline_interpretation.is_file():
            raise FileNotFoundError(
                "Pinned historical interpretation is unavailable: "
                f"{baseline_interpretation}"
            )

        baseline_data = read_json(
            baseline_interpretation
        )

        if (
            baseline_data.get("format")
            != "WINGS_INTERPRETATION_ARCHIVE"
        ):
            raise ValueError(
                "Pinned historical interpretation has invalid format."
            )

        if (
            str(baseline_data.get("snapshot_id", "")).strip()
            != snapshot_id
        ):
            raise ValueError(
                "Pinned historical interpretation snapshot mismatch."
            )

        if (
            str(
                baseline_data.get(
                    "provenance_sha256",
                    "",
                )
            ).strip()
            != snapshot_id
        ):
            raise ValueError(
                "Pinned interpretation provenance does not match "
                "the historical snapshot."
            )

        replay_snapshot_rel = str(
            baseline_data.get("replay_snapshot", "")
        ).strip()

        if not replay_snapshot_rel:
            raise ValueError(
                "Pinned historical interpretation has no replay snapshot."
            )

        replay_snapshot_path = (
            baseline_archive_root
            / replay_snapshot_rel
        ).resolve()

        try:
            replay_snapshot_path.relative_to(
                baseline_archive_root
            )
        except ValueError as error:
            raise ValueError(
                "Historical replay snapshot escapes baseline archive."
            ) from error

        if not replay_snapshot_path.is_file():
            raise FileNotFoundError(
                "Historical replay snapshot is unavailable: "
                f"{replay_snapshot_path}"
            )

        replay_snapshot = read_json(
            replay_snapshot_path
        )

        if (
            replay_snapshot.get("archive_format")
            != "WINGS_REPLAY_ARCHIVE"
        ):
            raise ValueError(
                "Historical replay snapshot has invalid format."
            )

        if (
            str(replay_snapshot.get("snapshot_id", "")).strip()
            != snapshot_id
        ):
            raise ValueError(
                "Historical replay snapshot ID mismatch."
            )

        baseline_artifacts = baseline_data.get("artifacts")
        if (
            not isinstance(baseline_artifacts, dict)
            or not baseline_artifacts
        ):
            raise ValueError(
                "Pinned historical interpretation has no artifacts."
            )

        baseline_artifact_count = 0

        for relative, record in sorted(
            baseline_artifacts.items()
        ):
            if not isinstance(record, dict):
                raise ValueError(
                    "Invalid historical artifact record: "
                    f"{relative}"
                )

            expected_sha = str(
                record.get("sha256", "")
            ).strip().lower()

            if not SHA256_RE.fullmatch(expected_sha):
                raise ValueError(
                    "Invalid historical artifact SHA-256: "
                    f"{relative}"
                )

            object_rel = str(
                record.get("object_path", "")
            ).strip()

            if not object_rel:
                raise ValueError(
                    "Historical artifact has no object path: "
                    f"{relative}"
                )

            artifact_object = (
                baseline_archive_root / object_rel
            ).resolve()

            try:
                artifact_object.relative_to(
                    baseline_archive_root
                )
            except ValueError as error:
                raise ValueError(
                    "Historical artifact escapes baseline archive: "
                    f"{relative}"
                ) from error

            if not artifact_object.is_file():
                raise FileNotFoundError(
                    "Historical artifact object is unavailable: "
                    f"{relative}"
                )

            if sha256_file(artifact_object) != expected_sha:
                raise ValueError(
                    "Historical artifact failed SHA-256 verification: "
                    f"{relative}"
                )

            baseline_artifact_count += 1

        #
        # Reverify primary sequencing inputs and staged symlinks.
        #
        primary_inputs = manifest.get("primary_inputs")
        if not isinstance(primary_inputs, dict) or not primary_inputs:
            raise ValueError(
                "Workspace has no primary sequencing inputs."
            )

        for sample, record in sorted(primary_inputs.items()):
            if not isinstance(record, dict):
                raise ValueError(
                    f"Invalid primary-input record: {sample}"
                )

            expected_sha = str(
                record.get("sha256", "")
            ).strip().lower()

            if not SHA256_RE.fullmatch(expected_sha):
                raise ValueError(
                    f"Invalid primary-input SHA-256: {sample}"
                )

            source = Path(
                str(record.get("verified_source_path", ""))
            ).expanduser().resolve()

            if not source.is_file():
                raise FileNotFoundError(
                    f"Primary sequencing input disappeared: {source}"
                )

            if sha256_file(source) != expected_sha:
                raise ValueError(
                    f"Primary sequencing input changed: {sample}"
                )

            staged_rel = str(
                record.get("workspace_path", "")
            ).strip()
            staged = workspace_entry(
                workspace,
                staged_rel,
            )

            if not staged.is_symlink():
                raise ValueError(
                    f"Primary staged input is not a symlink: {sample}"
                )

            if staged.resolve() != source:
                raise ValueError(
                    f"Primary staged input points elsewhere: {sample}"
                )

            if sha256_file(staged) != expected_sha:
                raise ValueError(
                    f"Primary staged input hash mismatch: {sample}"
                )

        #
        # Reverify every restored replay/context artifact.
        #
        replay_inputs = manifest.get("replay_inputs")
        if not isinstance(replay_inputs, dict):
            raise ValueError(
                "Workspace has no replay/context inputs."
            )

        frozen = historical.get("frozen_inputs")
        if not isinstance(frozen, dict):
            raise ValueError(
                "Execution configuration has no frozen_inputs mapping."
            )

        if set(frozen) != set(replay_inputs):
            raise ValueError(
                "Frozen-input labels do not match restored replay inputs."
            )

        for label, record in sorted(replay_inputs.items()):
            if not isinstance(record, dict):
                raise ValueError(
                    f"Invalid replay-input record: {label}"
                )

            expected_sha = str(
                record.get("sha256", "")
            ).strip().lower()

            if not SHA256_RE.fullmatch(expected_sha):
                raise ValueError(
                    f"Invalid replay-input SHA-256: {label}"
                )

            restored_rel = str(
                record.get("restored_path", "")
            ).strip()

            restored = workspace_entry(
                workspace,
                restored_rel,
            )

            if not restored.is_file():
                raise FileNotFoundError(
                    f"Restored replay input disappeared: {label}"
                )

            if sha256_file(restored) != expected_sha:
                raise ValueError(
                    f"Restored replay input changed: {label}"
                )

            frozen_path = Path(
                str(frozen[label])
            ).expanduser().resolve()

            if frozen_path != restored.resolve():
                raise ValueError(
                    f"Frozen-input mapping changed: {label}"
                )

        #
        # Require an identifiable, clean current workflow revision.
        #
        commit_before, clean_before = git_state(repo_root)

        if not clean_before:
            raise ValueError(
                "Tracked repository files are modified. "
                "Commit or revert them before launch validation."
            )

        snakefile = repo_root / "Snakefile"
        if not snakefile.is_file():
            raise FileNotFoundError(
                f"Snakefile not found: {snakefile}"
            )

        dry_run_path = workspace / "snakemake_dry_run.txt"

        command = [
            args.snakemake,
            "--snakefile",
            str(snakefile),
            "--configfile",
            str(config_path),
            "--use-conda",
            "--dry-run",
        ]

        completed = subprocess.run(
            command,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        dry_run_path.write_text(
            completed.stdout,
            encoding="utf-8",
        )

        if completed.returncode != 0:
            raise ValueError(
                "Snakemake dry-run failed. See "
                f"{dry_run_path}"
            )

        if "This was a dry-run" not in completed.stdout:
            raise ValueError(
                "Snakemake returned success without the expected "
                "dry-run completion marker."
            )

        commit_after, clean_after = git_state(repo_root)

        if commit_after != commit_before:
            raise ValueError(
                "Git commit changed during dry-run validation."
            )

        if not clean_after:
            raise ValueError(
                "Tracked repository files changed during dry-run validation."
            )

        total_match = re.search(
            r"(?m)^total\s+(\d+)\s*$",
            completed.stdout,
        )
        initial_job_count = (
            int(total_match.group(1))
            if total_match
            else None
        )

        checkpoint_dynamic = (
            "checkpoint jobs" in completed.stdout
            or "DAG of jobs will be updated after completion"
            in completed.stdout
        )

        validation = {
            "status": "PASS",
            "validated_at_utc": datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "execution_config_sha256": observed_config_sha,
            "executing_workflow_commit": commit_after,
            "tracked_worktree_clean": True,
            "primary_input_count": len(primary_inputs),
            "replay_input_count": len(replay_inputs),
            "baseline_snapshot_id": baseline_snapshot_id,
            "baseline_archive_root": str(
                baseline_archive_root
            ),
            "baseline_interpretation_sha256": sha256_file(
                baseline_interpretation
            ),
            "baseline_artifact_count": baseline_artifact_count,
            "new_archive_root": str(new_archive_root),
            "initial_dag_job_count": initial_job_count,
            "checkpoint_dynamic_dag": checkpoint_dynamic,
            "dry_run_output": dry_run_path.relative_to(
                workspace
            ).as_posix(),
            "command": command,
            "exit_code": completed.returncode,
        }

        manifest["executing_workflow_commit"] = commit_after
        manifest["dry_run_validation"] = validation
        manifest["dry_run_validated"] = True
        manifest["launch_ready"] = True

        atomic_write_json(manifest_path, manifest)

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as error:
        if manifest is not None:
            manifest["dry_run_validated"] = False
            manifest["launch_ready"] = False
            manifest["dry_run_validation"] = {
                "status": "FAILED",
                "error": str(error),
            }
            try:
                atomic_write_json(manifest_path, manifest)
            except OSError:
                pass

        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Historical snapshot: {snapshot_id}")
    print(
        "Primary sequencing inputs verified: "
        f"{len(primary_inputs)}"
    )
    print(
        "Frozen replay/context inputs verified: "
        f"{len(replay_inputs)}"
    )
    print(
        "Historical baseline artifacts verified: "
        f"{baseline_artifact_count}"
    )
    print("Historical/output archive separation: PASS")
    print(
        "Initial Snakemake DAG jobs: "
        f"{initial_job_count if initial_job_count is not None else 'UNKNOWN'}"
    )
    print(
        "Checkpoint-dynamic DAG: "
        + ("YES" if checkpoint_dynamic else "NO")
    )
    print(f"Executing workflow commit: {commit_after}")
    print("Dry-run validated: YES")
    print("Launch ready: YES")
    print(f"Dry-run record: {dry_run_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
