#!/usr/bin/env python3
"""Launch installed Porechop_ABI 0.5.1 with intact paths and per-job scratch."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_porechop_accelerated import file_hash, save_json


def counter_wrapper(binary, commands):
    def execute(args, out_file, conf_file, mr, v, print_dest=sys.stderr):
        command = [str(binary), str(args.input), '-v', str(v), '--config', str(conf_file),
                   '-o', str(out_file), '-nt', str(min(args.threads, os.cpu_count() or 1))]
        if mr > 1:
            command.extend(['-mr', str(mr)])
        commands.append(command)
        print('WINGS installed counter: ' + json.dumps(command), file=print_dest, flush=True)
        subprocess.check_call(command)  # Never split a string or use shell=True.
    return execute


def run(args):
    tool = importlib.import_module('porechop_abi.porechop_abi')
    abi = importlib.import_module('porechop_abi.abinitio')
    try:
        version = importlib.metadata.version('Porechop_ABI')
    except importlib.metadata.PackageNotFoundError:
        version = importlib.import_module('porechop_abi.version').__version__
    if version != '0.5.1':
        raise ValueError(f'Path-safe wrapper requires Porechop_ABI 0.5.1; found {version}')
    if not callable(getattr(abi, 'execApproxCounter', None)) or not callable(getattr(tool, 'main', None)):
        raise ValueError('Unsupported Porechop_ABI entry points')
    binary = Path(abi.__file__).resolve().parent / 'approx_counter'
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('Installed approx_counter is missing or not executable: ' + str(binary))
    source, destination = args.input.expanduser().resolve(), args.output.expanduser().resolve()
    if not source.is_file() or source == destination:
        raise ValueError('Input must exist and output must differ from input')
    if destination.exists():
        raise ValueError('Output already exists; let Snakemake manage replacement')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Other upstream helpers also construct command strings. Keep their scratch
    # paths free of whitespace; do not relocate or copy the large read input.
    scratch = Path(tempfile.mkdtemp(prefix='wings-porechop-', dir='/tmp')).resolve()
    if any(c.isspace() for c in str(scratch)):
        scratch.rmdir()
        raise ValueError('Porechop scratch must have a space-free path')
    provenance_path = destination.with_name(destination.name + '.porechop-provenance.json')
    provenance = dict(schema_version='wings.porechop_paths.v1', status='running',
        backend='installed', porechop_abi_version=version, python=sys.executable,
        input=str(source), input_bytes=source.stat().st_size,
        input_mtime_ns=source.stat().st_mtime_ns, output=str(destination),
        counter_path=str(binary), counter_sha256=file_hash(binary),
        tool_source_sha256=file_hash(Path(tool.__file__)),
        abinitio_source_sha256=file_hash(Path(abi.__file__)),
        wrapper_sha256=file_hash(Path(__file__)), requested_threads=args.threads,
        temporary_directory=str(scratch), temporary_directory_retained=True,
        counter_commands=[])
    original_counter, original_argv = abi.execApproxCounter, sys.argv
    started = time.monotonic()
    try:
        save_json(provenance_path, provenance)
        abi.execApproxCounter = counter_wrapper(binary, provenance['counter_commands'])
        sys.argv = ['porechop_abi', '-abi', '--threads', str(args.threads),
                    '-i', str(source), '-o', str(destination), '-tmp', str(scratch)]
        provenance['argv'] = sys.argv[:]
        print('WINGS path-safe Porechop: installed backend, isolated scratch ' + str(scratch), flush=True)
        try:
            tool.main()
        except SystemExit as error:
            if error.code not in (None, 0):
                raise
        if not destination.is_file():
            raise RuntimeError('Porechop returned without creating its output')
        provenance.update(status='complete', output_bytes=destination.stat().st_size)
    except BaseException as error:
        provenance.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                          error=f'{type(error).__name__}: {error}')
        raise
    finally:
        abi.execApproxCounter, sys.argv = original_counter, original_argv
        if provenance['status'] == 'complete':
            try:
                shutil.rmtree(scratch)
                provenance['temporary_directory_retained'] = False
            except OSError as error:
                provenance['temporary_cleanup_error'] = str(error)
        provenance['wall_seconds'] = time.monotonic() - started
        save_json(provenance_path, provenance)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.threads < 1:
        parser.error('Thread count must be positive')
    return run(args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit('Porechop failed: ' + str(error))
