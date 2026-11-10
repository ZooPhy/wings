# Explorer asset development

Explorer modules now have one source of truth. Previously the standalone module
files and copies embedded in `surveillance-explorer.js` could diverge. The initial
migration takes the reviewed embedded implementation and promotes it to the
standalone sources. It verifies that the complete production JavaScript and CSS
remain byte-for-byte identical. Existing HTML reports and `.wings` bundles are
not rewritten.

## Editing and building

The source/output map is `scripts/report/explorer-assets.json`.

| Change | Edit |
| --- | --- |
| Tabs, tree studio, braid clock, concordance, migration weave, evidence synthesis | Corresponding `.js` module in `scripts/report/` |
| Core Explorer logic and module mounting hooks | `scripts/report/templates/surveillance-explorer.js.tpl` |
| Core Explorer styles and stylesheet order | `scripts/report/templates/surveillance-explorer.css.tpl` |
| Tab layout styles | `scripts/report/templates/explorer-tabs.css.tpl` |
| Braid clock, tree studio, shared concordance styles | Corresponding `.css` source in `scripts/report/` |

Run from the repository root:

```sh
python scripts/build_explorer_assets.py --write
python scripts/build_explorer_assets.py --check
```

The builder uses Python's standard library. It needs no npm packages or network
access. Without options it previews which generated files differ.

Commit source/template edits together with these generated outputs:

- `scripts/report/surveillance-explorer.js`
- `scripts/report/surveillance-explorer.css`
- `scripts/report/explorer-tabs.css`

The report renderer continues to consume the same production asset paths.
Report generation does not invoke this developer build step automatically.
After a UI change, rebuild the assets before regenerating reports and bundles.
No Snakefile, sample metadata, pairing settings, or analysis outputs are modified
by the asset migration or builder.

## Includes and CSS order

Templates use `@@WINGS:scripts/report/module.js@@` includes. The manifest declares
allowed sources and generated outputs. The builder rejects unknown includes,
cycles, unresolved directives, and paths outside the checkout.

The existing Explorer stylesheet places concordance styles in two locations.
Both placements and their order are retained to preserve the CSS cascade; both
now use `genomic-ecological-concordance.css`. Its `#base`, `#summary`, and
`#takeaway` include selectors divide that source at the existing compact-summary
markers. Keep those markers when editing the stylesheet.

## Checks

```sh
python -m unittest discover -s tests -p test_explorer_asset_build.py -v
node --test tests/test_amino_explorer_tab.cjs tests/test_explorer_module_runtime.cjs tests/test_explorer_tabs.cjs tests/test_genome_braid_clock.cjs tests/test_genomic_ecological_concordance_ui.cjs tests/test_tree_studio.cjs
```

The new Python checks cover deterministic generation, drift detection, propagation
of JavaScript and shared CSS edits, and invalid include rejection. The new Node
tests mount tabs with a minimal DOM fixture, exercise the seven views, preserve
the Overview briefing and Sampling panels, and reset tree-tip selection. A
negative control reproduces the original undeclared `subtitle` error. The
existing module tests are run alongside them. These are automated module/DOM
fixture checks, not a full browser rendering test.

The `explorer-assets.yml` GitHub Actions workflow runs on Linux and macOS after
the files are committed and pushed.

## Migrating existing checkouts

`wings_update_explorer_assets.py` previews by default, stages and tests all changes
before applying, preserves file modes, and creates a backup on `--apply`.
`--check` verifies the installation, generated assets, and regression suite.
The updater refuses an unrecognized difference between standalone and embedded
modules instead of discarding local work. It also refuses to overwrite existing,
different files at newly introduced paths.

The five legacy module installers (`install_braid_clock.py`,
`install_explorer_tabs.py`, `install_tree_studio.py`,
`install_dynamic_phenology.py`, and `install_amino_explorer_tab.py`) stop when
the new manifest exists. Use the
canonical sources and builder for future changes. This prevents their older
insertion logic from rewriting the Explorer after migration.

The amino tab is maintained in `scripts/report/explorer-tabs.js` and included
once in the generated Explorer bundle. Its occurrence in both the source and
bundle is expected. Do not update it by rerunning a legacy installer. The amino
regression suite exercises lazy iframe mounting, retained state, height-message
validation, legacy report discovery, and empty states against both copies.
The builder tests verify that rebuilding preserves the exact canonical module.
See [Amino acids in Surveillance Explorer](amino-acid-explorer-tab.md) for saved
report refresh guidance.
