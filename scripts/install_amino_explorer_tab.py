#!/usr/bin/env python3
"""Legacy amino-tab migration for checkouts without canonical Explorer assets.

Migrated checkouts must edit canonical modules/templates and use the asset
builder. This installer refuses those checkouts before reading or writing
report assets, analysis scripts, or saved bundles.
"""
import argparse,base64,gzip,html,json,re,shutil,subprocess,sys,tempfile,zlib
from html.parser import HTMLParser
from pathlib import Path
sys.dont_write_bytecode=True

DATA=json.loads(zlib.decompress(base64.b64decode('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')))

# WINGS_AMINO_MINIMAL_DOM_INSTALL_FIX_V1
DATA["helper"]=DATA["helper"].replace('document.querySelector(\'section[aria-label="Amino acid changes"]\')','document.querySelector?.(\'section[aria-label="Amino acid changes"]\')')

def one(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected one source anchor: '+old[:85])
    return text.replace(old,new,1)

def patch_tabs(text):
    if '// WINGS_AMINO_EXPLORER_TAB_V1' in text:return text
    text=one(text,'"overview", "genome", "genotypes"','"overview", "genome", "amino", "genotypes"')
    text=one(text,'    genome: "Genome",','    genome: "Genome",\n    amino: "Amino acids",')
    text=one(text,'  function mount(explorer) {',DATA['helper']+'  function mount(explorer) {')
    text=one(text,'    const genotypeDashboard = mountGenotypeDashboard(explorer, panels.genotypes);','    const aminoDashboard = mountAminoDashboard(explorer, panels.amino);\n    const genotypeDashboard = mountGenotypeDashboard(explorer, panels.genotypes);')
    # Hide the external sample/host toolbar; this report owns its cohort controls.
    pattern=r'(^      toolbar.hidden = [^\n]+;)'
    if len(re.findall(pattern,text,re.M))!=1:raise ValueError('Cannot identify tab toolbar visibility handler')
    text=re.sub(pattern,lambda m:m[0]+'\n      if (name === "amino") toolbar.hidden = true;\n      if (name === "amino") requestAnimationFrame(() => aminoDashboard?.refresh());',text,count=1,flags=re.M)
    text=one(text,'coverageComparison,mountGenotypeDashboard}','coverageComparison,mountGenotypeDashboard,mountAminoDashboard}')
    return text

def patch_embedded(text,tabs):
    start='/* WINGS_EXPLORER_TABS_JS_BEGIN */';end='/* WINGS_EXPLORER_TABS_JS_END */'
    if text.count(start)!=1 or text.count(end)!=1:raise ValueError('Expected one embedded Explorer Tabs module')
    a=text.index(start)+len(start);b=text.index(end,a)
    return text[:a]+'\n'+tabs.rstrip()+'\n'+text[b:]

def height_bridge(report):
    if 'WINGS_AMINO_HEIGHT_BRIDGE_V1' in report:return report
    matches=list(re.finditer(r'</body\s*>',report,re.I))
    if not matches:raise ValueError('Amino acid report has no closing body')
    a=matches[-1].start();return report[:a]+DATA['bridge']+report[a:]

def template(report):
    return '<template id="wings-amino-acid-dashboard-0"><iframe title="WINGS amino acid landscape" sandbox="allow-scripts allow-downloads" style="display:block;width:100%;height:1000px;border:0" srcdoc="'+html.escape(height_bridge(report),quote=True)+'"></iframe></template>'

class FrameParser(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=True);self.frames=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='iframe' and attrs.get('srcdoc'):self.frames.append(attrs['srcdoc'])

def migrate_report(source,report,tabs):
    source=patch_embedded(source,tabs)
    # Remove the two known legacy embeddings so the report is stored only once.
    for begin,end in [('<!-- WINGS_AMINO_COHORT_START -->','<!-- WINGS_AMINO_COHORT_END -->'),('<!-- WINGS_AMINO_ACIDS_BEGIN -->','<!-- WINGS_AMINO_ACIDS_END -->'),('<!-- WINGS_AMINO_TAB_TEMPLATE_BEGIN -->','<!-- WINGS_AMINO_TAB_TEMPLATE_END -->')]:
        if source.count(begin)!=source.count(end) or source.count(begin)>1:raise ValueError('Malformed amino acid embedding markers')
        source=re.sub(re.escape(begin)+r'.*?'+re.escape(end),'',source,flags=re.S)
    matches=list(re.finditer(r'</body\s*>',source,re.I))
    if not matches:raise ValueError('Run report has no closing body')
    a=matches[-1].start()
    return source[:a]+'<!-- WINGS_AMINO_TAB_TEMPLATE_BEGIN -->'+template(report)+'<!-- WINGS_AMINO_TAB_TEMPLATE_END -->'+source[a:]

def patch_core(text):
    if '# WINGS_AMINO_TAB_EMBED_V1' in text:return text
    a=text.index('def embed(args):');b=text.index('\ndef main():',a)
    function='''def embed(args):
    # WINGS_AMINO_TAB_EMBED_V1
    p=Path(args.report);text=p.read_text();start='<!-- WINGS_AMINO_ACIDS_BEGIN -->';end='<!-- WINGS_AMINO_ACIDS_END -->'
    text=re.sub(re.escape(start)+'.*?'+re.escape(end)+r'\\n?','',text,flags=re.S)
    report=Path(args.amino).read_text()
    bridge=BRIDGE_LITERAL
    if 'WINGS_AMINO_HEIGHT_BRIDGE_V1' not in report:
        if '</body>' not in report:raise ValueError('Amino acid report has no closing body')
        report=report.replace('</body>',bridge+'\\n</body>',1)
    fragment=(start+'<template id="wings-amino-acid-dashboard-0"><iframe title="WINGS amino acid landscape" '
              'sandbox="allow-scripts allow-downloads" style="width:100%;height:1000px;border:0" srcdoc="'+
              html.escape(report,quote=True)+'"></iframe></template>'+end)
    if '</body>' not in text:raise ValueError('Run report has no closing body')
    text=text.replace('</body>',fragment+'\\n</body>',1);p.write_text(text)

'''.replace('BRIDGE_LITERAL',repr(DATA['bridge']))
    return text[:a]+function+text[b:]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd())
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--amino-report',type=Path,help='Saved amino acid HTML if the demo does not already embed it')
    args=parser.parse_args();repo=args.repo.resolve()
    # WINGS_CANONICAL_ASSETS_GUARD_V1
    if (repo / "scripts/report/explorer-assets.json").is_file():
        raise ValueError(
            "This legacy installer is disabled for canonical Explorer assets. "
            "Edit the standalone modules/templates, then run "
            "python scripts/build_explorer_assets.py --write. "
            "To refresh an existing demo with embedded amino results, use "
            "python scripts/refresh_demo_ui.py --apply."
        )
    updates={}
    tabs_path=repo/'scripts/report/explorer-tabs.js';tabs=patch_tabs(tabs_path.read_text())
    updates['scripts/report/explorer-tabs.js']=tabs.encode()
    asset=repo/'scripts/report/surveillance-explorer.js'
    updates['scripts/report/surveillance-explorer.js']=patch_embedded(asset.read_text(),tabs).encode()
    core=repo/'scripts/wings_amino_acids.py'
    updates['scripts/wings_amino_acids.py']=patch_core(core.read_text()).encode()
    oldtests=repo/'tests/test_explorer_tabs.cjs'
    if oldtests.exists():
        text=oldtests.read_text().replace("'overview', 'genome', 'genotypes'","'overview', 'genome', 'amino', 'genotypes'")
        updates['tests/test_explorer_tabs.cjs']=text.encode()
    updates['tests/test_amino_explorer_tab.cjs']=DATA['tests'].encode()
    updates['scripts/install_amino_explorer_tab.py']=Path(__file__).read_bytes()
    updates['docs/amino-acid-explorer-tab.md']=b'# Amino acids in Surveillance Explorer\n\nThe Amino acids tab follows Genome. Saved reports are embedded as a portable template and loaded on first activation; tab switches retain cohort, wheel, zoom and filter state. The report has its own sample controls and defaults to All samples / at least 80%.\n\nRefresh an existing demo without rerunning analyses:\n\n    python scripts/install_amino_explorer_tab.py --apply\n\nIf the demo has no saved amino acid report, supply --amino-report PATH. The compressed demo is canonical; an existing local uncompressed copy is synchronized but never added to Git by this script.\n'
    demo=repo/'demo/wings_demo.wings';packed=demo.with_suffix('.wings.gz')
    if packed.exists():raw=gzip.decompress(packed.read_bytes())
    else:raw=demo.read_bytes()
    original=json.loads(raw)
    if original.get('format')!='WINGS_REPORT_BUNDLE' or not original.get('samples'):raise ValueError('Invalid demo bundle')
    value=original['run_summary'];source=value if isinstance(value,str) else value['html']
    report=None
    for begin,end in [('<!-- WINGS_AMINO_COHORT_START -->','<!-- WINGS_AMINO_COHORT_END -->'),('<!-- WINGS_AMINO_TAB_TEMPLATE_BEGIN -->','<!-- WINGS_AMINO_TAB_TEMPLATE_END -->'),('<!-- WINGS_AMINO_ACIDS_BEGIN -->','<!-- WINGS_AMINO_ACIDS_END -->')]:
        match=re.search(re.escape(begin)+r'(.*?)'+re.escape(end),source,re.S)
        if match:
            frames=FrameParser(match[1]).frames
            if len(frames)!=1:raise ValueError('Expected one amino acid iframe in saved demo section')
            report=frames[0];break
    if args.amino_report:report=args.amino_report.read_text()
    if report is None:
        standalone=repo/'demo/amino_acid_landscape.html'
        if standalone.exists():report=standalone.read_text()
    if report is None:raise ValueError('No saved amino acid report found. Supply --amino-report PATH; no files changed.')
    if 'id="aa-data"' not in report or 'id="frequency"' not in report:raise ValueError('Selected HTML is not the current amino acid report')
    data_match=re.search(r'<script[^>]+id="aa-data"[^>]*>(.*?)</script>',report,re.S)
    if not data_match:raise ValueError('Amino acid report data block missing')
    aa_samples=json.loads(data_match[1]).get('samples',[])
    if len(aa_samples)!=len(original['samples']) or {s.get('sample') for s in aa_samples}!=set(original['samples']):
        raise ValueError('Amino acid report and demo sample IDs differ; no files changed.')

    revised=migrate_report(source,report,tabs)
    bundle={**original,'run_summary':revised if isinstance(value,str) else {**value,'html':revised}}
    assert bundle['samples']==original['samples'] and bundle.get('provenance')==original.get('provenance')
    output=(json.dumps(bundle,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    updates['demo/wings_demo.wings.gz']=gzip.compress(output,compresslevel=6,mtime=0)
    if demo.exists():updates['demo/wings_demo.wings']=output
    updates['demo/amino_acid_landscape.html']=height_bridge(report).encode()
    with tempfile.TemporaryDirectory(prefix='wings-amino-tab-check-') as temp:
        stage=Path(temp)
        for rel,data in updates.items():
            if rel.startswith('demo/'):continue
            path=stage/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        subprocess.run(['node','--check',str(stage/'scripts/report/explorer-tabs.js')],check=True)
        subprocess.run(['node','--check',str(stage/'scripts/report/surveillance-explorer.js')],check=True)
        tests=[str(stage/'tests/test_amino_explorer_tab.cjs')]
        if oldtests.exists():tests.append(str(stage/'tests/test_explorer_tabs.cjs'))
        subprocess.run(['node','--test',*tests],cwd=stage,check=True)
        compile(updates['scripts/wings_amino_acids.py'],str(core),'exec')
        assert gzip.decompress(updates['demo/wings_demo.wings.gz'])==output
    print('PASS: tab navigation, lazy mounting, retained frame, height validation, empty states and demo preservation')
    originals={rel:(repo/rel).read_bytes() if (repo/rel).exists() else None for rel in updates}
    changed={rel:data for rel,data in updates.items() if data!=originals[rel]}
    if not args.apply:print('No files written. Repeat with --apply.');return
    if not changed:print('Already installed; no changes needed.');return
    backup=Path(tempfile.mkdtemp(prefix='wings-amino-tab-backup-',dir=repo))
    for rel in changed:
        if originals[rel] is not None:
            path=backup/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(originals[rel])
    try:
        for rel,data in changed.items():
            target=repo/rel;target.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as f:f.write(data);tmp=Path(f.name)
            tmp.chmod(0o644);tmp.replace(target)
    except BaseException:
        for rel in changed:
            target=repo/rel
            if originals[rel] is None:target.unlink(missing_ok=True)
            else:target.write_bytes(originals[rel])
        raise
    print('Updated:',', '.join(changed));print('Backup:',backup)
    print('Amino acids now follows Genome in the demo Surveillance Explorer. No analyses were rerun.')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        print('ERROR:',exc,file=sys.stderr);sys.exit(1)
