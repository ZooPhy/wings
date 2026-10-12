#!/usr/bin/env python3
"""Bounded, isolated phase profiling of the installed Porechop_ABI package.

Use the same arguments as WINGS (-abi plus --threads), on a prefix subset.
This does not modify the installed package or existing workflow outputs.
"""
from __future__ import annotations

import argparse
import copy
import csv
import functools
import gzip
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import os
import platform
import resource
import shutil
import signal
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PHASES = {
    "get_arguments": "setup_and_read_count",
    "launch_ab_initio": "adapter_discovery",
    "load_reads": "read_loading",
    "find_matching_adapter_sets": "adapter_set_search",
    "find_adapters_at_read_ends": "end_trimming",
    "find_adapters_in_read_middles": "middle_trimming",
    "output_reads": "write_output",
}
DETAILS = {
    "execApproxCounter": "discovery_native_counting",
    "build_graph": "discovery_graph_build",
    "generic_build": "discovery_path_assembly",
}
SCRIPT = Path(__file__).resolve()


def save_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 ** 2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def counter_variants(manifest_path: Path | None, python: Path) -> tuple[list[dict], dict | None]:
    if not manifest_path:
        return [{"name": "installed", "path": None}], None
    manifest = json.loads(manifest_path.read_text())
    return validate_counter_manifest(manifest, python), manifest


def validate_counter_manifest(manifest: dict, python: Path) -> list[dict]:
    if manifest.get("schema_version") != "wings.porechop_openmp_build.v1":
        raise ValueError("Unrecognized counter build manifest.")
    if Path(manifest["installed_python"]).absolute() != python.absolute():
        raise ValueError("Counter build and benchmark must use the same Porechop_ABI environment.")
    variants = [{"name": "installed", "path": None}]
    for name in ("serial_build", "openmp_build"):
        binary = Path(manifest["binaries"][name]["path"])
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError(f"Counter binary missing or not executable: {binary}")
        if file_hash(binary) != manifest["binaries"][name]["sha256"]:
            raise ValueError(f"Counter binary differs from build manifest: {binary}")
        variants.append({"name": name, "path": str(binary)})
    return variants


