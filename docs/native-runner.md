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
