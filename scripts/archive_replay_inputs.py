#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


ARCHIVE_FORMAT = "WINGS_REPLAY_ARCHIVE"
ARCHIVE_SCHEMA_VERSION = 1


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


def archive_object(
    source: Path,
    destination: Path,
    expected_sha256: str,
) -> bool:
    """Store source by content hash. Return True only when newly archived."""

    if destination.is_file():
        observed = sha256_file(destination)
        if observed != expected_sha256:
            raise ValueError(
                "Existing archive object has unexpected SHA-256: "
                f"{destination}"
            )
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(
        f".{destination.name}.tmp-{os.getpid()}"
    )

    try:
        shutil.copyfile(source, temp)

        observed = sha256_file(temp)
        if observed != expected_sha256:
            raise ValueError(
                f"SHA-256 changed while archiving {source}: "
                f"expected {expected_sha256}, observed {observed}"
            )

        temp.replace(destination)
    finally:
        if temp.exists():
            temp.unlink()

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Archive replay-sensitive WINGS inputs in a "
            "content-addressed SHA-256 store."
        )
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="WINGS run_provenance.json",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve relative input paths",
    )
    parser.add_argument(
        "--archive-root",
        required=True,
        type=Path,
        help="Replay archive directory",
    )
    parser.add_argument(
        "--output-index",
        type=Path,
        help="Current snapshot index; defaults to ARCHIVE_ROOT/current.json",
    )
    args = parser.parse_args()

    manifest = args.manifest.resolve()
    repo_root = args.repo_root.resolve()
    archive_root = args.archive_root.expanduser().resolve()
    output_index = (
        args.output_index.expanduser().resolve()
        if args.output_index
        else archive_root / "current.json"
    )

    try:
        provenance = read_json_object(manifest)

        if int(provenance.get("schema_version", 0)) < 2:
            raise ValueError(
                "Replay archiving requires provenance schema_version 2 or newer."
            )

        replay_inputs = provenance.get("replay_inputs")
        if not isinstance(replay_inputs, dict) or not replay_inputs:
            raise ValueError(
                "Provenance does not contain replay inputs to archive."
            )

        provenance_sha256 = sha256_file(manifest)
        snapshot_id = provenance_sha256

        archived_inputs: dict[str, dict[str, object]] = {}
        newly_archived = 0
        reused = 0

        for label in sorted(replay_inputs):
            record = replay_inputs[label]

            if not isinstance(record, dict):
                raise ValueError(
                    f"Invalid replay input record for {label!r}."
                )

            recorded_path = str(record.get("path", "")).strip()
            expected_sha256 = str(record.get("sha256", "")).strip().lower()

            if not recorded_path:
                raise ValueError(
                    f"Replay input {label!r} does not contain a path."
                )

            if expected_sha256 == "missing":
                raise ValueError(
                    f"Replay input {label!r} was recorded as missing."
                )

            if (
                len(expected_sha256) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha256)
            ):
                raise ValueError(
                    f"Replay input {label!r} has invalid SHA-256: "
                    f"{expected_sha256!r}"
                )

            source = Path(recorded_path).expanduser()
            if not source.is_absolute():
                source = repo_root / source
            source = source.resolve()

            if not source.is_file():
                raise FileNotFoundError(
                    f"Replay input is unavailable: {label}: {source}"
                )

            observed_sha256 = sha256_file(source)
            if observed_sha256 != expected_sha256:
                raise ValueError(
                    f"Replay input changed before archival: {label}: "
                    f"expected {expected_sha256}, "
                    f"observed {observed_sha256}"
                )

            object_rel = (
                Path("objects")
                / "sha256"
                / expected_sha256[:2]
                / expected_sha256
            )
            object_path = archive_root / object_rel

            if archive_object(
                source,
                object_path,
                expected_sha256,
            ):
                newly_archived += 1
            else:
                reused += 1

            archived_inputs[label] = {
                "original_path": recorded_path,
                "sha256": expected_sha256,
                "size_bytes": source.stat().st_size,
                "object_path": object_rel.as_posix(),
            }

        snapshot_rel = Path("snapshots") / f"{snapshot_id}.json"
        snapshot_path = archive_root / snapshot_rel

        snapshot = {
            "archive_format": ARCHIVE_FORMAT,
            "schema_version": ARCHIVE_SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "snapshot_id": snapshot_id,
            "provenance": {
                "source_path": os.path.relpath(manifest, repo_root),
                "sha256": provenance_sha256,
                "schema_version": provenance.get("schema_version"),
            },
            "inputs": archived_inputs,
        }

        if snapshot_path.is_file():
            existing = read_json_object(snapshot_path)

            if (
                existing.get("snapshot_id") != snapshot_id
                or existing.get("inputs") != archived_inputs
            ):
                raise ValueError(
                    "Existing snapshot manifest does not match the "
                    f"current replay snapshot: {snapshot_path}"
                )
        else:
            atomic_write_json(snapshot_path, snapshot)

        current = {
            "archive_format": ARCHIVE_FORMAT,
            "schema_version": ARCHIVE_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "snapshot": snapshot_rel.as_posix(),
            "provenance_sha256": provenance_sha256,
        }
        atomic_write_json(output_index, current)

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Replay snapshot: {snapshot_id}")
    print(f"Inputs archived: {len(archived_inputs)}")
    print(f"New objects: {newly_archived}")
    print(f"Existing objects reused: {reused}")
    print(f"Snapshot manifest: {snapshot_path}")
    print(f"Current index: {output_index}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
