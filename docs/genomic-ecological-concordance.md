# Genomic-Ecological Concordance research module (v0.3)

WINGS automatically asks whether host identity, species-level seasonal ecology,
and local environmental context add explanatory value for **segment-specific
genomic relatedness** beyond simpler spatiotemporal models. Ordinary users do
not build pairwise tables, select predictors, or choose a statistical test.

This is an exploratory association analysis. It does **not** infer direct
transmission, infection source, migration-mediated transmission, reassortment,
or causality.

## Automatic model hierarchy

For every influenza segment, WINGS uses local samples that map to exactly one
tip in that segment tree. The response is patristic distance (the summed branch
length between two sample tips). It fits the same pre-specified hierarchy for
every segment:

1. **M0 - Spatiotemporal:** collection-date separation + geographic distance.
2. **M1 - Host:** M0 + same/different host.
3. **M2 - Ecology:** M1 + eBird Status & Trends seasonal-profile distance.
4. **M3 - Environment:** M2 + multivariate ERA5 environmental distance.

The primary ecology comparison is `M2 vs M1`: does seasonal ecological
connectivity add information beyond time, geography, and host identity? The
environment comparison is `M3 vs M2`.

## Seasonal ecological distance

When both samples have an eBird Status & Trends Ecological Clock profile, WINGS
calculates `1 - Pearson correlation` across jointly available weekly relative-
abundance values. Lower values indicate more similar annual seasonal shapes.
At least 26 jointly available weeks and non-flat profiles are required. Missing
values are not imputed.

## Environment without opportunistic variable selection

For each sample with ERA5 data, WINGS summarizes the seven calendar days
centered on collection date (collection date +/- 3 days):

- mean 2 m temperature (C),
- total precipitation (mm), and
- mean daily maximum 10 m wind speed (km/h).

The three sample-level summaries are standardized across WINGS samples with
complete weather data. Pairwise **environmental distance** is Euclidean distance
between the resulting three-dimensional z-score vectors. Individual weather
differences remain in `pairs.tsv` for transparency, but the inferential model
uses the single pre-specified environmental-distance term. A weather dimension
with no variation contributes zero rather than being selected or dropped ad
hoc.

If environmental distance is still linearly dependent on predictors already in
M2, WINGS does not force a coefficient. The machine result retains the rank
diagnostic and the report displays **Not independently estimable**.

## Pair dependence, permutation inference, and FDR

Pairs are not independent biological observations because each sample appears
in multiple pairs. WINGS therefore does not report ordinary OLS p-values. For
each nested comparison it uses a Freedman-Lane-style sample-label permutation:
fit the reduced model, arrange its dyadic residuals by sample pair, permute
sample labels on that residual matrix, add the permuted residuals back to the
reduced fitted values, and recalculate the increment in R-squared.

The empirical one-sided p-value is the fraction of valid permutations whose
increment in R-squared is at least as large as observed, using a +1 correction.
WINGS then applies Benjamini-Hochberg FDR correction **within each comparison
family across influenza segments**.

Readiness is gated by the number of unique samples, not pair count alone. The
default minimum is eight unique samples for a comparison. This is an automated
exploratory guardrail, not a claim that eight samples provides high statistical
power.

## Zero-configuration behavior

When the module is installed, it is enabled automatically for ordinary WINGS
runs that produce the Surveillance Explorer and phylogenies. Defaults are fixed
by WINGS: 999 permutations, deterministic seed, eight-sample minimum, and the
model hierarchy above.

If an ecological weather snapshot is already enabled in WINGS, the module uses
it. Otherwise it automatically creates a run-specific ERA5 snapshot using the
validated metadata. Only coordinates and date windows are sent to the
Open-Meteo Historical Weather API; sample identifiers, hosts, reads, and
sequences are not sent. Samples lacking coordinates remain unavailable rather
than receiving a centroid or zero.

For eBird Status & Trends phenology, WINGS uses profiles already embedded in the
Explorer. If profiles are not embedded but an existing run-level phenology file
is present, it is used. If `EBIRDST_ACCESS_KEY` is available, WINGS can build the
standard phenology output automatically with existing WINGS defaults. Without
an available profile source, host and spatiotemporal tiers can still run, while
the seasonal-ecology comparison reports unavailable rather than guessing.

Advanced users can opt out or override computational defaults, but ordinary
users do not need a `genomic_ecological_concordance` block in `config.yaml`.

## Report integration

v0.3 adds a **Concordance** tab to the WINGS Surveillance Explorer. The report
shows:

- total samples, phenology availability, ERA5 availability, distinct weather
  contexts, and the automatic minimum-sample guardrail;
- the fixed M0 -> M1 -> M2 -> M3 hierarchy;
- segment-specific incremental R-squared, permutation p-values, FDR q-values,
  unique sample counts, and pair counts;
- plain-language availability diagnostics such as **Too few unique samples** or
  **Not independently estimable**; and
- interpretation guardrails explaining that concordance does not establish
  transmission or causality.

The report receives a compact copy of the model results. The large pairwise
and sample-feature tables are **not** embedded into the Explorer payload.

## Outputs

The module writes:

- `results/run_summary/concordance/sample_features.tsv` - derived sample-level context
- `results/run_summary/concordance/pairs.tsv` - pairwise response and predictors
- `results/run_summary/concordance/models.tsv` - nested comparisons, permutation p-values, FDR q-values, and report-facing diagnostics
- `results/run_summary/concordance/concordance.json` - complete machine-readable result and provenance
- `results/run_summary/surveillance_explorer.concordance.json` - compact Explorer payload used by the run report

The output explicitly reports unique sample count and pair count for every
segment/comparison.

## Interpretation-first report (v0.3.1)

The Concordance tab now leads with **What this run suggests**, a plain-language summary generated from the run's model statuses and FDR-adjusted results. It reports the host, seasonal-ecology, and weather findings before the model ladder and detailed segment table. The summary never interprets concordance as transmission or causation.

Data-availability cards use novice-facing labels: **Seasonal ecology data**, **Samples with weather data**, and **Distinct weather settings**. ERA5 is described as the source of temperature, precipitation, and wind rather than used as an unexplained card label. Technical rank diagnostics remain available under a disclosure in the detailed table.
