"""Exercise saved-input isolation with upstream producers and a saved checkpoint."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo/'tests'))
from test_phylogeography_results import fixture,KEY

with tempfile.TemporaryDirectory(prefix='wings-shared-results-') as tmp:
    root=Path(tmp)
    for name in ('scripts','envs','tests'):(root/name).symlink_to(repo/name,target_is_directory=True)
    saved=root/'results/run_summary/phylodynamics';fixture(saved)
    keys=[f'HA/{s}/replicate_{i}' for s in ('balanced','available') for i in (1,2,3)]
    configured=keys+[f'HA/diversity/replicate_{i}' for i in (1,2,3)]
    (saved/'selection/selection_summary.json').write_text(json.dumps(dict(replicates=[dict(id=k,status='blocked' if k==keys[-1] else 'ready') for k in keys])))
    (root/'checkpoint-ready').write_text('ready')
    source='import sys,json\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(repo/'scripts'))+')\nRESULTS="results"\nFINAL_TARGETS=[]\nRUN_PHYLODYNAMICS=True\nPHYLODYNAMIC_IDS='+repr(configured)+'\n'
    source+='''
checkpoint upstream_checkpoint:
    output: 'checkpoint-ready'
    shell: 'exit 93'
def upstream_selection(w):
    checkpoints.upstream_checkpoint.get()
    return 'results/run_summary/phylodynamics/selection'
rule phylodynamic_replicate:
    input: upstream_selection
    output:
        'results/run_summary/phylodynamics/inference/{segment}/{strategy}/replicate_{rep}/result.json',
        'results/run_summary/phylodynamics/inference/{segment}/{strategy}/replicate_{rep}/movie.json'
    shell: 'exit 94'
rule posterior_phylogeography_publication:
    output: 'results/run_summary/phylodynamics/bayesian/{segment}/{strategy}/replicate_{rep}/long20m/posterior/posterior_5k/publication/publication.json'
    shell: 'exit 95'
'''
    source+='include: '+repr(str(repo/'rules/phylogeography_results.smk'))+'\nrule all:\n    input: FINAL_TARGETS\n'
    (root/'Snakefile').write_text(source)
    command=['snakemake','--directory',str(root),'--snakefile',str(root/'Snakefile'),'--configfile',str(root/'config.json'),'--cores','2']
    target='results/run_summary/phylodynamics/results/fast_v1/index.html'
    for enabled in (False,True):
        (root/'config.json').write_text(json.dumps(dict(phylogeography_results=dict(enabled=enabled,saved_inputs_only=True))))
        listing=subprocess.run(command+['--list-rules'],text=True,capture_output=True,check=True)
        assert ('phylogeography_results_fast' in listing.stdout)==enabled,listing.stdout
        if not enabled:continue
        for allowed in ([],['--allowed-rules','phylogeography_results_preflight','phylogeography_results_fast','phylogeography_results']):
            result=subprocess.run(command+['--dry-run',target]+allowed,text=True,capture_output=True)
            if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
            for rule in ('phylogeography_results_preflight','phylogeography_results_fast','phylogeography_results'):assert rule in result.stdout,result.stdout
            for forbidden in ('localrule phylodynamic_replicate:','rule phylodynamic_replicate:','localcheckpoint upstream_checkpoint:','localrule posterior_phylogeography_publication:','/diversity/'):
                assert forbidden not in result.stdout,result.stdout
        # Actual synthetic report: any accidental upstream execution fails (exit 93–95).
        result=subprocess.run(command+[target],text=True,capture_output=True)
        if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
        data=json.loads((saved/'results/fast_v1/results.json').read_text())
        assert [a['id'] for a in data['analyses']]==keys
        assert data['analyses'][0]['methods']['fast']['status']=='passed'
        assert all('fast' in a['unavailable'] for a in data['analyses'][1:])
        # File changes should trigger the report even without input edges to producers.
        p=saved/'inference'/KEY/'result.json';record=json.loads(p.read_text());record.update(status='blocked',reasons=['synthetic changed source']);p.write_text(json.dumps(record))
        result=subprocess.run(command+[target],text=True,capture_output=True)
        if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
        data=json.loads((saved/'results/fast_v1/results.json').read_text())
        assert 'synthetic changed source' in data['analyses'][0]['unavailable']['fast']
    # Exercise the actual standalone entry point with a deliberately invalid main Snakefile.
    (root/'Snakefile').write_text('THIS MAIN WORKFLOW MUST NEVER BE PARSED!!!\n')
    (root/'rules').symlink_to(repo/'rules',target_is_directory=True)
    (root/'Snakefile.phylogeography-report').write_bytes((repo/'Snakefile.phylogeography-report').read_bytes())
    (root/'config.yaml').write_text(json.dumps(dict(phylogeography_results=dict(saved_inputs_only=False,run_id='isolated_v3'))))
    isolated=['snakemake','--directory',str(root),'--snakefile',str(root/'Snakefile.phylogeography-report'),'--cores','2']
    listing=subprocess.run(isolated+['--list-rules'],text=True,capture_output=True,check=True)
    names=set(listing.stdout.strip().splitlines())
    assert names=={'all','phylogeography_results_preflight','phylogeography_results_fast','phylogeography_results'},listing.stdout
    result=subprocess.run(isolated+['--dry-run'],text=True,capture_output=True)
    if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
    # Restore the synthetic valid saved result and build through the default target.
    record.update(status='complete',reasons=[]);p.write_text(json.dumps(record))
    result=subprocess.run(isolated,text=True,capture_output=True)
    if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
    data=json.loads((saved/'results/isolated_v3/results.json').read_text())
    assert data['settings']['saved_inputs_only'] is True
    assert [a['id'] for a in data['analyses']]==keys
    assert data['analyses'][0]['methods']['fast']['status']=='passed'
print('PASS: saved cohort, missing-result handling, refresh tracking, and isolated entry point; main Snakefile never loaded.')
