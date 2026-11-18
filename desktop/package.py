#!/usr/bin/env python3
"""Developer build tool. End users do not need Python to launch the app."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parent
EXCLUDED = {'__pycache__', '.git', '.snakemake', '.pytest_cache', 'node_modules', 'desktop', 'dist', 'build'}


def source_files(source):
    tracked = None
    if (source / '.git').exists():
        tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=source).decode().split('\0'))
    for path in sorted(source.rglob('*')):
        rel = path.relative_to(source)
        if rel.parts[0] == 'demo':
            continue  # The large public demo download is not part of the runner.
        if tracked is not None and rel.as_posix() not in tracked:
            continue  # Excludes local reads, result folders and downloaded caches.
        if any(p in EXCLUDED for p in rel.parts) or path.suffix == '.pyc':
            continue
        if rel.as_posix() == 'config.yaml':
            continue  # Never package a developer's personal configuration.
        if path.is_symlink():
            raise ValueError('Source symlinks are not distributable: ' + str(rel))
        if path.is_file() and rel.name != 'desktop-source-manifest.json':
            yield rel.as_posix(), path.read_bytes()


def bundle(source, destination):
    app = destination / 'WINGS.app'
    resources = app / 'Contents' / 'Resources'
    binary = app / 'Contents' / 'MacOS'
    resources.mkdir(parents=True, exist_ok=True)
    binary.mkdir(parents=True, exist_ok=True)
    files = dict(source_files(source))
    forbidden = [name for name in files if name.startswith(('results/', 'data/', '.env', 'demo/'))]
    if forbidden:
        raise ValueError('Unexpected private/runtime data: ' + repr(forbidden[:5]))
    if 'README.md' not in files:
        raise ValueError('Missing required source README.md; build from the official repository checkout.')
    (resources / 'README.md').write_bytes(files['README.md'])
    files['config.yaml'] = b'# WINGS Desktop defaults, generated from the example.\n' + files['config/config.example.yaml']
    manifest = {'format': 1, 'version': '0.1.13-preview', 'files': {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files['desktop-source-manifest.json'] = json.dumps(manifest, sort_keys=True, indent=2).encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as tar:
            for name, data in sorted(files.items()):
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                entry.mode = 0o755 if name.endswith('.sh') else 0o644
                entry.mtime = 0
                tar.addfile(entry, io.BytesIO(data))
    archive = buffer.getvalue()
    (resources / 'source.tar.gz').write_bytes(archive)
    (resources / 'source.sha256').write_text(hashlib.sha256(archive).hexdigest() + '\n')
    for name in ('desktop.sh', 'WINGS.applescript', 'setup-session.sh', 'setup-progress.sh', 'setup-progress.html', 'setup-progress.js', 'ollama-settings.sh'):
        shutil.copyfile(ROOT / name, resources / name)
    shutil.copyfile(source / 'scripts/wings_ollama.py', resources / 'wings_ollama.py')
    shutil.copyfile(ROOT / 'wings_logo.jpg', resources / 'wings_logo.jpg')
    runtime = resources / 'runtime'
    runtime.mkdir(exist_ok=True)
    digest = hashlib.sha256()
    for p in sorted((ROOT / 'runtime').iterdir()):
        if not p.is_file():
            continue
        data = p.read_bytes()
        digest.update(p.name.encode() + b'\0' + data)
        (runtime / p.name).write_bytes(data)
    (resources / 'runtime.sha256').write_text(digest.hexdigest() + '\n')
    shim = binary / 'WINGS'
    shim.write_text('''#!/bin/bash
set -euo pipefail
export WINGS_APP_RESOURCES="$(cd "$(dirname "$0")/../Resources" && pwd -P)"
exec /usr/bin/osascript "$WINGS_APP_RESOURCES/WINGS.applescript"
''')
    shim.chmod(0o755)
    (resources / 'desktop.sh').chmod(0o755)
    info = {'CFBundleName': 'WINGS', 'CFBundleDisplayName': 'WINGS',
            'CFBundleIdentifier': 'org.zoophy.wings.desktop.preview',
            'CFBundleVersion': '15', 'CFBundleShortVersionString': '0.1.14',
            'CFBundlePackageType': 'APPL', 'CFBundleExecutable': 'WINGS',
            'LSMinimumSystemVersion': '13.0', 'NSHighResolutionCapable': True,
            'NSAppleEventsUsageDescription': 'WINGS opens your browser and local workspace.',
            'CFBundleIconFile': 'WINGS.icns'}
    (app / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps(info))
    if (ROOT / 'WINGS.icns').exists():
        shutil.copyfile(ROOT / 'WINGS.icns', resources / 'WINGS.icns')
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    app = bundle(args.source.resolve(), args.output.resolve())
    print(app)


if __name__ == '__main__':
    main()
