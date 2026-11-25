# Command-line and HPC guide

[README](../README.md) · [Questions and answers](../faq.md) · [Report/reference guide](report-reference.md)

Use this guide for a source checkout on a Mac or Linux computer, or inside an
HPC allocation. WINGS Desktop manages a separate runtime and installed source
snapshot; do not run these installation commands inside its release directory.

**Windows users: start with the [Windows/WSL2 setup guide](windows-wsl2.md)**.
Install Ubuntu on WSL2 before following the Linux commands, and use a Linux
Conda installation inside Ubuntu rather than a Windows Conda prompt.

## Requirements and execution routes

You need Git, Bash, Conda or Mamba, and Snakemake. Most analysis tools use
rule-specific Conda environments. IRMA additionally requires the runtime selected
in the local configuration: Docker, Apptainer, Singularity, or a local installation.

Linux reference setup also needs `curl`, `unzip`, `tar`, `gzip`, and a SHA-256
checksum utility. Minimal Ubuntu/WSL installations may lack `unzip`; check these
prerequisites before downloading resources. The [WSL2 guide](windows-wsl2.md#2-install-linux-system-prerequisites--ubuntu)
provides the explicit Ubuntu package-install command.

| Route | Runtime considerations |
| --- | --- |
| Native Apple Silicon | Use ARM64 Conda/Python and a running Docker Desktop for the configured container jobs. This differs from the desktop app's Linux AMD64 controller. |
| Linux ARM64 / SLURM | Use a compatible Conda environment, the site's IRMA runtime, writable project storage, and the supplied Linux ARM64 Quarto installer. A working native VADR installation can be used. |
| [Windows / WSL2](windows-wsl2.md) | Ubuntu under WSL2 with Linux Conda and Docker Desktop integration. Setup, dry run, and analysis launch have been reported; completed-analysis validation remains pending. |

Check Docker connectivity with `docker info` on the machine running the analysis.
The CLI alone does not start the daemon. Docker memory limits are separate from
Snakemake's `mem_mb` scheduling resource; size both for the workload and host.

## Install the source and workflow environment

```bash
git clone https://github.com/ZooPhy/wings.git
cd wings
```

Use an existing compatible Conda/Mamba installation, or install
[Miniforge](https://github.com/conda-forge/miniforge#install) for the actual operating
system and CPU architecture. Do not overwrite an existing installation or try
to convert an Intel environment into ARM64 by changing `CONDA_SUBDIR`.

For a new workflow environment:

```bash
conda create -n snakemake_env --strict-channel-priority \
  -c conda-forge -c bioconda \
  'snakemake>=9,<10' numpy scipy pyyaml
conda activate snakemake_env
snakemake --version
python -c 'import platform, sys; print(sys.executable); print(platform.machine())'
python -c 'import numpy, scipy, yaml; print("PASS: workflow imports available")'
```

This is an environment-creation example, not an exact dependency lock. Record
the resolved versions for your installation. Keep an already-working environment
until a replacement has been tested.

### Existing environments

If you already have a WINGS environment, activate it and install the
workflow-loading dependencies instead of creating another environment:

```bash
conda activate YOUR_WINGS_ENVIRONMENT
conda install -c conda-forge numpy scipy pyyaml
python -c 'import numpy, scipy, yaml; print("PASS: workflow imports available")'
```

Replace `YOUR_WINGS_ENVIRONMENT` with the environment used by your launcher or
SLURM script, for example `wings_snakemake_new`. Update it when no jobs are using
that environment. Both the environment's filesystem and the Conda package-cache
filesystem need sufficient space; changing `CONDA_PKGS_DIRS` does not move an
existing environment.

WINGS imports NumPy, SciPy, and PyYAML while loading the workflow. These packages
must be installed in the environment running Snakemake, even when using
`--sdm conda`. Rule-specific environments cannot supply imports needed before
the workflow has been loaded. A `ModuleNotFoundError` at this stage should be
resolved in the launcher environment, not an unrelated `base` environment.
Verify the imports above before submitting a batch job. This check verifies
these imports only; it does not validate every workflow dependency or analysis.

### Linux ARM64 reporting

On Linux ARM64, install the repository's pinned Quarto distribution:

```bash
bash scripts/install_quarto_linux_arm64.sh software
```

The installer verifies its download. The workflow supports the repo-local
`software/quarto-1.9.38/bin/quarto` installation; see the installer and Snakefile
when changing versions. macOS uses its configured reporting environment.

## Create configuration and provide inputs

Start from [config/config.example.yaml](../config/config.example.yaml). Copy it
only when you do not already have a local configuration:

```bash
test -f config.yaml || cp config/config.example.yaml config.yaml
```

Edit paths and analysis choices before running. Do not replace an existing
configuration with the example during an update. Common settings include:

```yaml
reads_dir: data
reads_pattern: "{sample}.fastq.gz"
results_dir: results
metadata_file: metadata.tsv
metadata_require_all_samples: true
blast_db: resources/flu_db/fluA_db
run_nanoplot: true
run_genoflu: true
run_summary: true
run_surveillance_explorer: true
```

These are selected settings to edit in the complete example, not a replacement
configuration. Use [metadata.example.tsv](../metadata.example.tsv); sample IDs
must match the reads. Retain missing locations as missing rather than guessing
coordinates. See [metadata preparation](metadata-wizard.md).

On a Linux cluster, choose `irma_runtime: apptainer` or `singularity` to match
the installed runtime. On a Mac, use the configured Docker route. The workflow
invokes these runtimes directly for IRMA; `--sdm conda` enables its Conda jobs.

## Install references and VADR models

Build the influenza BLAST database from the repository root:

```bash
bash scripts/build_blast_db.sh
```

The setup script records database provenance. `blast_db` is the database prefix
such as `resources/flu_db/fluA_db`, not a directory or an individual `.nin` file.
Preserve existing databases and provenance when planning a reference update.

VADR software and influenza models are separate installations. When VADR is
enabled, install the pinned models:

```bash
bash scripts/install_vadr_models.sh
```

The installer verifies the pinned archive and installs the influenza `1.7-1`
model set under `resources/vadr-models/vadr-models-flu-1.7-1`. The workflow
requires the model's `flu.minfo`, `flu.cm`, and `flu.fa` files.

For a working local VADR installation or cluster module:

```yaml
run_vadr: true
vadr_runtime: local
vadr_mkey: flu
vadr_model_dir: resources/vadr-models/vadr-models-flu-1.7-1
vadr_forcegene: true
```

Check `command -v v-annotate.pl` and `v-annotate.pl -h` after activating the
environment that launches Snakemake. Loading a module alone does not prove
that its Perl dependencies remain usable after Conda activation.

The evaluated ARM64 cluster installation used native VADR `1.7.3` with these
models. This does not establish compatibility of every cluster module or of an
AMD64 container on ARM64. If no compatible VADR is installed, explicitly use
`run_vadr: false` and record that VADR validation was omitted. The optional check
below makes that choice visible in the job log. An installed but broken VADR
should fail visibly rather than silently disabling validation.

## Dry run and execute

From the checkout, with the intended environment active:

```bash
snakemake --configfile config.yaml --sdm conda --cores 4 \
  --dry-run --printshellcmds
```

IRMA is a checkpoint. Some segment-specific inputs can remain `<TBD>` until
normalization identifies the available segments. A dry run does not test actual
scientific execution, downloads, or all jobs introduced by checkpoints.

To prepare currently discoverable Conda environments:

```bash
snakemake --configfile config.yaml --sdm conda --cores 4 \
  --conda-create-envs-only
```

An example execution command for a sufficiently provisioned host is:

```bash
snakemake --configfile config.yaml --sdm conda --cores 4 \
  --resources mem_mb=90000 kaleido=1 \
  --printshellcmds --rerun-incomplete
```

Adjust cores and memory to the allocation. Resume with the same configuration
and working directory; preserve `results/`, `.snakemake/`, and resource caches.
Updated code, parameters, or dependencies can cause completed jobs to rerun.

## Linux ARM64 / SLURM example

Save the following as a batch script on the HPC. Replace the partition,
environment name, project path, and module names with site-specific values.
Add account/QoS directives if required. The example runs Snakemake and its jobs
within one allocated node; it is not a separate SLURM job submission per rule.

```bash
#!/bin/bash
#SBATCH --job-name=wings
#SBATCH --partition=arm
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=200G
#SBATCH --time=7-00:00:00
#SBATCH --output=wings.out
#SBATCH --error=wings.err
#SBATCH --export=NONE

set -euo pipefail
module purge
# Load the site's Apptainer/Singularity module here if it is not on PATH.
if module load vadr/1.7.3; then
    echo "Loaded VADR module"
else
    echo "WARNING: VADR module unavailable; checking local installation." >&2
fi
unset PYTHONPATH
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate snakemake_env
export SLURM_EXPORT_ENV=ALL

# EDIT: existing project directory containing the wings checkout.
WINGS_PROJECT=/path/to/project
cd "$WINGS_PROJECT/wings"
export CONDA_PKGS_DIRS="$WINGS_PROJECT/conda_pkgs"
export XDG_CACHE_HOME="$WINGS_PROJECT/cache"
export TMPDIR="$WINGS_PROJECT/tmp"
export TEMP="$TMPDIR" TMP="$TMPDIR"
mkdir -p "$CONDA_PKGS_DIRS" "$XDG_CACHE_HOME" "$TMPDIR"
export APPTAINER_BINDPATH="${APPTAINER_BINDPATH:+${APPTAINER_BINDPATH},}${TMPDIR}:${TMPDIR}"

RUN_VADR=false
if command -v v-annotate.pl >/dev/null 2>&1; then
    # Failure here is fatal; do not silently skip a broken installation.
    v-annotate.pl -h >/dev/null
    RUN_VADR=true
else
    echo "WARNING: run_vadr=false; VADR annotation/validation will NOT run." >&2
fi
echo "run_vadr=$RUN_VADR, vadr_runtime=local"

snakemake --configfile config.yaml \
  --config "run_vadr=$RUN_VADR" vadr_runtime=local \
  --sdm conda --printshellcmds --cores "$SLURM_CPUS_PER_TASK" \
  --resources mem_mb=200000 kaleido=1 \
  --conda-cleanup-pkgs cache --latency-wait 300 --rerun-incomplete
```

Install/configure the model files before submission if VADR will be enabled.
WINGS checks their availability when it runs VADR. The optional-module branch
does not install VADR or switch to a container. If validation is mandatory for
your analysis, replace the missing-executable warning with an error and `exit 1`.

Submit with `sbatch your-script.sh` on the HPC. Ollama is optional and requires
a separately provisioned model/server on an appropriate compute node; see
[local model interpretation](local-llm-interpretation.md). Do not assume a
login-node service will be reachable from a batch job.

## Browser runner from a native checkout

For browser submission instead of a direct Snakemake command:

```bash
bash scripts/start_wings.sh /path/to/conda /path/to/conda/envs/snakemake_env \
  --runs-dir /path/to/wings-runs --conda-pkgs-dir /path/to/conda-cache
```

Use actual writable paths. See [native runner setup](native-runner.md) for
architecture checks and storage settings. An existing browser run uses its
saved execution configuration; editing the repository's `config.yaml` may not
change that job. Supply `NCBI_EMAIL` and, when needed, `EBIRDST_ACCESS_KEY` in the
environment that starts the native service.

## Windows / WSL2 status

Follow the dedicated [Windows/WSL2 setup guide](windows-wsl2.md). It separates
Windows PowerShell setup from Ubuntu commands and covers Linux prerequisites,
Miniforge, Docker integration and conditional socket-permission troubleshooting,
file paths, real metadata, resource verification, and sample-discovery checks.

As of 2026-11-24, a tester reported successful setup, a dry run, Conda-environment
creation, and full-analysis launch. Analysis completion and report review remain
pending. This is evidence of setup progress, not full end-to-end validation.
Record the exact WINGS revision, operating-system and tool versions, inputs,
configuration, final logs, and report checks before making a stronger claim.
Windows on ARM compatibility is not established by the available feedback.

## Results and updates

The default portable output is `results/wings_report_bundle.wings`. Transfer it
to the report viewer; retain the HPC workspace for full outputs and provenance.
Opening it in a newer app does not rebuild its embedded reports.

Before updating a source checkout, finish active jobs, inspect `git status`,
preserve local configuration, and record the current commit. Use
`git pull --ff-only origin main` only on the intended `main` checkout. A matching
Git branch does not establish that a downloaded report bundle was generated
from that revision. See [report maintenance](report-reference.md#report-and-bundle-maintenance).
