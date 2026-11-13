#!/usr/bin/env python3
"""Refresh published demo navigation and sample cards without rerunning analysis.

Preview: python scripts/refresh_demo_navigation.py --repo .
Apply:   python scripts/refresh_demo_navigation.py --repo . --apply
Verify:  python scripts/refresh_demo_navigation.py --repo . --check
"""
import argparse
import copy
import gzip
import json
from pathlib import Path
import sys

import refresh_demo_ui as ui
from refresh_saved_explorer_ui import refresh_sample_html, remove_refresh_notice
import wings_bundle_format as codec
from refresh_demo_qc_copy import refresh_html as refresh_qc_html
from refresh_concordance_inputs import enrich_report


def build_refresh(bundle, assets, sample_css, sample_js):
    original = codec.unpack_bundle(bundle)
    updated = copy.deepcopy(original)
    summary = updated.get('run_summary', {})
    if not isinstance(summary.get('html'), str):
        raise ValueError('Demo has no run-summary HTML')
    samples = updated.get('samples')
    if not isinstance(samples, dict) or not samples:
        raise ValueError('Demo has no sample reports')
    if updated.get('sample_count') != len(samples):
        raise ValueError('Demo sample count does not match its sample reports')
    summary['html'], labels = ui.refresh_html(summary['html'], assets)
    summary['html'] = remove_refresh_notice(summary['html'])
    summary['html'] = refresh_qc_html(summary['html'])
    summary['html'] = enrich_report(summary['html'])
    for sample in samples.values():
        sample['html'] = refresh_sample_html(remove_refresh_notice(sample['html']), sample_css, sample_js, ui)
    # Only report HTML may change. Metadata, calls and provenance stay exact.
    def evidence(value):
        result = copy.deepcopy(value)
        result['run_summary'].pop('html')
        for sample in result['samples'].values():
            sample.pop('html')
        return result
    if evidence(updated) != evidence(original):
        raise ValueError('Demo evidence or provenance changed')
    codec.verify_roundtrip(updated)
    if updated == original:
        return bundle, False, len(samples)
    packed = codec.pack_bundle(updated) if 'shared' in bundle else updated
    if codec.unpack_bundle(packed) != updated:
        raise ValueError('Refreshed demo failed its bundle round-trip')
    return packed, True, len(samples)


def refresh(repo, mode='preview'):
    repo = Path(repo).expanduser().resolve()
    raw_path = repo / 'demo/wings_demo.wings'
    gzip_path = repo / 'demo/wings_demo.wings.gz'
    for path in (raw_path, gzip_path):
        if path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise ValueError('Refusing a symlink or external demo path')
    existing = [path for path in (raw_path, gzip_path) if path.is_file()]
    if not existing:
        raise ValueError('No demo/wings_demo.wings or demo/wings_demo.wings.gz found')
    snapshots = {path: path.read_bytes() for path in existing}
    bundles = [codec.read_bundle(path) for path in existing]
    original = bundles[0]
    if any(codec.unpack_bundle(value) != codec.unpack_bundle(original) for value in bundles[1:]):
        raise ValueError('Demo raw and gzip copies disagree; no files changed')
    assets = ui.asset_bytes(repo)
    sample_paths = [repo / ('scripts/report/sample-navigation.' + suffix) for suffix in ('css', 'js')]
    sample_assets = [path.read_text(encoding='utf-8') for path in sample_paths]
    updated, changed, count = build_refresh(original, assets, *sample_assets)
    if not changed and gzip_path.is_file():
        print(f'PASS: demo summary and {count} sample reports match current UI assets.')
        return 0
    if mode == 'check':
        print('Demo UI is out of date. Run with --apply.')
        return 1
    if mode != 'apply':
        print(f'Preview: refresh summary and {count} sample pages. Repeat with --apply.')
        return 0
    payload = (json.dumps(updated, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    compressed = ui.gzip_bytes(payload)
    if gzip.decompress(compressed) != payload:
        raise ValueError('Demo gzip verification failed')
    if ui.asset_bytes(repo) != assets or [path.read_text(encoding='utf-8') for path in sample_paths] != sample_assets:
        raise ValueError('UI assets changed during preparation; no files changed')
    if any(path.read_bytes() != expected for path, expected in snapshots.items()):
        raise ValueError('Demo changed during preparation; no files changed')
    changes = []
    if raw_path.is_file() and snapshots[raw_path] != payload:
        changes.append((raw_path, snapshots[raw_path], payload))
    if snapshots.get(gzip_path) != compressed:
        changes.append((gzip_path, snapshots.get(gzip_path), compressed))
    backup = ui.apply_changes(repo, changes)
    print(f'PASS: demo summary and {count} sample pages refreshed; data and provenance preserved.')
    print('Original demo backed up to: ' + str(backup))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        return refresh(args.repo, 'apply' if args.apply else 'check' if args.check else 'preview')
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
