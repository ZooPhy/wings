#!/usr/bin/env python3
"""Exercise the actual production rules with synthetic annotated consensus data."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,default=Path.cwd());args=ap.parse_args()
    snakemake=shutil.which('snakemake')
    if not snakemake:raise SystemExit('Snakemake is required for --integration; activate snakemake_env.')
    root=args.repo.resolve();work=Path(tempfile.mkdtemp(prefix='wings-amino-integration-')).resolve()
    print('Test directory:',work,flush=True)
    (work/'scripts').mkdir()
    (work/'envs').mkdir()
    shutil.copy2(root/'envs/py-tools.yaml',work/'envs/py-tools.yaml')
    for name in ['wings_amino_acids.py','amino_acids.smk','amino_acid_visual_report.py']:shutil.copy2(root/'scripts'/name,work/'scripts'/name)
    (work/'scripts/report').mkdir()
    for name in ['amino-acid-visual.js','amino-acid-visual.css']:shutil.copy2(root/'scripts/report'/name,work/'scripts/report'/name)
    seq='ATGGCTTGTGATGAATTTGGTCATATTAAACTGATGAATCCTCAATAA' # MACDEFGHIKLMNPQ stop
    seqdir=work/'results/synthetic/medaka/PB2';seqdir.mkdir(parents=True)
    fasta=seqdir/'consensus.fasta';fasta.write_text('>synthetic_PB2\n'+seq+'\n')
    vd=work/'results/synthetic/vadr/output';vd.mkdir(parents=True)
    (vd.parent/'synthetic.vadr.done').touch()
    (vd/'synthetic.vadr.pass.tbl').write_text('>Feature synthetic_PB2\n1\t'+str(len(seq))+'\tCDS\n\t\t\tproduct\tPB2 protein\n')
    (work/'panel.json').write_text(json.dumps({'schema_version':1,'references':[dict(id='SYN.1:PB2',accession='SYN.1',protein_id='TEST.1',gene='PB2',segment='PB2',sequence='MACDEFGHIKLMNPQ',source_url='https://example.org/synthetic')]}))
    (work/'evidence.json').write_text(json.dumps({'schema_version':1,'entries':[]}))
    (work/'Snakefile').write_text('''from pathlib import Path
import shlex
RESULTS="results"
SAMPLES=["synthetic"]
AA_ENABLED=True
RUN_VADR=True
AA_PANEL="panel.json"
AA_EVIDENCE="evidence.json"
AA_MIN_IDENTITY=.9
AA_MIN_COVERAGE=.9
def segments_for_sample(wc): return ["PB2"]
include: "scripts/amino_acids.smk"
''')
    def run(label):
        command=[snakemake,'--cores','1','--profile','none','--workflow-profile','none','amino_acids_report']
        result=subprocess.run(command,cwd=work,capture_output=True,text=True)
        (work/(label+'.log')).write_text(result.stdout+'\n'+result.stderr)
        if result.returncode:raise RuntimeError('Snakemake failed; log: '+str(work/(label+'.log'))+'\n'+result.stdout[-2000:]+result.stderr[-4000:])
    run('initial')
    out=work/'results/synthetic/amino_acids/changes.json';data=json.loads(out.read_text())
    assert data['status']=='READY',data
    assert data['coordinate_schema_version']==1
    assert data['segment_sequences'][0]['sequence']==seq
    assert data['proteins'][0]['codon_map']['codons'][0]['positions']==[1,2,3]
    assert data['proteins'][0]['cds_annotation']['intervals']==[[1,len(seq)]]
    assert data['proteins'][0]['changes']==[]
    # Advance wall-clock time, never set a future input timestamp.
    time.sleep(1.1);fasta.write_text('>synthetic_PB2\n'+seq.replace('TTT','TAT')+'\n')
    run('modified_consensus');data=json.loads(out.read_text())
    assert data['proteins'][0]['changes'][0]['change']=='F6Y',data
    assert data['proteins'][0]['codon_map']['codons'][5]['bases']=='TAT'
    assert data['proteins'][0]['codon_map']['codons'][5]['positions']==[16,17,18]
    before=data['provenance']['evidence_sha256']
    time.sleep(1.1);p=work/'evidence.json';p.write_text(json.dumps({'schema_version':1,'entries':[],'version':'changed'}))
    run('modified_evidence');assert json.loads(out.read_text())['provenance']['evidence_sha256']!=before
    html=(work/'results/run_summary/amino_acids/report.html').read_text();assert 'F6Y' in html;assert 'segment-browser' in html
    print('PASS: production rules, consensus rerun, evidence rerun, and portable report.')

if __name__=='__main__':main()
