# Conditional Bayesian TMRCA dating

This opt-in module estimates a posterior date distribution for the common ancestor of the declared WINGS samples. It uses BEAST 2.7.7, the existing alignment, recorded collection dates, and the **rooted topology** from the screened analysis. Where the dated tree omits internal ML branches, WINGS recovers the original ML refinement at the same root, as described below. Node heights are free to change. There are no topology-changing operators and no constraint forcing the WINGS samples to form an exclusive clade.

The reference set, its rooting, and topology remain fixed. The result is a **95% HPD conditional on topology and model**, not a full joint tree posterior or a geographic introduction date. It does not update the geographic histories or the movie. It also cannot establish that the original rooting is correct.

## Run on existing results

From the repository root, install the code update, then preview these three new rules:

```bash
snakemake results/run_summary/phylodynamics/bayesian/HA/balanced/replicate_1/initial/summary.json \
  --configfile config.yaml config/bayesian-dating.example.yaml \
  --use-conda --cores 4 \
  --allowed-rules bayesian_dating_preflight bayesian_dating_chain bayesian_dating_summary \
  --dry-run
```

Remove `--dry-run` to run. The restricted rule list reuses saved alignments, metadata and rooted topologies; it does not rerun IRMA or reference selection. The separate Conda environment supplies BEAST 2.7.7, Java and ArviZ. The default is the predeclared primary replicate with two chains of 5 million steps each, logging every 1,000 steps. This is an initial budget, not a convergence guarantee. Runtime has not been benchmarked on the user's Mac.

`bayesian_dating_preflight` runs synthetic integration tests **before research chains**: XML parsing, two tiny BEAST chains, collection-date and topology invariance, and ArviZ diagnostics. It must pass. A missing/incompatible BEAST command or package environment causes a failure before research inference. `beast_command` can specify an installed BEAST 2.7.7 launcher as an argument list. It does not invoke a shell.

The updater leaves `config.yaml` untouched. All inputs, XMLs, seeds, logs, posterior trees, hashes, and completion markers are retained in:

```
results/run_summary/phylodynamics/bayesian/HA/balanced/replicate_1/initial/
```

Open the report:

```bash
open results/run_summary/phylodynamics/bayesian/HA/balanced/replicate_1/initial/tmrca.html
```

Add the result to the reference comparison page:

```bash
python scripts/build_phylodynamic_comparison.py \
  --summary results/run_summary/phylodynamics/summary.json --dating-run initial
open results/run_summary/phylodynamics/comparison.html
```

The page distinguishes the Bayesian TMRCA from the TreeTime point estimate. It withholds stale/mismatched or unconverged intervals. Changing the dating-run selector does not change the movie's dates.

## Restoring branches omitted from the dated tree

A dated tree can contain multiway branches even when its original `ml.treefile` is fully bifurcating. The dating module now recovers that existing ML refinement only when all of these checks pass:

- Both trees contain exactly the same unique tips.
- The dated root has two children and its bipartition identifies one unique ML edge.
- The ML tree is fully bifurcating as an unrooted graph.
- Every retained dated clade occurs in the rooted ML tree.

The original files are not edited. Retained nodes keep their IDs, dates, and sample labels; restored node IDs are derived from descendant tip sets. Restored nodes start at their dated parent's time, and the starting-tree builder opens positive branches. These times initialize the chains; they are not temporal calibrations or additional observations. All internal dates remain free during MCMC.

The chain manifest records the root partition, restored nodes, original ML SHA-256 and initialization method. The summary and HTML report identify the restoration, and the comparison page rejects results if the source ML file changes. Missing, nonbinary or conflicting ML inputs stop the run rather than introducing an arbitrary resolution. An unresolved dated root also stops the run.

The HPD remains conditional on **one ML refinement**, including any weak or zero-length ML branches. It does not integrate uncertainty about those relationships. The geographic histories and movie retain their original dated-tree inputs.

## Model and priors

- HKY nucleotide substitution model with four gamma rate categories; kappa, stationary frequencies and gamma shape are estimated.
- Strict molecular clock; clock rate and internal node heights are estimated.
- Constant-size coalescent working prior. This is not a claim that the globally sampled, structured reference population is panmictic or constant-sized.
- Clock rate: lognormal median 0.003 substitutions/site/year, natural-log SD 1.5.
- Coalescent population-size × generation-time: lognormal median 1 year, natural-log SD 2.
- Kappa: lognormal median 2, log SD 1.25; gamma shape: exponential mean 1; nucleotide frequencies: Dirichlet(1,1,1,1).

These are explicit configurable working assumptions, not automatically selected or validated for this outbreak. The clock prior is not fitted from the same TreeTime rate. Initial node heights use dispersed scalings of the existing dated tree; both chains have distinct fixed seeds and different starting parameters. BEAST uses the sequence likelihood to re-estimate dates; the starting TreeTime dates are not calibrating priors.

