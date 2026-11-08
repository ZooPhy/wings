# Linked nucleotide and CDS browser

The amino acid landscape now includes a segment browser. Select a sample/segment, use Fit segment for an overview, and Show bases or an explicit From/To range for nucleotide detail. Windows of 120 nucleotides or fewer show bases and translated CDS residues. Windows of 65 or fewer also label translated CDS indices.

CDS blocks, joins and directions come from each sample's passing VADR feature table, not a fixed subtype cartoon. The continuous stored consensus sequence supplies nucleotide coordinates (1-based). CDS arrows indicate biological orientation; dashed lines connect coding blocks across an intron. Overlapping CDSs have separate tracks. Reverse-strand CDS codons are complemented and traversed in biological order, while their coordinate positions refer to the stored consensus.

Click a lollipop to select a carrier sample and highlight its codon. The mutation detail panel includes a View codon in segment browser button. The browser's sample/segment selector permits comparison with another sample; when the same protein/reference is available, it highlights the aligned position. Clicking a translated CDS residue can select a corresponding plotted change. For a sample not already selected in the plot, this action adds that sample to the selection.

A splice-spanning codon records all three true nucleotide positions. Its glyph includes an arrow indicator and the detail card lists those positions, even when separated by an intron. A deletion has no sample codon: only neighboring codons are highlighted and explicitly labeled as flanks. Repeated inserted residues retain their own codon positions when they share a plotted event. Translation exceptions, nonstandard genetic codes and overlapping intervals within one CDS have no guessed codon map. Residues downstream of an internal stop are not displayed as translated amino acids. Partial annotations and codon_start offsets use local translated-CDS indices, never an inferred full-length reference position.

Colors distinguish coding tracks; they are not phenotype or severity annotations. Protein domains, epitopes and HA cleavage/signal-peptide coordinates are not supplied by this feature. Source filenames, feature-table hashes, original qualifiers, interval lists and translation flags are retained. Only passing VADR annotations are used, so a failed annotation is not converted into a confident coding track.

## Refresh older results

Older JSON files can still display lollipops, but do not contain the nucleotide sequence or codon map. Regenerate the two requested sample outputs after installing:

```
snakemake \
  results/12-11-2025_barcode03/amino_acids/changes.json \
  results/12-11-2025_barcode04/amino_acids/changes.json \
  --forcerun amino_acids_sample --cores 2 --use-conda

python scripts/wings_amino_acids.py report \
  --inputs results/12-11-2025_barcode03/amino_acids/changes.json \
           results/12-11-2025_barcode04/amino_acids/changes.json \
  --html results/run_summary/amino_acids/two_samples.html \
  --tsv results/run_summary/amino_acids/two_samples.tsv \
  --json results/run_summary/amino_acids/two_samples.json
```

These paths assume the default results_dir. Existing upstream dependencies are reused where current. A normal workflow run also rebuilds the run summary and .wings bundle.

## Data additions

The top-level analysis JSON keeps schema_version 1 and adds coordinate_schema_version 1 and module_version 1.1.0. `segment_sequences` stores each consensus sequence, segment, ID, length and sequence hash. Each CDS has `cds_annotation` (intervals, partial flag, strand, qualifiers and source hash) and a `codon_map` with status and ordered codons. A codon contains its translated CDS index, ordered consensus positions, coding-orientation bases, amino acid, splice-crossing flag and whether it lies downstream of a stop. This increases JSON size and places the consensus nucleotide sequence in the exported report; the HTML remains self-contained and makes no network requests.

The coordinate unit tests cover joined/reverse CDSs, codons across splice boundaries, independent overlapping frames, partial CDSs, reading offsets, exceptions, residual incomplete codons and internal stops. JavaScript tests exercise codon links, deletion flanks, zoom/fit and legacy data. The isolated production-rule test checks that regenerating a consensus updates the actual codon bases and positions.
