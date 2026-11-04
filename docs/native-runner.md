# Native runner setup

On Apple Silicon, use native ARM64 Python and Conda. Intel Python under Rosetta
cannot install recent official macOS PyTorch wheels. Keep existing installations
until the new setup has been verified; do not change their architecture in place.

For the separate Miniforge setup used on the M1 computer, run from the repository:

```bash
export CONDA_SUBDIR=osx-arm64
export CONDA_SOLVER=libmamba
bash scripts/start_wings.sh "$HOME/miniforge3-arm64" "$HOME/miniforge3-arm64/envs/wings-runner"
```

For other installations, provide their Conda root and runner environment prefix.
Do not copy the ARM64 override onto Intel machines. The startup script explicitly
prioritizes the chosen environment and Conda installation without editing shell
startup files. The runner validates Python, Snakemake, Conda root, and target
platform before launching a workflow. Errors are shown through the existing
portal error response; the portal itself remains available.

Workflow environments use `.snakemake/conda-platforms/<system>-<architecture>`.
The first run after this update creates environments in the new cache. Existing
`.snakemake/conda` caches and run results are preserved. This change applies to
portal-launched runs; direct Snakemake users must choose their own --conda-prefix.

These checks do not guarantee availability of every dependency or detect every
possible solver/plugin incompatibility. Do not disable dependency checks or force
an incompatible PyTorch version to work around an architecture mismatch.

## Explicit run storage and Conda package cache

The launcher accepts two independent directory options. On HPC, launch inside
your compute allocation with writable project storage:

```bash
bash scripts/start_wings.sh "$HOME/miniforge3" "$HOME/miniforge3/envs/wings_snakemake_new" \
  --runs-dir /path/to/project/wings-runs \
  --conda-pkgs-dir /path/to/project/conda_pkgs
```

Replace both project paths and the Conda installation/environment paths for your
system. The same options work on Apple Silicon Macs, Intel Macs and Linux/WSL;
Windows users run this shell launcher inside WSL. Paths containing spaces must
be quoted. On a Mac, omitting both options preserves the existing defaults.

| Setting | Command-line option | Behavior without the option |
| --- | --- | --- |
| Uploaded inputs, run state and results | `--runs-dir PATH` | Uses `WINGS_RUNS_DIR`, otherwise `~/.wings/runs` |
| Conda downloaded packages and metadata | `--conda-pkgs-dir PATH` | Preserves `CONDA_PKGS_DIRS` and Conda's configured cache locations |

An explicit option takes precedence over its environment variable. The runner
expands `~`, resolves relative paths against the launch directory, creates missing
directories and checks that it can write before opening the portal. It prints
the run directory and the cache override, or notes that Conda's configuration
controls the cache. The cache override is inherited by Snakemake and Conda.

Moving run storage alone does not relocate Conda's package cache. An error under
`~/miniforge3/.../pkgs/*.partial` can therefore still mean home storage is full.
Workflow environment prefixes remain separate, under the platform-specific path
described above. These options do not relocate temporary files or other tools'
caches, move existing runs, delete files or change global Conda configuration.

The write check cannot guarantee sufficient space for a complete run; check
filesystem capacity, quota and inodes on the selected storage. Apply directory
changes after active jobs finish, restart the runner, and select the same run
directory to resume existing runs. Runs in a different directory will not appear
until that directory is selected again.

### Choose storage in the browser

Under **Run details → Storage locations**, enter the run storage directory and,
optionally, the Conda package cache directory. These are paths on the machine
running WINGS (the compute node for an HPC desktop), not the computer viewing a
forwarded page. Use an absolute path or `~/...`; Windows/WSL users enter Linux
paths. There is no browser folder picker because the runner owns these paths.

Click **Validate and apply locations** before uploading files. The runner creates
missing directories and tests writing to them. Preflight shows the applied paths
and prevents starting with unapplied edits. A failed check leaves the previous
settings active. A path's filesystem free space does not account for every quota
or predict the space needed for a full analysis.

Browser settings apply to new runs in the current server session. The saved-run
list shows the selected directory. Already-created runs retain their directory
and saved package-cache setting, including on resume. Changing defaults while
another run is uploading or running does not redirect that run. Copied run IDs
in two directories are rejected rather than resolving to the wrong files.

Restarting the runner restores its command-line/environment defaults. Use the
launch options above for a repeatable startup configuration. To reopen an older
run after restarting, select the directory that contains it. Browser changes
never move existing files or edit your global Conda settings. This feature does
not change the separate Ollama connection or architecture checks.
