# Shared cohort references and default cohort view

## One reference per protein

Run the cohort reference command on the existing automatic-reference sample JSONs:

```bash
python scripts/assign_cohort_amino_references.py \
  --inputs results_amino_auto/*/changes.json \
  --output-dir results_amino_cohort
```

The candidate pool is the union of validated reference proteins embedded in those results. No BLAST search, reference downloads, raw reads, VADR or normal workflow jobs are required. Each gene/segment pair gets one shared reference for the entire supplied cohort.

Candidates first maximize the number of samples passing their previously recorded identity/coverage thresholds with callable positions. Remaining ranking uses summed length-normalized global alignment score, then identity and coverage. Each sample contributes equal weight; multiple distinct CDS sequences for the same gene within a sample share that sample's weight. Identical candidate sequences are scored once. Tied candidate scores use a deterministic versioned-ID ordering, and ties/equivalent IDs are recorded as selection conventions, not biological certainty.

Source JSONs are preserved. A new cohort_reference_panel.json and per-sample reference_panel.json/changes.json files record selected references, scores, cohort membership and source hashes. All candidate references are already versioned; conflicting metadata for the same ID is rejected. The original evidence version must match; provide its path using --evidence when needed. The existing ambiguity and CDS-quality protections still apply.

This is a separate cohort post-processing command; the earlier local database command still generates individually shortlisted candidate panels. Use cohort results for the cohort comparison report.

## Display defaults

The report starts with Displayed sample = All samples and Observed in samples = At least 80%. Change type continues to default to All changes.

The frequency filter uses observed carrier count divided by all currently selected comparison samples. For 30 selected samples, 24 carriers pass 80%; 23 do not. Unknown or unavailable comparisons never count as observed carriers. Marker height uses the same denominator; the number of callable comparisons is shown separately in mutation details. All frequencies and lower thresholds are available. When no changes pass, the status gives the number of changes before filtering and suggests lowering the cutoff.

All samples aggregates events only within identical protein/reference tracks. It shows reference residues, not an inferred cohort consensus. Individual sample views keep the rule of showing only that sample's changes and retain sample-specific CDS, codon and nucleotide context. The displayed-sample dropdown remains independent of the comparison-cohort checkboxes. Empty cohort selections are handled explicitly.

## Report rebuild

```bash
python scripts/wings_amino_acids.py report \
  --inputs results_amino_cohort/*/changes.json \
  --html results_amino_cohort/amino_acid_landscape.html \
  --tsv results_amino_cohort/amino_acid_landscape.tsv \
  --json results_amino_cohort/amino_acid_landscape.json
```

Full JSON/TSV results are retained independently of visual frequency/type filters. The previously removed report sections and explanatory paragraph remain removed.
