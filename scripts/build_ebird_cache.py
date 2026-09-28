#!/usr/bin/env python3
"""Cache original eBird records for WINGS metadata regions and dates locally.

The input observations are scanned once. A global species inventory is built
during that scan, while observations in the metadata's regions and date windows
are written to the cache. The cached EBD rows remain original eBird data: never
commit, publish, or add this directory to a WINGS report bundle.
"""

import argparse
import csv
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from filter_ebird_for_wings import matches, read_samples, tsv_rows, value, write_tsv


def input_lines(path):
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    return opener(path, "rt", encoding="utf-8-sig", newline="")


def scan_sampling(path, samples, output, event_ids):
    required = {"SAMPLING EVENT IDENTIFIER", "OBSERVATION DATE", "COUNTRY CODE",
                "COUNTRY", "STATE CODE", "STATE", "GROUP IDENTIFIER",
                "ALL SPECIES REPORTED"}
    # Ignore radius here so the cache can serve any radius within these regions.
    regions = [replace(s, radius_km=None) for s in samples]
    count = 0
    with output.open("wt", encoding="utf-8", newline="") as writer:
        # Preserve the original columns (including those needed for radius queries).
        with input_lines(path) as stream:
            header = stream.readline()
            if not header:
                raise ValueError(f"Empty sampling file: {path}")
            columns = header.rstrip("\r\n").split("\t")
            missing = required - set(columns)
            if missing:
                raise ValueError(f"{path}: missing columns {', '.join(sorted(missing))}")
            idx = {name: columns.index(name) for name in required}
            writer.write(header)
            for line_no, line in enumerate(stream, 2):
                fields = line.rstrip("\r\n").split("\t")
                if len(fields) > len(columns) and any(f.strip() for f in fields[len(columns):]):
                    raise ValueError(f"{path}: line {line_no} has extra nonempty fields")
                if len(fields) < len(columns):
                    fields.extend([""] * (len(columns) - len(fields)))
                row = {name: fields[pos] for name, pos in idx.items()}
                if any(matches(row, s) for s in regions):
                    event_id = value(row["SAMPLING EVENT IDENTIFIER"])
                    if not event_id:
                        raise ValueError(f"{path}: line {line_no} has no sampling event ID")
                    event_ids.add(event_id)
                    writer.write(line)
                    count += 1
    return count


