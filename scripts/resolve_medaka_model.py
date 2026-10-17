#!/usr/bin/env python3

"""
Resolve Medaka model selectors from Oxford Nanopore FASTQ metadata.

The script reads FASTQ record headers and extracts:

    basecall_model_version_id=<model>

For example:

    basecall_model_version_id=dna_r10.4.1_e8.2_400bps_hac@v5.0.0

It writes a TSV containing the detected basecaller model and Medaka-compatible
model selectors:

    dna_r10.4.1_e8.2_400bps_hac@v5.0.0:consensus
    dna_r10.4.1_e8.2_400bps_hac@v5.0.0:variant

Medaka performs the actual mapping from the basecaller model to the
corresponding Medaka model. This avoids maintaining a duplicate model mapping
inside WINGS.

Exit codes
----------
0
    A single basecaller model was resolved and the TSV was written.
3
    The FASTQ was read successfully but carries no basecall_model_version_id.
    This is the expected outcome for reads retrieved from public archives,
    because SRA normalisation discards ONT header comment fields. Callers may
    treat this as an unresolved model rather than a workflow failure.
1
    A genuine failure: unreadable or truncated FASTQ, malformed headers, or
    multiple basecaller models in one file. Callers must not treat this as a
    benign metadata omission.
2
    Invalid command-line usage.
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
from collections import Counter
from pathlib import Path


class NoModelMetadata(RuntimeError):
    """The FASTQ was read successfully but carries no basecall model field.

    Kept distinct from RuntimeError so that an ordinary metadata omission is
    never reported with the same exit code as a software or input failure.
    """


MODEL_PATTERN = re.compile(
    r"(?:^|\s)basecall_model_version_id=([^\s]+)"
)


def open_text(path: Path):
    """Open plain-text or gzip-compressed FASTQ."""
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("rt", encoding="utf-8", errors="replace")


def detect_basecaller_model(
    fastq: Path,
    max_records: int = 100,
) -> tuple[str, int]:
    """
    Extract the basecaller model from FASTQ headers.

    Returns
    -------
    tuple[str, int]
        The unique basecaller model and number of records containing it.

    Raises
    ------
    NoModelMetadata
        If the file was read successfully but no model field is present.
    RuntimeError
        If the FASTQ is truncated or malformed, or if multiple basecaller
        models are detected.
    """
    models: list[str] = []

    with open_text(fastq) as handle:
        record_number = 0

        while record_number < max_records:
            header = handle.readline()

            if not header:
                break

            sequence = handle.readline()
            plus = handle.readline()
            quality = handle.readline()

            if not sequence or not plus or not quality:
                raise RuntimeError(
                    f"FASTQ appears truncated near record "
                    f"{record_number + 1}: {fastq}"
                )

            record_number += 1

            if not header.startswith("@"):
                raise RuntimeError(
                    f"Invalid FASTQ header at record {record_number}: "
                    f"{header.rstrip()!r}"
                )

            if not plus.startswith("+"):
                raise RuntimeError(f"Invalid FASTQ separator at record {record_number}")
            sequence_text = sequence.rstrip("\r\n")
            quality_text = quality.rstrip("\r\n")

            if not sequence_text:
                raise RuntimeError(
                    f"Empty sequence at record {record_number}")

            if len(sequence_text) != len(quality_text):
                raise RuntimeError(
                    f"Sequence/quality length mismatch at record {record_number}")
            match = MODEL_PATTERN.search(header)
            if match:
                models.append(match.group(1))

    if record_number == 0:
        raise RuntimeError(f"FASTQ contains no records: {fastq}")

    if not models:
        raise NoModelMetadata(
            "No basecall_model_version_id metadata was found in the first "
            f"{max_records} FASTQ records of {fastq}"
        )

    counts = Counter(models)

    if len(counts) != 1:
        details = ", ".join(
            f"{model} ({count} reads)"
            for model, count in sorted(counts.items())
        )
        raise RuntimeError(
            "Multiple basecaller models were detected in the FASTQ: "
            f"{details}. WINGS will not choose a Medaka model automatically "
            "for mixed-basecaller input."
        )

    model, count = next(iter(counts.items()))
    return model, count


def write_tsv(
    output: Path,
    fastq: Path,
    basecaller_model: str,
    records_with_model: int,
) -> None:
    """Write resolved model metadata in a Snakemake-friendly TSV."""
    output.parent.mkdir(parents=True, exist_ok=True)

    consensus_selector = f"{basecaller_model}:consensus"
    variant_selector = f"{basecaller_model}:variant"

    with output.open("w", encoding="utf-8") as handle:
        handle.write(
            "\t".join(
                [
                    "fastq",
                    "basecaller_model",
                    "medaka_consensus_selector",
                    "medaka_variant_selector",
                    "records_with_model",
                ]
            )
            + "\n"
        )

        handle.write(
            "\t".join(
                [
                    str(fastq),
                    basecaller_model,
                    consensus_selector,
                    variant_selector,
                    str(records_with_model),
                ]
            )
            + "\n"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Oxford Nanopore basecaller metadata from FASTQ and "
            "generate Medaka model selectors."
        )
    )

    parser.add_argument(
        "--fastq",
        required=True,
        type=Path,
        help="Input FASTQ or FASTQ.GZ file.",
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output TSV file.",
    )

    parser.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Maximum FASTQ records to inspect (default: 100).",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.max_records < 1:
        print(
            "ERROR: --max-records must be at least 1.",
            file=sys.stderr,
        )
        return 2

    if not args.fastq.is_file():
        print(
            f"ERROR: FASTQ does not exist: {args.fastq}",
            file=sys.stderr,
        )
        return 2

    try:
        basecaller_model, records_with_model = detect_basecaller_model(
            args.fastq,
            args.max_records,
        )

        write_tsv(
            args.output,
            args.fastq,
            basecaller_model,
            records_with_model,
        )

    except NoModelMetadata as exc:
        # Expected for archived reads. Reported separately so a caller can
        # distinguish "the archive did not keep it" from "something broke".
        print(f"NO_MODEL_METADATA: {exc}", file=sys.stderr)
        return 3

    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"Detected basecaller model: {basecaller_model}",
        file=sys.stderr,
    )
    print(
        f"Medaka consensus selector: "
        f"{basecaller_model}:consensus",
        file=sys.stderr,
    )
    print(
        f"Medaka variant selector: "
        f"{basecaller_model}:variant",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
