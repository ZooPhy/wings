#!/usr/bin/env python3
"""Install additive WINGS UI modules. Dry-run by default; never writes run data."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
KIT = HERE if (HERE / 'scripts' / 'report' / 'genome-braid-clock.js').is_file() else HERE.parent
FILES = (
    'scripts/report/genome-braid-clock.js',
    'scripts/report/genome-braid-clock.css',
    'scripts/build_braid_clock_report.py',
    'scripts/install_braid_clock.py',
    'tests/test_genome_braid_clock.cjs',
    'tests/test_braid_clock_report.py',
    'tests/fixtures/braid_clock/synthetic_explorer.json',
    'tests/fixtures/braid_clock/synthetic_phenology.json',
    'docs/genome-braid-clock.md',
    'config/phenology-clock.example.json',
    'schemas/phenology-clock.schema.json',
)
ORIGINAL = '      new Explorer(root, payload);'
HOOK = '''      const explorer = new Explorer(root, payload);
      // WINGS_BRAID_CLOCK_HOOK_BEGIN
      try {
        globalThis.WINGS_BRAID_CLOCK.mountExplorer(explorer);
      } catch (error) {
        const notice = document.createElement("p");
        notice.className = "wbc-preview-error";
        notice.setAttribute("role", "status");
        notice.textContent = "Genome Braid / Ecological Clock unavailable: " + error.message;
        root.appendChild(notice);
        console.error("WINGS optional observatory preview:", error);
      }
      // WINGS_BRAID_CLOCK_HOOK_END'''


def replace_bundle(text: str, body: str, tag: str, prepend: bool) -> str:
    begin, end = f'/* {tag}_BEGIN */', f'/* {tag}_END */'
    if begin in text or end in text:
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError(f'Ambiguous existing {tag} block; no files changed.')
        text = re.sub(re.escape(begin) + r'.*?' + re.escape(end) + r'\n?', '', text, count=1, flags=re.S)
    block = begin + '\n' + body.rstrip() + '\n' + end + '\n'
    return block + text if prepend else text.rstrip() + '\n\n' + block


def patch_js(original: str, module: str) -> str:
    # A changed upstream initialization contract must be reviewed, not guessed.
    if HOOK in original:
        original = original.replace(HOOK, ORIGINAL, 1)
    if original.count(ORIGINAL) != 1:
        raise ValueError('Expected one "new Explorer(root, payload);" initialization. The upstream file differs; no files changed.')
    if 'WINGS_BRAID_CLOCK_HOOK_BEGIN' in original:
        raise ValueError('An unfamiliar hook is already installed; no files changed.')
    result = original.replace(ORIGINAL, HOOK, 1)
    return replace_bundle(result, module, 'WINGS_BRAID_CLOCK_JS', prepend=True)


def plan(repo: Path) -> dict[str, bytes]:
    repo = repo.resolve()
    if not (repo / 'Snakefile').is_file():
        raise ValueError('--repo must point to the WINGS repository root (Snakefile not found).')
    js_path = repo / 'scripts/report/surveillance-explorer.js'
    css_path = repo / 'scripts/report/surveillance-explorer.css'
    result = {rel: (KIT / rel).read_bytes() for rel in FILES}
    result['scripts/report/surveillance-explorer.js'] = patch_js(js_path.read_text(encoding='utf-8'), result['scripts/report/genome-braid-clock.js'].decode()).encode()
    result['scripts/report/surveillance-explorer.css'] = replace_bundle(css_path.read_text(encoding='utf-8'), result['scripts/report/genome-braid-clock.css'].decode(), 'WINGS_BRAID_CLOCK_CSS', prepend=False).encode()
    for rel in result:
        if not (repo / rel).resolve().is_relative_to(repo):
            raise ValueError(f'Destination escapes repository via symlink: {rel}')
    return {rel: content for rel, content in result.items() if not (repo/rel).is_file() or (repo/rel).read_bytes() != content}


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        f.write(data)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def apply(repo: Path, changes: dict[str, bytes]) -> Path:
    backup = Path(tempfile.mkdtemp(prefix='wings-braid-clock-backup-'))
    existing, written = {}, []
    for rel in changes:
        p = repo/rel
        existing[rel] = p.read_bytes() if p.is_file() else None
        if existing[rel] is not None:
            atomic_write(backup/rel, existing[rel])
    atomic_write(backup/'backup_manifest.json', json.dumps({'repository': str(repo.resolve()), 'files': {rel: {'existed': data is not None, 'sha256': hashlib.sha256(data).hexdigest() if data is not None else None} for rel, data in existing.items()}}, indent=2).encode())
    try:
        for rel, data in changes.items():
            atomic_write(repo/rel, data)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            if existing[rel] is None:
                (repo/rel).unlink(missing_ok=True)
            else:
                atomic_write(repo/rel, existing[rel])
        raise
    return backup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--apply', action='store_true', help='Apply reviewed changes; otherwise only print the plan')
    args = parser.parse_args(argv)
    try:
        changes = plan(args.repo)
        if not changes:
            print('Already installed; no changes needed.')
            return 0
        print('Files to add/update:')
        for rel in changes:
            print('  ' + rel)
        print('No Snakefile, config.yaml, README, sequences, or results files are changed.')
        if not args.apply:
            print('Dry-run only. Repeat with --apply after reviewing this list.')
            return 0
        backup = apply(args.repo, changes)
        print(f'Installed. Previous versions backed up outside the repo: {backup}')
        print('No commit, push, analysis run, or report rebuild was performed.')
    except (OSError, ValueError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
