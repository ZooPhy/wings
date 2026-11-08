# Reference identity in the combined report

The assessment-coverage section is removed from the visible report. Underlying QC statuses and position-specific frequency denominators are preserved in the data and computation.

A comparison-reference block above the canvas now identifies the reference strain and the versioned nucleotide segment and protein accessions for every CDS row in the displayed sample/segment. These values come from that sample's saved panel metadata, with protein-record accessions used when panel metadata is missing. Nucleotide sources and valid protein accessions are clickable. Missing strain/accession metadata is labeled, never replaced with an assumed default strain.

The displayed sample consensus is labeled separately. It supplies the nucleotide axis and the base letters. Amino acid substitutions are named against the comparison reference proteins. The protein accession therefore matters alongside the nucleotide accession. SVG exports label accessions next to CDS tracks and include complete reference metadata in the SVG description.

The default prepared panel uses A/goose/Guangdong/1/1996 (H5N1), with versioned RefSeq records NC_007357.1 through NC_007364.1. A custom panel may use other strains, so the report reads its recorded metadata instead of hard-coding this name. Synthetic previews explicitly identify their artificial reference and do not label it as a biological strain.

Install the reference-display updater after the combined-landscape updater, then rebuild your report using the existing coordinate-enabled sample changes.json inputs. No analysis recomputation is required.
