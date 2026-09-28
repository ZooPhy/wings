#!/usr/bin/env python3
r"""Summarize eBird EBD and sampling-event files around WINGS samples.

The input EBD files stay on the user's computer. Only aggregate, per-sample and
per-month checklist counts are written. These are eBird reporting frequencies,
not measures of bird abundance or infection.

Example, from the WINGS repository (using the already-filtered Kentucky files):

    python3 scripts/filter_ebird_for_wings.py \
        --metadata results/metadata/validated_metadata.tsv \
        --observations /path/to/ebd_KY_cangoo_2025_2026.txt \
        --sampling /path/to/ebd_KY_cangoo_2025_2026_sampling.txt \
        --map CAGO='Canada Goose' --days 30 \
        --release Aug-2026 --output-dir results/run_summary/ebird

The script inventories the species actually present in the EBD; it does not
assume which species the file contains. WINGS host codes are not eBird species
identifiers, so provide --map for each code unless metadata has host_species
or host_common_name. Species absent from the EBD get no reporting frequency.
For species present in the EBD, an unmatched complete checklist counts as
"not reported" only if the EBD subset includes all observation records for
that species in the matching area and period. This is not proof of absence.
"""

import argparse
import csv
import gzip
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


MISSING = {"", "NA", "N/A", "NONE", "NULL", "UNKNOWN"}
US_NAMES = {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}
CA_NAMES = {"CA", "CAN", "CANADA"}
csv.field_size_limit(10_000_000)


@dataclass(frozen=True)
class Sample:
    sample_id: str
    host: str
    species: str
    collected: date
    start: str
    end: str
    country_code: str
    country_name: str
    state: str
    latitude: float | None
    longitude: float | None
    radius_km: float | None
    status: str


def value(text):
    result = (text or "").strip()
    return "" if result.upper() in MISSING else result


def country_key(text):
    name = value(text).upper()
    if name in US_NAMES:
        return "US"
    if name in CA_NAMES:
        return "CA"
    return name


def parse_coordinate(text, lower, upper, field, sample_id):
    raw = value(text)
    if not raw:
        return None
    try:
        coordinate = float(raw)
    except ValueError as exc:
        raise ValueError(f"{sample_id}: invalid {field}: {raw!r}") from exc
    if not math.isfinite(coordinate) or not lower <= coordinate <= upper:
        raise ValueError(f"{sample_id}: {field} is out of range: {raw!r}")
    return coordinate


def tsv_rows(path, required, malformed=None, literal_quotes=False):
    # Stream large EBD .txt.gz inputs without extracting them to disk.
    opener = gzip.open if path.suffix.casefold() == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8-sig") as stream:
        # EBD records are literal tab-separated lines; quote characters in
        # free-text fields must not make the reader join adjacent records.
        reader = csv.DictReader(
            stream, delimiter="\t",
            quoting=csv.QUOTE_NONE if literal_quotes else csv.QUOTE_MINIMAL,
        )
        columns = set(reader.fieldnames or [])
        if missing := required - columns:
            raise ValueError(f"{path}: missing columns {', '.join(sorted(missing))}")
        for row in reader:
            if None in row:
                extra = row.pop(None)
                if any(cell.strip() for cell in extra):
                    if malformed is not None and len(malformed["rows"]) < malformed["limit"]:
                        malformed["rows"].append({
                            "source_file": str(path), "line": reader.line_num,
                            "extra_fields": len(extra), "reason": "nonempty extra fields",
                        })
                        continue
                    raise ValueError(
                        f"{path}: line {reader.line_num} has {len(extra)} extra "
                        f"nonempty field(s) beyond its {len(reader.fieldnames)}-column header; "
                        "check the source file, or use --max-malformed-rows to "
                        "explicitly skip and log a limited number of bad rows"
                    )
                # Some exports have an extra trailing tab. It adds no data.
            yield row


def parse_maps(entries, path=None):
    result = {}
    if path is not None:
        for row in tsv_rows(path, {"host", "ebird_species"}):
            entries.append(f"{row['host']}={row['ebird_species']}")
    for entry in entries:
        code, sep, name = entry.partition("=")
        if not sep or not value(code) or not value(name):
            raise ValueError(f"Invalid --map {entry!r}; use HOST='eBird species name'")
        code = code.strip().casefold()
        name = name.strip()
        if code in result and result[code] != name:
            raise ValueError(f"Conflicting mappings for {code!r}")
        result[code] = name
    return result


