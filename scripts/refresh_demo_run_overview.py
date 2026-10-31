#!/usr/bin/env python3
"""Update the demo's run overview presentation, preserving saved report data."""
import argparse,gzip,json,re,shutil,tempfile
from pathlib import Path

def refresh(source, enhancement):
    source=re.sub(r'<!-- WINGS_RUN_OVERVIEW_V1 -->.*?<!-- /WINGS_RUN_OVERVIEW_V1 -->\n{0,2}', '', source, flags=re.S)
    if 'id="overview"' not in source:
        raise ValueError('Distribution tab not found')
    if '</body>' not in source: raise ValueError('Report body not found')
    # The first closing-body string can be inside a popup JavaScript template.
    # Remove the prior enhancement above, then insert at the document's final closing tag.
    position = source.rfind('</body>')
    return source[:position] + enhancement + '\n' + source[position:]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1];path=repo/'demo/wings_demo.wings';packed=path.with_suffix('.wings.gz')
    raw=path.read_bytes();bundle=json.loads(raw)
    template=(repo/'scripts/report/run-overview.html').read_text()
    value=bundle['run_summary'];html=value if isinstance(value,str) else value['html']
    updated=refresh(html,template)
    bundle['run_summary']=updated if isinstance(value,str) else {**value,'html':updated}
    assert bundle['samples']==json.loads(raw)['samples']
    print('Validated run-report run overview update. Sample reports and saved evidence preserved.')
    if not args.apply: print('Repeat with --apply to update both demo formats.');return
    output=(json.dumps(bundle,ensure_ascii=False,separators=(',',':'))+'\n').encode();zipped=gzip.compress(output,mtime=0)
    folder=Path.home()/'.wings/demo-backups';folder.mkdir(parents=True,exist_ok=True);backup=Path(tempfile.mkdtemp(prefix='run overview-',dir=folder))
    for p in (path,packed):
        if p.exists():shutil.copy2(p,backup/p.name)
    if path.read_bytes()!=raw:raise ValueError('Demo changed during preparation')
    try:
        path.write_bytes(output);packed.write_bytes(zipped)
    except BaseException:
        for p in (path,packed):
            saved=backup/p.name
            if saved.exists():shutil.copy2(saved,p)
            else:p.unlink(missing_ok=True)
        raise
    print('Updated both demo formats. Backup:',backup)
if __name__=='__main__':main()
