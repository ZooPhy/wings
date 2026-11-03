#!/bin/bash
set -euo pipefail
# Supply the Conda installation and the full runner environment prefix.
if [ "$#" -lt 2 ]; then
  echo "Usage: bash scripts/start_wings.sh CONDA_ROOT RUNNER_PREFIX [runner options]" >&2
  exit 2
fi
wings_conda_root="$1"
wings_runner_prefix="$2"
shift 2
export PATH="$wings_runner_prefix/bin:$wings_conda_root/condabin:$wings_conda_root/bin:$PATH"
export CONDA_EXE="$wings_conda_root/bin/conda"
export CONDA_PYTHON_EXE="$wings_conda_root/bin/python"
export CONDA_PREFIX="$wings_runner_prefix"
export CONDA_DEFAULT_ENV="$wings_runner_prefix"
wings_script_dir="$(cd "$(dirname "$0")" && pwd)"
exec "$wings_runner_prefix/bin/python" "$wings_script_dir/wings_local_runner.py" "$@"
