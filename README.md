# Wild-bird Influenza Genomics and Surveillance (WINGS)

<p align="center">
  <img src="assets/wings_logo.jpg" alt="WINGS logo" width="360">
</p>

**Overview**

WINGS is a portable Snakemake workflow for genomic analysis of avian influenza A virus from Oxford Nanopore sequencing reads. It performs read preprocessing, influenza assembly, segment-level quality assessment, consensus polishing, variant calling, subtype screening, genotype assignment, annotation, and generation of interactive HTML reports.

The Surveillance Explorer combines sample locations with **USDA APHIS wild-bird detection context**, including a shared map with state-level detection counts, a dated timeline, source links, and snapshot provenance. These records provide context and do not establish epidemiological links between detections and WINGS samples.

An optional **Knowledge for action** briefing translates the run's results into plain-language public-health implications: what was learned, why it matters, and what it informs for surveillance. A locally hosted language model works from recorded subtype and genotype results, hosts, collection locations and dates, and available ecological and detection evidence. The briefing appears only on **Surveillance Explorer → Overview**, above the sample and host controls. See [Local public-health briefing](#optional-local-public-health-briefing) for setup and report refresh instructions.

WINGS was developed in support of the [**Pandemic ESCAPE Center**](https://escape.engr.uky.edu/), with a focus on genomic epidemiology, bioinformatics, and surveillance of avian influenza viruses in wild birds.

The workflow has been validated on Apple Silicon macOS using Snakemake, Conda, and Docker Desktop, and on Linux ARM64 SLURM clusters using Snakemake, Conda, and Apptainer. VADR is currently disabled on Linux ARM64 because the pinned VADR container image does not provide a Linux ARM64 image.

Most tools run in rule-specific Conda environments. IRMA runs in a container selected for the host environment.

## Features

- Oxford Nanopore influenza A analysis
- Porechop ABI adapter trimming
- `fastplong` read-quality and length filtering without a second adapter-trimming pass
- Sample metadata validation and integration
- IRMA `FLU-minion` assembly
- NanoPlot raw-read QC enabled by default and configurable with `run_nanoplot`
- Segment-level QC using depth, breadth-at-depth, expected-length, and N-content criteria
- Medaka consensus polishing and variant calling
- BLAST-based segment identification with identity/query-coverage evidence and confidence classification
- H5Nx analytical screening
- Conditional GenoFLU genotype assignment for H5Nx-screen-positive samples
- VADR sequence annotation and validation
- Interactive sample-level HTML reports
- Interactive sequencing-run summary report
- Optional internal eight-segment phylogeny inference from QC-qualified WINGS consensuses using MAFFT and IQ-TREE 2
- Linked eight-segment Surveillance Explorer with synchronized sample selection across timeline, map, and segment trees
- [Ecological context](docs/ecological-context.md) with aligned eBird reporting frequency, an offline BirdCast state pilot, and cached ERA5 weather; source scales, units, dates, and provenance remain visible
- [USDA APHIS outbreak context](#usda-aphis-outbreak-context) with state-level map shading, date filters, source-record browsing, and reproducible offline snapshots
- Optional [local public-health briefing](#optional-local-public-health-briefing) using Ollama, with staged assessment, plain-language writing, and evidence review
- Briefing context covering recorded subtype/genotype, host and location metadata, seasonal bird abundance, migration, weather, and public detections when supplied
- Portable `.wings` report bundles containing the run summary, all sample reports, and embedded run-level provenance
- Run-level provenance capturing workflow state, configuration hashes, environment hashes, runtime details, and BLAST database provenance
- Browser-based local report viewing at `wings.scotchlab.org` with no sequencing-data upload
- [Genotype frequencies](#public-genotype-frequency-graph) in the portal and Surveillance Explorer, with WINGS/public comparisons, genotype/host/location/month filters, separate sample/run denominators, automatic public-snapshot freshness checks, and SVG/CSV export
- Apple Silicon and Linux ARM64 support
- Docker, Apptainer, Singularity, or local IRMA execution

## Workflow

```text
Nanopore FASTQ
    |
    +--> NanoPlot raw-read QC
    |    (enabled by default; set run_nanoplot: false to disable)
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
    |    (from segment-QC-qualified polished consensuses)
    |
    +--> QC-qualified final segment consensuses
         |
         +--> Optional internal phylogeny (phylogeny.enabled: true)
              +--> MAFFT alignment
              +--> IQ-TREE 2 maximum-likelihood trees
              +--> Linked eight-segment Surveillance Explorer
    |
    v
Interactive HTML reports
    +--> Validated sample metadata
    +--> Sample report
    +--> Run summary report
    +--> Run-level provenance (TSV + JSON)
    +--> Portable WINGS report bundle (.wings; provenance embedded)
```

NanoPlot raw-read QC is included in the default `rule all` workflow. Set `run_nanoplot: false` in `config.yaml` to disable it. Internal phylogeny inference is opt-in with `phylogeny.enabled: true`; the Surveillance Explorer can still display supplied or pre-existing segment trees when internal inference is disabled.

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
│   ├── phylogeny.yaml
│   ├── porechop.yaml
│   ├── py-tools.yaml
│   ├── pysam.yaml
│   ├── reporting.yaml                 # macOS/default reporting environment
│   ├── reporting-linux-arm64.yaml     # Linux ARM64 reporting environment
│   └── seqtk.yaml
├── scripts/
│   ├── build_blast_db.sh
│   ├── build_ebird_cache.py
│   ├── build_ecological_context.py
│   ├── build_phylogeny_input.py
│   ├── build_report_bundle.py
│   ├── build_surveillance_explorer.py
│   ├── generate_public_health_interpretation.py  # evidence preparation and local model requests
│   ├── agency_briefing.py              # staged assessment, writing, and review
│   ├── install_vadr_models.sh           # pinned VADR influenza-model installer
│   ├── check_coverage.py
│   ├── coverage_table.py
│   ├── filter_ebird_for_wings.py
│   ├── install_quarto_linux_arm64.sh  # pinned ARM64 Quarto installer
│   ├── normalize_irma_outputs.py
│   ├── prepare_vadr_input.py
│   ├── public_reference_context.py
│   ├── resolve_medaka_model.py
│   ├── sample_summary.py
│   ├── validate_metadata.py
│   ├── extract_sample_metadata.py
│   ├── serve_reports.py
│   ├── summarize_blast.py
│   ├── summarize_vadr.py
│   ├── sample_summary.qmd
│   ├── run_summary.qmd
│   ├── write_run_provenance.py
│   └── report/
│       ├── escape-report.html
│       ├── escape-report.js
│       ├── genome-constellation.css
│       ├── genome-constellation.js
│       ├── map-boundaries.js
│       ├── run-report.html
│       ├── sample-report.css
│       ├── surveillance-explorer.css
│       └── surveillance-explorer.js
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

### Windows: WSL2 setup (validation pending)

Windows users need a Linux environment for the Bash-based workflow and its
Linux dependencies. The proposed Windows route is **Ubuntu on WSL2**, with Docker
Desktop's Linux-container backend. End-to-end WINGS execution on Windows/WSL2
has not yet been validated. Native PowerShell, Command Prompt, and Git Bash are
not documented execution environments. Windows on ARM also remains unvalidated.

#### 1. Install Ubuntu on WSL2

In **PowerShell as Administrator**, follow
[Microsoft's WSL installation guide](https://learn.microsoft.com/en-us/windows/wsl/install):

```powershell
wsl --install -d Ubuntu
```

Restart if prompted, then open Ubuntu and create its Linux user account.
In PowerShell, confirm that Ubuntu uses version 2:

```powershell
wsl --list --verbose
```

If an existing Ubuntu installation shows version 1, use
`wsl --set-version Ubuntu 2`; substitute the exact distribution name displayed
by the list command. Check current Docker Desktop system requirements separately;
the minimum Windows version for WSL installation is not necessarily sufficient
for a current Docker Desktop release.

#### 2. Enable Docker Desktop integration

Install and start [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
Use the WSL2 engine and enable Ubuntu under **Settings → Resources → WSL Integration**.
Docker must be using Linux containers. Follow
[Docker's WSL2 setup guide](https://docs.docker.com/desktop/features/wsl/)
if that setting is absent. Avoid maintaining a second Docker Engine installation
inside Ubuntu alongside Docker Desktop.

In the **Ubuntu terminal**, check connectivity:

```bash
docker info
```

A working Docker client in PowerShell alone does not establish that Ubuntu can
reach the daemon.

#### 3. Use Linux tools and paths inside Ubuntu

Run the README's Bash commands inside Ubuntu. Install the Linux edition of
[Miniforge](https://github.com/conda-forge/miniforge#install) inside Ubuntu,
matching the architecture reported by `uname -m`. A Windows Conda installation
does not supply Linux environments; the macOS Miniforge installer below also
does not apply.

Keep the checkout and working files in Ubuntu's Linux filesystem, for example
`~/projects/wings`, and use Linux paths in configuration files. A Windows path
such as `C:\\Users\\name\\data` is not a Linux path. Use a fresh Linux checkout
to preserve executable permissions and LF line endings. For filesystem guidance,
see [Microsoft's WSL environment guide](https://learn.microsoft.com/en-us/windows/wsl/setup/environment).

The existing platform-neutral Snakemake environment instructions are the starting
point for dependency setup. Platform-specific sections labeled macOS or Linux
ARM64 should not be applied to an x86-64 WSL2 installation.

#### Validation status

Before listing Windows as a validated platform, record the Windows build,
WSL version, Ubuntu release, CPU architecture, Docker Desktop version, dependency
versions, evaluated WINGS commit, and available resources. An independent tester
must document installation, report viewing, reproduction results, and failures
against agreed acceptance criteria. No Windows success or performance result is
claimed here.

The Windows job in `publication-evidence.yml` tests only the publication evidence
utility. It does not install or validate the WINGS workflow under Windows or WSL2.
See the [publication evaluation plan](docs/publication-evaluation.md).

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

### 2. Install Miniforge

Users who already have a working Conda or Mamba installation in the target
Linux or macOS environment may skip this step. On managed clusters, use the
site-provided Conda/Mamba module when available.

#### Apple Silicon macOS (zsh)

```bash
curl -fsSLo Miniforge3.sh \
  "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-$(uname -m).sh"

bash Miniforge3.sh -b -p "$HOME/miniforge3"
"$HOME/miniforge3/bin/conda" init zsh
exec zsh
```

#### Linux and Windows via WSL2 (Bash)

On Windows, complete the WSL2 setup above and open the **Ubuntu terminal**.
Install Linux Miniforge inside Ubuntu; a native Windows Conda installation
cannot supply the Linux environments used here. On Linux, use a Bash terminal.
The command selects the Linux installer for the architecture reported by
`uname -m`, including `x86_64` or `aarch64`.

Skip installation if a suitable Conda/Mamba installation already exists. The
installer below creates a new installation at `~/miniforge3`.

```bash
curl -fsSLo Miniforge3.sh \
  "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-$(uname -m).sh"

bash Miniforge3.sh -b -p "$HOME/miniforge3"
"$HOME/miniforge3/bin/conda" init bash
```

Close and reopen the Bash/Ubuntu terminal before continuing. If you use zsh
on Linux, initialize it with `conda init zsh` using the same full Conda path,
then reopen zsh.

Installing Miniforge does not establish full workflow compatibility. WINGS
Windows/WSL2 validation remains pending. See the
[Miniforge installation documentation](https://github.com/conda-forge/miniforge#install)
for installer requirements.

#### All platforms

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
| `specimen_type` | Optional | Specimen or swab type |
| `country` | Required | Country of collection |
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

run_nanoplot: true
run_genoflu: true
run_surveillance_explorer: true

phylogeny:
  enabled: false
  threads: 4
  min_sequences: 5
phylogeny_dir: "phylogeny"
phylogeny_pattern: "{segment}_Tree.newick"

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

run_nanoplot: true
run_genoflu: true
run_surveillance_explorer: true

phylogeny:
  enabled: false
  threads: 4
  min_sequences: 5
phylogeny_dir: "phylogeny"
phylogeny_pattern: "{segment}_Tree.newick"

run_vadr: false
vadr_runtime: auto
vadr_image: "docker://staphb/vadr:1.7"
vadr_mkey: flu
vadr_model_dir: "resources/vadr-models/vadr-models-flu-1.7-1"
vadr_forcegene: true
run_summary: true
```

Use `irma_runtime: "singularity"` instead when Singularity is installed rather than Apptainer. `irma_runtime: "auto"` selects Apptainer, Singularity, Docker, or local IRMA in that order based on what is available.

The `run_nanoplot`, `run_genoflu`, `run_vadr`, and `run_summary` settings control whether those analyses or run-level outputs are requested as default workflow targets. `run_surveillance_explorer` controls whether the linked Explorer is populated in the run report. NanoPlot is enabled by default; set `run_nanoplot: false` to omit raw-read NanoPlot QC from `rule all`. On Apple Silicon macOS, keep `run_genoflu: true`, `run_vadr: true`, and `run_summary: true` for a complete production run. On Linux ARM64, keep `run_genoflu: true` and `run_summary: true`, but set `run_vadr: false` when using the pinned VADR container image because that image does not provide a Linux ARM64 build.

Internal tree inference is disabled by default. Set `phylogeny.enabled: true` to build one tree per influenza segment from QC-qualified final WINGS consensuses. `phylogeny.threads` controls MAFFT and IQ-TREE 2 threads, and `phylogeny.min_sequences` sets the minimum number of QC-qualified sequences required for a segment; the current Snakefile requires at least 5. `phylogeny_dir` and `phylogeny_pattern` control the final Newick locations and names.

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

### Internal eight-segment phylogeny

WINGS can optionally infer sample-only phylogenies for the eight influenza A segments. Enable this with:

```yaml
phylogeny:
  enabled: true
  threads: 4
  min_sequences: 5
phylogeny_dir: "phylogeny"
phylogeny_pattern: "{segment}_Tree.newick"
```

For each segment, WINGS collects the final consensus sequence from samples whose existing segment QC decision qualifies that segment. The merged per-sample FASTA supplies the final Medaka-polished sequence, or the workflow's explicit IRMA fallback when applicable, while `coverage.tsv` supplies the existing segment QC decision and selected contig. WINGS writes a segment input FASTA and status table under `results/run_summary/phylogeny/`.

A segment proceeds only when at least `phylogeny.min_sequences` QC-qualified sequences are available. WINGS aligns the segment sequences with MAFFT (`--auto`) and infers a maximum-likelihood tree with IQ-TREE 2 using ModelFinder (`-m MFP`) and 1,000 ultrafast bootstrap replicates (`-B 1000`). The workflow uses a fixed IQ-TREE seed of 1 for reproducibility. Final Newick trees are written according to `phylogeny_dir` and `phylogeny_pattern`; with the defaults, these are `phylogeny/HA_Tree.newick`, `phylogeny/NA_Tree.newick`, and the corresponding files for PB2, PB1, PA, NP, MP, and NS.

When internal phylogeny is enabled, these generated trees are tracked as Snakemake dependencies and supplied to the Surveillance Explorer. If internal phylogeny is disabled, the Explorer can display non-empty pre-existing trees matching `phylogeny_dir` and `phylogeny_pattern`. When `public_references.enabled: true` and `public_references.tree_dir` is configured, the reviewed contextual trees from that directory are used for Explorer display instead.

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

### NanoPlot raw-read QC

NanoPlot is included in the default final targets when `run_nanoplot: true` (the default). Set `run_nanoplot: false` in `config.yaml` to omit NanoPlot from `rule all`. You can still target an individual NanoPlot result directly.

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
├── nanoplot/                    # enabled by default; configurable with run_nanoplot
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

When internal phylogeny is enabled, run-level phylogeny intermediates are written under:

```text
results/run_summary/phylogeny/<segment>.input.fasta
results/run_summary/phylogeny/<segment>.status.tsv
results/run_summary/phylogeny/<segment>.aligned.fasta
results/run_summary/phylogeny/<segment>.mafft.log
results/run_summary/phylogeny/<segment>.iqtree.log
results/run_summary/phylogeny/<segment>.iqtree.*
```

The final segment trees are written according to `phylogeny_dir` and `phylogeny_pattern`. With the defaults:

```text
phylogeny/HA_Tree.newick
phylogeny/NA_Tree.newick
phylogeny/PB2_Tree.newick
phylogeny/PB1_Tree.newick
phylogeny/PA_Tree.newick
phylogeny/NP_Tree.newick
phylogeny/MP_Tree.newick
phylogeny/NS_Tree.newick
```

The sequencing-run report is written to:

```text
results/run_summary/run_summary.html
```

The HTML report separates **Pipeline Results** from **Surveillance Explorer**. Pipeline Results contains **Run Summary**, **Sample Detail**, **Subtype/Genotype Distribution**, and **Genome Coverage**. The subtype tab shows HA and NA distributions and, when GenoFLU is enabled, genotype counts among H5Nx-screen-eligible samples. Samples without an assigned GenoFLU genotype are shown separately; samples ineligible for GenoFLU are excluded.

The Explorer has **Overview**, **Genome**, **Ecology**, **Sampling & Detections**, **Concordance**, and **Outbreak context** tabs. Its linked timeline, map, and segment trees share sample selection. The optional Knowledge for action briefing appears on Overview only; it summarizes the whole run and does not change with sample selection or host filters.

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

### Public genotype frequency graph

Open **Surveillance Explorer → Genotype frequencies** in a completed run
report to compare WINGS samples with public records from
[andersen-lab/avian-influenza](https://github.com/andersen-lab/avian-influenza).
The standalone graph is also linked from the portal home and run setup pages,
or available at `genotypes.html` on the local runner. Run reports embed the
chart code and data snapshots for offline viewing and portable `.wings` sharing.
The standalone portal shows public data; a completed run report also supplies
that run's WINGS samples.

#### Sources, filters, and denominators

| Data source | Display and counting unit | Initial month range |
| --- | --- | --- |
| **All** (default) | Aligned WINGS and Public Data panels, with shared genotype colors and separate denominators | WINGS collection span when usable WINGS dates are available; otherwise the available data span |
| **WINGS** | One record per unique sample ID in the run | WINGS collection span |
| **Public Data** | One record per public SRA run; multiple runs can represent the same specimen | Full available public collection span |

Views open by collection month when usable dates are available. The month range
can be widened or narrowed, and selections are remembered for each source view
while the page remains open. The default WINGS span is derived from the current
run, not a fixed date range.

Use the **genotype, host, location, and month** dropdowns to filter the graph.
In **All**, the selected filters apply to both panels. Selecting a genotype
shows its frequency while retaining all eligible genotypes in the denominator;
it does not make that genotype automatically equal 100%.

Location filters recognize `USA` and `United States` as the same country and
ignore empty slash-separated fields. Selecting a country includes its recorded
states and counties; selecting a state includes its recorded counties. For
example, **United States / Kentucky** includes WINGS locations stored as
`USA / Kentucky` and public locations stored as `United States/Kentucky//`.
Records without the selected state or county information cannot be assigned to
that location by the filter.

Percentages default to records **with an assigned genotype**, calculated
separately for each source. An alternate denominator includes all selected
records. WINGS counts samples; public data counts SRA runs. Unassigned and
unavailable results are reported separately, and records without a usable month
are excluded from date-based views. These are descriptive frequencies in the
included sequencing records, not estimates of population prevalence.

#### Calendar-month toggle

**Show all calendar months** controls whether months without eligible records
remain on the time axis:

- **Checked:** show every calendar month in the displayed range.
- **Unchecked, WINGS or Public Data:** omit months with no eligible records for
  that source and the selected denominator.
- **Unchecked, All:** omit a month only when **both sources** have no eligible
  records. If either source has data, the month remains visible in both panels
  so their time axes stay aligned.

The page explains when every month already has eligible records and toggling
will not change the graph. To hide months empty only in WINGS, select **WINGS**.
Dashed columns indicate unavailable frequencies, not measured zero frequency.
When months are omitted, equal bar spacing does not represent elapsed time.
Changing this display option does not change counts, percentages, or CSV exports.
Graphs and downloaded SVGs use the ASU color palette, with patterns for extra
categories. CSV downloads provide the underlying counts and denominators.

#### Keeping public data current

Each report build checks the public snapshot and, under the default refresh
policy, attempts to refresh it when it is **more than seven days old**. Downloads
are cached outside the repository. If a download fails, the last valid snapshot
is retained; a successful report build therefore does not by itself prove that
new data were downloaded. Refresh happens during report generation, **not
installation**, and does not install a background scheduler. Opening an existing
HTML report or `.wings` bundle does not refresh its embedded data.

For the standalone portal, run a freshness check:

```bash
python scripts/refresh_genotype_frequencies.py
```

To request a new download immediately, regardless of snapshot age:

```bash
python scripts/refresh_genotype_frequencies.py --force
```

The script downloads the genotype and collection-metadata tables from one
source commit and rebuilds `assets/data/genotype-frequencies.json`. Reload the
portal page afterward. Automatic report refresh saves a separate copy in
`results/run_summary/public_genotype_frequencies.json`; it does not modify the
portal's tracked snapshot. Refreshing the portal alone does not update an
already-built report or bundle.

Check the genotype page's source information for the **snapshot build date,
source commit, and report refresh status/note**, when present. For a report,
`results/run_summary/public_genotype_frequencies.json` also records `built_at`,
`source_commit`, and `report_refresh`. A `cached` status means the saved snapshot
was reused; check its date and the accompanying note when assessing freshness.
The report preserves the exact snapshot used for reproducibility.

#### Rebuild an existing report and bundle

From the WINGS repository, rebuild using the saved analysis results:

```bash
snakemake results/wings_report_bundle.wings \
  --cores 1 \
  --use-conda \
  --allowed-rules run_summary_html wings_report_bundle \
  --forcerun run_summary_html wings_report_bundle
```

Open `results/run_summary/run_summary.html`, or reload
`results/wings_report_bundle.wings` in the bundle viewer. This runs the report's
freshness check and embeds the resulting snapshot. It rebuilds the report and
bundle from existing results without rerunning sequencing analysis or Ollama.

Offline mode, source-commit pinning, local TSV import, join rules, date precision,
source provenance, and exports are documented in
[Genotype frequencies](docs/genotype-frequencies.md).

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

### Optional local public-health briefing

The **Knowledge for action** panel presents a headline and three bullets under
**Public Health Implications**:

- **What we learned:** the most useful finding from the sampled collection.
- **Why it matters:** how the genomic findings and available context fit together.
- **What this informs:** a proportionate implication for surveillance or a specific information gap.

WINGS prepares factual summaries from existing results. The local model assesses
them, writes the briefing, and reviews the draft against the fuller evidence.
The writing prompt asks for familiar language without statistical equations,
methods jargon, or internal evidence codes. Subtype screening and genotype
assignment retain their recorded status; missing or unassigned results remain
distinct from negative results.

Context can include USDA APHIS wild-bird detections, seasonal bird abundance,
BirdCast migration estimates, and weather. The briefing uses the supplied
geographic scope, date windows, source coverage, and comparison results. Seasonal
abundance is distinct from measured migration, and short-term weather is distinct
from a climate trend. An unavailable comparison does not establish that a
relationship is absent. The briefing generator summarizes existing analyses;
it does not run new association tests or retrieve missing context.

#### Enable the local model

This feature is disabled by default. Install and start Ollama separately, then
download the model you intend to use. For the model used during development:

```bash
ollama pull gpt-oss:20b
```

Add or update this block in your local `config.yaml`:

```yaml
public_health_interpretation:
  enabled: true
  mode: staged
  audience: wildlife
  provider: ollama
  model: "gpt-oss:20b"
  url: "http://127.0.0.1:11434/api/chat"
  timeout_seconds: 180
  allow_remote: false
```

Supported audiences are `wildlife`, `animal_health`, and `public_health`. The
model tag is configurable; WINGS does not install Ollama or download model
weights automatically. The workflow uses staged mode by default when enabled;
standalone commands should pass `--mode staged` explicitly. Each model request
has its own timeout, so the complete staged process can take longer than
`timeout_seconds`.

WINGS sends structured result summaries, sample identifiers and metadata,
contextual evidence, and any explicitly supplied briefing context to the
configured model endpoint. It does not send raw reads, consensus sequences, or
tree files. With the loopback endpoint above and a locally served model,
inference runs on your computer; WINGS does not train or fine-tune the model.
Nonlocal endpoints require an explicit opt-in.

The output is `results/run_summary/public_health_interpretation.json`. It retains
the evidence, prompts, responses, model identity, and validation diagnostics,
and is embedded in the HTML report. Sharing the HTML or a rebuilt `.wings`
bundle therefore also shares that embedded record. Automated checks and a
separate review call to the same model support traceability; they do not replace
scientific review. If a staged generation fails, its diagnostics are retained
and the report identifies the briefing as unavailable.

#### Regenerate a briefing from completed analyses

For a run with existing concordance outputs, use the commands below from the
repository root. Replace `results` with the completed run's actual results
directory where needed, including runs stored under `~/.wings/runs/`.

```bash
python scripts/generate_public_health_interpretation.py \
  --explorer-json results/run_summary/surveillance_explorer.concordance.json \
  --concordance-json results/run_summary/concordance/concordance.json \
  --host-map resources/ebird_host_codes_2025.tsv \
  --output results/run_summary/public_health_interpretation.staged.json \
  --mode staged \
  --audience wildlife \
  --enabled true \
  --provider ollama \
  --model "gpt-oss:20b" \
  --url http://127.0.0.1:11434/api/chat \
  --max-output-tokens 2048 \
  --timeout 180 \
  --fail-on-error \
  --print-narrative &&
cp results/run_summary/public_health_interpretation.staged.json \
   results/run_summary/public_health_interpretation.json
```

The copy runs only after successful generation. These commands reuse completed
analyses and do not rerun read processing, assembly, or tree inference. For a
run without concordance outputs, use `surveillance_explorer.json` instead and
omit `--concordance-json`; the briefing can use only the evidence in that input.

#### Rebuild the HTML after a briefing or layout change

With the required report inputs already present, rebuild only the HTML:

```bash
snakemake results/run_summary/run_summary.html \
  --cores 1 \
  --use-conda \
  --allowed-rules run_summary_html \
  --forcerun run_summary_html
```

This embeds the current briefing and report assets without calling Ollama or
rerunning upstream analyses. A layout-only change needs just this rebuild.
Use the configuration and output directory belonging to the completed run.
Rebuild the `.wings` bundle separately before sharing; an existing bundle keeps
its previously embedded HTML and data.

See [Local LLM interpretation](docs/local-llm-interpretation.md#staged-agency-briefing-v170)
for optional decision questions, user-supplied context, and saved diagnostics.

### eBird Status & Trends phenology: access key required for downloads

The Status & Trends phenology stage (`ebirdst_phenology`) uses raster data and is separate from the EBD observation and sampling-event reporting context described below. When a required raster is not already cached, this stage requires an **eBird Status & Trends access key** in the `EBIRDST_ACCESS_KEY` environment variable. Do not assume a general eBird API token grants Status & Trends data access. A key is unnecessary when all required rasters are already cached.

Set the key in the environment that starts WINGS, before launching a run:

```bash
export EBIRDST_ACCESS_KEY='YOUR_STATUS_AND_TRENDS_KEY'
```

Replace the placeholder with your own key. Keep the key private; do not commit it to the repository or include it in screenshots, logs, or shared reports.

- **Terminal launch:** Set the variable in the same terminal before running your usual WINGS command.
- **Browser launch:** The local WINGS server or launcher must inherit the variable when it starts. Setting it in a separate terminal, refreshing the browser, or clicking **Resume Run** does not update an already-running server's environment. When no run is active, restart the WINGS launcher from the terminal where the key is set, then resume the existing run in the browser. If another service starts the launcher, configure the variable in that service's environment instead.

**Current behavior:** If a required raster is missing and the key is unset, the phenology stage exits with the following error and Snakemake stops the workflow:

```text
ERROR: At least one required Status & Trends raster is not cached and EBIRDST_ACCESS_KEY is not set.
```

The detailed message is recorded in the run's `results/run_summary/phenology/phenology.log`. Preserve existing results when addressing this error; Docker cleanup and deleting outputs do not resolve a missing credential.

**Planned improvement (not yet implemented):** Check credential/cache availability before lengthy processing. If required phenology data cannot be obtained because the key is missing, issue a warning, record phenology as unavailable with the reason, and continue the remaining workflow. Reports should distinguish unavailable context from zero abundance. Until this change is implemented, the credential requirement above still applies.

### Optional eBird reporting context

eBird is an external ecological context, not an infection or abundance estimate. Keep the large EBD observation and sampling-event files outside the WINGS repository. After downloading an authorized matching pair, summarize it locally using `scripts/filter_ebird_for_wings.py` with `--metadata metadata.tsv`, `--observations`, `--sampling`, and an explicit `--map CAGO='Canada Goose'` for coded hosts. Save aggregates to `results/run_summary/ebird/` (the script's `--output-dir`). The script discovers which species are in the EBD and writes `ebird_samples.tsv`, `ebird_monthly.tsv`, and `ebird_species.tsv`; it does not copy raw EBD records into WINGS.

To have Snakemake build eBird summaries automatically before the Surveillance Explorer, set `ebird.enabled: true` in your local `config.yaml`. For an existing cache, set `build_cache: false`, use the absolute path to its directory, and supply a matching sampling-event export and release files:

```yaml
ebird:
  enabled: true
  build_cache: false
  cache_dir: /Users/matthewscotch/Documents/ebird_wings_cache
  sampling_file: /absolute/path/to/matching_sampling_events.txt.gz
  release_dir: /Users/matthewscotch/Downloads/ebd_relAug-2026
  release: Aug-2026
  days: 30
  radius_km: null
  host_map_file: resources/ebird_host_codes_2025.tsv
  host_map: {}
```

Use sampling-event data from the same release and with all relevant regions, dates, and checklists; a species-filtered download is insufficient for automatically comparing other hosts. WINGS includes `resources/ebird_host_codes_2025.tsv` for coded host names, derived from the [Institute for Bird Populations' 2025 four-letter list](https://www.birdpop.org/pages/birdSpeciesCodes.php): 2,212 species codes plus the local `CAGO` alias. Set `host_map_file` to another TSV with `host` and `ebird_species` columns when using another code reference; paths relative to WINGS are supported. `host_map` supplies additional local aliases; conflicting entries are rejected. The IBP list covers North and Central America and the Caribbean, not all birds worldwide. In that list Canada Goose is `CANG`; `CAGO` is a local WINGS alias. Hosts entered as eBird common or scientific names require no code mapping. Unknown codes remain `UNMAPPED_HOST`; verify name changes against the current eBird taxonomy rather than assigning a plausible species. This bundled reference contains no original eBird observation or sampling records. With this configuration, the ordinary `results/run_summary/run_summary.html` or `results/wings_report_bundle.wings` target first attaches the sampling events (if needed), computes the eBird summary, embeds the release terms and citation, and then builds the report. Setting `ebird.enabled: false` explicitly hides older eBird results in the Explorer. The eBird stage stays disabled until both the sampling file and paths have been configured.

To build a **new** cache through Snakemake, set `build_cache: true` and `observations_file` to the full EBD `.txt.gz` in an **empty** `cache_dir` outside WINGS. This reads the complete observation archive once and may take hours. For the already completed 837,883-record cache, keep `build_cache: false`; the raw archive is never reopened by routine report builds. Changes to the sampling source or host mappings trigger the relevant downstream steps. If metadata expands beyond the cached geography/date windows or the source EBD release changes, build a new cache. The original cache records remain outside Git and the report bundle.

For very large EBD releases, create a local cache once, using metadata to select country/state/date windows while keeping **all taxa** in those windows:

```bash
python3 scripts/build_ebird_cache.py \
  --metadata metadata.tsv \
  --observations "$HOME/Downloads/ebd_relAug-2026/ebd_relAug-2026.txt.gz" \
  --cache-dir "$HOME/Documents/ebird_wings_cache" \
  --days 30

# When a matching sampling-event file becomes available, add it to this cache:
python3 scripts/build_ebird_cache.py \
  --metadata metadata.tsv \
  --sampling /path/to/matching_sampling_events.txt.gz \
  --sampling-only \
  --cache-dir "$HOME/Documents/ebird_wings_cache" \
  --days 30

python3 scripts/filter_ebird_for_wings.py \
  --metadata metadata.tsv \
  --observations "$HOME/Documents/ebird_wings_cache/observations.txt.gz" \
  --sampling "$HOME/Documents/ebird_wings_cache/sampling.txt" \
  --species-catalog "$HOME/Documents/ebird_wings_cache/species_catalog.tsv" \
  --map 'CAGO=Canada Goose' \
  --release Aug-2026 \
  --output-dir results/run_summary/ebird
```

The first command still reads the entire compressed observation file once; later filtering uses the smaller cache. A matching eBird sampling-event download is required for the complete-checklist denominator; the cache builder can attach it later without rescanning observations. The catalog covers **all taxa in the original observations**, so a species with zero reports in the cached region remains distinguishable from a species absent from the original file. The cache holds original eBird records and must stay outside Git, public downloads, and `.wings` bundles. Its metadata scope and `--days` are recorded in `cache_manifest.json`; rebuild it if later samples fall outside that scope or if you switch EBD releases. Reuse it for different host mappings and sample coordinates within the cached locations and dates.

If you obtain a better matching sampling-event export for the same EBD release and metadata scope, repeat the `--sampling-only` command with `--replace-sampling`. This replaces only the cached sampling events, without reopening the full observation archive. Check that the sampling-event export covers the locations and dates of every host species being compared; a taxon-specific request may not provide a suitable denominator for all hosts.

If `ebird_samples.tsv` exists when Snakemake builds the run summary, the Surveillance Explorer displays READY results in a dedicated eBird panel. Samples sharing a host species, geographic scope, and collection-date window share **one** checklist context; do not add those checklist totals across samples. State-only metadata yield state-wide context; a local radius requires both sample coordinates and `--radius-km`. When these EBD aggregates are absent, the panel is hidden and the standard report still works. This behavior does not apply to the separate Status & Trends phenology stage; see its access-key requirement above. Rebuild `results/run_summary/run_summary.html` after updating eBird aggregates, then rebuild the portable bundle if needed.

### Linked eight-segment genome explorer

The Surveillance Explorer selects one sample across the collection timeline, map,
and all eight segment trees. Use **Sample** to select even an undated or
ungeolocated sample. **All eight segments** shows available trees together;
**Single segment** or a segment tab opens a larger tree. Selection is retained
when changing views or host filters. A selected sample outside the host filter
is explicitly identified and remains highlighted in the trees.
No sample is selected initially. Clicking a selected sample again, choosing the
empty sample option, or using **Clear selection** clears it. **Clear selection**
also restores **All eight segments**. Host filtering uses the host-distribution
buttons, and the timeline retains its full-run axis.

The map includes U.S. state boundaries (including Alaska and Hawaii), Canadian
province and territory boundaries, and generalized country outlines elsewhere.
**Sample area** fits all valid coordinates in the run and stays fixed when
filtering hosts. Use **North America** or **World** for broader context.
Drag the map to pan, use **+ / −** to zoom, and use **Reset view** to return to
the sample area. With the map focused, arrow keys pan, +/− zoom, and 0 resets.
Map navigation retains the selected sample. A drag beginning on a point does
not select or cycle that point's samples.

Click a sample point to show its ID, host, collection date, and sample-report
link directly beneath the map. Numbered points group samples sharing the same
coordinates: click repeatedly to cycle through them, or choose a sample by name
in the selection panel. State/province labels are placed within their visible
geometry; narrow areas use abbreviations where full names will not fit.
Locations outside a chosen extent are counted explicitly; samples without valid
coordinates remain available through the sample selector. Boundaries are bundled
with the report and work offline. See
[`map-boundaries.md`](scripts/report/map-boundaries.md) for sources and limitations.

The explorer shows the recorded GenoFLU consensus genotype and linked segment
trees. Trees can come from WINGS internal phylogeny inference, from non-empty
pre-existing files matching `phylogeny_dir` and `phylogeny_pattern`, or from a
reviewed `public_references.tree_dir` when public reference context is enabled.
When `phylogeny.enabled: true`, WINGS builds sample-only trees from QC-qualified
final consensuses using MAFFT and IQ-TREE 2; each segment must meet
`phylogeny.min_sequences` before alignment and tree inference proceed. When a
public-reference tree directory is configured, those contextual trees are used
for Explorer display instead of the sample-only tree set.

Detailed segment QC and coverage remain in the existing sample report;
the Surveillance Explorer does not repeat the segment-evidence table.
**Open sample report** leads to the detailed report and its supporting outputs,
including in the portable bundle.

An unavailable tree and a sample absent from an available tree are distinct
states. An absent tip alone does not establish QC failure. Multiple matching
tips are all highlighted. Recorded tree support labels are displayed without
assuming a method, percentage scale, or confidence threshold.

The data builder reads existing per-sample coverage tables and GenoFLU outputs.
Snakemake tracks these as report dependencies. Standalone callers may supply
repeated `--coverage <sample>/coverage/coverage.tsv` and
`--genoflu <sample>/genoflu/GenoFLU.tsv` arguments. Older explorer data still
display trees, with unavailable evidence labeled **Not recorded**.

After updating WINGS, rebuild the explorer and report bundle from your usual
configured results directory (replace `results` if needed):

```bash
snakemake results/run_summary/surveillance_explorer.json \
  --configfile config.yaml --sdm conda --cores 4 \
  --resources mem_mb=90000 kaleido=1 --force &&
snakemake results/run_summary/run_summary.html \
  --configfile config.yaml --sdm conda --cores 4 \
  --resources mem_mb=90000 kaleido=1 --force &&
snakemake results/wings_report_bundle.wings \
  --configfile config.yaml --sdm conda --cores 4 \
  --resources mem_mb=90000 kaleido=1 --force
```

Validate with one complete and one incomplete sample: confirm selection in every
available tree and open a sample report from the rebuilt bundle to inspect
its detailed segment evidence. These commands rebuild the data, then the HTML,
then the bundle so embedded JavaScript and snapshot data are refreshed. Existing
upstream analysis results are reused when their dependencies are current.
Reopen the newly generated bundle after rebuilding.

Developer checks:

```bash
python -m unittest discover -s tests -p test_linked_genome_explorer.py -v
python -m unittest discover -s tests -p test_outbreak_context.py -v
node --test tests/test_linked_genome_state.cjs tests/test_surveillance_map.cjs tests/test_outbreak_context.cjs
# Requires Playwright plus its Chromium browser:
node tests/test_linked_genome_explorer.cjs
```


### USDA APHIS outbreak context

The U.S. Department of Agriculture (USDA) Animal and Plant Health Inspection Service (APHIS) publishes wild-bird detections of highly pathogenic avian influenza (HPAI).

The Surveillance Explorer can display a pinned USDA APHIS wild-bird detection CSV as
an offline state-shading layer on the existing sample map, a dated timeline,
and a paginated source-record browser. Neighboring states retain their detection
counts when a sample is selected. Host-colored points represent WINGS samples;
teal state shading represents APHIS source-record counts. The national relative
color scale is shared across all states for the displayed date window.

- **Click a state:** open an on-map summary with its full name, record count,
  date basis, date window, and missing-date count. **View records** opens the
  corresponding source records, including county details.
- **Zoom to [state]:** fit the clicked state without requiring a selected WINGS
  sample. A sample without coordinates is represented by its recorded state
  outline, with its geographic precision labeled; no point is invented.
- **Lock date window:** keep the displayed dates while comparing samples.
  Editing From or Through also locks the window.
- **APHIS state shading:** show or hide the shading while retaining the timeline
  and source records.
- **Solid burgundy outline:** selected WINGS sample's recorded U.S. state.
  **Dashed outline:** state being browsed in the APHIS timeline and record list.

Clicking a state changes the APHIS record scope without changing the selected
WINGS sample. Selecting a different sample restores the record scope to that
sample's state. Host filters affect WINGS sample points only.
Selecting a WINGS sample defaults to matching its recorded U.S. state and a
collection-date window of ±30 days. Sample coordinates are not required. Change
the window, geography, or date basis in the panel. Date detected is kept separate
from collection date; a missing collection date is never replaced silently.

APHIS reports county/state geography in this CSV. WINGS shades state aggregates,
with county names retained in the source records. It does not infer exact
locations or calculate distance-based associations. Counts represent CSV rows;
repeated rows are retained because the export has no unique record IDs.
Geographic or temporal overlap does not imply epidemiological linkage.
Non-U.S. areas are outside this APHIS layer's coverage. A zero count means no
matching dated rows in the loaded snapshot and filters; it does not establish
absence of infections. Counts are not incidence or prevalence estimates.

The CSV has no unique APHIS record identifiers or record-specific URLs. Source
links open the APHIS table. Local record references identify the snapshot by its
SHA-256 digest and one-based CSV data-record number. The provenance panel shows
the snapshot date, date ranges, checksum, and retained repeat-row count.

A snapshot at `resources/aphis/hpai-wild-birds.csv` is detected automatically.
For explicit configuration, add to `config.yaml`:

```yaml
outbreak_context:
  enabled: true
  csv: resources/aphis/hpai-wild-birds.csv
  provenance: resources/aphis/hpai-wild-birds.provenance.json
```

Set `enabled: false` to disable context even if a snapshot exists. To refresh,
download a CSV from the [APHIS wild-bird detections page](https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza/hpai-detections/wild-birds),
then import it and matching provenance with:

```bash
python scripts/import_aphis_snapshot.py /path/to/downloaded-aphis.csv
```

The importer validates the export, preserves its bytes, and writes matching
provenance. Its recorded import date is not an APHIS release date.
Report builds use the local snapshot and do not fetch live data. Rebuild the
explorer JSON, HTML, and bundle using the three commands above after an import.
Previously saved or shared bundles retain the snapshot embedded when they were
built. See
[Outbreak context](docs/outbreak-context.md) for semantics, provenance, and exact
rebuild commands.

### Ecological context: eBird, BirdCast, and weather

The Surveillance Explorer includes three sample-linked ecological views with a
shared calendar-date axis. eBird retains its validated host reporting frequency,
checklist denominator, original aggregation period, geographic scope, and
release. The BirdCast state pilot displays imported nightly migration estimates
and missing-data explanations. Weather shows cached ERA5 daily mean temperature,
precipitation totals, and daily maximum wind speed, with units, grid coordinates,
resolution, and local timezone. The display does not assign point weather when
sample coordinates are missing or imply epidemiological linkage.

Build the first weather snapshot with:

```bash
python scripts/build_ecological_context.py \
  --metadata results/metadata/validated_metadata.tsv \
  --days 90 --fetch-weather
```

BirdCast numeric data require a separately supplied, provenance-backed pilot
CSV; no automatic BirdCast feed or real numeric snapshot is bundled. Missing
data are labeled unavailable, and the source dashboard link remains visible.
Reports and saved `.wings` bundles work offline. See
[Ecological context](docs/ecological-context.md) for source definitions, import
format, refresh behavior, configuration, and the three-step report rebuild.

## Public reference context

The Surveillance Explorer can annotate supplied contextual segment trees with a
reviewed **GenBank accession.version metadata manifest**. Public references have
teal square tips, clickable source records, explicit date precision and provenance,
and linked selection across segments with documented common sample identity.
WINGS sample QC stays separate. This display feature does not retrieve sequences
or add references to sample-only trees; contextual trees must already be supplied.

See [public reference context](docs/public-reference-context.md) and
[example configuration](config/public-references.example.yaml).

## Use of AI Statement

Generative AI tools were used during the development of WINGS to assist with software development tasks including code drafting, debugging, documentation, test development, and workflow refinement. All AI-generated or AI-assisted content was reviewed, tested, and modified by the project developers before inclusion in the repository. Scientific, analytical, and software-design decisions remain the responsibility of the authors and maintainers of WINGS.

The optional local public-health briefing is a separate, user-enabled runtime
use of a language model. It produces a narrative from existing WINGS evidence;
it does not replace the analytical pipeline. Passing the automated briefing
checks does not mean a human has reviewed or endorsed the generated conclusions.
