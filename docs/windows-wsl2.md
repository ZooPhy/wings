# Windows setup with Ubuntu on WSL2

[Command-line guide](command-line-guide.md) · [README](../README.md) · [FAQ](../faq.md)

**Install WSL2 and Ubuntu first. Run WINGS setup and analysis inside the Ubuntu
terminal.** Windows Command Prompt, a Windows Conda prompt, and native Windows
Python are not the execution environment for this workflow. This is the Linux
command-line route through WSL2; it is not a Windows build of the macOS WINGS app.

## Validation status

As of 2026-11-24, one tester reported successful Ubuntu/WSL2 setup, BLAST and
VADR-model installation, a successful Snakemake dry run, creation of the Conda
environments, and initiation of the full analysis. The analysis was still running
when feedback was received. Completed analysis, report contents, and reproducibility
have not yet been confirmed for that test. Its 40-job dry run is specific to its
dataset/configuration, not an expected job count for every WINGS run.

The examples below target Linux `x86_64` within WSL2. The tester's exact hardware
and software versions still need to be recorded. Windows on ARM is not established
by this report; check architecture before choosing installers and container images.

## 1. Install Ubuntu on WSL2 — Windows PowerShell

Open **PowerShell as Administrator** on Windows and run:

```powershell
wsl --install -d Ubuntu
```

Restart Windows if requested. Open **Ubuntu** from the Start menu and create its
Linux user account. In Windows PowerShell, check the distribution and WSL version:

```powershell
wsl --list --verbose
wsl --version
```

