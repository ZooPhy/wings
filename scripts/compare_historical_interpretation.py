#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from archive_interpretation_outputs import discover_artifacts


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


def read_vcf_variants(path: Path) -> set[tuple[str, int, str, str]]:
    variants: set[tuple[str, int, str, str]] = set()

    if not path.is_file() or path.stat().st_size == 0:
        return variants

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue

            fields = line.rstrip("\n").split("\t")
            if len(fields) < 5:
                continue

            try:
                pos = int(fields[1])
            except ValueError:
                continue

            chrom = fields[0]
            ref = fields[3]

            for alt in fields[4].split(","):
                if alt and alt != ".":
                    variants.add((chrom, pos, ref, alt))

    return variants


def sample_segment_from_vcf(relative_path: str) -> tuple[str, str]:
    parts = Path(relative_path).parts

    # Expected:
    # SAMPLE/medaka/SEGMENT/variants.vcf
    if len(parts) >= 4 and parts[-1] == "variants.vcf":
        return parts[-4], parts[-2]

    return "", ""


def variant_text(variant: tuple[str, int, str, str]) -> str:
    chrom, pos, ref, alt = variant
    return f"{chrom}:{pos}:{ref}>{alt}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare an archived WINGS interpretation with current "
            "analytical outputs."
        )
    )
    parser.add_argument(
        "--interpretation",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--archive-root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--results-root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--output-json",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--variant-tsv",
        required=True,
        type=Path,
    )
    args = parser.parse_args()

    archive_root = args.archive_root.resolve()
    results_root = args.results_root.resolve()

    try:
        historical = read_json(args.interpretation.resolve())

        historical_artifacts = historical.get("artifacts")
        if not isinstance(historical_artifacts, dict):
            raise ValueError(
                "Interpretation manifest has no artifacts mapping."
            )

        current_discovered = {
            path.relative_to(results_root).as_posix(): category
            for path, category in discover_artifacts(results_root).items()
        }

        artifact_results: dict[str, dict[str, object]] = {}
        variant_rows: list[dict[str, object]] = []

        all_paths = sorted(
            set(historical_artifacts) | set(current_discovered)
        )

        for relative in all_paths:
            historical_record = historical_artifacts.get(relative)
            current_path = results_root / relative

            if historical_record is None:
                artifact_results[relative] = {
                    "category": current_discovered[relative],
                    "status": "NEW",
                    "historical_sha256": None,
                    "current_sha256": (
                        sha256_file(current_path)
                        if current_path.is_file()
                        else None
                    ),
                }
                continue

            category = str(historical_record.get("category", ""))
            historical_sha = str(
                historical_record.get("sha256", "")
            )
            object_rel = str(
                historical_record.get("object_path", "")
            )

            historical_object = archive_root / object_rel

            if not historical_object.is_file():
                raise FileNotFoundError(
                    f"Historical archive object missing: "
                    f"{historical_object}"
                )

            if sha256_file(historical_object) != historical_sha:
                raise ValueError(
                    f"Historical archive object failed verification: "
                    f"{relative}"
                )

            if not current_path.is_file():
                artifact_status = "MISSING"
                current_sha = None
            else:
                current_sha = sha256_file(current_path)
                artifact_status = (
                    "MATCH"
                    if current_sha == historical_sha
                    else "CHANGED"
                )

            artifact_results[relative] = {
                "category": category,
                "status": artifact_status,
                "historical_sha256": historical_sha,
                "current_sha256": current_sha,
            }

            if category != "variant_vcf":
                continue

            sample, segment = sample_segment_from_vcf(relative)

            historical_variants = read_vcf_variants(
                historical_object
            )
            current_variants = (
                read_vcf_variants(current_path)
                if current_path.is_file()
                else set()
            )

            added = sorted(
                current_variants - historical_variants
            )
            removed = sorted(
                historical_variants - current_variants
            )

            if not current_path.is_file():
                variant_status = "MISSING_CURRENT"
            elif not added and not removed:
                variant_status = "STABLE"
            else:
                variant_status = "CHANGED"

            variant_rows.append(
                {
                    "sample": sample,
                    "segment": segment,
                    "status": variant_status,
                    "historical_variant_count": len(
                        historical_variants
                    ),
                    "current_variant_count": len(
                        current_variants
                    ),
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "added_variants": ";".join(
                        variant_text(v) for v in added
                    ),
                    "removed_variants": ";".join(
                        variant_text(v) for v in removed
                    ),
                    "artifact_path": relative,
                }
            )

        counts = Counter(
            record["status"]
            for record in artifact_results.values()
        )

        variant_counts = Counter(
            row["status"]
            for row in variant_rows
        )

        report = {
            "format": "WINGS_INTERPRETATION_COMPARISON",
            "schema_version": 1,
            "historical_snapshot_id": historical.get(
                "snapshot_id"
            ),
            "artifact_counts": dict(sorted(counts.items())),
            "variant_counts": dict(
                sorted(variant_counts.items())
            ),
            "artifacts": artifact_results,
            "variants": variant_rows,
        }

        args.output_json.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        with args.output_json.open(
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                report,
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")

        args.variant_tsv.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fieldnames = [
            "sample",
            "segment",
            "status",
            "historical_variant_count",
            "current_variant_count",
            "added_count",
            "removed_count",
            "added_variants",
            "removed_variants",
            "artifact_path",
        ]

        with args.variant_tsv.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fieldnames,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(variant_rows)

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "Artifact comparison: "
        + ", ".join(
            f"{status}={count}"
            for status, count in sorted(counts.items())
        )
    )
    print(
        "Variant comparison: "
        + ", ".join(
            f"{status}={count}"
            for status, count in sorted(
                variant_counts.items()
            )
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
