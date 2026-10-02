#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


VARIANT_FIELDS = [
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

SUMMARY_FIELDS = [
    "historical_snapshot_id",
    "genomic_overall",
    "primary_genomic",
    "variant_calls",
    "surveillance_context",
    "integrated_concordance",
    "stable_variant_vcfs",
    "changed_variant_vcfs",
    "missing_variant_vcfs",
    "interpretation",
]


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def write_empty_tsv(path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()


def write_no_baseline(
    output_json: Path,
    variant_tsv: Path,
    summary_tsv: Path,
) -> None:
    report = {
        "format": "WINGS_INTERPRETATION_COMPARISON",
        "schema_version": 2,
        "comparison_available": False,
        "historical_snapshot_id": None,
        "layers": {
            "genomic_overall": {"status": "NOT_AVAILABLE"},
            "primary_genomic": {"status": "NOT_AVAILABLE"},
            "variant_calls": {"status": "NOT_AVAILABLE"},
            "surveillance_context": {"status": "NOT_AVAILABLE"},
            "integrated_concordance": {"status": "NOT_AVAILABLE"},
        },
        "interpretation": (
            "No prior archived WINGS interpretation is available "
            "for historical comparison."
        ),
        "artifact_counts": {},
        "variant_counts": {},
        "artifacts": {},
        "variants": [],
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    write_empty_tsv(variant_tsv, VARIANT_FIELDS)
    write_empty_tsv(summary_tsv, SUMMARY_FIELDS)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate WINGS historical stability outputs from an "
            "automatically selected prior interpretation."
        )
    )
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--variant-tsv", required=True, type=Path)
    parser.add_argument("--summary-tsv", required=True, type=Path)
    args = parser.parse_args()

    try:
        selection = read_json(args.selection.resolve())

        if not selection.get("baseline_available", False):
            write_no_baseline(
                args.output_json,
                args.variant_tsv,
                args.summary_tsv,
            )
            print(
                "Historical stability: no prior interpretation available"
            )
            return 0

        relative = str(
            selection.get("baseline_interpretation", "")
        ).strip()

        if not relative:
            raise ValueError(
                "Baseline selection does not contain an interpretation path."
            )

        archive_root = args.archive_root.resolve()
        interpretation = (archive_root / relative).resolve()

        try:
            interpretation.relative_to(archive_root)
        except ValueError as error:
            raise ValueError(
                "Selected historical interpretation escapes archive root."
            ) from error

        if not interpretation.is_file():
            raise FileNotFoundError(
                f"Selected interpretation not found: {interpretation}"
            )

        comparator = Path(__file__).with_name(
            "compare_historical_interpretation.py"
        )

        subprocess.run(
            [
                sys.executable,
                str(comparator),
                "--interpretation",
                str(interpretation),
                "--archive-root",
                str(archive_root),
                "--results-root",
                str(args.results_root),
                "--output-json",
                str(args.output_json),
                "--variant-tsv",
                str(args.variant_tsv),
                "--summary-tsv",
                str(args.summary_tsv),
            ],
            check=True,
        )

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
