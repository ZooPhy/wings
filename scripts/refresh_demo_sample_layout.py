#!/usr/bin/env python3
"""Remove three redundant display sections from saved demo sample reports only."""
import argparse
from datetime import datetime, timezone
import gzip
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import tempfile

SECTION_IDS = {'influenza-subtype-evidence', 'irma-candidate-selection'}
METRICS = {'Segments detected', 'Segments passing segment QC', 'Consensus segments',
           'Medaka provenance', 'H5 + NA screen', 'GenoFLU status', 'Review flags'}
VOID = set('area base br col embed hr img input link meta param source track wbr'.split())


class Index(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.lines = [0] + [i+1 for i,c in enumerate(source) if c == '\n']
        self.stack = []
        self.nodes = []
        self.feed(source)
        self.close()

    def pos(self):
        line, column = self.getpos()
        return self.lines[line-1] + column

    def handle_starttag(self, tag, attrs):
        node = dict(tag=tag, attrs=dict(attrs), start=self.pos(), end=None,
                    parent=self.stack[-1] if self.stack else None, text=[])
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)
        else:
            node['end'] = self.pos() + len(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()['end'] = self.pos() + len(self.get_starttag_text())

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i]['tag'] == tag:
                self.stack[i]['end'] = self.source.index('>', self.pos())+1
                del self.stack[i:]
                break

    def handle_data(self, data):
        for node in reversed(self.stack):
            if node['tag'] in {'td', 'th'}:
                node['text'].append(data)
                break


def ancestor(node, test):
    while node:
        if test(node):
            return node
        node = node['parent']
    return None


def clean_html(source):
    parsed = Index(source)
    remove = []
    for section_id in SECTION_IDS:
        sections = [n for n in parsed.nodes if n['tag']=='section' and n['attrs'].get('id')==section_id]
        if len(sections)>1:
            raise ValueError('Duplicate report section: '+section_id)
        remove.extend(sections)
    tables = [n for n in parsed.nodes if n['tag']=='table']
    for table in tables:
        cells = [' '.join(''.join(n['text']).split()) for n in parsed.nodes
                 if n['tag'] in {'td','th'} and ancestor(n, lambda a: a['tag']=='table') is table]
        if METRICS.issubset(cells):
            panel = ancestor(table, lambda n:'report-panel' in n['attrs'].get('class','').split())
            if panel is None:
                raise ValueError('Metric summary table has no report panel')
            remove.append(panel)
    for node in parsed.nodes:
        if node['tag']=='a' and node['attrs'].get('href') in {'#'+s for s in SECTION_IDS}:
            remove.append(ancestor(node, lambda n:n['tag']=='li') or node)
    spans=[]
    for node in remove:
        if node['end'] is None:
            raise ValueError('Unclosed target HTML element')
        spans.append((node['start'],node['end']))
    # Discard any nested/duplicate spans; never remove surrounding sections.
    unique=[]
    for a,b in sorted(set(spans),key=lambda s:(s[0],-s[1])):
        if not unique or a>=unique[-1][1]:
            unique.append((a,b))
        elif b>unique[-1][1]:
            raise ValueError('Overlapping target sections')
    updated=source
    for a,b in reversed(unique):
        updated=updated[:a]+updated[b:]
    # All embedded data, chart payloads and scripts must remain intact.
    def protected(parser):
        return [(n['tag'], n['attrs'], parser.source[n['start']:n['end']])
                for n in parser.nodes if n['tag']=='script' or
                any(k.startswith('data-escape-') for k in n['attrs'])]
    if protected(parsed)!=protected(Index(updated)):
        raise ValueError('Embedded evidence or chart code changed unexpectedly')
    return updated


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    demo=repo/'demo/wings_demo.wings'
    packed=demo.with_suffix('.wings.gz')
    raw=demo.read_bytes()
    original=json.loads(raw)
    if original.get('format')!='WINGS_REPORT_BUNDLE' or not original.get('samples'):
        raise ValueError('Invalid demo bundle')
    bundle={**original,'samples':{}}
    changed=0
    for name,value in original['samples'].items():
        html=value if isinstance(value,str) else value['html']
        updated=clean_html(html)
        changed+=updated!=html
        bundle['samples'][name]=updated if isinstance(value,str) else {**value,'html':updated}
    assert bundle['run_summary']==original['run_summary']
    assert bundle.get('provenance')==original.get('provenance')
    print(f'Validated {len(bundle["samples"])} sample reports; {changed} need layout cleanup.')
    if not args.apply:
        print('No files written. Repeat with --apply to update both demo formats.')
        return
    output=(json.dumps(bundle,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    zipped=gzip.compress(output,compresslevel=6,mtime=0)
    assert gzip.decompress(zipped)==output
    folder=Path.home()/'.wings/demo-backups'
    folder.mkdir(parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('sample-layout-%Y%m%d-%H%M%S-'),dir=folder))
    for path in (demo,packed):
        if path.exists():shutil.copy2(path,backup/path.name)
    if demo.read_bytes()!=raw:raise ValueError('Demo changed during preparation; no files written')
    temp=demo.with_name('.wings-sample-layout.tmp')
    tempgz=packed.with_name('.wings-sample-layout.tmp.gz')
    try:
        temp.write_bytes(output);tempgz.write_bytes(zipped)
        temp.replace(demo);tempgz.replace(packed)
    except BaseException:
        for path in (demo,packed):
            old=backup/path.name
            if old.exists():shutil.copy2(old,path)
            elif path.exists():path.unlink()
        raise
    finally:
        temp.unlink(missing_ok=True);tempgz.unlink(missing_ok=True)
    print('Updated both demo formats. Briefing, chart cutoffs and underlying evidence preserved.')
    print('Backup:',backup)


if __name__=='__main__':
    main()