def scan_observations(path, event_ids, samples, output, catalog_output):
    counts = defaultdict(int)
    labels = {}
    count = 0
    with input_lines(path) as stream, gzip.open(output, "wt", compresslevel=1,
                                                 encoding="utf-8", newline="") as writer:
        header = stream.readline()
        if not header:
            raise ValueError(f"Empty observation file: {path}")
        columns = header.rstrip("\r\n").split("\t")
        required = {"SAMPLING EVENT IDENTIFIER", "COMMON NAME", "SCIENTIFIC NAME"}
        if event_ids is None:
            required.update({"OBSERVATION DATE", "COUNTRY CODE", "COUNTRY",
                             "STATE CODE", "STATE"})
        missing = required - set(columns)
        if missing:
            raise ValueError(f"{path}: missing columns {', '.join(sorted(missing))}")
        event_col = columns.index("SAMPLING EVENT IDENTIFIER")
        common_col = columns.index("COMMON NAME")
        scientific_col = columns.index("SCIENTIFIC NAME")
        scope_cols = {name: columns.index(name) for name in required}
        regions = [replace(s, radius_km=None) for s in samples]
        min_date = min(s.start for s in samples)
        max_date = max(s.end for s in samples)
        countries = {s.country_code for s in samples if s.country_code}
        writer.write(header)
        for line_no, line in enumerate(stream, 2):
            fields = line.rstrip("\r\n").split("\t")
            if len(fields) > len(columns) and any(f.strip() for f in fields[len(columns):]):
                raise ValueError(f"{path}: line {line_no} has extra nonempty fields")
            if len(fields) < len(columns):
                fields.extend([""] * (len(columns) - len(fields)))
            common = value(fields[common_col])
            scientific = value(fields[scientific_col])
            if common or scientific:
                key = (common.casefold(), scientific.casefold())
                counts[key] += 1
                labels[key] = (common, scientific)
            if event_ids is not None:
                selected = value(fields[event_col]) in event_ids
            else:
                # The sampling-event download can be attached later. Use the
                # observation's own location and date fields for this scan.
                when = fields[scope_cols["OBSERVATION DATE"]][:10]
                country = fields[scope_cols["COUNTRY CODE"]].strip().upper()
                selected = (min_date <= when <= max_date and
                            (not countries or country in countries) and
                            any(matches({name: fields[idx] for name, idx in scope_cols.items()}, s)
                                for s in regions))
            if selected:
                writer.write(line)
                count += 1
            if line_no % 1_000_000 == 0:
                print(f"Scanned {line_no - 1:,} observation records; cached {count:,}",
                      file=sys.stderr, flush=True)
    catalog = ((labels[key][0], labels[key][1], n) for key, n in sorted(counts.items()))
    write_tsv(catalog_output, ["common_name", "scientific_name", "observation_rows"],
              ({"common_name": common, "scientific_name": scientific,
                "observation_rows": n} for common, scientific, n in catalog))
    return count, len(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--sampling", type=Path)
    parser.add_argument("--sampling-only", action="store_true",
                        help="Add matching sampling events to an existing observation cache")
    parser.add_argument("--replace-sampling", action="store_true",
                        help="Replace a cached sampling file without rescanning observations")
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    if not args.sampling_only and args.observations is None:
        parser.error("--observations is required when building the cache")
    if args.sampling_only and args.sampling is None:
        parser.error("--sampling is required with --sampling-only")
    if args.replace_sampling and not args.sampling_only:
        parser.error("--replace-sampling requires --sampling-only")
    if not 0 <= args.days <= 365:
        parser.error("--days must be between 0 and 365")
    repo_root = Path(__file__).resolve().parent.parent
    dest = args.cache_dir.resolve()
    if dest == repo_root or repo_root in dest.parents:
        parser.error("Keep original eBird cache records outside the WINGS repository")
    if (args.observations and dest == args.observations.resolve().parent or
        args.sampling and dest == args.sampling.resolve().parent):
        parser.error("Cache directory must differ from source directories")
    dest.mkdir(parents=True, exist_ok=True)
    sampling = dest / "sampling.txt"
    observations = dest / "observations.txt.gz"
    catalog = dest / "species_catalog.tsv"
    tmp_sampling = dest / "sampling.txt.tmp"
    tmp_observations = dest / "observations.txt.gz.tmp"
    tmp_catalog = dest / "species_catalog.tsv.tmp"
    if args.sampling_only:
        if not observations.is_file() or not catalog.is_file():
            parser.error("Build the observation cache before adding sampling events")
        if sampling.exists() and not args.replace_sampling:
            parser.error("sampling.txt already exists; use --replace-sampling to update it")
    elif any(p.exists() for p in (sampling, observations, catalog, dest / "cache_manifest.json")):
        parser.error("Cache already exists; use a new cache directory for a new scope or release")
    # Use the existing metadata parser to validate dates/countries. Cache all
    # observed taxa for the regions, independent of today's WINGS host mapping.
    try:
        samples = read_samples(args.metadata, {}, args.days, None)
        fingerprint = hashlib.sha256(args.metadata.read_bytes()).hexdigest()
        if args.sampling_only:
            manifest = json.loads((dest / "cache_manifest.json").read_text())
            if manifest["metadata_sha256"] != fingerprint or manifest["days"] != args.days:
                raise ValueError("Metadata or --days differ from the observation cache scope")
            sed_count = scan_sampling(args.sampling, samples, tmp_sampling, set())
            tmp_sampling.replace(sampling)
            sampling_manifest = {
                "source_sampling": str(args.sampling.resolve()),
                "metadata_sha256": fingerprint,
                "days": args.days,
                "sampling_rows": sed_count,
            }
            (dest / "sampling_manifest.json").write_text(
                json.dumps(sampling_manifest, indent=2) + "\n")
            obs_count, taxa_count = manifest["observation_rows"], manifest["species"]
        else:
            event_ids = set() if args.sampling else None
            if args.sampling:
                sed_count = scan_sampling(args.sampling, samples, tmp_sampling, event_ids)
            else:
                sed_count = 0
            print(f"Matched {sed_count:,} sampling events; scanning observations once...", flush=True)
            obs_count, taxa_count = scan_observations(args.observations, event_ids,
                                                      samples, tmp_observations, tmp_catalog)
            # Each file is promoted only after the full observations scan succeeds.
            tmp_observations.replace(observations)
            tmp_catalog.replace(catalog)
            if args.sampling:
                tmp_sampling.replace(sampling)
            manifest = {
                "source_observations": str(args.observations.resolve()),
                "source_sampling": str(args.sampling.resolve()) if args.sampling else None,
                "metadata_sha256": fingerprint,
                "coverage_scopes": [
                    {"country": s.country_code or s.country_name,
                     "state": s.state, "start": s.start, "end": s.end}
                    for s in samples
                ],
                "days": args.days, "sampling_rows": sed_count,
                "observation_rows": obs_count, "species": taxa_count,
                "scope": "Metadata country/state/date windows; all observed species; no radius restriction",
            }
            (dest / "cache_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    except (OSError, EOFError, ValueError, csv.Error) as exc:
        parser.exit(1, f"eBird cache failed: {exc}\n")
    print(f"Cache ready: {sed_count:,} sampling events, {obs_count:,} observations, "
          f"{taxa_count:,} taxa in {dest}")


if __name__ == "__main__":
    main()
