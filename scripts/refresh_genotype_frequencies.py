#!/usr/bin/env python3
"""Refresh public genotype metadata when stale, retaining a validated cached copy."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import urllib.error

from build_genotype_frequencies import (
    REPOSITORY, SCHEMA, SOURCE_FILES, build_snapshot, collection_month,
    fetch_sources, read_table,
)


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_snapshot(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA or data.get("unit") != "SRA run":
        raise ValueError("Expected a public genotype-frequency snapshot")
    if not isinstance(data.get("has_metadata"), bool) or not isinstance(data.get("groups"), list):
        raise ValueError("Missing public snapshot metadata or groups")
    total = assigned = 0
    statuses = {"assigned", "unassigned", "no_result", "missing_call", "conflicting_calls", "unrecognized_call"}
    for group in data["groups"]:
        if not isinstance(group, dict) or type(group.get("n")) is not int or group["n"] <= 0 or group.get("status") not in statuses:
            raise ValueError("Invalid snapshot count or status")
        if not all(isinstance(group.get(key), str) and len(group[key]) <= 1000 for key in ("host", "location")):
            raise ValueError("Invalid snapshot metadata")
        month = group.get("month")
        if month is not None and (not isinstance(month, str) or collection_month(month) != month or not data["has_metadata"]):
            raise ValueError("Invalid snapshot collection month")
        call = group.get("genotype")
        if group["status"] == "assigned":
            if not isinstance(call, str) or not call.strip() or len(call) > 100:
                raise ValueError("Invalid recorded genotype")
            assigned += group["n"]
        elif call is not None:
            raise ValueError("Unavailable assignments must not contain a genotype")
        total += group["n"]
    audit = data.get("audit", {})
    if not isinstance(audit, dict) or audit.get("included_runs") != total or audit.get("assigned_runs") != assigned:
        raise ValueError("Snapshot counts do not reconcile")
    return data


def timestamp(data: dict):
    value = data.get("fetched_at") or data.get("built_at")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def refresh(seed: Path, cache_dir: Path, *, ref="master", max_age_days=7,
            offline=False, force=False, timeout=20, now=None) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", ref):
        raise ValueError("Invalid public source ref")
    if not math.isfinite(max_age_days) or max_age_days < 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Use a nonnegative maximum age and a positive timeout")
    now = now or datetime.now(timezone.utc)
    pinned = bool(re.fullmatch(r"[0-9a-f]{40}", ref))
    cache = cache_dir.expanduser() / ("frequencies-" + hashlib.sha256(ref.encode()).hexdigest()[:16] + ".json")
    candidates = []
    for path in (cache, seed):
        try:
            data = validate_snapshot(json.loads(path.read_text(encoding="utf-8")))
            if pinned and data.get("source_commit") != ref:
                continue
            if not pinned and data.get("source_ref", "master") != ref:
                continue
            candidates.append(data)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    fallback = max(candidates, key=lambda d: timestamp(d) or datetime.min.replace(tzinfo=timezone.utc)) if candidates else None

    def report(data, status, note):
        result = dict(data)
        result["report_refresh"] = {"status": status, "checked_at": now.isoformat(),
                                    "source_ref": ref, "max_age_days": max_age_days, "note": note}
        return result

    if offline:
        if not candidates:
            raise ValueError("Offline mode needs a valid saved public snapshot matching the requested ref")
        # An explicitly supplied seed takes precedence over a newer cache offline.
        return report(candidates[-1], "offline", "Using the saved snapshot; no network request was made.")
    fetched = timestamp(fallback) if fallback else None
    fresh = fetched is not None and 0 <= (now - fetched).total_seconds() <= max_age_days * 86400
    if fallback is not None and not force and (pinned or fresh):
        return report(fallback, "pinned" if pinned else "cached", "Using the saved snapshot; no network request was needed.")
    try:
        tables, commit = fetch_sources(ref, timeout=timeout)
        g = read_table(tables[SOURCE_FILES[0]], ("sample", "Genotype"))
        m = read_table(tables[SOURCE_FILES[1]], ("Run", "Collection_Date"))
        data = build_snapshot(g, m)
        data.update(built_at=now.isoformat(), fetched_at=now.isoformat(), source_ref=ref,
                    source_commit=commit, source_repository=f"https://github.com/{REPOSITORY}",
                    sources=[{"name": name, "sha256": hashlib.sha256(tables[name]).hexdigest(),
                              "url": f"https://github.com/{REPOSITORY}/blob/{commit}/metadata/{name}"}
                             for name in SOURCE_FILES])
        validate_snapshot(data)
        atomic_json(cache, data)
        return report(data, "updated", "Downloaded both public metadata tables from the same source commit.")
    except (OSError, ValueError, KeyError, TypeError, csv.Error, urllib.error.URLError) as error:
        if fallback is None:
            raise ValueError(f"Public refresh failed and no valid saved snapshot is available: {error}") from error
        return report(fallback, "fallback", "Refresh was unavailable; the last valid saved snapshot was retained. " + str(error))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=Path("assets/data/genotype-frequencies.json"))
    parser.add_argument("--output", type=Path, default=Path("assets/data/genotype-frequencies.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("~/.cache/wings/genotype-frequencies"))
    parser.add_argument("--ref", default="master")
    parser.add_argument("--max-age-days", type=float, default=7)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = refresh(args.seed, args.cache_dir, ref=args.ref, max_age_days=args.max_age_days,
                       offline=args.offline, force=args.force, timeout=args.timeout)
        atomic_json(args.output, data)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Genotype refresh failed: {error}\n")
    print(f"Public genotype snapshot {data['report_refresh']['status']}: {args.output}")
    print(data["report_refresh"]["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
