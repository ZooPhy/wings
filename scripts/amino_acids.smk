# Consensus amino acid comparison; all data dependencies are declared to Snakemake.
rule amino_acids_sample:
    input:
        consensus=lambda wc: [f"{RESULTS}/{wc.sample}/medaka/{s}/consensus.fasta" for s in segments_for_sample(wc)] if AA_ENABLED and RUN_VADR else [],
        vadr=lambda wc: [f"{RESULTS}/{wc.sample}/vadr/output", f"{RESULTS}/{wc.sample}/vadr/{wc.sample}.vadr.done"] if AA_ENABLED and RUN_VADR else [],
        panel=[AA_PANEL] if Path(AA_PANEL).is_file() else [],
        evidence=AA_EVIDENCE,
        script="scripts/wings_amino_acids.py"
    output:
        json=f"{RESULTS}/{{sample}}/amino_acids/changes.json"
    params:
        enabled=int(AA_ENABLED),
        vadr=lambda wc: ("--vadr-dir " + shlex.quote(f"{RESULTS}/{wc.sample}/vadr/output")) if RUN_VADR else "",
        panel=("--panel " + shlex.quote(AA_PANEL)) if Path(AA_PANEL).is_file() else "",
        identity=AA_MIN_IDENTITY,
        coverage=AA_MIN_COVERAGE,
        consensus=lambda wc, input: " ".join("--consensus " + shlex.quote(Path(p).parent.name) + " " + shlex.quote(str(p)) for p in input.consensus)
    conda:
        "../envs/py-tools.yaml"
    shell:
        "python {input.script:q} analyze --sample {wildcards.sample:q} --enabled {params.enabled} --evidence {input.evidence:q} --min-identity {params.identity} --min-coverage {params.coverage} --output {output.json:q} {params.vadr} {params.panel} {params.consensus}"

rule amino_acids_report:
    input:
        samples=expand(f"{RESULTS}/{{sample}}/amino_acids/changes.json", sample=SAMPLES),
        script="scripts/wings_amino_acids.py",
        visual="scripts/amino_acid_visual_report.py",
        visual_assets=["scripts/report/amino-acid-visual.js", "scripts/report/amino-acid-visual.css"]
    output:
        html=f"{RESULTS}/run_summary/amino_acids/report.html",
        tsv=f"{RESULTS}/run_summary/amino_acids/changes.tsv",
        json=f"{RESULTS}/run_summary/amino_acids/changes.json"
    conda:
        "../envs/py-tools.yaml"
    shell:
        "python {input.script:q} report --inputs {input.samples:q} --html {output.html:q} --tsv {output.tsv:q} --json {output.json:q}"
