#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run_git(repo: Path, *args: str) -> str:
    try:
        p = subprocess.run(
            ['git', '-C', str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return p.stdout.strip()
    except Exception:
        return 'NOT_CAPTURED'


def load_single_row_tsv(path: Path) -> dict[str, str]:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    with path.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    return rows[0] if rows else {}


def parse_labeled_path(item: str, option: str) -> tuple[str, Path]:
    if '=' not in item:
        raise ValueError(f"{option} must be LABEL=PATH, got: {item}")
    label, path = item.split('=', 1)
    label = label.strip()
    if not label:
        raise ValueError(f"empty label in {option}: {item}")
    return label, Path(path)


def parse_env_arg(item: str) -> tuple[str, Path]:
    return parse_labeled_path(item, "--env")


def parse_replay_input_arg(item: str) -> tuple[str, Path]:
    return parse_labeled_path(item, "--replay-input")


def parse_primary_input_arg(item: str) -> tuple[str, Path]:
    return parse_labeled_path(item, "--primary-input")


def main() -> None:
    ap = argparse.ArgumentParser(description='Write WINGS run-level provenance records.')
    ap.add_argument('--output-tsv', required=True, type=Path)
    ap.add_argument('--output-json', required=True, type=Path)
    ap.add_argument('--repo-root', required=True, type=Path)
    ap.add_argument('--config', required=True, type=Path)
    ap.add_argument('--snakefile', required=True, type=Path)
    ap.add_argument('--blast-manifest', required=True, type=Path)
    ap.add_argument('--sample-count', required=True, type=int)
    ap.add_argument('--snakemake-version', required=True)
    ap.add_argument('--irma-image', required=True)
    ap.add_argument('--irma-module', required=True)
    ap.add_argument('--irma-runtime', required=True)
    ap.add_argument('--vadr-image', required=True)
    ap.add_argument('--vadr-mkey', required=True)
    ap.add_argument('--vadr-runtime', required=True)
    ap.add_argument('--medaka-model', default='AUTO')
    ap.add_argument('--medaka-model-records', required=True, type=int)
    ap.add_argument('--medaka-fail-soft', required=True)
    ap.add_argument('--coverage-min-depth', required=True)
    ap.add_argument('--coverage-min-breadth', required=True)
    ap.add_argument('--segment-max-n-fraction', required=True)
    ap.add_argument('--blast-min-identity', required=True)
    ap.add_argument('--blast-min-query-coverage', required=True)
    ap.add_argument('--blast-max-target-seqs', required=True)
    ap.add_argument('--blast-max-hsps', required=True)
    ap.add_argument('--env', action='append', default=[])
    ap.add_argument(
        '--replay-input',
        action='append',
        default=[],
        help='Replay-sensitive scientific input as LABEL=PATH; may be repeated.',
    )
    ap.add_argument(
        '--primary-input',
        action='append',
        default=[],
        help=(
            'Primary sequencing input as LABEL=PATH; '
            'may be repeated.'
        ),
    )
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    config = args.config.resolve()
    snakefile = args.snakefile.resolve()
    blast_manifest = args.blast_manifest.resolve()

    snakemake_version = args.snakemake_version

    git_commit = run_git(repo, 'rev-parse', 'HEAD')
    git_branch = run_git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')
    git_describe = run_git(repo, 'describe', '--tags', '--always', '--dirty')
    git_status = run_git(repo, 'status', '--porcelain')
    git_dirty = 'UNKNOWN' if git_status == 'NOT_CAPTURED' else ('true' if git_status else 'false')

    envs: dict[str, dict[str, str]] = {}
    for item in args.env:
        label, path = parse_env_arg(item)
        p = (repo / path).resolve() if not path.is_absolute() else path.resolve()
        envs[label] = {
            'path': os.path.relpath(p, repo),
            'sha256': sha256_file(p) if p.is_file() else 'MISSING',
        }

    blast = load_single_row_tsv(blast_manifest)

    replay_inputs: dict[str, dict[str, str]] = {}
    for item in args.replay_input:
        label, path = parse_replay_input_arg(item)
        p = (repo / path).resolve() if not path.is_absolute() else path.resolve()
        replay_inputs[label] = {
            'path': os.path.relpath(p, repo),
            'sha256': sha256_file(p) if p.is_file() else 'MISSING',
        }

    primary_inputs: dict[str, dict[str, object]] = {}
    for item in args.primary_input:
        label, path = parse_primary_input_arg(item)
        p = (
            (repo / path).resolve()
            if not path.is_absolute()
            else path.resolve()
        )
        primary_inputs[label] = {
            'path': os.path.relpath(p, repo),
            'sha256': sha256_file(p) if p.is_file() else 'MISSING',
            'size_bytes': p.stat().st_size if p.is_file() else None,
        }

    provenance = {
        'schema_version': 3,
        'created_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'workflow': {
            'name': 'WINGS',
            'git_commit': git_commit,
            'git_branch': git_branch,
            'git_describe': git_describe,
            'git_dirty': git_dirty,
            'snakefile': os.path.relpath(snakefile, repo),
            'snakefile_sha256': sha256_file(snakefile),
            'config_file': os.path.relpath(config, repo),
            'config_sha256': sha256_file(config),
            'sample_count': args.sample_count,
        },
        'runtime': {
            'snakemake_version': snakemake_version,
            'python_version': platform.python_version(),
            'python_executable': sys.executable,
            'platform': platform.platform(),
            'machine': platform.machine(),
            'system': platform.system(),
            'release': platform.release(),
        },
        'irma': {
            'image': args.irma_image,
            'module': args.irma_module,
            'runtime': args.irma_runtime,
        },
        'medaka': {
            'model': args.medaka_model,
            'model_records': args.medaka_model_records,
            'fail_soft': args.medaka_fail_soft,
        },
        'vadr': {
            'image': args.vadr_image,
            'mkey': args.vadr_mkey,
            'runtime': args.vadr_runtime,
        },
        'qc': {
            'coverage_min_depth': args.coverage_min_depth,
            'coverage_min_breadth': args.coverage_min_breadth,
            'segment_max_n_fraction': args.segment_max_n_fraction,
        },
        'blast': {
            'min_identity': args.blast_min_identity,
            'min_query_coverage': args.blast_min_query_coverage,
            'max_target_seqs': args.blast_max_target_seqs,
            'max_hsps': args.blast_max_hsps,
            'database_manifest': os.path.relpath(blast_manifest, repo),
            'database_manifest_sha256': sha256_file(blast_manifest),
            'database': blast,
        },
        'conda_environment_files': envs,
        'primary_inputs': primary_inputs,
        'replay_inputs': replay_inputs,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open('w', encoding='utf-8') as f:
        json.dump(provenance, f, indent=2, sort_keys=True)
        f.write('\n')

    rows: list[tuple[str, str]] = []

    def flatten(prefix: str, value):
        if isinstance(value, dict):
            for key in sorted(value):
                flatten(f'{prefix}.{key}' if prefix else key, value[key])
        else:
            rows.append((prefix, str(value)))

    flatten('', provenance)
    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_tsv.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['field', 'value'])
        w.writerows(rows)


if __name__ == '__main__':
    main()
