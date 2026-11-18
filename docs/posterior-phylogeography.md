# Posterior dates and geographic histories

This optional workflow reuses completed BEAST `chain.log` and `chain.trees` files. It does not rerun, resume, shorten, or modify BEAST chains. Its standalone movie shows the WINGS common ancestor, all WINGS tips, a coherent sampled geographic history, and cumulative entry intervals across dated-tree draws.

## Run

From the WINGS repository, after installing the updater:

```bash
snakemake results/run_summary/phylodynamics/bayesian/HA/balanced/replicate_1/long20m/posterior/posterior_v1/publication/movie.html \
  --configfile config.yaml config/posterior-phylogeography.example.yaml \
  --use-conda --cores 4 \
  --allowed-rules \
    posterior_phylogeography_preflight \
    posterior_phylogeography_gate \
    posterior_phylogeography_map \
    posterior_phylogeography_publish
```

Add `--dry-run` to inspect the four-stage DAG first. The rules are included from `rules/bayesian_dating.smk`, already included by the existing phylodynamics workflow. No main Snakefile replacement is needed.

When successful, on macOS:

```bash
open results/run_summary/phylodynamics/bayesian/HA/balanced/replicate_1/long20m/posterior/posterior_v1/publication/movie.html
```

The existing TreeTime comparison/movie remains a separate analysis. Open this new posterior movie to see the propagated Bayesian dating uncertainty. It is self-contained and works offline; adjacent JSON links provide diagnostic and downloadable data files.

## Gates

1. **Preflight:** numerical regression tests must run with ArviZ; skipped numerical tests are a failure. The dedicated Conda environment needs no Java or BEAST installation.
2. **Dating gate:** completed independent chains, matching files and hashes, complete matching trace/tree states, fixed rooted splits, collection dates, reference selection, and observed geographic states are required. Prior-only runs are rejected.
3. **Convergence:** recompute rank-normalized split R-hat, bulk ESS, tail ESS, and per-chain bulk ESS for every logged parameter, WINGS TMRCA, reference root date, and every internal-node date. Repeat these checks for the subset of trees used for mapping.
4. **Date precision:** mean-date MCSE at most 7 days and approximate HPD-endpoint MCSE at most 14 days for WINGS TMRCA and the reference root. HPD endpoint errors use 250 circular moving-block bootstrap replicates, separately within each chain; block length is at least twice the largest estimated mean/tail autocorrelation time. This is a Monte Carlo precision check, not an additional posterior interval.
5. **Mapping/publication:** each dated tree must have a converged rate quadrature and a valid complete conditional history. Geographic rate draws and variable entry counts must meet the same convergence/ESS thresholds. Entry-mean MCSE must be at most 0.15 entries; zero-entry and interval-tail probability MCSE at most 0.025.

Default hard floors are R-hat ≤ 1.01, bulk and tail ESS ≥ 400, and per-chain bulk ESS ≥ 100. A stricter original dating configuration remains binding. Configuration may tighten thresholds, not loosen them.

A constant sampled count is explicitly marked as such: no fabricated ESS or zero MCSE is reported. Boundary probabilities receive an approximate one-sided 95% unseen-event bound using the smaller of the draw count and the minimum selected-date ESS. This effective-sample-size approximation does not prove the absence of rare events or establish a true point mass. All zero-event histories remain in denominators.

A failed gate exits nonzero and creates no success token. Starting validation or mapping invalidates that run's older publication. Failed publication removes its movie data and replaces the HTML with a withheld-results page. Independently downloaded older HTML files remain historical snapshots and cannot be revoked.

## If blocked

Read `gate/diagnostics.json`, `mapping/mapping_status.json`, or `publication/diagnostics.json` under the posterior run directory.

- **Full-chain ESS/R-hat failure:** inspect chain traces and model behavior; obtain sufficiently long, well-mixed independent dating chains. Choose a new dating run ID and preserve the old chains. This workflow never extends them automatically.
- **Only selected-tree ESS failure:** increase `trees_per_chain` and use a new posterior `run_id`. The default is 1,000 distinct post-burn-in draws per chain. There is no replacement sampling or duplication to inflate ESS. At most 10,000 per chain are supported, and the requested number must exist.
- **Mapping precision failure:** use more distinct dated trees, with a new posterior run ID. Additional mappings alone cannot repair poor dating-chain mixing.
- **Hash, topology, or taxon mismatch:** restore the corresponding original input set or create a new consistent analysis. Never delete the checks to force publication.
- **Prior/model sensitivity:** passing these checks does not validate the clock, coalescent, geographic model, root, reference sample, or reference-sampling design. Compare those assumptions in separately labeled analyses. Do not pool different reference replicates into one posterior.

## Statistical scope

This is a **two-stage (modular) analysis**, not joint BEAST phylogeography:

- Draw dated trees from the BEAST dating posterior, conditional on the fixed rooted ML topology, selected references, substitution/clock/coalescent model, and priors.
- For each distinct selected tree, integrate the symmetric equal-rate geographic CTMC's Gamma-prior transition rate by quadrature. Draw one conditional geographic history using stochastic bridges. The root-state prior is uniform over observed locations. Geography does not feed back into the dating posterior.
- Use equal numbers of randomly selected, distinct trees per chain, sorted in MCMC order for diagnostics. Each tree/history has equal weight. There is one history per tree, so repeated histories on a single tree cannot inflate the dating sample size.
- Fit geography on the full selected reference tree. Display and count only branches on the WINGS samples' ancestry, starting at their MRCA. Exclude the ancestral stem and reference-only branches. Count re-entries separately.
- Every movie history retains its own node and event dates. Median dates are never substituted into sampled histories. The TMRCA card uses the full retained dating posterior; geography uses the checked selected subset. Entry intervals are discrete equal-tailed 95% intervals, not date HPDs or simultaneous uncertainty bands.

All internal dates are monitored because a well-mixed root/TMRCA does not establish mixing of other branches used by the geographic model. Diagnostics detect problems, but no finite collection of diagnostic thresholds guarantees convergence or model adequacy.

Methods references:

- [Vehtari et al., rank-normalization, folding, and localization of R-hat](https://doi.org/10.1214/20-BA1221).
- [ArviZ diagnostics: R-hat, ESS, MCSE](https://python.arviz.org/en/v0.22.0/api/diagnostics.html). The implementation environment pins ArviZ 0.21.0.
- [BEAST documentation on Markov jumps and stochastic mapping](https://beast.community/markov_jumps.html). This implementation reuses the WINGS conditional mapper; it does not claim to run BEAST's joint geographic model.

## Validation status

Local tests cover provenance, stale-output removal, topology/date continuity, study-ancestry scope, zero-entry histories, equal weighting, the existing numerical mapper, and the standalone viewer. Browser checks exercised playback, draw/location changes, every WINGS tip, and mobile layout using synthetic data.

The development workspace did not contain ArviZ or Snakemake, and package downloads were unavailable. Their integration tests are supplied: installation runs the Snakemake dry-run test when available, and the actual workflow's mandatory Conda preflight runs all ArviZ numerical tests before processing any posterior data. No validation claim is made for a user's raw chains before the gate reads them.
