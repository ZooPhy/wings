#!/usr/bin/env python3
"""Refresh location controls in saved presentation files without rerunning inference."""
import base64
import gzip
from html.parser import HTMLParser
import json
from pathlib import Path
import re

MARKER='/* Shared results for a fixed dated tree and checked BEAST dated-tree draws. */'
ASSET=re.compile(r'(globalThis\.WINGS_PHYLODYNAMICS_ASSETS\s*=\s*\{\s*script\s*:\s*)([\"\'])([A-Za-z0-9+/=]+)\2')
class Scripts(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=False);self.text=text;self.offsets=[0];self.blocks=[];self.active=None
        for line in text.splitlines(keepends=True):self.offsets.append(self.offsets[-1]+len(line))
        self.feed(text);self.close()
    def absolute_position(self):
        line,col=self.getpos();return self.offsets[line-1]+col
    def handle_starttag(self,tag,attrs):
        if tag=='script':self.active=(self.absolute_position()+len(self.get_starttag_text()),dict(attrs))
    def handle_endtag(self,tag):
        if tag=='script' and self.active:
            start,attrs=self.active;self.blocks.append((start,self.absolute_position(),attrs));self.active=None

def update_script(body,viewer):
    encoded=base64.b64encode(viewer.encode()).decode()
    body=ASSET.sub(lambda m:m[1]+m[2]+encoded+m[2],body)
    if MARKER in body:
        if body.count(MARKER)!=1:raise ValueError('Ambiguous shared viewer script')
        start=body.index(MARKER)
        if not body[start:].rstrip().endswith('})(typeof globalThis!==\'undefined\'?globalThis:this);'):
            raise ValueError('Viewer is followed by unexpected code; presentation left unchanged')
        body=body[:start]+viewer
    return body

def refresh_html(text,viewer):
    blocks=Scripts(text).blocks
    before=[text[a:b] for a,b,attrs in blocks if attrs.get('type')=='application/json']
    result=text
    for a,b,attrs in reversed(blocks):
        if attrs.get('src') or attrs.get('type','').lower() not in ('','text/javascript','application/javascript','module'):continue
        result=result[:a]+update_script(text[a:b],viewer)+result[b:]
    after=[result[a:b] for a,b,attrs in Scripts(result).blocks if attrs.get('type')=='application/json']
    if before!=after:raise ValueError('Scientific JSON payload changed during presentation refresh')
    return result

def refresh_bundle(content,viewer):
    compressed=content[:2]==b'\x1f\x8b';data=json.loads(gzip.decompress(content) if compressed else content)
    summary=data.get('run_summary')
    if not isinstance(summary,dict) or not isinstance(summary.get('html'),str):raise ValueError('Unknown WINGS bundle layout')
    old=summary['html'];new=refresh_html(old,viewer)
    if new==old:return content
    summary['html']=new
    result=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
    return gzip.compress(result,mtime=0) if compressed else result

def plan_refresh(run,viewer):
    run=Path(run).expanduser().resolve()
    if not (run/'results').is_dir():raise ValueError('Expected an existing run folder containing results: '+str(run))
    paths=set((run/'results').rglob('*.html'))|set((run/'results').rglob('phylodynamics-embed.js'))
    paths.update(p for p in run.rglob('*.wings*') if p.name.endswith(('.wings','.wings.gz')))
    changes={}
    for path in sorted(paths):
        for parent in [path,*path.parents]:
            if parent==run:break
            if parent.is_symlink():raise ValueError('Symlinked presentation path: '+str(path))
        if not path.resolve().is_relative_to(run):raise ValueError('Presentation path escapes run')
        old=path.read_bytes()
        if path.name.endswith(('.wings','.wings.gz')):new=refresh_bundle(old,viewer)
        elif path.suffix=='.html':new=refresh_html(old.decode(),viewer).encode()
        else:new=update_script(old.decode(),viewer).encode()
        if new!=old:changes[path]=(old,new)
    return changes
