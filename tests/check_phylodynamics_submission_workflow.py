"""Dry-run real rule files with synthetic upstream producers; no analyses run."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from phylodynamics_submission import live_beast


def main():
    if not shutil.which('snakemake'):
        raise SystemExit('Snakemake is required to validate BEAST submission dependencies; use snakemake_env.')
    with tempfile.TemporaryDirectory(prefix='wings-beast-submission-dag-') as t:
        root = Path(t)
        for name in ('scripts', 'envs', 'tests'):
            (root / name).symlink_to(REPO / name, target_is_directory=True)
        # Stub scientific imports, not the rule files or orchestration helpers.
        # This checks scheduling without Java, NCBI, sequence data or numerical libraries.
        bootstrap = '''import sys,json,types
from pathlib import Path
sys.path.insert(0, SCRIPT_DIR)
RESULTS='results'
FINAL_TARGETS=[]
RUN_PHYLODYNAMICS=True
PHYLODYNAMIC_IDS=['HA/balanced/replicate_1']
m=types.ModuleType('phylodynamic_bayesian')
m.configuration=lambda c:c
sys.modules[m.__name__]=m
m=types.ModuleType('phylodynamic_posterior')
m.configuration=lambda c:c
def forbidden_saved_read(*args):
    raise ValueError('New-job DAG read a nonexistent saved summary')
m.source_paths=forbidden_saved_read
sys.modules[m.__name__]=m
m=types.ModuleType('build_phylogeography_results')
m.config=lambda c:c
m.analysis_ids=lambda root,c,ids:ids
m.fast_rule_inputs=lambda root,key,c:[] if c.get('saved_inputs_only') else [root+'/inference/'+key+'/result.json']
m.beast_rule_inputs=lambda *a:[]
m.fast_rule_signature=lambda *a:''
m.beast_rule_signature=lambda *a:''
sys.modules[m.__name__]=m
rule phylodynamic_replicate:
    output: 'results/run_summary/phylodynamics/inference/{segment}/{strategy}/replicate_{rep}/result.json'
    shell: 'exit 99'
'''.replace('SCRIPT_DIR', repr(str(REPO / 'scripts')))
        for rule in ('bayesian_dating', 'posterior_phylogeography', 'phylogeography_results'):
            bootstrap += '\ninclude: ' + repr(str(REPO / 'rules' / (rule + '.smk'))) + '\n'
        (root / 'Snakefile').write_text(bootstrap)
        c = yaml.safe_load((REPO / 'config/phylodynamics-beast-job.yaml').read_text())
        c['phylogeography_results'] = dict(enabled=True, method='beast', saved_inputs_only=False,
            include_beast=True, run_id='submission_test', analyses=[],
            dating_run=c['bayesian_dating']['run_id'],
            posterior_run=c['posterior_phylogeography']['run_id'])
        assert live_beast(c)
        for method in ('beast', 'fast'):
            c['phylogeography_results']['method'] = method
            c['bayesian_dating']['enabled'] = method == 'beast'
            c['posterior_phylogeography']['enabled'] = method == 'beast'
            (root / 'config.json').write_text(json.dumps(c))
            command = ['snakemake', '--snakefile', str(root / 'Snakefile'), '--directory', str(root),
                       '--configfile', str(root / 'config.json'), '--cores', '4', '--dry-run',
                       'results/run_summary/phylodynamics/results/submission_test/index.html']
            run = subprocess.run(command, text=True, capture_output=True)
            output = run.stdout + run.stderr
            if run.returncode:
                raise RuntimeError(output)
            for name in ('bayesian_dating_chain', 'bayesian_dating_summary',
                         'posterior_phylogeography_gate', 'posterior_phylogeography_map',
                         'posterior_phylogeography_publish'):
                assert (name in output) == (method == 'beast'), output
            assert 'phylogeography_results' in output and 'phylodynamic_replicate' in output, output
            if method == 'beast':
                assert 'chain=1' in output and 'chain=2' in output, output
        print('PASS: real Fast/BEAST rules dry-run; BEAST waits for two chains, diagnostics, mapping and publication.')


if __name__ == '__main__':
    main()
