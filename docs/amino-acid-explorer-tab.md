# Amino acids in Surveillance Explorer

The Amino acids tab follows Genome. Saved reports are embedded as a portable
template and loaded on first activation; tab switches retain cohort, wheel,
zoom and filter state. The report has its own sample controls and defaults to
All samples / at least 80%.

## Canonical asset development

Edit `scripts/report/explorer-tabs.js` for tab and iframe mounting behavior.
Edit `scripts/report/templates/surveillance-explorer.js.tpl` for core Explorer
hooks. Build and verify the committed production assets:

```sh
python scripts/build_explorer_assets.py --write
python scripts/build_explorer_assets.py --check
node --test tests/test_amino_explorer_tab.cjs
```

The legacy `install_amino_explorer_tab.py` is disabled when
`scripts/report/explorer-assets.json` exists. It remains available only for
older, unmigrated checkouts. It must not rewrite a migrated checkout's source,
production assets, analysis script, or saved reports.

## Refresh saved reports

Building assets does not update the JavaScript embedded in existing HTML or
`.wings` reports. To refresh the demo's UI when its amino report is already
embedded, run:

```sh
python scripts/refresh_demo_ui.py --apply
```

This refreshes report assets; it does not add missing amino results or change
existing amino HTML. To add an already generated amino report to a run-summary
HTML file, use the existing embed command with your actual paths:

```sh
python scripts/wings_amino_acids.py embed \
  --report /path/to/run_summary.html \
  --amino /path/to/amino_acid_landscape.html
```

The embed command changes the HTML file in place. Back it up first, and rebuild
the portable report bundle afterward if you distribute `.wings` files. For
newly rendered run summaries, use the normal reporting workflow so they consume
the current generated Explorer assets. Do not use the legacy installer as a
report refresh command on migrated checkouts.
