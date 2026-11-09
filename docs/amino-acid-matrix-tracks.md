# M1 and M2 matrix annotations

The MP segment now includes a compact CDS overview on the same report canvas, followed by independent M1 and M2 amino acid lollipop tracks.

- M1: #8C1D40.
- M2: #FFC627.

The CDS overview uses the displayed sample's stored consensus nucleotide coordinates and VADR CDS annotations. M1 and M2 blocks are drawn from their actual intervals, with dashed connectors joining separated blocks (including the spliced M2 CDS). Arrow ends follow coding direction. Partial CDSs are labeled. No positions are copied from the example screenshot or a different reference.

The overview is explicitly labeled as sample nucleotide positions. The protein plots continue to use their own selected-reference amino acid positions and lengths. A nucleotide position is not treated as a protein residue number. M1/M2 lollipop stems, heads, track baselines and legend use matching protein colors. The same sample nucleotide overview remains valid when M1 and M2 select different protein reference strains.

Missing or invalid CDS coordinate records are omitted from the overview; existing protein comparisons remain visible when available. Fully unavailable protein comparisons continue to use compact notices. Saved sample annotations are unchanged.

Rebuild the report using existing results_amino_auto/*/changes.json. No reference assignment, amino acid analysis or upstream workflow reruns are needed.
