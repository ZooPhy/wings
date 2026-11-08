# HA reference processing regions

The HA landscape includes a colored region bar beneath the reference amino acid axis:

| Region | Full-length precursor coordinates, inclusive |
| --- | --- |
| Signal peptide (SP) | 1–16 |
| HA1 | 17–346 |
| HA2 | 347–568 |

These coordinates apply only to the pinned A/goose/Guangdong/1/1996 HA precursor, protein YP_308669.1, segment NC_007362.1, 568 residues, associated with UniProt Q9Q0U6. The signal peptide is the 16-residue N-terminal segment described in Wibawa et al. HA1 and the HA2 start use the PDB 4MHI depositor's UniProt-coordinate annotations (HA1 17–346; HA2 ectodomain construct starts at 347). HA2 is extended to the end of the full-length pinned precursor at 568; the truncated structural construct ends earlier and is not used as the full HA2 endpoint.

Sources:

- Wibawa et al., Virology Journal 8:425 (2011): https://doi.org/10.1186/1743-422X-8-425
- PDB 4MHI depositor annotation: https://pdbj.org/emnavi/quick.php?id=pdb-4mhi
- Full precursor and version: https://www.ncbi.nlm.nih.gov/protein/YP_308669.1
- NCBI cross-reference to UniProt and mature chains: https://www.ncbi.nlm.nih.gov/gene/3654620

These are reference annotations, not inferred processing boundaries in the displayed sample. Protein accession version, segment accession, length and consistency of the stored reference alignment with the recorded panel are checked before showing labels. They are not applied to unrelated HA references or other proteins.

The region bar clips to the zoomed range. SP abbreviates Signal peptide when space is narrow; the full name and complete precursor-coordinate ranges remain in the caption and hover text. Mutation details name the reference region. HA1/HA2 numbering is not reset, and mutation calls and frequency denominators are unchanged. SVG exports include the annotations; source links appear under Annotation sources and numbering. Raw TSV/JSON sample results are unchanged by this display update.

Rebuild the report from existing results_amino_resolved/*/changes.json; no recompare or upstream processing is required.

## Region colors

Signal peptide: #4AB7C4; HA1: #8C1D40; HA2: #FFC627. HA marker stems and heads use the same region colors as the annotation bars. The HA legend describes regions; other proteins retain change-type colors. HA2 labels use darker text and a fine head outline for contrast. Insertions use their reference anchor region (an insertion before residue 1 uses Signal peptide). Region endpoints and mutation numbering do not change.
