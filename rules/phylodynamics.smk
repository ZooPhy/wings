# Optional reference sampling and conditional geographic inference.
# Included before FINAL_TARGETS is frozen for provenance archiving.
sys.path.insert(0, str(Path(workflow.basedir) / 'scripts'))
from phylodynamic_selection import configuration as phylodynamic_configuration

PHYLODYNAMIC_CONFIG = phylodynamic_configuration(config.get('phylodynamics', {}) or {})
RUN_PHYLODYNAMICS = PHYLODYNAMIC_CONFIG['enabled']
PHYLODYNAMIC_DIR = f'{RESULTS}/run_summary/phylodynamics'
PHYLODYNAMIC_REFERENCES = f'{PHYLODYNAMIC_DIR}/references'
PHYLODYNAMIC_SELECTION = f'{PHYLODYNAMIC_DIR}/selection'
PHYLODYNAMIC_SUMMARY = f'{PHYLODYNAMIC_DIR}/summary.json'
PHYLODYNAMIC_IDS = [f'{s}/{strategy}/replicate_{rep}'
    for s in PHYLODYNAMIC_CONFIG['segments']
    for strategy in PHYLODYNAMIC_CONFIG['strategies']
    for rep in range(1, PHYLODYNAMIC_CONFIG['replicates']+1)]

if RUN_PHYLODYNAMICS:
    FINAL_TARGETS.extend([PHYLODYNAMIC_SUMMARY, f'{PHYLODYNAMIC_DIR}/sensitivity.html', f'{PHYLODYNAMIC_DIR}/primary_movie.json'])

    rule phylodynamic_reference_snapshot:
        input:
            metadata=f'{RESULTS}/metadata/validated_metadata.tsv',
            coverage=expand(f'{RESULTS}/{{sample}}/coverage/coverage.tsv', sample=SAMPLES),
            local=([PHYLODYNAMIC_CONFIG['references']['source_fasta'],
                    PHYLODYNAMIC_CONFIG['references']['source_metadata']]
                   if PHYLODYNAMIC_CONFIG['references']['source']=='local' else []),
            code=['scripts/phylodynamic_references.py','scripts/phylodynamic_selection.py',
                  'scripts/phylodynamic_lineages.py','scripts/phylodynamic_temporal.py',
                  'scripts/select_contextual_references.py','scripts/build_contextual_phylogeny_inputs.py',
                  'scripts/report/map-boundaries.js']
        output:
            directory(PHYLODYNAMIC_REFERENCES)
        params:
            settings=json.dumps(PHYLODYNAMIC_CONFIG,sort_keys=True)
        resources:
            ncbi=1
        run:
            from phylodynamic_references import prepare
            prepare(Path(input.metadata),Path(RESULTS),Path(output[0]),json.loads(params.settings))

    rule phylodynamic_reference_selection:
        input:
            references=PHYLODYNAMIC_REFERENCES,
            metadata=f'{RESULTS}/metadata/validated_metadata.tsv',
            coverage=expand(f'{RESULTS}/{{sample}}/coverage/coverage.tsv', sample=SAMPLES),
            consensus=expand(f'{RESULTS}/{{sample}}/merged/consensus_all_segments.fasta', sample=SAMPLES),
            code=['scripts/phylodynamic_selection.py','scripts/phylodynamic_references.py',
                  'scripts/phylodynamic_lineages.py','scripts/phylodynamic_temporal.py',
                  'scripts/select_contextual_references.py',
                  'scripts/build_contextual_phylogeny_inputs.py','scripts/report/map-boundaries.js']
        output:
            directory(PHYLODYNAMIC_SELECTION)
        params:
            settings=json.dumps(PHYLODYNAMIC_CONFIG,sort_keys=True),
            samples=json.dumps(list(SAMPLES)),
            results=str(RESULTS)
        threads: PHYLODYNAMIC_CONFIG['threads']
        conda: '../envs/phylodynamics.yaml'
        shell:
            'python scripts/phylodynamic_selection.py --results {params.results:q} '
            '--metadata {input.metadata:q} --public-table {input.references:q}/references.tsv '
            '--fasta {input.references:q}/references.fasta --output {output:q} '
            '--settings-json {params.settings:q} --samples-json {params.samples:q} --threads {threads}'

    rule phylodynamic_replicate:
        input:
            selected=PHYLODYNAMIC_SELECTION,
            code=['scripts/phylodynamic_inference.py','scripts/phylodynamic_mapping.py','scripts/phylodynamic_estimands.py',
                  'scripts/phylodynamic_selection.py','scripts/phylodynamic_references.py',
                  'scripts/phylodynamic_lineages.py','scripts/phylodynamic_temporal.py','scripts/build_phylogeography_movie.py',
                  'scripts/report/phylogeography-movie.js']
        output:
            result=f'{PHYLODYNAMIC_DIR}/inference/{{segment}}/{{strategy}}/replicate_{{rep}}/result.json',
            movie=f'{PHYLODYNAMIC_DIR}/inference/{{segment}}/{{strategy}}/replicate_{{rep}}/movie.json'
        wildcard_constraints:
            segment='|'.join(PHYLODYNAMIC_CONFIG['segments']),
            strategy='|'.join(PHYLODYNAMIC_CONFIG['strategies']),
            rep='|'.join(str(n) for n in range(1,PHYLODYNAMIC_CONFIG['replicates']+1))
        params:
            selection=lambda w: f'{PHYLODYNAMIC_SELECTION}/{w.segment}/{w.strategy}/replicate_{w.rep}',
            destination=lambda w: f'{PHYLODYNAMIC_DIR}/inference/{w.segment}/{w.strategy}/replicate_{w.rep}'
        threads: PHYLODYNAMIC_CONFIG['threads']
        conda: '../envs/phylodynamics.yaml'
        shell:
            'python scripts/phylodynamic_inference.py --selection {params.selection:q} '
            '--output {params.destination:q} --threads {threads}'

    rule phylodynamic_sensitivity:
        input:
            selected=PHYLODYNAMIC_SELECTION,
            results=[f'{PHYLODYNAMIC_DIR}/inference/{key}/result.json' for key in PHYLODYNAMIC_IDS],
            movies=[f'{PHYLODYNAMIC_DIR}/inference/{key}/movie.json' for key in PHYLODYNAMIC_IDS],
            code=['scripts/phylodynamic_summary.py', 'scripts/build_phylodynamic_comparison.py',
                  'scripts/report/phylodynamic-comparison.js', 'scripts/report/phylodynamic-comparison.css',
                  'scripts/report/phylogeography-movie.js', 'scripts/report/phylogeography-movie.css',
                  'scripts/report/map-boundaries.js']
        output:
            json=PHYLODYNAMIC_SUMMARY,
            html=f'{PHYLODYNAMIC_DIR}/sensitivity.html',
            movie=f'{PHYLODYNAMIC_DIR}/primary_movie.json',
            comparison=f'{PHYLODYNAMIC_DIR}/comparison.html',
            comparison_assets=directory(f'{PHYLODYNAMIC_DIR}/comparison_assets')
        run:
            from phylodynamic_summary import summarize
            summarize(Path(PHYLODYNAMIC_SELECTION), Path(PHYLODYNAMIC_DIR)/'inference', Path(PHYLODYNAMIC_DIR))
    
# Independent opt-in dating of saved rooted topologies.
include: "bayesian_dating.smk"

include: "posterior_phylogeography.smk"

include: "phylogeography_results.smk"
