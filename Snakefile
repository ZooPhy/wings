################################################################################
# Avian influenza Nanopore workflow
#
#                             -> NanoPlot (raw-read QC; enabled by default)
# FASTQ -> Porechop -> fastplong -> IRMA -> coverage filtering
#       -> Medaka consensus/VCF -> BLAST -> VADR -> summary -> H5+NA screen -> GenoFLU
#
# The workflow is architecture-neutral. Tool portability is controlled through
# Conda environments plus an IRMA runtime that can use Apptainer/Singularity on
# Linux clusters or Docker on laptops.
################################################################################

configfile: "config.yaml"

import csv
import os
import re
import shlex
import shutil
import statistics as stats
import subprocess
import sys
import platform
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

try:
    SNAKEMAKE_VERSION = version("snakemake")
except PackageNotFoundError:
    SNAKEMAKE_VERSION = "Not captured"

from snakemake.io import glob_wildcards

shell.executable("/bin/bash")
IS_LINUX_ARM64 = (
    sys.platform.startswith("linux")
    and platform.machine().lower() in {"aarch64", "arm64"}
)

REPORTING_ENV = (
    "envs/reporting-linux-arm64.yaml"
    if IS_LINUX_ARM64
    else "envs/reporting.yaml"
)

QUARTO_ARM64 = Path(workflow.basedir) / "software" / "quarto-1.9.38" / "bin" / "quarto"
QUARTO_CMD = (
    str(QUARTO_ARM64)
    if IS_LINUX_ARM64 and QUARTO_ARM64.is_file()
    else "quarto"
)

# -----------------------------------------------------------------------------
# Configuration helpers
# -----------------------------------------------------------------------------
def as_bool(value):
    """Parse YAML booleans and common string representations safely."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1", "on"}:
            return True
        if normalized in {"false", "no", "n", "0", "off", ""}:
            return False
    return bool(value)


def config_path(key, default):
    """Return a normalized path string while preserving relative-path behavior."""
    return os.path.normpath(str(config.get(key, default)))


READS = config_path("reads_dir", "data")
RESULTS = config_path("results_dir", "results")
METADATA_FILE = config_path("metadata_file", "metadata.tsv")
METADATA_REQUIRE_ALL = as_bool(config.get("metadata_require_all_samples", True))
READ_PATTERN = str(config.get("reads_pattern", "{sample}.fastq.gz"))

if "{sample}" not in READ_PATTERN:
    raise ValueError("config key 'reads_pattern' must contain the wildcard {sample}")


def _discover_fastq_files(reads_dir: str, read_pattern: str):
    """Discover FASTQ inputs from the configured Snakemake-style sample pattern."""
    pattern = os.path.join(reads_dir, read_pattern)
    samples = sorted(set(glob_wildcards(pattern).sample))

    return {
        sample: pattern.format(sample=sample)
        for sample in samples
    }


SAMPLE_FASTQ = _discover_fastq_files(READS, READ_PATTERN)
SAMPLES = sorted(SAMPLE_FASTQ)

COVERAGE_MIN = float(config.get("coverage_min_depth", 50.0))
COVERAGE_MIN_BREADTH = float(config.get("coverage_min_breadth", 0.95))
SEGMENT_MAX_N_FRACTION = float(config.get("segment_max_n_fraction", 0.01))

if not 0.0 <= COVERAGE_MIN_BREADTH <= 1.0:
    raise ValueError("coverage_min_breadth must be between 0 and 1")
if not 0.0 <= SEGMENT_MAX_N_FRACTION <= 1.0:
    raise ValueError("segment_max_n_fraction must be between 0 and 1")

# Segment-length bounds are QC guardrails. The lower bound is a hard minimum;
# the upper bound is a review threshold only and does not block downstream analysis.
DEFAULT_SEGMENT_EXPECTED_LENGTHS = {
    "PB2": (2200, 2400),
    "PB1": (2200, 2400),
    "PA": (2100, 2300),
    "HA": (1600, 1800),
    "NP": (1450, 1600),
    "NA": (1300, 1500),
    "MP": (950, 1050),
    "NS": (800, 950),
}

configured_expected_lengths = config.get("segment_expected_lengths", {}) or {}
if not isinstance(configured_expected_lengths, dict):
    raise ValueError("segment_expected_lengths must be a YAML mapping")
unknown_length_segments = set(configured_expected_lengths) - set(DEFAULT_SEGMENT_EXPECTED_LENGTHS)
if unknown_length_segments:
    raise ValueError(
        "segment_expected_lengths contains unsupported segment(s): "
        + ", ".join(sorted(unknown_length_segments))
    )

SEGMENT_EXPECTED_LENGTHS = {}
for segment, default_bounds in DEFAULT_SEGMENT_EXPECTED_LENGTHS.items():
    bounds = configured_expected_lengths.get(segment, default_bounds)
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        raise ValueError(
            f"segment_expected_lengths[{segment!r}] must contain [minimum, maximum]"
        )
    minimum, maximum = (int(bounds[0]), int(bounds[1]))
    if minimum <= 0 or maximum < minimum:
        raise ValueError(
            f"invalid segment-length bounds for {segment}: {minimum}-{maximum}"
        )
    SEGMENT_EXPECTED_LENGTHS[segment] = (minimum, maximum)

IRMA_IMAGE = str(config.get("irma_image", "docker://ghcr.io/cdcgov/irma:v1.3.5"))
IRMA_MODULE = str(config.get("irma_module", "FLU-minion"))
IRMA_RUNTIME = str(config.get("irma_runtime", "auto")).strip().lower()

BLAST_DB = config_path("blast_db", "data/flu_db/flu")
BLAST_MIN_IDENTITY = float(config.get("blast_min_identity", 95.0))
BLAST_MIN_QUERY_COVERAGE = float(config.get("blast_min_query_coverage", 90.0))
BLAST_MAX_TARGET_SEQS = int(config.get("blast_max_target_seqs", 10))
BLAST_MAX_HSPS = int(config.get("blast_max_hsps", 1))
if not 0.0 <= BLAST_MIN_IDENTITY <= 100.0:
    raise ValueError("blast_min_identity must be between 0 and 100")
if not 0.0 <= BLAST_MIN_QUERY_COVERAGE <= 100.0:
    raise ValueError("blast_min_query_coverage must be between 0 and 100")
if BLAST_MAX_TARGET_SEQS < 1:
    raise ValueError("blast_max_target_seqs must be at least 1")
if BLAST_MAX_HSPS < 1:
    raise ValueError("blast_max_hsps must be at least 1")
PORECHOP_CMD = config.get("porechop_command", "porechop_abi")

FASTPLONG_MEAN_QUAL = int(config.get("fastplong_mean_quality", 10))
FASTPLONG_MIN_LENGTH = int(config.get("fastplong_min_length", 500))

MEDAKA_MODEL = config.get("medaka_model")
if MEDAKA_MODEL is not None:
    MEDAKA_MODEL = str(MEDAKA_MODEL).strip() or None

MEDAKA_MODEL_RECORDS = int(config.get("medaka_model_records", 100))
if MEDAKA_MODEL_RECORDS < 1:
    raise ValueError("medaka_model_records must be at least 1")

MEDAKA_FAIL_SOFT = as_bool(config.get("medaka_fail_soft", True))

NANOPLOT_INSTALL_CHROME = as_bool(
    config.get("nanoplot_install_chrome", True)
)
# Include NanoPlot raw-read QC in the default rule-all workflow.
# Set run_nanoplot: false in config.yaml to disable it.
RUN_NANOPLOT = as_bool(config.get("run_nanoplot", True))
RUN_GENOFLU = as_bool(config.get("run_genoflu", True))
RUN_VADR = as_bool(config.get("run_vadr", True))
RUN_SUMMARY = as_bool(config.get("run_summary", True))
RUN_SURVEILLANCE_EXPLORER = as_bool(config.get("run_surveillance_explorer", True))

PHYLOGENY_CONFIG = config.get("phylogeny", {}) or {}
if not isinstance(PHYLOGENY_CONFIG, dict):
    raise ValueError("config key 'phylogeny' must be a mapping")

RUN_PHYLOGENY = as_bool(PHYLOGENY_CONFIG.get("enabled", False))
PHYLOGENY_MIN_SEQUENCES = int(PHYLOGENY_CONFIG.get("min_sequences", 5))
if PHYLOGENY_MIN_SEQUENCES < 5:
    raise ValueError("phylogeny.min_sequences must be at least 5")

PHYLOGENY_DIR = config_path("phylogeny_dir", "phylogeny")
PHYLOGENY_PATTERN = str(config.get("phylogeny_pattern", "{segment}_Tree.newick"))
if "{segment}" not in PHYLOGENY_PATTERN:
    raise ValueError("config key 'phylogeny_pattern' must contain {segment}")
VADR_IMAGE = str(config.get("vadr_image", "docker://staphb/vadr:1.7"))
VADR_RUNTIME = str(config.get("vadr_runtime", "auto")).strip().lower()
VADR_MKEY = str(config.get("vadr_mkey", "flu"))
VADR_THREADS = int(config.get("vadr_threads", 1))
VADR_FAIL_SOFT = as_bool(config.get("vadr_fail_soft", False))
VADR_MODEL_DIR = config_path(
    "vadr_model_dir",
    "resources/vadr-models/vadr-models-flu-1.7-1",
)
VADR_FORCEGENE = as_bool(config.get("vadr_forcegene", True))

# Rule-level threads can be overridden in config or by a Snakemake profile.
NANOPLOT_THREADS = int(config.get("nanoplot_threads", 1))
FASTPLONG_THREADS = int(config.get("fastplong_threads", 4))
IRMA_THREADS = int(config.get("irma_threads", 4))
MEDAKA_THREADS = int(config.get("medaka_threads", 2))
BLAST_THREADS = int(config.get("blast_threads", 2))

# Canonical influenza A segment families and deterministic reporting order.
SEGSET = {"PB2", "PB1", "PA", "NP", "MP", "NS"}
SEGMENT_ORDER = {
    "HA": 0,
    "NA": 1,
    "PB2": 2,
    "PB1": 3,
    "PA": 4,
    "NP": 5,
    "MP": 6,
    "NS": 7,
}

# Discover samples directly from the FASTQ files in reads_dir.
if not SAMPLES:
    print(
        f"WARNING: no *.fastq.gz files matched {READS!r}. "
        "Check reads_dir in config.yaml."
    )


# -----------------------------------------------------------------------------
# Stable normalized IRMA interface
# -----------------------------------------------------------------------------
SEGMENT_SEQUENCE = ("HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS")


def surveillance_tree_inputs(_wildcards):
    """Return supplied segment trees that exist at DAG construction time."""
    if not RUN_SURVEILLANCE_EXPLORER:
        return []
    paths = []
    for segment in SEGMENT_SEQUENCE:
        candidate = Path(PHYLOGENY_DIR) / PHYLOGENY_PATTERN.format(segment=segment)
        if candidate.is_file() and candidate.stat().st_size > 0:
            paths.append(str(candidate))
    return paths


def irma_segments_dir(wildcards):
    """Return the normalized segment directory after the IRMA checkpoint."""
    return str(checkpoints.normalize_irma_outputs.get(sample=wildcards.sample).output.segments)


def irma_manifest_path(wildcards):
    """Return the normalized IRMA manifest after the checkpoint."""
    return str(checkpoints.normalize_irma_outputs.get(sample=wildcards.sample).output.manifest)


def _manifest_rows(wildcards):
    manifest = Path(irma_manifest_path(wildcards))
    if not manifest.is_file():
        return []
    with manifest.open(encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def segments_for_sample(wildcards):
    """Return segments with both a normalized FASTA and BAM."""
    segments_dir = Path(irma_segments_dir(wildcards))
    ready = []
    for row in _manifest_rows(wildcards):
        segment = row.get("segment", "")
        if row.get("status") != "READY" or segment not in SEGMENT_SEQUENCE:
            continue
        fasta = segments_dir / segment / "consensus.fasta"
        bam = segments_dir / segment / "alignment.bam"
        if fasta.is_file() and fasta.stat().st_size > 0 and bam.is_file() and bam.stat().st_size > 0:
            ready.append(segment)
    return sorted(ready, key=lambda segment: SEGMENT_SEQUENCE.index(segment))


def bam_path(wildcards):
    path = Path(irma_segments_dir(wildcards)) / wildcards.segment / "alignment.bam"
    if not path.is_file():
        raise ValueError(
            f"No normalized BAM found for sample={wildcards.sample}, "
            f"segment={wildcards.segment}: {path}"
        )
    return str(path)


def fasta_path(wildcards):
    path = Path(irma_segments_dir(wildcards)) / wildcards.segment / "consensus.fasta"
    if not path.is_file():
        raise ValueError(
            f"No normalized FASTA found for sample={wildcards.sample}, "
            f"segment={wildcards.segment}: {path}"
        )
    return str(path)


def optional_genoflu_input(wildcards):
    """Return GenoFLU output when enabled without scheduling GenoFLU when disabled."""
    if RUN_GENOFLU:
        return f"{RESULTS}/{wildcards.sample}/genoflu/GenoFLU.tsv"
    return os.devnull


def optional_vadr_log_input(wildcards):
    """Return the VADR log when enabled without scheduling VADR when disabled."""
    if RUN_VADR:
        return f"{RESULTS}/{wildcards.sample}/vadr/{wildcards.sample}.vadr.log"
    return os.devnull


def blast_db_files(_wildcards):
    """Stage all files belonging to the configured BLAST database prefix."""
    prefix = Path(BLAST_DB)
    files = sorted(prefix.parent.glob(f"{prefix.name}.*"), key=lambda path: path.name)
    if not files:
        raise ValueError(
            f"No BLAST database files found for prefix {BLAST_DB!r}. "
            "Build the database or update blast_db in config.yaml."
        )
    return [str(path) for path in files]


# -----------------------------------------------------------------------------
# Sample metadata
# -----------------------------------------------------------------------------
rule validate_metadata:
    input:
        metadata=METADATA_FILE
    output:
        validated=f"{RESULTS}/metadata/validated_metadata.tsv",
        report=f"{RESULTS}/metadata/metadata_validation.tsv"
    params:
        samples=",".join(SAMPLES),
        require_all_samples="true" if METADATA_REQUIRE_ALL else "false"
    conda:
        "envs/py-tools.yaml"
    script:
        "scripts/validate_metadata.py"


rule sample_metadata:
    input:
        metadata=f"{RESULTS}/metadata/validated_metadata.tsv"
    output:
        tsv=f"{RESULTS}/{{sample}}/metadata/{{sample}}.metadata.tsv"
    conda:
        "envs/py-tools.yaml"
    script:
        "scripts/extract_sample_metadata.py"


# -----------------------------------------------------------------------------
# Final targets
# -----------------------------------------------------------------------------
FINAL_TARGETS = [
    f"{RESULTS}/metadata/validated_metadata.tsv",
    f"{RESULTS}/metadata/metadata_validation.tsv",
    expand(f"{RESULTS}/{{sample}}/metadata/{{sample}}.metadata.tsv", sample=SAMPLES),
    expand(f"{RESULTS}/{{sample}}/irma/project", sample=SAMPLES),
    expand(f"{RESULTS}/{{sample}}/irma/manifest.tsv", sample=SAMPLES),
    expand(f"{RESULTS}/{{sample}}/coverage/coverage.tsv", sample=SAMPLES),
    expand(f"{RESULTS}/{{sample}}/summary/blast_top_hits.csv", sample=SAMPLES),
    expand(
        f"{RESULTS}/{{sample}}/merged/consensus_all_segments.fasta",
        sample=SAMPLES,
    ),
    expand(
        f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.tsv",
        sample=SAMPLES,
    ),
    expand(
        f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.html",
        sample=SAMPLES,
    ),
]

if RUN_NANOPLOT:
    FINAL_TARGETS.extend(
        expand(
            f"{RESULTS}/{{sample}}/nanoplot/done.txt",
            sample=SAMPLES,
        )
    )

if RUN_GENOFLU:
    FINAL_TARGETS.extend(
        expand(
            f"{RESULTS}/{{sample}}/genoflu/GenoFLU.tsv",
            sample=SAMPLES,
        )
    )

if RUN_VADR:
    FINAL_TARGETS.extend(
        [
            expand(
                f"{RESULTS}/{{sample}}/vadr/{{sample}}.vadr_summary.tsv",
                sample=SAMPLES,
            ),
            expand(
                f"{RESULTS}/{{sample}}/vadr/{{sample}}.vadr.done",
                sample=SAMPLES,
            ),
        ]
    )

if RUN_SUMMARY:
    FINAL_TARGETS.extend([
        f"{RESULTS}/run_summary/run_summary.html",
        f"{RESULTS}/run_summary/run_provenance.tsv",
        f"{RESULTS}/run_summary/run_provenance.json",
    ])


rule all:
    input:
        FINAL_TARGETS
    default_target: True

# -----------------------------------------------------------------------------
# NanoPlot
# -----------------------------------------------------------------------------
rule nanoplot:
    input:
        fastq=lambda wildcards: SAMPLE_FASTQ[wildcards.sample]
    output:
        done=touch(f"{RESULTS}/{{sample}}/nanoplot/done.txt")
    log:
        f"{RESULTS}/{{sample}}/nanoplot/nanoplot.log"
    conda:
        "envs/nanoplot.yaml"
    threads:
        NANOPLOT_THREADS
    resources:
        kaleido=1
    params:
        install_chrome="true" if NANOPLOT_INSTALL_CHROME else "false"
    shell:
        r"""
        set -euo pipefail
        mkdir -p "$(dirname {output.done:q})"
        exec > >(tee -a {log:q}) 2>&1

        if [[ {params.install_chrome:q} == "true" ]]; then
            python - <<'PY'
