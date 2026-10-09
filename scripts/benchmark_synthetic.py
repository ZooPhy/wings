#!/usr/bin/env python3
"""Measure a deterministic, non-biological workload with Python's standard library."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "WINGS_SYNTHETIC_BENCHMARK_V1"
WORKLOAD = "integer-sort-sha256-v1"


def synthetic_workload(items: int, seed: int) -> str:
    """Generate, sort, and hash integers; no files or biological data are read."""
    values = []
    state = seed
    for _ in range(items):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        values.append(state)
    values.sort()
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack("<I", value))
    return digest.hexdigest()


def measure(items: int, seed: int) -> dict:
    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    checksum = synthetic_workload(items, seed)
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    peak_bytes = None
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            peak_bytes = int(rss)
        elif sys.platform.startswith("linux"):
            peak_bytes = int(rss * 1024)
    except ImportError:
        pass
    return {"wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds,
            "peak_rss_bytes": peak_bytes, "output_sha256": checksum}


def environment() -> dict:
    return {"python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "logical_cpu_count": os.cpu_count()}


def validate_settings(items: int, seed: int, repeats: int, warmups: int) -> None:
    if not 1 <= items <= 5_000_000:
        raise ValueError("items must be between 1 and 5,000,000")
    if not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("seed must be between 0 and 4,294,967,295")
    if not 1 <= repeats <= 50 or not 0 <= warmups <= 5:
        raise ValueError("repeats must be 1–50 and warmups must be 0–5")


def benchmark(items: int, seed: int, repeats: int, warmups: int, label: str) -> dict:
    validate_settings(items, seed, repeats, warmups)
    rows = []
    checksums = set()
    for index in range(warmups + repeats):
        # A fresh process gives each repeat its own memory high-water mark.
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "_worker",
             "--items", str(items), "--seed", str(seed)],
            check=True, capture_output=True, text=True, timeout=300,
        )
        row = json.loads(result.stdout)
        checksums.add(row["output_sha256"])
        if index >= warmups:
            rows.append(row)
    if len(checksums) != 1:
        raise ValueError("Output checksums differed across repeats or warmups")
    return {"format": FORMAT, "label": label,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "settings": {"workload": WORKLOAD, "items": items, "seed": seed,
                         "repeats": repeats, "warmups": warmups},
            "environment": environment(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "runs": rows, "summary": summarize(rows)}


def summarize(rows: list[dict]) -> dict:
    summary = {"output_sha256": rows[0]["output_sha256"]}
    for key in ("wall_seconds", "cpu_seconds", "peak_rss_bytes"):
        values = [row[key] for row in rows]
        summary[key] = None if any(v is None for v in values) else {
            "median": statistics.median(values), "min": min(values), "max": max(values)}
    return summary


def validate_report(report: dict) -> None:
    if report.get("format") != FORMAT:
        raise ValueError("Unrecognized benchmark report format")
    settings = report["settings"]
    if settings["workload"] != WORKLOAD:
        raise ValueError("Unsupported synthetic workload")
    validate_settings(settings["items"], settings["seed"], settings["repeats"], settings["warmups"])
    rows = report["runs"]
    if not rows or len(rows) != settings["repeats"]:
        raise ValueError("Run count does not match settings")
    for row in rows:
        digest = row["output_sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid output checksum")
        for key in ("wall_seconds", "cpu_seconds", "peak_rss_bytes"):
            value = row[key]
            if key == "peak_rss_bytes" and value is None:
                continue
            if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid measurement: {key}")
    if len({row["output_sha256"] for row in rows}) != 1:
        raise ValueError("Output checksums differ within a report")


def compare(baseline: dict, candidate: dict) -> dict:
    for report in (baseline, candidate):
        validate_report(report)
    if baseline["settings"] != candidate["settings"]:
        raise ValueError("Use identical workload, items, seed, repeats, and warmups")
    # Recompute summaries from recorded measurements, not editable summary fields.
    before, after = summarize(baseline["runs"]), summarize(candidate["runs"])
    if before["output_sha256"] != after["output_sha256"]:
        raise ValueError("Output checksums differ; performance comparison rejected")
    ratios = {}
    for key in ("wall_seconds", "cpu_seconds", "peak_rss_bytes"):
        a, b = before[key], after[key]
        ratios[key] = b["median"] / a["median"] if a and b and a["median"] > 0 else None
    env_a, env_b = baseline["environment"], candidate["environment"]
    differences = {key: {"baseline": env_a.get(key), "candidate": env_b.get(key)}
                   for key in sorted(set(env_a) | set(env_b)) if env_a.get(key) != env_b.get(key)}
    return {"baseline": baseline.get("label"), "candidate": candidate.get("label"),
            "output_checksums_match": True, "baseline_summary": before, "candidate_summary": after,
            "candidate_over_baseline_median": ratios, "environment_differences": differences,
            "script_changed": baseline.get("script_sha256") != candidate.get("script_sha256"),
            "interpretation": "Ratios below 1 mean lower measured time or memory. Compare ranges and repeat measurements; this is not a significance test or an IRMA benchmark."}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Measure the synthetic workload")
    run.add_argument("--items", type=int, default=1_000_000)
    run.add_argument("--seed", type=int, default=20261009)
    run.add_argument("--repeats", type=int, default=5)
    run.add_argument("--warmups", type=int, default=1)
    run.add_argument("--label", default="baseline")
    run.add_argument("--output", type=Path, required=True)
    comparison = commands.add_parser("compare", help="Compare two compatible reports")
    comparison.add_argument("baseline", type=Path)
    comparison.add_argument("candidate", type=Path)
    worker = commands.add_parser("_worker", help="Internal measurement subprocess")
    worker.add_argument("--items", type=int, required=True)
    worker.add_argument("--seed", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "_worker":
            validate_settings(args.items, args.seed, 1, 0)
            print(json.dumps(measure(args.items, args.seed)))
        elif args.command == "run":
            output = args.output.expanduser()
            if output.exists():
                raise ValueError(f"Output already exists; choose a new filename: {output}")
            report = benchmark(args.items, args.seed, args.repeats, args.warmups, args.label)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2, allow_nan=False)
                handle.write("\n")
            print(f"Saved {output}")
            print(json.dumps(report["summary"], indent=2))
        else:
            reports = [json.loads(path.expanduser().read_text(encoding="utf-8"))
                       for path in (args.baseline, args.candidate)]
            print(json.dumps(compare(*reports), indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
