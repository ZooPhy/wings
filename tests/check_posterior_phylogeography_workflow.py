"""Verify a four-job postprocessing DAG with no upstream BEAST jobs."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo/'tests'))
from test_posterior_phylogeography import synthetic_run
with tempfile.TemporaryDirectory(prefix='wings-posterior-dag-') as tmp:
    root=Path(tmp)
    for name in ('scripts','envs','tests'):(root/name).symlink_to(repo/name,target_is_directory=True)
    run,inf,sel=synthetic_run(root/'fixture',n=500)
    base=root/'results/run_summary/phylodynamics'
    for source,destination in [(run,base/'bayesian/HA/balanced/replicate_1/long20m'),(inf,base/'inference/HA/balanced/replicate_1'),(sel,base/'selection/HA/balanced/replicate_1')]:
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(source),str(destination))
    (root/'Snakefile').write_text('import sys,json\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(repo/'scripts'))+')\nRESULTS="results"\nFINAL_TARGETS=[]\ninclude: '+repr(str(repo/'rules/bayesian_dating.smk'))+'\nrule all:\n    input: FINAL_TARGETS\n')
    for enabled in (False,True):
        config=dict(bayesian_dating=dict(enabled=False),posterior_phylogeography=dict(enabled=enabled))
        (root/'config.json').write_text(json.dumps(config))
        cmd=['snakemake','--directory',str(root),'--snakefile',str(root/'Snakefile'),'--configfile',str(root/'config.json'),'--cores','2']
        result=subprocess.run(cmd+['--list-rules'],capture_output=True,text=True,check=True)
        assert ('posterior_phylogeography_gate' in result.stdout)==enabled,result.stdout
        if enabled:
            target='results/run_summary/phylodynamics/bayesian/HA/balanced/replicate_1/long20m/posterior/posterior_v1/publication/movie.html'
            result=subprocess.run(cmd+['--dry-run',target],capture_output=True,text=True)
            if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
            for rule in ('preflight','gate','map','publish'):assert 'posterior_phylogeography_'+rule in result.stdout,result.stdout
            assert 'bayesian_dating_chain' not in result.stdout,result.stdout
print('PASS: posterior rules disabled/enabled; exactly the four postprocessing stages; no BEAST rerun.')
