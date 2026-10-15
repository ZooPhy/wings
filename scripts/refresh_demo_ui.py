#!/usr/bin/env python3
"""Refresh the saved WINGS demo using the checkout's current report UI assets.

Preview: python3 refresh_wings_demo_ui.py --repo .
Apply:   python3 refresh_wings_demo_ui.py --repo . --apply
Check:   python3 refresh_wings_demo_ui.py --repo . --check

Updates demo/wings_demo.wings and its gzip copy together. Preserves sample
reports, embedded data, provenance, and the original report-generation date.
Uses the Python standard library; no workflow rerun or external downloads.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import gzip
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

DEMO = Path('demo/wings_demo.wings')
ASSETS = {
    'explorer script': Path('scripts/report/surveillance-explorer.js'),
    'explorer stylesheet': Path('scripts/report/surveillance-explorer.css'),
    'report stylesheet': Path('scripts/report/sample-report.css'),
    'WINGS logo': Path('assets/wings_logo.jpg'),
}


class ReportHTML(HTMLParser):
    """Index real HTML nodes; ignore tag-like strings inside script bodies."""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0] + [m.end() for m in re.finditer('\n', source)]
        self.blocks: list[dict] = []
        self.active: dict[str, dict] = {}
        self.div_depth = 0
        self.logo: dict | None = None
        self.feed(source)
        self.close()

    def source_position(self) -> int:
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        body_start = self.source_position() + len(self.get_starttag_text())
        if tag in ('script', 'style'):
            self.active[tag] = {'kind': tag, 'attrs': attributes, 'start': body_start}
        if tag == 'div':
            self.div_depth += 1
            if 'report-brand-logo' in (attributes.get('class') or '').split():
                if self.logo is not None:
                    raise ValueError('Nested report-logo containers are unsupported.')
                self.logo = {'kind': 'logo', 'start': body_start, 'depth': self.div_depth}

    def handle_endtag(self, tag):
        if tag in self.active:
            block = self.active.pop(tag)
            block['end'] = self.source_position()
            self.blocks.append(block)
        if tag == 'div':
            if self.logo is not None and self.logo['depth'] == self.div_depth:
                self.logo['end'] = self.source_position()
                self.blocks.append(self.logo)
                self.logo = None
            self.div_depth -= 1

    def body(self, block: dict) -> str:
        return self.source[block['start']:block['end']]


def asset_bytes(repo: Path) -> dict[str, bytes]:
    assets = {}
    for label, relative in ASSETS.items():
        path = repo / relative
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'Required report asset missing or empty: {relative}')
        assets[label] = path.read_bytes()
    script = assets['explorer script'].decode('utf-8')
    required = ('WINGS_TAXON_SEARCH_V1', 'WINGS_TAXON_CONTROL_ALIGNMENT_V1',
                'WINGS_EVIDENCE_LAYOUT_V1', 'WINGS_COMPACT_REFERENCE_PANEL_V1')
    missing = [marker for marker in required if marker not in script]
    if missing:
        raise ValueError('The checkout is missing the revised report UI: ' + ', '.join(missing))
    if re.search(r'</script', script, re.I):
        raise ValueError('The source Explorer script contains a literal closing-script sequence.')
    for label in ('explorer stylesheet', 'report stylesheet'):
        if re.search(r'</style', assets[label].decode('utf-8'), re.I):
            raise ValueError(f'The {label} contains a closing-style sequence.')
    return assets


def data_scripts(parsed: ReportHTML) -> list[tuple[dict, str]]:
    return [(block['attrs'], parsed.body(block)) for block in parsed.blocks
            if block['kind'] == 'script' and
            block['attrs'].get('type', '').lower() in ('application/json', 'application/ld+json')]


def refresh_html(source: str, assets: dict[str, bytes]) -> tuple[str, list[str]]:
    parsed = ReportHTML(source)
    tests = {
        'explorer script': lambda block, body: block['kind'] == 'script' and
            'class Explorer' in body and 'WINGS_MIGRATION_WEAVE_JS_BEGIN' in body,
        'explorer stylesheet': lambda block, body: block['kind'] == 'style' and
            '.wings-surveillance-explorer' in body and '.wse-genome-controls' in body,
        'report stylesheet': lambda block, body: block['kind'] == 'style' and
            '--escape-maroon:' in body and '.report-header' in body,
        'WINGS logo': lambda block, body: block['kind'] == 'logo',
    }
    replacements = []
    labels = []
    for label, matches in tests.items():
        candidates = [block for block in parsed.blocks if matches(block, parsed.body(block))]
        if len(candidates) != 1:
            raise ValueError(f'Expected one embedded {label}; found {len(candidates)}. Demo files unchanged.')
        block = candidates[0]
        if label == 'WINGS logo':
            uri = 'data:image/jpeg;base64,' + base64.b64encode(assets[label]).decode('ascii')
            replacement = '\n    <img src="' + uri + '" alt="WINGS logo">\n  '
        else:
            replacement = assets[label].decode('utf-8')
        if parsed.body(block) != replacement:
            labels.append(label)
            replacements.append((block['start'], block['end'], replacement))
    previous = len(source) + 1
    result = source
    for start, end, replacement in sorted(replacements, reverse=True):
        if end > previous:
            raise ValueError('Overlapping UI replacements. Demo files unchanged.')
        result = result[:start] + replacement + result[end:]
        previous = start
    if data_scripts(parsed) != data_scripts(ReportHTML(result)):
        raise ValueError('An embedded data block changed unexpectedly. Demo files unchanged.')
    return result, labels


def build_refresh(original: bytes, assets: dict[str, bytes]) -> tuple[bytes, list[str], int]:
    bundle = json.loads(original.decode('utf-8-sig'))
    if not isinstance(bundle, dict) or bundle.get('format') != 'WINGS_REPORT_BUNDLE':
        raise ValueError('The demo is not a WINGS report bundle.')
    summary = bundle.get('run_summary')
    samples = bundle.get('samples')
    if not isinstance(summary, dict) or not isinstance(summary.get('html'), str):
        raise ValueError('The demo has no embedded run-summary HTML.')
    if not isinstance(samples, dict) or not samples:
        raise ValueError('The demo has no sample reports.')
    if bundle.get('sample_count') != len(samples):
        raise ValueError('The demo sample count does not match its sample reports.')
    refreshed, labels = refresh_html(summary['html'], assets)
    if refreshed == summary['html']:
        return original, labels, len(samples)
    # Share all original data values; replace only the run-summary HTML value.
    updated = {**bundle, 'run_summary': {**summary, 'html': refreshed}}
    serialized = (json.dumps(updated, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    return serialized, labels, len(samples)


def compressed_matches(path: Path, source: bytes) -> bool:
    if not path.is_file():
        return False
    try:
        with gzip.open(path, 'rb') as stream:
            return stream.read() == source
    except (OSError, EOFError, ValueError):
        return False


def gzip_bytes(source: bytes) -> bytes:
    target = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=target, mode='wb', compresslevel=6, mtime=0) as stream:
        stream.write(source)
    return target.getvalue()


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    descriptor, name = tempfile.mkstemp(prefix='.wings-demo-ui-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def current_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def apply_changes(repo: Path, changes: list[tuple[Path, bytes | None, bytes]]) -> Path:
    root = Path.home() / '.wings' / 'ui-backups'
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path(tempfile.mkdtemp(prefix=f'demo-ui-{stamp}-', dir=root))
    manifest = []
    for path, original, _ in changes:
        if current_bytes(path) != original:
            raise ValueError(f'Demo changed during preparation: {path}. No demo files changed.')
        relative = path.relative_to(repo)
        manifest.append({'path': str(relative), 'created': original is None})
        if original is not None:
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    written = []
    try:
        for path, original, updated in changes:
            if current_bytes(path) != original:
                raise ValueError(f'Demo changed before writing: {path}')
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
            atomic_write(path, updated, mode)
            written.append((path, original, mode))
    except Exception:
        for path, original, mode in reversed(written):
            if original is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, original, mode)
        raise
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        repo = args.repo.expanduser().resolve()
        source = repo / DEMO
        compressed = source.with_suffix(source.suffix + '.gz')
        for path in (source, compressed):
            if path.is_symlink() or not path.resolve().is_relative_to(repo):
                raise ValueError(f'Refusing a symlink or external demo path: {path}')
        assets = asset_bytes(repo)
        original = source.read_bytes()
        updated, labels, sample_count = build_refresh(original, assets)
        gzip_current = compressed_matches(compressed, updated)
        if updated == original and gzip_current:
            print(f'Demo UI matches the current report assets; gzip verified; {sample_count} sample reports preserved.')
            return 0
        if labels:
            print('Refresh: ' + ', '.join(labels))
        print(f'Preserve {sample_count} sample reports, embedded datasets, provenance, and original generation date.')
        if args.check:
            print('Demo UI or gzip is out of date. Run with --apply to refresh both published formats.')
            return 1
        if not args.apply:
            print('Dry-run only. Repeat with --apply to update demo/wings_demo.wings and its gzip copy.')
            return 0
        changes = []
        if updated != original:
            changes.append((source, original, updated))
        if not gzip_current:
            packed = gzip_bytes(updated)
            if gzip.decompress(packed) != updated:
                raise ValueError('Generated gzip verification failed. Demo files unchanged.')
            changes.append((compressed, current_bytes(compressed), packed))
        # Ensure every source asset still matches the snapshot used for refresh.
        if asset_bytes(repo) != assets:
            raise ValueError('Report assets changed during preparation. Retry the refresh.')
        backup = apply_changes(repo, changes)
        print(f'Demo UI refreshed in both formats. Original files backed up to: {backup}')
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
