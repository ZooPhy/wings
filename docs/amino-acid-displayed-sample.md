# Mutation markers and the displayed sample

Cohort mutation markers now show whether the coordinate sample actually carries each plotted change.

- A filled head indicates that the displayed sample carries the change.
- A hollow head and dashed stem indicate that only other selected samples carry that change. The label includes the displayed residue, for example `A54T (1/2) [A here]`. Indel boundaries use filled/hollow diamonds with the same presence distinction.
- Selecting a marker shows an explicit present/absent status and the actual amino acid in the displayed sample. For absent substitutions, codon highlighting uses the comparison-site color rather than the altered-codon color.
- When another sample carries the mutation and has coordinate data, **Show carrier: sample-name** switches the displayed sequence and highlights that carrier's actual codon. A54T then shows T in the carrier's amino acid row.

The cohort count remains position-specific and independent of which sample supplies the nucleotide axis. Selecting a raw codon without a corresponding change clears the previous mutation selection. Sample sequences, variant calls and frequency denominators are never rewritten to match the marker label.

Rebuild the existing report using its coordinate-enabled sample JSON inputs after installing this display update. No analysis recomputation is needed.
