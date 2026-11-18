"""Verify recovered backend closure and optionally resolve a synthetic DAG."""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))


def check_sources():
    import yaml
    from phylodynamic_selection import configuration as selection_config
    from phylodynamic_bayesian import configuration as dating_config
    from phylodynamic_posterior import configuration as posterior_config
    from build_phylogeography_results import config as results_config
    from phylodynamics_job_options import apply_options

    for name, key, validate in (
        ('phylodynamics.example.yaml', 'phylodynamics', selection_config),
        ('bayesian-dating.example.yaml', 'bayesian_dating', dating_config),
        ('posterior-phylogeography.example.yaml', 'posterior_phylogeography', posterior_config),
        ('phylogeography-results.example.yaml', 'phylogeography_results', results_config),
    ):
        validate(yaml.safe_load((REPO / 'config' / name).read_text())[key])
    rules = ['phylodynamics', 'bayesian_dating', 'posterior_phylogeography', 'phylogeography_results']
    for name in rules:
        text = (REPO / 'rules' / (name + '.smk')).read_text()
        for dep in re.findall(r"['\"]((?:scripts|tests|envs)/[^'\"]+)['\"]", text):
            if not (REPO / dep).is_file():
                raise AssertionError('Missing rule dependency: ' + dep)
    includes = (REPO / 'rules/phylodynamics.smk').read_text()
    for name in rules[1:]:
        assert re.search(r'include:\s*[\'\"]' + name + r'\.smk[\'\"]', includes), name
    assert 'summarize(' in includes, 'Declared summary report has no producer'
    summary_source = (REPO / 'scripts/phylodynamic_summary.py').read_text()
    assert 'write_comparison(' in summary_source, 'Declared comparison report has no producer'
    # Exercise the actual new-job adapter. Never send any NCBI request.
    from unittest.mock import patch
    with patch.dict('os.environ', {'NCBI_EMAIL': 'fixture@example.org'}):
        c = {'phylogeny': {'enabled': False}}
        apply_options(c, {'phylodynamics': True}, REPO)
    selection_config(c['phylodynamics']); results_config(c['phylogeography_results'])
    assert c['phylogeography_results']['saved_inputs_only'] is False
    assert c['phylogeography_results']['method'] == 'fast'
    assert c['bayesian_dating']['enabled'] is False
    assert c['posterior_phylogeography']['enabled'] is False
    assert c['phylogeny']['enabled'] is False
    assert c['run_surveillance_explorer'] is True
    return c


def check_dag(c):
    with tempfile.TemporaryDirectory(prefix='wings-backend-dag-') as t:
        root = Path(t)
        for folder in ('scripts', 'rules', 'envs', 'tests'):
            (root / folder).symlink_to(REPO / folder, target_is_directory=True)
        metadata = root / 'results/metadata/validated_metadata.tsv'
        metadata.parent.mkdir(parents=True)
        metadata.write_text('sample_id\tcollection_date\thost\tcountry\tstate\n')
        snakefile = root / 'Snakefile'
        snakefile.write_text('import sys,json\nfrom pathlib import Path\n'
            'sys.path.insert(0,' + repr(str(REPO / 'scripts')) + ')\n'
            'RESULTS="results"\nSAMPLES=[]\nFINAL_TARGETS=[]\n'
            'include: ' + repr(str(REPO / 'rules/phylodynamics.smk')) + '\n'
            'rule all:\n    input: FINAL_TARGETS\n')
        c['phylodynamics'].update(strategies=['balanced'], replicates=1)
        for enabled in (False, True):
            c['phylodynamics']['enabled'] = enabled
            c['phylogeography_results']['enabled'] = enabled
            settings = root / 'config.json'; settings.write_text(json.dumps(c))
            command = ['snakemake', '--directory', str(root), '--snakefile', str(snakefile),
                       '--configfile', str(settings), '--cores', '1', '--dry-run', 'all']
            run = subprocess.run(command, text=True, capture_output=True)
            output = run.stdout + run.stderr
            if run.returncode:
                raise RuntimeError(output)
            for name in ('phylodynamic_reference_snapshot', 'phylodynamic_reference_selection',
                         'phylodynamic_replicate', 'phylodynamic_sensitivity', 'phylogeography_results'):
                assert (name in output) == enabled, output
            for forbidden in ('porechop', 'irma', 'bayesian_dating_chain', 'posterior_phylogeography_map'):
                assert forbidden not in output, output
    print('PASS: disabled and Fast synthetic DAG; no sequencing or BEAST jobs scheduled.')


if __name__ == '__main__':
    c = check_sources()
    print('PASS: configuration schemas, rule dependencies, report producer and submission adapter.')
    if '--unit' in sys.argv:
        suite = unittest.TestSuite()
        for filename in ('test_phylodynamics.py', 'test_phylodynamics_references.py',
                         'test_phylodynamics_lineages.py', 'test_phylodynamics_bayesian.py',
                         'test_phylodynamics_comparison.py', 'test_phylodynamics_backend_output.py', 'test_phylogeography_results.py',
                         'test_posterior_phylogeography.py'):
            if not (REPO / 'tests' / filename).is_file():
                raise SystemExit('Missing required test: ' + filename)
            found = unittest.defaultTestLoader.discover(str(REPO / 'tests'), pattern=filename)
            if not found.countTestCases():
                raise SystemExit('No tests discovered in ' + filename)
            suite.addTests(found)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        if not result.wasSuccessful():
            raise SystemExit(1)
    if '--dag' in sys.argv:
        if not shutil.which('snakemake'):
            raise SystemExit('Snakemake is required for --dag; activate the runner environment.')
        check_dag(c)
