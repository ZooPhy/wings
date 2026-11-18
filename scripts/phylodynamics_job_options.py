"""Translate the explicit new-job Phylodynamics option into workflow settings."""
import copy
import os
from pathlib import Path
import yaml
from wings_credentials import runtime_environment


BEAST_REQUIRED = (
    'scripts/phylodynamic_bayesian.py', 'scripts/WingsBeast.java',
    'scripts/validate_bayesian_dating.py', 'scripts/phylodynamic_posterior.py',
    'scripts/phylodynamics_submission.py', 'rules/bayesian_dating.smk',
    'rules/posterior_phylogeography.smk', 'rules/phylogeography_results.smk',
    'envs/bayesian-dating.yaml', 'envs/posterior-phylogeography.yaml',
    'config/phylodynamics-beast-job.yaml',
    'tests/test_phylodynamics_bayesian.py', 'tests/test_posterior_phylogeography.py',
)


def supported_methods(repo):
    return ['fast', 'beast'] if all((Path(repo) / p).is_file() for p in BEAST_REQUIRED) else ['fast']


def validate_options(options, repo=None):
    value = options.get('phylodynamics', False)
    if not isinstance(value, bool):
        raise ValueError('The phylodynamics option must be true or false')
    method = options.get('phylodynamics_method', 'fast')
    if method not in ('fast', 'beast'):
        raise ValueError('Phylodynamics method must be fast or beast')
    if value and method == 'beast' and repo is not None and 'beast' not in supported_methods(repo):
        raise ValueError('BEAST workflow files are missing; install the complete BEAST submission update')
    if value and not runtime_environment().get('NCBI_EMAIL', '').strip():
        if os.environ.get('WINGS_DESKTOP_WORKSPACE'):
            raise ValueError('Add an NCBI contact email in WINGS Settings → Add or update NCBI email, then refresh this page before running Phylodynamics.')
        raise ValueError('Set NCBI_EMAIL before starting the local runner to retrieve Phylodynamics references')


def apply_options(config, options, repo):
    validate_options(options, repo)
    for key in ('phylodynamics', 'phylogeography_results', 'bayesian_dating', 'posterior_phylogeography'):
        config[key] = dict(config.get(key) or {}, enabled=False)
    if not options.get('phylodynamics', False):
        return
    repo = Path(repo)
    selection = yaml.safe_load((repo / 'config/phylodynamics.example.yaml').read_text())['phylodynamics']
    results = yaml.safe_load((repo / 'config/phylogeography-results.example.yaml').read_text())['phylogeography_results']
    config['phylodynamics'] = copy.deepcopy(selection)
    config['phylodynamics']['enabled'] = True
    # The reviewed HA lineage workflow currently uses the H5 reference dataset.
    config['phylodynamics']['references'].update(source='ncbi', email_env='NCBI_EMAIL', subtypes=['H5'])
    for section in ('references', 'lineage'):
        value = config['phylodynamics'].get(section, {})
        if value.get('cache_dir'):
            value['cache_dir'] = str((repo / value['cache_dir']).resolve())
    config['phylogeography_results'] = copy.deepcopy(results)
    config['phylogeography_results'].update(enabled=True, method='fast', saved_inputs_only=False, include_beast=False, analyses=[])
    config['run_surveillance_explorer'] = True
    if options.get('phylodynamics_method', 'fast') == 'beast':
        preset = yaml.safe_load((repo / 'config/phylodynamics-beast-job.yaml').read_text())
        for key in ('bayesian_dating', 'posterior_phylogeography'):
            config[key] = copy.deepcopy(preset[key])
        config['phylogeography_results'].update(
            method='beast', include_beast=True,
            dating_run=config['bayesian_dating']['run_id'],
            posterior_run=config['posterior_phylogeography']['run_id'])
        from phylodynamics_submission import live_beast
        live_beast(config)
