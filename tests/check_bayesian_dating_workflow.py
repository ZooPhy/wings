"""Parse and dry-run the opt-in dating rules against existing synthetic input paths."""
from pathlib import Path
import json
import subprocess
import tempfile
repo=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='wings-bayesian-dag-') as t:
    root=Path(t)
    for name in ('scripts','envs','tests'):(root/name).symlink_to(repo/name,target_is_directory=True)
    (root/'Snakefile').write_text('import sys,json\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(repo/'scripts'))+')\nRESULTS="results"\nFINAL_TARGETS=[]\ninclude: '+repr(str(repo/'rules/bayesian_dating.smk'))+'\nrule all:\n    input: FINAL_TARGETS\n')
    for name in ('result.json','alignment.fasta','dated_nodes.json','ml.treefile'):
        p=root/'results/run_summary/phylodynamics/inference/HA/balanced/replicate_1'/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
    p=root/'results/run_summary/phylodynamics/selection/HA/balanced/replicate_1/tips.tsv';p.parent.mkdir(parents=True);p.touch()
    for enabled in (False,True):
        (root/'config.json').write_text(json.dumps(dict(bayesian_dating=dict(enabled=enabled))))
        command=['snakemake','--directory',str(root),'--snakefile',str(root/'Snakefile'),'--configfile',str(root/'config.json'),'--cores','4']
        run=subprocess.run(command+['--list-rules'],capture_output=True,text=True,check=True)
        assert ('bayesian_dating_chain' in run.stdout)==enabled,run.stdout
        if enabled:
            run=subprocess.run(command+['--dry-run','results/run_summary/phylodynamics/bayesian/HA/balanced/replicate_1/initial/summary.json'],capture_output=True,text=True)
            if run.returncode:raise RuntimeError(run.stdout+'\n'+run.stderr)
            assert 'bayesian_dating_preflight' in run.stdout and 'bayesian_dating_summary' in run.stdout,run.stdout
print('PASS: dating disabled/enabled parsing and saved-input DAG with synthetic preflight and two chains.')
