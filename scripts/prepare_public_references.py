#!/usr/bin/env python3
"""Prepare locally downloaded NCBI/GenBank influenza references for WINGS.

The script joins a FASTA file to an NCBI metadata TSV by exact GenBank
accession, preserves the large source files in place, and normalizes the NCBI
influenza segment number to the WINGS segment names:

    1 -> PB2
    2 -> PB1
    3 -> PA
    4 -> HA
    5 -> NP
    6 -> NA
    7 -> MP
    8 -> NS

The GenBank accession remains the primary sequence key. Cross-segment
biological-sample linkage is NOT inferred automatically from matching Isolate
strings; that remains a separate reviewed step.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, TextIO, Tuple


REQUIRED_METADATA_COLUMNS = ("Accession", "Segment")
OPTIONAL_METADATA_COLUMNS = (
    "Isolate",
    "Geo_Location",
    "Country",
    "USA",
    "Host",
    "Collection_Date",
)

SEGMENT_NUMBER_TO_NAME = {
    "1": "PB2",
    "2": "PB1",
    "3": "PA",
    "4": "HA",
    "5": "NP",
    "6": "NA",
    "7": "MP",
    "8": "NS",
}
SEGMENT_ORDER = ("HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS")

IUPAC_DNA = frozenset("ACGTRYSWKMBDHVN.-U")
VERSIONED_ACCESSION_RE = re.compile(r"^[A-Za-z]{1,8}_?\d+(?:\.\d+)$")
ACCESSION_RE = re.compile(r"^[A-Za-z]{1,8}_?\d+(?:\.\d+)?$")


@contextmanager
def open_text(path: Path) -> Iterator[TextIO]:
    """Open plain text or gzip-compressed text using UTF-8."""
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            yield handle
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            yield handle


def clean(value: Optional[str]) -> str:
    return (value or "").strip()


def accession_base(accession: str) -> str:
    return re.sub(r"\.\d+$", "", accession)


def accession_version(accession: str) -> str:
    return accession if VERSIONED_ACCESSION_RE.fullmatch(accession) else ""


def normalize_segment(value: str) -> Tuple[str, str]:
    """Return (segment_number, WINGS segment name), or blank values if invalid.

    NCBI influenza exports are not perfectly uniform. In addition to bare
    segment numbers, accept common NCBI variants such as ``RNA 4`` and
    ``segment 4``. ``MA`` is normalized to WINGS ``MP`` (influenza A segment 7,
    the matrix segment). Blank values remain unresolved rather than inferred.
    """
    raw = clean(value).upper()
    if raw in SEGMENT_NUMBER_TO_NAME:
        return raw, SEGMENT_NUMBER_TO_NAME[raw]

    # Also accept already-normalized WINGS names in case an export is edited or
    # another trusted metadata source is used.
    aliases = {name: number for number, name in SEGMENT_NUMBER_TO_NAME.items()}
    aliases["MA"] = "7"
    if raw in aliases:
        number = aliases[raw]
        return number, SEGMENT_NUMBER_TO_NAME[number]

    # NCBI metadata can express segment numbers as "RNA 4" or "segment 4".
    match = re.fullmatch(r"(?:RNA|SEGMENT)\s*([1-8])", raw)
    if match:
        number = match.group(1)
        return number, SEGMENT_NUMBER_TO_NAME[number]

    return "", ""


def date_precision(value: str) -> str:
    """Classify an NCBI collection date without inventing missing precision."""
    if not value:
        return "not_recorded"
    try:
        if re.fullmatch(r"\d{4}", value):
            date(int(value), 1, 1)
            return "year"
        if re.fullmatch(r"\d{4}-\d{2}", value):
            date.fromisoformat(value + "-01")
            return "month"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date.fromisoformat(value)
            return "day"
    except ValueError:
        return "invalid"
    return "invalid"


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} does not exist or is not a file: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"{label} is empty: {path}")


def load_metadata(path: Path) -> Tuple[List[dict], Dict[str, dict], List[dict]]:
    """Load metadata keyed by exact Accession and preserve input row order."""
    rows: List[dict] = []
    by_accession: Dict[str, dict] = {}
    issues: List[dict] = []

    with open_text(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
        missing = [name for name in REQUIRED_METADATA_COLUMNS if name not in fieldnames]
        if missing:
            raise ValueError(
                "Metadata TSV is missing required column(s): " + ", ".join(missing)
            )

        for line_number, source in enumerate(reader, start=2):
            accession = clean(source.get("Accession"))
            if not accession:
                issues.append(
                    {
                        "level": "ERROR",
                        "code": "MISSING_ACCESSION",
                        "accession": "",
                        "line": str(line_number),
                        "message": "Metadata row has an empty Accession primary key.",
                    }
                )
                continue

            if accession in by_accession:
                raise ValueError(
                    f"Duplicate metadata Accession {accession!r} at line {line_number}; "
                    "Accession must be unique."
                )

            source_segment = clean(source.get("Segment"))
            segment_number, segment = normalize_segment(source_segment)

            normalized = {
                "accession": accession,
                "accession_base": accession_base(accession),
                "accession_version": accession_version(accession),
                "segment_number": segment_number,
                "segment": segment,
                "source_segment": source_segment,
                "isolate": clean(source.get("Isolate")),
                "geo_location": clean(source.get("Geo_Location")),
                "country": clean(source.get("Country")),
                # NCBI Virus exports commonly label the U.S. first-level field "USA".
                # Preserve it verbatim as state; do not infer a state from Geo_Location.
                "state": clean(source.get("USA")),
                "host": clean(source.get("Host")),
                "collection_date": clean(source.get("Collection_Date")),
                "collection_date_precision": "",
                "metadata_line": str(line_number),
            }
            normalized["collection_date_precision"] = date_precision(
                normalized["collection_date"]
            )

            if not ACCESSION_RE.fullmatch(accession):
                issues.append(
                    {
                        "level": "WARNING",
                        "code": "UNUSUAL_ACCESSION_FORMAT",
                        "accession": accession,
                        "line": str(line_number),
                        "message": "Accession does not match the expected GenBank-style pattern; exact joining is still used.",
                    }
                )

            if not segment:
                issues.append(
                    {
                        "level": "WARNING",
                        "code": "INVALID_OR_MISSING_SEGMENT",
                        "accession": accession,
                        "line": str(line_number),
                        "message": (
                            "Segment must be 1-8, RNA 1-8, segment 1-8, MA, or one of PB2, PB1, PA, HA, NP, NA, MP, NS; "
                            f"observed {source_segment!r}."
                        ),
                    }
                )

            if normalized["collection_date_precision"] == "invalid":
                issues.append(
                    {
                        "level": "WARNING",
                        "code": "INVALID_COLLECTION_DATE",
                        "accession": accession,
                        "line": str(line_number),
                        "message": (
                            "Collection_Date is not blank, YYYY, YYYY-MM, or YYYY-MM-DD: "
                            + repr(normalized["collection_date"])
                        ),
                    }
                )

            rows.append(normalized)
            by_accession[accession] = normalized

    if not rows:
        raise ValueError("Metadata TSV contains no usable records.")
    return rows, by_accession, issues


def iter_fasta_records(path: Path) -> Iterator[Tuple[str, str, int, int]]:
    """Yield (accession, header, sequence_length, invalid_symbol_count)."""
    with open_text(path) as handle:
        header: Optional[str] = None
        accession: Optional[str] = None
        length = 0
        invalid = 0

        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None and accession is not None:
                    yield accession, header, length, invalid
                header = line[1:].strip()
                if not header:
                    raise ValueError(f"FASTA line {line_number}: empty definition line")
                accession = header.split()[0]
                length = 0
                invalid = 0
                continue

            if header is None or accession is None:
                raise ValueError(
                    f"FASTA line {line_number}: sequence data encountered before the first definition line"
                )
            seq = "".join(line.split()).upper()
            length += len(seq)
            invalid += sum(base not in IUPAC_DNA for base in seq)

        if header is not None and accession is not None:
            yield accession, header, length, invalid


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_tsv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            fieldnames=list(fieldnames),
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def prepare(
    fasta: Path,
    metadata: Path,
    output_dir: Path,
    hash_inputs: bool = False,
    strict: bool = False,
) -> dict:
    require_file(fasta, "FASTA")
    require_file(metadata, "metadata TSV")
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata_rows, metadata_by_accession, issues = load_metadata(metadata)

    fasta_index_path = output_dir / "fasta_index.tsv"
    fasta_seen = set()
    matched_accessions = set()
    fasta_without_metadata = 0
    fasta_records = 0
    total_bases = 0
    invalid_symbol_records = 0
    versioned_fasta_accessions = 0

    with fasta_index_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            fieldnames=(
                "accession",
                "accession_base",
                "accession_version",
                "sequence_length",
                "invalid_symbol_count",
                "metadata_status",
                "fasta_header",
            ),
            lineterminator="\n",
        )
        writer.writeheader()

        for accession, header, sequence_length, invalid_count in iter_fasta_records(fasta):
            fasta_records += 1
            total_bases += sequence_length
            if accession in fasta_seen:
                raise ValueError(
                    f"Duplicate FASTA accession {accession!r}; FASTA accessions must be unique."
                )
            fasta_seen.add(accession)

            if VERSIONED_ACCESSION_RE.fullmatch(accession):
                versioned_fasta_accessions += 1

            if invalid_count:
                invalid_symbol_records += 1
                issues.append(
                    {
                        "level": "WARNING",
                        "code": "NON_IUPAC_SEQUENCE_SYMBOL",
                        "accession": accession,
                        "line": "",
                        "message": f"FASTA sequence contains {invalid_count} non-IUPAC symbol(s).",
                    }
                )

            if accession in metadata_by_accession:
                metadata_status = "MATCHED"
                matched_accessions.add(accession)
                row = metadata_by_accession[accession]
                row["sequence_length"] = str(sequence_length)
                row["fasta_header"] = header
                row["in_fasta"] = "true"
            else:
                metadata_status = "NO_METADATA"
                fasta_without_metadata += 1
                issues.append(
                    {
                        "level": "WARNING",
                        "code": "FASTA_WITHOUT_METADATA",
                        "accession": accession,
                        "line": "",
                        "message": "FASTA accession has no exact Accession match in the metadata TSV.",
                    }
                )

            writer.writerow(
                {
                    "accession": accession,
                    "accession_base": accession_base(accession),
                    "accession_version": accession_version(accession),
                    "sequence_length": sequence_length,
                    "invalid_symbol_count": invalid_count,
                    "metadata_status": metadata_status,
                    "fasta_header": header,
                }
            )

    if fasta_records == 0:
        raise ValueError("FASTA contains no records.")

    metadata_without_fasta = 0
    for row in metadata_rows:
        if "in_fasta" not in row:
            row["in_fasta"] = "false"
            row["sequence_length"] = ""
            row["fasta_header"] = ""
            metadata_without_fasta += 1
            issues.append(
                {
                    "level": "WARNING",
                    "code": "METADATA_WITHOUT_FASTA",
                    "accession": row["accession"],
                    "line": row["metadata_line"],
                    "message": "Metadata accession has no exact match in the FASTA definition lines.",
                }
            )

    normalized_path = output_dir / "normalized_metadata.tsv"
    normalized_fields = (
        "accession",
        "accession_base",
        "accession_version",
        "segment_number",
        "segment",
        "source_segment",
        "isolate",
        "geo_location",
        "country",
        "state",
        "host",
        "collection_date",
        "collection_date_precision",
        "sequence_length",
        "in_fasta",
        "fasta_header",
        "metadata_line",
    )
    write_tsv(normalized_path, normalized_fields, metadata_rows)

    candidate_path = output_dir / "public_reference_candidates.tsv"
    candidate_rows = []
    for row in metadata_rows:
        if row["in_fasta"] != "true":
            continue
        candidate_rows.append(
            {
                "accession": row["accession"],
                "accession_version": row["accession_version"],
                "segment_number": row["segment_number"],
                "segment": row["segment"],
                "tip_label": row["accession"],
                # Keep accession as the default reference_id. Matching Isolate
                # strings are useful review evidence but are not sufficient by
                # themselves to establish cross-segment biological identity.
                "reference_id": row["accession"],
                "isolate": row["isolate"],
                "isolate_linkage_candidate": row["isolate"],
                "host": row["host"],
                "collection_date": row["collection_date"],
                "country": row["country"],
                "state": row["state"],
                "geo_location": row["geo_location"],
                "sequence_length": row["sequence_length"],
                "linkage_basis": "",
                "manifest_ready": (
                    "true"
                    if row["accession_version"] and row["segment"]
                    else "false"
                ),
            }
        )
    write_tsv(
        candidate_path,
        (
            "accession",
            "accession_version",
            "segment_number",
            "segment",
            "tip_label",
            "reference_id",
            "isolate",
            "isolate_linkage_candidate",
            "host",
            "collection_date",
            "country",
            "state",
            "geo_location",
            "sequence_length",
            "linkage_basis",
            "manifest_ready",
        ),
        candidate_rows,
    )

    validation_path = output_dir / "validation.tsv"
    write_tsv(
        validation_path,
        ("level", "code", "accession", "line", "message"),
        issues,
    )

    segment_counts = {segment: 0 for segment in SEGMENT_ORDER}
    invalid_segment_records = 0
    for row in metadata_rows:
        if row["segment"]:
            segment_counts[row["segment"]] += 1
        else:
            invalid_segment_records += 1

    summary = {
        "schema_version": 2,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "join_key": "exact GenBank accession from metadata Accession and first FASTA definition-line token",
        "segment_source": "NCBI metadata Segment column",
        "segment_mapping": SEGMENT_NUMBER_TO_NAME,
        "fasta": {
            "path": str(fasta.resolve()),
            "size_bytes": fasta.stat().st_size,
            "records": fasta_records,
            "total_bases": total_bases,
            "versioned_accessions": versioned_fasta_accessions,
            "unversioned_accessions": fasta_records - versioned_fasta_accessions,
            "records_with_non_iupac_symbols": invalid_symbol_records,
        },
        "metadata": {
            "path": str(metadata.resolve()),
            "size_bytes": metadata.stat().st_size,
            "records": len(metadata_rows),
            "versioned_accessions": sum(
                1 for row in metadata_rows if row["accession_version"]
            ),
            "unversioned_accessions": sum(
                1 for row in metadata_rows if not row["accession_version"]
            ),
            "invalid_or_missing_segment_records": invalid_segment_records,
            "segment_counts": segment_counts,
        },
        "join": {
            "matched_records": len(matched_accessions),
            "metadata_without_fasta": metadata_without_fasta,
            "fasta_without_metadata": fasta_without_metadata,
        },
        "issues": {
            "errors": sum(1 for issue in issues if issue["level"] == "ERROR"),
            "warnings": sum(1 for issue in issues if issue["level"] == "WARNING"),
        },
        "outputs": {
            "normalized_metadata": str(normalized_path.resolve()),
            "fasta_index": str(fasta_index_path.resolve()),
            "public_reference_candidates": str(candidate_path.resolve()),
            "validation": str(validation_path.resolve()),
        },
        "notes": [
            "The original FASTA and metadata files are read in place and are not copied.",
            "Segment identity comes directly from the NCBI metadata Segment field; BLAST is not used for segment assignment.",
            "GenBank accession remains the primary sequence-to-metadata key.",
            "Cross-segment biological-sample linkage is not inferred automatically from matching Isolate strings.",
            "isolate_linkage_candidate is provided only to support later manual or provenance-backed grouping.",
            "The current WINGS public-reference display manifest requires accession.version. Unversioned NCBI accessions remain valid preparation records but are not marked manifest_ready.",
        ],
    }

    if hash_inputs:
        summary["fasta"]["sha256"] = sha256_file(fasta)
        summary["metadata"]["sha256"] = sha256_file(metadata)

    summary_path = output_dir / "summary.json"
    summary["outputs"]["summary"] = str(summary_path.resolve())
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if strict and issues:
        raise ValueError(
            f"Strict mode: {len(issues)} validation issue(s) were written to {validation_path}"
        )

    return summary


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Join a local NCBI/GenBank FASTA to NCBI influenza metadata by exact "
            "GenBank accession and normalize the metadata Segment field for WINGS."
        )
    )
    parser.add_argument("--fasta", required=True, type=Path, help="Local FASTA or FASTA.gz")
    parser.add_argument(
        "--metadata",
        required=True,
        type=Path,
        help="Local tab-delimited NCBI metadata TSV or TSV.gz containing Accession and Segment",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/run_summary/public_references/prepared"),
        help="Directory for lightweight prepared outputs",
    )
    parser.add_argument(
        "--hash-inputs",
        action="store_true",
        help="Also compute SHA-256 hashes of the raw source files (extra I/O for large files)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any validation warning/error is recorded",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        summary = prepare(
            fasta=args.fasta,
            metadata=args.metadata,
            output_dir=args.output_dir,
            hash_inputs=args.hash_inputs,
            strict=args.strict,
        )
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary["join"], indent=2))
    print("Segment counts:")
    for segment in SEGMENT_ORDER:
        print(f"  {segment}: {summary['metadata']['segment_counts'][segment]}")
    invalid = summary["metadata"]["invalid_or_missing_segment_records"]
    print(f"  INVALID_OR_MISSING: {invalid}")
    print(f"Prepared outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
