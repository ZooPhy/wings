#!/usr/bin/env python3
"""Update only embedded sample-chart JavaScript in both saved demo formats."""
import argparse
from datetime import datetime, timezone
import gzip
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import tempfile


class Scripts(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.offsets = [0]
        self.offsets.extend(i + 1 for i, ch in enumerate(text) if ch == '\n')
        self.start = None
        self.blocks = []
        self.feed(text)
        self.close()

    def pos(self):
        line, col = self.getpos()
        return self.offsets[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.start = self.pos() + len(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.start is not None:
            self.blocks.append((self.start, self.pos()))
            self.start = None


def refresh(html, script, css):
    candidates = [(a, b) for a, b in Scripts(html).blocks
                  if 'const renderSegmentViz = ' in html[a:b]
                  and 'escape-segment-viz' in html[a:b]]
    if len(candidates) != 1:
        raise ValueError(f'Expected one embedded segment-chart script; found {len(candidates)}')
    start, end = candidates[0]
    styles = [(a, b) for a, b in Scripts(html).blocks if '--escape-maroon:' in html[a:b] and '.report-header' in html[a:b]]
    if len(styles) != 1:
        raise ValueError(f'Expected one report stylesheet; found {len(styles)}')
    replacements = [(start, end, script), (*styles[0], css)]
    for a, b, content in sorted(replacements, reverse=True):
        html = html[:a] + '\n' + content + '\n' + html[b:]
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Otherwise validate without writing')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    path = repo / 'demo/wings_demo.wings'
    packed = path.with_suffix('.wings.gz')
    script = (repo / 'scripts/report/escape-report.js').read_text()
    if 'WINGS_SUMMARY_CARDS_V1' not in script or '</script' in script.lower():
        raise ValueError('Updated chart script missing or unsuitable for embedding')
    css = (repo / 'scripts/report/sample-report.css').read_text()
    raw = path.read_bytes()
    bundle = json.loads(raw)
    if bundle.get('format') != 'WINGS_REPORT_BUNDLE' or not bundle.get('samples'):
        raise ValueError('Invalid demo bundle')
    changed = 0
    for key, value in list(bundle['samples'].items()):
        html = value if isinstance(value, str) else value['html']
        updated = refresh(html, script, css)
        if updated != html:
            changed += 1
        bundle['samples'][key] = updated if isinstance(value, str) else {**value, 'html': updated}
    updated = (json.dumps(bundle, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    original = json.loads(raw)
    assert bundle['run_summary'] == original['run_summary'], 'Run report changed'
    assert bundle.get('provenance') == original.get('provenance'), 'Provenance changed'
    assert bundle.keys() == original.keys()
    print(f'Validated {len(bundle["samples"])} sample reports; {changed} card presentations need updating.')
    print('Sample data, saved QC statuses, run report, and briefing remain unchanged.')
    if not args.apply:
        print('No files written. Repeat with --apply to update both demo formats.')
        return
    compressed = gzip.compress(updated, compresslevel=6, mtime=0)
    assert gzip.decompress(compressed) == updated
    parent = Path.home() / '.wings/demo-backups'
    parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('summary-cards-%Y%m%d-%H%M%S-'), dir=parent))
    for p in (path, packed):
        if p.exists():
            shutil.copy2(p, backup / p.name)
    if path.read_bytes() != raw:
        raise ValueError('Demo changed during preparation; no files written')
    # All parsing and validation complete before replacing either asset.
    temp = path.with_name('.wings-demo-qc.tmp')
    temp_gz = packed.with_name('.wings-demo-qc.tmp.gz')
    try:
        temp.write_bytes(updated)
        temp_gz.write_bytes(compressed)
        temp.replace(path)
        temp_gz.replace(packed)
    except BaseException:
        for p in (path, packed):
            saved = backup / p.name
            if saved.exists():
                shutil.copy2(saved, p)
            elif p.exists():
                p.unlink()
        raise
    finally:
        temp.unlink(missing_ok=True)
        temp_gz.unlink(missing_ok=True)
    print('Updated demo/wings_demo.wings and demo/wings_demo.wings.gz')
    print('Backup:', backup)


if __name__ == '__main__':
    main()
