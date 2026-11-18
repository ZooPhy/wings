## HA clade-screen update

See [current update validation and limitations](phylodynamics-clade-update.md).
The historical benchmark below predates clade filtering and nearest-reference
anchors; it does not validate the revised selection policy.

# Verification record — 2026-11-14

This update was prepared against the installed `wings_add_phylodynamic_selection.py` source snapshot. The user’s Mac checkout was not mounted here.

## Completed

- 25 phylodynamic unit/numerical tests passed; the real-tool test was explicitly skipped.
- 14 legacy public-reference regression tests passed.
- The phylogeography movie regression suite passed.
- Imported all 17,508 uploaded FASTA/metadata records with unique accession-version joins and HA header annotations.
- Using the uploaded study metadata, source filters retained 16,255 records; 1,253 were audited exclusions. This is before geographic and sequence QC. Of the retained source records, 617 lack a resolvable modeled geographic unit and will be excluded during selection.
- 420 known-tree conditional fits completed with no computational failures: 7 scenarios × 2 independent seed partitions × 3 simulated datasets × 2 budgets × 5 designs. Each fit used 40 conditional histories.
- Installer staging, guarded application, repeat application and modified-file rejection were checked on a recovered copy.

## Pending

- Live NCBI compatibility: direct access returned HTTP 403 in this execution environment. Paging, frozen accession versions, response parsing, partial-response rejection, integrity checks and private-key handling were tested with fixtures. Run `python tests/check_phylodynamics_ncbi.py` locally.
- Snakemake parsing and DAG resolution: Snakemake was unavailable here. The installer runs this check when Snakemake is present. CI is configured for 8.30.0 and 9.24.0.
- Real MAFFT/IQ-TREE/TreeTime integration: those tools were unavailable here. The gated integration test and CI cover this requirement, but their addition is not evidence of a successful run.
- Larger calibration, estimated-tree uncertainty, structured-coalescent comparisons and validation against actual surveillance. No biological analysis was run.

## Smoke results

The table below reports mean absolute error in focal-entry counts for all seven validation scenarios at budget 32. Each cell has only three independent simulated datasets and 40 posterior histories per fit. These results demonstrate a working benchmark and tradeoffs; they cannot establish an optimum or precise coverage. No settings were tuned to these validation outcomes.

| Scenario | Available-pool random | Location/month balanced |
|---|---:|---:|
| equal_rates | 0.417 | 6.342 |
| geographic_bias | 2.942 | 2.400 |
| host_bias | 1.525 | 5.467 |
| recent_migrants | 3.442 | 3.442 |
| asymmetric_rates | 3.333 | 5.517 |
| time_varying_rates | 4.450 | 6.667 |
| missing_deme | 1.383 | 1.650 |

Balancing is not uniformly better in this smoke run. The primary strategy remains predeclared; no method or quota is automatically selected from favorable results.

Full per-fit results: [JSON](benchmarks/phylodynamics-smoke-results.json). Protocol and summaries: [JSON](benchmarks/phylodynamics-smoke-summary.json).

Reproduce (runtime will vary):

```bash
python scripts/phylodynamic_benchmark.py --output results/reference-benchmark-smoke \
  --replicates 3 --histories 40 --budgets 16 32
```
