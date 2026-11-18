from phylodynamics_submission import posterior_inputs
# Postprocess completed BEAST runs only. No upstream chain rules are dependencies.
from phylodynamic_posterior import configuration as posterior_configuration, source_paths as posterior_source_paths
POSTERIOR_CONFIG = posterior_configuration(config.get('posterior_phylogeography', {}) or {})
if POSTERIOR_CONFIG['enabled']:
    POSTERIOR_ROOT = f'{RESULTS}/run_summary/phylodynamics'
    POSTERIOR_PATH = POSTERIOR_ROOT + '/bayesian/{segment}/{strategy}/replicate_{rep}/' + POSTERIOR_CONFIG['dating_run'] + '/posterior/' + POSTERIOR_CONFIG['run_id']

    def posterior_run(w):
        return f'{POSTERIOR_ROOT}/bayesian/{w.segment}/{w.strategy}/replicate_{w.rep}/{POSTERIOR_CONFIG["dating_run"]}'

    def posterior_inference(w):
        return f'{POSTERIOR_ROOT}/inference/{w.segment}/{w.strategy}/replicate_{w.rep}'

    def posterior_selection(w):
        return f'{POSTERIOR_ROOT}/selection/{w.segment}/{w.strategy}/replicate_{w.rep}'

    def posterior_destination(w):
        return posterior_run(w) + '/posterior/' + POSTERIOR_CONFIG['run_id']

    rule posterior_phylogeography_preflight:
        input:
            code=['scripts/phylodynamic_posterior.py','tests/test_posterior_phylogeography.py',
                  'scripts/report/posterior-phylogeography.js','scripts/report/posterior-phylogeography.css',
                  'envs/posterior-phylogeography.yaml']
        output:
            verified=f'{POSTERIOR_ROOT}/bayesian/posterior_preflight/{POSTERIOR_CONFIG["run_id"]}/verified.json'
        conda: '../envs/posterior-phylogeography.yaml'
        shell:
            'WINGS_REQUIRE_POSTERIOR_DIAGNOSTICS=1 python tests/test_posterior_phylogeography.py --preflight-output {output.verified:q}'

    rule posterior_phylogeography_gate:
        input:
            preflight=f'{POSTERIOR_ROOT}/bayesian/posterior_preflight/{POSTERIOR_CONFIG["run_id"]}/verified.json',
            sources=lambda w: posterior_inputs(config,posterior_run(w),posterior_inference(w),posterior_selection(w),posterior_source_paths),
            orchestration='scripts/phylodynamics_submission.py'
        output:
            verified=POSTERIOR_PATH+'/gate/verified.json',
            trees=POSTERIOR_PATH+'/gate/trees.json'
        params:
            settings=json.dumps(POSTERIOR_CONFIG,sort_keys=True),
            run=posterior_run,inference=posterior_inference,selection=posterior_selection,
            dest=lambda w:posterior_destination(w)+'/gate',
            publication=lambda w:posterior_destination(w)+'/publication'
        conda: '../envs/posterior-phylogeography.yaml'
        shell:
            'python scripts/phylodynamic_posterior.py gate --settings-json {params.settings:q} '
            '--run {params.run:q} --inference {params.inference:q} --selection {params.selection:q} '
            '--output {params.dest:q} --publication {params.publication:q}'

    rule posterior_phylogeography_map:
        input:
            verified=POSTERIOR_PATH+'/gate/verified.json',trees=POSTERIOR_PATH+'/gate/trees.json',
            code=['scripts/phylodynamic_posterior.py','scripts/phylodynamic_mapping.py','scripts/phylodynamic_estimands.py']
        output:
            mapping=POSTERIOR_PATH+'/mapping/mapping.json'
        params:
            settings=json.dumps(POSTERIOR_CONFIG,sort_keys=True),
            gate=lambda w:posterior_destination(w)+'/gate',dest=lambda w:posterior_destination(w)+'/mapping',
            publication=lambda w:posterior_destination(w)+'/publication'
        threads: 1
        conda: '../envs/posterior-phylogeography.yaml'
        shell:
            'python scripts/phylodynamic_posterior.py map --settings-json {params.settings:q} '
            '--gate {params.gate:q} --output {params.dest:q} --publication {params.publication:q}'

    rule posterior_phylogeography_publish:
        input:
            verified=POSTERIOR_PATH+'/gate/verified.json',trees=POSTERIOR_PATH+'/gate/trees.json',
            mapping=POSTERIOR_PATH+'/mapping/mapping.json',
            code=['scripts/phylodynamic_posterior.py','scripts/report/posterior-phylogeography.js',
                  'scripts/report/posterior-phylogeography.css','scripts/report/map-boundaries.js']
        output:
            verified=POSTERIOR_PATH+'/publication/publication.json',
            movie=POSTERIOR_PATH+'/publication/movie.html',data=POSTERIOR_PATH+'/publication/movie.json'
        params:
            settings=json.dumps(POSTERIOR_CONFIG,sort_keys=True),
            gate=lambda w:posterior_destination(w)+'/gate',mapping=lambda w:posterior_destination(w)+'/mapping',
            dest=lambda w:posterior_destination(w)+'/publication'
        conda: '../envs/posterior-phylogeography.yaml'
        shell:
            'python scripts/phylodynamic_posterior.py publish --settings-json {params.settings:q} '
            '--gate {params.gate:q} --mapping {params.mapping:q} --output {params.dest:q}'
