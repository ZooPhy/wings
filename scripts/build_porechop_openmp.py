#!/usr/bin/env python3
"""Build isolated serial/OpenMP Porechop_ABI counters on macOS; optionally profile.

Uses the source commit and tarball checksum in the Bioconda 0.5.1 recipe.
The installed package, conda environment and sequencing results are read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from benchmark_porechop_abi import file_hash, save_json, terminate_group

COMMIT = "0bc9f17f31d4ec1dcbab4796871cc09324cc143b"
ARCHIVE_SHA256 = "10a179639ff4db0899ea43843ede4c4e48abd7e1b5edc16e84e9a573aa18041c"
SOURCE_URL = f"https://github.com/bonsai-team/Porechop_ABI/archive/{COMMIT}.tar.gz"
MAX_ARCHIVE_BYTES = 100 * 1024 ** 2
MAX_EXTRACTED_BYTES = 512 * 1024 ** 2
SMOKE_SOURCE = r'''
#include <omp.h>
#include <iostream>
#ifndef _OPENMP
#error OpenMP compiler support was not enabled
#endif
int main() {
    int team = 0;
    omp_set_dynamic(0);
    #pragma omp parallel num_threads(4)
    {
        #pragma omp single
        { team = omp_get_num_threads(); }
    }
    std::cout << "{\"threads\":" << team
              << ",\"openmp_version\":" << _OPENMP << "}\n";
    return team >= 2 ? 0 : 1;
}
'''


def download_archive(destination: Path) -> None:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "WINGS-OpenMP-benchmark/1"})
    size = 0
    with urllib.request.urlopen(request, timeout=30) as source, destination.open("xb") as output:
        while True:
            chunk = source.read(1024 ** 2)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise ValueError("Source download exceeds the size limit.")
            output.write(chunk)


def unpack_source(archive: Path, destination: Path, expected_sha: str = ARCHIVE_SHA256) -> Path:
    if file_hash(archive) != expected_sha:
        raise ValueError("Source archive checksum mismatch; no source was extracted.")
    if sys.version_info < (3, 12):
        raise RuntimeError("Use Python 3.12+ for safe source extraction (your snakemake_env is suitable).")
    with tarfile.open(archive, "r:gz") as handle:
        members = handle.getmembers()
        if sum(member.size for member in members) > MAX_EXTRACTED_BYTES:
            raise ValueError("Extracted source would exceed the size limit.")
        handle.extractall(destination, filter="data")
    directories = [path for path in destination.iterdir() if path.is_dir()]
    if len(directories) != 1:
        raise ValueError("Unexpected source archive directory layout.")
    root = directories[0]
    for name in ("porechop_abi/ab_initio_src/approx_counter.cpp",
                 "porechop_abi/include/seqan/seq_io.h", "porechop_abi/porechop_abi.py", "LICENSE"):
        if not (root / name).is_file():
            raise ValueError(f"Required source file missing: {name}")
    return root


def installed_info(prefix: Path) -> dict:
    python = prefix / "bin/python"
    if not python.is_file():
        raise ValueError(f"Environment Python not found: {python}")
    code = (
        "import json; from pathlib import Path; from porechop_abi import porechop_abi as p; "
        "from porechop_abi.version import __version__; "
        "print(json.dumps({'version':__version__,'tool_source':str(Path(p.__file__).resolve()),"
        "'counter':str(Path(p.__file__).parent/'approx_counter')}))"
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([str(python), "-c", code], env=environment,
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Cannot import the installed Porechop_ABI package: " + result.stderr.strip())
    info = json.loads(result.stdout)
    if info["version"] != "0.5.1":
        raise ValueError(f"This experiment requires Porechop_ABI 0.5.1, found {info['version']}.")
    info["tool_source_sha256"] = file_hash(Path(info["tool_source"]))
    info["counter_sha256"] = file_hash(Path(info["counter"]))
    return info


def compile_command(compiler: str, source: Path, includes: Path, prefix: Path,
                    output: Path, openmp: bool) -> list[str]:
    # Same compiler, source and optimization flags in both rebuilt controls.
    command = [compiler, "-O2", "-DNDEBUG", "-std=c++17", "-DSEQAN_HAS_ZLIB=1",
               "-D_LIBCPP_DISABLE_AVAILABILITY", "-Dbinary_function=__binary_function",
               "-Dunary_function=__unary_function", "-I", str(includes),
               "-I", str(prefix / "include")]
    if openmp:
        command.extend(["-Xpreprocessor", "-fopenmp"])
    command.extend([str(source), "-L", str(prefix / "lib"),
                    "-Wl,-rpath," + str(prefix / "lib"), "-lz"])
    if openmp:
        command.append("-lomp")
    command.extend(["-o", str(output)])
    return command


def compile_logged(command: list[str], log: Path, timeout: float) -> None:
    with log.open("w") as handle:
        handle.write("Command: " + repr(command) + "\n")
        handle.flush()
        process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            terminate_group(process)
            raise
    if code:
        raise RuntimeError(f"Compiler failed with exit {code}; inspect {log}")


def build(prefix: Path, directory: Path, source: Path, compiler: str,
          timeout: float, info: dict) -> dict:
    if file_hash(source / "porechop_abi/porechop_abi.py") != info["tool_source_sha256"]:
        raise ValueError("Installed Python tool source does not match the pinned source archive; no counter was built.")
    for name in ("include/omp.h", "lib/libomp.dylib"):
        if not (prefix / name).is_file():
            raise ValueError(f"Required existing OpenMP file missing: {prefix / name}")
    binary_dir = directory / "bin"
    binary_dir.mkdir()
    smoke_cpp = directory / "openmp_probe.cpp"
    smoke_cpp.write_text(SMOKE_SOURCE)
    smoke_binary = binary_dir / "openmp_probe"
    includes = source / "porechop_abi/include"
    smoke_command = compile_command(compiler, smoke_cpp, includes, prefix, smoke_binary, True)
    print("Checking compiler/OpenMP runtime with a four-thread probe...", flush=True)
    compile_logged(smoke_command, directory / "probe-build.log", timeout)
    result = subprocess.run([str(smoke_binary)], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("OpenMP runtime probe failed: " + result.stdout + result.stderr)
    probe = json.loads(result.stdout)
    if probe.get("threads", 0) < 2 or not probe.get("openmp_version"):
        raise RuntimeError("OpenMP probe did not form a multi-thread team.")
    compiler_version = subprocess.check_output([compiler, "--version"], text=True, timeout=30)
    manifest = {
        "schema_version": "wings.porechop_openmp_build.v1",
        "created_at": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
        "source_commit": COMMIT, "source_archive_sha256": ARCHIVE_SHA256,
        "installed_python": str(prefix / "bin/python"),
        "installed_tool_source_sha256": info["tool_source_sha256"], "installed": info,
        "compiler_version": compiler_version, "openmp_probe": probe,
        "openmp_library": str((prefix / "lib/libomp.dylib").resolve()),
        "openmp_library_sha256": file_hash(prefix / "lib/libomp.dylib"), "binaries": {},
    }
    native_source = source / "porechop_abi/ab_initio_src/approx_counter.cpp"
    for name, enabled in (("serial_build", False), ("openmp_build", True)):
        binary = binary_dir / ("approx_counter_" + name)
        command = compile_command(compiler, native_source, includes, prefix, binary, enabled)
        print(f"Building {name}...", flush=True)
        started = time.perf_counter()
        compile_logged(command, directory / (name + "-build.log"), timeout)
        dependencies = subprocess.check_output(["otool", "-L", str(binary)], text=True, timeout=30)
        if enabled and "libomp" not in dependencies:
            raise RuntimeError("OpenMP counter did not link libomp; inspect the build log.")
        manifest["binaries"][name] = {"path": str(binary), "sha256": file_hash(binary),
                                       "command": command, "dependencies": dependencies,
                                       "build_seconds": time.perf_counter() - started}
    if file_hash(Path(info["counter"])) != info["counter_sha256"]:
        raise RuntimeError("Installed counter changed during the build; investigate before benchmarking.")
    shutil.copy2(source / "LICENSE", directory / "UPSTREAM-LICENSE.txt")
    save_json(directory / "build_manifest.json", manifest)
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-prefix", type=Path, required=True)
    parser.add_argument("--compiler", default="clang++")
    parser.add_argument("--source-archive", type=Path, help="Optional already-downloaded pinned archive")
    parser.add_argument("--output-root", type=Path, default=Path("results/performance/porechop_openmp"))
    parser.add_argument("--build-timeout-seconds", type=float, default=600)
    parser.add_argument("--benchmark-input", type=Path, help="After building, run the bounded comparison")
    parser.add_argument("--reads", type=int, default=5000)
    parser.add_argument("--max-bases", type=int, default=10_000_000)
    parser.add_argument("--trial-timeout-seconds", type=float, default=600)
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        parser.error("This isolated build experiment targets macOS with Apple Clang and llvm-openmp.")
    if args.build_timeout_seconds <= 0 or args.trial_timeout_seconds <= 0 or args.reads < 1 or args.max_bases < 1:
        parser.error("Time and sampling limits must be positive.")
    prefix = args.env_prefix.expanduser().resolve()
    compiler = shutil.which(args.compiler)
    if not compiler or not shutil.which("otool"):
        raise RuntimeError("Apple Clang and otool are required (Xcode Command Line Tools).")
    if args.benchmark_input and not args.benchmark_input.expanduser().is_file():
        raise ValueError("Benchmark input was not found.")
    info = installed_info(prefix)
    root = args.output_root.expanduser().resolve()
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < 2 * 1024 ** 3:
        raise RuntimeError("Free at least 2 GiB of disk space before this experiment.")
    directory = root / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    print(f"Isolated build folder: {directory}", flush=True)
    archive = args.source_archive.expanduser().resolve() if args.source_archive else directory / "source.tar.gz"
    if not args.source_archive:
        print("Downloading pinned Porechop_ABI 0.5.1 source...", flush=True)
        download_archive(archive)
    source = unpack_source(archive, directory / "source")
    build(prefix, directory, source, compiler, args.build_timeout_seconds, info)
    manifest = directory / "build_manifest.json"
    print(f"Build manifest: {manifest}", flush=True)
    if args.benchmark_input:
        command = [sys.executable, str(Path(__file__).with_name("benchmark_porechop_abi.py")),
                   "--input", str(args.benchmark_input.expanduser().resolve()),
                   "--python", str(prefix / "bin/python"), "--counter-build", str(manifest),
                   "--reads", str(args.reads), "--max-bases", str(args.max_bases),
                   "--threads", "1", "4", "--timeout-seconds", str(args.trial_timeout_seconds)]
        print("Starting installed / rebuilt-serial / rebuilt-OpenMP comparison...", flush=True)
        return subprocess.call(command)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Build cancelled; installed files were not replaced.", file=sys.stderr)
        raise SystemExit(130)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"Build error: {error}", file=sys.stderr)
        raise SystemExit(1)
