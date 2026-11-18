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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['verify', 'prepare', 'serve', 'smoke'])
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
    os.environ['CONDA_PKGS_DIRS'] = str(workspace / 'cache' / 'conda-pkgs')
    for path in [workspace / 'runs', workspace / 'cache' / 'conda-pkgs']:
        path.mkdir(parents=True, exist_ok=True)
    if args.action == 'verify':
        print('Source integrity verified')
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
        for image in ('ghcr.io/cdcgov/irma:v1.3.5', 'staphb/vadr:1.7'):
            present = subprocess.run(['docker', 'image', 'inspect', image],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            if not present:
                run(['docker', 'pull', '--platform', 'linux/amd64', image], repo)
        return
    token = os.environ['WINGS_DESKTOP_TOKEN']
    child_env = os.environ.copy()
    child_env.pop('WINGS_DESKTOP_TOKEN', None)
    child_env['WINGS_DESKTOP_WORKSPACE'] = str(workspace)
    command = [sys.executable, 'scripts/wings_local_runner.py', '--no-browser',
               '--host', '127.0.0.1', '--port', '8765',
               '--runs-dir', str(workspace / 'runs'),
               '--conda-pkgs-dir', str(workspace / 'cache' / 'conda-pkgs')]
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
