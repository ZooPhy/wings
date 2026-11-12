#!/usr/bin/env python3
"""Refresh demo QC wording without rerendering reports or changing analysis data."""
import argparse
import copy
from datetime import datetime, timezone
import gzip
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import wings_bundle_format as codec


def refresh_html(text):
    paragraph = re.compile(r'<p>\s*Each influenza segment passes WINGS segment QC\b.*?hard QC criteria:\s*</p>', re.S)
    matches = list(paragraph.finditer(text))
    if len(matches) > 1:
        raise ValueError('Multiple QC explanations found; no files changed')
    if matches:
        old = matches[0].group()
        values = re.findall(r'<strong>(.*?)</strong>', old, re.S)
        if len(values) != 5:
            raise ValueError('Unrecognized QC thresholds; no files changed')
        values = [html.unescape(re.sub(r'<[^>]+>', '', v)).strip() for v in values]
        depth, breadth, repeated_depth, ns, status = values
        if (depth != repeated_depth or status != 'PASS'
                or not re.fullmatch(r'\d+(?:\.\d+)?x', depth)
                or any(not re.fullmatch(r'\d+(?:\.\d+)?%', v) for v in (breadth, ns))):
            raise ValueError('Unrecognized QC thresholds; no files changed')
        replacement = (
            '<p><strong>Segment PASS criteria:</strong></p>\n<ul>\n'
            f'<li>Median depth ≥ <strong>{depth}</strong></li>\n'
            f'<li>Reference positions at ≥ <strong>{depth}</strong>: ≥ <strong>{breadth}</strong></li>\n'
            '<li>Consensus length ≥ configured segment minimum</li>\n'
            f'<li>Consensus N fraction ≤ <strong>{ns}</strong></li>\n</ul>\n'
            '<p><strong>Length warning:</strong> above the configured upper length guide; '
            'still <strong>PASS</strong> if all criteria are met.</p>\n'
            '<p><strong>Genome status — segments passing QC:</strong></p>'
        )
        text = text[:matches[0].start()] + replacement + text[matches[0].end():]
    elif '<strong>Segment PASS criteria:</strong>' not in text:
        raise ValueError('QC explanation not found; no files changed')
    text = re.sub(
        r'<p>\s*These categories describe\s*<strong>QC-qualified genome recovery</strong>'
        r'\s*and should not be interpreted as a substitute for downstream annotation,'
        r' biological review, or other assay-specific quality checks\.\s*</p>\s*',
        '', text)
    if 'These categories describe' in text or 'Each influenza segment passes WINGS segment QC' in text:
        raise ValueError('Old QC explanation remains; no files changed')
    return text


def atomic_write(path, payload):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def refresh(repo, apply=False):
    repo = Path(repo).expanduser().resolve()
    candidates = [repo / 'demo' / name for name in ('wings_demo.wings', 'wings_demo.wings.gz')]
    if any(p.is_symlink() or not p.resolve().is_relative_to(repo) for p in candidates):
        raise ValueError('Refusing a symlink or external demo path')
    paths = [p for p in candidates if p.is_file()]
    if not paths:
        raise ValueError('No demo bundle found')
    snapshots = {p: p.read_bytes() for p in paths}
    bundles = [codec.read_bundle(p) for p in paths]
    if any(codec.unpack_bundle(b) != codec.unpack_bundle(bundles[0]) for b in bundles[1:]):
        raise ValueError('Raw and compressed demo copies disagree; no files changed')
    updated = copy.deepcopy(bundles[0])
    updated['run_summary']['html'] = refresh_html(updated['run_summary']['html'])
    expected = copy.deepcopy(bundles[0])
    expected['run_summary']['html'] = updated['run_summary']['html']
    if updated != expected:
        raise ValueError('Unexpected demo data change')
    if updated == bundles[0]:
        print('PASS: demo QC text is current.')
        return 0
    if not apply:
        print('Demo QC text is out of date. Run with --apply.')
        return 1
    codec.verify_roundtrip(updated)
    payload = (json.dumps(updated, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    compressed = gzip.compress(payload, compresslevel=9, mtime=0)
    if json.loads(gzip.decompress(compressed)) != updated:
        raise ValueError('Demo round-trip failed')
    if any(p.read_bytes() != snapshots[p] for p in paths):
        raise ValueError('Demo changed during refresh; no files changed')
    backup = repo / '.wings-backups' / ('demo-qc-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True, exist_ok=False)
    for p in paths:
        (backup / p.name).write_bytes(snapshots[p])
    try:
        for p in paths:
            atomic_write(p, compressed if p.suffix == '.gz' else payload)
        for p in paths:
            if codec.read_bundle(p) != updated:
                raise ValueError('Saved demo failed verification')
    except Exception:
        for p in paths:
            atomic_write(p, snapshots[p])
        raise
    print('PASS: demo QC bullets updated; sample reports, analysis data and provenance preserved.')
    print('Backup: ' + str(backup))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        return refresh(args.repo, apply=args.apply)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
