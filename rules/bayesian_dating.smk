from phylodynamics_submission import live_beast, dating_sidecar
# Optional conditional Bayesian node dating, separate from geographic jump inference.
from phylodynamic_bayesian import configuration as bayesian_dating_configuration
BAYESIAN_DATING_CONFIG = bayesian_dating_configuration(config.get('bayesian_dating', {}) or {})
BAYESIAN_DATING_DIR = f'{RESULTS}/run_summary/phylodynamics/bayesian'
if BAYESIAN_DATING_CONFIG['enabled']:
    BAYESIAN_DATING_RUN = BAYESIAN_DATING_CONFIG['run_id']
    BAYESIAN_DATING_IDS = BAYESIAN_DATING_CONFIG['analyses']
    FINAL_TARGETS.extend([f'{BAYESIAN_DATING_DIR}/{key}/{BAYESIAN_DATING_RUN}/summary.json' for key in BAYESIAN_DATING_IDS])

    rule bayesian_dating_preflight:
        input:
            code=['scripts/WingsBeast.java', 'scripts/phylodynamic_bayesian.py', 'scripts/validate_bayesian_dating.py',
                  'tests/test_phylodynamics_bayesian.py', 'envs/bayesian-dating.yaml']
        output:
            verified=f'{BAYESIAN_DATING_DIR}/preflight/{BAYESIAN_DATING_RUN}/verified.json'
        params:
            command=json.dumps(BAYESIAN_DATING_CONFIG['beast_command'])
        conda: '../envs/bayesian-dating.yaml'
        shell:
            'python scripts/validate_bayesian_dating.py --command-json {params.command:q} --output {output.verified:q}'

    rule bayesian_dating_chain:
        input:
            preflight=f'{BAYESIAN_DATING_DIR}/preflight/{BAYESIAN_DATING_RUN}/verified.json',
            result=f'{RESULTS}/run_summary/phylodynamics/inference/{{segment}}/{{strategy}}/replicate_{{rep}}/result.json',
            alignment=lambda w: dating_sidecar(config, f'{RESULTS}/run_summary/phylodynamics/inference/{w.segment}/{w.strategy}/replicate_{w.rep}/alignment.fasta'),
            ml=lambda w: dating_sidecar(config, f'{RESULTS}/run_summary/phylodynamics/inference/{w.segment}/{w.strategy}/replicate_{w.rep}/ml.treefile'),
            nodes=lambda w: dating_sidecar(config, f'{RESULTS}/run_summary/phylodynamics/inference/{w.segment}/{w.strategy}/replicate_{w.rep}/dated_nodes.json'),
            tips=lambda w: dating_sidecar(config, f'{RESULTS}/run_summary/phylodynamics/selection/{w.segment}/{w.strategy}/replicate_{w.rep}/tips.tsv'),
            code=['scripts/phylodynamics_submission.py', 'scripts/phylodynamic_bayesian.py', 'scripts/WingsBeast.java']
        output:
            complete=f'{BAYESIAN_DATING_DIR}/{{segment}}/{{strategy}}/replicate_{{rep}}/{BAYESIAN_DATING_RUN}/chain_{{chain}}/complete.json'
        wildcard_constraints:
            segment='[A-Za-z0-9_-]+', strategy='[A-Za-z0-9_-]+', rep='[1-9][0-9]*',
            chain='|'.join(str(n) for n in range(1,BAYESIAN_DATING_CONFIG['chains']+1))
        params:
            settings=json.dumps(BAYESIAN_DATING_CONFIG,sort_keys=True),
            inference=lambda w: f'{RESULTS}/run_summary/phylodynamics/inference/{w.segment}/{w.strategy}/replicate_{w.rep}',
            selection=lambda w: f'{RESULTS}/run_summary/phylodynamics/selection/{w.segment}/{w.strategy}/replicate_{w.rep}',
            destination=lambda w: f'{BAYESIAN_DATING_DIR}/{w.segment}/{w.strategy}/replicate_{w.rep}/{BAYESIAN_DATING_RUN}/chain_{w.chain}'
        threads: BAYESIAN_DATING_CONFIG['threads']
        conda: '../envs/bayesian-dating.yaml'
        shell:
            'python scripts/phylodynamic_bayesian.py chain --settings-json {params.settings:q} '
            '--inference {params.inference:q} --selection {params.selection:q} '
            '--chain {wildcards.chain} --threads {threads} --output {params.destination:q}'

    rule bayesian_dating_summary:
        input:
            chains=lambda w: [f'{BAYESIAN_DATING_DIR}/{w.segment}/{w.strategy}/replicate_{w.rep}/{BAYESIAN_DATING_RUN}/chain_{n}/complete.json' for n in range(1,BAYESIAN_DATING_CONFIG['chains']+1)],
            code=['scripts/phylodynamics_submission.py', 'scripts/phylodynamic_bayesian.py', 'scripts/WingsBeast.java']
        output:
            json=f'{BAYESIAN_DATING_DIR}/{{segment}}/{{strategy}}/replicate_{{rep}}/{BAYESIAN_DATING_RUN}/summary.json',
            html=f'{BAYESIAN_DATING_DIR}/{{segment}}/{{strategy}}/replicate_{{rep}}/{BAYESIAN_DATING_RUN}/tmrca.html'
        params:
            settings=json.dumps(BAYESIAN_DATING_CONFIG,sort_keys=True),
            chains=lambda w: [f'{BAYESIAN_DATING_DIR}/{w.segment}/{w.strategy}/replicate_{w.rep}/{BAYESIAN_DATING_RUN}/chain_{n}' for n in range(1,BAYESIAN_DATING_CONFIG['chains']+1)],
            destination=lambda w: f'{BAYESIAN_DATING_DIR}/{w.segment}/{w.strategy}/replicate_{w.rep}/{BAYESIAN_DATING_RUN}'
        conda: '../envs/bayesian-dating.yaml'
        shell:
            'python scripts/phylodynamic_bayesian.py summary --settings-json {params.settings:q} '
            '--chains {params.chains:q} --output {params.destination:q}'
