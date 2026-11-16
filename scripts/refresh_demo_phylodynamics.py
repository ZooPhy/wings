#!/usr/bin/env python3
"""Refresh saved bundle UI and attach explicitly simulated or checked real results.

Default: update the supplied demo with its clearly labelled illustrative fixture.
--bundle FILE --results FILE: attach real checked results to a matching saved run.
No biological analyses, workflow jobs or reference downloads are performed.
"""
import argparse
import gzip
import json
from pathlib import Path
from refresh_demo_ui import ReportHTML, asset_bytes, refresh_html, atomic_write
from explorer_phylodynamics import attach_results


def refresh(data, repo, results=None):
    bundle = json.loads(data)
    html, _ = refresh_html(bundle['run_summary']['html'], asset_bytes(repo))
    blocks = [b for b in ReportHTML(html).blocks if b['kind'] == 'script' and (b['attrs'].get('id') or '').startswith('wings-surveillance-data-')]
    if len(blocks) != 1:
        raise ValueError('Expected one surveillance payload in the saved report')
    block = blocks[0]
    payload = json.loads(html[block['start']:block['end']])
    if results:
        attach_results(payload, results)
    else:
        existing = payload.get('phylodynamics_results')
        if existing and existing.get('demo') is not True:
            raise ValueError('The demo already contains real results; refusing to replace them with simulated data')
        model = json.loads((repo / 'resources/demo/phylodynamics.json').read_text())
        if model.get('demo') is not True:
            raise ValueError('Demo fixture must be explicitly marked as simulated')
        payload['phylodynamics_results'] = model
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    bundle['run_summary']['html'] = html[:block['start']] + encoded + html[block['end']:]
    return json.dumps(bundle, ensure_ascii=False, separators=(',', ':')).encode()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path('.'))
    p.add_argument('--bundle', type=Path)
    p.add_argument('--results', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args(); repo = a.repo.resolve()
    if a.bundle and not a.results:
        p.error('--bundle requires --results; simulated data are only used in the supplied demo')
    if a.results and not a.bundle:
        p.error('--results requires --bundle')
    path = a.bundle or repo / 'demo/wings_demo.wings.gz'
    raw = path.read_bytes(); raw = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
    updated = refresh(raw, repo, a.results)
    target = a.output or path
    if not a.apply:
        print('Validated bundle refresh. Use --apply to write:', target); return
    if a.bundle and not a.output:
        p.error('Use --output for real runs so the original bundle is preserved')
    content = gzip.compress(updated, mtime=0) if target.suffix == '.gz' else updated
    atomic_write(target, content, 0o644)
    if not a.bundle:
        plain = repo / 'demo/wings_demo.wings'
        if plain.exists():
            atomic_write(plain, updated, 0o644)
    print('Updated:', target)


if __name__ == '__main__':
    main()
