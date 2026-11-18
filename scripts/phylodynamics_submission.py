"""Dependencies for explicitly requested new-job BEAST runs.

Saved-result reporting and the standalone posterior workflow retain their
existing behavior. Scientific validation remains in the dating and posterior
engines; these helpers only establish execution order.
"""
from pathlib import Path


def live_beast(config):
    results = config.get('phylogeography_results') or {}
    if not (results.get('enabled') and results.get('method') == 'beast'
            and not results.get('saved_inputs_only', False)):
        return False
    dating = config.get('bayesian_dating') or {}
    posterior = config.get('posterior_phylogeography') or {}
    if not (dating.get('enabled') and posterior.get('enabled')):
        raise ValueError('A new BEAST job requires both dating and posterior reconstruction enabled')
    if (dating.get('run_id') != posterior.get('dating_run')
            or dating.get('run_id') != results.get('dating_run')
            or posterior.get('run_id') != results.get('posterior_run')):
        raise ValueError('BEAST dating, posterior and report run IDs must agree')
    ids = dating.get('analyses')
    if not ids or ids != posterior.get('analyses'):
        raise ValueError('BEAST dating and posterior analysis IDs must agree')
    if results.get('analyses') and not set(ids).issubset(results['analyses']):
        raise ValueError('The report must include every requested BEAST analysis')
    return True


def beast_publications(config, root):
    if not live_beast(config):
        return []
    c = config['posterior_phylogeography']
    return [str(Path(root) / 'bayesian' / key / c['dating_run'] /
                'posterior' / c['run_id'] / 'publication' / name)
            for key in c['analyses'] for name in ('publication.json', 'movie.json')]


def dating_sidecar(config, path):
    # result.json is the declared producer output; load_inputs validates the
    # associated alignment/tree/metadata after inference has finished.
    return [] if live_beast(config) else [str(path)]


def posterior_inputs(config, run, inference, selection, saved_sources):
    if live_beast(config):
        # Do not read summary.json while constructing the DAG. The summary
        # depends on both completed chains. gate() then fingerprints and checks
        # ALL logs, trees, manifests, provenance and diagnostics at execution.
        return [str(Path(run) / 'summary.json')]
    return [str(p) for p in saved_sources(run, inference, selection)]
