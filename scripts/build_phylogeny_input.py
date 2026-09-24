#!/usr/bin/env python3

"""Build a QC-qualified segment FASTA for optional WINGS phylogeny inference."""

from __future__ import annotations

import csv
from pathlib import Path


def read_fasta(path: Path) -> dict[str, str]:
    """Read FASTA records keyed by the first token of each header."""
    records: dict[str, str] = {}

    if not path.is_file() or path.stat().st_size == 0:
        return records

    header: str | None = None
    parts: list[str] = []

    def store() -> None:
        nonlocal header, parts
        if header is None:
            return
        sequence = "".join(parts).upper()
        if sequence:
            records[header] = sequence

    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith(">"):
                store()
                header = line[1:].split()[0]
                parts = []
            else:
                if header is None:
                    raise ValueError(
                        f"sequence encountered before FASTA header in {path}"
                    )
                parts.append("".join(line.split()))

    store()
    return records


def coverage_row(path: Path, segment: str) -> dict[str, str] | None:
    """Return the coverage-table row for one segment."""
    if not path.is_file() or path.stat().st_size == 0:
        return None

    with path.open(encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("segment") == segment:
                return row

    return None


def taxon_suffix(contig: str, segment: str) -> str:
    """Convert IRMA contig labels to compact Explorer-compatible labels."""
    value = contig.strip()

    if value.startswith("A_"):
        value = value[2:]

    return value or segment


def main() -> None:
    segment = str(snakemake.wildcards.segment)

    samples = [
        value
        for value in str(snakemake.params.samples).split(",")
        if value
    ]

    merged_paths = [Path(str(path)) for path in snakemake.input.merged]
    coverage_paths = [Path(str(path)) for path in snakemake.input.coverage]

    if not (
        len(samples)
        == len(merged_paths)
        == len(coverage_paths)
    ):
        raise ValueError(
            "sample/input counts do not match: "
            f"samples={len(samples)}, "
            f"merged={len(merged_paths)}, "
            f"coverage={len(coverage_paths)}"
        )

    min_sequences = int(snakemake.params.min_sequences)

    fasta_out = Path(str(snakemake.output.fasta))
    status_out = Path(str(snakemake.output.status))
    fasta_out.parent.mkdir(parents=True, exist_ok=True)

    retained: list[tuple[str, str]] = []

    excluded_nonpass = 0
    excluded_missing_coverage = 0
    excluded_missing_contig = 0
    excluded_missing_consensus = 0

    for sample, merged_path, coverage_path in zip(
        samples,
        merged_paths,
        coverage_paths,
    ):
        row = coverage_row(coverage_path, segment)

        if row is None:
            excluded_missing_coverage += 1
            continue

        if row.get("overall_status", "").strip().upper() != "PASS":
            excluded_nonpass += 1
            continue

        contig = row.get("contig", "").strip()
        if not contig or contig == "NA":
            excluded_missing_contig += 1
            continue

        records = read_fasta(merged_path)
        sequence = records.get(contig)

        if not sequence:
            excluded_missing_consensus += 1
            continue

        suffix = taxon_suffix(contig, segment)
        taxon = f"{sample}__{suffix}"

        retained.append((taxon, sequence))

    with fasta_out.open("w", encoding="utf-8") as handle:
        for taxon, sequence in retained:
            handle.write(f">{taxon}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start:start + 80] + "\n")

    sequence_count = len(retained)

    status = (
        "READY"
        if sequence_count >= min_sequences
        else "INSUFFICIENT_SEQUENCES"
    )

    fieldnames = [
        "segment",
        "status",
        "sequence_count",
        "min_sequences",
        "excluded_nonpass",
        "excluded_missing_coverage",
        "excluded_missing_contig",
        "excluded_missing_consensus",
    ]

    with status_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "segment": segment,
                "status": status,
                "sequence_count": sequence_count,
                "min_sequences": min_sequences,
                "excluded_nonpass": excluded_nonpass,
                "excluded_missing_coverage": excluded_missing_coverage,
                "excluded_missing_contig": excluded_missing_contig,
                "excluded_missing_consensus": excluded_missing_consensus,
            }
        )


if __name__ == "__main__":
    main()
