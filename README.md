# Wild-bird Influenza Genomics and Surveillance (WINGS)

<p align="center">
  <img src="wings_logo.jpg" alt="WINGS logo" width="360">
</p>

**Overview**

WINGS is a portable Snakemake workflow for genomic analysis of avian influenza A virus from Oxford Nanopore sequencing reads. It performs read preprocessing, influenza assembly, segment-level quality assessment, consensus polishing, variant calling, subtype screening, genotype assignment, annotation, and generation of interactive HTML reports.

WINGS was developed in support of the [**Pandemic ESCAPE Center**](https://escape.engr.uky.edu/), with a focus on genomic epidemiology, bioinformatics, and surveillance of avian influenza viruses in wild birds.

The workflow has been validated on Apple Silicon macOS using Snakemake, Conda, and Docker Desktop, and on Linux ARM64 SLURM clusters using Snakemake, Conda, and Apptainer. VADR is currently disabled on Linux ARM64 because the pinned VADR container image does not provide a Linux ARM64 image.

Most tools run in rule-specific Conda environments. IRMA runs in a container selected for the host environment.

## Features

- Oxford Nanopore influenza A analysis
- Porechop ABI adapter trimming
- `fastplong` read-quality and length filtering without a second adapter-trimming pass
- Sample metadata validation and integration
- IRMA `FLU-minion` assembly
- Segment-level QC using depth, breadth-at-depth, expected-length, and N-content criteria
- Medaka consensus polishing and variant calling
- BLAST-based segment identification with identity/query-coverage evidence and confidence classification
- H5Nx analytical screening
- Conditional GenoFLU genotype assignment for H5Nx-screen-positive samples
- VADR sequence annotation and validation
- Interactive sample-level HTML reports
- Interactive sequencing-run summary report
- Portable `.wings` report bundles containing the run summary, all sample reports, and embedded run-level provenance
- Run-level provenance capturing workflow state, configuration hashes, environment hashes, runtime details, and BLAST database provenance
- Browser-based local report viewing at `wings.scotchlab.org` with no sequencing-data upload
- Apple Silicon and Linux ARM64 support
- Docker, Apptainer, Singularity, or local IRMA execution

## Workflow

```text
Nanopore FASTQ
    |
    v
Porechop ABI
(adapter trimming)
    |
    v
fastplong
(long-read quality and length filtering; adapter trimming disabled)
    |
    v
seqtk rename
(read identifier normalization)
    |
    v
IRMA FLU-minion
(influenza assembly)
    |
    v
Segment-level QC
(default: median depth >=50x; >=95% of positions at >=50x;
 minimum segment length; <=1% Ns; long segments warned)
    |
    +--> FASTQ basecaller-model detection
    |    (sample-specific Medaka model resolution)
    +--> Medaka consensus polishing
    +--> Medaka variant calling
    |
    +--> BLAST segment identification
    |        |
    |        v
    |    H5Nx screening
    |        |
    |        +--> GenoFLU genotype assignment
    |             (only when the H5Nx screen is DETECTED)
    |
    +--> VADR annotation and validation
         (from segment-QC-qualified polished consensuses)
    |
    v
Interactive HTML reports
    +--> Validated sample metadata
    +--> Sample report
    +--> Run summary report
    +--> Run-level provenance (TSV + JSON)
    +--> Portable WINGS report bundle (.wings; provenance embedded)
```

NanoPlot is also available as an optional raw-read quality-control target.

## Repository structure

```text
.
├── Snakefile
├── view_reports.sh                    # convenience launcher for local HTML reports
├── config.yaml                       # local configuration; not committed
├── config/
│   └── config.example.yaml
├── envs/
│   ├── blast.yaml
│   ├── coverage.yaml
│   ├── fastplong.yaml
│   ├── genoflu.yaml
│   ├── medaka.yaml
│   ├── nanoplot.yaml
│   ├── porechop.yaml
│   ├── py-tools.yaml
│   ├── pysam.yaml
│   ├── reporting.yaml                 # macOS/default reporting environment
│   ├── reporting-linux-arm64.yaml     # Linux ARM64 reporting environment
│   └── seqtk.yaml
├── scripts/
│   ├── build_blast_db.sh
│   ├── build_report_bundle.py
│   ├── install_vadr_models.sh           # pinned VADR influenza-model installer
│   ├── check_coverage.py
│   ├── coverage_table.py
│   ├── install_quarto_linux_arm64.sh  # pinned ARM64 Quarto installer
│   ├── normalize_irma_outputs.py
│   ├── prepare_vadr_input.py
│   ├── resolve_medaka_model.py
│   ├── sample_summary.py
│   ├── validate_metadata.py
│   ├── extract_sample_metadata.py
│   ├── serve_reports.py
│   ├── summarize_blast.py
│   ├── sample_summary.qmd
│   ├── run_summary.qmd
│   ├── write_run_provenance.py
│   └── report/
│       ├── escape-report.html
│       ├── escape-report.js
│       └── sample-report.css
├── profiles/
│   └── slurm-arm/
├── tests/                             # regression tests
├── demo/
│   └── wings_demo.wings              # public demonstration bundle for the website
├── data/                             # input FASTQ files; not committed
├── metadata.example.tsv               # sample metadata template
├── metadata.tsv                       # local sample metadata; not committed
├── resources/
│   ├── fluA_reference.fasta.zip      # downloaded resource; not committed
│   ├── flu_db/                       # generated BLAST database; not committed
│   │   └── database_manifest.tsv     # BLAST database provenance manifest
│   └── vadr-models/                  # downloaded VADR influenza models; not committed
├── results/                          # generated outputs; not committed
├── README.md
└── .gitignore
```

## Requirements

### All environments

- Git
- Bash
- Conda or Mamba
- Snakemake
- A supported IRMA execution method:
  - Docker
  - Apptainer
  - Singularity
  - a local IRMA installation

The BLAST database setup script additionally requires `curl`, `unzip`, and either local `makeblastdb` or one of the supported container runtimes. The VADR model installer requires `curl`, `tar`, and either `shasum` or `sha256sum`.

### Apple Silicon laptop

The validated macOS configuration uses:

- Miniforge or another native `osx-arm64` Conda distribution
- Snakemake 9
- Docker Desktop
- native `osx-arm64` Conda environments for non-IRMA rules

Docker Desktop must be installed and running before IRMA executes.

#### Docker Desktop memory

Large or highly multiplexed influenza datasets can require substantially more memory than the Docker Desktop default. A low Docker memory limit can cause IRMA preprocessing to be killed even when the host Mac has ample RAM.

For a high-memory Apple Silicon workstation, a validated configuration is approximately:

- Memory: 96 GB
- Swap: 4 GB or more

Choose values appropriate for the physical RAM available on the host. Leave sufficient memory for macOS and other applications. Verify the memory visible inside Docker with:

```bash
docker run --rm alpine sh -c 'free -h'
```

WINGS now checks the IRMA log and expected outputs after execution. Internal failures such as a killed process, an out-of-memory condition, or `found no QC'd data` cause the workflow to stop instead of continuing to downstream reports.

### Linux ARM64 cluster

The validated cluster configuration uses:

- Mamba or Conda
- Snakemake
- Apptainer or Singularity
- SLURM
- standalone Quarto 1.9.38 installed with the included ARM64 installer

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/ZooPhy/wings.git
cd wings
```

### Linux ARM64: install Quarto

On Linux ARM64, WINGS uses a standalone pinned Quarto installation because the Conda Quarto package is not available for the validated ARM64 environment.

From the repository root, run:

```bash
./scripts/install_quarto_linux_arm64.sh software
```

The installer downloads Quarto 1.9.38 for Linux ARM64, verifies the pinned SHA-256 checksum, and installs it under:

```text
software/quarto-1.9.38/
```

WINGS automatically uses `software/quarto-1.9.38/bin/quarto` on Linux ARM64 when that executable is present. Otherwise, it falls back to `quarto` found on `PATH`.

### 2. Install Miniforge on Apple Silicon macOS

Users who already have a working Conda or Mamba installation may skip this step.

```bash
curl -fsSLo Miniforge3.sh \
  "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-$(uname -m).sh"

bash Miniforge3.sh -b -p "$HOME/miniforge3"
"$HOME/miniforge3/bin/conda" init zsh
exec zsh
```

Configure strict channel priority:

```bash
conda config --set channel_priority strict
```

### 3. Create the Snakemake environment

```bash
mamba create -n snakemake_env \
  -c conda-forge \
  -c bioconda \
  snakemake
```

Activate it:

```bash
conda activate snakemake_env
```

Confirm the installation:

```bash
snakemake --version
```

### 4. Install and start Docker Desktop on macOS

IRMA runs in Docker on macOS. Docker may also be used by the BLAST database setup script when local BLAST+ is not installed.

After starting Docker Desktop, verify that the daemon is available:

```bash
docker info
```

Installing the Docker command-line program alone is not sufficient; the Docker daemon must be running.

## First-time workflow setup

### 1. Create a local configuration file

```bash
cp config/config.example.yaml config.yaml
```

`config.yaml` is intentionally excluded from Git so that paths and machine-specific settings can be changed locally.

### 2. Install the pinned VADR influenza models

VADR 1.7 does not bundle the influenza model library in the pinned `staphb/vadr:1.7` container. WINGS therefore keeps the VADR software image and influenza model data separate. Install the pinned influenza models from the repository root with:

```bash
./scripts/install_vadr_models.sh
```

The installer downloads NCBI VADR influenza models version `1.7-1`, verifies the WINGS-pinned SHA-256 checksum before extraction, checks for the required `flu.minfo`, `flu.cm`, and `flu.fa` files, and installs the models under:

```text
resources/vadr-models/vadr-models-flu-1.7-1/
```

The pinned archive SHA-256 is:

```text
5f09b8d95413251499a2e49a0b93ea119bc96814b4742d92ba55fd3bdadac7ec
```

The installer also writes `WINGS_MODEL_MANIFEST.tsv` inside the installed model directory with the model version, source URL, and pinned archive checksum. The downloaded models are local resources and are excluded from Git.

Configure VADR with:

```yaml
run_vadr: true
vadr_runtime: auto
vadr_image: "docker://staphb/vadr:1.7"
vadr_mkey: flu
vadr_model_dir: "resources/vadr-models/vadr-models-flu-1.7-1"
vadr_forcegene: true
```

On Apple Silicon, `vadr_runtime: auto` can select Docker and WINGS mounts the model directory read-only into the VADR container. On Linux ARM64, keep `run_vadr: false` when using the pinned VADR image because that image does not provide a native Linux ARM64 build.

### 3. Build the influenza BLAST database

Run the included setup script from the repository root:

```bash
./scripts/build_blast_db.sh
```

If needed, make the script executable first:

```bash
chmod +x scripts/build_blast_db.sh
```

The script:

1. Looks for `resources/fluA_reference.fasta.zip`.
2. Downloads the reference archive when it is absent.
3. Extracts the influenza A reference FASTA.
4. Removes an older database with the same prefix.
5. Builds a nucleotide BLAST database.
6. Writes the database under `resources/flu_db/`.
7. Writes `resources/flu_db/database_manifest.tsv` with the source release, archive and FASTA SHA-256 hashes, `makeblastdb` version, BLAST database format version, build method, container image, and database prefix.

By default, the reference archive is obtained from the `v0.1.0` release of `ZooPhy/apgap-influenza-pipeline`. The source can be changed with environment variables when needed.

Expected output:

```text
resources/
├── fluA_reference.fasta.zip
└── flu_db/
    ├── fluA_reference.fasta
    ├── fluA_db.nhr
    ├── fluA_db.nin
    ├── fluA_db.nsq
    ├── database_manifest.tsv
    └── ...
```

The default container image for database construction is pinned to `ncbi/blast-static:2.17.0`. The script tries the following database-building methods in order:

1. local `makeblastdb`
2. Docker
3. Apptainer
4. Singularity

Set the resulting database prefix in `config.yaml`:

```yaml
blast_db: "resources/flu_db/fluA_db"
```

The value must be the database prefix, not the directory and not an individual database file.

#### Override the reference source

Use another release tag:

```bash
RELEASE_TAG="vX.Y.Z" ./scripts/build_blast_db.sh
```

Use another GitHub repository and release:

```bash
GITHUB_REPO="owner/repository" \
RELEASE_TAG="vX.Y.Z" \
./scripts/build_blast_db.sh
```

Use a direct archive URL:

```bash
ZIP_URL="https://example.org/fluA_reference.fasta.zip" \
./scripts/build_blast_db.sh
```

For a private GitHub release, authenticate the GitHub CLI before running the script:

```bash
gh auth login
```

The archive may also be downloaded manually and placed at:

```text
resources/fluA_reference.fasta.zip
```

## Input data

Place one compressed Nanopore FASTQ file per sample in the configured input directory.

Example:

```text
data/
├── 24-0514.fastq.gz
├── sample02.fastq.gz
└── sample03.fastq.gz
```

The default pattern is:

```text
{sample}.fastq.gz
```

The text matched by `{sample}` becomes the sample identifier used in output paths.

### Sample metadata

WINGS supports a tab-delimited `metadata.tsv` file that is validated against the detected FASTQ samples before sample-level reporting. Metadata are matched to sequencing inputs by `sample_id`. By default, every detected FASTQ sample must have exactly one corresponding metadata record.

The supported schema is:

| Field | Requirement | Description |
|---|---|---|
| `sample_id` | Required | Must exactly match the `{sample}` identifier derived from the FASTQ filename |
| `host` | Required | Host species or host code; use `environmental` when there is no animal host |
| `collection_date` | Required | Collection date in ISO `YYYY-MM-DD` format |
| `country` | Required | Country of collection |
| `specimen_type` | Optional | Specimen or swab type |
| `state` | Optional | State, province, or equivalent first-level administrative area |
| `latitude` | Optional | Decimal latitude from -90 to 90 |
| `longitude` | Optional | Decimal longitude from -180 to 180 |

Example:

```tsv
sample_id	host	specimen_type	collection_date	state	country	latitude	longitude
12-11-2025_barcode03	BLVU	Dry (Oral+Cloacal)	2025-10-20	Kentucky	USA		
21-07-2026_barcode13	RTHA	Dry (Oral+Cloacal)	2026-04-08	Kentucky	USA	38.069739	-84.746138
```

Host values are preserved as supplied; WINGS does not silently expand or normalize species codes. Latitude and longitude may both be blank, but when supplied they must be valid numeric coordinates.

Metadata validation checks required columns and fields, unique `sample_id` values, ISO-formatted collection dates, coordinate ranges, and agreement between metadata records and detected FASTQ samples. The normalized table is written to `results/metadata/validated_metadata.tsv`, and each sample receives a sample-specific metadata table under `results/<sample>/metadata/`.

Configure metadata with:

```yaml
metadata_file: "metadata.tsv"
metadata_require_all_samples: true
```

Set `metadata_require_all_samples: false` only when intentionally allowing FASTQ samples without metadata.

## Configuration

### Apple Silicon laptop example

```yaml
reads_dir: "data"
reads_pattern: "{sample}.fastq.gz"
results_dir: "results"

coverage_min_depth: 50
coverage_min_breadth: 0.95
segment_max_n_fraction: 0.01

porechop_command: "porechop_abi"
porechop_mem_mb: 12000
porechop_time_min: 240

fastplong_mean_quality: 10
fastplong_min_length: 500
fastplong_threads: 4

metadata_file: "metadata.tsv"
metadata_require_all_samples: true

irma_image: "docker://ghcr.io/cdcgov/irma:v1.3.5"
irma_module: "FLU-minion"
irma_runtime: "docker"

blast_db: "resources/flu_db/fluA_db"
blast_min_identity: 95.0
blast_min_query_coverage: 90.0
blast_max_target_seqs: 10
blast_max_hsps: 1

medaka_model: null
medaka_fail_soft: true

run_genoflu: true
run_vadr: true
vadr_runtime: auto
vadr_image: "docker://staphb/vadr:1.7"
vadr_mkey: flu
vadr_model_dir: "resources/vadr-models/vadr-models-flu-1.7-1"
vadr_forcegene: true
run_summary: true
```

### Linux ARM64 cluster example

```yaml
reads_dir: "data"
reads_pattern: "{sample}.fastq.gz"
results_dir: "results"

coverage_min_depth: 50
coverage_min_breadth: 0.95
segment_max_n_fraction: 0.01

porechop_command: "porechop_abi"
porechop_mem_mb: 80000
porechop_time_min: 720

fastplong_mean_quality: 10
fastplong_min_length: 500
fastplong_threads: 4

metadata_file: "metadata.tsv"
metadata_require_all_samples: true

irma_image: "docker://ghcr.io/cdcgov/irma:v1.3.5"
irma_module: "FLU-minion"
irma_runtime: "apptainer"

blast_db: "resources/flu_db/fluA_db"
blast_min_identity: 95.0
blast_min_query_coverage: 90.0
blast_max_target_seqs: 10
blast_max_hsps: 1

medaka_model: null
medaka_fail_soft: true

run_genoflu: true
run_vadr: false
vadr_runtime: auto
vadr_image: "docker://staphb/vadr:1.7"
vadr_mkey: flu
vadr_model_dir: "resources/vadr-models/vadr-models-flu-1.7-1"
vadr_forcegene: true
run_summary: true
```

Use `irma_runtime: "singularity"` instead when Singularity is installed rather than Apptainer. `irma_runtime: "auto"` selects Apptainer, Singularity, Docker, or local IRMA in that order based on what is available.

The `run_genoflu`, `run_vadr`, and `run_summary` settings control whether those analyses or run-level reporting outputs are requested as default workflow targets. On Apple Silicon macOS, keep all three set to `true` for a complete production run. On Linux ARM64, keep `run_genoflu: true` and `run_summary: true`, but set `run_vadr: false` when using the pinned VADR container image because that image does not provide a Linux ARM64 build.

When VADR is enabled, `vadr_model_dir` must point to a complete influenza model installation. WINGS validates the required model files before launching VADR and passes the directory with `--mdir`; container runtimes mount it read-only. `vadr_forcegene: true` adds gene qualifiers to CDS and mat_peptide features using the influenza model information.

### Medaka model

WINGS automatically determines the Medaka consensus model for each sample from the `basecall_model_version_id` metadata embedded in the original Oxford Nanopore FASTQ headers. The workflow inspects multiple FASTQ records, verifies that the detected basecaller model is consistent, and writes the result to `results/<sample>/medaka/model.tsv`.

The detected basecaller model is passed to Medaka using its `:consensus` model selector, allowing the installed Medaka version to resolve the corresponding supported consensus model. This avoids relying on automatic model detection from the normalized IRMA BAM, which may not retain the original Nanopore read-group metadata.

For example:

```text
FASTQ basecaller model:
dna_r10.4.1_e8.2_400bps_hac@v5.0.0

Medaka selector:
dna_r10.4.1_e8.2_400bps_hac@v5.0.0:consensus

Resolved Medaka model:
r1041_e82_400bps_hac_v5.0.0
```

`medaka_model` remains available as an expert configuration override. With `medaka_model: null`, WINGS uses automatic FASTQ-based model resolution. The number of FASTQ records inspected can be configured with `medaka_model_records` (default: 100).

## Running on an Apple Silicon laptop

Activate the Snakemake environment and confirm that Docker Desktop is running:

```bash
conda activate snakemake_env
docker info
```

### Dry run

```bash
snakemake \
  --configfile config.yaml \
  --sdm conda \
  --cores 4 \
  --dry-run \
  --printshellcmds
```

`<TBD>` inputs are normal during a dry run of this workflow because IRMA is a checkpoint. Segment-specific jobs are added after IRMA completes and the available influenza segments are known.

### Pre-create Conda environments

```bash
snakemake \
  --configfile config.yaml \
  --sdm conda \
  --cores 4 \
  --conda-create-envs-only
```

Because some segment-specific jobs are created after the IRMA checkpoint, additional Conda environments may be created later during the first complete execution.

### Run the complete workflow

```bash
snakemake \
  --configfile config.yaml \
  --sdm conda \
  --cores 4 \
  --resources mem_mb=90000 kaleido=1 \
  --printshellcmds \
  --rerun-incomplete
```

Snakemake reuses completed outputs automatically when the command is rerun after a failure or interruption. The `mem_mb` value is a Snakemake scheduling resource; it does not configure Docker Desktop memory. Docker resources must be configured separately in Docker Desktop.

### Run NanoPlot optionally

NanoPlot is available as an optional target and is not required by the default final targets.

For one sample:

```bash
snakemake \
  --configfile config.yaml \
  --sdm conda \
  --cores 4 \
  results/24-0514/nanoplot/done.txt
```

## Running on a Linux ARM64 SLURM cluster

The following submission script reflects the validated Linux ARM64 configuration used for WINGS testing. Adjust the SLURM account, node, paths, and environment name for your cluster as needed.

```bash
#!/bin/bash

#SBATCH --job-name=snakemake
#SBATCH --mem=200G
#SBATCH -p arm
#SBATCH --cpus-per-task=4
#SBATCH -q grp_mscotch
#SBATCH -e wings.err
#SBATCH -o wings.out
#SBATCH -t 7-00:00:00
#SBATCH --export=NONE
#SBATCH --nodelist=scgh003

set -euo pipefail
module purge
unset PYTHONPATH

source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate wings_snakemake_new
hash -r

export CONDA_PKGS_DIRS=/data/pipp2/Scotch/Snakemake/conda_pkgs
export XDG_CACHE_HOME=/data/pipp2/Scotch/Snakemake/cache
export TMPDIR=/data/pipp2/Scotch/Snakemake/tmp
export TEMP="$TMPDIR"
export TMP="$TMPDIR"

mkdir -p "$CONDA_PKGS_DIRS" "$XDG_CACHE_HOME" "$TMPDIR"

cd /data/pipp2/Scotch/Snakemake/wings/

snakemake \
  --configfile config.yaml \
  --sdm conda \
  --printshellcmds \
  --cores "$SLURM_CPUS_PER_TASK" \
  --resources mem_mb=200000 kaleido=1 \
  --conda-cleanup-pkgs cache \
  --latency-wait 300 \
  --rerun-incomplete
```

The cache and temporary-directory overrides keep large Conda package caches and transient files on a writable project filesystem rather than a space-limited home or runtime filesystem. The repo-local Quarto installation at `software/quarto-1.9.38/bin/quarto` is detected automatically, so no Quarto `PATH` override is required.

Set `irma_runtime` in the cluster `config.yaml` to `apptainer` or `singularity` as appropriate. The current Snakefile invokes the selected IRMA runtime directly, so a separate Snakemake container deployment flag is not required for IRMA. On Linux ARM64, keep `run_vadr: false` unless a compatible ARM64 VADR image is provided.

## Output structure

Outputs are organized by sample:

```text
results/<sample>/
├── nanoplot/                    # optional
├── porechop/
├── fastplong/
├── metadata/
├── irma/
│   ├── project/
│   ├── segments/
│   ├── manifest.tsv
│   └── irma.log
├── coverage/
├── coverage_flags/
├── coverage_stats/
├── medaka/
├── blast/
├── merged/
├── genoflu/
├── vadr/
└── summary/
```

Important sample outputs include:

```text
results/<sample>/fastplong/report.html
results/<sample>/metadata/<sample>.metadata.tsv
results/<sample>/irma/manifest.tsv
results/<sample>/irma/segments/<segment>/consensus.fasta
results/<sample>/coverage/coverage.tsv
results/<sample>/coverage_stats/<segment>.tsv
results/<sample>/medaka/model.tsv
results/<sample>/medaka/<segment>/consensus.fasta
results/<sample>/medaka/<segment>/variants.vcf
results/<sample>/blast/<segment>.blast.txt
results/<sample>/summary/blast_top_hits.csv
results/<sample>/merged/consensus_all_segments.fasta
results/<sample>/genoflu/h5.flag
results/<sample>/genoflu/GenoFLU.tsv
results/<sample>/vadr/<sample>.vadr.log
results/<sample>/summary/<sample>.sample_summary.tsv
results/<sample>/summary/<sample>.sample_summary.html
```

Validated run-level metadata and provenance outputs include:

```text
results/metadata/validated_metadata.tsv
results/metadata/metadata_validation.tsv
results/run_summary/run_provenance.tsv
results/run_summary/run_provenance.json
```

The sequencing-run report is written to:

```text
results/run_summary/run_summary.html
```

The HTML report uses tabs for **Run Summary**, **Sample Detail**, **Subtype/Genotype Distribution**, **Genome Coverage**, and **Surveillance Explorer**. The subtype tab shows HA and NA distributions and, when GenoFLU is enabled, genotype counts among H5Nx-screen-eligible samples. Samples without an assigned GenoFLU genotype are shown separately; samples ineligible for GenoFLU are excluded. The Explorer shows the linked timeline, map, segment trees, and a compact host distribution beneath the map. Click a host bar to filter the Explorer; click it again to show all hosts.

A portable WINGS report bundle containing the run summary and all sample reports is written to:

```text
results/wings_report_bundle.wings
```

The `.wings` bundle is a self-contained JSON report package intended for browser-based viewing. It contains rendered HTML reports plus the embedded `run_provenance.json` record, but not the raw sequencing reads or intermediate analysis files.

## Run-level provenance

WINGS writes machine-readable provenance for each completed run to:

```text
results/run_summary/run_provenance.tsv
results/run_summary/run_provenance.json
```

The record captures the WINGS Git commit, branch and dirty/clean state; SHA-256 hashes of the `Snakefile` and active `config.yaml`; Snakemake, Python, operating-system and architecture information; the configured IRMA, Medaka, VADR, QC and BLAST settings; the BLAST database manifest and its checksum; and SHA-256 hashes of the Conda environment YAML files. The JSON provenance record is embedded directly in `results/wings_report_bundle.wings`, so the portable bundle carries its computational provenance with the rendered reports.

For a formal reproducible analysis, generate provenance from a clean committed repository state so `workflow.git_dirty` is `false`.

## Reports

### Sample report

Each sample report summarizes validated sample metadata, read filtering, segment recovery, coverage, BLAST assignments, H5Nx screening, GenoFLU results when applicable, VADR status, and review flags. Reports are generated as self-contained HTML and are also packaged into the portable `.wings` bundle for browser-based navigation.

Build one sample report with:

```bash
snakemake \
  --configfile config.yaml \
  --sdm conda \
  --cores 4 \
  --resources mem_mb=90000 kaleido=1 \
  --rerun-incomplete \
  results/<sample>/summary/<sample>.sample_summary.html
```

### Run summary report

The run summary combines all configured samples into a single HTML dashboard. Build it with:

```bash
snakemake \
  --configfile config.yaml \
  --sdm conda \
  --cores 4 \
  --resources mem_mb=90000 kaleido=1 \
  --rerun-incomplete \
  results/run_summary/run_summary.html
```

Because the run summary depends on all sample reports, target an individual sample report when rerunning only one barcode.

### Build the portable WINGS report bundle

Build the portable report bundle with:

```bash
snakemake results/wings_report_bundle.wings \
  --configfile config.yaml \
  --sdm conda \
  --cores 4 \
  --resources mem_mb=90000 kaleido=1
```

The resulting `results/wings_report_bundle.wings` file contains the rendered run summary, all rendered sample reports, and the run-level provenance JSON in a single portable package. It can be opened at `wings.scotchlab.org` by selecting or dragging the `.wings` file into the report viewer. The browser reads the bundle locally; the sequencing results are not uploaded to the WINGS website.

For a public demonstration, a deliberately selected example bundle can be placed at:

```text
demo/wings_demo.wings
```

Only use non-sensitive data that are appropriate for public distribution in the demo bundle.

### View reports locally

The preferred way to review a completed analysis is to open `results/wings_report_bundle.wings` at `wings.scotchlab.org`. The site can display the run summary and navigate to individual sample reports directly from the local bundle without uploading the report contents.

The included local report server remains available as an alternative for development, offline use, or direct browsing of the generated HTML files. Some browsers, including Safari, restrict navigation between local `file://` HTML documents, so use the local server rather than opening the HTML files directly.

Launch the local report server from the repository root with:

```bash
./view_reports.sh
```

The wrapper starts `scripts/serve_reports.py`, which by default binds only to the local loopback interface and opens:

```text
http://127.0.0.1:4174/run_summary/run_summary.html
```

The report server serves the existing static HTML reports from the local `results/` directory. By default it binds only to the loopback interface, so it does not upload sequencing data or publish the reports to the network.

Press `Ctrl+C` to stop the server.

The Python launcher can also be run directly:

```bash
python scripts/serve_reports.py
```

To use another port:

```bash
python scripts/serve_reports.py --port 8080
```

To start the server without automatically opening a browser:

```bash
python scripts/serve_reports.py --no-browser
```

## Segment QC criterion

Each influenza segment is evaluated independently before Medaka polishing. Per-position depth is calculated from the normalized IRMA BAM with `samtools depth -aa -q 0 -Q 0`. The `-aa` option ensures that zero-depth reference positions are included in the denominator. Coverage breadth is the fraction of reference positions whose depth is greater than or equal to `coverage_min_depth`. WINGS also evaluates the normalized IRMA consensus FASTA for segment length and the fraction of ambiguous `N` bases. The configured lower length bound is a hard minimum; the upper bound is a review guide rather than a hard failure threshold.

Defaults:

```yaml
coverage_min_depth: 50
coverage_min_breadth: 0.95
segment_max_n_fraction: 0.01
segment_expected_lengths:
  PB2: [2200, 2400]
  PB1: [2200, 2400]
  PA: [2100, 2300]
  HA: [1600, 1800]
  NP: [1450, 1600]
  NA: [1300, 1500]
  MP: [950, 1050]
  NS: [800, 950]
```

With these defaults, a segment passes the hard QC gate when **all** of the following are true: median depth is at least **50x**; at least **95% of reference positions are at 50x or greater**; consensus length is at least the configured segment-specific minimum; and no more than **1% of consensus bases are `N`**. A consensus longer than the configured upper length guide remains eligible for downstream analysis but receives a length `WARNING` for review. The reported `breadth_covered` value therefore represents breadth at the configured depth threshold, not merely the fraction of positions with any coverage.

The segment-length bounds are configurable QC guardrails rather than subtype-confirmation criteria. The lower bound protects against truncated assemblies. The upper bound highlights unexpectedly long consensuses without automatically rejecting sequences that may contain valid terminal or assay-specific sequence. Bounds should be changed only when the assay design or validated biological targets justify different values.

The per-segment statistics record the individual `coverage_status`, `length_status`, and `n_content_status` values as well as the final `overall_status`. The existing `results/<sample>/coverage_flags/<segment>.flag` path is retained for workflow compatibility, but its `PASS` now means that the segment passed the complete segment-QC criterion rather than coverage alone.

If IRMA does not recover a segment, WINGS treats that absence as an explicit analytical state rather than a workflow error. The normalized IRMA manifest still contains a row for the segment with `status=MISSING`; `check_coverage` writes corresponding `MISSING` flag and statistics outputs; and the final `coverage.tsv` retains all eight influenza A segment rows. This allows incomplete genomes to proceed through reporting without fabricating FASTA or BAM files for unrecovered segments.

Only segments passing the hard segment-QC criteria proceed through Medaka and BLAST analysis; an upper-length warning alone does not block downstream analysis.

For each segment, WINGS selects a normalized IRMA candidate deterministically and records the candidate count, selection status, selected contig, and selection reason in the manifest and segment QC outputs. When IRMA produces more than one candidate for a segment, the selected candidate remains eligible for the normal hard QC gate, but the sample receives a `multiple_irma_candidates` review flag and the ambiguity is surfaced in sample- and run-level reports.

## BLAST evidence and confidence

For each QC-passing segment, WINGS runs `blastn` against the configured influenza A nucleotide database and retains up to `blast_max_target_seqs` subject sequences with at most `blast_max_hsps` HSPs per subject. The default settings are:

```yaml
blast_min_identity: 95.0
blast_min_query_coverage: 90.0
blast_max_target_seqs: 10
blast_max_hsps: 1
```

The raw `results/<sample>/blast/<segment>.blast.txt` files retain the evidence rows. `results/<sample>/summary/blast_top_hits.csv` summarizes the top HSP for each segment with subject accession/title, percent identity, alignment length, query length, query coverage, E-value, bit score, and a confidence state. Query coverage is calculated as alignment length divided by query length for the selected top HSP; HSPs are not merged.

BLAST summary states are:

- `HIGH_CONFIDENCE`: a hit exists and meets both the identity and query-coverage thresholds.
- `LOW_CONFIDENCE`: a hit exists but fails one or both thresholds.
- `NO_HIT`: BLAST ran for a QC-passing segment but returned no hit.
- `SKIPPED_QC`: BLAST was not run because the segment failed the upstream hard QC gate.

The BLAST database provenance is recorded in `resources/flu_db/database_manifest.tsv` and is incorporated into the run-level provenance record.

## H5Nx screening

The H5Nx rule is a screening criterion based on IRMA-supported HA and NA assignments and segment QC. It requires:

- an H5-associated HA assignment
- a subtype-resolved NA assignment of any N subtype (for example, N1, N2, N5, N6, or N8)
- passing HA segment QC
- passing NA segment QC

The H5Nx screen uses three states. `DETECTED` means the HA segment passes QC and is identified as H5, and the NA segment also passes QC with an informative NA subtype assignment. The NA subtype is retained and reported but is not restricted to N1. `NOT_DETECTED` means the QC-qualified HA evidence is informative and indicates a non-H5 subtype. `INDETERMINATE` means the HA evidence is not sufficiently QC-qualified to determine H5 status, or an H5 HA is present but the NA segment is missing, fails QC, or lacks an informative subtype assignment. `DETECTED` is an analytical screening flag rather than an independent confirmatory subtype test. GenoFLU is run only for `DETECTED` H5Nx samples.

## Troubleshooting

### Metadata validation fails

WINGS validates `metadata.tsv` before sample-level metadata are propagated into reports. Common causes of failure include missing required columns, duplicate `sample_id` values, sample identifiers that do not match FASTQ filenames, non-ISO collection dates, or invalid coordinates.

Check the configured metadata path:

```yaml
metadata_file: "metadata.tsv"
metadata_require_all_samples: true
```

Then inspect the identifiers derived from the input FASTQs and compare them with the first column of `metadata.tsv`:

```bash
printf "FASTQ samples:\n"
find data -maxdepth 1 -type f -name '*.fastq.gz' -print \
  | sed 's#^.*/##; s/\.fastq\.gz$//' \
  | sort

printf "\nMetadata sample_id values:\n"
cut -f1 metadata.tsv | tail -n +2 | sort
```

With `metadata_require_all_samples: true`, every detected FASTQ sample must have a matching metadata record.

### No samples are detected

Message:

```text
WARNING: no samples matched 'data/{sample}.fastq.gz'
```

Confirm that:

- FASTQ files are present under `reads_dir`
- filenames match `reads_pattern`
- `reads_pattern` contains `{sample}`

### Docker is installed but IRMA cannot start

Message:

```text
Cannot connect to the Docker daemon
```

Start Docker Desktop and verify:

```bash
docker info
```

Then rerun the complete Snakemake command. Completed upstream files will be reused.

### IRMA is killed or reports no QC'd data

Messages may include:

```text
Killed
found no QC'd data
```

This commonly indicates that the container runtime did not have enough memory. On macOS, increase Docker Desktop memory, restart Docker Desktop, remove the affected sample's incomplete IRMA and downstream outputs, and rerun only that sample report target.

Check Docker memory with:

```bash
docker run --rm alpine sh -c 'free -h'
```

Monitor the affected sample with:

```bash
tail -f results/<sample>/irma/irma.log
```

The workflow should stop on these failures rather than interpreting them as a biological negative result.

### Rerun one sample after an IRMA failure

Remove only that sample's IRMA and downstream outputs:

```bash
rm -rf \
  results/<sample>/irma \
  results/<sample>/coverage \
  results/<sample>/coverage_flags \
  results/<sample>/coverage_stats \
  results/<sample>/medaka \
  results/<sample>/blast \
  results/<sample>/merged \
  results/<sample>/genoflu \
  results/<sample>/vadr \
  results/<sample>/summary
```

Then target only that sample's HTML report:

```bash
snakemake \
  --configfile config.yaml \
  --sdm conda \
  --cores 4 \
  --resources mem_mb=90000 kaleido=1 \
  --rerun-incomplete \
  results/<sample>/summary/<sample>.sample_summary.html
```

### VADR influenza models are not installed

If VADR reports that `flu.minfo` is missing, or WINGS reports that the configured VADR model directory is absent or incomplete, install the pinned influenza models:

```bash
./scripts/install_vadr_models.sh
```

Then confirm:

```bash
ls -lh resources/vadr-models/vadr-models-flu-1.7-1/flu.minfo \
       resources/vadr-models/vadr-models-flu-1.7-1/flu.cm \
       resources/vadr-models/vadr-models-flu-1.7-1/flu.fa
```

The pinned `staphb/vadr:1.7` image contains VADR itself but does not contain the influenza model bundle used by WINGS. WINGS supplies the models separately through `vadr_model_dir`.

### BLAST database files are not found

Message:

```text
No BLAST database files found for prefix
```

Build the database:

```bash
./scripts/build_blast_db.sh
```

Then confirm that `config.yaml` contains:

```yaml
blast_db: "resources/flu_db/fluA_db"
```

Verify the files:

```bash
ls -lh resources/flu_db/fluA_db.*
```

### Porechop command is not found on Apple Silicon

The workflow uses the maintained `porechop_abi` package on Apple Silicon and Linux ARM64. Confirm that the configuration contains:

```yaml
porechop_command: "porechop_abi"
```

The corresponding Conda environment should provide an executable named `porechop_abi`.

### A Conda environment fails to solve

First enable strict channel priority:

```bash
conda config --set channel_priority strict
```

Then remove only Snakemake's generated environments and allow them to be rebuilt:

```bash
rm -rf .snakemake/conda
```

Rerun the environment creation or complete workflow command.

## Reproducibility and data management

- `porechop_abi` is used instead of the original Porechop package for Apple Silicon and Linux ARM64 portability, with ab-initio adapter inference enabled.
- `fastplong` performs long-read quality and length filtering with its adapter-trimming step disabled to avoid a second adapter-trimming pass after Porechop ABI.
- Segment depth is calculated with `samtools depth -aa -q 0 -Q 0`; breadth is the fraction of all reference positions meeting the configured depth threshold.
- Sample metadata are validated before report generation and propagated into sample-specific metadata outputs.
- The Oxford Nanopore basecaller model is detected from the original FASTQ metadata for each sample, and the resulting Medaka selector is recorded in `results/<sample>/medaka/model.tsv`.
- Segment QC requires the configured depth, breadth-at-depth, minimum-length, and N-content criteria; by default this is median depth >=50x, >=95% of positions at >=50x, the configured segment-specific minimum length, and <=1% Ns. Consensus lengths above the configured upper guide generate a warning rather than a hard failure.
- Rule-specific Conda environments are stored under `.snakemake/conda/`.
- IRMA runs in Docker on macOS and in Apptainer or Singularity on the ARM64 cluster.
- The BLAST database build records source and build provenance in `resources/flu_db/database_manifest.tsv`; the default BLAST build image is pinned to `ncbi/blast-static:2.17.0`.
- Run-level provenance is written to `results/run_summary/run_provenance.tsv` and `.json`, and the JSON record is embedded in the portable `.wings` bundle.
- The BLAST reference archive, generated database, input reads, results, local configuration, and Snakemake working files should not be committed to Git. Commit the BLAST provenance manifest only when intentionally maintaining a fixed reference build record in the repository.
- `results/wings_report_bundle.wings` is generated from local reports and should be treated as analysis output; do not publish it unless its contents are appropriate for public release.
- IRMA and VADR use pinned container tags (`ghcr.io/cdcgov/irma:v1.3.5` and `staphb/vadr:1.7`). VADR influenza models are independently pinned to model release `1.7-1` and archive SHA-256 `5f09b8d95413251499a2e49a0b93ea119bc96814b4742d92ba55fd3bdadac7ec`; GenoFLU and other primary workflow tools use pinned Conda package versions to improve reproducibility.

Recommended `.gitignore` entries:

```text
/config.yaml
/metadata.tsv
/software/
.snakemake/
results/
data/*.fastq
data/*.fastq.gz
data/*.fq
data/*.fq.gz
resources/fluA_reference.fasta.zip
resources/flu_db/
resources/vadr-models/
*.log
.DS_Store
```

## Acknowledgements

WINGS integrates or builds on the following projects:

- Snakemake
- CDC IRMA
- Porechop ABI
- fastplong
- Medaka
- NCBI BLAST+
- GenoFLU
- VADR
- NanoPlot
- Oxford Nanopore Technologies sequencing software and file formats

Please cite the underlying tools used in an analysis according to their respective documentation and publications.

## Roadmap

Planned or under-development enhancements include:

- Additional interactive run-level visualizations and comparative views
- Improved genotype visualizations
- Automated public-health narrative summaries
- Additional export formats, including PDF

## Use of large language models and ChatGPT

Large language models, including OpenAI ChatGPT, were used during development of WINGS as a software-development and documentation assistant. Uses included brainstorming workflow design, reviewing and refining code, troubleshooting Snakemake and reporting behavior, and drafting or editing documentation.

All workflow logic, code changes, configuration decisions, and scientific interpretations remain the responsibility of the WINGS developers and should be independently reviewed and validated. ChatGPT is not used by the workflow to generate sequencing results, assemble influenza genomes, assign subtypes or genotypes, call variants, or replace the underlying bioinformatics tools described above.

Users adapting WINGS should apply the same standard to any LLM-assisted changes: review the generated code, verify tool parameters and dependencies, test changes on appropriate data, and document substantive LLM assistance when required by institutional, journal, or funding-agency policies.

## Optional segment phylogenies

The stage is off by default. To infer trees, add this block to `config.yaml` (or set `enabled: true` in an existing `phylogeny` block):

```yaml
phylogeny:
  enabled: true
  min_sequences: 5
  threads: 4
```

Run the report from the repository root with Docker Desktop running on macOS:

```bash
snakemake --configfile config.yaml --sdm conda --cores 4 \
  --resources mem_mb=90000 kaleido=1 \
  --rerun-incomplete results/run_summary/run_summary.html
```

WINGS selects QC-passing final consensus sequences for HA, NA, PB2, PB1, PA, NP, MP, and NS. It aligns each segment with MAFFT `--auto`, then uses IQ-TREE 2 with `-m MFP` for maximum-likelihood inference and automatic model selection and `-B 1000` for ultrafast bootstrap (UFBoot) branch support. On reruns, `-redo` lets IQ-TREE recompute a completed analysis when Snakemake finds its output out of date. Outputs are `phylogeny/{segment}_Tree.newick`, per-segment status and alignment files under `results/run_summary/phylogeny/`, and the Surveillance Explorer in `results/run_summary/run_summary.html`. Snakemake creates the tool environment from `envs/phylogeny.yaml`.

Every segment needs at least `phylogeny.min_sequences` QC-passing sequences (minimum 5). If a segment has fewer, check its `results/run_summary/phylogeny/{segment}.status.tsv` for the count and exclusions. With the stage disabled, the Explorer reads existing external trees from `phylogeny_dir` when available; generating all eight trees requires `enabled: true`.

After the run, check that the Explorer parsed all eight trees and that their tip counts match the QC-passing input counts:

```bash
python3 - <<'PY'
import csv
import json
from pathlib import Path

segments = ("HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS")
data = json.loads(Path("results/run_summary/surveillance_explorer.json").read_text())
assert set(data["trees"]) == set(segments), data["trees"].keys()

for segment in segments:
    status_path = Path(f"results/run_summary/phylogeny/{segment}.status.tsv")
    with status_path.open(newline="") as handle:
        status = next(csv.DictReader(handle, delimiter="\t"))
    tree = data["trees"][segment]
    assert status["status"] == "READY", (segment, status)
    assert tree["tip_count"] == int(status["sequence_count"]), segment
    assert tree["unmatched_tip_count"] == 0, segment
    print(f"{segment}: {tree['tip_count']} tips")

print("Explorer warnings:", data["warnings"])
PY
```

Review any Explorer warnings, the alignments, and `results/run_summary/phylogeny/{segment}.iqtree.iqtree` before interpreting the trees. Check sequence identity, selected models, and UFBoot support values in the IQ-TREE report; the Explorer displays numeric support labels of at least 70. UFBoot is an approximation, not the standard nonparametric bootstrap. Inspect the trees for unexpected placements; successful execution alone does not establish biological validity. See the [IQ-TREE tutorial](https://iqtree.github.io/doc/Tutorial) for UFBoot interpretation.