def phase_thread_wrapper(function, threads: int, discovery: bool = False):
    """Override only thread arguments, leaving the upstream main and thresholds intact."""
    signature = inspect.signature(function)
    parameter = "args" if discovery else "threads"
    if parameter not in signature.parameters:
        raise RuntimeError(f"Unsupported thread-control signature: {function.__name__}")

    @functools.wraps(function)
    def allocated(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        if discovery:
            namespace = copy.copy(bound.arguments[parameter])
            namespace.threads = threads
            bound.arguments[parameter] = namespace
        else:
            bound.arguments[parameter] = threads
        return function(*bound.args, **bound.kwargs)
    return allocated


def native_counter(binary: Path):
    """Keep the installed ABI counter protocol; only substitute its executable."""
    def execute(args, out_file, conf_file, mr, v, print_dest=sys.stderr):
        command = [str(binary), str(args.input), "-v", str(v), "--config", str(conf_file),
                   "-o", str(out_file), "-nt", str(min(args.threads, os.cpu_count() or 1))]
        if mr > 1:
            command.extend(["-mr", str(mr)])
        print("Benchmark counter:", command, file=print_dest, flush=True)
        subprocess.check_call(command)
    return execute


def usage() -> dict:
    own = resource.getrusage(resource.RUSAGE_SELF)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    divisor = 1024 ** 2 if sys.platform == "darwin" else 1024
    return {
        "cpu_self_seconds": own.ru_utime + own.ru_stime,
        "cpu_children_seconds": child.ru_utime + child.ru_stime,
        "peak_self_rss_mib": own.ru_maxrss / divisor,
        "peak_largest_child_rss_mib": child.ru_maxrss / divisor,
    }


def subset_fastq(source: Path, destination: Path, reads: int, bases: int) -> dict:
    """Copy complete four-line reads from a bounded prefix, validating records."""
    count = total = 0
    digest = hashlib.sha256()
    limit = 5_000_000
    reason = "end_of_file"
    with source.open("rb") as raw:
        compressed = raw.read(2) == b"\x1f\x8b"
    opener = gzip.open if compressed else open
    with opener(source, "rb") as handle, destination.open("xb") as output:
        while count < reads:
            header = handle.readline(limit + 1)
            if not header:
                break
            lines = [header] + [handle.readline(limit + 1) for _ in range(3)]
            if any(not line or len(line) > limit for line in lines):
                raise ValueError(f"Incomplete or oversized FASTQ record {count + 1}.")
            sequence = lines[1].rstrip(b"\r\n")
            quality = lines[3].rstrip(b"\r\n")
            if (not header.startswith(b"@") or not lines[2].startswith(b"+")
                    or not sequence or len(sequence) != len(quality)):
                raise ValueError(f"Invalid four-line FASTQ record {count + 1}.")
            if total + len(sequence) > bases:
                reason = "base_limit"
                break
            record = b"".join(line.rstrip(b"\r\n") + b"\n" for line in lines)
            output.write(record)
            digest.update(record)
            count += 1
            total += len(sequence)
        else:
            reason = "read_limit"
    if count == 0:
        raise ValueError("No reads fit the limits; check FASTQ input and --max-bases.")
    return {"reads": count, "bases": total, "sha256": digest.hexdigest(),
            "size_bytes": destination.stat().st_size, "stop_reason": reason,
            "sampling": "first complete reads; not a random full-file sample"}


def probe_python(executable: Path, environment: dict) -> dict | None:
    code = (
        "import json,sys; from importlib.util import find_spec; "
        "print(json.dumps({'python':sys.executable,'prefix':sys.prefix,"
        "'found':find_spec('porechop_abi') is not None}))"
    )
    try:
        result = subprocess.run([str(executable), "-c", code], env=environment,
                                capture_output=True, text=True, timeout=15)
        value = json.loads(result.stdout)
        return value if result.returncode == 0 and value["found"] else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def resolve_environment(repo: Path, requested: Path | None) -> tuple[Path, dict]:
    if requested:
        candidates = [requested.absolute()]
    else:
        candidates = [Path(sys.executable)]
        candidates.extend(sorted((repo / ".snakemake/conda").glob("*/bin/python")))
    seen = set()
    for candidate in candidates:
        if str(candidate) in seen or not candidate.is_file():
            continue
        seen.add(str(candidate))
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PATH"] = str(candidate.parent) + os.pathsep + env.get("PATH", "")
        found = probe_python(candidate, env)
        if found:
            env["CONDA_PREFIX"] = found["prefix"]
            return candidate, env
    raise RuntimeError("Porechop_ABI environment not found. Supply --python with the "
                       "Python executable from its installed Snakemake conda environment.")


class Recorder:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"status": "running", "phases": {}, "active_phase": None}

    def checkpoint(self):
        save_json(self.path, self.data)

    def wrap(self, function, label: str, scope: str):
        @functools.wraps(function)
        def measured(*args, **kwargs):
            previous = self.data["active_phase"]
            self.data["active_phase"] = label
            # Only checkpoint coarse phases and the long-running native counter.
            checkpoint = scope == "phase" or label == "discovery_native_counting"
            if checkpoint:
                self.checkpoint()
            before, started = usage(), time.perf_counter()
            successful = False
            try:
                result = function(*args, **kwargs)
                successful = True
                return result
            finally:
                elapsed = time.perf_counter() - started
                after = usage()
                row = self.data["phases"].setdefault(label, {
                    "scope": scope, "calls": 0, "successful_calls": 0,
                    "wall_seconds": 0.0, "cpu_self_seconds": 0.0,
                    "cpu_children_seconds": 0.0,
                })
                row["calls"] += 1
                row["successful_calls"] += int(successful)
                row["wall_seconds"] += elapsed
                for key in ("cpu_self_seconds", "cpu_children_seconds"):
                    row[key] += max(0, after[key] - before[key])
                self.data["active_phase"] = previous
                if checkpoint:
                    self.checkpoint()
        return measured


