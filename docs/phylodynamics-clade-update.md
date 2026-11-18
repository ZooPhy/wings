# H5 HA clade screening and temporal diagnostics

This update addresses mixing genetically distant H5 references into one clock
analysis. It does not lower `min_clock_r2` or select references using clock fit.

## What changes

1. Nextclade 3.25.0 classifies eligible study HA and reference sequences locally,
   using `community/moncla-lab/iav-h5/ha/all-clades`. The dataset is downloaded
   once, then its exact version and all file hashes are frozen. No study sequence
   is uploaded to Nextclade or NCBI. Dataset classification happens before quotas.
2. All eligible study sequences must have one usable common clade. Missing/bad
   study calls and multiple study clades block the analysis; samples are not
   silently discarded. Other influenza segments currently block pending a
   segment-specific lineage policy. Clade assignment is not perfect.
3. References with usable matching clade calls form the sampling frame. Good
   and mediocre Nextclade QC are accepted; warnings are retained. Bad/failed
   calls and other clades are excluded with explicit reasons.
4. Two nearest eligible references per study sample are reserved using aligned
   callable nucleotide distance (at least 80% overlap of study callable sites).
   Ties use stable IDs. The union of reservations is shared across all strategies;
   the remaining budget supplies geographic/time context. Exceeding a quota
   blocks rather than dropping reserved relatives. No 5% genetic cutoff is used.
5. Original sequences are retained for MAFFT/IQ-TREE. Nextclade orientation calls
   normalize reverse complements, with original and oriented hashes recorded.
   Its insertion-stripped alignment is used only to rank nearest references.
6. Every replicate gets root-to-tip points and 199 tip permutations plus 199
   same-date monophyletic-cluster permutations. Root position is refitted for
   every permutation on the unconstrained ML tree. The least-squares root search
   is unconstrained in slope; nonpositive observed rates block. The positive-rate
   R² statistic and add-one empirical p-values are recorded. Both p-values must
   be <=0.05, and raw-ML R² must meet the configured threshold. The existing
   TreeTime rate/R² check still applies after these diagnostics pass.

This is a regression permutation screen, not a full Bayesian rate-interval
randomization test. Cluster membership is determined at the observed root and
held fixed for permutation. Tree uncertainty and residual population-structure
confounding remain. Passing does not guarantee accurate dates or introductions.
The original sampling smoke benchmark predates this change and does not validate
these revised sampling settings.

## Install

```bash
python ~/Downloads/wings_add_phylodynamic_clade_screening.py --repo . --apply
```

The installer stages and tests changes before applying them, preserves
`config.yaml`, backs up changed files under `~/.wings/code-backups`, and refuses
to overwrite edits that differ from its reviewed baseline. It does not download
references or execute biological analyses. The existing Snakefile includes the
updated `rules/phylodynamics.smk`; no new main-Snakefile include is required.

## Rerun only this analysis

With existing validated metadata, study consensus and coverage files present:

```bash
snakemake results/run_summary/phylodynamics/summary.json \
  --configfile config.yaml config/phylodynamics.example.yaml \
  --use-conda --cores 8 \
  --allowed-rules \
    phylodynamic_reference_snapshot \
    phylodynamic_reference_selection \
    phylodynamic_replicate \
    phylodynamic_sensitivity \
  --dry-run --quiet rules
```

Review the plan, then repeat without `--dry-run --quiet rules`. This rule-limited
run deliberately reuses existing upstream outputs; it does not verify whether
those outputs need regeneration. Keep `NCBI_EMAIL` configured as previously.
The new conda environment includes Nextclade. The first selection downloads its
dataset; the existing NCBI cache remains usable. `references.offline: true`
requires both the NCBI snapshot and the Nextclade dataset already cached.

Changing `lineage.snapshot` explicitly refreshes the Nextclade dataset. Set
`lineage.tag` to an exact dataset tag to pin a known release. Missing, modified,
or incomplete frozen cache files produce an error; they are not silently reused.
Do not run simultaneous workflows against one dataset cache.

## Review outputs

- `selection/HA/lineage/lineage.json`: dataset version/hashes, software, clade,
  status and reserved-reference IDs.
- `selection/HA/lineage/clade_decisions.tsv`: every usable study/reference call,
  QC, orientation, and inclusion/exclusion decision.
- `selection/HA/lineage/nearest_references.tsv`: retained nearest-reference links,
  distances, overlap and ranks.
- `selection/HA/STRATEGY/replicate_N/reference_decisions.tsv`: reserved relatives
  versus sampled context.
- `inference/HA/STRATEGY/replicate_N/temporal_diagnostics.json`: all null draws,
  observed regression, permutation clusters, p-values, failure reasons.
- `inference/HA/STRATEGY/replicate_N/clock_points.tsv`: plot-ready dates/distances.
- `sensitivity.html`: clade, raw-ML clock diagnostics and per-replicate results.

Blocked runs replace movie data with null and remove stale dated-node outputs.
No successful replicate is substituted for a blocked predeclared primary.

## Validation in the development environment

- Unit/numerical tests cover clade eligibility, missing/mixed calls, orientation,
  frozen caches, anchors/caps, root optimization, permutation reproducibility,
  and refusal of unscreened legacy selections.
- The original six uploaded ML trees were replayed through the new diagnostic;
  all remained blocked. No clade calls or new fitted trees were fabricated.
- Legacy reference-import and movie regression tests pass.
- Live Nextclade/dataset classification, MAFFT/IQ-TREE/TreeTime integration and
  Snakemake execution are pending in this environment because their executables
  are unavailable. CI contains dedicated real-tool and Nextclade reference/
  reverse-complement controls. Local mock tests do not validate a live dataset.

Within an environment containing the full tools, explicit integration checks are:

```bash
WINGS_TEST_PHYLODYNAMIC_TOOLS=1 WINGS_TEST_PHYLODYNAMIC_LINEAGES=1 \
  python -m unittest discover -s tests -p 'test_phylodynamics*.py' -v
python tests/check_phylodynamics_workflow.py
```

The live Nextclade control downloads the public dataset. The other integration
fixture uses synthetic sequences; neither test estimates biological results.

## Sources

- Ort et al. 2025, Virus Evolution: https://doi.org/10.1093/ve/veaf058
- Murray et al. 2016: https://doi.org/10.1111/2041-210X.12466
- Rambaut et al. 2016 (TempEst): https://doi.org/10.1093/ve/vew007
- Nextclade dataset versioning: https://docs.nextstrain.org/projects/nextclade/en/stable/user/datasets.html
