# Streamlined amino acid report

The permanent mutation-details side panel and protein/reference dropdown are removed. The combined mutation/CDS canvas uses the full report width. Segment and sample navigation is through the constellation wheel and displayed-sample selector. All CDS rows on a segment, including overlapping/spliced proteins, remain visible.

Clicking a lollipop opens a native modal dialog with mutation, sample-carrier, evidence and codon details. Clicking a translated codon also opens its details. Close or Escape dismisses the dialog; Zoom to codon dismisses it and zooms the plot. There is no empty Select a lollipop panel. No amino acid analysis is rerun by this display update.

## Color labels

The old Assessed and Review labels are replaced with Compared and Partial comparison.

- **Compared:** all protein records available in these results for that segment have READY comparison status. It does not establish completeness of all possible influenza proteins or sequencing QC.
- **Partial comparison:** one or more records did not complete reliable comparison, including partial CDSs, ambiguous alignments, distant references or other recorded limitations. Some or all calls may be withheld. Available calls are still displayed.
- **No AA data:** there are no protein-result records for the segment; this does not imply biological absence of the segment.

The wheel's expandable color key explains these definitions. Color describes the recorded protein comparisons, independently of whether an older result includes coordinate maps needed for plotting. Missing coordinates still produce the existing explicit regeneration message.

Rebuild the HTML from the existing per-sample changes.json files after installing the updater. Reference panel, amino acid calls, cohort counts and input data are preserved.
