# Synthetic performance benchmark

This standalone tool validates a measurement and comparison framework using
deterministically generated integers. It does not launch WINGS, Docker, IRMA,
or any sequence analysis. Its results are not evidence of IRMA performance.

Python 3.9 or later is sufficient. No additional packages are required.

## Collect a baseline

Use the same idle computer and power settings for comparable runs. Each repeat
generates, sorts, and hashes the same integers in a fresh Python process.
The default is one discarded warmup and five measured repeats of one million
integers. The warmup runs in its own process; it does not warm another process's
Python heap or interpreter state.

```bash
python scripts/benchmark_synthetic.py run \
  --label baseline \
  --output "$HOME/.wings/benchmarks/synthetic-baseline.json"
```

The JSON report includes every repeat, median/minimum/maximum measurements,
output checksums, workload settings, environment information, and a hash of
the benchmark script. Existing output files are never overwritten.

## Check repeatability

Collect another report with unchanged settings. This is a repeatability check,
not an optimization experiment:

```bash
python scripts/benchmark_synthetic.py run \
  --label repeat \
  --output "$HOME/.wings/benchmarks/synthetic-repeat.json"
python scripts/benchmark_synthetic.py compare \
  "$HOME/.wings/benchmarks/synthetic-baseline.json" \
  "$HOME/.wings/benchmarks/synthetic-repeat.json"
```

The comparison requires identical workload settings and consistent matching
output checksums. It reports candidate/baseline ratios: below 1 means less
measured time or memory. Environmental differences are listed explicitly.
Small differences can be noise; inspect the measurement ranges and repeat
before drawing conclusions. A script change is recorded separately and does
not automatically invalidate a comparison if outputs and workload settings match.

## What the measurements mean

- **Wall time:** time spent generating, sorting, and hashing integers. It
  excludes interpreter startup, imports, and JSON report writing.
- **CPU time:** CPU time of the worker over that same interval. This workload
  is single-process and does not exercise multithreaded scaling.
- **Peak RSS:** the worker process's lifetime peak resident memory, including
  interpreter startup. Reported in bytes on macOS and Linux; null elsewhere.
- **Checksum:** SHA-256 of sorted unsigned 32-bit integers in little-endian
  order. It checks deterministic output, not biological correctness.

The benchmark does not characterize disk I/O, container overhead, alignment,
assembly, or workload-specific scheduling. Measurements are from the computer
where the command runs. Comparing across computers or Python versions changes
the experimental conditions.

## Tests

```bash
python -m unittest discover -s tests -p test_synthetic_benchmark.py
```

This adds no pipeline rules, dependencies, or public-interface controls.
