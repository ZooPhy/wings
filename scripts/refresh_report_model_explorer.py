#!/usr/bin/env python3
"""Refresh one saved .wings bundle with the current model-explorer interface."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import sys

import refresh_demo_ui as ui
from refresh_concordance_inputs import enrich_report
import wings_bundle_format as codec


def refresh(repo, source, output=None):
    repo, source = Path(repo).expanduser().resolve(), Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve() if output else source.with_name(source.name.removesuffix('.gz').removesuffix('.wings') + '-model-explorer.wings')
    if output.exists() or output == source:
        raise ValueError('Choose a new output path; existing bundles are never overwritten')
    original = codec.read_bundle(source)
    updated = copy.deepcopy(original)
    refreshed, _labels = ui.refresh_html(updated['run_summary']['html'], ui.asset_bytes(repo))
    updated['run_summary']['html'] = enrich_report(refreshed)
    before, after = copy.deepcopy(original), copy.deepcopy(updated)
    before['run_summary'].pop('html')
    after['run_summary'].pop('html')
    if before != after:
        raise ValueError('Saved sample reports or evidence changed')
    codec.verify_roundtrip(updated)
    payload = (json.dumps(updated, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()
    if output.suffix == '.gz':
        payload = gzip.compress(payload, mtime=0)
    with output.open('xb') as stream:
        stream.write(payload)
    if codec.read_bundle(output) != updated:
        output.unlink()
        raise ValueError('Refreshed bundle failed verification')
    print('PASS: refreshed model explorer; original bundle, sample reports and saved results preserved.')
    print('Open this file in WINGS:\n' + str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        refresh(args.repo, args.input, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
