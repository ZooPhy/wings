#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


ARCHIVE_FORMAT = "WINGS_INTERPRETATION_ARCHIVE"
SELECTION_FORMAT = "WINGS_HISTORICAL_BASELINE_SELECTION"


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


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Select the most recent prior WINGS interpretation, excluding "
            "the interpretation belonging to the current provenance."
        )
    )
    parser.add_argument(
        "--provenance",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--archive-root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )
    args = parser.parse_args()

    provenance = args.provenance.resolve()
    archive_root = args.archive_root.resolve()

    try:
        if not provenance.is_file():
            raise FileNotFoundError(
                f"Current provenance not found: {provenance}"
            )

        current_snapshot_id = sha256_file(provenance)
        interpretations_dir = archive_root / "interpretations"

        candidates: list[tuple[str, str, Path, dict]] = []

        if interpretations_dir.is_dir():
            for path in interpretations_dir.glob("*.json"):
                if path.name == "current.json":
                    continue

                # Interpretation manifests are named by their 64-character
                # provenance SHA-256. Ignore unrelated JSON files.
                if len(path.stem) != 64:
                    continue

                try:
                    data = read_json(path)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue

                if data.get("format") != ARCHIVE_FORMAT:
                    continue

                snapshot_id = str(
                    data.get("snapshot_id", "")
                ).strip()

                # Never select the current run as its own historical baseline.
                if snapshot_id == current_snapshot_id:
                    continue

                created = str(
                    data.get("created_at_utc", "")
                ).strip()

                candidates.append(
                    (created, path.name, path, data)
                )

        if candidates:
            # ISO-8601 UTC timestamps sort chronologically as strings.
            candidates.sort(
                key=lambda item: (item[0], item[1])
            )
            _, _, baseline_path, baseline = candidates[-1]

            selection = {
                "format": SELECTION_FORMAT,
                "schema_version": 1,
                "current_snapshot_id": current_snapshot_id,
                "baseline_available": True,
                "baseline_snapshot_id": baseline.get(
                    "snapshot_id"
                ),
                "baseline_created_at_utc": baseline.get(
                    "created_at_utc"
                ),
                "baseline_interpretation": os.path.relpath(
                    baseline_path,
                    archive_root,
                ),
                "selection_method": (
                    "most_recent_prior_interpretation"
                ),
            }
        else:
            selection = {
                "format": SELECTION_FORMAT,
                "schema_version": 1,
                "current_snapshot_id": current_snapshot_id,
                "baseline_available": False,
                "baseline_snapshot_id": None,
                "baseline_created_at_utc": None,
                "baseline_interpretation": None,
                "selection_method": (
                    "most_recent_prior_interpretation"
                ),
            }

        write_json(args.output, selection)

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if selection["baseline_available"]:
        print(
            "Historical baseline: "
            f"{selection['baseline_snapshot_id']}"
        )
    else:
        print("Historical baseline: none available")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
