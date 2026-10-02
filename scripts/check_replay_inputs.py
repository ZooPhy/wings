#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_replay_inputs(manifest: Path, repo_root: Path) -> list[dict[str, str]]:
    data = json.loads(manifest.read_text(encoding="utf-8"))

    if int(data.get("schema_version", 0)) < 2:
        raise ValueError(
            "Replay checking requires provenance schema_version 2 or newer."
        )

    replay_inputs = data.get("replay_inputs")
    if not isinstance(replay_inputs, dict):
        raise ValueError("Manifest does not contain a replay_inputs mapping.")

    results: list[dict[str, str]] = []

    for label in sorted(replay_inputs):
        record = replay_inputs[label]

        if not isinstance(record, dict):
            raise ValueError(f"Invalid replay input record: {label}")

        recorded_path = str(record.get("path", "")).strip()
        expected_sha256 = str(record.get("sha256", "")).strip()

        if not recorded_path:
            raise ValueError(f"Replay input {label!r} has no path.")

        path = Path(recorded_path).expanduser()
        if not path.is_absolute():
            path = repo_root / path
        path = path.resolve()

        if not path.is_file():
            status = "MISSING"
            observed_sha256 = ""
        else:
            observed_sha256 = sha256_file(path)
            status = (
                "MATCH"
                if observed_sha256 == expected_sha256
                else "CHANGED"
            )

        results.append(
            {
                "label": label,
                "status": status,
                "path": recorded_path,
                "expected_sha256": expected_sha256,
                "observed_sha256": observed_sha256,
            }
        )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether replay-sensitive WINGS inputs still match "
            "a historical run_provenance.json."
        )
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="Historical WINGS run_provenance.json",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="WINGS repository root used to resolve relative paths",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional machine-readable replay-check report",
    )
    args = parser.parse_args()

    try:
        results = check_replay_inputs(
            args.manifest.resolve(),
            args.repo_root.resolve(),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    counts = {
        "MATCH": sum(row["status"] == "MATCH" for row in results),
        "CHANGED": sum(row["status"] == "CHANGED" for row in results),
        "MISSING": sum(row["status"] == "MISSING" for row in results),
    }

    for row in results:
        print(
            f"{row['status']:7}  "
            f"{row['label']:<28}  "
            f"{row['path']}"
        )

    print()
    print(
        "Replay readiness: "
        f"{counts['MATCH']} matched, "
        f"{counts['CHANGED']} changed, "
        f"{counts['MISSING']} missing"
    )

    if args.output_json:
        report = {
            "manifest": str(args.manifest),
            "counts": counts,
            "inputs": results,
            "replay_ready": (
                counts["CHANGED"] == 0
                and counts["MISSING"] == 0
            ),
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return 0 if counts["CHANGED"] == 0 and counts["MISSING"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
