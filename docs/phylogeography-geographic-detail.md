# Geographic detail

The toolbar has one detail selector: **Regions** or **States and countries**. It applies to the map, tree locations, chord diagram, focus selector and entry summaries. Regions remains the default and keeps Kentucky separate.

The former Expand selected region and Regional overview buttons are removed. The membership disclosure is read-only; it no longer expands one region or selects individual members. This replaces the earlier per-region expansion interface described in phylogeography-regions.md.

Switching detail preserves the selected posterior draw and date. An individual focus maps back to its parent region; switching a focused region to individual locations selects its first represented member. Focus location can then select another member. Within-region jumps are excluded in Regions and restored in States and countries. Kentucky counts are unchanged.

This is a display update. Existing inference, source posterior histories, primary-set policy and checks are unchanged. Rebuild with Snakefile.phylogeography-report.
