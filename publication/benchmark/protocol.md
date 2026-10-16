# WINGS comparative validation protocol

Status: prospective protocol. Complete and freeze the manifests before inspecting comparative outcomes.

## Objective and primary claim

Test whether WINGS produces accurate, reproducible influenza A segment consensuses from Oxford Nanopore reads while adding traceable QC, provenance, linked genomic context, and reviewable reports. Accuracy and completeness are primary. Reporting and provenance are evaluated separately; they must not be presented as evidence of better consensus accuracy.

The unit of biological replication is the sample. Segment observations are clustered within samples and are not treated as independent biological replicates.

## Cohorts

1. **Analytical truth cohort.** Nanopore FASTQ from independently characterized influenza A material with a prespecified truth sequence. Prefer matched Illumina-derived consensus or a characterized isolate reference generated independently of WINGS. Record discordant or unresolved truth rather than adjudicating it after seeing WINGS results.
2. **External validation cohort.** Public Nanopore influenza A reads selected by a reproducible search and frozen before running any compared workflow. No sample may have contributed to WINGS development, parameter tuning, or demonstration data.
3. **Real-world case cohort.** The existing wild-bird sequencing run demonstrates workflow behavior, missingness, ecological context, and report utility. It is not an independent accuracy cohort unless it has orthogonal truth.
4. **Negative and mixture controls.** Include available negatives and mixtures. Analyze them descriptively unless their composition and expected proportions are independently known.

Create one row per dataset in `datasets.tsv` using `datasets.template.tsv`. Create a separate input manifest containing one row per FASTQ with sample ID, path or accession, byte size, and SHA-256.

## Comparators

| Tool | Role | Inclusion rule |
| --- | --- | --- |
| WINGS frozen release | Evaluated workflow | Required |
| ONT `wf-flu` frozen release/container | Primary end-to-end comparator | Required when the cohort matches its documented amplified-influenza input scope |
| IRMA, matching WINGS module/version | Component baseline | Required; isolates the contribution of WINGS processing and polishing around IRMA |
| FluViewer or fluviewer-nf | Sensitivity comparator | Include only after a documented pilot confirms that the same Nanopore inputs and scientific endpoints are supported without workflow-specific preprocessing that advantages one method |

Pin every workflow by immutable commit, release, and container digest where available. Preserve commands, configuration, logs, failures, and outputs from every attempted run. Do not silently retry with changed parameters; record a new attempt.

## Prespecified endpoints

### Primary analytical endpoints

For each biological sample, summarize across the eight influenza A segments:

- complete, QC-qualified segments recovered out of eight;
- total callable truth positions;
- consensus nucleotide errors per 10,000 callable bases;
- whole-segment exact-match count;
- segment consensus identity to truth;
- false-negative segment count.

The primary paired comparison is the sample-level difference between WINGS and `wf-flu` in complete segments recovered. The co-primary accuracy measure is the sample-level difference in errors per 10,000 callable truth bases. Report paired estimates and 95% bootstrap confidence intervals resampling biological samples. Report the full distribution and denominators. Do not substitute segment count for sample count.

### Secondary endpoints

- subtype agreement with independent truth;
- genotype agreement when an independent genotype label exists;
- insertion, deletion, and substitution errors separately;
- N fraction and callable breadth;
- low-input performance by prespecified read-count or depth strata;
- successful runs, failed runs, retries, and failure categories;
- wall-clock time and peak whole-workflow resident memory under controlled conditions;
- cross-platform scientific equivalence and byte-identical artifact counts;
- provenance completeness and replay success;
- user task accuracy, completion time, and help requests for the reporting layer.

Variant precision/recall is reported only where an independently established variant truth set exists. Consensus agreement between two pipelines is not variant truth.

## Acceptance criteria

Freeze numeric thresholds before the first comparative result is inspected. At minimum, the frozen analysis plan must specify:

- the largest acceptable loss in complete segments per sample;
- the largest acceptable increase in errors per 10,000 callable bases;
- minimum acceptable subtype agreement;
- the definition of a successful replay;
- permissible cross-platform output differences;
- handling of samples with no callable truth positions.

A suggested starting point for collaborator review is non-inferiority margins of 0.5 segment per sample and 1 consensus error per 10,000 callable bases. These are placeholders, not validated scientific thresholds, and must be justified or replaced before freezing the protocol.

## Execution design

Run all tools on identical immutable FASTQ inputs. Use default recommended settings first, followed only by prespecified sensitivity analyses. Randomize tool execution order when shared host load could matter. For performance measurements, use an otherwise idle host, cold and warm cache conditions as separate strata, and at least three executions per tool-dataset combination. Record the host, operating system, CPU architecture, logical CPU limit, task concurrency, total memory budget, storage, container runtime, image digest, and measurement boundaries.

Docker monitoring measures containers only. WINGS also uses native Conda processes, so whole-workflow peak memory requires host-level process-tree measurement. Do not add peaks from sequential stages. Keep sampled Docker statistics as diagnostic evidence rather than the primary whole-workflow memory measure.

## Statistical analysis

Report paired sample-level effects with uncertainty. Use a cluster bootstrap over biological samples for descriptive confidence intervals. If formal non-inferiority testing is retained, specify the margin, sidedness, alpha, missing-data rule, and multiplicity strategy before analysis. Stratified results are secondary unless powered and prespecified. Failed runs remain failures; they are not removed from denominators because a later retry succeeds.

For ecological and genomic concordance, maintain exploratory labeling until assumptions and estimability have been independently reviewed. Co-occurrence does not establish transmission.

## Reproducibility and blinding

Freeze the release commit, dataset manifests, truth files, comparator versions, commands, and analysis script before execution. Where feasible, hide tool identity from the person adjudicating sequence discrepancies. Keep raw outputs immutable and derive normalized comparison files with versioned scripts. A second analyst should reproduce the summary tables from the archived inputs without access to the first analyst's working directory.

## Required outputs

- `datasets.tsv` and per-dataset FASTQ manifests;
- `attempts.tsv` containing every attempted workflow execution;
- `segment_results.tsv` containing one row per sample, segment, tool, and attempt;
- `environments/` with version and digest records;
- original logs and raw workflow outputs;
- a frozen analysis plan with final margins;
- discrepancy/adjudication records;
- independent reproduction record;
- final claim-to-evidence table.
