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
INTERPRETATION_FORMAT = "WINGS_INTERPRETATION_ARCHIVE"
SCHEMA_VERSION = 1

ARTIFACT_PATTERNS = (
    ("sample_summary", "*/summary/*.sample_summary.tsv"),
    ("blast", "*/summary/blast_top_hits.csv"),
    ("coverage", "*/coverage/coverage.tsv"),
    ("consensus", "*/merged/consensus_all_segments.fasta"),
    ("genoflu", "*/genoflu/GenoFLU.tsv"),
    ("variant_vcf", "*/medaka/*/variants.vcf"),
    ("variant_status", "*/medaka/*/variants.status.tsv"),
    ("surveillance_explorer", "run_summary/surveillance_explorer*.json"),
    ("concordance", "run_summary/concordance/sample_features.tsv"),
    ("concordance", "run_summary/concordance/pairs.tsv"),
    ("concordance", "run_summary/concordance/models.tsv"),
    ("concordance", "run_summary/concordance/concordance.json"),
    (
        "contextual_tree",
        "run_summary/public_references/**/trees/*.newick",
    ),
    (
        "contextual_tree",
        "run_summary/contextual_phylogeny/*.treefile",
    ),
)


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
    if destination.is_file():
        if sha256_file(destination) != expected_sha256:
            raise ValueError(
                f"Archive object failed verification: {destination}"
            )
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(
        f".{destination.name}.tmp-{os.getpid()}"
    )

    try:
        shutil.copyfile(source, temp)
        if sha256_file(temp) != expected_sha256:
            raise ValueError(
                f"File changed during archival: {source}"
            )
        temp.replace(destination)
    finally:
        if temp.exists():
            temp.unlink()

    return True


def discover_artifacts(results_root: Path) -> dict[Path, str]:
    artifacts: dict[Path, str] = {}

    for category, pattern in ARTIFACT_PATTERNS:
        for path in sorted(results_root.glob(pattern)):
            if path.is_file():
                artifacts.setdefault(path.resolve(), category)

    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive WINGS scientific interpretation outputs."
    )
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--archive-root", required=True, type=Path)
    args = parser.parse_args()

    provenance_path = args.provenance.resolve()
    results_root = args.results_root.resolve()
    archive_root = args.archive_root.resolve()

    try:
        if not provenance_path.is_file():
            raise FileNotFoundError(
                f"Provenance not found: {provenance_path}"
            )

        provenance = read_json(provenance_path)
        if int(provenance.get("schema_version", 0)) < 2:
            raise ValueError(
                "Interpretation archival requires provenance schema 2+."
            )

        provenance_sha = sha256_file(provenance_path)
        snapshot_id = provenance_sha

        # An interpretation must be anchored to an archived replay snapshot.
        replay_snapshot = (
            archive_root / "snapshots" / f"{snapshot_id}.json"
        )
        if not replay_snapshot.is_file():
            raise FileNotFoundError(
                "Matching replay snapshot does not exist: "
                f"{replay_snapshot}"
            )

        replay_data = read_json(replay_snapshot)
        if replay_data.get("snapshot_id") != snapshot_id:
            raise ValueError(
                "Replay snapshot ID does not match provenance."
            )

        discovered = discover_artifacts(results_root)
        if not discovered:
            raise ValueError(
                f"No WINGS interpretation outputs found in {results_root}"
            )

        artifacts: dict[str, dict[str, object]] = {}
        new_objects = 0
        reused_objects = 0

        for source, category in sorted(
            discovered.items(),
            key=lambda item: str(item[0]),
        ):
            relative = source.relative_to(results_root).as_posix()
            digest = sha256_file(source)

            object_rel = (
                Path("objects")
                / "sha256"
                / digest[:2]
                / digest
            )
            object_path = archive_root / object_rel

            if archive_object(source, object_path, digest):
                new_objects += 1
            else:
                reused_objects += 1

            artifacts[relative] = {
                "category": category,
                "sha256": digest,
                "size_bytes": source.stat().st_size,
                "object_path": object_rel.as_posix(),
            }

        interpretation = {
            "format": INTERPRETATION_FORMAT,
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "snapshot_id": snapshot_id,
            "provenance_sha256": provenance_sha,
            "replay_snapshot": (
                Path("snapshots") / f"{snapshot_id}.json"
            ).as_posix(),
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        }

        interpretation_dir = archive_root / "interpretations"
        interpretation_path = (
            interpretation_dir / f"{snapshot_id}.json"
        )

        if interpretation_path.is_file():
            existing = read_json(interpretation_path)
            if existing.get("artifacts") != artifacts:
                raise ValueError(
                    "Interpretation snapshot already exists but its "
                    "artifacts differ. Historical snapshots are immutable."
                )
        else:
            atomic_write_json(
                interpretation_path,
                interpretation,
            )

        current = {
            "format": INTERPRETATION_FORMAT,
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "interpretation": (
                Path("interpretations")
                / f"{snapshot_id}.json"
            ).as_posix(),
            "provenance_sha256": provenance_sha,
        }

        atomic_write_json(
            interpretation_dir / "current.json",
            current,
        )

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Interpretation snapshot: {snapshot_id}")
    print(f"Artifacts archived: {len(artifacts)}")
    print(f"New objects: {new_objects}")
    print(f"Existing objects reused: {reused_objects}")
    print(f"Manifest: {interpretation_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
