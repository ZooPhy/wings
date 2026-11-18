from phylodynamics_submission import beast_publications
# Shared results: fast is the default; completed, checked BEAST results are optional.
from build_phylogeography_results import (config as phylogeography_results_configuration,
    analysis_ids as phylogeography_analysis_ids, fast_rule_inputs as phylogeography_fast_inputs,
    beast_rule_inputs as phylogeography_beast_inputs, fast_rule_signature as phylogeography_fast_signature,
    beast_rule_signature as phylogeography_beast_signature)
PHYLOGEOGRAPHY_RESULTS_CONFIG = phylogeography_results_configuration(config.get('phylogeography_results', {}) or {})
PHYLOGEOGRAPHY_RESULTS_ROOT = f'{RESULTS}/run_summary/phylodynamics'
PHYLOGEOGRAPHY_RESULTS_OUTPUT = PHYLOGEOGRAPHY_RESULTS_ROOT + '/results/' + PHYLOGEOGRAPHY_RESULTS_CONFIG['run_id']
PHYLOGEOGRAPHY_RESULTS_IDS = (phylogeography_analysis_ids(PHYLOGEOGRAPHY_RESULTS_ROOT,PHYLOGEOGRAPHY_RESULTS_CONFIG,PHYLODYNAMIC_IDS)
    if PHYLOGEOGRAPHY_RESULTS_CONFIG['enabled'] else [])
if PHYLOGEOGRAPHY_RESULTS_CONFIG['enabled']:
    if RUN_PHYLODYNAMICS:
        FINAL_TARGETS.append(PHYLOGEOGRAPHY_RESULTS_OUTPUT+'/index.html')

    rule phylogeography_results_preflight:
        input:
            code=['scripts/build_phylogeography_results.py','scripts/geographic_rate_prior.py',
                  'tests/test_phylogeography_results.py','envs/phylogeography-results.yaml']
        output:
            verified=PHYLOGEOGRAPHY_RESULTS_OUTPUT+'/preflight.json'
        conda: '../envs/phylogeography-results.yaml'
        shell:
            'python tests/test_phylogeography_results.py --preflight-output {output.verified:q}'

    rule phylogeography_results_fast:
        input:
            verified=PHYLOGEOGRAPHY_RESULTS_OUTPUT+'/preflight.json',
            saved=lambda w:phylogeography_fast_inputs(PHYLOGEOGRAPHY_RESULTS_ROOT,f'{w.segment}/{w.strategy}/replicate_{w.rep}',PHYLOGEOGRAPHY_RESULTS_CONFIG),
            code=['scripts/build_phylogeography_results.py','scripts/geographic_rate_prior.py',
                  'scripts/phylodynamic_mapping.py','scripts/phylodynamic_estimands.py','scripts/phylodynamic_posterior.py']
        output:
            result=PHYLOGEOGRAPHY_RESULTS_OUTPUT+'/fast/{segment}/{strategy}/replicate_{rep}/result.json'
        params:
            root=PHYLOGEOGRAPHY_RESULTS_ROOT,
            settings=json.dumps(PHYLOGEOGRAPHY_RESULTS_CONFIG,sort_keys=True),
            analysis=lambda w:f'{w.segment}/{w.strategy}/replicate_{w.rep}',
            source_signature=lambda w:phylogeography_fast_signature(PHYLOGEOGRAPHY_RESULTS_ROOT,f'{w.segment}/{w.strategy}/replicate_{w.rep}',PHYLOGEOGRAPHY_RESULTS_CONFIG)
        conda: '../envs/phylogeography-results.yaml'
        shell:
            'python scripts/build_phylogeography_results.py fast --root {params.root:q} '
            '--analysis {params.analysis:q} --settings-json {params.settings:q} --output {output.result:q}'

    rule phylogeography_results:
        input:
            fast=[PHYLOGEOGRAPHY_RESULTS_OUTPUT+'/fast/'+key+'/result.json' for key in PHYLOGEOGRAPHY_RESULTS_IDS],
            submitted_beast=lambda w: beast_publications(config,PHYLOGEOGRAPHY_RESULTS_ROOT),
            orchestration='scripts/phylodynamics_submission.py',
            beast=lambda w:phylogeography_beast_inputs(PHYLOGEOGRAPHY_RESULTS_ROOT,PHYLOGEOGRAPHY_RESULTS_IDS,PHYLOGEOGRAPHY_RESULTS_CONFIG),
            code=['scripts/build_phylogeography_results.py','scripts/report/phylogeography-results.js',
                  'scripts/report/phylogeography-results.css','scripts/report/map-boundaries.js']
        output:
            html=PHYLOGEOGRAPHY_RESULTS_OUTPUT+'/index.html',
            json=PHYLOGEOGRAPHY_RESULTS_OUTPUT+'/results.json'
        params:
            root=PHYLOGEOGRAPHY_RESULTS_ROOT,
            dest=PHYLOGEOGRAPHY_RESULTS_OUTPUT,
            analyses=PHYLOGEOGRAPHY_RESULTS_IDS,
            settings=json.dumps(PHYLOGEOGRAPHY_RESULTS_CONFIG,sort_keys=True),
            source_signature=lambda w:phylogeography_beast_signature(PHYLOGEOGRAPHY_RESULTS_ROOT,PHYLOGEOGRAPHY_RESULTS_IDS,PHYLOGEOGRAPHY_RESULTS_CONFIG)
        conda: '../envs/phylogeography-results.yaml'
        shell:
            'python scripts/build_phylogeography_results.py report --root {params.root:q} '
            '--analyses {params.analyses:q} --settings-json {params.settings:q} --output {params.dest:q}'
