#!/usr/bin/env python3
"""Assign GenoFLU genotypes to metadata-linked public influenza reference genomes.

This script is the bridge between per-segment GenBank records and WINGS
contextual-reference selection. It groups public segment records into candidate
whole genomes using an exact metadata tuple, extracts the corresponding
sequences from a large FASTA in one streaming pass, and runs GenoFLU on complete
8-segment genomes.

The biological isolate string is never used alone as the grouping key. A group
must agree on isolate, collection date, country, state, and host. Groups with
missing isolate metadata, duplicate segments, or fewer than the requested
number of distinct segments are recorded but are not sent to GenoFLU.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

SEGMENTS = ("PB2", "PB1", "PA", "HA", "NP", "NA", "MP", "NS")
NORTH_AMERICA = {"USA", "UNITED STATES", "CANADA", "MEXICO"}
MISSING = {"", "N/A", "NONE", "NULL", "UNKNOWN", "NAN"}


def clean(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.upper() in MISSING else text


def normalize_country(value: str) -> str:
    text = clean(value)
    upper = text.upper()
    if upper in {"US", "U.S.", "U.S.A.", "UNITED STATES", "UNITED STATES OF AMERICA"}:
        return "USA"
    if upper == "CANADA":
        return "Canada"
    if upper == "MEXICO":
        return "Mexico"
    return text


def year_from_date(value: str) -> Optional[int]:
    match = re.match(r"^(\d{4})", clean(value))
    if not match:
        return None
    year = int(match.group(1))
    return year if 1800 <= year <= 2200 else None


def stable_group_id(parts: Sequence[str]) -> str:
    payload = "\t".join(parts).encode("utf-8")
    return "PUB_" + hashlib.sha1(payload).hexdigest()[:14]


def read_tsv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def write_tsv(path: Path, fields: Sequence[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def iter_fasta(path: Path) -> Iterator[Tuple[str, str]]:
    header: Optional[str] = None
    chunks: List[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\r\n")
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(chunks)
                header = line[1:].strip()
                chunks = []
            elif header is not None:
                chunks.append(line.strip())
        if header is not None:
            yield header, "".join(chunks)


def fasta_accession(header: str) -> str:
    return header.split(None, 1)[0].split("|", 1)[0].strip()


@dataclass
class GenomeGroup:
    group_id: str
    isolate: str
    collection_date: str
    country: str
    state: str
    host: str
    rows_by_segment: Dict[str, dict]
    eligible: bool
    reason: str

    @property
    def accessions(self) -> List[str]:
        return [clean(self.rows_by_segment[s].get("accession")) for s in SEGMENTS if s in self.rows_by_segment]


def group_candidates(
    rows: Sequence[dict],
    countries: set[str],
    min_year: int,
    require_segments: int,
) -> Tuple[List[GenomeGroup], List[dict], Counter]:
    buckets: Dict[Tuple[str, str, str, str, str], List[dict]] = defaultdict(list)
    issues: List[dict] = []
    stats: Counter = Counter()

    for row in rows:
        stats["candidate_rows"] += 1
        segment = clean(row.get("segment")).upper()
        if segment not in SEGMENTS:
            stats["excluded_invalid_segment"] += 1
            continue
        isolate = clean(row.get("isolate"))
        if not isolate:
            stats["excluded_missing_isolate"] += 1
            continue
        country = normalize_country(clean(row.get("country")))
        if countries and country.upper() not in countries:
            stats["excluded_country"] += 1
            continue
        year = year_from_date(clean(row.get("collection_date")))
        if year is None or year < min_year:
            stats["excluded_date"] += 1
            continue

        key = (
            isolate,
            clean(row.get("collection_date")),
            country,
            clean(row.get("state")),
            clean(row.get("host")),
        )
        buckets[key].append(row)

    groups: List[GenomeGroup] = []
    for key, members in buckets.items():
        isolate, collection_date, country, state, host = key
        rows_by_segment: Dict[str, dict] = {}
        duplicate_segments: List[str] = []
        for row in members:
            segment = clean(row.get("segment")).upper()
            if segment in rows_by_segment:
                duplicate_segments.append(segment)
            else:
                rows_by_segment[segment] = row

        reasons: List[str] = []
        if duplicate_segments:
            reasons.append("duplicate_segments=" + ",".join(sorted(set(duplicate_segments))))
        if len(rows_by_segment) < require_segments:
            reasons.append(f"segments={len(rows_by_segment)}<{require_segments}")

        eligible = not reasons
        gid = stable_group_id(key)
        group = GenomeGroup(
            group_id=gid,
            isolate=isolate,
            collection_date=collection_date,
            country=country,
            state=state,
            host=host,
            rows_by_segment=rows_by_segment,
            eligible=eligible,
            reason=";".join(reasons) if reasons else "eligible",
        )
        groups.append(group)
        stats["groups_total"] += 1
        stats["groups_eligible"] += int(eligible)
        stats["groups_ineligible"] += int(not eligible)
        if not eligible:
            issues.append(
                {
                    "group_id": gid,
                    "isolate": isolate,
                    "collection_date": collection_date,
                    "country": country,
                    "state": state,
                    "host": host,
                    "segments_present": ",".join(s for s in SEGMENTS if s in rows_by_segment),
                    "reason": group.reason,
                }
            )

    groups.sort(key=lambda g: (g.collection_date, g.country, g.state, g.isolate, g.group_id))
    return groups, issues, stats


def extract_sequences(fasta: Path, needed: set[str]) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for header, sequence in iter_fasta(fasta):
        acc = fasta_accession(header)
        if acc in needed:
            found[acc] = sequence
            if len(found) == len(needed):
                break
    return found


def parse_genoflu(text: str) -> dict:
    result = {
        "genotype": "",
        "status": "NOT_ASSIGNED",
        "reason": "",
        "threshold": "",
        "segment_calls": {},
    }

    threshold = re.search(r"pident_threshold:\s*([0-9.]+)", text, flags=re.IGNORECASE)
    if threshold:
        result["threshold"] = threshold.group(1)

    summary = re.search(
        r"(?:consensus|\S+)\s+Genotype\s+-->\s+([^:\n]+):\s*(.*)",
        text,
        flags=re.IGNORECASE,
    )
    if summary:
        label = summary.group(1).strip()
        result["reason"] = summary.group(2).strip()
        if label.lower() not in {"not assigned", "no matching genotypes", "no match", "not available"}:
            result["genotype"] = label
            result["status"] = "ASSIGNED"
        else:
            result["status"] = label.upper().replace(" ", "_")

    def add_calls(payload: str) -> None:
        # GenoFLU emits segment calls as comma-separated SEGMENT:TYPE pairs.
        # Assigned genotypes place them immediately after the genotype label,
        # while NOT_ASSIGNED output places them after "segments in input file:".
        payload = re.split(
            r"\s+at\s+percent\s+identity",
            payload,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        for item in payload.split(","):
            if ":" not in item:
                continue
            segment, call = item.split(":", 1)
            segment = segment.strip().upper()
            call = call.strip()
            if segment in SEGMENTS and call:
                result["segment_calls"][segment] = call

    # For assigned genotypes GenoFLU writes, for example:
    # consensus Genotype --> D1.1: HA:ea3, NA:am4N1, ... at percent identity ...
    if summary:
        add_calls(summary.group(2))

    # For NOT_ASSIGNED reports GenoFLU describes only the segment calls that
    # exceeded the identity threshold in this alternate phrase. Keep this
    # fallback because incomplete WINGS/public genomes can use that format.
    calls = re.search(
        r"segments\s+in\s+input\s+file:\s*(.*?)\s+at\s+percent\s+identity",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if calls:
        add_calls(calls.group(1))
    return result


def run_genoflu(group: GenomeGroup, sequences: Dict[str, str], exe: str) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"wings_{group.group_id}_") as tmp:
        tmpdir = Path(tmp)
        fasta_path = tmpdir / f"{group.group_id}.fasta"
        with fasta_path.open("w", encoding="utf-8") as handle:
            for segment in SEGMENTS:
                row = group.rows_by_segment.get(segment)
                if not row:
                    continue
                acc = clean(row.get("accession"))
                seq = sequences.get(acc, "")
                if not seq:
                    return {
                        "group_id": group.group_id,
                        "run_status": "MISSING_FASTA_SEQUENCE",
                        "genotype": "",
                        "genoflu_status": "",
                        "reason": f"Sequence not found for {acc}",
                        "threshold": "",
                        "segment_calls": {},
                        "raw_output": "",
                    }
                handle.write(f">{acc}|{segment}\n{seq}\n")

        proc = subprocess.run(
            [exe, "-f", fasta_path.name],
            cwd=tmpdir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        parsed = parse_genoflu(proc.stdout)
        return {
            "group_id": group.group_id,
            "run_status": "OK" if proc.returncode == 0 else f"EXIT_{proc.returncode}",
            "genotype": parsed["genotype"],
            "genoflu_status": parsed["status"],
            "reason": parsed["reason"],
            "threshold": parsed["threshold"],
            "segment_calls": parsed["segment_calls"],
            "raw_output": proc.stdout,
        }


def build_output_row(group: GenomeGroup, result: dict) -> dict:
    row = {
        "reference_id": group.group_id,
        "isolate": group.isolate,
        "host": group.host,
        "collection_date": group.collection_date,
        "country": group.country,
        "state": group.state,
        "genotype": result.get("genotype", ""),
        "genoflu_status": result.get("genoflu_status", ""),
        "run_status": result.get("run_status", ""),
        "genoflu_threshold": result.get("threshold", ""),
        "genoflu_reason": result.get("reason", ""),
    }
    calls = result.get("segment_calls", {}) or {}
    for segment in SEGMENTS:
        source = group.rows_by_segment.get(segment, {})
        row[f"{segment}_accession"] = clean(source.get("accession"))
        row[f"{segment}_type"] = clean(calls.get(segment))
    return row


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path, help="public_reference_candidates.tsv")
    parser.add_argument("--fasta", type=Path, help="Large public reference FASTA; required unless --dry-run")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--genoflu-exe", default="genoflu.py")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--min-year", type=int, default=2021)
    parser.add_argument("--require-segments", type=int, default=8, choices=range(1, 9))
    parser.add_argument(
        "--countries",
        default="USA,Canada,Mexico",
        help="Comma-separated countries retained before genotyping; empty means all countries",
    )
    parser.add_argument("--dry-run", action="store_true", help="Group and summarize only; do not run GenoFLU")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if not args.candidates.is_file():
        print(f"ERROR: candidates file not found: {args.candidates}", file=sys.stderr)
        return 2
    if not args.dry_run and (args.fasta is None or not args.fasta.is_file()):
        print("ERROR: --fasta is required and must exist unless --dry-run is used", file=sys.stderr)
        return 2
    if not args.dry_run and shutil.which(args.genoflu_exe) is None:
        print(f"ERROR: GenoFLU executable not found on PATH: {args.genoflu_exe}", file=sys.stderr)
        return 2
    if args.workers < 1:
        print("ERROR: --workers must be >=1", file=sys.stderr)
        return 2

    countries = {normalize_country(x).upper() for x in args.countries.split(",") if clean(x)}
    rows = read_tsv(args.candidates)
    groups, issues, stats = group_candidates(rows, countries, args.min_year, args.require_segments)
    eligible = [g for g in groups if g.eligible]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    issue_fields = ("group_id", "isolate", "collection_date", "country", "state", "host", "segments_present", "reason")
    write_tsv(args.output_dir / "grouping_issues.tsv", issue_fields, issues)

    group_manifest_fields = [
        "reference_id", "isolate", "host", "collection_date", "country", "state", "eligible", "reason",
        *[f"{segment}_accession" for segment in SEGMENTS],
    ]
    group_manifest = []
    for g in groups:
        record = {
            "reference_id": g.group_id,
            "isolate": g.isolate,
            "host": g.host,
            "collection_date": g.collection_date,
            "country": g.country,
            "state": g.state,
            "eligible": "true" if g.eligible else "false",
            "reason": g.reason,
        }
        for segment in SEGMENTS:
            record[f"{segment}_accession"] = clean(g.rows_by_segment.get(segment, {}).get("accession"))
        group_manifest.append(record)
    write_tsv(args.output_dir / "public_genome_groups.tsv", group_manifest_fields, group_manifest)

    summary = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_file": str(args.candidates.resolve()),
        "fasta": str(args.fasta.resolve()) if args.fasta else None,
        "min_year": args.min_year,
        "countries": sorted(countries),
        "require_segments": args.require_segments,
        "grouping_key": ["isolate", "collection_date", "country", "state", "host"],
        "stats": dict(stats),
        "dry_run": bool(args.dry_run),
    }

    if args.dry_run:
        (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary["stats"], indent=2))
        print(f"Prepared grouping outputs: {args.output_dir}")
        return 0

    needed = {acc for g in eligible for acc in g.accessions if acc}
    sequences = extract_sequences(args.fasta, needed)
    missing = sorted(needed - set(sequences))
    summary["sequence_extraction"] = {
        "requested_accessions": len(needed),
        "found_accessions": len(sequences),
        "missing_accessions": len(missing),
    }
    if missing:
        (args.output_dir / "missing_fasta_accessions.txt").write_text("\n".join(missing) + "\n", encoding="utf-8")

    results: Dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_genoflu, g, sequences, args.genoflu_exe): g for g in eligible}
        for index, future in enumerate(as_completed(futures), start=1):
            g = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # defensive: preserve long batch runs
                result = {
                    "group_id": g.group_id,
                    "run_status": "ERROR",
                    "genotype": "",
                    "genoflu_status": "",
                    "reason": str(exc),
                    "threshold": "",
                    "segment_calls": {},
                    "raw_output": "",
                }
            results[g.group_id] = result
            if index % 100 == 0 or index == len(eligible):
                print(f"GenoFLU completed: {index}/{len(eligible)}", file=sys.stderr)

    output_fields = [
        "reference_id", "isolate", "host", "collection_date", "country", "state",
        "genotype", "genoflu_status", "run_status", "genoflu_threshold", "genoflu_reason",
    ]
    for segment in SEGMENTS:
        output_fields.extend((f"{segment}_accession", f"{segment}_type"))

    output_rows = [build_output_row(g, results[g.group_id]) for g in eligible]
    write_tsv(args.output_dir / "public_reference_genotypes.tsv", output_fields, output_rows)

    genotype_counts = Counter(clean(row.get("genotype")) or "UNASSIGNED" for row in output_rows)
    run_counts = Counter(clean(row.get("run_status")) or "UNKNOWN" for row in output_rows)
    summary["genoflu"] = {
        "groups_submitted": len(eligible),
        "genotype_counts": dict(sorted(genotype_counts.items())),
        "run_status_counts": dict(sorted(run_counts.items())),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("GenoFLU genotype counts:")
    for genotype, count in genotype_counts.most_common():
        print(f"  {genotype}: {count}")
    print(f"Wrote: {args.output_dir / 'public_reference_genotypes.tsv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
