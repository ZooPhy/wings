#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


ARCHIVE_FORMAT = "WINGS_REPLAY_ARCHIVE"
REPORT_FORMAT = "WINGS_REEXECUTION_READINESS"


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


def resolve_archive_path(
    archive_root: Path,
    relative_text: str,
) -> Path:
    relative = Path(relative_text)

    if relative.is_absolute():
        raise ValueError(
            f"Archive path must be relative: {relative_text}"
        )

    resolved = (archive_root / relative).resolve()

    try:
        resolved.relative_to(archive_root)
    except ValueError as error:
        raise ValueError(
            f"Archive path escapes archive root: {relative_text}"
        ) from error

    return resolved


def resolve_snapshot(
    archive_root: Path,
    requested: str,
) -> Path:
    if requested == "current":
        current = read_json(archive_root / "current.json")

        if current.get("archive_format") != ARCHIVE_FORMAT:
            raise ValueError("Invalid replay archive current.json")

        relative = str(current.get("snapshot", "")).strip()
        if not relative:
            raise ValueError(
                "Replay archive current.json has no snapshot path."
            )

        return resolve_archive_path(
            archive_root,
            relative,
        )

    if not re.fullmatch(r"[0-9a-fA-F]{64}", requested):
        raise ValueError(
            "--snapshot must be 'current' or a 64-character "
            "snapshot ID"
        )

    return (
        archive_root
        / "snapshots"
        / f"{requested.lower()}.json"
    )


