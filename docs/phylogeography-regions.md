# Regional phylogeography display

The viewer opens in Regional overview. Kentucky remains separate. Choose a region and click **Expand selected region**, or choose **Individual locations** to restore all original locations. The same grouping applies to the map, tree colors, ancestral probabilities, directed chord diagram, entry timeline and reference-sampling comparison.

## Group definitions

- U.S. Northeast, Midwest, South and West follow Census regions, with Kentucky removed from South and shown separately.
- International locations use UN M49: Northern America outside the U.S.; Latin America and the Caribbean; Europe; Asia; Africa; Oceania. Antarctica is separate.
- Canadian provinces retain their identity when expanded. U.S. territories follow their international geographic grouping when their own country/territory code is supplied.
- Unrecognized identifiers and country-only U.S. records remain separate. No region is inferred from coordinates.
- Bundled Natural Earth compatibility identifiers: SAH, SDS and SOL map to Africa; PSX, CYN and TWN to Asia; KOS to Europe. These display assignments do not change recorded identities or sovereignty claims.

Sources: [U.S. Census geographic definitions](https://www.census.gov/data/data-tools/survey-explorer/geo.html), [UN M49](https://unstats.un.org/unsd/methodology/m49/overview/), retrieved 2026-11-16.

## Calculation

This is a projection of existing posterior histories, not a new geographic model. Original root priors, rates, dates, topology, chain weights, input data and diagnostic gates are unchanged. Source results.json retains original locations.

For every retained history, replace each location with its display group and remove transitions within a group. Then calculate group probabilities, mean counts, equal-tailed 95% count intervals and P(0 entries). Zero-entry histories are included. Component intervals are never added. Kentucky entry counts are identical before and after grouping.

Each reference replicate is summarized separately. Replicates are not pooled. A group missing from a replicate is unavailable, not zero. Partial member coverage is labeled; member counts refer to locations represented in the loaded analyses, not every jurisdiction in the geographic region.

Regional map markers are fixed display anchors, not inferred ancestor coordinates or flight paths. Display grouping does not correct sampling bias. A projected process is not asserted to be a newly fitted equal-rate Markov model. Original Monte Carlo checks apply to the source inference; no new group-specific precision gate is claimed.

## Install and rebuild

This installer targets the previously installed WINGS_REPORT_ONLY_V3 report workflow and checks the supported source files before changing anything. It updates only the viewer, styling, regional tests and this document. Existing differing local files cause an error before any edits. Backups are written under ~/.wings/code-backups/.

```bash
python ~/Downloads/wings_add_regional_phylogeography_v1.py --repo . --apply
snakemake --snakefile Snakefile.phylogeography-report \
  --configfile config.yaml config/phylogeography-results.example.yaml \
  --use-conda --cores 4
open results/run_summary/phylodynamics/results/fast_v1/index.html
```

Use the isolated report Snakefile. With saved report inputs unchanged, this viewer update requires only report generation, not biological inference or sequencing.

## Validation

Six existing viewer tests and eight regional regression tests run before installation. Checks cover all 51 U.S. state/DC boundaries, bundled international identifiers, unchanged Kentucky counts, original-history validation, per-history grouped intervals, zero counts, reversible expansion, BEAST date/chain preservation and agreement across the displayed summaries. Browser checks used synthetic Fast/BEAST fixtures with 30 WINGS tips, playback, member drill-down, unavailable-method handling and a 390-pixel mobile viewport. No biological analysis was run by the installer.
