# Compact cohort picker and genome constellation

The report now uses a closed-by-default comparison-sample picker instead of rows of barcode chips. Open **Edit selection** to search sample names and change cohort membership. Select all applies to the complete dataset, including samples hidden by the search; the selection count remains visible when the picker is closed. Searches do not themselves change the cohort.

The compact genome constellation reuses the clockwise segment order and annular geometry from WINGS' existing `scripts/report/genome-constellation.js`: PB2, PB1, PA, HA, NP, NA, MP and NS. Select the displayed sample, then click a wedge or focus it and press Enter/Space to navigate the shared mutation/CDS canvas. The active wedge has a gold outline. Switching protein references or selecting a mutation carrier also synchronizes the wheel and displayed sample.

Wheel colors describe amino acid assessment, not the sequencing QC in the original sample-detail wheel:

- **Assessed** (green): coordinate sequence exists and all recorded CDS entries for the segment are READY.
- **Review** (gold): CDS results exist but at least one entry is partial, unassessed, or lacks coordinate sequence data.
- **No AA data** (gray): no CDS entries are available for that segment in the amino acid results. It does not assert that the segment was absent biologically or failed sequencing QC.

The center shows the selected segment and reported AA-change count for the displayed sample. Counts are unique across gene/reference/change records and do not count duplicate CDS annotations twice. These per-sample counts are independent of the cohort-specific marker frequencies. An unassessed segment with no reported changes is not a negative mutation screen.

Selecting an unavailable wedge clears the plot and identifies the missing amino acid coordinate data instead of leaving another segment's plot visible. Sequencing QC, subtype and read-depth values are not invented or copied from unrelated records. They remain available in the existing sample-detail report.

The layout also reduces padding and summary-card sizes while keeping reference strain/accessions visible. This is a report presentation update. Regenerate the HTML from existing sample `changes.json` inputs; consensus calling, annotation, variant analysis, and the external source backup are unchanged.