try:
    from choreographer.cli._cli_utils import get_chrome_sync
    get_chrome_sync()
except Exception as exc:
    print(f"Chrome setup skipped: {{exc}}")
PY
        fi

        NanoPlot \
            --fastq {input.fastq:q} \
            --threads {threads} \
            --tsv_stats \
            -o "$(dirname {output.done:q})" \
            -p {wildcards.sample:q}

        echo done > {output.done:q}
        """


# -----------------------------------------------------------------------------
# Porechop
# -----------------------------------------------------------------------------
rule porechop:
    input:
        fastq=lambda wildcards: SAMPLE_FASTQ[wildcards.sample]
    output:
        trimmed=f"{RESULTS}/{{sample}}/porechop/trimmed.fastq"
    log:
        f"{RESULTS}/{{sample}}/porechop/porechop.log"
    conda:
        "envs/porechop.yaml"
    threads:
        1
    resources:
        mem_mb=int(config.get("porechop_mem_mb", 64000)),
        time_min=int(config.get("porechop_time_min", 240))
    shell:
        r"""
        set -euo pipefail
        mkdir -p "$(dirname {output.trimmed:q})"
        exec > >(tee -a {log:q}) 2>&1
        {PORECHOP_CMD} -abi -i {input.fastq} -o {output.trimmed}
        """


# -----------------------------------------------------------------------------
# fastplong
# -----------------------------------------------------------------------------
rule fastplong:
    input:
        trimmed=f"{RESULTS}/{{sample}}/porechop/trimmed.fastq"
    output:
        filtered=f"{RESULTS}/{{sample}}/fastplong/filtered.fastq.gz",
        html=f"{RESULTS}/{{sample}}/fastplong/report.html",
        json=f"{RESULTS}/{{sample}}/fastplong/report.json"
    log:
        f"{RESULTS}/{{sample}}/fastplong/fastplong.log"
    conda:
        "envs/fastplong.yaml"
    threads:
        FASTPLONG_THREADS
    params:
        mean_quality=FASTPLONG_MEAN_QUAL,
        minimum_length=FASTPLONG_MIN_LENGTH
    shell:
        r"""
        set -euo pipefail
        mkdir -p "$(dirname {output.filtered:q})"
        exec > >(tee -a {log:q}) 2>&1

        fastplong \
            -i {input.trimmed:q} \
            -o {output.filtered:q} \
            --mean_qual {params.mean_quality} \
            --length_required {params.minimum_length} \
            --disable_adapter_trimming \
            -h {output.html:q} \
            --thread {threads} \
            -j {output.json:q}
        """


# -----------------------------------------------------------------------------
# Rename FASTQ reads with seqtk
# -----------------------------------------------------------------------------
rule seqtk_rename:
    input:
        filtered=f"{RESULTS}/{{sample}}/fastplong/filtered.fastq.gz"
    output:
        renamed=f"{RESULTS}/{{sample}}/fastplong/filtered_renamed.fastq.gz"
    log:
        f"{RESULTS}/{{sample}}/fastplong/seqtk_rename.log"
    conda:
        "envs/seqtk.yaml"
    threads:
        1
    shell:
        r"""
        set -euo pipefail
        mkdir -p "$(dirname {output.renamed:q})"
        exec > >(tee -a {log:q}) 2>&1
        seqtk rename {input.filtered:q} | gzip -c > {output.renamed:q}
        """


# -----------------------------------------------------------------------------
# IRMA
#
# Runtime selection:
#   auto        -> Apptainer, Singularity, Docker, then local IRMA
#   apptainer   -> require apptainer
#   singularity -> require singularity
#   docker      -> require Docker
#   local       -> require IRMA on PATH
# -----------------------------------------------------------------------------
rule irma:
    input:
        renamed=f"{RESULTS}/{{sample}}/fastplong/filtered_renamed.fastq.gz"
    output:
        project=directory(f"{RESULTS}/{{sample}}/irma/project")
    log:
        f"{RESULTS}/{{sample}}/irma/irma.log"
    threads:
        IRMA_THREADS
    params:
        image=IRMA_IMAGE,
        module=IRMA_MODULE,
        runtime=IRMA_RUNTIME
    run:
        input_path = Path(str(input.renamed)).resolve()
        project_path = Path(str(output.project)).resolve()
        log_path = Path(str(log[0])).resolve()

        project_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        if project_path.exists():
            shutil.rmtree(project_path)

        runtime = str(params.runtime).lower()
        allowed = {"auto", "apptainer", "singularity", "docker", "local"}
        if runtime not in allowed:
            raise ValueError(
                f"Unsupported irma_runtime={runtime!r}; choose one of {sorted(allowed)}"
            )

        if runtime == "auto":
            if shutil.which("apptainer"):
                runtime = "apptainer"
            elif shutil.which("singularity"):
                runtime = "singularity"
            elif shutil.which("docker"):
                runtime = "docker"
            elif shutil.which("IRMA"):
                runtime = "local"
            else:
                raise RuntimeError(
                    "No IRMA runtime found. Install Apptainer/Singularity, Docker, "
                    "or IRMA locally; alternatively set irma_runtime in config.yaml."
                )

        mount_root = Path(
            os.path.commonpath([str(input_path.parent), str(project_path.parent)])
        )

        if runtime in {"apptainer", "singularity"}:
            executable = shutil.which(runtime)
            if executable is None:
                raise RuntimeError(f"Requested {runtime}, but it is not on PATH")
            command = [
                executable,
                "exec",
                "--bind",
                f"{mount_root}:{mount_root}",
                str(params.image),
                "IRMA",
                str(params.module),
                str(input_path),
                str(project_path),
            ]
        elif runtime == "docker":
            executable = shutil.which("docker")
            if executable is None:
                raise RuntimeError("Requested Docker, but docker is not on PATH")
            docker_image = str(params.image)
            if docker_image.startswith("docker://"):
                docker_image = docker_image[len("docker://"):]
            command = [
                executable,
                "run",
                "--rm",
                "-v",
                f"{mount_root}:{mount_root}",
                "-w",
                str(mount_root),
                docker_image,
                "IRMA",
                str(params.module),
                str(input_path),
                str(project_path),
            ]
        else:
            executable = shutil.which("IRMA")
            if executable is None:
                raise RuntimeError("Requested local IRMA, but IRMA is not on PATH")
            command = [
                executable,
                str(params.module),
                str(input_path),
                str(project_path),
            ]

        def remove_partial_project():
            if project_path.exists():
                shutil.rmtree(project_path, ignore_errors=True)

        with log_path.open("w") as log_handle:
            log_handle.write(f"IRMA runtime: {runtime}\n")
            log_handle.write("Command: " + shlex.join(command) + "\n\n")
            log_handle.flush()
            try:
                subprocess.run(
                    command,
                    check=True,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                )
            except subprocess.CalledProcessError as exc:
                log_handle.write(
                    f"\nESCAPE_STATUS=IRMA_EXECUTION_FAILED\n"
                    f"IRMA_RETURN_CODE={exc.returncode}\n"
                )
                log_handle.flush()
                remove_partial_project()
                raise RuntimeError(
                    f"IRMA failed for sample {wildcards.sample} with return code "
                    f"{exc.returncode}. See {log_path}."
                ) from exc

        # IRMA can occasionally return exit code 0 even when an internal process
        # was killed or no QC-passing reads were available. Treat those messages
        # as execution failures so infrastructure problems cannot be reported
        # downstream as biological negatives.
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        fatal_patterns = {
            "process killed": r"(?im)^.*\bKilled\b.*$",
            "no QC-passing data": r"(?i)found no QC[’']?d data",
            "out of memory": r"(?i)(out of memory|oom-kill|oom killed|cannot allocate memory)",
            "segmentation fault": r"(?i)segmentation fault",
        }
        fatal_matches = [
            label for label, pattern in fatal_patterns.items()
            if re.search(pattern, log_text)
        ]
        if fatal_matches:
            with log_path.open("a") as log_handle:
                log_handle.write(
                    "\nESCAPE_STATUS=IRMA_INTERNAL_FAILURE\n"
                    "ESCAPE_FAILURE_REASONS=" + ", ".join(fatal_matches) + "\n"
                )
            remove_partial_project()
            raise RuntimeError(
                f"IRMA reported an internal failure for sample {wildcards.sample}: "
                f"{', '.join(fatal_matches)}. See {log_path}."
            )

        if not project_path.is_dir():
            raise RuntimeError(
                f"IRMA did not create the expected project directory for "
                f"sample {wildcards.sample}. See {log_path}."
            )

        with log_path.open("a") as log_handle:
            log_handle.write("\nESCAPE_STATUS=IRMA_COMPLETED\n")


# -----------------------------------------------------------------------------
# Normalize IRMA outputs
#
# This is intentionally a checkpoint separate from the expensive IRMA assembly.
# Changes to normalization or candidate-selection logic therefore rerun only
# normalization and downstream analysis, while the completed IRMA project is reused.
# -----------------------------------------------------------------------------
checkpoint normalize_irma_outputs:
    input:
        project=f"{RESULTS}/{{sample}}/irma/project",
        normalizer="scripts/normalize_irma_outputs.py"
    output:
        segments=directory(f"{RESULTS}/{{sample}}/irma/segments"),
        manifest=f"{RESULTS}/{{sample}}/irma/manifest.tsv"
    log:
        f"{RESULTS}/{{sample}}/irma/normalize.log"
    conda:
        "envs/pysam.yaml"
    run:
        project_path = Path(str(input.project)).resolve()
        normalizer_path = Path(str(input.normalizer)).resolve()
        segments_path = Path(str(output.segments)).resolve()
        manifest_path = Path(str(output.manifest)).resolve()
        log_path = Path(str(log[0])).resolve()

        segments_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        if segments_path.exists():
            shutil.rmtree(segments_path)
        if manifest_path.exists():
            manifest_path.unlink()

        def remove_partial_normalized_outputs():
            if segments_path.exists():
                shutil.rmtree(segments_path, ignore_errors=True)
            if manifest_path.exists():
                manifest_path.unlink()

        normalize_command = [
            sys.executable,
            str(normalizer_path),
            "--project",
            str(project_path),
            "--segments",
            str(segments_path),
            "--manifest",
            str(manifest_path),
            "--sample",
            str(wildcards.sample),
        ]
        with log_path.open("w") as log_handle:
            log_handle.write("Normalization command: " + shlex.join(normalize_command) + "\n")
            log_handle.flush()
            try:
                subprocess.run(
                    normalize_command,
                    check=True,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                )
            except subprocess.CalledProcessError as exc:
                log_handle.write(
                    f"\nESCAPE_STATUS=IRMA_NORMALIZATION_FAILED\n"
                    f"NORMALIZER_RETURN_CODE={exc.returncode}\n"
                )
                log_handle.flush()
                remove_partial_normalized_outputs()
                raise RuntimeError(
                    f"IRMA output normalization failed for sample {wildcards.sample}. "
                    f"See {log_path}."
                ) from exc

        if not manifest_path.is_file() or manifest_path.stat().st_size == 0:
            remove_partial_normalized_outputs()
            raise RuntimeError(
                f"IRMA normalization did not create a non-empty manifest for "
                f"sample {wildcards.sample}. See {log_path}."
            )

        with manifest_path.open(encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required_columns = {"segment", "status"}
            if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
                fieldnames = reader.fieldnames or []
                remove_partial_normalized_outputs()
                raise RuntimeError(
                    f"IRMA manifest for sample {wildcards.sample} is malformed; "
                    f"required columns are {sorted(required_columns)}, found "
                    f"{fieldnames}. See {log_path}."
                )
            manifest_rows = list(reader)

        ready_segments = sorted({
            row.get("segment", "")
            for row in manifest_rows
            if row.get("status") == "READY" and row.get("segment") in SEGMENT_SEQUENCE
        })
        with log_path.open("a") as log_handle:
            log_handle.write("\nESCAPE_STATUS=IRMA_NORMALIZATION_COMPLETED\n")
            log_handle.write(f"ESCAPE_READY_SEGMENT_COUNT={len(ready_segments)}\n")
            log_handle.write(
                "ESCAPE_READY_SEGMENTS="
                + (",".join(ready_segments) if ready_segments else "NONE")
                + "\n"
            )


# -----------------------------------------------------------------------------
# Pre-polishing segment QC
#
# The legacy coverage_flags path is retained for compatibility, but the flag now
# represents the overall segment QC decision: coverage + expected length +
# consensus N content.
# -----------------------------------------------------------------------------
rule check_coverage:
    input:
        segments_dir=irma_segments_dir,
        manifest=irma_manifest_path
    output:
        flag=f"{RESULTS}/{{sample}}/coverage_flags/{{segment}}.flag",
        stats=f"{RESULTS}/{{sample}}/coverage_stats/{{segment}}.tsv"
    params:
        min_median_depth=COVERAGE_MIN,
        min_breadth=COVERAGE_MIN_BREADTH,
        max_n_fraction=SEGMENT_MAX_N_FRACTION,
        expected_length_min=lambda wildcards: SEGMENT_EXPECTED_LENGTHS[wildcards.segment][0],
        expected_length_max=lambda wildcards: SEGMENT_EXPECTED_LENGTHS[wildcards.segment][1]
    conda:
        "envs/coverage.yaml"
    script:
        "scripts/check_coverage.py"


# -----------------------------------------------------------------------------
# Per-sample segment QC summary
# -----------------------------------------------------------------------------
rule coverage_table:
    input:
        manifest=irma_manifest_path,
        flags=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/coverage_flags/{segment}.flag"
            for segment in SEGMENT_SEQUENCE
        ],
        stats=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/coverage_stats/{segment}.tsv"
            for segment in SEGMENT_SEQUENCE
        ]
    output:
        tsv=f"{RESULTS}/{{sample}}/coverage/coverage.tsv"
    conda:
        "envs/pysam.yaml"
    script:
        "scripts/coverage_table.py"


# -----------------------------------------------------------------------------
# Resolve Medaka model from original FASTQ metadata
# -----------------------------------------------------------------------------
rule resolve_medaka_model:
    input:
        fastq=lambda wildcards: SAMPLE_FASTQ[wildcards.sample]
    output:
        model=f"{RESULTS}/{{sample}}/medaka/model.tsv"
    params:
        max_records=MEDAKA_MODEL_RECORDS
    shell:
        r"""
        set -euo pipefail

        python scripts/resolve_medaka_model.py \
            --fastq {input.fastq:q} \
            --output {output.model:q} \
            --max-records {params.max_records}
        """


# -----------------------------------------------------------------------------
# Medaka inference
# -----------------------------------------------------------------------------
rule medaka_inference:
    input:
        bam=bam_path,
        fasta=fasta_path,
        flag=f"{RESULTS}/{{sample}}/coverage_flags/{{segment}}.flag",
        model=f"{RESULTS}/{{sample}}/medaka/model.tsv"
    output:
        features=f"{RESULTS}/{{sample}}/medaka/{{segment}}/features.hdf",
        status=f"{RESULTS}/{{sample}}/medaka/{{segment}}/inference.status.tsv"
    log:
        f"{RESULTS}/{{sample}}/medaka/{{segment}}/medaka_inference.log"
    conda:
        "envs/medaka.yaml"
    threads:
        MEDAKA_THREADS
    resources:
        mem_mb=int(config.get("medaka_inference_mem_mb", 16000)),
        time_min=int(config.get("medaka_inference_time_min", 240))
    params:
        model_override=MEDAKA_MODEL or "",
        use_override="true" if MEDAKA_MODEL else "false",
        fail_soft="true" if MEDAKA_FAIL_SOFT else "false"
    shell:
        r"""
        set -euo pipefail
        mkdir -p "$(dirname {output.features:q})"

        if [[ {params.use_override:q} == "true" ]]; then
            model={params.model_override:q}
            model_source="config override"
        else
            model="$(awk -F '\t' 'NR == 2 {{print $3}}' {input.model:q})"
            model_source="FASTQ metadata"
        fi

        if [[ -z "$model" ]]; then
            echo -e "status\tmodel_source\tmodel\treason\nFAILED\t$model_source\t\tmodel resolution failed" > {output.status:q}
            echo "Could not resolve Medaka consensus model from {input.model:q}." > {log:q}
            exit 1
        fi

        echo "Medaka consensus selector: $model" > {log:q}
        echo "Medaka model source: $model_source" >> {log:q}

        if ! grep -q '^PASS$' {input.flag:q}; then
            echo "Segment did not pass segment QC; Medaka inference skipped." >> {log:q}
            : > {output.features:q}
            echo -e "status\tmodel_source\tmodel\treason\nSKIPPED_QC\t$model_source\t$model\tsegment_qc_failed" > {output.status:q}
        elif medaka inference {input.bam:q} {output.features:q} \
                --threads {threads} \
                --model "$model" \
                >> {log:q} 2>&1 && [[ -s {output.features:q} ]]; then
            echo -e "status\tmodel_source\tmodel\treason\nSUCCESS\t$model_source\t$model\tinference_completed" > {output.status:q}
        elif [[ {params.fail_soft:q} == "true" ]]; then
            echo "Medaka inference failed; continuing with explicit FAILED status because medaka_fail_soft=true." >> {log:q}
            : > {output.features:q}
            echo -e "status\tmodel_source\tmodel\treason\nFAILED\t$model_source\t$model\tmedaka_inference_failed" > {output.status:q}
        else
            echo "Medaka inference failed and medaka_fail_soft=false." >> {log:q}
            exit 1
        fi
        """


# -----------------------------------------------------------------------------
# Medaka consensus
# -----------------------------------------------------------------------------
rule medaka_consensus:
    input:
        features=f"{RESULTS}/{{sample}}/medaka/{{segment}}/features.hdf",
        inference_status=f"{RESULTS}/{{sample}}/medaka/{{segment}}/inference.status.tsv",
        fasta=fasta_path,
        flag=f"{RESULTS}/{{sample}}/coverage_flags/{{segment}}.flag"
    output:
        consensus=f"{RESULTS}/{{sample}}/medaka/{{segment}}/consensus.fasta",
        status=f"{RESULTS}/{{sample}}/medaka/{{segment}}/consensus.status.tsv"
    log:
        f"{RESULTS}/{{sample}}/medaka/{{segment}}/medaka_sequence.log"
    conda:
        "envs/medaka.yaml"
    threads:
        MEDAKA_THREADS
    params:
        fail_soft="true" if MEDAKA_FAIL_SOFT else "false"
    shell:
        r"""
        set -euo pipefail
        mkdir -p "$(dirname {output.consensus:q})"

        inference_status="$(awk -F '\t' 'NR == 2 {{print $1}}' {input.inference_status:q})"

        if ! grep -q '^PASS$' {input.flag:q}; then
            echo "Segment did not pass segment QC; consensus skipped." > {log:q}
            : > {output.consensus:q}
            echo -e "status\tconsensus_source\treason\nSKIPPED_QC\tNONE\tsegment_qc_failed" > {output.status:q}
        elif [[ "$inference_status" == "SUCCESS" && -s {input.features:q} ]]; then
            if medaka sequence \
                --threads {threads} \
                {input.features:q} \
                {input.fasta:q} \
                {output.consensus:q} \
                > {log:q} 2>&1 && [[ -s {output.consensus:q} ]]; then
                echo -e "status\tconsensus_source\treason\nSUCCESS\tMEDAKA\tpolishing_completed" > {output.status:q}
            elif [[ {params.fail_soft:q} == "true" ]]; then
                echo "Medaka polishing failed; falling back to the QC-passing IRMA consensus because medaka_fail_soft=true." >> {log:q}
                cp {input.fasta:q} {output.consensus:q}
                echo -e "status\tconsensus_source\treason\nFAILED\tIRMA_FALLBACK\tmedaka_consensus_failed" > {output.status:q}
            else
                echo "Medaka polishing failed and medaka_fail_soft=false." >> {log:q}
                exit 1
            fi
        elif [[ "$inference_status" == "FAILED" && {params.fail_soft:q} == "true" ]]; then
            echo "Medaka inference failed; falling back to the QC-passing IRMA consensus because medaka_fail_soft=true." > {log:q}
            cp {input.fasta:q} {output.consensus:q}
            echo -e "status\tconsensus_source\treason\nFAILED\tIRMA_FALLBACK\tmedaka_inference_failed" > {output.status:q}
        elif [[ "$inference_status" == "FAILED" ]]; then
            echo "Medaka inference failed and medaka_fail_soft=false." > {log:q}
            exit 1
        elif [[ "$inference_status" == "SKIPPED_QC" ]]; then
            echo "Medaka inference was skipped because segment QC failed; no consensus generated." > {log:q}
            : > {output.consensus:q}
            echo -e "status\tconsensus_source\treason\nSKIPPED_QC\tNONE\tinference_skipped_qc" > {output.status:q}
        elif [[ {params.fail_soft:q} == "true" ]]; then
            echo "Medaka inference status or features were invalid; falling back to the QC-passing IRMA consensus because medaka_fail_soft=true." > {log:q}
            cp {input.fasta:q} {output.consensus:q}
            echo -e "status\tconsensus_source\treason\nFAILED\tIRMA_FALLBACK\tinvalid_inference_state" > {output.status:q}
        else
            echo "Medaka inference status or features were invalid and medaka_fail_soft=false." > {log:q}
            exit 1
        fi
        """


# -----------------------------------------------------------------------------
# Medaka VCF
# -----------------------------------------------------------------------------
rule medaka_vcf:
    input:
        features=f"{RESULTS}/{{sample}}/medaka/{{segment}}/features.hdf",
        inference_status=f"{RESULTS}/{{sample}}/medaka/{{segment}}/inference.status.tsv",
        fasta=fasta_path,
        flag=f"{RESULTS}/{{sample}}/coverage_flags/{{segment}}.flag"
    output:
        vcf=f"{RESULTS}/{{sample}}/medaka/{{segment}}/variants.vcf",
        status=f"{RESULTS}/{{sample}}/medaka/{{segment}}/variants.status.tsv"
    log:
        f"{RESULTS}/{{sample}}/medaka/{{segment}}/medaka_variant.log"
    conda:
        "envs/medaka.yaml"
    threads:
        1
    resources:
        mem_mb=int(config.get("medaka_variant_mem_mb", 8000)),
        time_min=int(config.get("medaka_variant_time_min", 60))
    params:
        fail_soft="true" if MEDAKA_FAIL_SOFT else "false"
    shell:
        r"""
        set -euo pipefail
        mkdir -p "$(dirname {output.vcf:q})"

        medaka --version >> {log:q} 2>&1 || true
        python -c "import medaka; print('python medaka __version__ =', getattr(medaka, '__version__', '<no __version__>'))" \
            >> {log:q} 2>&1 || true

        inference_status="$(awk -F '\t' 'NR == 2 {{print $1}}' {input.inference_status:q})"

        if ! grep -q '^PASS$' {input.flag:q}; then
            echo "Segment did not pass segment QC; VCF generation skipped." >> {log:q}
            : > {output.vcf:q}
            echo -e "status\treason\nSKIPPED_QC\tsegment_qc_failed" > {output.status:q}
        elif [[ "$inference_status" == "FAILED" ]]; then
            echo "Medaka inference failed; VCF generation skipped." >> {log:q}
            : > {output.vcf:q}
            echo -e "status\treason\nFAILED\tmedaka_inference_failed" > {output.status:q}
        elif [[ "$inference_status" == "SUCCESS" && -s {input.features:q} ]]; then
            rm -f {output.vcf:q}

            if medaka vcf \
                {input.features:q} \
                {input.fasta:q} \
                {output.vcf:q} \
                >> {log:q} 2>&1; then

                if [[ ! -s {output.vcf:q} ]]; then
                    found_vcf="$(
                        find "$(dirname {output.vcf:q})" \
                            -type f \
                            -name '*.vcf' \
                            -size +0c \
                            | LC_ALL=C sort \
                            | head -n 1 || true
                    )"

                    if [[ -n "$found_vcf" && "$found_vcf" != {output.vcf:q} ]]; then
                        cp "$found_vcf" {output.vcf:q}
                    fi
                fi

                if [[ -s {output.vcf:q} ]]; then
                    echo -e "status\treason\nSUCCESS\tvcf_generated" > {output.status:q}
                elif [[ {params.fail_soft:q} == "true" ]]; then
                    echo "Medaka VCF command completed without producing a non-empty VCF; continuing with explicit FAILED status because medaka_fail_soft=true." >> {log:q}
                    : > {output.vcf:q}
                    echo -e "status\treason\nFAILED\tmedaka_vcf_empty_output" > {output.status:q}
                else
                    echo "Medaka VCF command completed without producing a non-empty VCF and medaka_fail_soft=false." >> {log:q}
                    exit 1
                fi

            elif [[ {params.fail_soft:q} == "true" ]]; then
                echo "Medaka VCF generation failed; continuing with explicit FAILED status because medaka_fail_soft=true." >> {log:q}
                : > {output.vcf:q}
                echo -e "status\treason\nFAILED\tmedaka_vcf_failed" > {output.status:q}
            else
                echo "Medaka VCF generation failed and medaka_fail_soft=false." >> {log:q}
                exit 1
            fi
        elif [[ "$inference_status" == "SKIPPED_QC" ]]; then
            echo "Medaka inference was skipped because segment QC failed; VCF generation skipped." >> {log:q}
            : > {output.vcf:q}
            echo -e "status\treason\nSKIPPED_QC\tinference_skipped_qc" > {output.status:q}
        elif [[ {params.fail_soft:q} == "true" ]]; then
            echo "Medaka inference state or features were invalid; VCF generation recorded as FAILED." >> {log:q}
            : > {output.vcf:q}
            echo -e "status\treason\nFAILED\tinvalid_inference_output" > {output.status:q}
        else
            echo "Medaka inference state or features were invalid and medaka_fail_soft=false." >> {log:q}
            exit 1
        fi
        """

# -----------------------------------------------------------------------------
# Prepare segment-QC-qualified polished consensuses for VADR
# -----------------------------------------------------------------------------
rule prepare_vadr_input:
    input:
        consensus=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/medaka/{segment}/consensus.fasta"
            for segment in segments_for_sample(wildcards)
        ],
        flags=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/coverage_flags/{segment}.flag"
            for segment in segments_for_sample(wildcards)
        ]
    output:
        fasta=f"{RESULTS}/{{sample}}/vadr/{{sample}}.vadr_input.fasta"
    conda:
        "envs/py-tools.yaml"
    script:
        "scripts/prepare_vadr_input.py"


# -----------------------------------------------------------------------------
# VADR influenza annotation
#
# Runtime selection:
#   auto        -> local v-annotate.pl, Docker, Apptainer, then Singularity
#   local       -> require v-annotate.pl on PATH
#   docker      -> run the staphb/vadr image (amd64 emulation on Apple Silicon)
#   apptainer   -> run the configured image with Apptainer
#   singularity -> run the configured image with Singularity
# -----------------------------------------------------------------------------
rule vadr_annotate:
    input:
        fasta=f"{RESULTS}/{{sample}}/vadr/{{sample}}.vadr_input.fasta"
    output:
        outdir=directory(f"{RESULTS}/{{sample}}/vadr/output"),
        done=touch(f"{RESULTS}/{{sample}}/vadr/{{sample}}.vadr.done")
    log:
        f"{RESULTS}/{{sample}}/vadr/{{sample}}.vadr.log"
    threads:
        VADR_THREADS
    resources:
        mem_mb=int(config.get("vadr_mem_mb", 8000)),
        time_min=int(config.get("vadr_time_min", 120))
    params:
        image=VADR_IMAGE,
        runtime=VADR_RUNTIME,
        mkey=VADR_MKEY,
        model_dir=VADR_MODEL_DIR,
        forcegene="true" if VADR_FORCEGENE else "false",
        fail_soft="true" if VADR_FAIL_SOFT else "false"
    run:
        input_path = Path(str(input.fasta)).resolve()
        outdir = Path(str(output.outdir)).resolve()
        done_path = Path(str(output.done)).resolve()
        log_path = Path(str(log[0])).resolve()
        
        outdir.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if outdir.exists():
            shutil.rmtree(outdir)
        outdir.mkdir(parents=True)

        # An empty input is a legitimate result when no segment passes coverage.
        if input_path.stat().st_size == 0:
            log_path.write_text("No segment-QC-qualified consensus sequences; VADR skipped.\n")
            done_path.touch()
        else:
            model_dir = Path(str(params.model_dir)).resolve()

            if not model_dir.is_dir():
                raise RuntimeError(
                    f"VADR model directory not found: {model_dir}. "
                    "Install the pinned influenza models or update vadr_model_dir."
                )

            required_model_files = [
                model_dir / f"{params.mkey}.minfo",
                model_dir / f"{params.mkey}.cm",
                model_dir / f"{params.mkey}.fa",
            ]
            missing_model_files = [
                str(path) for path in required_model_files if not path.is_file()
            ]
            if missing_model_files:
                raise RuntimeError(
                    "VADR model directory is incomplete; missing: "
                    + ", ".join(missing_model_files)
                )

            runtime = str(params.runtime).lower()
            allowed = {"auto", "local", "docker", "apptainer", "singularity"}
            if runtime not in allowed:
                raise ValueError(
                    f"Unsupported vadr_runtime={runtime!r}; choose one of {sorted(allowed)}"
                )
            if runtime == "auto":
                if shutil.which("v-annotate.pl"):
                    runtime = "local"
                elif shutil.which("docker"):
                    runtime = "docker"
                elif shutil.which("apptainer"):
                    runtime = "apptainer"
                elif shutil.which("singularity"):
                    runtime = "singularity"
                else:
                    raise RuntimeError(
                        "No VADR runtime found. Install VADR locally or provide Docker, "
                        "Apptainer, or Singularity; alternatively set vadr_runtime."
                    )

            prefix = wildcards.sample
            vadr_args = [
                "v-annotate.pl", "-f", "--split", "--cpu", str(threads),
                "-r", "--atgonly", "--xnocomp", "--nomisc",
                "--alt_fail", "extrant5,extrant3",
                "--mkey", str(params.mkey),
            ]

            if str(params.forcegene).lower() == "true":
                vadr_args.append("--forcegene")
            mount_root = Path(
                os.path.commonpath([str(input_path.parent), str(outdir.parent)])
            )

            if runtime == "local":
                command = [
                    *vadr_args,
                    "--mdir", str(model_dir),
                    str(input_path), prefix,
                ]

            elif runtime == "docker":
                image = str(params.image)
                if image.startswith("docker://"):
                    image = image[len("docker://"):]

                command = [
                    "docker", "run", "--rm",
                    "--platform", "linux/amd64",
                    "-v", f"{mount_root}:{mount_root}",
                    "-v", f"{model_dir}:/models:ro",
                    "-w", str(outdir),
                    image,
                    *vadr_args,
                    "--mdir", "/models",
                    str(input_path), prefix,
                ]

            else:
                executable = shutil.which(runtime)
                if executable is None:
                    raise RuntimeError(
                        f"Requested {runtime}, but it is not on PATH"
                    )

                command = [
                    executable, "exec",
                    "--bind", f"{mount_root}:{mount_root}",
                    "--bind", f"{model_dir}:/models:ro",
                    str(params.image),
                    *vadr_args,
                    "--mdir", "/models",
                    str(input_path), prefix,
                ]
            with log_path.open("w") as log_handle:
                completed = subprocess.run(
                    command, cwd=outdir, stdout=log_handle,
                    stderr=subprocess.STDOUT, text=True,
                )
            if completed.returncode != 0:
                if str(params.fail_soft).lower() == "true":
                    with log_path.open("a") as log_handle:
                        log_handle.write(
                            f"VADR exited with code {completed.returncode}; "
                            "continuing because vadr_fail_soft=true.\n"
                        )
                else:
                    raise RuntimeError(
                        f"VADR failed with exit code {completed.returncode}; see {log_path}"
                    )

            nested = outdir / prefix
            if nested.is_dir():
                for path in nested.glob(f"{prefix}.vadr.*"):
                    shutil.move(str(path), str(outdir / path.name))
                shutil.rmtree(nested, ignore_errors=True)
            done_path.touch()


# -----------------------------------------------------------------------------
# Compact VADR status table for reporting
# -----------------------------------------------------------------------------
rule summarize_vadr:
    input:
        done=f"{RESULTS}/{{sample}}/vadr/{{sample}}.vadr.done",
        outdir=f"{RESULTS}/{{sample}}/vadr/output"
    output:
        tsv=f"{RESULTS}/{{sample}}/vadr/{{sample}}.vadr_summary.tsv"
    conda:
        "envs/py-tools.yaml"
    script:
        "scripts/summarize_vadr.py"

# -----------------------------------------------------------------------------
# BLAST
# -----------------------------------------------------------------------------
rule blastn:
    input:
        fasta=f"{RESULTS}/{{sample}}/medaka/{{segment}}/consensus.fasta",
        flag=f"{RESULTS}/{{sample}}/coverage_flags/{{segment}}.flag",
        database=blast_db_files
    output:
        txt=f"{RESULTS}/{{sample}}/blast/{{segment}}.blast.txt"
    log:
        f"{RESULTS}/{{sample}}/blast/{{segment}}.log"
    conda:
        "envs/blast.yaml"
    threads:
        BLAST_THREADS
    params:
        database_prefix=BLAST_DB,
        max_target_seqs=BLAST_MAX_TARGET_SEQS,
        max_hsps=BLAST_MAX_HSPS
    shell:
        r"""
        set -euo pipefail
        mkdir -p "$(dirname {output.txt:q})"

        if [[ ! -s {input.fasta:q} ]] || ! grep -q '^PASS$' {input.flag:q}; then
            echo "Segment did not pass segment QC or consensus is empty; BLAST skipped." > {log:q}
            : > {output.txt:q}
            exit 0
        fi

        blastn \
            -query {input.fasta:q} \
            -db {params.database_prefix:q} \
            -outfmt '6 qseqid sacc stitle pident length qlen qstart qend sstart send evalue bitscore' \
            -max_target_seqs {params.max_target_seqs} \
            -max_hsps {params.max_hsps} \
            -num_threads {threads} \
            2> {log:q} \
          | LC_ALL=C sort -t $'\t' -k12,12gr -k11,11g -k4,4gr \
          > {output.txt:q}
        """


# -----------------------------------------------------------------------------
# BLAST summary
# -----------------------------------------------------------------------------
rule summarize_blast:
    input:
        blast_files=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/blast/{segment}.blast.txt"
            for segment in segments_for_sample(wildcards)
        ],
        flags=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/coverage_flags/{segment}.flag"
            for segment in SEGMENT_SEQUENCE
        ]
    output:
        csv=f"{RESULTS}/{{sample}}/summary/blast_top_hits.csv"
    params:
        min_identity=BLAST_MIN_IDENTITY,
        min_query_coverage=BLAST_MIN_QUERY_COVERAGE
    conda:
        "envs/py-tools.yaml"
    script:
        "scripts/summarize_blast.py"


# -----------------------------------------------------------------------------
# Concatenate polished segment consensuses
#
# The VCF list is an explicit dependency so variant files are generated during
# a normal rule-all run, even though only consensus FASTAs are concatenated.
# -----------------------------------------------------------------------------
rule concat_consensus:
    input:
        consensus=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/medaka/{segment}/consensus.fasta"
            for segment in segments_for_sample(wildcards)
        ],
        vcfs=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/medaka/{segment}/variants.vcf"
            for segment in segments_for_sample(wildcards)
        ]
    output:
        merged=f"{RESULTS}/{{sample}}/merged/consensus_all_segments.fasta"
    log:
        f"{RESULTS}/{{sample}}/merged/concat_consensus.log"
    run:
        output_path = Path(str(output.merged))
        log_path = Path(str(log[0]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        consensus_paths = [Path(str(path)) for path in input.consensus]
        with output_path.open("wb") as destination:
            for consensus_path in consensus_paths:
                if not consensus_path.exists() or consensus_path.stat().st_size == 0:
                    continue
                with consensus_path.open("rb") as source:
                    shutil.copyfileobj(source, destination)

        log_path.write_text(
            "Concatenated consensus files:\n"
            + "".join(f"- {path}\n" for path in consensus_paths)
        )


# -----------------------------------------------------------------------------
# H5 + QC-passing NA screen
#
# GenoFLU eligibility is based on a QC-passing H5 HA together with a
# QC-passing, subtype-resolved NA segment of any neuraminidase subtype.
# The NA subtype is retained for reporting but does not need to be N1.
# DETECTED means the sample is eligible for GenoFLU; NOT_DETECTED means HA and
# NA are both informative but HA is not H5; INDETERMINATE means HA or NA lacks
# sufficient QC-qualified evidence.
# -----------------------------------------------------------------------------
rule detect_h5_with_na:
    input:
        ha_flag=f"{RESULTS}/{{sample}}/coverage_flags/HA.flag",
        na_flag=f"{RESULTS}/{{sample}}/coverage_flags/NA.flag",
        ha_stats=f"{RESULTS}/{{sample}}/coverage_stats/HA.tsv",
        na_stats=f"{RESULTS}/{{sample}}/coverage_stats/NA.tsv"
    output:
        flag=f"{RESULTS}/{{sample}}/genoflu/h5.flag"
    log:
        f"{RESULTS}/{{sample}}/genoflu/detect_h5_with_na.log"
    params:
        threshold=COVERAGE_MIN,
        min_breadth=COVERAGE_MIN_BREADTH,
        max_n_fraction=SEGMENT_MAX_N_FRACTION
    run:
        def read_flag(path):
            try:
                return Path(str(path)).read_text().strip()
            except OSError:
                return "MISSING"

        def selected_contig(path):
            try:
                with Path(str(path)).open() as handle:
                    reader = csv.DictReader(handle, delimiter="\t")
                    row = next(reader, None)
                    if not row:
                        return "NA"
                    return row.get("selected_contig") or row.get("chosen_table", "NA")
            except OSError:
                return "NA"

        ha_status = read_flag(input.ha_flag)
        na_status = read_flag(input.na_flag)
        ha_contig = selected_contig(input.ha_stats)
        na_contig = selected_contig(input.na_stats)

        is_h5 = ha_contig.startswith("A_HA_H5")
        ha_informative = (
            ha_status == "PASS"
            and ha_contig not in {"", "NA", "MISSING"}
        )
        na_informative = (
            na_status == "PASS"
            and na_contig not in {"", "NA", "MISSING"}
            and na_contig.startswith("A_NA_N")
        )

        if not ha_informative or not na_informative:
            screen_status = "INDETERMINATE"
            reasons = []
            if not ha_informative:
                reasons.append(
                    f"HA_not_informative(status={ha_status},contig={ha_contig})"
                )
            if not na_informative:
                reasons.append(
                    f"NA_not_informative_or_unresolved(status={na_status},contig={na_contig})"
                )
            screen_reason = ";".join(reasons)
        elif is_h5:
            screen_status = "DETECTED"
            screen_reason = (
                "QC-passing H5-associated HA and QC-passing subtype-resolved NA detected"
            )
        else:
            screen_status = "NOT_DETECTED"
            screen_reason = (
                "QC-passing HA and NA were informative, but HA was not identified as H5"
            )

        output_path = Path(str(output.flag))
        log_path = Path(str(log[0]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(f"{screen_status}\n")
        log_path.write_text(
            f"sample={wildcards.sample}\n"
            f"segment_qc_depth_threshold={params.threshold}\n"
            f"segment_qc_minimum_breadth={params.min_breadth}\n"
            f"segment_qc_max_n_fraction={params.max_n_fraction}\n"
            f"HA_status={ha_status}\n"
            f"HA_selected_contig={ha_contig}\n"
            f"HA_informative={ha_informative}\n"
            f"HA_is_H5={is_h5}\n"
            f"NA_status={na_status}\n"
            f"NA_selected_contig={na_contig}\n"
            f"NA_informative={na_informative}\n"
            f"H5_with_NA_screen={screen_status}\n"
            f"H5_with_NA_reason={screen_reason}\n"
        )


# -----------------------------------------------------------------------------
# Produce the summary of the individual samples
# -----------------------------------------------------------------------------
rule sample_summary:
    input:
        metadata=f"{RESULTS}/{{sample}}/metadata/{{sample}}.metadata.tsv",
        fastplong=f"{RESULTS}/{{sample}}/fastplong/report.json",
        coverage=f"{RESULTS}/{{sample}}/coverage/coverage.tsv",
        blast=f"{RESULTS}/{{sample}}/summary/blast_top_hits.csv",
        h5=f"{RESULTS}/{{sample}}/genoflu/h5.flag",  # compatibility key; H5+NA gate
        genoflu=optional_genoflu_input,
        consensus=f"{RESULTS}/{{sample}}/merged/consensus_all_segments.fasta"
    output:
        tsv=f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.tsv"
    conda:
        REPORTING_ENV
    script:
        "scripts/sample_summary.py"


# -----------------------------------------------------------------------------
# Produce the summary of the individual samples in HTML
# -----------------------------------------------------------------------------
rule sample_summary_html:
    input:
        summary=f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.tsv",
        coverage=f"{RESULTS}/{{sample}}/coverage/coverage.tsv",
        blast=f"{RESULTS}/{{sample}}/summary/blast_top_hits.csv",
        template="scripts/sample_summary.qmd",
        genoflu=optional_genoflu_input,
        vadr_log=optional_vadr_log_input,
        medaka_inference_status=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/medaka/{segment}/inference.status.tsv"
            for segment in segments_for_sample(wildcards)
        ],
        medaka_consensus_status=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/medaka/{segment}/consensus.status.tsv"
            for segment in segments_for_sample(wildcards)
        ],
        medaka_variant_status=lambda wildcards: [
            f"{RESULTS}/{wildcards.sample}/medaka/{segment}/variants.status.tsv"
            for segment in segments_for_sample(wildcards)
        ],
        css="scripts/report/sample-report.css",
        report_html="scripts/report/escape-report.html",
        report_js="scripts/report/escape-report.js",
        constellation_css="scripts/report/genome-constellation.css",
        constellation_js="scripts/report/genome-constellation.js"
    output:
        html=f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.html"
    params:
        coverage_threshold=COVERAGE_MIN,
        coverage_breadth_threshold=COVERAGE_MIN_BREADTH,
        max_n_fraction=SEGMENT_MAX_N_FRACTION,
        snakemake_version=SNAKEMAKE_VERSION,
        quarto=QUARTO_CMD,
    conda:
        REPORTING_ENV
    shell:
        r"""
        set -euo pipefail

        output_dir="$(cd "$(dirname {output.html:q})" && pwd)"
        summary_abs="$(cd "$(dirname {input.summary:q})" && pwd)/$(basename {input.summary:q})"
        coverage_abs="$(cd "$(dirname {input.coverage:q})" && pwd)/$(basename {input.coverage:q})"
        blast_abs="$(cd "$(dirname {input.blast:q})" && pwd)/$(basename {input.blast:q})"
        genoflu_abs="$(cd "$(dirname {input.genoflu:q})" && pwd)/$(basename {input.genoflu:q})"
        vadr_log_abs="$(cd "$(dirname {input.vadr_log:q})" && pwd)/$(basename {input.vadr_log:q})"
        template_abs="$(cd "$(dirname {input.template:q})" && pwd)/$(basename {input.template:q})"
        css_abs="$(cd "$(dirname {input.css:q})" && pwd)/$(basename {input.css:q})"
        report_html_abs="$(cd "$(dirname {input.report_html:q})" && pwd)/$(basename {input.report_html:q})"
        report_js_abs="$(cd "$(dirname {input.report_js:q})" && pwd)/$(basename {input.report_js:q})"
        constellation_css_abs="$(cd "$(dirname {input.constellation_css:q})" && pwd)/$(basename {input.constellation_css:q})"
        constellation_js_abs="$(cd "$(dirname {input.constellation_js:q})" && pwd)/$(basename {input.constellation_js:q})"

        temp_qmd="$output_dir/.sample_summary.qmd"
        temp_report_dir="$output_dir/report"

        mkdir -p "$temp_report_dir"

        cp "$template_abs" "$temp_qmd"
        cp "$css_abs" "$temp_report_dir/sample-report.css"
        cp "$report_html_abs" "$temp_report_dir/escape-report.html"
        cp "$report_js_abs" "$temp_report_dir/escape-report.js"
        cp "$constellation_css_abs" "$temp_report_dir/genome-constellation.css"
        cp "$constellation_js_abs" "$temp_report_dir/genome-constellation.js"

        (
            cd "$output_dir"
            runtime_dir="${{TMPDIR:-/tmp}}/wings-jupyter-{wildcards.sample}"
            mkdir -p "$runtime_dir"
            export XDG_RUNTIME_DIR="$runtime_dir"
            export JUPYTER_RUNTIME_DIR="$runtime_dir"
            export DENO_DIR="$output_dir/.deno-cache"
            export REPORT_SNAKEMAKE_VERSION={params.snakemake_version:q}
            {params.quarto:q} render ".sample_summary.qmd" \
              --to html \
              --output "{wildcards.sample}.sample_summary.html" \
              -P "sample_id:{wildcards.sample}" \
              -P "summary_file:${{summary_abs}}" \
              -P "coverage_file:${{coverage_abs}}" \
              -P "blast_file:${{blast_abs}}" \
              -P "genoflu_file:${{genoflu_abs}}" \
              -P "vadr_log_file:${{vadr_log_abs}}" \
              -P "coverage_threshold:{params.coverage_threshold}" \
              -P "coverage_breadth_threshold:{params.coverage_breadth_threshold}" \
              -P "max_n_fraction:{params.max_n_fraction}"
            rm -rf "$runtime_dir"
            )

        rm -f "$temp_qmd"
        rm -rf "$output_dir/.sample_summary_files"
        rm -rf "$temp_report_dir"
        """


# -----------------------------------------------------------------------------
# Collect QC-qualified final consensus sequences for optional phylogeny
# inference. The merged per-sample FASTA provides the final Medaka-polished
# sequence (or explicit IRMA fallback), while coverage.tsv supplies the
# existing WINGS segment QC decision and selected contig.
# -----------------------------------------------------------------------------

rule phylogeny_segment_input:
    input:
        merged=expand(
            f"{RESULTS}/{{sample}}/merged/consensus_all_segments.fasta",
            sample=SAMPLES,
        ),
        coverage=expand(
            f"{RESULTS}/{{sample}}/coverage/coverage.tsv",
            sample=SAMPLES,
        )
    output:
        fasta=f"{RESULTS}/run_summary/phylogeny/{{segment}}.input.fasta",
        status=f"{RESULTS}/run_summary/phylogeny/{{segment}}.status.tsv"
    params:
        samples=",".join(SAMPLES),
        min_sequences=PHYLOGENY_MIN_SEQUENCES
    conda:
        "envs/py-tools.yaml"
    script:
        "scripts/build_phylogeny_input.py"


# -----------------------------------------------------------------------------
# Build the linked map/timeline/phylogeny data bundle used by the run report.
# Supplied phylogeny files are optional external inputs; WINGS displays the
# first Newick tree in each file without inferring or modifying the phylogeny.
# -----------------------------------------------------------------------------
rule surveillance_explorer_data:
    input:
        metadata=f"{RESULTS}/metadata/validated_metadata.tsv",
        summaries=expand(
            f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.tsv",
            sample=SAMPLES,
        ),
        trees=surveillance_tree_inputs
    output:
        json=f"{RESULTS}/run_summary/surveillance_explorer.json"
    script:
        "scripts/build_surveillance_explorer.py"


# Produce a run-level report across all FASTQ-derived samples
# -----------------------------------------------------------------------------
rule run_summary_html:
    input:
        metadata=f"{RESULTS}/metadata/validated_metadata.tsv",
        summaries=expand(
            f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.tsv",
            sample=SAMPLES,
        ),
        reports=expand(
            f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.html",
            sample=SAMPLES,
        ),
        coverage=expand(
            f"{RESULTS}/{{sample}}/coverage/coverage.tsv",
            sample=SAMPLES,
        ),
        genoflu=(
            expand(
                f"{RESULTS}/{{sample}}/genoflu/GenoFLU.tsv",
                sample=SAMPLES,
            )
            if RUN_GENOFLU
            else []
        ),
        vadr_logs=(
            expand(
                f"{RESULTS}/{{sample}}/vadr/{{sample}}.vadr.log",
                sample=SAMPLES,
            )
            if RUN_VADR
            else []
        ),
        medaka_inference_status=expand(
            f"{RESULTS}/{{sample}}/medaka/{{segment}}/inference.status.tsv",
            sample=SAMPLES,
            segment=SEGMENT_SEQUENCE,
        ),
        medaka_consensus_status=expand(
            f"{RESULTS}/{{sample}}/medaka/{{segment}}/consensus.status.tsv",
            sample=SAMPLES,
            segment=SEGMENT_SEQUENCE,
        ),
        medaka_variant_status=expand(
            f"{RESULTS}/{{sample}}/medaka/{{segment}}/variants.status.tsv",
            sample=SAMPLES,
            segment=SEGMENT_SEQUENCE,
        ),
        template="scripts/run_summary.qmd",
        css="scripts/report/sample-report.css",
        report_html="scripts/report/escape-report.html",
        report_js="scripts/report/escape-report.js",
        explorer_json=f"{RESULTS}/run_summary/surveillance_explorer.json",
        run_report_html="scripts/report/run-report.html",
        explorer_css="scripts/report/surveillance-explorer.css",
        explorer_js="scripts/report/surveillance-explorer.js"
    output:
        html=f"{RESULTS}/run_summary/run_summary.html",
        tsv=f"{RESULTS}/run_summary/run_summary.tsv",
        review=f"{RESULTS}/run_summary/samples_requiring_review.tsv"
    params:
        samples=",".join(SAMPLES),
        snakemake_version=SNAKEMAKE_VERSION,
        results_dir=RESULTS,
        coverage_threshold=COVERAGE_MIN,
        coverage_breadth_threshold=COVERAGE_MIN_BREADTH,
        max_n_fraction=SEGMENT_MAX_N_FRACTION,
        explorer_enabled="true" if RUN_SURVEILLANCE_EXPLORER else "false",
        quarto=QUARTO_CMD,
    conda:
        REPORTING_ENV
    shell:
        r"""
        set -euo pipefail

        output_dir="$(cd "$(dirname {output.html:q})" && pwd)"
        results_abs="$(cd {params.results_dir:q} && pwd)"
        template_abs="$(cd "$(dirname {input.template:q})" && pwd)/$(basename {input.template:q})"
        css_abs="$(cd "$(dirname {input.css:q})" && pwd)/$(basename {input.css:q})"
        report_html_abs="$(cd "$(dirname {input.report_html:q})" && pwd)/$(basename {input.report_html:q})"
        report_js_abs="$(cd "$(dirname {input.report_js:q})" && pwd)/$(basename {input.report_js:q})"
        explorer_json_abs="$(cd "$(dirname {input.explorer_json:q})" && pwd)/$(basename {input.explorer_json:q})"
        run_report_html_abs="$(cd "$(dirname {input.run_report_html:q})" && pwd)/$(basename {input.run_report_html:q})"
        explorer_css_abs="$(cd "$(dirname {input.explorer_css:q})" && pwd)/$(basename {input.explorer_css:q})"
        explorer_js_abs="$(cd "$(dirname {input.explorer_js:q})" && pwd)/$(basename {input.explorer_js:q})"

        temp_qmd="$output_dir/.run_summary.qmd"
        temp_report_dir="$output_dir/report"

        mkdir -p "$temp_report_dir"
        cp "$template_abs" "$temp_qmd"
        cp "$css_abs" "$temp_report_dir/sample-report.css"
        cp "$report_html_abs" "$temp_report_dir/escape-report.html"
        cp "$report_js_abs" "$temp_report_dir/escape-report.js"
        cp "$run_report_html_abs" "$temp_report_dir/run-report.html"
        cp "$explorer_css_abs" "$temp_report_dir/surveillance-explorer.css"
        cp "$explorer_js_abs" "$temp_report_dir/surveillance-explorer.js"

        (
            cd "$output_dir"
            runtime_dir="${{TMPDIR:-/tmp}}/wings-jupyter-run-summary"
            mkdir -p "$runtime_dir"
            export XDG_RUNTIME_DIR="$runtime_dir"
            export JUPYTER_RUNTIME_DIR="$runtime_dir"
            export REPORT_SNAKEMAKE_VERSION={params.snakemake_version:q}
            {params.quarto:q} render ".run_summary.qmd" \
              --to html \
              --output "run_summary.html" \
              -P "results_dir:${{results_abs}}" \
              -P "samples:{params.samples}" \
              -P "run_summary_tsv:run_summary.tsv" \
              -P "review_tsv:samples_requiring_review.tsv" \
              -P "explorer_json:${{explorer_json_abs}}" \
              -P "explorer_enabled:{params.explorer_enabled}" \
              -P "coverage_threshold:{params.coverage_threshold}" \
              -P "coverage_breadth_threshold:{params.coverage_breadth_threshold}" \
              -P "max_n_fraction:{params.max_n_fraction}"
            rm -rf "$runtime_dir"
        )

        rm -f "$temp_qmd"
        rm -rf "$output_dir/.run_summary_files"
        rm -rf "$temp_report_dir"
        """


# -----------------------------------------------------------------------------
# GenoFLU, gated by QC-passing H5 HA plus a QC-passing resolved NA subtype
# -----------------------------------------------------------------------------
rule genoflu:
    input:
        flag=f"{RESULTS}/{{sample}}/genoflu/h5.flag",
        fasta=f"{RESULTS}/{{sample}}/merged/consensus_all_segments.fasta",
        summary=f"{RESULTS}/{{sample}}/summary/blast_top_hits.csv"
    output:
        tsv=f"{RESULTS}/{{sample}}/genoflu/GenoFLU.tsv"
    log:
        f"{RESULTS}/{{sample}}/genoflu/genoflu.log"
    conda:
        "envs/genoflu.yaml"
    shell:
        r"""
        set -euo pipefail
        mkdir -p "$(dirname {output.tsv:q})"

        h5_status="$(tr -d '\r\n' < {input.flag:q})"

        if [[ "$h5_status" == "DETECTED" ]]; then
            fasta_dir="$(dirname {input.fasta:q})"
            fasta_base="$(basename {input.fasta:q})"
            (
                cd "$fasta_dir"
                genoflu.py -f "$fasta_base"
            ) | tee {log:q} > {output.tsv:q}
        elif [[ "$h5_status" == "NOT_DETECTED" ]]; then
            printf "sample\tstatus\n%s\tH5_NOT_DETECTED\n" {wildcards.sample:q} \
              | tee {log:q} > {output.tsv:q}
        elif [[ "$h5_status" == "INDETERMINATE" ]]; then
            printf "sample\tstatus\n%s\tH5_OR_NA_INDETERMINATE\n" {wildcards.sample:q} \
              | tee {log:q} > {output.tsv:q}
        else
            echo "Unexpected H5+NA screen status: '$h5_status'" > {log:q}
            exit 1
        fi
        """

# -----------------------------------------------------------------------------
# Run-level provenance
# -----------------------------------------------------------------------------
rule run_provenance:
    input:
        config="config.yaml",
        snakefile="Snakefile",
        blast_manifest="resources/flu_db/database_manifest.tsv",
        script="scripts/write_run_provenance.py",
        envs=[
            "envs/blast.yaml",
            "envs/coverage.yaml",
            "envs/fastplong.yaml",
            "envs/genoflu.yaml",
            "envs/medaka.yaml",
            "envs/nanoplot.yaml",
            "envs/porechop.yaml",
            "envs/py-tools.yaml",
            "envs/pysam.yaml",
            "envs/seqtk.yaml",
            REPORTING_ENV,
        ]
    output:
        tsv=f"{RESULTS}/run_summary/run_provenance.tsv",
        json=f"{RESULTS}/run_summary/run_provenance.json"
    params:
        repo_root=".",
        sample_count=len(SAMPLES),
        snakemake_version=SNAKEMAKE_VERSION,
        irma_image=IRMA_IMAGE,
        irma_module=IRMA_MODULE,
        irma_runtime=IRMA_RUNTIME,
        vadr_image=VADR_IMAGE,
        vadr_mkey=VADR_MKEY,
        vadr_runtime=VADR_RUNTIME,
        medaka_model=MEDAKA_MODEL or "AUTO",
        medaka_model_records=MEDAKA_MODEL_RECORDS,
        medaka_fail_soft="true" if MEDAKA_FAIL_SOFT else "false",
        coverage_min_depth=COVERAGE_MIN,
        coverage_min_breadth=COVERAGE_MIN_BREADTH,
        segment_max_n_fraction=SEGMENT_MAX_N_FRACTION,
        blast_min_identity=BLAST_MIN_IDENTITY,
        blast_min_query_coverage=BLAST_MIN_QUERY_COVERAGE,
        blast_max_target_seqs=BLAST_MAX_TARGET_SEQS,
        blast_max_hsps=BLAST_MAX_HSPS,
        reporting_env=REPORTING_ENV
    conda:
        "envs/py-tools.yaml"
    shell:
        r"""
        set -euo pipefail
        python {input.script:q} \
          --output-tsv {output.tsv:q} \
          --output-json {output.json:q} \
          --repo-root {params.repo_root:q} \
          --config {input.config:q} \
          --snakefile {input.snakefile:q} \
          --blast-manifest {input.blast_manifest:q} \
          --sample-count {params.sample_count} \
          --snakemake-version {params.snakemake_version:q} \
          --irma-image {params.irma_image:q} \
          --irma-module {params.irma_module:q} \
          --irma-runtime {params.irma_runtime:q} \
          --vadr-image {params.vadr_image:q} \
          --vadr-mkey {params.vadr_mkey:q} \
          --vadr-runtime {params.vadr_runtime:q} \
          --medaka-model {params.medaka_model:q} \
          --medaka-model-records {params.medaka_model_records} \
          --medaka-fail-soft {params.medaka_fail_soft:q} \
          --coverage-min-depth {params.coverage_min_depth} \
          --coverage-min-breadth {params.coverage_min_breadth} \
          --segment-max-n-fraction {params.segment_max_n_fraction} \
          --blast-min-identity {params.blast_min_identity} \
          --blast-min-query-coverage {params.blast_min_query_coverage} \
          --blast-max-target-seqs {params.blast_max_target_seqs} \
          --blast-max-hsps {params.blast_max_hsps} \
          --env blast=envs/blast.yaml \
          --env coverage=envs/coverage.yaml \
          --env fastplong=envs/fastplong.yaml \
          --env genoflu=envs/genoflu.yaml \
          --env medaka=envs/medaka.yaml \
          --env nanoplot=envs/nanoplot.yaml \
          --env porechop=envs/porechop.yaml \
          --env py-tools=envs/py-tools.yaml \
          --env pysam=envs/pysam.yaml \
          --env reporting={params.reporting_env:q} \
          --env seqtk=envs/seqtk.yaml
        """


# -----------------------------------------------------------------------------
# Portable WINGS report bundle
# -----------------------------------------------------------------------------
rule wings_report_bundle:
    input:
        run_summary=f"{RESULTS}/run_summary/run_summary.html",
        provenance_tsv=f"{RESULTS}/run_summary/run_provenance.tsv",
        provenance_json=f"{RESULTS}/run_summary/run_provenance.json",
        reports=expand(
            f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.html",
            sample=SAMPLES,
        ),
        builder="scripts/build_report_bundle.py"
    output:
        bundle=f"{RESULTS}/wings_report_bundle.wings"
    shell:
        r"""
        set -euo pipefail
        python {input.builder:q} \
          --run-summary {input.run_summary:q} \
          --provenance {input.provenance_json:q} \
          --output {output.bundle:q} \
          {input.reports:q}
        """
