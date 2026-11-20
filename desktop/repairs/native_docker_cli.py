#!/usr/bin/env python3
"""Guarded repair inside an existing Apple Silicon WINGS controller.

The shell helper supplies an ARM64 CLI from the pinned official Docker image.
No workflow, run, cache, Docker setting, or scientific environment is changed.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile


def verify_elf(candidate):
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError('Candidate must be a regular file')
    with candidate.open('rb') as handle:
        header = handle.read(20)
    if (len(header) < 20 or header[:6] != b'\x7fELF\x02\x01'
            or struct.unpack('<H', header[18:20])[0] != 183):
        raise ValueError('Candidate is not a little-endian Linux ARM64 ELF executable')


def probe(candidate):
    checks = [
        (['version', '--format', '{{.Client.Os}}/{{.Client.Arch}} {{.Server.Os}}/{{.Server.Arch}}'],
         {'linux/arm64 linux/arm64'}),
        (['info', '--format', '{{.OSType}}/{{.Architecture}}'],
         {'linux/arm64', 'linux/aarch64'}),
    ]
    for args, expected in checks:
        result = subprocess.run([str(candidate), *args], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, timeout=30)
        if result.returncode or result.stdout.strip() not in expected:
            raise RuntimeError('Docker check failed: ' + ' '.join(args) + '\n'
                               + result.stdout[:6000] + result.stderr[:6000])
        print('PASS:', result.stdout.strip(), flush=True)


def replace_atomically(source, target):
    descriptor, name = tempfile.mkstemp(prefix='.wings-docker-', dir=target.parent)
    os.close(descriptor)
    pending = Path(name)
    try:
        shutil.copy2(source, pending)
        pending.chmod(0o755)
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


def install(candidate, target, backup_root, *, check=probe):
    verify_elf(candidate)
    if target.is_symlink() or not target.is_file():
        raise ValueError('Installed Docker CLI is not a regular file; no changes made')
    with candidate.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    print('Candidate SHA256:', digest, flush=True)
    check(candidate)
    print('PASS: candidate works from the controller Python process.', flush=True)
    backup = Path(tempfile.mkdtemp(prefix='docker-cli-', dir=backup_root)) / 'docker.original'
    shutil.copy2(target, backup)
    print('Backup inside this container:', backup, flush=True)
    original_mode = stat.S_IMODE(target.stat().st_mode)
    try:
        replace_atomically(candidate, target)
        check(target)
    except BaseException:
        replace_atomically(backup, target)
        target.chmod(original_mode)
        print('Restored the original Docker CLI after failed verification.', flush=True)
        raise
    print('PASS: installed Docker CLI communicates with the engine.', flush=True)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.environ.get('DOCKER_DEFAULT_PLATFORM') != 'linux/amd64':
        raise SystemExit('Expected the WINGS linux/amd64 analysis platform; no changes made')
    if os.environ.get('DOCKER_HOST') != 'unix:///var/run/docker.sock':
        raise SystemExit('Expected the WINGS local Docker socket; no changes made')
    verify_elf(args.candidate)
    if not args.apply:
        probe(args.candidate)
        print('PASS: diagnostic only; installed CLI unchanged.')
        return
    install(args.candidate, Path('/usr/local/bin/docker'), Path('/opt/wings-desktop'))
    print('No analyses were started. Return to WINGS and click Resume once.')
    print('This live repair lasts for this container. Rebuild the app with the permanent patch.')


if __name__ == '__main__':
    main()