def read_samples(path, maps, days, radius_km):
    required = {"sample_id", "host", "collection_date", "country"}
    samples = []
    seen = set()
    for row in tsv_rows(path, required):
        sample_id = value(row["sample_id"])
        if not sample_id or sample_id in seen:
            raise ValueError(f"Empty or duplicate WINGS sample_id: {sample_id!r}")
        seen.add(sample_id)
        try:
            collected = date.fromisoformat(value(row["collection_date"]))
        except ValueError as exc:
            raise ValueError(f"{sample_id}: collection_date must be YYYY-MM-DD") from exc
        host = value(row["host"])
        country = value(row["country"])
        if not host or not country:
            raise ValueError(f"{sample_id}: host and country are required")

        latitude = parse_coordinate(row.get("latitude"), -90, 90, "latitude", sample_id)
        longitude = parse_coordinate(row.get("longitude"), -180, 180, "longitude", sample_id)
        if (latitude is None) != (longitude is None):
            raise ValueError(f"{sample_id}: supply both latitude and longitude")

        species = (maps.get(host.casefold()) or value(row.get("host_species"))
                   or value(row.get("host_common_name")))
        if not species and (" " in host or host.istitle() and len(host) > 4):
            species = host

        state = value(row.get("state"))
        effective_radius = radius_km if latitude is not None else None
        status = "OK"
        if not species:
            status = "UNMAPPED_HOST"
        elif not state and effective_radius is None:
            status = "NO_LOCATION"

        start = collected - timedelta(days=days)
        end = collected + timedelta(days=days)
        key = country_key(country)
        samples.append(Sample(
            sample_id, host, species, collected, start.isoformat(), end.isoformat(),
            key if len(key) == 2 else "", country.casefold(), state,
            latitude, longitude, effective_radius, status,
        ))
    if not samples:
        raise ValueError(f"No sample rows found in {path}")
    return samples


def check_cache_scope(samples, observations):
    """Fail if a new query extends beyond the original metadata cache scope."""
    manifest_path = observations.parent / "cache_manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scopes = manifest.get("coverage_scopes", [])
    if not scopes:
        raise ValueError(f"Cache manifest has no coverage scopes: {manifest_path}")
    for sample in samples:
        country = sample.country_code or sample.country_name
        matched = any(
            scope["country"].casefold() == country.casefold()
            and (not scope["state"] or scope["state"].casefold() == sample.state.casefold())
            and scope["start"] <= sample.start and sample.end <= scope["end"]
            for scope in scopes
        )
        if not matched:
            raise ValueError(f"{sample.sample_id}: location/date window is outside the "
                             f"observation cache; rebuild it for the new metadata ({manifest_path})")


def haversine_km(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    dp = b - a
    h = math.sin(dp / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, h)))


def matches(row, sample):
    when = (row.get("OBSERVATION DATE") or "")[:10]
    if not sample.start <= when <= sample.end:
        return False

    if sample.country_code:
        if value(row.get("COUNTRY CODE")).upper() != sample.country_code:
            return False
    elif value(row.get("COUNTRY")).casefold() != sample.country_name:
        return False

    if sample.state:
        state = sample.state.casefold()
        region = value(row.get("STATE CODE")).casefold()
        name = value(row.get("STATE")).casefold()
        short = region.rsplit("-", 1)[-1] if region.startswith(
            sample.country_code.casefold() + "-"
        ) else ""
        if state not in {region, name, short}:
            return False

    if sample.radius_km is not None:
        try:
            latitude = float(row["LATITUDE"])
            longitude = float(row["LONGITUDE"])
        except (TypeError, ValueError, KeyError):
            return False
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            return False
        if haversine_km(sample.latitude, sample.longitude, latitude, longitude) > sample.radius_km:
            return False
    return True


