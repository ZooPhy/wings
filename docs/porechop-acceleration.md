# Optional Porechop_ABI CPU acceleration

The optional backend uses an OpenMP-enabled native counter for adapter discovery
and one thread for adapter-set search. Trimming uses Snakemake's allocated
threads. The installed Porechop_ABI 0.5.1 main function, adapter database,
thresholds and output logic are retained. The backend is currently validated
on Apple Silicon macOS.

Two paired prefix pilots on one input produced matching discovery intermediates
and final trimmed bytes across all trials:

| Reads | Uniform OpenMP median | Phase-specific median | Elapsed reduction |
| --- | ---: | ---: | ---: |
| 5,000 | 25.86 s | 21.71 s | 16.1% |
| 20,000 | 71.90 s | 64.20 s | 10.7% |

Worker peak RSS at 20,000 reads fell from approximately 506 MiB to 152 MiB;
the native child's peak remained approximately 312 MiB. These are separate
measurements, not aggregate process-tree memory. Results do not estimate
full-file runtime or establish agreement for other samples.

## Settings

```yaml
porechop_threads: 4
porechop_adapter_search_threads: 1
porechop_counter_build: /absolute/path/to/cache/build_manifest.json
```

Without `porechop_counter_build`, the rule uses the configured installed command.
The accelerated backend requires `porechop_command: porechop_abi` (the default).
Snakemake may allocate fewer threads than requested: `--cores 1` keeps discovery,
search and trimming at one thread. With four allocated threads, the validated
configuration is discovery=4, search=1, trimming=4. Requested search threads are
capped at the allocated budget. Native threads are also capped at logical CPUs.

The web launcher copies only these three Porechop settings from local
`config.yaml` into each execution configuration. Its selected CPU capacity and
parallel-job limit remain independent. For an accelerated web run, select four
CPU cores and one parallel job. Restart the local launcher after updating its
Python source. Existing saved run configurations are not automatically changed.

## Enable an existing validated build

Run in the Snakemake environment, after installing these scripts:

```bash
python scripts/configure_porechop_acceleration.py \
  --repo "$PWD" \
  --benchmark results/performance/porechop_abi/PILOT_ID/summary.json
```

The helper requires at least four completed paired trials on at least 20,000
reads, matching discovery and final output hashes, and matching counter/tool
provenance. It copies both counter builds and their upstream license into a new
directory under `~/.cache/wings/porechop`, preserves the validation summary, and
validates the promoted OpenMP executable in its original conda environment.
The original conda package and library files are not modified.

It backs up local `config.yaml` and atomically merges the three settings above.
Other values are preserved; YAML formatting/comments are rewritten by PyYAML.
The cache is outside `results`, so removal of benchmark output directories does
not remove the configured executable. The counter still links to the original
conda environment's OpenMP runtime. Rebuild and validate after replacing that
environment or its runtime.

## First workflow run

Use a separate results directory for a single sample:

```bash
snakemake --cores 4 --use-conda --dry-run --printshellcmds \
  --config results_dir=results/porechop_acceleration_check \
  -- results/porechop_acceleration_check/SAMPLE_ID/porechop/trimmed.fastq
```

Review that the DAG contains one Porechop job and the command uses the cached
manifest, then run the same command without `--dry-run`. This writes a complete
sample output in the separate directory; it does not overwrite existing sample
outputs. Monitor disk space, especially for large uncompressed FASTQ output.
Run on additional samples and compare outputs before broader deployment.

## Validation and provenance

Before processing input, the wrapper checks the build schema, pinned source
commit/archive checksum, conda prefix, Porechop_ABI version/main source hash,
thread signatures, native executable hash, and OpenMP runtime hash/probe.
An invalid explicitly configured build fails before processing. To use the
installed backend, set `porechop_counter_build: ""` and rerun.

The wrapper logs the selected backend, hashes and effective stage threads. It
also writes `trimmed.fastq.porechop-provenance.json` beside the output, including
status, timing and input/output sizes. A final output hash is omitted in normal
workflow runs to avoid an extra pass over a potentially large file. The paired
benchmark does compare final output SHA-256 hashes. Native commands use argument
lists, including paths with spaces. Each workflow job runs in a fresh process.
Discovery intermediates use a unique directory beside that job's output, passed
through the upstream `-tmp` option. Successful jobs remove their own temporary
directory; failed jobs retain it for inspection. The provenance records its path
and whether it was retained. Concurrent jobs do not share the default `./tmp`
directory. Existing files in `./tmp` are not removed by this wrapper.

## Rebuild and benchmark

The included builder uses Apple Clang and the existing conda `omp.h`/`libomp`,
downloads the pinned upstream source, verifies its checksum, and builds isolated
serial/OpenMP controls with matching optimization flags. It checks a four-thread
OpenMP probe and dynamic runtime linkage. It never replaces the installed native
counter. Building requires Python 3.12 or later for safe archive extraction;
the production wrapper runs inside the existing Python 3.10 Porechop environment.

```bash
python scripts/build_porechop_openmp.py --env-prefix /path/to/porechop/conda/env

python scripts/benchmark_porechop_abi.py \
  --input data/SAMPLE_ID.fastq.gz \
  --python /path/to/porechop/conda/env/bin/python \
  --counter-build /path/to/new/build_manifest.json \
  --phase-thread-comparison --threads 4 \
  --reads 20000 --max-bases 40000000 --repeats 2
```

Use the matching-output benchmark summary with the configuration helper. The
source recipe corresponds to Porechop_ABI commit
`0bc9f17f31d4ec1dcbab4796871cc09324cc143b` and the Bioconda 0.5.1 archive SHA-256
`10a179639ff4db0899ea43843ede4c4e48abd7e1b5edc16e84e9a573aa18041c`.

## Tests

```bash
python -m unittest discover -s tests -p 'test_porechop_acceleration.py' -v
python -m unittest discover -s tests -p 'test_benchmark_porechop_abi.py' -v
python -m unittest discover -s tests -p 'test_build_porechop_openmp.py' -v
python -m pytest -q tests/test_wings_local_runner.py
```

Wrapper/configuration tests use a synthetic tool and counter. They verify
thread bounds, unchanged output/thresholds in the fixture, quoted paths,
installed/accelerated rule branches, source/build/runtime mismatch rejection,
failure provenance, cache promotion, backups and selective web inheritance.
The shell harness replaces only Bash log mirroring to accommodate its sandbox.
Actual Snakemake DAG and native Porechop execution are checked separately on the
target machine. The build tests include a real Linux GCC OpenMP probe when
available; Apple Clang/native-counter validation comes from the macOS pilot.
