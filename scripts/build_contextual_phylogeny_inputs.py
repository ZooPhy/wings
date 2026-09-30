#!/usr/bin/env python3
"""Build WINGS + public-reference FASTA inputs for contextual influenza phylogenies.

This script combines QC-passing WINGS consensus sequences with the selected public
reference FASTAs produced by ``select_contextual_references.py``. It preserves the
existing WINGS tree-tip convention for study samples and uses the GenBank accession
as the public-reference tree tip.

Outputs are deterministic for identical inputs:
  <output-dir>/<SEGMENT>.contextual.input.fasta
  <output-dir>/contextual_tip_manifest.tsv
  <output-dir>/segment_status.tsv
  <output-dir>/build_summary.json

The script does not align sequences or infer trees. Those files are intended for the
existing WINGS MAFFT + IQ-TREE 2 phylogeny rules.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

SEGMENTS = ("PB2", "PB1", "PA", "HA", "NP", "NA", "MP", "NS")
MISSING = {"", "NA", "N/A", "NONE", "NULL", "NAN", "UNKNOWN"}
IUPAC = frozenset("ACGTRYSWKMBDHVN.-U")


def clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() in MISSING else text


def read_tsv(path: Path) -> List[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def iter_fasta(path: Path) -> Iterator[Tuple[str, str]]:
    header: Optional[str] = None
    parts: List[str] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(parts).upper()
                header = line[1:].strip()
                parts = []
            else:
                if header is None:
                    raise ValueError(f"Sequence encountered before FASTA header in {path}")
                parts.append("".join(line.split()))
    if header is not None:
        yield header, "".join(parts).upper()


def read_fasta_by_token(path: Path) -> Dict[str, str]:
    records: Dict[str, str] = {}
    if not path.is_file() or path.stat().st_size == 0:
        return records
    for header, sequence in iter_fasta(path):
        token = header.split()[0]
        if token in records:
            raise ValueError(f"Duplicate FASTA identifier {token!r} in {path}")
        validate_sequence(sequence, path, token)
        records[token] = sequence
    return records


def validate_sequence(sequence: str, path: Path, identifier: str) -> None:
    if not sequence:
        raise ValueError(f"Empty FASTA sequence for {identifier!r} in {path}")
    bad = sorted(set(sequence) - IUPAC)
    if bad:
        raise ValueError(
            f"Unsupported sequence characters for {identifier!r} in {path}: {''.join(bad)}"
        )


def write_fasta(path: Path, rows: Iterable[Tuple[str, str]]) -> int:
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for tip, sequence in rows:
            handle.write(f">{tip}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start:start + 80] + "\n")
            count += 1
    return count


def coverage_row(path: Path, segment: str) -> Optional[dict]:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            # Segment labels are biological identifiers. In particular, "NA"
            # means neuraminidase here and must not be treated as a generic
            # missing-value token.
            row_segment = str(row.get("segment") or "").strip().upper()
            if row_segment == segment:
                return dict(row)
    return None


def taxon_suffix(contig: str, segment: str) -> str:
    value = clean(contig)
    if value.startswith("A_"):
        value = value[2:]
    return value or segment


def load_metadata(path: Optional[Path]) -> Dict[str, dict]:
    if path is None:
        return {}
    rows = read_tsv(path)
    if not rows:
        return {}
    fields = set(rows[0])
    key = "sample_id" if "sample_id" in fields else "sample" if "sample" in fields else None
    if key is None:
        raise ValueError("Metadata must contain sample_id or sample")
    result: Dict[str, dict] = {}
    for row in rows:
        sample = clean(row.get(key))
        if not sample:
            continue
        if sample in result:
            raise ValueError(f"Duplicate metadata sample identifier: {sample}")
        result[sample] = row
    return result


def discover_samples(results_dir: Path, metadata: Dict[str, dict]) -> List[str]:
    if metadata:
        return sorted(metadata)
    samples: List[str] = []
    for path in results_dir.iterdir() if results_dir.is_dir() else []:
        if not path.is_dir() or path.name == "run_summary":
            continue
        if (path / "merged" / "consensus_all_segments.fasta").is_file():
            samples.append(path.name)
    return sorted(samples)


def load_selected_rows(path: Path) -> Dict[Tuple[str, str], dict]:
    rows = read_tsv(path)
    result: Dict[Tuple[str, str], dict] = {}
    for line, row in enumerate(rows, start=2):
        # Do not use generic clean() here: "NA" is a valid influenza segment,
        # not a missing-value token.
        segment = str(row.get("segment") or "").strip().upper()
        accession = clean(row.get("accession") or row.get("tip_label"))
        if segment not in SEGMENTS or not accession:
            raise ValueError(f"Invalid selected-reference row {line}: segment={segment!r}, accession={accession!r}")
        key = (segment, accession)
        if key in result:
            raise ValueError(f"Duplicate selected reference: {segment}/{accession}")
        result[key] = row
    return result


def get_first(row: dict, *names: str) -> str:
    for name in names:
        value = clean(row.get(name))
        if value:
            return value
    return ""


def wings_manifest_row(
    segment: str,
    tip: str,
    sample: str,
    contig: str,
    sequence: str,
    coverage: dict,
    metadata: dict,
) -> dict:
    return {
        "segment": segment,
        "tip_label": tip,
        "tip_kind": "wings_sample",
        "sample_id": sample,
        "accession": "",
        "reference_id": "",
        "isolate": "",
        "host": get_first(metadata, "host", "host_common_name", "host_species"),
        "collection_date": clean(metadata.get("collection_date")),
        "country": clean(metadata.get("country")),
        "state": clean(metadata.get("state")),
        "genotype": "",
        "segment_type": "",
        "selection_reason": "study_sample",
        "overall_status": clean(coverage.get("overall_status")).upper(),
        "contig": contig,
        "sequence_length": str(len(sequence)),
    }


def public_manifest_row(segment: str, accession: str, sequence: str, source: dict) -> dict:
    type_field = f"{segment}_type"
    return {
        "segment": segment,
        "tip_label": accession,
        "tip_kind": "public_reference",
        "sample_id": "",
        "accession": accession,
        "reference_id": get_first(source, "reference_id"),
        "isolate": get_first(source, "isolate"),
        "host": get_first(source, "host"),
        "collection_date": get_first(source, "collection_date"),
        "country": get_first(source, "country"),
        "state": get_first(source, "state"),
        "genotype": get_first(source, "genotype"),
        "segment_type": get_first(source, "segment_type", type_field),
        "selection_reason": get_first(source, "selection_reason"),
        "overall_status": "PUBLIC_REFERENCE",
        "contig": "",
        "sequence_length": str(len(sequence)),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Combine QC-passing WINGS segment consensuses with selected public references for contextual phylogenies."
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--selected-dir",
        type=Path,
        default=Path("results/run_summary/public_references/selected"),
        help="Directory containing selected_<SEGMENT>.fasta and selected_references.tsv",
    )
    parser.add_argument("--metadata", type=Path, default=Path("metadata.tsv"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/run_summary/contextual_phylogeny"),
    )
    parser.add_argument(
        "--min-total-sequences",
        type=int,
        default=5,
        help="Minimum combined WINGS + public sequences required to mark a segment READY",
    )
    args = parser.parse_args(argv)

    selected_table = args.selected_dir / "selected_references.tsv"
    selected_rows = load_selected_rows(selected_table)
    metadata = load_metadata(args.metadata if args.metadata.is_file() else None)
    samples = discover_samples(args.results_dir, metadata)
    if not samples:
        raise ValueError("No WINGS samples found")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: List[dict] = []
    status_rows: List[dict] = []
    summary_segments: Dict[str, dict] = {}

    for segment in SEGMENTS:
        tips_seen: set[str] = set()
        combined: List[Tuple[str, str]] = []
        exclusions = Counter()
        wings_count = 0

        for sample in samples:
            sample_dir = args.results_dir / sample
            coverage_path = sample_dir / "coverage" / "coverage.tsv"
            merged_path = sample_dir / "merged" / "consensus_all_segments.fasta"
            row = coverage_row(coverage_path, segment)
            if row is None:
                exclusions["wings_missing_coverage"] += 1
                continue
            if clean(row.get("overall_status")).upper() != "PASS":
                exclusions["wings_nonpass"] += 1
                continue
            contig = clean(row.get("contig"))
            if not contig:
                exclusions["wings_missing_contig"] += 1
                continue
            records = read_fasta_by_token(merged_path)
            sequence = records.get(contig)
            if not sequence:
                exclusions["wings_missing_consensus"] += 1
                continue
            tip = f"{sample}__{taxon_suffix(contig, segment)}"
            if tip in tips_seen:
                raise ValueError(f"Duplicate tree tip {tip!r} for {segment}")
            tips_seen.add(tip)
            combined.append((tip, sequence))
            wings_count += 1
            manifest_rows.append(
                wings_manifest_row(segment, tip, sample, contig, sequence, row, metadata.get(sample, {}))
            )

        public_fasta = args.selected_dir / f"selected_{segment}.fasta"
        public_records = read_fasta_by_token(public_fasta)
        public_count = 0
        missing_selected_metadata = 0
        for accession in sorted(public_records):
            sequence = public_records[accession]
            source = selected_rows.get((segment, accession))
            if source is None:
                missing_selected_metadata += 1
                raise ValueError(
                    f"Public FASTA record {segment}/{accession} is absent from {selected_table}"
                )
            if accession in tips_seen:
                raise ValueError(f"Tree-tip collision for {segment}: {accession}")
            tips_seen.add(accession)
            combined.append((accession, sequence))
            public_count += 1
            manifest_rows.append(public_manifest_row(segment, accession, sequence, source))

        expected_public = sum(1 for key in selected_rows if key[0] == segment)
        observed_public = set(public_records)
        expected_public_ids = {accession for seg, accession in selected_rows if seg == segment}
        missing_public_fasta = sorted(expected_public_ids - observed_public)
        unexpected_public_fasta = sorted(observed_public - expected_public_ids)
        if missing_public_fasta or unexpected_public_fasta:
            raise ValueError(
                f"Selected public FASTA/table mismatch for {segment}: "
                f"missing={len(missing_public_fasta)}, unexpected={len(unexpected_public_fasta)}"
            )

        output_fasta = args.output_dir / f"{segment}.contextual.input.fasta"
        total_count = write_fasta(output_fasta, combined)
        status = "READY" if total_count >= args.min_total_sequences else "INSUFFICIENT_SEQUENCES"
        status_row = {
            "segment": segment,
            "status": status,
            "wings_sequence_count": str(wings_count),
            "public_sequence_count": str(public_count),
            "total_sequence_count": str(total_count),
            "min_total_sequences": str(args.min_total_sequences),
            "wings_nonpass": str(exclusions["wings_nonpass"]),
            "wings_missing_coverage": str(exclusions["wings_missing_coverage"]),
            "wings_missing_contig": str(exclusions["wings_missing_contig"]),
            "wings_missing_consensus": str(exclusions["wings_missing_consensus"]),
        }
        status_rows.append(status_row)
        summary_segments[segment] = {
            "status": status,
            "wings_sequences": wings_count,
            "public_sequences": public_count,
            "total_sequences": total_count,
            "selected_public_rows": expected_public,
            "output_fasta": str(output_fasta),
            "wings_exclusions": dict(exclusions),
        }

    manifest_fields = [
        "segment", "tip_label", "tip_kind", "sample_id", "accession", "reference_id",
        "isolate", "host", "collection_date", "country", "state", "genotype",
        "segment_type", "selection_reason", "overall_status", "contig", "sequence_length",
    ]
    with (args.output_dir / "contextual_tip_manifest.tsv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest_fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(manifest_rows)

    status_fields = [
        "segment", "status", "wings_sequence_count", "public_sequence_count",
        "total_sequence_count", "min_total_sequences", "wings_nonpass",
        "wings_missing_coverage", "wings_missing_contig", "wings_missing_consensus",
    ]
    with (args.output_dir / "segment_status.tsv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=status_fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(status_rows)

    summary = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "results_dir": str(args.results_dir.resolve()),
        "selected_dir": str(args.selected_dir.resolve()),
        "metadata_file": str(args.metadata.resolve()) if args.metadata.is_file() else None,
        "sample_count_considered": len(samples),
        "tip_label_policy": {
            "wings": "<sample_id>__<IRMA_contig_without_A_>",
            "public_reference": "GenBank accession",
        },
        "segments": summary_segments,
        "notes": [
            "Only WINGS segments with coverage.tsv overall_status=PASS are included.",
            "Public references are exactly those present in selected_<SEGMENT>.fasta and selected_references.tsv.",
            "This stage does not align sequences or infer phylogenies.",
            "Public accessions are preserved exactly; accession versions are not fabricated.",
        ],
    }
    (args.output_dir / "build_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    print("Contextual phylogeny inputs:")
    for segment in SEGMENTS:
        info = summary_segments[segment]
        print(
            f"  {segment}: {info['wings_sequences']} WINGS + "
            f"{info['public_sequences']} public = {info['total_sequences']} ({info['status']})"
        )
    print(f"Wrote: {args.output_dir / 'contextual_tip_manifest.tsv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
