"""Runs inside the container, never in the user's Python environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import tempfile

from proxy import make_server


def verify(repo):
    manifest = json.loads((repo / 'desktop-source-manifest.json').read_text())
    for name, expected in manifest['files'].items():
        path = repo / name
        if not path.resolve().is_relative_to(repo.resolve()):
            raise RuntimeError('Source manifest escapes its installation: ' + name)
        if path.is_symlink() or not path.is_file() or path.resolve().parent != (repo / name).absolute().parent:
            raise RuntimeError('Missing or redirected source: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Source checksum mismatch: ' + name)
    required = ['Snakefile', 'rules/phylodynamics.smk', 'scripts/phylodynamic_selection.py',
                'scripts/phylodynamic_bayesian.py', 'config/phylodynamics.example.yaml',
                'scripts/phylodynamics_job_options.py', 'scripts/phylodynamics_submission.py']
    for name in required:
        if name not in manifest['files']:
            raise RuntimeError('Incomplete desktop source: ' + name)


def run(command, repo):
    subprocess.run(command, cwd=repo, check=True)



def check_case_sensitive_directory(path):
    """Probe the mounted filesystem itself; a space-free prefix is insufficient."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='.wings-case-check-', dir=path) as temp:
            lower, upper = Path(temp) / 'probea', Path(temp) / 'probeA'
            lower.write_bytes(b'lower')
            try:
                with upper.open('xb') as handle:
                    handle.write(b'upper')
            except FileExistsError:
                raise RuntimeError(f'Conda storage is case-insensitive: {path}. '
                                   'Reopen the updated WINGS app using its managed Docker volumes.') from None
            if lower.read_bytes() != b'lower' or upper.read_bytes() != b'upper':
                raise RuntimeError(f'Conda storage does not preserve filename case: {path}')
    except OSError as exc:
        raise RuntimeError(f'Cannot write to Conda storage {path}: {exc}') from exc


def prepare_conda_storage():
    prefix = os.environ.get('WINGS_DESKTOP_CONDA_PREFIX', '/opt/wings-conda-envs')
    cache = os.environ.get('WINGS_DESKTOP_CONDA_PKGS_DIR', '/opt/wings-conda-pkgs')
    for path in (prefix, cache):
        check_case_sensitive_directory(path)
    os.environ['WINGS_DESKTOP_CONDA_PREFIX'] = prefix
    os.environ['WINGS_DESKTOP_CONDA_PKGS_DIR'] = cache
    os.environ['CONDA_PKGS_DIRS'] = cache
    print('Conda storage verified: case-sensitive package cache and environments', flush=True)
    return cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['verify', 'docker-check', 'prepare', 'serve', 'smoke'])
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    repo, workspace = args.repo.resolve(), args.workspace.resolve()
    if not repo.is_relative_to(workspace):
        raise ValueError('The source must be inside the mounted workspace')
    verify(repo)
    os.chdir(repo)
    os.environ['HOME'] = str(workspace / 'runtime-home')
    Path(os.environ['HOME']).mkdir(exist_ok=True)
    cache = prepare_conda_storage()
    (workspace / 'runs').mkdir(parents=True, exist_ok=True)
    if args.action == 'verify':
        print('Source integrity verified')
        return
    if args.action == 'docker-check':
        # Test subprocess execution from the same Python used by the runner.
        # A CLI crash must stop setup before the browser offers Resume.
        subprocess.run(['docker', 'version'], cwd=repo, check=True, timeout=30)
        subprocess.run(['docker', 'info', '--format', '{{.OSType}}/{{.Architecture}}'],
                       cwd=repo, check=True, timeout=30)
        return
    if args.action == 'smoke':
        run([sys.executable, 'scripts/build_explorer_assets.py', '--check'], repo)
        run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
             '-p', 'test_phylodynamics_submission.py'], repo)
        run([sys.executable, 'tests/check_phylodynamics_backend.py', '--unit'], repo)
        run([sys.executable, 'tests/check_phylodynamics_submission_workflow.py'], repo)
        return
    # These resources are separate from the application and source checksums.
    if args.action == 'prepare':
        db = repo / 'resources' / 'flu_db'
        if not ((db / 'database_manifest.tsv').is_file() and list(db.glob('fluA_db*.nin'))):
            run(['bash', 'scripts/build_blast_db.sh'], repo)
        run(['bash', 'scripts/install_vadr_models.sh'], repo)
        # desktop.sh prepares tool images with the native host Docker CLI.
        # Do not invoke the emulated Docker CLI during resource preparation.
        return
    token = os.environ['WINGS_DESKTOP_TOKEN']
    child_env = os.environ.copy()
    child_env.pop('WINGS_DESKTOP_TOKEN', None)
    child_env['WINGS_DESKTOP_WORKSPACE'] = str(workspace)
    command = [sys.executable, 'scripts/wings_local_runner.py', '--no-browser',
               '--host', '127.0.0.1', '--port', '8765',
               '--runs-dir', str(workspace / 'runs'),
               '--conda-pkgs-dir', cache]
    child = subprocess.Popen(command, env=child_env)
    server = make_server(token)

    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    def watch():
        child.wait()
        server.shutdown()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    threading.Thread(target=watch, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
        if child.returncode not in (0, None, -15):
            raise SystemExit(child.returncode)


if __name__ == '__main__':
    main()
