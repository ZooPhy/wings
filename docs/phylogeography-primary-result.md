# Primary result and reference sampling

The main report shows the predeclared location/time-balanced reference set 1 for the selected segment. It is not selected by likelihood, clock R², interval width or which sets passed their checks. The saved default method remains respected. With more than one segment, the main toolbar retains a segment selector and applies the same primary policy separately to each segment.

The reference-set dropdown and sensitivity table are under **Advanced → Reference sampling**. Labels describe the strategies and use Set 1, Set 2, etc. Set numbers are identifiers, not ranks. Choosing a different set explicitly marks the page **Comparison result** and exposes a **Return to primary result** button. Closing Advanced does not disguise the selected comparison as the primary.

When the primary set is missing or unavailable for the selected method, the report displays its reason and withholds that result. It never silently replaces it with a successful alternative. Saved alternatives remain accessible under Advanced. The sensitivity table retains unavailable rows, including a missing primary. Counts require a focus location; no missing result is represented as zero.

Balancing favors underrepresented locations and collection periods; the random strategy samples the eligible pool. Both preserve reserved close genetic relatives. The report does not claim balancing is universally more accurate or that sampling bias has been eliminated. The selector and table support sensitivity inspection, not automatic ranking or pooling.

This update changes the viewer, CSS, tests and this document. Reference-selection algorithms, inference, checks, saved posterior draws, configuration and workflow rules are unchanged. Alternative analyses are retained. Rebuild only the report using:

```bash
snakemake --snakefile Snakefile.phylogeography-report \
  --configfile config.yaml config/phylogeography-results.example.yaml \
  --use-conda --cores 4
```

The viewer primary policy is explicit and independent of saved analysis-list ordering; the original results.json retains its source ordering/settings. All primary and comparison data remain traceable by their original identifiers.

Validation: 20 Node tests, plus synthetic browser checks for ordering-independent primary selection, collapsed comparison controls, explicit alternatives, return-to-primary, failed/missing primary without fallback, method-specific availability, segment handling and a 390-pixel mobile viewport. No biological inference was run during this UI update.
