# Shared Fast / BEAST phylogeography results

Fast conditional geographic reconstruction is the default. One results page provides a linked map, dated WINGS tree, directed Markov-jump chord diagram, ancestor-location probabilities, entry timeline, and reference-sampling sensitivity table. The same page displays completed BEAST posterior results when available and verified.

## Build from existing WINGS results

Use the dedicated report-only entry point from the WINGS repository. It has no sequencing, reference-selection, inference or BEAST producer rules, and always enforces saved-input mode even if the configuration requests otherwise.

```bash
snakemake --snakefile Snakefile.phylogeography-report \
  --configfile config.yaml config/phylogeography-results.example.yaml \
  --use-conda --cores 4 --dry-run
```

Then run the same command without `--dry-run`. Only `phylogeography_results_preflight`, `phylogeography_results_fast`, `phylogeography_results` and the aggregate `all` target can be scheduled. Do not use the main Snakefile to rebuild this report from saved inputs.

Then:

```bash
open results/run_summary/phylodynamics/results/fast_v1/index.html
```

Add `--dry-run` to inspect the DAG. The example sets `saved_inputs_only: true`: the report reads existing analyses without declaring dependencies on upstream inference, reference selection or BEAST rules. This isolation does not rely on `--allowed-rules`, which is insufficient for this project’s checkpoint workflow. The standalone entry point never loads the main Snakefile. File hashes are recorded as rule parameters so saved-source changes trigger a refresh under the default rerun settings. Keep the default rerun triggers; do not restrict them to modification time.

In saved-input mode, an empty `analyses` list uses every replicate in `selection/selection_summary.json`, preserving its order and including blocked or missing analyses as unavailable. It does not expand the cohort from newer configuration settings or select only successful results. If the saved summary is absent or malformed, the workflow stops with a clear error; an explicit analysis list can identify an older exported cohort.

For a fresh complete WINGS workflow, use `saved_inputs_only: false` (the code default), omit the allowed-rule restriction, and enable phylodynamics. That mode uses the current configured cohort and connects to upstream rules normally. The report is added to full-workflow targets when phylodynamics is enabled.

The example overlay disables the independent BEAST-dating and posterior-mapping workflows for this invocation. It does not alter a job that is already running in another terminal, and the installer does not edit existing chains, config.yaml, the posterior checker, or its fingerprinted scripts. Stopping an already-running mapping job is optional; its unfinished mappings are not checkpointed by the previous implementation, while the completed BEAST chains remain saved.

## Method selection

- **Fast:** fixed dated ML tree, conditional Bayesian geographic histories. Matching completed histories are reused. Default: 600 histories with the source Gamma prior. There is no MCMC ESS for these direct conditional geographic draws.
- **BEAST:** dated-tree posterior propagation produced by the existing checked posterior workflow. The report verifies publication/gate hashes, source fingerprints, diagnostic thresholds, complete WINGS cohorts and equal weighting across independent chains. Unavailable or failed BEAST results are shown as unavailable; the page never substitutes fast results for a requested BEAST analysis.

The Fast/BEAST buttons change the displayed analysis. They do not launch external programs from the browser. The existing BEAST MCMC and posterior-propagation commands remain the opt-in analysis path.

Default BEAST source: `bayesian/<analysis>/long20m/posterior/posterior_5k/publication`. Set `dating_run` and `posterior_run` under `phylogeography_results` to select another completed run. After BEAST finishes, rerun the report command. If necessary, force only the report stage with `--forcerun phylogeography_results`.

Set `method: beast` to initially display BEAST. Missing results remain visibly unavailable. Set `include_beast: false` to omit BEAST reading entirely. A nonempty `analyses` list selects exact IDs; requested missing analyses are shown as unavailable. With an empty list, saved-input mode uses the saved selection cohort and full-workflow mode uses the current `phylodynamics` configuration. The first configured analysis is the default; a failed primary is never replaced by a more favorable replicate.

## What the views summarize