Assess sensitivity to clock/tree priors, reference strategy, and alternative rooted topologies before interpreting a narrow interval. A prior-only run is available with `prior_only: true` and a **new `run_id`**; its report is clearly labelled PRIOR-ONLY and is never shown as a posterior HPD. This first version does not implement a relaxed clock or topology sampling.

## Reporting and failure handling

The module extracts the WINGS taxon-set MRCA and the entire reference-tree root from every sampled tree, using recorded tip dates. It verifies that all sampled trees retain the exact rooted topology and taxon set. WINGS and reference sample IDs must match the alignment and metadata exactly.

After discarding the configured 10% burn-in, reporting requires:

- Every chain reaches its requested final state, with complete matching trace/tree logs and intact hashes.
- Distinct seeds and identical analysis/model/input provenance across chains.
- Rank-normalized split R-hat ≤1.01; bulk and tail ESS ≥400; each chain's bulk ESS ≥100.
- Checks on the WINGS TMRCA, whole-tree root date and all logged variable model/posterior quantities. Constant or nonfinite chains fail. The inactive likelihood is not assessed in prior-only mode.

Convergence criteria are screening diagnostics, not proof of model adequacy. When they pass, independent chains from the **same model and reference replicate** are combined. Different reference replicates are never pooled. The reported HPD approximation is the shortest contiguous interval containing at least 95% of retained draws. For strongly multimodal posteriors, inspect the draws; a single contiguous interval can obscure separate modes.

If thresholds fail, the report says `not_converged` and withholds the interval. Inspect trace plots in Tracer, increase the chain budget or reconsider the model, and use a new `run_id`. Existing outputs are never silently overwritten or automatically resumed. A model/input change also requires a new run ID. A failed command leaves diagnostic logs; it cannot create a valid completion marker.

A successful date-only run does **not** propagate date uncertainty into the geographic entry intervals. That would require mapping geographic histories over the sampled dated trees in a subsequent update.

## Verification status

Local tests cover XML structure, variable node heights, fixed topology, tip-date consistency, non-monophyletic focal taxon sets, NEXUS extraction, HPD calculation, complete-state requirements, provenance, withheld intervals and prior-only labelling. Live BEAST 2.7.7 validation now passes with the uploaded runtime on Linux OpenJDK 21: XML initialization and two synthetic chains, each with 101 trees retaining the recorded tip dates and rooted topology. The headless preflight subsequently passed all 17 tests, including BEAST and ArviZ, on the user’s Mac. For the topology update, two 1,000-step runs on the uploaded 210-tip alignment each produced 101 trees with the recovered topology and recorded tip dates intact. The 39 multiway dated nodes required restoration of 94 existing ML nodes. These are execution checks, not a convergence result. The expanded preflight and Snakemake checks still run on the actual machine and in CI. The required synthetic preflight and CI job run those checks in the dedicated environment before use; do not bypass a failure.

## Primary documentation

- [BEAST 2: fixing the topology while permitting node-height changes](https://www.beast2.org/fix-starting-tree/)
- [BEAST 2 command-line options](https://www.beast2.org/2021/03/31/command-line-options.html)
- [BEAST 2 TreeParser](https://www.beast2.org/xml/beast.base.evolution.tree.TreeParser.html)
- [BEAST 2 Uniform node-height operator](https://www.beast2.org/xml/beast.base.evolution.operator.Uniform.html)
- [ArviZ rank-normalized R-hat](https://python.arviz.org/en/v0.21.0/api/generated/arviz.rhat.html)
- [ArviZ effective sample sizes](https://python.arviz.org/en/v0.21.0/api/generated/arviz.ess.html)

## Headless runtime compatibility

The environment retains the Matplotlib 3.9.4 pin required by ArviZ 0.21. WINGS discovers native Java from the active OpenJDK package inventory, including macOS nested JDK layouts and symlinked paths. It does not use the BEAST package's bundled platform-specific runtime.

`scripts/WingsBeast.java` uses JDK 17+ source-file mode to invoke BEAST's XML parser and MCMC engine directly. It loads the pinned `launcher.jar`, `BEAST.base.jar`, and accompanying version metadata. It avoids the GUI launcher's JavaFX dependency and does not discover or download external user plugins. Likelihood calculations use BEAST's Java implementation. XML validation initializes the model without sampling; errors return a nonzero exit code.

Live XML parsing also identified and corrected the explicit `stateNode` inputs and `clock.rate` attribute. Prior-only chains omit the uncomputed likelihood from their trace, keeping finite-value checks intact. These are format corrections; the model, priors, fixed topology, and convergence requirements remain as described above. Execution tests do not establish convergence or model suitability.

After installing the update, repeat the restricted Snakemake command above. The existing environment is reused. If only preflight failed, no research chain exists, so `run_id: initial` can be reused. Do not mark preflight complete manually. Failures include BEAST's output and retain `version.log`, `validation.log`, or `tools.log`. The required preflight verifies the complete BEAST/ArviZ integration on the actual machine before research chains start.
