# Protein coordinates in the amino acid landscape

The constellation wheel selects a genome segment. Its colors are navigation styling, not sequencing QC, comparison completeness, or biological significance.

Each recorded protein gets a separate track with its own full-length reference amino acid coordinates, including any signal peptide. NS1 and NEP, M1 and M2, and PB1 and PB1-F2 therefore have independent axes. A54T is anchored at reference residue 54. An insertion is anchored after a reference residue (including before residue 1); deletion markers identify deleted reference residues. Protein length is taken from the recorded reference, not nucleotide segment length divided by three.

Fit proteins restores the entire range of each reference. From aa / To aa filters each independent track to the same residue-number interval, clipped to its reference length. Show residues narrows the view; letters are the displayed sample's aligned amino acids. Inserted residues are inspected from insertion markers, not assigned fictitious reference positions. A deleted reference residue appears as a dash. CDS genomic spans and splice junctions are retained in annotation details rather than drawn as amino acid coordinates.

Marker height remains the fraction of selected samples callable for that specific event carrying it. Unknown, withheld, or absent comparisons do not inflate the denominator. These are cohort fractions, not within-sample allele frequencies or population prevalence. Reference identity and accession versions remain visible. Markers from different references are never pooled.

Clicking a marker opens mutation details and, when available, the true consensus codon and nucleotide positions in coding order. Older protein results without DNA/codon maps still plot protein differences; missing codon context is stated explicitly.

Generic Compared / Partial comparison wheel badges are removed. An affected protein instead states its recorded sequence or alignment problem in plain language. When the result does not record a cause, the report says so. Calls withheld by the analysis remain withheld. No analysis thresholds, references, mutation calls, or saved JSONs are changed by this presentation update.

Rebuild only the HTML/TSV/JSON report with the existing `report --inputs ...` command. No upstream Snakemake processing is required.

Only changes recorded in the displayed sample and protein are plotted. Changes present only in other samples are omitted. Switching the displayed sample refreshes the plotted set. Marker heights still use the selected comparison cohort; analysis outputs and TSV/JSON exports retain all original calls.

Unavailable protein comparisons appear once as compact notices with their recorded reasons and reference identity. They reserve no SVG plotting rows. Mixed segments allocate space only to available tracks, and segments with no usable comparisons show no empty plot. Unselected wheel wedges use #747474.
