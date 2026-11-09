# Retain reliable protein calls when alignments tie

The amino acid comparison no longer rejects an entire protein because multiple global affine-gap alignments share the best score. It traverses every path in the optimal traceback graph, without enumerating alignments or imposing a path-count limit.

A reference residue contributes to calls or frequency denominators only when all optimal paths map it to the same query residue index (or the same deletion boundary). Insertions require an unambiguous anchor and callable flanking reference positions. Unknown amino acids and positions after an early stop remain excluded. Requiring consistent query indices also preserves reliable links to actual consensus codons; identical amino acids with different possible codon mappings are conservatively masked.

The JSON records `alignment_resolution`, including callable reference positions, callable insertion anchors, uncertain reference positions and uncertain insertion anchors. TSV exports include the method and uncertainty lists. `PARTIAL_INTERPRETATION` means reliable positions remain available. If no callable reference position remains, mutation calls remain unavailable. Reference selection ties, identity/coverage thresholds, partial-CDS blockers and reference/evidence matching are unchanged. Alignment scores and identity/coverage metrics retain the representative best-alignment convention; uncertainty is established across the entire optimal graph.

The UI shows “Some positions are uncertain”, names the affected reference positions, and shades them gray. Only reliable, displayed-sample mutations are plotted. Uncertain sites never contribute mutation-free observations to cohort denominators. A representative alignment remains available for inspection, explicitly labeled as such.

## Refresh existing results without upstream processing

Old JSONs withheld all ambiguous-alignment calls. A report rebuild alone cannot recover those calls. Use saved translated proteins:

```bash
python scripts/wings_amino_acids.py recompare \
  --inputs results_amino_external/*/changes.json \
  --output-dir results_amino_resolved
```

This command reads each JSON's translated proteins, embedded original reference panel and recorded identity/coverage thresholds. It requires the evidence JSON to match the recorded SHA-256; use `--evidence PATH` if the original evidence file is elsewhere. Missing sequences, thresholds or evidence cause a clear error. Every sample is validated and computed before output writing starts.

New results are written to `results_amino_resolved/<sample>/changes.json`, preserving the source JSONs and recording their hashes and previous module versions. No raw reads, original consensus inputs, VADR installation, downloads, external drive access or Snakemake are needed. CDS blockers remain blocked.

```bash
python scripts/wings_amino_acids.py report \
  --inputs results_amino_resolved/*/changes.json \
  --html results_amino_resolved/amino_acid_landscape.html \
  --tsv results_amino_resolved/amino_acid_landscape.tsv \
  --json results_amino_resolved/amino_acid_landscape.json
```

Tests include an independent exhaustive oracle over 900 short sequence pairs, a repeated-residue indel with a separate retained substitution, early stops/unknown residues, saved-result refresh and input preservation, plus UI shading, masked frequency denominators and codon-coordinate behavior.

Each track with mutations labels its frequency axis “Samples with change (%)”, with 0%, 50%, and 100% ticks. The hover explanation specifies selected samples callable for that change; uncertain and unavailable comparisons are excluded.

The human-readable label for a stop-gain substitution is “Nonsense mutation”. Existing `stop_gain` machine keys, calls and exports remain compatible; relabeling does not remove these observations.
