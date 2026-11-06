from pathlib import Path
rule context_phenology:
    input:
        metadata=lambda wildcards: config['metadata'],
        script=lambda wildcards: str(Path(config['repo']) / 'scripts/build_ebirdst_phenology.py'),
        hosts=lambda wildcards: str(Path(config['repo']) / 'resources/ebird_host_codes_2025.tsv')
    output:
        config['output']
    params:
        cache=lambda wildcards: config['cache'],
        year=lambda wildcards: int(config['year'])
    conda:
        '../envs/phenology.yaml'
    shell:
        'python {input.script:q} --metadata {input.metadata:q} --host-map {input.hosts:q} --output {output:q} --cache-dir {params.cache:q} --version-year {params.year}'
