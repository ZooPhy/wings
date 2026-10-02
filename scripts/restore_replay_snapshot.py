#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


ARCHIVE_FORMAT = "WINGS_REPLAY_ARCHIVE"
WORKSPACE_FORMAT = "WINGS_REPLAY_WORKSPACE"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_object(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in: {path}")

    return data


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")

    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def safe_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("._")
    if not cleaned:
        raise ValueError(f"Unsafe replay input label: {label!r}")
    return cleaned


def resolve_archive_object(
    archive_root: Path,
    object_path: str,
) -> Path:
    relative = Path(object_path)

    if relative.is_absolute():
        raise ValueError(
            f"Archive object path must be relative: {object_path}"
        )

    resolved = (archive_root / relative).resolve()

    try:
        resolved.relative_to(archive_root)
    except ValueError as error:
        raise ValueError(
            f"Archive object escapes archive root: {object_path}"
        ) from error

    return resolved


def resolve_snapshot(
    archive_root: Path,
    requested: str,
) -> Path:
    if requested == "current":
        current = read_json_object(archive_root / "current.json")

        if current.get("archive_format") != ARCHIVE_FORMAT:
            raise ValueError("Invalid replay archive current.json")

        snapshot_rel = str(current.get("snapshot", "")).strip()
        if not snapshot_rel:
            raise ValueError("Replay archive current.json has no snapshot")

        snapshot_path = resolve_archive_object(
            archive_root,
            snapshot_rel,
        )
        return snapshot_path

    if not re.fullmatch(r"[0-9a-fA-F]{64}", requested):
        raise ValueError(
            "--snapshot must be 'current' or a 64-character snapshot ID"
        )

    return archive_root / "snapshots" / f"{requested.lower()}.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Restore an archived WINGS replay snapshot into an isolated "
            "workspace without modifying current project inputs."
        )
    )
    parser.add_argument(
        "--archive-root",
        required=True,
        type=Path,
        help="WINGS replay archive directory",
    )
    parser.add_argument(
        "--snapshot",
        default="current",
        help="'current' or a replay snapshot SHA-256 ID",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="New or empty directory for restored replay inputs",
    )
    args = parser.parse_args()

    archive_root = args.archive_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    try:
        snapshot_path = resolve_snapshot(
            archive_root,
            args.snapshot,
        )
        snapshot = read_json_object(snapshot_path)

        if snapshot.get("archive_format") != ARCHIVE_FORMAT:
            raise ValueError(
                f"Invalid replay snapshot format: {snapshot_path}"
            )

        snapshot_id = str(snapshot.get("snapshot_id", "")).strip()
        if not re.fullmatch(r"[0-9a-f]{64}", snapshot_id):
            raise ValueError(
                f"Invalid replay snapshot ID: {snapshot_id!r}"
            )

        inputs = snapshot.get("inputs")
        if not isinstance(inputs, dict) or not inputs:
            raise ValueError(
                "Replay snapshot does not contain archived inputs."
            )

        if output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError(
                f"Replay output directory is not empty: {output_dir}"
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        restored: dict[str, dict[str, object]] = {}

        for label in sorted(inputs):
            record = inputs[label]

            if not isinstance(record, dict):
                raise ValueError(
                    f"Invalid archived input record: {label}"
                )

            expected_sha256 = str(
                record.get("sha256", "")
            ).strip().lower()

            object_rel = str(
                record.get("object_path", "")
            ).strip()

            original_path = str(
                record.get("original_path", "")
            ).strip()

            if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
                raise ValueError(
                    f"Invalid SHA-256 for archived input {label!r}"
                )

            if not object_rel:
                raise ValueError(
                    f"Archived input {label!r} has no object path"
                )

            source = resolve_archive_object(
                archive_root,
                object_rel,
            )

            if not source.is_file():
                raise FileNotFoundError(
                    f"Archived object missing for {label}: {source}"
                )

            observed = sha256_file(source)
            if observed != expected_sha256:
                raise ValueError(
                    f"Archived object failed SHA-256 verification for "
                    f"{label}: expected {expected_sha256}, "
                    f"observed {observed}"
                )

            name = Path(original_path).name or safe_label(label)
            destination = (
                output_dir
                / "inputs"
                / safe_label(label)
                / name
            )

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            shutil.copyfile(source, destination)

            restored_sha256 = sha256_file(destination)
            if restored_sha256 != expected_sha256:
                raise ValueError(
                    f"Restored file failed SHA-256 verification: "
                    f"{destination}"
                )

            restored[label] = {
                "original_path": original_path,
                "restored_path": destination.relative_to(
                    output_dir
                ).as_posix(),
                "sha256": expected_sha256,
                "size_bytes": destination.stat().st_size,
            }

        workspace = {
            "format": WORKSPACE_FORMAT,
            "schema_version": 1,
            "created_at_utc": datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "snapshot_id": snapshot_id,
            "snapshot_manifest": os.path.relpath(
                snapshot_path,
                archive_root,
            ),
            "inputs": restored,
        }

        workspace_path = output_dir / "replay_workspace.json"
        atomic_write_json(
            workspace_path,
            workspace,
        )

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Replay snapshot restored: {snapshot_id}")
    print(f"Inputs restored: {len(restored)}")
    print(f"Workspace: {output_dir}")
    print(f"Manifest: {workspace_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
