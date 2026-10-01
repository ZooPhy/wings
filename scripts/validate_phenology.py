#!/usr/bin/env python3
"""Validate a WINGS wings.phenology.v1 snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date
from pathlib import Path


def iso(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(data: dict, metadata: Path | None = None) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "wings.phenology.v1":
        errors.append('schema_version must be "wings.phenology.v1"')
    if not isinstance(data.get("synthetic"), bool):
        errors.append("synthetic must be boolean")
    profiles = data.get("profiles")
    statuses = data.get("sample_status")
    if not isinstance(profiles, list):
        errors.append("profiles must be an array")
        profiles = []
    if statuses is not None and not isinstance(statuses, list):
        errors.append("sample_status must be an array")
        statuses = []

    ids = set()
    for i, p in enumerate(profiles):
        label = p.get("profile_id") or f"profiles[{i}]"
        if not isinstance(p.get("profile_id"), str) or not p["profile_id"].strip():
            errors.append(f"{label}: nonempty profile_id required")
        elif p["profile_id"] in ids:
            errors.append(f"{label}: duplicate profile_id")
        else:
            ids.add(p["profile_id"])
        if not isinstance(p.get("sample_id"), str) or not p["sample_id"].strip():
            errors.append(f"{label}: sample_id required for point profile")
        for field in ("host", "country", "state"):
            if not isinstance(p.get("scope", {}).get(field), str) or not p["scope"][field].strip():
                errors.append(f"{label}: scope.{field} required")
        if p.get("baseline_kind") not in {"reference_season", "year_specific"}:
            errors.append(f"{label}: invalid baseline_kind")
        if not isinstance(p.get("measure"), str) or not p["measure"].strip():
            errors.append(f"{label}: measure required")
        if not isinstance(p.get("unit"), str) or not p["unit"].strip():
            errors.append(f"{label}: unit required")
        start, end = iso(p.get("season_start")), iso(p.get("season_end"))
        if start is None or end is None or end < start:
            errors.append(f"{label}: invalid season interval")
            continue
        bins = p.get("bins")
        if not isinstance(bins, list) or len(bins) != 52:
            errors.append(f"{label}: exactly 52 bins required")
            bins = bins if isinstance(bins, list) else []
        previous = None
        for j, b in enumerate(bins):
            bs, be = iso(b.get("start")), iso(b.get("end"))
            value = b.get("value")
            if bs is None or be is None or bs > be or bs < start or be > end:
                errors.append(f"{label}: invalid bin {j+1} interval")
            if previous is not None and bs is not None and bs <= previous:
                errors.append(f"{label}: bins overlap or are unordered at {j+1}")
            if be is not None:
                previous = be
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                errors.append(f"{label}: bin {j+1} value must be nonnegative finite or null")
        anchor = p.get("anchor")
        if anchor is not None:
            a, b = iso(anchor.get("earliest")), iso(anchor.get("latest"))
            if a is None or b is None or a > b or a < start or b > end:
                errors.append(f"{label}: invalid anchor interval")
            for field in ("label", "basis"):
                if not isinstance(anchor.get(field), str) or not anchor[field].strip():
                    errors.append(f"{label}: anchor.{field} required")
        prov = p.get("provenance", {})
        for field in ("source", "citation", "retrieved_on", "method"):
            if not isinstance(prov.get(field), str) or not prov[field].strip():
                errors.append(f"{label}: provenance.{field} required")
        if prov.get("retrieved_on") and iso(prov.get("retrieved_on")) is None:
            errors.append(f"{label}: provenance.retrieved_on must be ISO date")

    if isinstance(statuses, list):
        status_ids = [s.get("sample_id") for s in statuses if isinstance(s, dict)]
        if len(status_ids) != len(set(status_ids)):
            errors.append("sample_status contains duplicate sample_id values")
        ready = {s.get("sample_id") for s in statuses if isinstance(s, dict) and s.get("status") == "READY"}
        profile_samples = {p.get("sample_id") for p in profiles}
        if ready != profile_samples:
            errors.append("READY sample_status IDs must exactly match profile sample_id values")

    if metadata is not None:
        recorded = data.get("inputs", {}).get("metadata_sha256")
        if not recorded:
            errors.append("inputs.metadata_sha256 missing")
        elif recorded != sha256(metadata):
            errors.append("phenology snapshot does not match current metadata SHA-256")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--metadata", type=Path)
    args = ap.parse_args()
    data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    errors = validate(data, args.metadata)
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print(f"PASS: {args.snapshot} is a valid wings.phenology.v1 snapshot ({len(data['profiles'])} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
