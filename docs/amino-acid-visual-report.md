# Interactive amino acid landscape

The amino acid report now opens with a lollipop plot instead of a table. Use the protein/reference selector, sample chips, change-type filter, and search field to explore existing results. Click a marker (or focus it with Tab and press Enter) to inspect carrier samples, exact-match literature annotations and local aligned sequence context. From/To controls zoom the protein axis; Reset restores the whole reference. SVG export contains the current protein plot and its reference numbering. TSV/JSON downloads retain the complete report dataset, independently of view filters.

## Rebuild an existing two-sample report

```
python scripts/wings_amino_acids.py report \
  --inputs results/12-11-2025_barcode03/amino_acids/changes.json \
           results/12-11-2025_barcode04/amino_acids/changes.json \
  --html results/run_summary/amino_acids/two_samples.html \
  --tsv results/run_summary/amino_acids/two_samples.tsv \
  --json results/run_summary/amino_acids/two_samples.json
```

This command reads existing sample JSON results. A normal Snakemake run also rebuilds the run summary and embeds the new visual report in the `.wings` bundle. Since the main script is a declared analysis input, a later normal workflow run may schedule recomputation after the renderer update; the direct report command above only regenerates the report.

## Meaning of the plot

- Horizontal position is the recorded full-length reference-protein coordinate. Insertion positions are anchors after which residues were inserted; position zero is before the first residue.
- Height is the number of distinct selected carrier samples divided by the number of selected samples assessed at that reference position. This is not within-sample allele frequency or population prevalence.
- An unassessed protein, ambiguous residue or position downstream of a premature stop is excluded from the denominator. A callable deletion is an assessed state. An insertion requires callable flanking anchors (one anchor at a sequence end). Duplicate CDS records within one sample do not inflate sample counts.
- Colors identify substitutions, insertions, deletions and stop gains. A ring indicates an exact-match annotation in the pilot catalog; it is not a severity score.
- Closely spaced stems can fan out to separate marker heads. Their roots retain the true reference coordinates. Dense plots suppress most labels; click or zoom for details.
- Each track uses a single protein, reference ID and reference sequence. Different reference sequences are never pooled even if their IDs match. Sample track lines show availability for the protein; consult the coverage cards and site-specific denominator for assessment at an individual position.
- Empty plots distinguish no reference-based comparisons, no selected samples and no changes matching the current view. Coverage remains available to distinguish unassessed inputs from assessed unchanged proteins.

The supplied figure inspired the lollipop layout. No epitope labels, signal peptide, HA1/HA2 or other domain boundaries are assigned without a reviewed map tied to the reference. This update changes report presentation; the underlying consensus comparison and evidence-matching functions are unchanged.

The HTML embeds its JavaScript, CSS, and data, works offline, and is compatible with the existing sandboxed `.wings` report iframe. It makes no network requests. Synthetic preview data are labeled prominently. Unit/model/DOM tests are included; visual browser validation on the target browser remains appropriate.
