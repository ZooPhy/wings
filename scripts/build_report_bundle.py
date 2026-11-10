#!/usr/bin/env python3
"""Build a portable WINGS report bundle from rendered HTML reports.

The resulting .wings file is JSON and contains the rendered run-summary,
sample-summary HTML files, run-level provenance, and a small manifest. It is
designed to be read locally in a web browser without uploading report contents
to a server.

Sample reports rendered from the same Quarto template share a large
byte-identical prefix and suffix. Schema version 2 stores that shared material
once instead of once per sample, which cuts the bundle roughly in half on a
30-sample run. This is a storage change only: every report, provenance field,
and run-summary byte is preserved, and a reader reconstructs each report
character for character. See scripts/wings_bundle_format.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from wings_bundle_format import pack_bundle, verify_roundtrip

FORMAT_NAME = "WINGS_REPORT_BUNDLE"
FORMAT_VERSION = 1
SAMPLE_SUFFIX = ".sample_summary.html"


def read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Report file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Report file is empty: {path}")
    return text


def sample_id_from_path(path: Path) -> str:
    name = path.name
    if not name.endswith(SAMPLE_SUFFIX):
        raise ValueError(
            f"Sample report filename must end with '{SAMPLE_SUFFIX}': {path}"
        )
    sample_id = name[: -len(SAMPLE_SUFFIX)]
    if not sample_id:
        raise ValueError(f"Could not determine sample ID from: {path}")
    return sample_id


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in: {path}")
    return data


def build_bundle(run_summary: Path, provenance: Path, sample_reports: list[Path]) -> dict:
    samples = {}
    for report_path in sample_reports:
        sample_id = sample_id_from_path(report_path)
        if sample_id in samples:
            raise ValueError(f"Duplicate sample report for sample '{sample_id}'")
        samples[sample_id] = {
            "filename": report_path.name,
            "html": read_text(report_path),
        }

    if not samples:
        raise ValueError("At least one sample report is required")

    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(samples),
        "run_summary": {
            "filename": run_summary.name,
            "html": read_text(run_summary),
        },
        "provenance": {
            "filename": provenance.name,
            "data": read_json(provenance),
        },
        "samples": samples,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a portable WINGS report bundle from rendered HTML reports."
    )
    parser.add_argument(
        "--run-summary",
        required=True,
        type=Path,
        help="Rendered WINGS run_summary.html file",
    )
    parser.add_argument(
        "--provenance",
        required=True,
        type=Path,
        help="WINGS run-level provenance JSON file",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output .wings bundle path",
    )
    parser.add_argument(
        "--no-pack",
        action="store_true",
        help=(
            "Write a schema version 1 bundle with each report stored whole. "
            "Only needed for readers that predate shared-chunk support."
        ),
    )
    parser.add_argument(
        "sample_reports",
        nargs="+",
        type=Path,
        help="Rendered *.sample_summary.html files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bundle = build_bundle(args.run_summary, args.provenance, args.sample_reports)
    sample_count = bundle["sample_count"]

    saved_bytes = 0
    if not args.no_pack:
        # Confirm every report reconstructs exactly before the packed form is
        # allowed anywhere near the output path. A bundle that cannot be
        # unpacked byte-for-byte is not written at all.
        saved_bytes = verify_roundtrip(bundle)["saved_bytes"]
        bundle = pack_bundle(bundle)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = args.output.with_suffix(args.output.suffix + ".tmp")
    with temp_output.open("w", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    temp_output.replace(args.output)

    size_mb = args.output.stat().st_size / (1024 * 1024)
    detail = ""
    if saved_bytes > 0:
        detail = f", {saved_bytes / (1024 * 1024):.2f} MB of shared report HTML stored once"
    print(
        f"WINGS report bundle created: {args.output} "
        f"({sample_count} samples, {size_mb:.2f} MB, "
        f"schema v{bundle['version']}{detail})"
    )


if __name__ == "__main__":
    main()
