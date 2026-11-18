# Summary and posterior-draw views

The default Posterior summary colors each ancestor by its highest marginal posterior location probability. Click the ancestor to inspect all probabilities. Ties are resolved deterministically by location identifier and identified in the tooltip. Fast uses fixed dated-tree dates; BEAST uses median node dates. Gray summary branches do not show a reconstructed jump path. Independently chosen modal states do not constitute a joint most-probable history.

The summary map and directed chord diagram show posterior mean Markov-jump counts through the selected date. The map shows up to 12 strongest routes entering or leaving the focus location; the chord diagram retains all routes and emphasizes those connected to the focus.

Advanced → Explore uncertainty provides One posterior draw. The number selects a complete reconstruction, not one jump. A draw can contain zero or many jumps. The map, tree and chord all use the same draw and selected date. Node colors show that draw's locations; branch-color changes show its jumps. BEAST additionally shows the source chain and MCMC state. Fast uses a conditional geographic draw on the fixed dated tree. The first retained draw is the default, not a ranked best or median reconstruction.

In draw mode, the ancestor panel explicitly shows **This draw: [location]** above **Across all posterior draws**. Entry cards, probability bars, entry timelines and reference comparisons remain posterior summaries and are labeled accordingly. Closing the advanced controls or changing method/reference returns to Posterior summary. Regional display aggregation still excludes within-region jumps and preserves Kentucky entry counts.

Only rendering and documentation change. Inference, posterior files, diagnostic gates and source data are unchanged. Use the isolated report workflow to rebuild:

```bash
snakemake --snakefile Snakefile.phylogeography-report \
  --configfile config.yaml config/phylogeography-results.example.yaml \
  --use-conda --cores 4
```

Validation: 17 Node regression tests plus browser checks of summary modes, individual-draw states, matching map/chord counts, BEAST chain labels, regional expansion, disclosure/method resets and mobile layout. A contrasting synthetic fixture verifies a Midwest 55% modal state while the first draw assigns West (5%). These are software checks, not new biological analyses.