def worker(config_path: Path) -> int:
    config = json.loads(config_path.read_text())
    recorder = Recorder(Path("phase_metrics.json"))
    started = time.perf_counter()
    code = 1
    try:
        tool = importlib.import_module("porechop_abi.porechop_abi")
        abi = importlib.import_module("porechop_abi.abinitio")
        missing = [name for name in PHASES if not callable(getattr(tool, name, None))]
        if missing:
            raise RuntimeError("Unsupported Porechop_ABI entry points: " + ", ".join(missing))
        try:
            version = importlib.metadata.version("Porechop_ABI")
        except importlib.metadata.PackageNotFoundError:
            try:
                version = importlib.import_module("porechop_abi.version").__version__
            except (ImportError, AttributeError):
                version = "unknown"
        recorder.data.update(porechop_abi_version=version,
                             tool_source=str(Path(tool.__file__).resolve()),
                             tool_source_sha256=hashlib.sha256(Path(tool.__file__).read_bytes()).hexdigest(),
                             python=sys.version, threads=config["threads"])
        recorder.data["backend"] = config.get("backend", "installed")
        if config.get("expected_tool_source_sha256"):
            if recorder.data["tool_source_sha256"] != config["expected_tool_source_sha256"]:
                raise RuntimeError("Installed tool source no longer matches the counter build.")
        counter = Path(config["counter_path"]) if config.get("counter_path") else Path(abi.__file__).parent / "approx_counter"
        if config.get("counter_path"):
            abi.execApproxCounter = native_counter(counter)
        if counter.is_file():
            recorder.data.update(counter_path=str(counter.resolve()), counter_sha256=file_hash(counter))
        allocations = config.get("phase_threads")
        if allocations:
            recorder.data["phase_threads"] = allocations
            for name, count, discovery in (
                ("launch_ab_initio", allocations["discovery"], True),
                ("find_matching_adapter_sets", allocations["adapter_search"], False),
                ("find_adapters_at_read_ends", allocations["trimming"], False),
                ("find_adapters_in_read_middles", allocations["trimming"], False),
            ):
                setattr(tool, name, phase_thread_wrapper(getattr(tool, name), count, discovery))
        for name, label in PHASES.items():
            setattr(tool, name, recorder.wrap(getattr(tool, name), label, "phase"))
        for name, label in DETAILS.items():
            function = getattr(abi, name, None)
            if callable(function):
                setattr(abi, name, recorder.wrap(function, label, "discovery_detail"))
        sys.argv = ["porechop_abi", "-abi", "--threads", str(config["threads"]),
                    "-i", "input.fastq", "-o", "trimmed.fastq", "-tmp", "abi_tmp"]
        recorder.data["argv"] = sys.argv[:]
        recorder.checkpoint()
        tool.main()
        if not Path("trimmed.fastq").is_file():
            raise RuntimeError("Tool returned without creating trimmed.fastq; inspect the trial log.")
        code = 0
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else (0 if error.code is None else 1)
        if code:
            recorder.data["error"] = str(error)
    except Exception as error:
        recorder.data["error"] = f"{type(error).__name__}: {error}"
        print(recorder.data["error"], file=sys.stderr)
    finally:
        recorder.data.update(status="complete" if code == 0 else "failed", exit_code=code,
                             worker_wall_seconds=time.perf_counter() - started, **usage())
        recorder.checkpoint()
    return code


