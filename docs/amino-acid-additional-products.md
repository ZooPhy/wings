# Additional CDS/product tracks

The existing compact MP CDS overview is generalized to the following annotated multi-product segments:

| Segment | Primary product | Additional product |
| --- | --- | --- |
| MP | M1 | M2 |
| NS | NS1 | NEP (NS2) |
| PB1 | PB1 | PB1-F2 |
| PA | PA | PA-X |

Primary products use #8C1D40 and additional products #FFC627. CDS blocks, protein lollipop stems/heads and the legend use matching colors. NS2 is recognized as an alias for NEP for display matching; saved gene identifiers and analysis results are not rewritten.

CDS overviews use the displayed sample's saved consensus nucleotide coordinates. Discontinuous annotated blocks are connected with a dashed line; this is a coordinate connector, not a claim that every discontinuous product is spliced. NEP shows its saved joined CDS structure. Arrow ends indicate coding direction. Partial annotations are labeled; absent, invalid or mixed-strand coordinates are omitted. Duplicate identical annotations are deduplicated.

Protein plots retain separate selected-reference amino acid axes and tight content-fitted spacing. Unsupported translation events and withheld mutation calls remain withheld. PA-X/PB1-F2 appear only if the product is recorded in the existing sample results; this display update does not predict additional ORFs or infer a frameshift translation.

Rebuild the report from results_amino_auto/*/changes.json. No sample analyses, reference selection, VADR or upstream workflow reruns are needed. The removed report paragraphs and provenance panels remain removed.
