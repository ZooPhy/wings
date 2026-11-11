#!/usr/bin/env python3
"""Refresh a saved WINGS report's navigation into a new output directory.

Run after applying wings-explorer-navigator.patch to the WINGS checkout.
No sequencing, ecological analysis, downloads or configuration changes occur.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def module(repo, name):
    spec = importlib.util.spec_from_file_location('_navigation_' + name, repo / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PresentationIndex(HTMLParser):
    """Index actual presentation nodes, ignoring tag-like script strings."""
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0] + [m.end() for m in re.finditer('\n', source)]
        self.body_ends = []
        self.nodes = []
        self.active = {}
        self.notice = None
        self.feed(source)
        self.close()

    def position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        identity = attributes.get('id')
        if identity in ('wings-sample-navigation-css', 'wings-sample-navigation-js'):
            node = {'start': self.position(), 'id': identity}
            if tag == 'link':
                node['end'] = self.position() + len(self.get_starttag_text())
                self.nodes.append(node)
            else:
                self.active[tag] = node
        if tag == 'aside':
            if self.notice is not None:
                self.notice['depth'] += 1
            elif identity == 'wings-ebird-refresh-notice':
                self.notice = {'start': self.position(), 'id': identity, 'depth': 1}

    def handle_endtag(self, tag):
        if tag == 'body':
            self.body_ends.append(self.position())
        if tag in self.active:
            node = self.active.pop(tag)
            node['end'] = self.source.index('>', self.position()) + 1
            self.nodes.append(node)
        if tag == 'aside' and self.notice is not None:
            self.notice['depth'] -= 1
            if not self.notice['depth']:
                self.notice['end'] = self.source.index('>', self.position()) + 1
                self.nodes.append(self.notice)
                self.notice = None


def remove_refresh_notice(source):
    result = source
    nodes = [node for node in PresentationIndex(source).nodes if node['id'] == 'wings-ebird-refresh-notice']
    for node in sorted(nodes, key=lambda n: n['start'], reverse=True):
        result = result[:node['start']] + result[node['end']:]
    return result


def refresh_sample_html(source, css, javascript, ui):
    if re.search(r'</style', css, re.I) or re.search(r'</script', javascript, re.I):
        raise ValueError('Unsafe closing tag in sample navigation asset')
    index = PresentationIndex(source)
    result = source
    for node in sorted((n for n in index.nodes if n['id'].startswith('wings-sample-navigation-')), key=lambda n: n['start'], reverse=True):
        end = node['end'] + (source[node['end']:node['end'] + 1] == '\n')
        result = result[:node['start']] + result[end:]
    ends = PresentationIndex(result).body_ends
    if len(ends) != 1:
        raise ValueError('Sample report must have exactly one actual closing body tag')
    fragment = ('<style id="wings-sample-navigation-css">' + css + '</style>\n'
                '<script id="wings-sample-navigation-js">' + javascript + '</script>')
    position = ends[0]
    result = result[:position] + fragment + result[position:]
    if ui.data_scripts(ui.ReportHTML(source)) != ui.data_scripts(ui.ReportHTML(result)):
        raise ValueError('Embedded sample evidence changed during navigation refresh')
    return result


def add_record(source, record, ui):
    parsed = ui.ReportHTML(source)
    blocks = [b for b in parsed.blocks if b['kind'] == 'script' and b['attrs'].get('id') == 'wings-navigation-refresh']
    value = json.dumps(record, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    if len(blocks) == 1:
        b = blocks[0]
        return source[:b['start']] + value + source[b['end']:]
    if blocks:
        raise ValueError('Duplicate navigation provenance blocks')
    class BodyEnd(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.lines = [0] + [m.end() for m in re.finditer('\n', source)]
            self.positions = []
        def handle_endtag(self, tag):
            if tag == 'body':
                line, column = self.getpos()
                self.positions.append(self.lines[line - 1] + column)
    p = BodyEnd()
    p.feed(source)
    p.close()
    if len(p.positions) != 1:
        raise ValueError('Expected exactly one actual closing body tag')
    position = p.positions[0]
    fragment = '<script type="application/json" id="wings-navigation-refresh">' + value + '</script>\n'
    return source[:position] + fragment + source[position:]


def update(args):
    repo, source_dir, output = [p.expanduser().resolve() for p in (args.repo, args.input_dir, args.output_dir)]
    if output.exists():
        raise ValueError('Output already exists; choose a new output directory')
    if source_dir in output.parents or output in source_dir.parents:
        raise ValueError('Input and output must be separate directories')
    ui = module(repo, 'refresh_demo_ui')
    codec = module(repo, 'wings_bundle_format')
    assets = ui.asset_bytes(repo)
    script = assets['explorer script'].decode('utf-8')
    if 'WINGS_VIEW_NAVIGATOR_V1' not in script or 'WINGS_D3_HIERARCHY_BEGIN' not in script:
        raise ValueError('Apply the navigation patch and rebuild Explorer assets first')
    node = shutil.which('node')
    if not node:
        raise ValueError('Node.js is required for the script syntax check')
    result = subprocess.run([node, '--check'], input=script, text=True, capture_output=True)
    if result.returncode:
        raise ValueError('Explorer script failed syntax check: ' + result.stderr[:1200])
    refresh_samples = getattr(args, 'refresh_samples', False)
    remove_notice = getattr(args, 'remove_refresh_notice', False)
    sample_assets = {}
    if refresh_samples:
        for kind in ('css', 'js'):
            path = repo / ('scripts/report/sample-navigation.' + kind)
            sample_assets[kind] = path.read_text(encoding='utf-8')
        result = subprocess.run([node, '--check'], input=sample_assets['js'], text=True, capture_output=True)
        if result.returncode:
            raise ValueError('Sample navigation script failed syntax check: ' + result.stderr[:1200])
    html_path = source_dir / 'run_summary/run_summary.html'
    bundle_path = source_dir / 'wings_report_bundle.wings'
    hashes = {str(p): sha(p) for p in (html_path, bundle_path)}
    source = html_path.read_text(encoding='utf-8')
    original = codec.unpack_bundle(codec.read_bundle(bundle_path))
    if original['run_summary']['html'] != source:
        raise ValueError('Saved HTML and bundle do not match')
    print('Updating navigation; preserving saved evidence and sample reports...', flush=True)
    refreshed, changed = ui.refresh_html(source, assets)
    # refresh_html independently verifies that all embedded JSON blocks are unchanged.
    if remove_notice:
        refreshed = remove_refresh_notice(refreshed)
    record = {
        'schema': 'wings.navigation-refresh.v1',
        'refreshed_at': datetime.now(timezone.utc).isoformat(),
        'tool_sha256': sha(Path(__file__)),
        'source_sha256': hashes,
        'assets_sha256': {str(p): sha(repo / p) for p in ui.ASSETS.values()},
        'changed_assets': changed,
        'analysis_evidence_preserved': True,
        'sample_reports_preserved': not refresh_samples,
        'sample_analysis_content_preserved': True,
        'sample_navigation_updated': refresh_samples,
        'refresh_notice_removed': remove_notice,
    }
    refreshed = add_record(refreshed, record, ui)
    updated = copy.deepcopy(original)
    updated['run_summary'] = {**original['run_summary'], 'html': refreshed}
    updated['navigation_refresh'] = record
    if refresh_samples:
        record['sample_assets_sha256'] = {kind: sha(repo / ('scripts/report/sample-navigation.' + kind)) for kind in sample_assets}
        for sid, data in updated['samples'].items():
            if Path(sid).name != sid or sid in ('.', '..'):
                raise ValueError('Unsafe sample identifier')
            sample_path = source_dir / sid / 'summary' / (sid + '.sample_summary.html')
            if sample_path.read_text(encoding='utf-8') != original['samples'][sid]['html']:
                raise ValueError('Saved sample HTML and bundle disagree: ' + sid)
            hashes[str(sample_path)] = sha(sample_path)
            html = remove_refresh_notice(data['html']) if remove_notice else data['html']
            data['html'] = refresh_sample_html(html, sample_assets['css'], sample_assets['js'], ui)
            assert {k: v for k, v in data.items() if k != 'html'} == {k: v for k, v in original['samples'][sid].items() if k != 'html'}
        # Include the finalized sample-asset record in the report as well.
        refreshed = add_record(refreshed, record, ui)
        updated['run_summary']['html'] = refreshed
    assert {k: v for k, v in updated.items() if k not in ('run_summary', 'navigation_refresh', 'samples')} == {k: v for k, v in original.items() if k not in ('run_summary', 'navigation_refresh', 'samples')}
    codec.verify_roundtrip(updated)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.wings-navigation-', dir=output.parent))
    try:
        shutil.copytree(source_dir, stage, dirs_exist_ok=True)
        (stage / 'run_summary/run_summary.html').write_text(refreshed, encoding='utf-8')
        if refresh_samples:
            for sid, data in updated['samples'].items():
                (stage / sid / 'summary' / (sid + '.sample_summary.html')).write_text(data['html'], encoding='utf-8')
        codec.write_bundle(codec.pack_bundle(updated), stage / 'wings_report_bundle.wings')
        check = codec.unpack_bundle(codec.read_bundle(stage / 'wings_report_bundle.wings'))
        assert check['run_summary']['html'] == refreshed
        assert check['samples'] == updated['samples']
        assert check.get('provenance') == original.get('provenance')
        (stage / 'navigation_refresh.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        for path, expected in hashes.items():
            if sha(Path(path)) != expected:
                raise ValueError('An input changed during the update: ' + path)
        if output.exists():
            raise ValueError('Output appeared during the update')
        stage.rename(output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    print('PASS: saved evidence and bundle round-trip preserved; sample navigation ' + ('updated.' if refresh_samples else 'unchanged.'))
    print('HTML: ' + str(output / 'run_summary/run_summary.html'))
    print('Bundle: ' + str(output / 'wings_report_bundle.wings'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--refresh-samples', action='store_true', help='Add sample section navigation and return links')
    parser.add_argument('--remove-refresh-notice', action='store_true', help='Remove the visible refresh banner; retain recorded provenance')
    update(parser.parse_args())


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, AssertionError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