Ubuntu must show **VERSION 2**. If an existing Ubuntu installation uses version 1,
follow [Microsoft's conversion instructions](https://learn.microsoft.com/en-us/windows/wsl/install#upgrade-version-from-wsl-1-to-wsl-2).
Use the exact distribution name shown by the list command. Check current
[Docker Desktop Windows requirements](https://docs.docker.com/desktop/setup/install/windows-install/)
separately; WSL installation alone does not establish Docker compatibility.

**All `bash` blocks below run in Ubuntu**, except where explicitly stated otherwise.
Do not paste the PowerShell commands into Conda or the WINGS configuration file.

## 2. Install Linux system prerequisites — Ubuntu

```bash
sudo apt update &&
sudo apt install -y ca-certificates curl git unzip tar gzip bzip2 coreutils
```

Check the commands before downloading reference resources:

```bash
for tool in bash curl git unzip tar gzip sha256sum; do
  command -v "$tool" || break
done
uname -s
uname -m
```

Expect Linux and, for these container examples, `x86_64`. A minimal Ubuntu
installation may lack `unzip`, which the BLAST setup script needs after downloading
the archive. If it is missing, install it here and rerun the setup step. Dependency
installation is explicit; an analysis script should not silently invoke `sudo apt`.

## 3. Connect Docker Desktop to Ubuntu

Install and start **Docker Desktop for Windows**. Select its **WSL 2 based engine**
and Linux containers, then enable the intended Ubuntu distribution under
**Settings → Resources → WSL Integration** and apply the changes. Docker working
from Windows does not demonstrate that it is available inside Ubuntu.

In Ubuntu, run:

```bash
command -v docker
docker info
```

Both must succeed under your ordinary Ubuntu user. If `docker` is not found,
recheck integration for the exact distribution, then reopen Ubuntu. Do not install
a second Docker Engine inside WSL as a workaround for disabled Desktop integration.
See [Docker's WSL2 instructions](https://docs.docker.com/desktop/features/wsl/).

### If Docker reports socket permission denied

Inspect the endpoint and permissions before changing groups:

```bash
docker context show
printf 'DOCKER_HOST=%s\n' "${DOCKER_HOST:-<not set>}"
ls -l /var/run/docker.sock
id -nG
getent group docker
```

The tester resolved a Unix-socket permission error by joining the Linux `docker`
group and starting a new session. Apply this only when the intended socket is
group-accessible to `docker`, that group exists, and your current session lacks
membership. Under those conditions:

```bash
sudo usermod -aG docker "$(id -un)"
```

Sign out of the Ubuntu session and reopen it, then repeat `id -nG` and `docker info`.
If the session does not pick up membership, `newgrp docker` starts a subshell with
the group active; reactivate the intended Conda environment in that shell.
Docker-group access is privileged access to the daemon. The Linux `docker` group
is different from Windows' `docker-users` group; do not substitute one for the other.

Do not change the socket to world-writable or run the whole workflow with `sudo`.
If the socket/group or Docker context differs, troubleshoot Desktop integration
instead of applying the group command blindly. See
[Docker's Linux permissions guidance](https://docs.docker.com/engine/install/linux-postinstall/).

## 4. Install Linux Miniforge and the workflow environment

Windows Conda cannot supply Linux packages to WSL. A compatible Conda installation
already inside Ubuntu can be reused. Otherwise install the **Linux** Miniforge
distribution in Ubuntu's filesystem. First check `uname -m`; the following
installer is for `x86_64` only:

```bash
mkdir -p "$HOME/wings-install"
cd "$HOME/wings-install"
curl -fL --retry 3 -o Miniforge3-Linux-x86_64.sh \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
```

Compare its SHA-256 with the matching asset's official checksum on the
[Miniforge release page](https://github.com/conda-forge/miniforge/releases), then
install it at a new path (normally `~/miniforge3`). Do not install over an existing
Conda directory:

```bash
sha256sum Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh
source "$HOME/miniforge3/etc/profile.d/conda.sh"
```

If you selected another prefix, substitute it in the `source` command. For a
new workflow environment:

```bash
conda create -n snakemake_env --strict-channel-priority \
  -c conda-forge -c bioconda \
  'snakemake>=9,<10' numpy scipy pyyaml
conda activate snakemake_env
snakemake --version
python -c 'import platform, sys; print(sys.executable); print(platform.system(), platform.machine()); import numpy, scipy, yaml; print("PASS: workflow imports available")'
```

Expect a Linux interpreter inside the intended Conda environment, rather than a
Windows executable under `/mnt/c`. NumPy, SciPy and PyYAML are needed by the
environment loading the workflow, before rule-specific environments are activated.
For an existing environment, use the
[existing-environment instructions](command-line-guide.md#existing-environments).
Do not replace environments used by an active analysis.

## 5. Keep the checkout and analysis in Linux storage

In Ubuntu:

```bash
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone https://github.com/ZooPhy/wings.git
cd wings
git rev-parse HEAD
mkdir -p data
test -f config.yaml || cp config/config.example.yaml config.yaml
```

If the repository already exists, use that checkout and inspect `git status`
instead of cloning over it. Preserve existing configuration and real metadata.
Do not copy Windows-created Conda environments or `.snakemake` environments into
Linux and expect them to work.

| Windows location | Location inside Ubuntu/WSL |
| --- | --- |
| `C:\Users\Alice\Downloads\sample01.fastq.gz` | `/mnt/c/Users/Alice/Downloads/sample01.fastq.gz` |
| Linux project `~/projects/wings` | `/home/<Linux-user>/projects/wings` |

Windows and Linux usernames can differ. Replace the username and filename below
with the real Windows input path; quotes preserve spaces:

```bash
cp -i "/mnt/c/Users/YOUR_WINDOWS_USERNAME/Downloads/sample01.fastq.gz" data/
gzip -t data/sample01.fastq.gz
ls -lh data/sample01.fastq.gz
df -h .
```

`cp -i` asks before replacing an existing file. `gzip -t` checks compressed-file
integrity, not FASTQ record validity. Repeat for the intended samples and confirm
sufficient disk space for reads, environments, container images, and intermediates.
Prefer Linux storage for the workflow and working data, as recommended in
[Microsoft's WSL filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/setup/environment).

## 6. Configure runtimes, references and models

Edit the following entries in the complete `config.yaml`; this is not a complete
replacement configuration:

```yaml
reads_dir: data
reads_pattern: "{sample}.fastq.gz"
results_dir: results
metadata_file: metadata.tsv
metadata_require_all_samples: true
irma_runtime: docker
blast_db: resources/flu_db/fluA_db
run_vadr: true
vadr_runtime: docker
vadr_image: "docker://staphb/vadr:1.7"
vadr_mkey: flu
vadr_model_dir: resources/vadr-models/vadr-models-flu-1.7-1
run_summary: true
run_surveillance_explorer: true
```

Use the actual reads extension and location. Choose optional modules deliberately;
copying an example does not preserve previous run settings. With Docker VADR,
`v-annotate.pl` need not be installed on the Ubuntu host.

Before resource setup, confirm `docker info` and `command -v unzip` succeed.
From the repository root:

```bash
bash scripts/build_blast_db.sh
bash scripts/install_vadr_models.sh
docker pull staphb/vadr:1.7
docker run --rm staphb/vadr:1.7 v-annotate.pl -h
```

The resource scripts verify their pinned archive checksums. Wait for the BLAST
script's successful database-verification message and retain
`resources/flu_db/database_manifest.tsv`. Inspect the recorded resource provenance:

```bash
cat resources/flu_db/database_manifest.tsv
```

The `blast_db` configuration is a prefix, not a directory or individual index
file. Check the model files without running an annotation:

```bash
for suffix in minfo cm fa; do
  model="resources/vadr-models/vadr-models-flu-1.7-1/flu.$suffix"
  if [[ -s "$model" ]]; then
    printf 'PASS: %s\n' "$model"
  else
    printf 'MISSING OR EMPTY: %s\n' "$model" >&2
  fi
done
```

Resolve any missing file before continuing. Image download and `-h` checks do not
prove every annotation dependency works. The actual workflow provides that test.
Do not install the Linux ARM64 Quarto build on x86-64 WSL; use the workflow's
architecture-appropriate reporting environment.

## 7. Create real sample metadata

Use tab-separated columns including `sample_id`, `host`, `collection_date`, and
`country`; add `specimen_type`, `state`, `latitude`, and `longitude` when known.
For `{sample}.fastq.gz`, the ID of `sample01.fastq.gz` is `sample01`. It must match
exactly. Collection dates describe specimen collection, not download, submission,
or analysis dates. Do not infer biological metadata from a filename or accession.

The following creates a template with one row per discovered sample and **blank
biological fields**. It refuses to overwrite an existing `metadata.tsv` and fails
if no reads match. Run it only when creating a new metadata file:

```bash
python - <<'PY'
import csv
from pathlib import Path
import yaml
from snakemake.io import glob_wildcards

with open("config.yaml") as handle:
    config = yaml.safe_load(handle)
pattern = str(Path(config["reads_dir"]) / config["reads_pattern"])
samples = sorted(set(glob_wildcards(pattern).sample))
if not samples:
    raise SystemExit("No matching FASTQ files; correct reads_dir/reads_pattern first.")
fields = ["sample_id", "host", "collection_date", "country", "specimen_type",
          "state", "latitude", "longitude"]
with open("metadata.tsv", "x", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fields, delimiter="\t")
    writer.writeheader()
    writer.writerows({"sample_id": sample} for sample in samples)
print(f"Created metadata.tsv for {len(samples)} samples. Fill the biological fields before running.")
PY
```

Edit the TSV in a tab-aware editor. An illustrative row, **not real study data**,
would map `sample01.fastq.gz` to sample ID `sample01`, a documented host name,
an ISO collection date such as `YYYY-MM-DD`, and its recorded country. Do not
leave that date placeholder in an analysis file. Keep genuinely unknown values
blank; review which analyses require them rather than inventing replacements.

### Public SRA and BioSample metadata

For public inputs, preserve the relationship between the SRA run accession and
the linked BioSample, along with retrieval date and source records. NCBI's web
pages can return HTML or a reCAPTCHA challenge to automated requests; such a
response is not usable metadata.

Use [NCBI E-utilities](https://www.nlm.nih.gov/dataguide/eutilities/utilities.html)
for supported programmatic retrieval: locate the SRA record with ESearch,
retrieve it with EFetch, and inspect linked BioSample identifiers (using ELink
where supported). Retrieve and review the BioSample attributes. Attribute names,
collection-date precision, and location availability vary. This is metadata
retrieval, not a method for bypassing a web challenge.

Include tool/contact information and follow the
[NCBI usage guidance](https://eutilities.github.io/site/API_Key/usageandkey/).
Retain original values if only partial dates or locations are provided; do not
make them more precise just to satisfy a field. Accessions are not themselves
collection dates, host names, or geographic coordinates.

## 8. Verify sample discovery and metadata before analysis

This read-only check detects missing reads, duplicate IDs, missing metadata rows,
and invalid supplied dates. It also reports blank context fields for review.
Run it from the Linux WINGS checkout with `snakemake_env` active:

```bash
python - <<'PY'
import csv
from collections import Counter
from datetime import date
from pathlib import Path
import yaml
from snakemake.io import glob_wildcards

with open("config.yaml") as handle:
    config = yaml.safe_load(handle)
reads = Path(config["reads_dir"])
samples = sorted(set(glob_wildcards(str(reads / config["reads_pattern"])).sample))
print("Reads directory:", reads.resolve())
print("Matched samples:", len(samples))
if not samples:
    raise SystemExit("STOP: no matching reads. Check the directory and extension.")
for sample in samples:
    path = reads / config["reads_pattern"].format(sample=sample)
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit("STOP: missing or empty FASTQ: " + str(path))
    print(" ", sample)
with open(config["metadata_file"], encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    required = {"sample_id", "host", "collection_date", "country"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit("STOP: missing metadata columns: " + ", ".join(sorted(missing)))
    rows = [row for row in reader if any(str(v or "").strip() for v in row.values())]
ids = [(row.get("sample_id") or "").strip() for row in rows]
duplicates = [key for key, n in Counter(ids).items() if n > 1]
if "" in ids or duplicates:
    raise SystemExit("STOP: blank or duplicate metadata sample IDs: " + repr(duplicates))
absent = set(samples) - set(ids)
if absent:
    raise SystemExit("STOP: reads without metadata: " + ", ".join(sorted(absent)))
extra = set(ids) - set(samples)
if extra:
    print("REVIEW: metadata without matching reads:", ", ".join(sorted(extra)))
for row in rows:
    value = (row.get("collection_date") or "").strip()
    if value:
        date.fromisoformat(value)
    for key in ("host", "collection_date", "country"):
        if not (row.get(key) or "").strip():
            print("REVIEW: blank", key, "for", row["sample_id"])
print("PASS: nonempty reads and metadata IDs checked; review all notices.")
PY
```

This is a preliminary consistency check, not complete scientific validation.
Review the workflow's metadata validation table as well. A dry run alone does
not execute that validator or confirm gzip integrity, sequence contents, model
execution, or downstream inference.

## 9. Dry run, create environments, and execute

First check available resources:

```bash
conda info --envs
command -v python snakemake docker unzip
docker info
free -h
df -h . "$CONDA_PREFIX"
```

Choose resource values that fit the WSL/Docker allocation. The following example
uses four cores and a 16,000 MB Snakemake scheduling budget; it is not a minimum,
universal recommendation, or a change to the WSL/Docker memory limit:

```bash
WINGS_CORES=4
WINGS_MEM_MB=16000
snakemake --configfile config.yaml --sdm conda --cores "$WINGS_CORES" \
  --resources "mem_mb=$WINGS_MEM_MB" kaleido=1 --printshellcmds --dry-run
```

Review the discovered sample count and targets. Checkpoint-dependent jobs can
appear later. If the dry run is correct, prepare discoverable environments:

```bash
snakemake --configfile config.yaml --sdm conda --cores "$WINGS_CORES" \
  --conda-create-envs-only
```

Then launch the workflow in Ubuntu:

```bash
snakemake --configfile config.yaml --sdm conda --cores "$WINGS_CORES" \
  --resources "mem_mb=$WINGS_MEM_MB" kaleido=1 \
  --printshellcmds --rerun-incomplete
```

Keep the environment, Ubuntu session, and Docker service available during the
analysis. Do not shut down WSL or restart Docker while the workflow is active.
Record failures and resume with the same configuration after addressing their
cause; preserve completed results and caches.

## 10. Review results and document the test

Once Snakemake reports successful completion, retain the complete log and inspect
the sample reports, run report, and `results/wings_report_bundle.wings`. Transfer
or open the bundle with the WINGS browser viewer. Windows does not need the macOS
desktop app to view it. A workflow can complete with explicitly unavailable or
failed biological QC results; review the statuses rather than treating completion
as universal validation.

For a reproducible Windows test record, capture:

- Windows version/build, CPU architecture, RAM, and WSL/Docker resource allocation.
- `wsl --version` and `wsl --list --verbose` from Windows PowerShell.
- Ubuntu version (`cat /etc/os-release`), `uname -m`, Docker version and context.
- WINGS commit (`git rev-parse HEAD`) and working-tree changes (`git status --short`).
- Snakemake/Python versions, resolved environment packages (`conda list --explicit`),
  configuration, resource manifests, input accessions/hashes, and metadata provenance.
- Final workflow status/log, runtime, any failed/unavailable modules, and report review.

Review exported environment files and logs for private URLs or credentials before
sharing. These records distinguish successful setup, complete execution, and
scientific/reproducibility assessment. Update the validation statement only when
the corresponding evidence is available.
