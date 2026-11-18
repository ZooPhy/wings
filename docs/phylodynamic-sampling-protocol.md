# Phylodynamic reference sampling protocol

Status: literature-informed implementation and simulation harness. **No reference
quota is certified as bias-correcting.** Benchmarking uses known trees and does
not validate the complete alignment, tree estimation, dating, or inference chain.

## Evidence review

Targeted review completed 2026-11-14, using primary research retrieved through
PubMed/PMC and journal sites. Searches combined *phylogeography*, *sampling bias*,
*spatial temporal subsampling*, *discrete trait*, *Markov jumps*, *influenza*, and
*H5N1*. Included simulation studies with known truth and relevant influenza
sampling comparisons. This was not an exhaustive systematic review or a
meta-analysis. Dataset-specific percentages were not transferred to WINGS.

| Primary study | Evidence relevant to this protocol | Consequence for WINGS |
|---|---|---|
| Layan et al. (2023), [Virus Evolution, vead010](https://doi.org/10.1093/ve/vead010) | Spatial and spatiotemporal subsampling can improve discrete phylogeographic inference under studied bias scenarios; performance depends on the model and bias severity. | Use stratified random sampling as a candidate design and evaluate the existing CTMC, including misspecification. Monthly bins are an engineering choice, not a result of this paper. |
| Magee & Scotch (2018), [Infection, Genetics and Evolution 64:225–230](https://doi.org/10.1016/j.meegid.2018.07.003) | Influenza sampling fractions and geographic grouping affect reconstruction; more taxa need not monotonically improve inference. | Compare sample sizes and independently seeded replicates. Do not adopt a universal sampling percentage. |
| Liu et al. (2022), [PLOS Global Public Health e0000577](https://doi.org/10.1371/journal.pgph.0000577) | Sampling changes which migration events remain represented as well as ancestral-state inference. | Separate event loss from inference error on retained ancestry. Root accuracy alone is insufficient. |
| De Maio et al. (2015), [PLOS Genetics e1005421](https://doi.org/10.1371/journal.pgen.1005421) | Sampling-sensitive discrete-trait reconstruction motivated structured-coalescent alternatives. | Balancing references does not remove model assumptions or unobserved-state bias. |
| *Ecology and spread of the North American H5N1 epizootic* (2025), [Nature](https://doi.org/10.1038/s41586-025-09737-x) | Includes alternative host sampling designs and broad international context. | Examine host composition and preserve external context; do not treat its study-specific quotas as validated WINGS defaults. |

The implementation decisions below are our synthesis, not a single published
algorithm. The evidence supports sensitivity analyses, not a guarantee of
unbiased introductions or population representativeness.

## Prespecified selection procedure

1. **Freeze the question and frame.** Record segment, study collection interval,
   geographic scope, subtype, date buffers, requested locations, seeds and limits
   before fitting geographic histories. Eligible study tips remain fixed across
   reference replicates. All segments are analyzed separately.
2. **Retrieve a broad candidate universe.** NCBI Entrez nucleotide queries use
   influenza taxonomy, recorded subtype and segment annotations. Freeze all
   returned accession versions. Locally filter actual specimen collection dates
   and declared geography using the study-derived interval. The example uses
   global context; location frequencies in the study do not determine the query.
3. **Classify genetic scope before sampling.** Use the frozen Nextclade H5 HA
   all-clades dataset to classify study sequences and candidate references.
   Require one usable study clade, retain matching reference calls, and audit
   every exclusion. Unresolved study calls or multiple study clades block this
   release rather than silently discarding samples or mixing lineages. Reserve
   two nearest eligible references per study sequence using callable aligned
   sites; use remaining capacity for geographic/time context. No fixed genetic
   distance or clock R² is used to decide clade eligibility. Internal segments
   need a separate lineage policy and are currently blocked.
4. **Apply recorded QC and audit exclusions.** Passing study segment coverage,
   callable bases, comparable sequence length, exact dates and resolved modeled
   locations are required. Partial dates are not midpoint-imputed. Report missing
   metadata separately; completeness filtering itself can bias the pool.
5. **Control actual duplication.** Reject duplicate accession rows and conflicting
   accession metadata. Collapse identical sequences only when the same explicit
   specimen identifier, date, location and host agree. Different animals with
   identical sequences stay eligible. Identical sequences alone, isolate names,
   and same-day collections do not prove duplicate specimens.
6. **Sample without replacement.** All strategies retain the same nearest-reference
   anchors. For remaining capacity, `balanced` chooses the least
   represented combined study+reference location, then its least represented
   time stratum, with seeded random ties. The total/per-location caps are
   engineering limits. `available` samples remaining capacity randomly from the
   same clade-eligible pool. Its anchors are fixed, so it is no longer an entirely
   random sample. Anchors that exceed a budget/cap block rather than relax it.
   `diversity` retains balanced strata but uses bounded canonical 9-mer sketch diversity to break ties;
   it is only a sensitivity analysis and is not a phylogenetic-distance method.
7. **Inspect combined composition.** Report study, candidate and selected location,
   month and host counts; missed available locations; and places that cannot
   attain the largest study-location count even with available references and
   the configured cap. Adding references cannot fix every study imbalance.
8. **Keep uncertainty separate.** Independently repeat each design. A range across
   reference replicates is sensitivity, not a pooled credible interval. Never
   replace an unsuccessful primary replicate with a favorable one.

Free-text host strata are not harmonized taxonomic or surveillance categories.
Use them only when labels are consistent. Neither eBird abundance, BirdCast
activity, sequence submission counts nor unadjusted detections supply a valid
infection-incidence denominator by themselves. Incidence-proportional selection
is therefore not implemented as a default.

The bundled geography uses US states and Canadian provinces; other available
countries are explicit country-level states. This mixed resolution is a modeling
choice. Regional North American analysis cannot establish intercontinental origins
when external countries are excluded. Missing locations are not zero introductions.
The current CTMC cannot represent unsampled demes.

## Fixed estimand

Main introduction summaries count geographic entries on branches from the MRCA
of the retained study samples to those same study samples. This avoids comparing
whole-tree counts that mechanically expand with added background tips. It excludes
the ancestral stem above that MRCA, and is not the number of introductions into
an entire epidemic. At least two study tips are required for this summary.

All-tree jump means are retained separately in `all_tree_jumps` for audit. Each
estimated tree still has its own uncertainty and possibly a different focal MRCA;
the fast analysis conditions on that estimated tree. Reversals and repeated entries
are retained. No direct transmission interpretation is implied.

## Benchmark design

`python scripts/phylodynamic_benchmark.py --output results/reference-benchmark`

- Known dated branching trees with simulated geographic histories and serial
  terminal dates; simple sequence evolution supplies the diversity comparator.
- Three geographic states; fixed focal tips retained across designs.
- Seven scenarios: equal rates, geographic surveillance bias, host surveillance
  bias, recent-migrant enrichment, asymmetric rates, time-varying rates and a
  missing geographic state.
- Two reference budgets by default (16 and 32); random, location/month,
  location/quarter, location/month/host and diversity comparisons.
- Independent development and validation seed ranges; paired designs use the
  same simulated realization and candidate pool.
- Metrics: focal-entry error, 95% interval coverage/width, entry-presence Brier
  score, root accuracy/probability, fraction of true full-tree entries retained
  after sampling, and runtime. Event retention measures observability; it is
  not exact recovery of individual jump times.
- Raw simulated truth and every completed, blocked or failed fit are saved.
  Failures never become zero counts. Posterior histories are not pooled.
- The default three simulation replicates per scenario are a **smoke run**, not
  a precise coverage study. Report the number of independent simulations, not
  the number of correlated designs, when estimating Monte Carlo uncertainty.

For a larger prespecified evaluation:

```bash
python scripts/phylodynamic_benchmark.py --output results/benchmark-development \
  --partition development --replicates 100 --histories 600 --budgets 16 32 64
python scripts/phylodynamic_benchmark.py --output results/benchmark-validation \
  --partition validation --replicates 100 --histories 600 --budgets 16 32 64
```

Do not tune on the validation set or on desired results from the real data. The
script deliberately emits `quota_recommendation: null`. Choosing operational
quotas requires declared loss/coverage criteria and adequate simulations; the
provided small run does not establish an optimum. Before scientific adoption,
add sequence-to-tree/dating uncertainty, more realistic epidemic sampling and
independent model comparisons. These remain outside this initial benchmark.

## API basis

- [NCBI E-utilities reference](https://www.ncbi.nlm.nih.gov/books/NBK25499/):
  ESearch/history, paginated accession lists, EFetch GenBank XML.
- [NCBI source modifiers](https://submit.ncbi.nlm.nih.gov/help/genbank/source_modifiers/):
  specimen collection dates and date precision.
- [NCBI usage guidance](https://eutilities.github.io/site/API_Key/usageandkey/):
  paced requests, optional API key, tool/contact identification.

WINGS sends no study identifiers or private sequences. It uses public search
terms, then applies study-derived filters locally. A frozen snapshot is reusable
and checked by hashes. A record cap aborts rather than selecting the first results.

## HA clade and temporal-screen update

- Ort et al. (2025), *Development of avian influenza A(H5) virus datasets for
  Nextclade enables rapid and accurate clade assignment*, Virus Evolution,
  https://doi.org/10.1093/ve/veaf058 supports the H5 clade-assignment dataset.
  Its published benchmark is not validation of WINGS sampling quotas or dating.
- Murray et al. (2016), *The effect of genetic structure on molecular dating
  and tests for temporal signal*, https://doi.org/10.1111/2041-210X.12466,
  motivates inspecting genetic/temporal confounding and clustered permutations.
- Rambaut et al. (2016), TempEst,
  https://doi.org/10.1093/ve/vew007: root-to-tip R² alone is exploratory.

The new regression diagnostic refits the least-squares root for each of 199
permutations on the unconstrained ML tree. It checks positive slope, configured
R², and empirical p <= 0.05 under both tip and same-date monophyletic-cluster
permutations. Cluster membership is fixed at the observed root. A nonpositive
observed slope gets statistic zero. This is not the Bayesian evolutionary-rate
credible-interval date-randomization test, and passing does not integrate tree
uncertainty or prove reliable dates. Population structure may remain confounded.
The existing TreeTime positive-rate/R² check is also retained.

Nearest-reference count, 80% callable-overlap requirement, QC acceptance of
Nextclade good/mediocre (not bad), and quotas are declared engineering settings.
Clade membership does not guarantee a homogeneous molecular clock. The earlier
known-tree sampling smoke benchmark predates these anchors/clade screens and
must not be presented as validating the revised sampler.