- **Posterior summary** is the default. Tree-node pies and the ancestor-location bars show marginal probabilities across all sampled histories, including zero-jump histories. Node dates are fixed in Fast mode and medians of displayed dated-tree draws in BEAST mode.
- **Sampled history** shows one coherent realization with its own node dates and geographic changes. This is not a highest-likelihood or uniquely best history. The chord diagram, probability bars and uncertainty timeline still summarize all histories and are labeled accordingly.
- The time slider controls accumulated map routes, chord counts, tree timing and the timeline cursor. The overview cards and reference table summarize the full study ancestry.
- Map arcs show up to 12 strongest routes involving the selected location. Chord ribbons include all sampled directed routes; their width is posterior mean jump count through the selected date. Hover shows a discrete equal-tailed 95% interval and the sampled probability of at least one jump.
- Counts begin at the WINGS common ancestor. The ancestral stem and reference-only branches are excluded from the counts and displayed ancestry. Geography is fitted using the full reference tree before this restriction.
- All WINGS tips remain in a scrollable tree. Gold marks WINGS samples; clicking an internal node selects its location-probability distribution.
- Fast TMRCA is labeled a point estimate, with dates held fixed. The report does not invent a date interval. BEAST TMRCA and its 95% HPD come from the checked full dating posterior.
- Replicates are displayed separately, not pooled. Missing locations and missing analyses are not reported as zero entries.

The model remains a symmetric equal-rate CTMC, with one off-diagonal rate and a uniform root-location prior. The directed chord counts do not establish asymmetric transition rates. Recorded locations, not physical distances, enter the model. Neither current method samples tree topology uncertainty.

## Configurable geographic priors

Default:

```yaml
geographic_prior:
  family: source
```

This preserves the source model and can reuse its completed histories. To change the fast geographic prior, specify `gamma` or `lognormal` and choose `pair_rate` or `exit_rate`. The total exit rate is `(K-1) × pair_rate`, where K is the number of locations. Using an exit-rate prior preserves its overall movement scale when K changes.

Illustrative lognormal sensitivity configuration:

```yaml
phylogeography_results:
  run_id: fast_lognormal
  geographic_prior:
    family: lognormal
    parameter: exit_rate
    median: 1.0
    log_sd: 1.0
```

These numbers are an example, not a validated default for WINGS. The supplied `config/phylogeography-results.lognormal.example.yaml` can be merged after the main report overlay. Use `results/.../results/fast_lognormal/index.html` as the target. The new model remaps geography on the existing full dated tree; it does not relabel old histories or rerun dating. Gamma takes `shape` and `rate`; lognormal takes `median` and natural-log standard deviation `log_sd`.

These prior overrides apply to **fast mapping**. Existing BEAST publications retain their actual geographic prior. The report states when the two displayed methods use different priors. This update does not change or invalidate a running BEAST propagation job. Use separately labeled runs to assess prior sensitivity; do not silently change a prior to force a desired reconstruction.

## Checks

A lightweight numerical preflight runs before fast processing. It verifies rate integration against analytical Gamma/lognormal expectations, exit-rate normalization, history continuity, study-ancestry restriction, zero-history accounting, blocked analyses, and source tampering.

Fast publication requires a complete screened source reconstruction; matching ML tree/temporal-screen hashes, tip metadata, saved counts and selection provenance; valid conditional histories; rate-quadrature convergence; and Monte Carlo precision. Default limits are mean-count MCSE ≤ 0.15 and probability MCSE ≤ 0.025. These may be tightened but not loosened. At probability boundaries, a one-sided unseen-event bound is used instead of claiming zero Monte Carlo uncertainty. Constant sampled counts are labeled and are not proof of a point mass.

If Fast is withheld for precision, increase `histories` (400–10000) in a new run ID. The rate integral is computed once for the dated tree, then new geographic histories are drawn. Failed temporal checks require addressing the underlying dating inputs/model, not changing the report threshold. A blocked replicate is represented by a diagnostic record, so the page can show its unavailable status alongside other explicitly selected replicates.

BEAST retains the existing R-hat/ESS, internal-node date, date-precision and mapping-precision requirements. This report never relaxes or reruns those checks silently.

## Validation

The supplied numerical/structural Python tests and JavaScript tests run at installation. When Snakemake is available, the installer runs an isolated synthetic workflow regression with six saved analyses, nine configured analyses, an upstream checkpoint and inference/publication rules that fail if accidentally executed. It checks both dry runs and actual report generation, preserves unavailable replicates, verifies that changed saved inputs trigger a refresh, and builds through the standalone entry point with a deliberately invalid main Snakefile. Only the three report rules and aggregate target may be registered. Snakemake could not be installed in this development environment; this regression runs in the user's Snakemake environment before installation. It does not run biological analyses. Browser checks used synthetic 30-tip data and exercised Fast/BEAST switching, all study tips, chord rendering, playback, location selection, unavailable-method handling and mobile overflow. No new biological analysis was run during development.
