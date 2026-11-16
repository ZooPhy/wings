"""Translate the explicit new-job Phylodynamics option into workflow settings."""
import copy
import os
from pathlib import Path
import yaml


def validate_options(options):
    value = options.get('phylodynamics', False)
    if not isinstance(value, bool):
        raise ValueError('The phylodynamics option must be true or false')
    if value and not os.environ.get('NCBI_EMAIL', '').strip():
        raise ValueError('Set NCBI_EMAIL before starting the local runner to retrieve Phylodynamics references')


def apply_options(config, options, repo):
    validate_options(options)
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