def write_tsv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def summarize(samples, observations, sampling, malformed):
    active = [s for s in samples if s.status == "OK"]
    candidates = defaultdict(list)
    for sample in active:
        for key in {sample.country_code, sample.country_name} - {""}:
            candidates[key].append(sample)

    def row_candidates(row):
        keys = {value(row.get("COUNTRY CODE")).upper(),
                value(row.get("COUNTRY")).casefold()} - {""}
        found = {}
        for key in keys:
            for sample in candidates.get(key, ()):
                found[sample.sample_id] = sample
        return found.values()

    groups = {}
    event_to_group = {}
    required_sed = {"SAMPLING EVENT IDENTIFIER", "OBSERVATION DATE", "COUNTRY CODE",
                    "COUNTRY", "STATE CODE", "STATE", "GROUP IDENTIFIER",
                    "ALL SPECIES REPORTED"}
    if any(sample.radius_km is not None for sample in active):
        required_sed.update({"LATITUDE", "LONGITUDE"})

    # Retain the smallest sampling-event ID per shared group, as auk_unique does.
    for row in tsv_rows(sampling, required_sed, malformed, literal_quotes=True):
        choices = row_candidates(row)
        if not choices or not any(matches(row, sample) for sample in choices):
            continue
        event_id = value(row["SAMPLING EVENT IDENTIFIER"])
        if not event_id:
            raise ValueError(f"{sampling}: empty SAMPLING EVENT IDENTIFIER")
        group = value(row["GROUP IDENTIFIER"]) or event_id
        event_to_group[event_id] = group
        if group not in groups or event_id < groups[group][0]:
            groups[group] = (event_id, row)

    eligible = defaultdict(list)
    denominator = defaultdict(int)
    for group, (_, row) in groups.items():
        if value(row["ALL SPECIES REPORTED"]) != "1":
            continue
        for sample in row_candidates(row):
            if matches(row, sample):
                month = row["OBSERVATION DATE"][:7]
                eligible[group].append((sample, month))
                denominator[(sample.sample_id, month)] += 1

    detected = set()
    species_counts = defaultdict(int)
    species_labels = {}
    required_ebd = {"SAMPLING EVENT IDENTIFIER", "COMMON NAME", "SCIENTIFIC NAME"}
    for row in tsv_rows(observations, required_ebd, malformed, literal_quotes=True):
        common = value(row["COMMON NAME"])
        scientific = value(row["SCIENTIFIC NAME"])
        if common or scientific:
            species_counts[(common.casefold(), scientific.casefold())] += 1
            species_labels[(common.casefold(), scientific.casefold())] = (common, scientific)
        group = event_to_group.get(value(row["SAMPLING EVENT IDENTIFIER"]))
        if group not in eligible:
            continue
        names = {common.casefold(), scientific.casefold()}
        for sample, month in eligible[group]:
            if sample.species.casefold() in names:
                detected.add((sample.sample_id, group, month))

    numerator = defaultdict(int)
    for sample_id, _, month in detected:
        numerator[(sample_id, month)] += 1
    catalog = sorted((species_labels[key][0], species_labels[key][1], count)
                     for key, count in species_counts.items())
    return denominator, numerator, catalog


