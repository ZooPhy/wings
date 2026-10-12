#!/usr/bin/env python3
"""Promote a validated pilot build into a persistent cache and enable it locally."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml
from run_porechop_accelerated import file_hash


def configure(repo: Path, benchmark: Path, cache_root: Path) -> tuple[Path, Path]:
    repo, benchmark, cache_root = repo.resolve(), benchmark.resolve(), cache_root.expanduser().resolve()
    result = json.loads(benchmark.read_text())
    if (result.get("schema_version") != "wings.porechop_benchmark.v1" or
            result.get("subset", {}).get("reads", 0) < 20000 or
            not result.get("output_comparison", {}).get("all_pairs_match")):
        raise ValueError("Use the matching-output phase-comparison summary from at least 20,000 reads.")
    trials = result.get("trials", [])
    if (len(trials) < 4 or len(trials) != result.get("planned_trials") or
            any(row.get("status") != "complete" for row in trials)):
        raise ValueError("Benchmark must have at least four completed trials and no incomplete trials.")
    for row in trials:
        if not row.get("output_sha256") or not row.get("discovery_file_hashes"):
            raise ValueError("Benchmark must record final output and discovery hashes for every trial.")
    if len({row["output_sha256"] for row in trials}) != 1:
        raise ValueError("Final benchmark outputs differ; inspect before integrating.")
    if any(row["discovery_file_hashes"] != trials[0]["discovery_file_hashes"] for row in trials[1:]):
        raise ValueError("Discovery benchmark files differ; inspect before integrating.")
    for repeat in {row.get("repeat") for row in trials}:
        if {row.get("allocation") for row in trials if row.get("repeat") == repeat} != {"uniform", "phase_split"}:
            raise ValueError("Each benchmark repeat must include uniform and phase-split trials.")
    build = result["counter_build"]
    for row in trials:
        if (row.get("backend") != "openmp_build" or
                row.get("counter_sha256") != build["binaries"]["openmp_build"]["sha256"] or
                row.get("tool_source_sha256") != build["installed_tool_source_sha256"]):
            raise ValueError("Benchmark trials do not match the recorded counter and tool build.")
    config_path = repo / "config.yaml"
    config = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(config, dict):
        raise ValueError("config.yaml must contain a YAML mapping.")
    if config.get("porechop_command", "porechop_abi") != "porechop_abi":
        raise ValueError("This backend requires porechop_command: porechop_abi.")
    runner = repo / "scripts/run_porechop_accelerated.py"
    if not runner.is_file():
        raise ValueError("Apply the acceleration patch before enabling the backend.")
    if not all(row.get("phase_threads") == {"discovery": 4, "adapter_search": 1, "trimming": 4}
               for row in trials if row.get("allocation") == "phase_split"):
        raise ValueError("Expected a validated discovery=4/search=1/trimming=4 trial.")
    cache_root.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="openmp-", dir=cache_root))
    promoted = json.loads(json.dumps(build))
    try:
        (target / "bin").mkdir()
        for name, record in promoted["binaries"].items():
            if name not in ("serial_build", "openmp_build"):
                raise ValueError("Unexpected counter variant in build manifest.")
            source = Path(record["path"])
            destination = target / "bin" / ("approx_counter_" + name)
            shutil.copy2(source, destination)
            if file_hash(destination) != record["sha256"]:
                raise ValueError("Counter differs from its recorded build hash.")
            record["path"] = str(destination)
        original_build_dir = Path(build["binaries"]["openmp_build"]["path"]).parent.parent
        license_path = original_build_dir / "UPSTREAM-LICENSE.txt"
        if not license_path.is_file():
            raise ValueError("Counter build is missing its upstream license.")
        shutil.copy2(license_path, target / "UPSTREAM-LICENSE.txt")
        promoted["validated_benchmark"] = str(benchmark)
        promoted["validation_subset"] = result["subset"]
        promoted["validation_pairs"] = result["output_comparison"]["pairs"]
        manifest_path = target / "build_manifest.json"
        manifest_path.write_text(json.dumps(promoted, indent=2, sort_keys=True) + "\n")
        (target / "validation-summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PATH"] = str(Path(promoted["installed_python"]).parent) + os.pathsep + environment.get("PATH", "")
        environment["CONDA_PREFIX"] = str(Path(promoted["installed_python"]).parent.parent)
        subprocess.run([promoted["installed_python"], str(runner), "--counter-build", str(manifest_path),
                        "--validate-only"], env=environment, check=True)
    except BaseException:
        shutil.rmtree(target)
        raise
    config.update(porechop_counter_build=str(manifest_path), porechop_threads=4,
                  porechop_adapter_search_threads=1)
    backup = config_path.with_name(config_path.name + ".backup-porechop-" +
                                  datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    shutil.copy2(config_path, backup)
    fd, name = tempfile.mkstemp(dir=repo, prefix=".porechop-config-")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as handle:
            yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)
        temporary.chmod(config_path.stat().st_mode & 0o777)
        temporary.replace(config_path)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest_path, backup


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("~/.cache/wings/porechop"))
    args = parser.parse_args(argv)
    manifest, backup = configure(args.repo.expanduser(), args.benchmark.expanduser(), args.cache_dir)
    print(f"Enabled counter: {manifest}")
    print(f"Config backup: {backup}")
    print("Requested threads: 4; adapter search threads: 1. Snakemake may allocate fewer cores.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
