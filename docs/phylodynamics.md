# Reference retrieval and conditional geographic inference

WINGS now supports metadata-driven NCBI retrieval and segment-specific references.
**HA analysis does not require complete influenza genomes or public GenoFLU calls.**
Read the [sampling protocol and literature review](phylodynamic-sampling-protocol.md)
for evidence, design choices, estimands and benchmark limits.

For the HA clade-screening update and targeted rerun, see
[Clade update](phylodynamics-clade-update.md).

## Start with automatic NCBI references

The example overlay keeps your main configuration and disables the separate old
complete-genome contextual-reference pipeline. That old pipeline would otherwise
continue requesting the obsolete `H5Nx_sequences.fasta` path.

```bash
export NCBI_EMAIL="your-email@example.org"
snakemake --configfile config.yaml config/phylodynamics.example.yaml --use-conda --cores 8 --dry-run
snakemake --configfile config.yaml config/phylodynamics.example.yaml --use-conda --cores 8
```

Set `NCBI_API_KEY` in your shell if available; it is optional. Never commit it.
Review the example before running: it requests HA from H5Nx isolates, global
context and the study collection interval extended by 730 days before and 90 days
after. These windows and caps are adjustable engineering settings, not optimized
scientific defaults. `countries: []` means global; an explicit country list narrows
it. To retain the legacy contextual trees as well, remove the overlay's
`public_references` block and configure that separate workflow correctly.

The existing Snakefile include now creates a reference snapshot, selections,
replicate inference and sensitivity outputs. No additional main-Snakefile edit
is needed. The feature remains disabled when `phylodynamics.enabled` is absent.
It does not require `run_genoflu` or `public_references.enabled`.

For a persistent configuration, merge the example into your main `config.yaml`.
Do not add a second duplicate `phylodynamics:` YAML key. The installer does not
rewrite your main configuration.

## Use your existing downloaded HA files instead

Change only the `references` block:

```yaml
references:
  source: local
  subtypes: [H5]
  source_fasta: resources/phylodynamics/phylodynamics_sequences.fasta
  source_metadata: resources/phylodynamics/phylodynamics_sequences.tsv
```

Tab-separated and comma-separated exports are accepted. An unversioned metadata
accession is joined only when it has one unambiguous versioned FASTA match.
An explicit `segment 4` FASTA description can supply HA when the export has no
Segment column. Conflicting/missing annotations are excluded and audited.
Missing metadata, ambiguous accession matches and duplicate accession rows fail.
The new route does not alter the older public-reference importer.

## Retrieval and audit

NCBI queries retrieve all matching versioned records in paced batches. The
candidate frame is frozen by `references.snapshot` and query. Raw XML and hashes
are cached outside Snakemake's disposable output directory. Interrupted downloads
reuse completed batches. Set `offline: true` to require an existing complete
cache. Change the snapshot name deliberately to refresh the accession universe.
Avoid simultaneous workflows sharing the same cache/contact API quota.

Collection dates, not release dates, define eligibility. Exact recorded dates
are required for the current dating method. Missing/partial dates remain in the
exclusion audit. Broad subtype/segment annotation is not a clade assignment.
The full GenBank records are downloaded before local date/geography filtering;
large global queries may take time. The first-N truncation of a candidate pool is
never used. `max_records` aborts an unexpectedly large query.

US and Canadian references need resolvable state/province qualifiers. Other
countries use explicitly labeled country-level states in the bundled map.
Unknown countries and missing North American administrative units are excluded.
Inspect this mixed geographic resolution for your question. `requested_locations`
can block inference when required places are absent; it does not invent observations.

## Selection and inference

- Classify study/candidate H5 HA sequences with a frozen Nextclade all-clades
  dataset. Require one usable study clade; other segments and mixed study clades
  block pending a separate analysis policy. No genetic-distance cutoff is used.
- Reserve two nearest clade-eligible references per study sample.
- Keep eligible study tips fixed; balance combined location/time counts, with
  seeded random selection without replacement.
- Compare balanced sampling with random available-pool and optional diversity
  sampling. `time_bin` supports month, quarter and year.
- Preserve identical sequences from distinct specimens. Collapse only explicit
  duplicate specimen/sequence records with agreeing date/location/host.
- Report all exclusions, coverage, combined composition and unfillable imbalance.
- Run MAFFT, IQ-TREE 2 and TreeTime separately for each segment and replicate.
- Infer geographic histories using a symmetric equal-rates CTMC on the fixed
  dated tree. Integrate a Gamma-prior rate by quadrature, then sample conditional
  ancestral states and Markov bridges. This avoids tree MCMC; it is not a full
  Bayesian tree analysis, structured coalescent or epidemic model.
- Require positive rate/R² and root-optimized tip and same-date-clade permutation
  diagnostics on the unconstrained ML tree, plus the existing TreeTime screen.
  This is not a Bayesian rate-interval DRT. Tree/clock uncertainty is not integrated.

For K modeled locations, each off-diagonal rate is q; total exit rate is (K−1)q.
The root prior is uniform over observed locations. The default q prior is
Gamma(shape=1, rate=1) per year. Its total exit-rate implications change with K.
Zero-jump histories and repeated entries/reversals remain in the outputs.

Main entry counts refer to the ancestry from the study-sample MRCA to the same
study tips. They exclude its ancestral stem and do not estimate all epidemic
introductions. Whole-tree jump means are separate audit outputs. A count summary
requires two study tips. Replicate posteriors remain separate; a range of means
is sensitivity, not a pooled interval. The predeclared primary is balanced
replicate 1 (or the first configured strategy if balanced is absent).

## Outputs

Under `results/run_summary/phylodynamics/`:

| Path | Contents |
|---|---|
| `references/provenance.json` | Study-derived scope, query, source counts, hashes |
| `references/references.tsv`, `.fasta` | Normalized segment candidates |
| `references/excluded.tsv` | Source/annotation/date/geography exclusions |
| `selection/selection_summary.json` | Combined composition, gaps, quotas, replicate status |
| `selection/HA/lineage/` | Frozen dataset provenance, all clade calls, exclusions and nearest-reference audit |
| `selection/HA/eligible.tsv`, `excluded.tsv`, `coverage.tsv` | QC and eligibility audit |
| `selection/HA/STRATEGY/replicate_N/` | Selected FASTA, tips and decisions |
| `inference/HA/STRATEGY/replicate_N/` | Alignment, trees, diagnostics, conditional counts and movie |
| `sensitivity.html`, `summary.json` | Separate replicate results |
| `primary_movie.json` | Predeclared primary reconstruction embedded in the explorer |

## Verification

```bash
python -m unittest discover -s tests -p 'test_phylodynamics*.py' -v
node --test tests/test_phylogeography_movie.cjs
python tests/check_phylodynamics_workflow.py
python tests/check_phylodynamics_ncbi.py
python scripts/phylodynamic_benchmark.py --output results/reference-benchmark
```

The live NCBI check uses two small requests and requires `NCBI_EMAIL`; it does not
run the biological analysis. Set `WINGS_TEST_PHYLODYNAMIC_TOOLS=1` for the real
MAFFT/IQ-TREE/TreeTime integration test when their environment is available.
The dedicated CI workflow checks Snakemake 8 and 9. Review the bundled
[verification record](phylodynamics-verification.md) for checks actually completed
when this update was prepared. Small simulation smoke runs do not validate quotas.

Per-replicate `temporal_diagnostics.json` and `clock_points.tsv` report raw-ML
regression, root optimization, permutation draws, clusters and failure reasons.
