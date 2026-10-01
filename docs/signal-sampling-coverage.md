# Signal-or-Sampling and Coverage lens

WINGS can optionally display surveillance-effort denominators alongside the genomic records already produced by the workflow. The goal is descriptive surveillance interpretation: show how observed detections and genomic recovery relate to the amount of sampling performed.

## Data contract

Configure a tab-delimited file with one aggregate surveillance record per time/geography/host stratum. Required columns are `period_start` and `period_end` (ISO dates, `YYYY-MM-DD`). Optional stratifiers are `state`, `county`, and `host`. Count columns are `sampled`, `tested`, `positive`, and `sequenced`; blanks or `NA` mean unavailable, while `0` is a real zero. `source` and `notes` are optional provenance fields.

Counts must be non-negative integers. When both values are available, WINGS checks `tested <= sampled` and `positive <= tested`. WINGS deliberately does not assume that `sequenced` must be a subset of `positive`, because surveillance programs define sequencing effort differently.

Example configuration:

```yaml
surveillance_effort:
  enabled: true
  file: resources/surveillance_effort.tsv
```

Copy `config/surveillance-effort.example.tsv` to a project-specific path and replace the example values with program data. Do not fabricate missing denominators.

## Coverage lens

The Coverage tab separates two kinds of information:

1. **External surveillance effort** — sampled, tested, positive, and sequenced counts supplied by the surveillance program.
2. **WINGS genomic coverage** — records entering this WINGS run, records with at least one QC-passing influenza segment, complete eight-segment genomes, and subtype-resolved records.

These are not automatically treated as one continuous funnel because the external surveillance totals and the WINGS run may represent different inclusion windows or transfer processes.

## Signal-or-Sampling diagnostic

When at least two dated periods contain both tested and positive counts, the portal compares the two most recent periods. It reports changes in tested specimens, positive detections, and positivity. The language is descriptive (for example, detections increased faster than testing) and does not infer causation, transmission intensity, prevalence, or a biological mechanism.

If a denominator is unavailable, WINGS states that explicitly rather than computing a rate from positive genomes alone.

## Interpretation limits

The Coverage lens is a denominator-awareness tool, not a formal surveillance model. Differences in host mix, geography, sampling design, laboratory criteria, submission practices, and sequencing eligibility can all affect observed counts. A later modeling layer can add binomial or count-regression methods once those design variables are represented consistently.