def terminate_group(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    # A child may remain even after the group leader exits.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_trial(python: Path, env: dict, subset: Path, directory: Path,
              threads: int, timeout: float, variant: dict | None = None,
              expected_tool_hash: str | None = None,
              phase_threads: dict | None = None, allocation: str = "uniform") -> dict:
    directory.mkdir()
    (directory / "input.fastq").symlink_to(subset)
    config_path = directory / "worker_config.json"
    variant = variant or {"name": "installed", "path": None}
    save_json(config_path, {"threads": threads, "backend": variant["name"],
                            "counter_path": variant["path"],
                            "expected_tool_source_sha256": expected_tool_hash,
                            "phase_threads": phase_threads})
    command = [str(python), str(SCRIPT), "_worker", str(config_path)]
    started = time.perf_counter()
    interrupted = False
    status = None
    with (directory / "porechop.log").open("w") as log:
        process = subprocess.Popen(command, cwd=directory, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            status = "timeout"
            terminate_group(process)
        except KeyboardInterrupt:
            interrupted = True
            status = "cancelled"
            terminate_group(process)
    metrics = directory / "phase_metrics.json"
    row = json.loads(metrics.read_text()) if metrics.is_file() else {"phases": {}}
    row.update(status=status or ("complete" if process.returncode == 0 else "failed"),
               process_exit_code=process.returncode, threads=threads,
               wall_seconds=time.perf_counter() - started, directory=str(directory),
               command=command)
    row["backend"] = variant["name"]
    row["allocation"] = allocation
    row["phase_threads"] = phase_threads or {
        "discovery": threads, "adapter_search": threads, "trimming": threads}
    output = directory / "trimmed.fastq"
    if row["status"] == "complete" and output.is_file():
        digest = hashlib.sha256()
        with output.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 ** 2), b""):
                digest.update(chunk)
        row.update(output_sha256=digest.hexdigest(), output_bytes=output.stat().st_size)
        native_files = directory / "abi_tmp"
        row["discovery_file_hashes"] = {
            str(path.relative_to(native_files)): file_hash(path)
            for path in sorted(native_files.rglob("*")) if path.is_file() and not path.is_symlink()
        } if native_files.is_dir() else {}
    save_json(directory / "trial_summary.json", row)
    if interrupted:
        row["interrupted"] = True
    return row


def compare_outputs(result: dict) -> dict:
    """Compare complete baseline/candidate pairs within each repeat explicitly."""
    pairs = []
    for repeat in sorted({row.get("repeat", 1) for row in result["trials"]}):
        rows = {row.get("allocation", "uniform"): row for row in result["trials"]
                if row.get("repeat", 1) == repeat}
        a, b = rows.get("uniform"), rows.get("phase_split")
        complete = bool(a and b and a["status"] == b["status"] == "complete")
        output_equal = bool(complete and a.get("output_sha256") and
                            a["output_sha256"] == b.get("output_sha256"))
        discovery_equal = bool(complete and a.get("discovery_file_hashes") and
                               a["discovery_file_hashes"] == b.get("discovery_file_hashes"))
        pairs.append({"repeat": repeat, "complete": complete,
                      "trimmed_output_identical": output_equal,
                      "discovery_intermediates_identical": discovery_equal,
                      "uniform_seconds": a.get("wall_seconds") if a else None,
                      "phase_split_seconds": b.get("wall_seconds") if b else None})
    all_scheduled = len(result["trials"]) == result.get("planned_trials", len(result["trials"]))
    return {"pairs": pairs, "all_pairs_match": all_scheduled and bool(pairs) and all(
        p["complete"] and p["trimmed_output_identical"] and
        p["discovery_intermediates_identical"] for p in pairs)}


