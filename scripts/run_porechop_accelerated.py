#!/usr/bin/env python3
"""Run Porechop_ABI 0.5.1 with a verified OpenMP counter and bounded stage threads."""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

SOURCE_COMMIT = "0bc9f17f31d4ec1dcbab4796871cc09324cc143b"
ARCHIVE_SHA256 = "10a179639ff4db0899ea43843ede4c4e48abd7e1b5edc16e84e9a573aa18041c"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 ** 2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def validate_build(path: Path, tool) -> tuple[dict, Path]:
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != "wings.porechop_openmp_build.v1":
        raise ValueError("Unrecognized Porechop counter manifest.")
    if (manifest.get("source_commit") != SOURCE_COMMIT or
            manifest.get("source_archive_sha256") != ARCHIVE_SHA256):
        raise ValueError("Counter was not built from the validated Porechop_ABI source.")
    expected_prefix = Path(manifest["installed_python"]).parent.parent.resolve()
    if expected_prefix != Path(sys.prefix).resolve():
        raise ValueError("Counter build belongs to another conda environment; rebuild or disable acceleration.")
    if file_hash(Path(tool.__file__)) != manifest["installed_tool_source_sha256"]:
        raise ValueError("Installed Porechop_ABI source differs from the counter build.")
    try:
        version = importlib.metadata.version("Porechop_ABI")
    except importlib.metadata.PackageNotFoundError:
        version = importlib.import_module("porechop_abi.version").__version__
    if version != "0.5.1":
        raise ValueError(f"Acceleration is validated for Porechop_ABI 0.5.1; found {version}.")
    binary_record = manifest["binaries"]["openmp_build"]
    binary = Path(binary_record["path"])
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError("OpenMP counter missing or not executable; rebuild or disable acceleration.")
    if file_hash(binary) != binary_record["sha256"]:
        raise ValueError("OpenMP counter hash differs from its build manifest.")
    library = Path(manifest["openmp_library"])
    if not library.is_file() or file_hash(library) != manifest["openmp_library_sha256"]:
        raise ValueError("OpenMP runtime is missing or changed; rebuild or disable acceleration.")
    probe = manifest.get("openmp_probe", {})
    if probe.get("threads", 0) < 2 or not probe.get("openmp_version"):
        raise ValueError("Build did not record a successful OpenMP runtime probe.")
    if not callable(getattr(tool, "main", None)):
        raise ValueError("Unsupported Porechop_ABI main entry point.")
    for name in ("find_matching_adapter_sets", "find_adapters_at_read_ends", "find_adapters_in_read_middles"):
        function = getattr(tool, name, None)
        if not callable(function) or "threads" not in inspect.signature(function).parameters:
            raise ValueError(f"Unsupported Porechop_ABI thread signature: {name}")
    return manifest, binary


def search_thread_wrapper(function, threads: int):
    signature = inspect.signature(function)
    @functools.wraps(function)
    def search(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.arguments["threads"] = threads
        return function(*bound.args, **bound.kwargs)
    return search


def counter_wrapper(binary: Path, budget: int):
    def execute(args, out_file, conf_file, mr, v, print_dest=sys.stderr):
        native_threads = min(budget, args.threads, os.cpu_count() or 1)
        command = [str(binary), str(args.input), "-v", str(v), "--config", str(conf_file),
                   "-o", str(out_file), "-nt", str(native_threads)]
        if mr > 1:
            command.extend(["-mr", str(mr)])
        print("WINGS counter command: " + json.dumps(command), file=print_dest, flush=True)
        subprocess.run(command, check=True)
    return execute


def run(args) -> int:
    tool = importlib.import_module("porechop_abi.porechop_abi")
    abi = importlib.import_module("porechop_abi.abinitio")
    manifest_path = args.counter_build.expanduser().resolve()
    manifest, binary = validate_build(manifest_path, tool)
    if args.validate_only:
        print("Validated Porechop_ABI 0.5.1 and OpenMP counter: " + str(binary))
        return 0
    if not args.input or not args.output:
        raise ValueError("Supply --input and --output, or use --validate-only.")
    source, destination = args.input.expanduser().resolve(), args.output.expanduser().resolve()
    if not source.is_file() or source == destination:
        raise ValueError("Input must exist and output must differ from input.")
    if destination.exists():
        raise ValueError("Output already exists; let Snakemake manage replacement or choose a new output.")
    budget = min(args.threads, os.cpu_count() or 1)
    search_threads = min(args.adapter_search_threads, budget)
    provenance = {
        "schema_version": "wings.porechop_acceleration.v1", "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend": "openmp_build", "porechop_abi_version": "0.5.1",
        "source_commit": manifest["source_commit"], "python": sys.executable,
        "counter_build": str(manifest_path), "counter_build_sha256": file_hash(manifest_path),
        "counter_path": str(binary), "counter_sha256": file_hash(binary),
        "openmp_library_sha256": manifest["openmp_library_sha256"],
        "tool_source_sha256": manifest["installed_tool_source_sha256"],
        "wrapper_sha256": file_hash(Path(__file__)), "requested_threads": args.threads,
        "phase_threads": {"discovery": budget, "adapter_search": search_threads, "trimming": budget},
        "input": str(source), "input_bytes": source.stat().st_size,
        "input_mtime_ns": source.stat().st_mtime_ns, "output": str(destination),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_directory = Path(tempfile.mkdtemp(prefix=".porechop-abi-", dir=destination.parent))
    provenance.update(temporary_directory=str(temporary_directory), temporary_directory_retained=True)
    provenance_path = destination.with_name(destination.name + ".porechop-provenance.json")
    save_json(provenance_path, provenance)
    print("WINGS Porechop acceleration: " + json.dumps(provenance, sort_keys=True), flush=True)
    # Fresh process per workflow job; restore hooks as well for tests/embedded callers.
    original_counter, original_search, original_argv = abi.execApproxCounter, tool.find_matching_adapter_sets, sys.argv
    started, exit_code = time.perf_counter(), 1
    try:
        abi.execApproxCounter = counter_wrapper(binary, budget)
        tool.find_matching_adapter_sets = search_thread_wrapper(original_search, search_threads)
        sys.argv = ["porechop_abi", "-abi", "--threads", str(budget),
                    "-i", str(source), "-o", str(destination), "-tmp", str(temporary_directory)]
        provenance["argv"] = sys.argv[:]
        try:
            tool.main()
        except SystemExit as error:
            if error.code not in (None, 0):
                raise
        if not destination.is_file():
            raise RuntimeError("Porechop_ABI returned without creating its output.")
        provenance["output_bytes"] = destination.stat().st_size
        provenance["status"] = "complete"
        exit_code = 0
    except BaseException as error:
        provenance.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                          error=f"{type(error).__name__}: {error}")
        raise
    finally:
        abi.execApproxCounter, tool.find_matching_adapter_sets, sys.argv = original_counter, original_search, original_argv
        if exit_code == 0:
            try:
                shutil.rmtree(temporary_directory)
                provenance["temporary_directory_retained"] = False
            except OSError as error:
                provenance["temporary_cleanup_error"] = str(error)
        provenance.update(wall_seconds=time.perf_counter() - started, exit_code=exit_code)
        save_json(provenance_path, provenance)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counter-build", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--adapter-search-threads", type=int, default=1)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if args.threads < 1 or args.adapter_search_threads < 1:
        parser.error("Thread counts must be positive.")
    return run(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit("Porechop acceleration unavailable: " + str(error) +
                         "\nRebuild the counter or set porechop_counter_build to an empty string for the installed backend.")
