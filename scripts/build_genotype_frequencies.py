#!/usr/bin/env python3
"""Build descriptive genotype frequencies from public metadata, never sequences."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import urllib.request

SCHEMA = "wings.genotype-frequencies.v1"
REPOSITORY = "andersen-lab/avian-influenza"
SOURCE_FILES = ("genoflu_results.tsv", "SraRunTable_automated_normalized.tsv")
MISSING = {"", "na", "n/a", "nan", "none", "null", "missing", "not provided", "not collected", "not applicable", "unknown"}


def read_table(data: bytes, required: tuple[str, ...]) -> list[dict]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter="\t", strict=True)
    fields = reader.fieldnames or []
    if len(fields) != len(set(fields)) or not set(required).issubset(fields):
        raise ValueError(f"Expected unique columns including {required}; found {fields}")
    rows = []
    for index, row in enumerate(reader, 2):
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f"Malformed TSV row {index}")
        rows.append({k: v.strip() for k, v in row.items()})
    if not rows:
        raise ValueError("Input table has no records")
    return rows


def collection_month(value: str) -> str | None:
    """Keep day/month precision; never invent a month for a year-only date."""
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}", value):
        try:
            date.fromisoformat(value + "-01")
            return value
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value).isoformat()[:7]
        except ValueError:
            return None
    return None


def call_status(value: str) -> tuple[str, str | None]:
    if value.lower() in MISSING:
        return "missing_call", None
    if value.lower().startswith("not assigned") or value.lower() == "unassigned":
        return "unassigned", None
    if not re.fullmatch(r"(?:[A-Z]\d+(?:\.\d+)*|Minor\d+)", value):
        return "unrecognized_call", None
    return "assigned", value


def genotype_index(rows: list[dict]) -> tuple[dict, dict]:
    grouped = defaultdict(list)
    for row in rows:
        if not row["sample"]:
            raise ValueError("Genotype row has no sample key")
        grouped[row["sample"]].append(row)
    index = {}
    for key, records in grouped.items():
        calls = {call_status(r["Genotype"]) for r in records}
        index[key] = next(iter(calls)) if len(calls) == 1 else ("conflicting_calls", None)
    return index, {"genotype_rows": len(rows), "unique_genotype_runs": len(index),
                   "duplicate_genotype_rows_collapsed": len(rows) - len(index),
                   "runs_with_conflicting_calls": sum(v[0] == "conflicting_calls" for v in index.values())}


def text_value(value: str) -> str:
    return "Not recorded" if value.lower() in MISSING or not value.strip("/") else value


def build_snapshot(genotype_rows: list[dict], metadata_rows: list[dict] | None = None,
                   *, date_column: str = "Collection_Date", host_column: str = "Host",
                   location_column: str = "geo_loc_name") -> dict:
    calls, audit = genotype_index(genotype_rows)
    metadata = {}
    if metadata_rows is not None:
        # Identical repeats may collapse; conflicting metadata must be resolved.
        for row in metadata_rows:
            key = row["Run"]
            if not key:
                raise ValueError("Metadata row has no Run key")
            values = (row[date_column], row.get(host_column, ""), row.get(location_column, ""))
            if key in metadata and metadata[key] != values:
                raise ValueError(f"Conflicting collection metadata for Run {key}")
            metadata[key] = values
        keys = sorted(metadata)
        audit.update(metadata_rows=len(metadata_rows), unique_metadata_runs=len(keys),
                     duplicate_metadata_rows_collapsed=len(metadata_rows) - len(keys),
                     genotype_runs_outside_metadata=len(set(calls) - set(metadata)),
                     metadata_runs_without_genotype_result=len(set(metadata) - set(calls)))
    else:
        keys = sorted(calls)
        audit.update(metadata_rows=None, unique_metadata_runs=None,
                     duplicate_metadata_rows_collapsed=None, genotype_runs_outside_metadata=None,
                     metadata_runs_without_genotype_result=None)
    groups = Counter()
    status_counts = Counter()
    dates_missing = 0
    assigned_missing_dates = 0
    for key in keys:
        status, genotype = calls.get(key, ("no_result", None))
        raw_date, host, location = metadata.get(key, ("", "", ""))
        month = collection_month(raw_date)
        if month is None:
            dates_missing += 1
            assigned_missing_dates += status == "assigned"
        status_counts[status] += 1
        groups[(month, text_value(host), text_value(location), status, genotype)] += 1
    audit.update(included_runs=len(keys), assigned_runs=status_counts["assigned"],
                 runs_without_collection_month=dates_missing,
                 assigned_runs_without_collection_month=assigned_missing_dates,
                 status_counts=dict(sorted(status_counts.items())))
    return {"schema_version": SCHEMA, "unit": "SRA run", "has_metadata": metadata_rows is not None,
            "universe": "Metadata Run keys" if metadata_rows is not None else "Genotype sample keys",
            "join": {"metadata_key": "Run", "genotype_key": "sample", "collection_date_column": date_column if metadata_rows is not None else None},
            "audit": audit,
            "groups": [{"month": month, "host": host, "location": location, "status": status,
                        "genotype": genotype, "n": n}
                       for (month, host, location, status, genotype), n in sorted(groups.items(), key=lambda item: tuple(str(v or "") for v in item[0]))]}


def download(url: str, timeout: float = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "WINGS-genotype-frequencies"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(25_000_001)
    if len(data) > 25_000_000:
        raise ValueError("Source exceeds the 25 MB import limit")
    return data


def fetch_sources(ref: str, timeout: float = 120) -> tuple[dict, str]:
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", ref):
        raise ValueError("Invalid source ref")
    # Resolve once so the two tables always come from the same immutable commit.
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        commit = json.loads(download(f"https://api.github.com/repos/{REPOSITORY}/commits/{ref}", timeout=timeout))
        ref = commit["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("Could not resolve an immutable source commit")
    data = {name: download(f"https://raw.githubusercontent.com/{REPOSITORY}/{ref}/metadata/{name}", timeout=timeout) for name in SOURCE_FILES}
    return data, ref


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--genoflu", type=Path, help="Local genoflu_results.tsv")
    source.add_argument("--fetch", action="store_true", help="Download both public tables from one source commit")
    parser.add_argument("--metadata", type=Path, help="Optional local normalized metadata TSV")
    parser.add_argument("--ref", default="master", help="Source ref for --fetch; resolved to a commit before downloading")
    parser.add_argument("--date-column", default="Collection_Date")
    parser.add_argument("--host-column", default="Host")
    parser.add_argument("--location-column", default="geo_loc_name")
    parser.add_argument("--output", type=Path, default=Path("assets/data/genotype-frequencies.json"))
    args = parser.parse_args(argv)
    try:
        if args.fetch and args.metadata:
            raise ValueError("Use --fetch for both public tables, or --genoflu with --metadata for local files")
        sources = []
        if args.fetch:
            data, ref = fetch_sources(args.ref)
            genotype_data, metadata_data = (data[name] for name in SOURCE_FILES)
            for name in SOURCE_FILES:
                sources.append({"name": name, "sha256": hashlib.sha256(data[name]).hexdigest(),
                                "url": f"https://github.com/{REPOSITORY}/blob/{ref}/metadata/{name}"})
        else:
            genotype_data = args.genoflu.read_bytes()
            metadata_data = args.metadata.read_bytes() if args.metadata else None
            ref = None
            for path, content in [(args.genoflu, genotype_data), (args.metadata, metadata_data)]:
                if path:
                    sources.append({"name": path.name, "sha256": hashlib.sha256(content).hexdigest(), "url": None})
        g = read_table(genotype_data, ("sample", "Genotype"))
        m = read_table(metadata_data, ("Run", args.date_column)) if metadata_data is not None else None
        snapshot = build_snapshot(g, m, date_column=args.date_column, host_column=args.host_column, location_column=args.location_column)
        snapshot.update(built_at=datetime.now(timezone.utc).isoformat(), source_commit=ref,
                        source_repository=f"https://github.com/{REPOSITORY}", sources=sources)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent, delete=False) as stream:
            tmp = Path(stream.name)
            json.dump(snapshot, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
        tmp.replace(args.output)
    except (ValueError, OSError, csv.Error, KeyError) as exc:
        parser.exit(1, f"Genotype frequency import failed: {exc}\n")
    print(f"Wrote {args.output}: {snapshot['audit']['included_runs']:,} runs; {snapshot['audit']['assigned_runs']:,} assigned")
    if not snapshot["has_metadata"]:
        print("Collection metadata not supplied: overall frequencies only; monthly view unavailable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