def run_git(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "NOT_CAPTURED"


def check_archived_object(
    archive_root: Path,
    record: dict,
) -> dict[str, object]:
    expected = str(
        record.get("sha256", "")
    ).strip().lower()
    object_rel = str(
        record.get("object_path", "")
    ).strip()

    result: dict[str, object] = {
        "sha256": expected or None,
        "object_path": object_rel or None,
    }

    if not object_rel or not re.fullmatch(
        r"[0-9a-f]{64}",
        expected,
    ):
        result["status"] = "INVALID"
        return result

    path = resolve_archive_path(
        archive_root,
        object_rel,
    )

    if not path.is_file():
        result["status"] = "MISSING"
        return result

    observed = sha256_file(path)
    result["observed_sha256"] = observed

    result["status"] = (
        "AVAILABLE"
        if observed == expected
        else "INVALID"
    )

    return result


def check_primary_inputs(
    provenance: dict,
    repo_root: Path,
) -> dict[str, object]:
    primary = provenance.get("primary_inputs")

    if not isinstance(primary, dict) or not primary:
        return {
            "status": "NOT_AVAILABLE",
            "counts": {},
            "inputs": [],
        }

    rows: list[dict[str, object]] = []

    for label in sorted(primary):
        record = primary[label]

        if not isinstance(record, dict):
            rows.append(
                {
                    "label": label,
                    "status": "INVALID",
                }
            )
            continue

        recorded_path = str(
            record.get("path", "")
        ).strip()
        expected_sha = str(
            record.get("sha256", "")
        ).strip().lower()
        expected_size = record.get("size_bytes")

        path = Path(recorded_path).expanduser()
        if not path.is_absolute():
            path = repo_root / path
        path = path.resolve()

        row: dict[str, object] = {
            "label": label,
            "path": recorded_path,
            "expected_sha256": expected_sha or None,
            "expected_size_bytes": expected_size,
        }

        if not recorded_path or not re.fullmatch(
            r"[0-9a-f]{64}",
            expected_sha,
        ):
            row["status"] = "INVALID"
        elif not path.is_file():
            row["status"] = "MISSING"
        else:
            observed_sha = sha256_file(path)
            observed_size = path.stat().st_size

            row["observed_sha256"] = observed_sha
            row["observed_size_bytes"] = observed_size

            row["status"] = (
                "MATCH"
                if observed_sha == expected_sha
                else "CHANGED"
            )

        rows.append(row)

    counts = Counter(
        str(row["status"])
        for row in rows
    )

    overall = (
        "MATCH"
        if rows and all(
            row["status"] == "MATCH"
            for row in rows
        )
        else "NOT_READY"
    )

    return {
        "status": overall,
        "counts": dict(sorted(counts.items())),
        "inputs": rows,
    }


def check_replay_inputs(
    archive_root: Path,
    snapshot: dict,
) -> dict[str, object]:
    inputs = snapshot.get("inputs")

    if not isinstance(inputs, dict) or not inputs:
        return {
            "status": "NOT_AVAILABLE",
            "counts": {},
            "inputs": [],
        }

    rows = []

    for label in sorted(inputs):
        record = inputs[label]

        if not isinstance(record, dict):
            rows.append(
                {
                    "label": label,
                    "status": "INVALID",
                }
            )
            continue

        checked = check_archived_object(
            archive_root,
            record,
        )
        checked["label"] = label
        rows.append(checked)

    counts = Counter(
        str(row["status"])
        for row in rows
    )

    overall = (
        "AVAILABLE"
        if rows and all(
            row["status"] == "AVAILABLE"
            for row in rows
        )
        else "INVALID"
    )

    return {
        "status": overall,
        "counts": dict(sorted(counts.items())),
        "inputs": rows,
    }


def check_environment_records(
    provenance: dict,
) -> dict[str, object]:
    envs = provenance.get("conda_environment_files")

    if not isinstance(envs, dict) or not envs:
        return {
            "status": "NOT_AVAILABLE",
            "count": 0,
            "incomplete": [],
        }

    incomplete = []

    for label, record in envs.items():
        if not isinstance(record, dict):
            incomplete.append(label)
            continue

        sha = str(
            record.get("sha256", "")
        ).strip().lower()

        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            incomplete.append(label)

    return {
        "status": (
            "AVAILABLE"
            if not incomplete
            else "INCOMPLETE"
        ),
        "count": len(envs),
        "incomplete": sorted(incomplete),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Assess whether a historical WINGS replay snapshot "
            "can be re-executed using current workflow code and "
            "historical inputs/configuration."
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
        "--output-json",
        type=Path,
    )
    args = parser.parse_args()

    archive_root = args.archive_root.resolve()
    repo_root = args.repo_root.resolve()

    try:
        snapshot_path = resolve_snapshot(
            archive_root,
            args.snapshot,
        )
        snapshot = read_json(snapshot_path)

        if snapshot.get("archive_format") != ARCHIVE_FORMAT:
            raise ValueError(
                f"Invalid replay snapshot: {snapshot_path}"
            )

        snapshot_id = str(
            snapshot.get("snapshot_id", "")
        ).strip()

        blockers: list[str] = []
        warnings: list[str] = []

        provenance_record = snapshot.get("provenance")
        provenance_check: dict[str, object]
        provenance: dict | None = None

        if not isinstance(provenance_record, dict):
            provenance_check = {
                "status": "NOT_AVAILABLE",
            }
            blockers.append(
                "Historical provenance record is unavailable."
            )
        elif not provenance_record.get("object_path"):
            provenance_check = {
                "status": "NOT_AVAILABLE",
                "sha256": provenance_record.get("sha256"),
            }
            blockers.append(
                "Historical provenance bytes were not archived."
            )
        else:
            provenance_check = check_archived_object(
                archive_root,
                provenance_record,
            )

            if provenance_check["status"] == "AVAILABLE":
                provenance_path = resolve_archive_path(
                    archive_root,
                    str(provenance_record["object_path"]),
                )
                provenance = read_json(provenance_path)
            else:
                blockers.append(
                    "Historical provenance archive object is "
                    "missing or invalid."
                )

        provenance_schema = (
            int(provenance.get("schema_version", 0))
            if provenance is not None
            else 0
        )

        if provenance is not None and provenance_schema < 3:
            blockers.append(
                "Historical provenance predates schema 3 and "
                "does not contain primary sequencing inputs."
            )

        if provenance is not None:
            primary = check_primary_inputs(
                provenance,
                repo_root,
            )
        else:
            primary = {
                "status": "NOT_AVAILABLE",
                "counts": {},
                "inputs": [],
            }

        if primary["status"] != "MATCH":
            blockers.append(
                "One or more historical primary sequencing "
                "inputs are missing, changed, or invalid."
            )

        execution_spec = snapshot.get("execution_spec")
        effective_config: dict[str, object]

        if (
            isinstance(execution_spec, dict)
            and isinstance(
                execution_spec.get("effective_config"),
                dict,
            )
        ):
            effective_config = check_archived_object(
                archive_root,
                execution_spec["effective_config"],
            )
        else:
            effective_config = {
                "status": "NOT_AVAILABLE",
            }

        if effective_config["status"] != "AVAILABLE":
            blockers.append(
                "Historical effective configuration is "
                "unavailable or invalid."
            )

        replay = check_replay_inputs(
            archive_root,
            snapshot,
        )

        if replay["status"] != "AVAILABLE":
            blockers.append(
                "One or more archived replay/context inputs "
                "are unavailable or invalid."
            )

        workflow_commit = {
            "historical": None,
            "current": None,
            "status": "UNKNOWN",
        }

        if provenance is not None:
            workflow = provenance.get("workflow")
            if isinstance(workflow, dict):
                historical_commit = str(
                    workflow.get("git_commit", "")
                ).strip()
                current_commit = run_git(
                    repo_root,
                    "rev-parse",
                    "HEAD",
                )

                workflow_commit = {
                    "historical": (
                        historical_commit or None
                    ),
                    "current": (
                        current_commit
                        if current_commit != "NOT_CAPTURED"
                        else None
                    ),
                    "status": "UNKNOWN",
                }

                if (
                    historical_commit
                    and current_commit != "NOT_CAPTURED"
                ):
                    workflow_commit["status"] = (
                        "SAME"
                        if historical_commit == current_commit
                        else "DIFFERENT"
                    )

        if workflow_commit["status"] == "DIFFERENT":
            warnings.append(
                "Current workflow commit differs from the "
                "historical workflow commit."
            )
        elif workflow_commit["status"] == "UNKNOWN":
            warnings.append(
                "Historical/current workflow commit comparison "
                "could not be completed."
            )

        environments = (
            check_environment_records(provenance)
            if provenance is not None
            else {
                "status": "NOT_AVAILABLE",
                "count": 0,
                "incomplete": [],
            }
        )

        if environments["status"] != "AVAILABLE":
            warnings.append(
                "Historical Conda environment records are "
                "incomplete or unavailable."
            )

        ready = len(blockers) == 0

        report = {
            "format": REPORT_FORMAT,
            "schema_version": 1,
            "mode": "current_code_historical_inputs",
            "snapshot_id": snapshot_id,
            "snapshot_manifest": str(snapshot_path),
            "ready": ready,
            "blockers": blockers,
            "warnings": warnings,
            "provenance": {
                **provenance_check,
                "schema_version": (
                    provenance_schema
                    if provenance is not None
                    else None
                ),
            },
            "primary_inputs": primary,
            "effective_config": effective_config,
            "replay_inputs": replay,
            "workflow_commit": workflow_commit,
            "environment_records": environments,
        }

        if args.output_json:
            args.output_json.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            args.output_json.write_text(
                json.dumps(
                    report,
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
        return 2

    print(f"Historical snapshot: {snapshot_id}")
    print(
        "Primary sequencing inputs: "
        f"{primary['status']}"
    )
    print(
        "Effective configuration: "
        f"{effective_config['status']}"
    )
    print(
        "Replay/context inputs: "
        f"{replay['status']}"
    )
    print(
        "Workflow commit: "
        f"{workflow_commit['status']}"
    )
    print(
        "Environment records: "
        f"{environments['status']}"
    )
    print(
        "Re-execution ready: "
        + ("YES" if ready else "NO")
    )

    if blockers:
        print()
        print("Blockers:")
        for blocker in blockers:
            print(f"- {blocker}")

    if warnings:
        print()
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
