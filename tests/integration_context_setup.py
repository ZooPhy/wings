#!/usr/bin/env python3
"""Isolated production Snakemake snapshot/metadata rules; no downloads or reads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]

def rule(source,name):
    start=source.index('rule '+name+':')
    match=re.search(r'^rule \w+:|^if |^# WINGS_',source[start+1:],re.M)
    return source[start:start+1+match.start()] if match else source[start:]


def write_changed_seed(seed, output, data):
    """Age only the synthetic prior output, then write the input at real time.

    This makes the new input newer even on filesystems with coarse timestamp
    resolution, without creating future-dated inputs or forcing a job rerun.
    """
    old = output.stat()
    past = min(old.st_mtime_ns, time.time_ns() - 5_000_000_000)
    os.utime(output, ns=(old.st_atime_ns, past))
    seed.write_text(json.dumps(data) + "\n")
    if seed.stat().st_mtime_ns <= output.stat().st_mtime_ns:
        raise RuntimeError("Synthetic input must be newer than the previous output")


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--self-check',action='store_true');args=p.parse_args()
    source=(ROOT/'Snakefile').read_text();snapshot=rule(source,'public_genotype_snapshot');metadata=rule(source,'validate_metadata')
    report=rule(source,'run_summary_html')
    assert 'input.genotype_refresh' not in report
    assert 'genotype_snapshot=f"{RESULTS}/run_summary/public_genotype_frequencies.json"' in report
    assert '"genotype_frequencies", f"{RESULTS}/run_summary/public_genotype_frequencies.json"' in source
    assert '("context_setup", CONTEXT_SELECTION)' in source
    assert 'genotype_frequencies")' in snapshot
    if args.self_check:
        print('PASS: production rule extraction, separated acquisition, and replay dependencies.');return
    executable=shutil.which('snakemake')
    if not executable:raise SystemExit('Snakemake is required for --integration; activate snakemake_env first.')
    work=Path(tempfile.mkdtemp(prefix='wings-context-integration-')).resolve();print('Test directory:',work,flush=True)
    sys.path.insert(0,str(ROOT/'scripts'));import context_setup as c
    meta=work/'metadata.tsv';meta.write_text('sample_id\thost\tcollection_date\tcountry\tstate\nB\tCAGO\t2024-09-15\tUS\tAZ\nA\tCAGO\t2024-09-15\tUS\tAZ\n')
    expected=work/'expected.tsv';c.normalized_metadata(meta,expected)
    (work/'scripts').mkdir();(work/'envs').mkdir()
    for name in ('prepare_public_genotype_snapshot.py','refresh_genotype_frequencies.py','build_genotype_frequencies.py','validate_metadata.py'):
        shutil.copyfile(ROOT/'scripts'/name,work/'scripts'/name)
    shutil.copyfile(ROOT/'envs/py-tools.yaml',work/'envs/py-tools.yaml')
    seed=work/'seed.json'
    data={'schema_version':'wings.genotype-frequencies.v1','unit':'SRA run','has_metadata':True,
          'audit':{'included_runs':0,'assigned_runs':0},'groups':[],'context_scope':{'reason':'Synthetic offline integration'}}
    seed.write_text(json.dumps(data,indent=2)+'\n')
    header='''from pathlib import Path
RESULTS="results"
METADATA_FILE="metadata.tsv"
METADATA_REQUIRE_ALL=True
SAMPLES=["A","B"]
GENOTYPE_FREQUENCY_SEED="seed.json"
GENOTYPE_FREQUENCY_CONFIG={"prepared_snapshot":True}
GENOTYPE_FREQUENCY_OFFLINE=True
CONTEXT_SELECTION="prepared"
def as_bool(value):return bool(value)
def frozen_reexecution_input(label):return ""
'''
    (work/'Snakefile').write_text(header+snapshot+'\n'+metadata)
    env={k:v for k,v in os.environ.items() if not k.startswith('SNAKEMAKE_')};env['PYTHONDONTWRITEBYTECODE']='1'
    def execute(label):
        cmd=[executable,'--cores','1','--profile','none','--workflow-profile','none','--rerun-incomplete',
             'results/run_summary/public_genotype_frequencies.json','results/metadata/validated_metadata.tsv']
        p=subprocess.run(cmd,cwd=work,env=env,capture_output=True,text=True)
        log=work/(label+'.log');log.write_text(p.stdout+'\n'+p.stderr)
        if p.returncode:
            raise RuntimeError('Integration failed; see '+str(log)+'\n'+(p.stdout+'\n'+p.stderr)[-12000:])
    execute('initial')
    out=work/'results/run_summary/public_genotype_frequencies.json'
    assert out.read_bytes()==seed.read_bytes()
    assert (work/'results/metadata/validated_metadata.tsv').read_bytes()==expected.read_bytes()
    stamp=out.stat().st_mtime_ns;execute('unchanged');assert out.stat().st_mtime_ns==stamp
    data['context_scope']['reason']='Changed synthetic snapshot'
    write_changed_seed(seed,out,data)
    execute('changed');assert out.read_bytes()==seed.read_bytes()
    refreshed=out.stat().st_mtime_ns
    execute('changed-unchanged')
    assert out.stat().st_mtime_ns==refreshed
    assert out.read_bytes()==seed.read_bytes()
    summary={'passed':True,'checks':['exact prepared bytes','production metadata normalization','unchanged snapshot reused','changed seed refreshes output','refreshed snapshot remains up to date'],'synthetic':True}
    (work/'test_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('PASS: isolated context snapshot integration. No genomic jobs, source downloads, or repository results were used.')
    print('Summary:',work/'test_summary.json')

if __name__=='__main__':main()
