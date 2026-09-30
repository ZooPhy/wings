#!/usr/bin/env python3
"""Select North American avian H5Nx contextual references for WINGS trees.

Selection is automatic and reproducible. WINGS sample GenoFLU outputs define
which public genotypes and segment types are most relevant. Public genomes with
the same whole-genome GenoFLU genotype are preferred; for each segment, genomes
sharing that GenoFLU segment type are the next priority. A bounded background
of other assigned North American H5 2.3.4.4b genotypes is retained for context.

The selector builds one shared reference pool per segment for the entire WINGS
run, so runs containing more than one genotype remain interpretable in the same
trees. It never invents a genotype from HA clade alone.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

SEGMENTS = ("PB2", "PB1", "PA", "HA", "NP", "NA", "MP", "NS")
NORTH_AMERICA = {"USA", "UNITED STATES", "CANADA", "MEXICO"}
MISSING = {"", "N/A", "NONE", "NULL", "UNKNOWN", "NAN"}

# Conservative bird taxa commonly represented in influenza surveillance data.
# Unknown taxa are not silently treated as avian. Users can supply an override
# TSV with --host-classification when a local taxonomy mapping is available.
AVIAN_TAXA = {
    "AVES", "ANATIDAE", "LARIDAE", "ACCIPITRIDAE", "FALCONIDAE", "STRIGIDAE",
    "CATHARTIDAE", "CORVIDAE", "PHASIANIDAE", "NUMIDIDAE", "SULIDAE",
    "PELECANIDAE", "PHALACROCORACIDAE", "ALCIDAE", "SCOLOPACIDAE",
    "CHARADRIIDAE", "ARDEIDAE", "RALLIDAE", "GRUIDAE", "COLUMBIDAE",
    "PASSERIFORMES", "CHARADRIIFORMES", "ANSERIFORMES", "GALLIFORMES",
    "ACCIPITRIFORMES", "FALCONIFORMES", "STRIGIFORMES", "PELECANIFORMES",
    "GALLUS", "MELEAGRIS", "ANAS", "ANSER", "BRANTA", "SPATULA", "MARECA",
    "AIX", "AYTHYA", "SOMATERIA", "CYGNUS", "CAIRINA", "LOPHODYTES",
    "MERGUS", "OXYURA", "BUCEPHALA", "CLANGULA", "MELANITTA", "POLYSTICTA",
    "HALIAEETUS", "BUTEO", "ACCIPITER", "AQUILA", "FALCO", "BUBO", "STRIX",
    "ATHENE", "TYTO", "CATHARTES", "CORAGYPS", "CORVUS", "PICA", "CYANOCITTA",
    "LARUS", "CHROICOCEPHALUS", "LEUCOPHAEUS", "RISSA", "STERNA", "THALASSEUS",
    "URIA", "ALCA", "FRATERCULA", "CEPPHUS", "CALIDRIS", "CHARADRIUS",
    "LIMOSA", "TRINGA", "ACTITIS", "ARENARIA", "NUMENIUS", "RECURVIROSTRA",
    "PELECANUS", "MORUS", "PHALACROCORAX", "NANNOPTERUM", "ARDEA", "EGRETTA",
    "NYCTICORAX", "IBIS", "PLEGADIS", "GRUS", "ANTIGONE", "FULICA", "GALLINULA",
    "COLUMBA", "ZENAIDA", "STREPTOPELIA", "PHASIANUS", "COTURNIX", "NUMIDA",
}


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


def open_text(path: Path):
    """Open plain-text or gzip-compressed input in text mode."""
    if str(path).lower().endswith(".gz"):
        import gzip
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def iter_fasta(path: Path) -> Iterator[Tuple[str, str]]:
    """Yield FASTA records as (header_without_>, sequence)."""
    header: Optional[str] = None
    parts: List[str] = []
    with open_text(path) as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(parts)
                header = line[1:].strip()
                parts = []
            else:
                if header is None:
                    raise ValueError(f"FASTA sequence encountered before first header in {path}")
                parts.append(line)
    if header is not None:
        yield header, "".join(parts)


def fasta_accession(header: str) -> str:
    """Return the accession token used by the prepared NCBI reference tables."""
    token = header.split(None, 1)[0].strip()
    # Preserve the accession exactly as represented in the source FASTA.
    return token


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


def parse_date(value: str) -> Optional[date]:
    text = clean(value)
    if not text:
        return None
    try:
        if re.fullmatch(r"\d{4}", text):
            return date(int(text), 7, 1)
        if re.fullmatch(r"\d{4}-\d{2}", text):
            return date.fromisoformat(text + "-15")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text)
    except ValueError:
        return None
    return None


def parse_genoflu(text: str) -> dict:
    """Parse genotype and per-segment calls from GenoFLU plain-text output."""
    result = {"genotype": "", "segment_calls": {}}

    # Assigned genotypes are reported on one line, e.g.
    # consensus Genotype --> D1.1: HA:ea3, NA:am4N1, ... at percent identity at 98.0
    summary = re.search(
        r"(?:consensus|\S+)\s+Genotype\s+-->\s+([^:\n]+):\s*(.*?)\s+at\s+percent\s+identity",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if summary:
        label = summary.group(1).strip()
        if label.lower() not in {"not assigned", "no matching genotypes", "no match", "not available"}:
            result["genotype"] = label

        # GenoFLU includes the segment-type constellation directly after the
        # genotype label for assigned genomes. Parse those calls here instead
        # of relying only on the separate unassigned-genotype wording below.
        for item in summary.group(2).split(","):
            if ":" not in item:
                continue
            segment, call = item.split(":", 1)
            segment = segment.strip().upper()
            call = call.strip()
            if segment in SEGMENTS and call:
                result["segment_calls"][segment] = call

    # When a complete genotype is not assigned, GenoFLU reports any matched
    # segment types in the "segments in input file" clause. Keep those calls
    # because they remain useful for segment-specific contextual selection.
    calls = re.search(
        r"segments\s+in\s+input\s+file:\s*(.*?)\s+at\s+percent\s+identity",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if calls:
        for item in calls.group(1).split(","):
            if ":" not in item:
                continue
            segment, call = item.split(":", 1)
            segment = segment.strip().upper()
            call = call.strip()
            if segment in SEGMENTS and call:
                result["segment_calls"][segment] = call
    return result


def load_wings_targets(results_dir: Path, metadata_path: Optional[Path]) -> List[dict]:
    metadata: Dict[str, dict] = {}
    if metadata_path and metadata_path.is_file():
        for row in read_tsv(metadata_path):
            sid = clean(row.get("sample_id") or row.get("sample"))
            if sid:
                metadata[sid] = row

    targets: List[dict] = []
    for path in sorted(results_dir.glob("*/genoflu/GenoFLU.tsv")):
        sample_id = path.parent.parent.name
        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_genoflu(text)
        if not parsed["genotype"] and not parsed["segment_calls"]:
            continue
        meta = metadata.get(sample_id, {})
        targets.append(
            {
                "sample_id": sample_id,
                "genotype": parsed["genotype"],
                "segment_calls": parsed["segment_calls"],
                "collection_date": clean(meta.get("collection_date")),
                "country": normalize_country(clean(meta.get("country"))),
                "state": clean(meta.get("state")),
                "host": clean(meta.get("host") or meta.get("host_species") or meta.get("host_common_name")),
            }
        )
    return targets


def load_host_overrides(path: Optional[Path]) -> Dict[str, bool]:
    if not path:
        return {}
    rows = read_tsv(path)
    result: Dict[str, bool] = {}
    for row in rows:
        host = clean(row.get("host"))
        value = clean(row.get("is_avian")).lower()
        if host and value in {"true", "false", "1", "0", "yes", "no"}:
            result[host.casefold()] = value in {"true", "1", "yes"}
    return result


def classify_avian(host: str, overrides: Dict[str, bool]) -> Tuple[bool, str]:
    text = clean(host)
    if not text:
        return False, "missing_host"
    key = text.casefold()
    if key in overrides:
        return overrides[key], "override"
    upper = text.upper()
    tokens = set(re.findall(r"[A-Z][A-Z.-]*", upper))
    first = upper.split(None, 1)[0]
    if upper in AVIAN_TAXA or first in AVIAN_TAXA or tokens.intersection(AVIAN_TAXA):
        return True, "curated_avian_taxon"
    return False, "unclassified_host"


def stable_tie(*parts: str) -> int:
    digest = hashlib.sha1("\t".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def date_distance_days(public_date: str, target_date: str) -> int:
    a, b = parse_date(public_date), parse_date(target_date)
    if a is None or b is None:
        return 10**9
    return abs((a - b).days)


def named_genotype(value: str) -> bool:
    text = clean(value)
    return bool(text) and text.upper() not in {"UNASSIGNED", "NOT_ASSIGNED", "NO_MATCH", "NO_MATCHING_GENOTYPES"}


def candidate_priority(row: dict, target: dict, segment: str) -> Tuple[int, int, int, int]:
    genotype = clean(row.get("genotype"))
    target_genotype = clean(target.get("genotype"))
    public_type = clean(row.get(f"{segment}_type"))
    target_type = clean((target.get("segment_calls") or {}).get(segment))

    same_genotype = bool(genotype and target_genotype and genotype == target_genotype)
    same_segment_type = bool(public_type and target_type and public_type == target_type)
    same_state = bool(clean(row.get("state")) and clean(target.get("state")) and clean(row.get("state")) == clean(target.get("state")))
    same_country = bool(normalize_country(clean(row.get("country"))) == normalize_country(clean(target.get("country"))) and clean(target.get("country")))

    if same_genotype and same_state:
        tier = 0
    elif same_genotype and same_country:
        tier = 1
    elif same_genotype:
        tier = 2
    elif same_segment_type:
        tier = 3
    else:
        tier = 4

    return (
        tier,
        date_distance_days(clean(row.get("collection_date")), clean(target.get("collection_date"))),
        0 if same_state else 1 if same_country else 2,
        stable_tie(clean(row.get("reference_id")), segment, clean(target.get("sample_id"))),
    )


def round_robin_select(
    public_rows: Sequence[dict],
    targets: Sequence[dict],
    segment: str,
    max_per_segment: int,
    same_genotype_quota: int,
    same_segment_type_quota: int,
    background_quota: int,
) -> List[Tuple[dict, str, List[str]]]:
    """Select a bounded, deterministic context set for one segment.

    Quotas are aggregate per segment, not per WINGS sample. Unique target
    genotypes and unique target segment types are round-robin balanced so an
    abundant genotype (for example D1.1) cannot consume the entire tree and
    crowd out a rarer target genotype.
    """
    selected: Dict[str, Tuple[dict, str, set[str]]] = {}

    def add(row: dict, reason: str, sample_ids: Iterable[str]) -> bool:
        acc = clean(row.get(f"{segment}_accession"))
        if not acc:
            return False
        sample_set = {clean(x) for x in sample_ids if clean(x)}
        if acc in selected:
            selected[acc][2].update(sample_set)
            return False
        selected[acc] = (row, reason, sample_set)
        return True

    # 1) Same whole-genome genotype. Balance by UNIQUE target genotype, not by
    # sample count, so many D1.1 WINGS samples do not crowd out Minor114.
    targets_by_genotype: Dict[str, List[dict]] = defaultdict(list)
    for target in targets:
        genotype = clean(target.get("genotype"))
        if genotype:
            targets_by_genotype[genotype].append(target)

    genotype_lists: Dict[str, List[dict]] = {}
    for genotype, genotype_targets in sorted(targets_by_genotype.items()):
        matches = [
            row for row in public_rows
            if clean(row.get("genotype")) == genotype
            and clean(row.get(f"{segment}_accession"))
        ]
        matches.sort(
            key=lambda row: min(candidate_priority(row, target, segment) for target in genotype_targets)
        )
        genotype_lists[genotype] = matches

    same_genotype_added = 0
    idx = 0
    genotype_names = sorted(genotype_lists)
    while same_genotype_added < same_genotype_quota and len(selected) < max_per_segment:
        progressed = False
        for genotype in genotype_names:
            rows = genotype_lists[genotype]
            while idx < len(rows):
                row = rows[idx]
                sample_ids = [t["sample_id"] for t in targets_by_genotype[genotype]]
                if add(row, "same_genotype", sample_ids):
                    same_genotype_added += 1
                    progressed = True
                    break
                idx += 1
            if same_genotype_added >= same_genotype_quota or len(selected) >= max_per_segment:
                break
        if not progressed:
            break
        idx += 1

    # 2) Same GenoFLU segment type. Again balance by UNIQUE target segment type.
    targets_by_type: Dict[str, List[dict]] = defaultdict(list)
    for target in targets:
        target_type = clean((target.get("segment_calls") or {}).get(segment))
        if target_type:
            targets_by_type[target_type].append(target)

    type_lists: Dict[str, List[dict]] = {}
    for target_type, type_targets in sorted(targets_by_type.items()):
        matches = [
            row for row in public_rows
            if clean(row.get(f"{segment}_type")) == target_type
            and clean(row.get(f"{segment}_accession"))
            and clean(row.get(f"{segment}_accession")) not in selected
        ]
        matches.sort(
            key=lambda row: min(candidate_priority(row, target, segment) for target in type_targets)
        )
        type_lists[target_type] = matches

    same_type_added = 0
    idx = 0
    type_names = sorted(type_lists)
    while same_type_added < same_segment_type_quota and len(selected) < max_per_segment:
        progressed = False
        for target_type in type_names:
            rows = type_lists[target_type]
            while idx < len(rows):
                row = rows[idx]
                sample_ids = [t["sample_id"] for t in targets_by_type[target_type]]
                if add(row, "same_segment_type", sample_ids):
                    same_type_added += 1
                    progressed = True
                    break
                idx += 1
            if same_type_added >= same_segment_type_quota or len(selected) >= max_per_segment:
                break
        if not progressed:
            break
        idx += 1

    # 3) Background. Exclude the target whole-genome genotypes themselves so
    # this category actually provides broader 2.3.4.4b context.
    target_genotypes = set(targets_by_genotype)
    remaining = [
        row for row in public_rows
        if clean(row.get(f"{segment}_accession"))
        and clean(row.get(f"{segment}_accession")) not in selected
        and named_genotype(clean(row.get("genotype")))
        and clean(row.get("genotype")) not in target_genotypes
    ]
    remaining.sort(
        key=lambda row: (
            clean(row.get("genotype")),
            clean(row.get("collection_date")),
            clean(row.get("country")),
            clean(row.get("state")),
            stable_tie(clean(row.get("reference_id")), segment),
        )
    )
    by_genotype: Dict[str, List[dict]] = defaultdict(list)
    for row in remaining:
        by_genotype[clean(row.get("genotype"))].append(row)

    background_added = 0
    idx = 0
    background_genotypes = sorted(by_genotype)
    while background_added < background_quota and len(selected) < max_per_segment:
        progressed = False
        for genotype in background_genotypes:
            rows = by_genotype[genotype]
            if idx < len(rows) and add(rows[idx], "background_genotype", []):
                background_added += 1
                progressed = True
                if background_added >= background_quota or len(selected) >= max_per_segment:
                    break
        if not progressed:
            break
        idx += 1

    # If one category is sparse, fill any unused capacity deterministically
    # without violating the primary priority order.
    if len(selected) < max_per_segment:
        leftovers = [
            row for row in public_rows
            if clean(row.get(f"{segment}_accession"))
            and clean(row.get(f"{segment}_accession")) not in selected
        ]
        leftovers.sort(
            key=lambda row: (
                0 if clean(row.get("genotype")) in target_genotypes else 1,
                clean(row.get("genotype")),
                clean(row.get("collection_date")),
                stable_tie(clean(row.get("reference_id")), segment),
            )
        )
        for row in leftovers:
            if add(row, "quota_backfill", []):
                if len(selected) >= max_per_segment:
                    break

    return [
        (row, reason, sorted(samples))
        for row, reason, samples in selected.values()
    ]

def extract_selected_fastas(fasta: Path, selected_by_segment: Dict[str, List[Tuple[dict, str, List[str]]]], output_dir: Path) -> dict:
    wanted: Dict[str, str] = {}
    for segment, items in selected_by_segment.items():
        for row, _, _ in items:
            acc = clean(row.get(f"{segment}_accession"))
            if acc:
                wanted[acc] = segment
    handles = {segment: (output_dir / f"selected_{segment}.fasta").open("w", encoding="utf-8") for segment in SEGMENTS}
    found: set[str] = set()
    try:
        for header, seq in iter_fasta(fasta):
            acc = fasta_accession(header)
            segment = wanted.get(acc)
            if segment:
                handles[segment].write(f">{acc}\n{seq}\n")
                found.add(acc)
                if len(found) == len(wanted):
                    break
    finally:
        for handle in handles.values():
            handle.close()
    return {"requested": len(wanted), "found": len(found), "missing": sorted(set(wanted) - found)}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-genotypes", required=True, type=Path, help="public_reference_genotypes.tsv")
    parser.add_argument("--results-dir", required=True, type=Path, help="WINGS results directory")
    parser.add_argument("--metadata", type=Path, help="WINGS metadata.tsv; used for date/geography prioritization")
    parser.add_argument("--fasta", type=Path, help="Public FASTA; when supplied, selected per-segment FASTAs are extracted")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--host-classification", type=Path, help="Optional TSV with columns host and is_avian")
    parser.add_argument("--max-per-segment", type=int, default=250)
    parser.add_argument("--same-genotype-quota", type=int, default=160)
    parser.add_argument("--same-segment-type-quota", type=int, default=60)
    parser.add_argument("--background-quota", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    for path, label in ((args.public_genotypes, "public genotype table"), (args.results_dir, "WINGS results directory")):
        if not path.exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            return 2
    if args.max_per_segment < 1:
        print("ERROR: --max-per-segment must be >=1", file=sys.stderr)
        return 2

    metadata_path = args.metadata
    if metadata_path is None:
        default_metadata = Path("metadata.tsv")
        if default_metadata.is_file():
            metadata_path = default_metadata
            print(f"Using WINGS metadata automatically: {metadata_path}")

    targets = load_wings_targets(args.results_dir, metadata_path)
    if not targets:
        print("ERROR: no usable WINGS GenoFLU assignments found under results/*/genoflu/GenoFLU.tsv", file=sys.stderr)
        return 2

    overrides = load_host_overrides(args.host_classification)
    public_rows_all = read_tsv(args.public_genotypes)
    public_rows: List[dict] = []
    filter_counts: Counter = Counter()
    for row in public_rows_all:
        filter_counts["input_public_genomes"] += 1
        if clean(row.get("run_status")) != "OK":
            filter_counts["excluded_genoflu_run"] += 1
            continue
        if not named_genotype(clean(row.get("genotype"))):
            filter_counts["excluded_unassigned_genotype"] += 1
            continue
        country = normalize_country(clean(row.get("country")))
        if country.upper() not in NORTH_AMERICA:
            filter_counts["excluded_non_north_american"] += 1
            continue
        avian, host_basis = classify_avian(clean(row.get("host")), overrides)
        if not avian:
            filter_counts[f"excluded_{host_basis}"] += 1
            continue
        row = dict(row)
        row["country"] = country
        row["avian_basis"] = host_basis
        public_rows.append(row)
        filter_counts["eligible_public_genomes"] += 1

    if not public_rows:
        print("ERROR: no assigned North American avian public genomes remain after filtering", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected_by_segment: Dict[str, List[Tuple[dict, str, List[str]]]] = {}
    output_rows: List[dict] = []

    for segment in SEGMENTS:
        items = round_robin_select(
            public_rows,
            targets,
            segment,
            args.max_per_segment,
            args.same_genotype_quota,
            args.same_segment_type_quota,
            args.background_quota,
        )
        selected_by_segment[segment] = items
        accessions: List[str] = []
        for row, reason, samples in items:
            acc = clean(row.get(f"{segment}_accession"))
            if not acc:
                continue
            accessions.append(acc)
            output_rows.append(
                {
                    "segment": segment,
                    "accession": acc,
                    "reference_id": clean(row.get("reference_id")),
                    "isolate": clean(row.get("isolate")),
                    "host": clean(row.get("host")),
                    "collection_date": clean(row.get("collection_date")),
                    "country": clean(row.get("country")),
                    "state": clean(row.get("state")),
                    "genotype": clean(row.get("genotype")),
                    "segment_type": clean(row.get(f"{segment}_type")),
                    "selection_reason": reason,
                    "target_samples": ",".join(samples),
                    "avian_basis": clean(row.get("avian_basis")),
                }
            )
        (args.output_dir / f"selected_{segment}.txt").write_text("\n".join(accessions) + ("\n" if accessions else ""), encoding="utf-8")

    fields = (
        "segment", "accession", "reference_id", "isolate", "host", "collection_date",
        "country", "state", "genotype", "segment_type", "selection_reason",
        "target_samples", "avian_basis",
    )
    write_tsv(args.output_dir / "selected_references.tsv", fields, output_rows)

    extraction = None
    if args.fasta:
        if not args.fasta.is_file():
            print(f"ERROR: public FASTA not found: {args.fasta}", file=sys.stderr)
            return 2
        extraction = extract_selected_fastas(args.fasta, selected_by_segment, args.output_dir)
        if extraction["missing"]:
            (args.output_dir / "missing_selected_accessions.txt").write_text("\n".join(extraction["missing"]) + "\n", encoding="utf-8")

    target_summary = []
    for target in targets:
        target_summary.append(
            {
                "sample_id": target["sample_id"],
                "genotype": target["genotype"],
                "segment_calls": target["segment_calls"],
                "collection_date": target["collection_date"],
                "country": target["country"],
                "state": target["state"],
            }
        )

    summary = {
        "schema_version": 2,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_strategy": [
            "same whole-genome GenoFLU genotype",
            "same GenoFLU segment type for the segment tree",
            "assigned North American avian background genotypes",
        ],
        "targets": target_summary,
        "metadata_file": str(metadata_path.resolve()) if metadata_path else "",
        "filter_counts": dict(filter_counts),
        "selected_counts": {segment: len(selected_by_segment[segment]) for segment in SEGMENTS},
        "selected_reason_counts": dict(Counter(row["selection_reason"] for row in output_rows)),
        "parameters": {
            "max_per_segment": args.max_per_segment,
            "same_genotype_quota": args.same_genotype_quota,
            "same_segment_type_quota": args.same_segment_type_quota,
            "background_quota": args.background_quota,
        },
        "fasta_extraction": extraction,
        "notes": [
            "Whole-genome genotype is taken from GenoFLU; it is not inferred from HA clade alone.",
            "Only public genomes with a named GenoFLU genotype are used by default.",
            "Unknown host taxa are excluded unless classified as avian through --host-classification.",
            "Selection is deterministic for identical inputs and parameters.",
            "Selection quotas are aggregate per segment and balanced across unique target genotypes/segment types.",
        ],
    }
    (args.output_dir / "selection_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("WINGS target genotypes:")
    for target in targets:
        print(f"  {target['sample_id']}: {target['genotype'] or 'UNASSIGNED'}")
    print("Selected references per segment:")
    for segment in SEGMENTS:
        print(f"  {segment}: {len(selected_by_segment[segment])}")
    print(f"Wrote: {args.output_dir / 'selected_references.tsv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
