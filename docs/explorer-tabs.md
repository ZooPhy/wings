# WINGS tabbed Surveillance Explorer

This additive UI layer reorganizes the existing Surveillance Explorer into four views without changing analytical outputs:

- **Overview** — collection timeline and map.
- **Genome** — Genome Braid first; the existing individual segment trees and QC evidence are retained in a collapsed disclosure.
- **Ecology** — the existing ecological context panel, including the Ecological Clock preview and source-specific context.
- **Outbreak context** — the existing USDA APHIS context panel and source records.

A compact global Sample/Host toolbar controls the existing Explorer state. Selecting a sample in any existing view remains synchronized because the module moves existing DOM nodes rather than recreating analytical content.

The Genome Braid's duplicate sample/host controls are hidden only in embedded mode; Load phenology and Export evidence remain available. The existing Genome panel's duplicate sample selector and clear button are also hidden. Public-reference and tree-view controls remain available inside the expandable detailed Genome section.

## Install

From the WINGS repository root, unpack the kit elsewhere and inspect the dry run:

```bash
python /path/to/wings_explorer_tabs_v0.1/install_explorer_tabs.py --repo .
```

Apply only after the file list looks correct:

```bash
python /path/to/wings_explorer_tabs_v0.1/install_explorer_tabs.py --repo . --apply
```

The installer requires the Genome Braid hook already present. It does not change the Snakefile, config, README, sequence data, results, or phylogenies.

## Test

```bash
node --test tests/test_explorer_tabs.cjs tests/test_genome_braid_clock.cjs
git diff --check
```

Then use the existing report-only rebuild path so upstream genomics are not recomputed during UI evaluation.

## Design notes

The tab layer intentionally preserves one selected record across views. It does not introduce new scientific metrics, recalculate trees, or alter data provenance. Moving the APHIS record browser out of the Overview map does not change its source data; a View records action switches to the Outbreak context tab.


## v0.1.1: Genome / Ecology split

The Genome Braid and Ecological Clock remain one live component so sample selection, host filtering, imported phenology, and evidence state stay synchronized. The tab shell presents different lenses of that single component: the Genome tab shows the braid/evidence view, while the Ecology tab shows the Ecological Clock above the existing eBird, migration, and weather context. The component is not duplicated.
