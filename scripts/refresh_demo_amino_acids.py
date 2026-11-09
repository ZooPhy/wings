#!/usr/bin/env python3
"""Embed saved cohort amino acid results into both WINGS demos; optionally commit scoped changes."""
import argparse
import gzip
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

START='<!-- WINGS_AMINO_COHORT_START -->'
END='<!-- WINGS_AMINO_COHORT_END -->'

def demo_bundle(original, report, records):
    if original.get('format')!='WINGS_REPORT_BUNDLE' or not original.get('samples'):
        raise ValueError('Invalid demo bundle')
    names=[r['sample'] for r in records]
    if len(names)!=len(set(names)) or set(names)!=set(original['samples']):
        raise ValueError('Cohort sample IDs must match the demo sample IDs exactly. No demo files changed.')
    refs={}
    for record in records:
        if not record.get('provenance',{}).get('panel',{}).get('cohort_samples'):
            raise ValueError('Use shared cohort results from assign_cohort_amino_references.py.')
        for protein in record.get('proteins',[]):
            key=(protein.get('gene'),protein.get('segment'))
            rid=protein.get('reference_id')
            if rid: refs.setdefault(key,set()).add(rid)
    if any(len(ids)>1 for ids in refs.values()):
        raise ValueError('Inputs use different references for the same protein; regenerate shared cohort results.')
    value=original['run_summary'];source=value if isinstance(value,str) else value['html']
    if source.count(START)!=source.count(END) or source.count(START)>1:
        raise ValueError('Malformed existing amino acid demo section')
    source=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',source,flags=re.S)
    section=(START+'<section id="amino-acid-cohort-demo" style="margin:24px 0">'
        '<h2>Amino acid landscape</h2><p>Shared cohort references · All samples · At least 80% by default</p>'
        '<iframe title="Interactive amino acid landscape" sandbox="allow-scripts allow-downloads" '
        'style="width:100%;height:1100px;border:0" loading="lazy" srcdoc="'+html.escape(report,quote=True)+'"></iframe></section>'+END)
    # Insert before the final body close, preserving all original scripts and evidence.
    close=list(re.finditer(r'</body\s*>',source,re.I))
    if not close:raise ValueError('Run summary has no closing body element')
    pos=close[-1].start();updated=source[:pos]+section+source[pos:]
    result=dict(original)
    result['run_summary']=updated if isinstance(value,str) else {**value,'html':updated}
    assert result['samples']==original['samples']
    assert result.get('provenance')==original.get('provenance')
    return result

def scoped_paths(repo):
    paths={'Snakefile','demo/wings_demo.wings','demo/wings_demo.wings.gz',
           'demo/amino_acid_landscape.html','scripts/refresh_demo_amino_acids.py',
           '.github/workflows/amino-acids.yml','resources/amino_acids/evidence.json'}
    for folder in ['scripts','tests','docs']:
        for p in (repo/folder).rglob('*'):
            if p.is_file() and 'amino' in p.name and '__pycache__' not in p.parts and p.suffix in {'.py','.js','.cjs','.css','.smk','.md'}:
                paths.add(p.relative_to(repo).as_posix())
    return sorted(p for p in paths if (repo/p).is_file())

def commit(repo):
    def git(*args,check=True):
        return subprocess.run(['git','-C',str(repo),*args],text=True,capture_output=True,check=check)
    git('rev-parse','--verify','HEAD')
    paths=scoped_paths(repo)
    staged=set(git('diff','--cached','--name-only','-z').stdout.rstrip('\0').split('\0'))-{''}
    if staged-set(paths):
        raise ValueError('Unrelated files are staged; unstage them before using --commit: '+', '.join(sorted(staged-set(paths))))
    git('add','--',*paths)
    if git('diff','--cached','--quiet',check=False).returncode==0:
        print('No amino acid/demo changes to commit.');return
    result=git('commit','-m','Add shared cohort amino acid landscape and interactive demo')
    print(result.stdout.strip())
    print('Commit:',git('rev-parse','--short','HEAD').stdout.strip())
    print('Local commit created; not pushed.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd())
    parser.add_argument('--inputs',nargs='+',required=True,type=Path)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--commit',action='store_true',help='Commit amino acid files, Snakefile integration and demo outputs only; no push')
    args=parser.parse_args();repo=args.repo.resolve()
    if args.commit and not args.apply:parser.error('--commit requires --apply')
    demo=repo/'demo/wings_demo.wings';packed=demo.with_suffix('.wings.gz')
    raw=demo.read_bytes();original=json.loads(raw)
    inputs=[p.resolve() for p in args.inputs];records=[json.loads(p.read_text()) for p in inputs]
    renderer=repo/'scripts/wings_amino_acids.py'
    with tempfile.TemporaryDirectory(prefix='wings-demo-amino-check-') as temp:
        work=Path(temp);report=work/'report.html'
        subprocess.run([sys.executable,str(renderer),'report','--inputs',*[str(p) for p in inputs],
            '--html',str(report),'--tsv',str(work/'report.tsv'),'--json',str(work/'report.json')],check=True,cwd=repo)
        rendered=report.read_text()
        result=demo_bundle(original,rendered,records)
    output=(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    compressed=gzip.compress(output,compresslevel=6,mtime=0)
    assert gzip.decompress(compressed)==output
    print('PASS: cohort references, sample IDs, demo preservation and gzip round trip')
    print('Samples:',len(records))
    if not args.apply:
        print('No files written. Repeat with --apply; add --commit to create a local Git commit.');return
    target=repo/'scripts/refresh_demo_amino_acids.py'
    updates={demo:output,packed:compressed,repo/'demo/amino_acid_landscape.html':rendered.encode(),target:Path(__file__).read_bytes()}
    backup=Path(tempfile.mkdtemp(prefix='wings-amino-demo-backup-',dir=repo))
    for path in updates:
        if path.exists():
            dest=backup/path.relative_to(repo);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    if demo.read_bytes()!=raw:raise ValueError('Demo changed during validation; no files written')
    try:
        for path,data in updates.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
                f.write(data);tmp=Path(f.name)
            tmp.chmod(0o644);tmp.replace(path)
    except BaseException:
        for path in updates:
            old=backup/path.relative_to(repo)
            if old.exists():shutil.copy2(old,path)
            else:path.unlink(missing_ok=True)
        raise
    print('Updated both demo formats and demo/amino_acid_landscape.html. Backup:',backup)
    if args.commit:commit(repo)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print('ERROR:',exc,file=sys.stderr)
        if isinstance(exc,subprocess.CalledProcessError) and exc.stderr:print(exc.stderr,file=sys.stderr)
        sys.exit(1)
