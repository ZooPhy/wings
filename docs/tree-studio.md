# WINGS Tree Studio v0.1.9

## v0.1.9: lasso multi-selection

Tree Studio now supports freehand **Lasso select** for terminal taxa. Turn lasso mode on, drag a loop around tips, and every terminal tip inside the loop becomes part of a local multi-selection. Hold **Shift** while drawing another loop to add to the existing selection. **Shift-click** also toggles individual terminal tips in or out of a multi-selection.

**Zoom to selected** now fits all visible selected taxa when more than one tip is selected. **Deselect all** clears the selection. Lasso mode temporarily replaces drag-to-pan behavior; turn it off to restore ordinary panning.

A multi-selection is local to Tree Studio because the parent WINGS Explorer currently has a single-record selection model. Single-tip clicks continue to synchronize back to the parent Explorer. Deselect all also clears the synchronized parent selection.

Lasso selection is a display interaction only. It does not prune the tree, alter topology, change branch lengths, reroot the source tree, or create an epidemiological grouping.

## v0.1.7: zoom to selected

Tree Studio now provides **Zoom to selected** for terminal WINGS and public-reference tips. The action recenters the current layout around the selected tip and zooms to a contextual neighborhood. If the current view is already more deeply zoomed, it recenters without zooming back out. **Fit** restores the full displayed tree. The operation changes only the browser view box.

## v0.1.6: canonical U.S. state traits


Tree Studio now canonicalizes U.S. state names and postal codes before trait coloring and filtering. For example, `Kentucky`, `KY`, and `US-KY` are one `KY` trait value rather than three categories. The source string is preserved separately for audit/export. This normalization covers the 50 states, District of Columbia, and common U.S. territories. Values not recognized as U.S. states are left unchanged.

The smoother pointer-centered wheel/trackpad zoom introduced in v0.1.5 is retained.

Tree Studio is a browser-only, offline-capable phylogenetic viewer for segment trees already present in the WINGS Surveillance Explorer. It does **not** rerun MAFFT, IQ-TREE, GenoFLU, or any upstream analysis, and it never overwrites source Newick files.

## Interactive tree features

The Genome tab provides **Open Tree Studio ↗**. The pop-out supports:

- PB2, PB1, PA, HA, NP, NA, MP, and NS switching when those trees are present.
- Rectangular, radial-rooted, and unrooted equal-angle displays.
- As-supplied orientation, midpoint display rooting, and user-selected outgroup display rooting.
- Source order, ascending/descending ladderization, and collection-date ordering.
- Tip coloring by GenoFLU genotype, host, country, state, collection date, or WINGS/public-reference source.
- Optional branch coloring by descendant consensus for categorical traits.
- Tip labels by selected/search-only focus, sample/reference ID, source tree tip, accession, isolate, host, or genotype.
- Automatic large-tree label decluttering until the user zooms in.
- Recorded numeric internal support labels on/off; support defaults to hidden for large trees.
- Tip search, click/keyboard selection, **freehand lasso multi-selection**, Shift-click additive selection, pan, gentle pointer-centered wheel zoom, **Zoom to selected**, **Deselect all**, and fit-to-view.
- SVG, PNG, displayed Newick, and metadata TSV export.
- Initial selection synchronization from the parent Explorer and terminal-tip selection synchronization back to the parent Explorer.

## Trait filtering

Tree Studio provides a **Filter trait** control for:

- GenoFLU genotype
- host
- country
- state (U.S. names/codes canonicalized to postal abbreviations)
- WINGS versus public-reference source

After selecting a trait, Tree Studio lists the observed values and their tip counts in the Tree evidence panel. Clicking a value toggles it into or out of the active filter.

The display uses these semantics:

- One selected value means tips with that value are emphasized.
- Multiple selected values use **OR** logic.
- Nonmatching tips are shaded; they are not removed from the tree.
- A branch remains emphasized if at least one descendant tip satisfies the active filter.
- A branch with no matching descendants is shaded.
- Missing categorical metadata are represented explicitly as `Not recorded / not assigned` and may be filtered as a separate value.
- Search and trait filtering can be used simultaneously; a tip or branch is emphasized only when it remains relevant to both active display constraints.
- Tip coloring and filtering are independent. For example, a user can filter to genotype D1.1 while coloring the retained context by host.

The tree status line shows the number of matching tips while a filter is active, such as `filter 37/280`.

Trait filtering is deliberately **non-destructive**. It does not prune source Newick, recompute the topology, alter branch lengths, or change WINGS analytical outputs.

## Interpretation safeguards

Tree Studio is a display layer over existing WINGS trees.

- The as-supplied view does not claim that the IQ-TREE topology has a biological root. Midpoint and outgroup rooting are display transformations only.
- The unrooted option is an equal-angle topology display. The root is not interpreted in that mode.
- Ladderization and collection-date ordering affect presentation only, not topology or branch lengths.
- Numeric internal labels are shown exactly as recorded by the WINGS tree parser. Rerooting does not recompute support.
- “Descendant consensus” branch coloring is a visual summary. A branch receives a trait color only when all annotated descendant tips share that categorical trait. It is **not** ancestral-state reconstruction.
- Trait filters summarize supplied metadata; they do not establish transmission, adaptation, ecological association, or causation.
- Collection dates are metadata. Tree Studio does not time-calibrate a phylogeny.

## Install

From the WINGS repository root, unpack the kit outside the repository and run the installer in dry-run mode first:

```bash
TREE_KIT="$(mktemp -d)"
unzip -q "$HOME/Downloads/wings_tree_studio_v0.1.9.zip" -d "$TREE_KIT"

python "$TREE_KIT/wings_tree_studio_v0.1.9/install_tree_studio.py" \
  --repo .
```

If the file list is expected, apply it:

```bash
python "$TREE_KIT/wings_tree_studio_v0.1.9/install_tree_studio.py" \
  --repo . \
  --apply
```

The installer replaces the marked Tree Studio JavaScript/CSS blocks already present in the Surveillance Explorer and keeps the existing mount hook. It creates backups outside the repository. It does not touch the Snakefile, `config.yaml`, README, source sequence data, phylogenies, or generated analysis results.

## Tests

```bash
node --test tests/test_tree_studio.cjs \
  tests/test_explorer_tabs.cjs \
  tests/test_genome_braid_clock.cjs

git diff --check
```

The kit also contains a Playwright/Chromium smoke test using synthetic data:

```bash
python tests/browser_tree_studio.py
```

## Rebuild only the report layer

```bash
snakemake results/wings_report_bundle.wings \
  --configfile config.yaml \
  --sdm conda \
  --cores 4 \
  --resources mem_mb=90000 kaleido=1 \
  --allowed-rules run_summary_html wings_report_bundle \
  --forcerun run_summary_html
```

Then open `results/run_summary/run_summary.html` and go to **Genome → Open Tree Studio ↗**.

## Current scope

Tree Studio v0.1.9 intentionally does not perform ancestral-state reconstruction, molecular-clock inference, formal rerooting of saved trees, topology comparison, reassortment inference, or tree re-estimation. Internal branch/clade selection is also not implemented yet; selection applies to terminal tips. Those capabilities should remain explicit additions rather than being implied by the visualization.