def inventory_species(observations, malformed):
    """Inventory names in an EBD observation file without sampling events."""
    counts = defaultdict(int)
    labels = {}
    for row in tsv_rows(observations, {"COMMON NAME", "SCIENTIFIC NAME"},
                        malformed, literal_quotes=True):
        common = value(row["COMMON NAME"])
        scientific = value(row["SCIENTIFIC NAME"])
        if common or scientific:
            key = (common.casefold(), scientific.casefold())
            counts[key] += 1
            labels[key] = (common, scientific)
    return sorted((labels[key][0], labels[key][1], count)
                  for key, count in counts.items())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--metadata", type=Path, help="WINGS metadata.tsv or validated_metadata.tsv")
    parser.add_argument("--observations", required=True, type=Path, help="EBD observations (.txt or .txt.gz)")
    parser.add_argument("--sampling", type=Path, help="Matching sampling events (.txt or .txt.gz)")
    parser.add_argument("--species-catalog", type=Path,
                        help="Full observation-file species catalog saved by build_ebird_cache.py")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for aggregated TSVs")
    parser.add_argument("--list-species", action="store_true",
                        help="Inventory the observations without metadata or sampling events")
    parser.add_argument("--map", action="append", default=[], metavar="HOST=SPECIES",
                        help="Explicit WINGS host-code to eBird common or scientific name; repeatable")
    parser.add_argument("--host-map", type=Path,
                        help="Optional TSV with host and ebird_species columns")
    parser.add_argument("--days", type=int, default=30, help="Days before and after collection (default: 30)")
    parser.add_argument("--radius-km", type=float, help="Optional distance around sample coordinates; otherwise state only")
    parser.add_argument("--release", default="unspecified", help="EBD release label for provenance")
    parser.add_argument("--max-malformed-rows", type=int, default=0,
                        help="Explicit maximum bad EBD rows to skip and log (default: 0)")
    args = parser.parse_args(argv)
    if args.days < 0 or args.days > 365:
        parser.error("--days must be between 0 and 365")
    if args.radius_km is not None and (not math.isfinite(args.radius_km) or args.radius_km <= 0):
        parser.error("--radius-km must be a positive, finite number")
    if args.max_malformed_rows < 0:
        parser.error("--max-malformed-rows must be nonnegative")
    malformed = {"limit": args.max_malformed_rows, "rows": []}
    if args.list_species:
        try:
            catalog = inventory_species(args.observations, malformed)
            write_tsv(args.output_dir / "ebird_species.tsv",
                      ["common_name", "scientific_name", "observation_rows"],
                      ({"common_name": common, "scientific_name": scientific,
                        "observation_rows": count} for common, scientific, count in catalog))
            write_tsv(args.output_dir / "ebird_malformed_rows.tsv",
                      ["source_file", "line", "extra_fields", "reason"], malformed["rows"])
        except (ValueError, OSError, EOFError, csv.Error) as exc:
            parser.exit(1, f"eBird inventory failed: {exc}\n")
        print(f"Found {len(catalog)} distinct eBird taxa in {args.observations}; "
              f"saved to {args.output_dir / 'ebird_species.tsv'}")
        if malformed["rows"]:
            print(f"WARNING: skipped {len(malformed['rows'])} malformed row(s); "
                  f"see {args.output_dir / 'ebird_malformed_rows.tsv'}", file=sys.stderr)
        return
    if args.metadata is None or args.sampling is None:
        parser.error("--metadata and --sampling are required unless --list-species is set")
    try:
        samples = read_samples(args.metadata, parse_maps(args.map, args.host_map), args.days,
                               args.radius_km)
        if args.species_catalog is not None:
            check_cache_scope(samples, args.observations)
        denominator, numerator, catalog = summarize(
            samples, args.observations, args.sampling, malformed
        )
    except (ValueError, OSError, csv.Error) as exc:
        parser.exit(1, f"eBird filtering failed: {exc}\n")

    base = {"source": "eBird Basic Dataset", "release": args.release,
            "date_window_days": args.days}
    monthly = []
    summary = []
    if args.species_catalog is not None:
        catalog = [(value(row["common_name"]), value(row["scientific_name"]),
                    row["observation_rows"])
                   for row in tsv_rows(args.species_catalog,
                                       {"common_name", "scientific_name", "observation_rows"})]
    available = {name.casefold() for common, scientific, _ in catalog
                 for name in (common, scientific) if name}
    for sample in samples:
        species_in_input = sample.species.casefold() in available if sample.species else False
        total = positive = 0
        for (sample_id, month), count in sorted(denominator.items()):
            if sample_id != sample.sample_id:
                continue
            n = numerator[(sample_id, month)]
            total += count
            positive += n
            monthly.append({**base, "sample_id": sample_id, "host": sample.host,
                            "ebird_species": sample.species, "month": month,
                            "complete_checklists": count,
                            "reporting_checklists": n if species_in_input else "",
                            "reporting_frequency": f"{n / count:.6f}" if species_in_input else "",
                            "species_in_input": int(species_in_input)})
        status = (sample.status if sample.status != "OK" else
                  "SPECIES_NOT_IN_INPUT" if not species_in_input else
                  "READY" if total else "NO_CHECKLISTS")
        summary.append({**base, "sample_id": sample.sample_id, "host": sample.host,
                        "ebird_species": sample.species, "collection_date": sample.collected,
                        "country": sample.country_code or sample.country_name,
                        "state": sample.state, "radius_km": sample.radius_km or "",
                        "date_from": sample.start, "date_to": sample.end,
                        "complete_checklists": total,
                        "reporting_checklists": positive if species_in_input else "",
                        "reporting_frequency": f"{positive / total:.6f}" if total and species_in_input else "",
                        "species_in_input": int(species_in_input), "status": status})

    output = args.output_dir
    write_tsv(output / "ebird_samples.tsv",
              ["sample_id", "host", "ebird_species", "collection_date", "country", "state",
               "radius_km", "date_from", "date_to", "complete_checklists",
               "reporting_checklists", "reporting_frequency", "species_in_input",
               "status", "source", "release",
               "date_window_days"], summary)
    write_tsv(output / "ebird_monthly.tsv",
              ["sample_id", "host", "ebird_species", "month", "complete_checklists",
               "reporting_checklists", "reporting_frequency", "species_in_input",
               "source", "release",
               "date_window_days"], monthly)
    write_tsv(output / "ebird_species.tsv",
              ["common_name", "scientific_name", "observation_rows"],
              ({"common_name": common, "scientific_name": scientific,
                "observation_rows": count} for common, scientific, count in catalog))
    write_tsv(output / "ebird_malformed_rows.tsv",
              ["source_file", "line", "extra_fields", "reason"], malformed["rows"])
    print(f"Wrote {len(summary)} sample summaries, {len(monthly)} monthly rows, "
          f"and {len(catalog)} input taxa to {output}")
    if malformed["rows"]:
        print(f"WARNING: skipped {len(malformed['rows'])} malformed EBD row(s); "
              f"see {output / 'ebird_malformed_rows.tsv'}", file=sys.stderr)
    for status in sorted({row["status"] for row in summary}):
        print(f"  {status}: {sum(row['status'] == status for row in summary)}", file=sys.stderr)


if __name__ == "__main__":
    main()