def report(directory: Path, result: dict) -> None:
    if result.get("phase_thread_comparison"):
        result["output_comparison"] = compare_outputs(result)
    save_json(directory / "summary.json", result)
    fields = ["trial", "repeat", "allocation", "backend", "threads", "phase_threads", "status", "phase", "scope", "calls",
              "successful_calls", "wall_seconds", "cpu_self_seconds", "cpu_children_seconds"]
    with (directory / "phase_times.tsv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for trial, row in enumerate(result["trials"], 1):
            for phase, metrics in row["phases"].items():
                writer.writerow({"trial": trial, "threads": row["threads"],
                                 "backend": row.get("backend", "installed"),
                                 "repeat": row.get("repeat", 1),
                                 "allocation": row.get("allocation", "uniform"),
                                 "phase_threads": json.dumps(row.get("phase_threads", {}), sort_keys=True),
                                 "status": row["status"], "phase": phase, **metrics})
    lines = ["Porechop_ABI benchmark", f"Subset: {result['subset']['reads']} reads; "
             f"{result['subset']['bases']:,} bases", ""]
    for index, row in enumerate(result["trials"], 1):
        lines.append(f"Trial {index}: backend={row.get('backend', 'installed')} threads={row['threads']} status={row['status']} "
                     f"elapsed={row['wall_seconds']:.2f}s")
        lines.append(f"  Repeat {row.get('repeat', 1)}; allocation={row.get('allocation', 'uniform')}; "
                     f"phase threads={row.get('phase_threads', {})}")
        for phase, metrics in sorted(row["phases"].items(),
                                     key=lambda item: item[1]["wall_seconds"], reverse=True):
            if metrics["scope"] == "phase":
                lines.append(f"  {phase}: {metrics['wall_seconds']:.2f}s "
                             f"({metrics['successful_calls']}/{metrics['calls']} calls completed)")
        counting = row["phases"].get("discovery_native_counting")
        if counting:
            lines.append(f"    Native counting within discovery: {counting['wall_seconds']:.2f}s")
        for label in ("end_trimming", "middle_trimming"):
            if row["status"] == "complete" and label not in row["phases"]:
                lines.append(f"  {label}: not called; no usable timing for this phase")
        if "peak_self_rss_mib" in row:
            lines.append(f"  Peak worker RSS: {row['peak_self_rss_mib']:.1f} MiB; "
                         f"largest reaped child: {row['peak_largest_child_rss_mib']:.1f} MiB")
        if row.get("active_phase"):
            lines.append(f"  Last active phase: {row['active_phase']}")
        if row.get("error"):
            lines.append(f"  Error: {row['error']}")
    complete = [row for row in result["trials"] if row["status"] == "complete"]
    lines.append(f"Completed trials: {len(complete)}/{result.get('planned_trials', len(result['trials']))}")
    if len(complete) > 1:
        for label, key in (("Final trimmed output hashes", "output_sha256"),
                           ("Discovery intermediate hashes", "discovery_file_hashes")):
            captured = all(row.get(key) for row in complete)
            equal = captured and all(row[key] == complete[0][key] for row in complete[1:])
            lines.append(label + ": " + ("identical among completed trials" if equal else
                         "differ; inspect before interpreting equivalence" if captured else "not fully captured"))
    if result.get("phase_thread_comparison"):
        for pair in result["output_comparison"]["pairs"]:
            lines.append(f"Repeat {pair['repeat']} output check: " + (
                "incomplete" if not pair["complete"] else
                "MATCH (discovery and final trimmed bytes)" if
                pair["trimmed_output_identical"] and pair["discovery_intermediates_identical"] else
                "NOT VERIFIED; inspect hashes before integrating"))
            if pair["complete"]:
                baseline, candidate = pair["uniform_seconds"], pair["phase_split_seconds"]
                lines.append(f"  Uniform: {baseline:.2f}s; phase split: {candidate:.2f}s; "
                             f"elapsed reduction: {(1 - candidate / baseline) * 100:.1f}%")
        complete_pairs = [p for p in result["output_comparison"]["pairs"] if p["complete"]]
        if complete_pairs:
            baseline = statistics.median(p["uniform_seconds"] for p in complete_pairs)
            candidate = statistics.median(p["phase_split_seconds"] for p in complete_pairs)
            lines.append(f"Median total over {len(complete_pairs)} complete pairs: "
                         f"uniform={baseline:.2f}s; phase_split={candidate:.2f}s; "
                         f"elapsed reduction={(1 - candidate / baseline) * 100:.1f}%")
    visible = lines[:]
    lines.extend(["", "This is a prefix pilot, not a full-file runtime estimate.",
                  "Discovery detail timers overlap the adapter_discovery timer; do not add them together.",
                  "Memory reports worker peak RSS and largest reaped child RSS, not aggregate process-tree peak.",
                  "ABI inference may vary between trials; output hashes flag differences, not their cause.",
                  "Full provenance and raw timings: summary.json; tabular timings: phase_times.tsv."])
    (directory / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(visible))
    print(f"Results: {directory}")


def main(argv=None) -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "_worker":
        return worker(Path(sys.argv[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path, help="Original FASTQ or FASTQ.gz")
    inputs.add_argument("--reuse-benchmark", type=Path,
                        help="Previous summary.json; reuse its exact subset and counter build")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--python", type=Path, help="Explicit installed Porechop_ABI environment Python")
    parser.add_argument("--counter-build", type=Path, help="Manifest from the isolated OpenMP builder")
    parser.add_argument("--reads", type=int, default=5000)
    parser.add_argument("--max-bases", type=int, default=10_000_000)
    parser.add_argument("--threads", nargs="+", type=int, default=[1, 4])
    parser.add_argument("--phase-thread-comparison", action="store_true",
                        help="Pair uniform OpenMP threads with separate phase threads")
    parser.add_argument("--discovery-threads", type=int)
    parser.add_argument("--adapter-search-threads", type=int)
    parser.add_argument("--trimming-threads", type=int)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument("--min-free-gb", type=float, default=2)
    parser.add_argument("--output-root", type=Path, default=Path("results/performance/porechop_abi"))
    args = parser.parse_args(argv)
    if args.reads < 1 or args.max_bases < 1 or args.repeats < 1 or any(t < 1 for t in args.threads):
        parser.error("Read/base limits, repeats, and threads must be positive.")
    if args.timeout_seconds <= 0 or args.min_free_gb < 0:
        parser.error("Timeout must be positive and minimum free space nonnegative.")
    if os.name != "posix":
        parser.error("This benchmark currently supports macOS and Linux.")
    overrides = [args.discovery_threads, args.adapter_search_threads, args.trimming_threads]
    if any(t is not None and t < 1 for t in overrides):
        parser.error("Phase thread counts must be positive.")
    if any(t is not None for t in overrides) and not args.phase_thread_comparison:
        parser.error("Phase controls require --phase-thread-comparison.")
    if args.phase_thread_comparison and (len(args.threads) != 1 or args.threads[0] < 2):
        parser.error("For phase comparison supply one thread budget, e.g. --threads 4.")
    previous = None
    reuse_path = args.reuse_benchmark.expanduser().resolve() if args.reuse_benchmark else None
    if reuse_path:
        if args.counter_build:
            parser.error("--reuse-benchmark already supplies the counter build.")
        previous = json.loads(reuse_path.read_text())
        if previous.get("schema_version") != "wings.porechop_benchmark.v1":
            raise ValueError("Unrecognized previous benchmark summary.")
        source = reuse_path.parent / "subset.fastq"
        stats = previous["subset"]
        if (not source.is_file() or source.stat().st_size != stats["size_bytes"] or
                file_hash(source) != stats["sha256"]):
            raise ValueError("Previous subset is missing or differs from its recorded hash.")
        if stats["reads"] < 1 or stats["bases"] < 1:
            raise ValueError("Previous subset is empty.")
    else:
        source = args.input.expanduser().resolve()
        if not source.is_file():
            parser.error(f"Input not found: {source}")
    repo = args.repo.expanduser().resolve()
    requested_python = args.python.expanduser() if args.python else (
        Path(previous["python_executable"]) if previous else None)
    python, env = resolve_environment(repo, requested_python)
    if previous:
        build_manifest = previous.get("counter_build")
        if not build_manifest:
            raise ValueError("Previous benchmark has no isolated counter build.")
        variants = validate_counter_manifest(build_manifest, python)
    else:
        variants, build_manifest = counter_variants(args.counter_build.expanduser().resolve() if args.counter_build else None, python)
    split = None
    if args.phase_thread_comparison:
        if not build_manifest:
            parser.error("Phase comparison requires --counter-build or --reuse-benchmark.")
        budget = args.threads[0]
        split = {"discovery": args.discovery_threads or budget,
                 "adapter_search": args.adapter_search_threads or 1,
                 "trimming": args.trimming_threads or budget}
        if max(split.values()) > budget:
            parser.error("Phase threads cannot exceed the --threads budget.")
    root = args.output_root.expanduser().resolve()
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < args.min_free_gb * 1024 ** 3:
        raise RuntimeError("Not enough disk space for the pilot; free space before running.")
    directory = root / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    subset = directory / "subset.fastq"
    print(f"Benchmark folder: {directory}", flush=True)
    print(f"Porechop_ABI Python: {python}", flush=True)
    if previous:
        with source.open("rb") as handle, subset.open("xb") as output:
            shutil.copyfileobj(handle, output)
        if file_hash(subset) != stats["sha256"]:
            raise RuntimeError("Subset changed while copying; benchmark not started.")
        stats = dict(stats)
        print("Reusing the exact previous subset; no new sampling or counter build.", flush=True)
    else:
        stats = subset_fastq(source, subset, args.reads, args.max_bases)
    result = {"schema_version": "wings.porechop_benchmark.v1", "created_at": datetime.now(timezone.utc).isoformat(),
              "input": str(source), "input_size_bytes": source.stat().st_size,
              "input_mtime_ns": source.stat().st_mtime_ns, "subset": stats,
              "platform": platform.platform(), "logical_cpus": os.cpu_count(),
              "python_executable": str(python), "timeout_seconds": args.timeout_seconds,
              "benchmark_script_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
              "limits": {"reads": args.reads, "bases": args.max_bases}, "trials": []}
    if build_manifest:
        result["counter_build"] = build_manifest
    if previous:
        result["reused_benchmark"] = str(reuse_path)
        result["limits"] = previous.get("limits", {})
        result["original_input"] = previous.get("original_input", previous.get("input"))
    result["phase_thread_comparison"] = args.phase_thread_comparison
    save_json(directory / "summary.json", result)
    failed = cancelled = False
    if split:
        variant = next(v for v in variants if v["name"] == "openmp_build")
        uniform = {"discovery": budget, "adapter_search": budget, "trimming": budget}
        schedule = [(variant, budget, uniform, "uniform"),
                    (variant, budget, split, "phase_split")]
    else:
        schedule = [(variant, threads, None, "uniform") for variant in variants for threads in args.threads
                    if variant["name"] != "serial_build" or threads == args.threads[0]]
    result["planned_trials"] = len(schedule) * args.repeats
    for repeat in range(args.repeats):
        ordered = list(reversed(schedule)) if split and repeat % 2 else schedule
        for variant, threads, allocation_threads, allocation in ordered:
            print(f"Starting repeat {repeat + 1}, backend={variant['name']}, allocation={allocation}, threads={threads} (limit {args.timeout_seconds:g}s)", flush=True)
            row = run_trial(python, env, subset,
                            directory / f"repeat-{repeat + 1}-{variant['name']}-{allocation}-threads-{threads}-{len(result['trials']) + 1}",
                            threads, args.timeout_seconds, variant,
                            build_manifest["installed_tool_source_sha256"] if build_manifest else None,
                            allocation_threads, allocation)
            row["repeat"] = repeat + 1
            save_json(Path(row["directory"]) / "trial_summary.json", row)
            result["trials"].append(row)
            report(directory, result)
            if row.get("interrupted"):
                cancelled = True
                break
            if row["status"] != "complete":
                failed = True
                break
        if cancelled or failed:
            break
    mismatch = bool(split and not failed and not cancelled and
                    not result["output_comparison"]["all_pairs_match"])
    return 130 if cancelled else (1 if failed else (2 if mismatch else 0))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Benchmark error: {error}", file=sys.stderr)
        raise SystemExit(1)
