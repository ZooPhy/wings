# Phylogeography movie

The **Phylogeography movie** view plays dated geographic histories alongside
their segment tree. It shows samples on their collection dates, directional
Markov-jump counts, a cumulative introduction curve, and the count distribution
at the current date. Click a visible tree node, or choose a node in **Inspect
nodes and transitions**, to see state probabilities. Nodes carrying a matching
`sample_id` also select that WINGS sample. Choosing a geographic route highlights
the branches supporting it.

This module visualizes existing reconstructions. It does not infer a dated tree,
fit a migration model, or derive histories from ML node labels. Reports without
reconstruction data open with a **Load reconstruction** control and an optional,
explicitly synthetic example. The example is never attached to run evidence.

## Play a reconstruction

1. Open **Genomics → Phylogeography movie**.
2. Load a JSON file using the schema below.
3. Select a segment and focal destination.
4. Choose **Posterior summary** or **Sampled history**; play or scrub the date.

Loading JSON affects this browser view only. Retain the input file to reload it.
Reports can embed the same JSON object as `phylogeography` in their Explorer
payload for automatic loading; never put demonstration data in a real payload.

## Export a movie

**Export video** records the full selected segment at normal speed, including
the tree, map, date, count distribution, and uncertainty label. It uses MP4 where
the browser supports recording MP4, otherwise WebM. Keep the page visible during
recording; hiding the page or changing tabs stops it and saves the partial video.
Click **Stop export** to save a shorter recording.

For a deterministic MP4 independent of browser recording codecs:

```bash
npm install --no-save playwright
npx playwright install chromium
# Install ffmpeg separately; on macOS: brew install ffmpeg
node scripts/render_phylogeography_movie.cjs \
  --input reconstruction.json --output phylogeography.mp4 \
  --segment HA --target KY --seconds 20 --fps 24
```

Use `--mode history --history 0` for one history, or `--example` instead of
`--input` for a watermarked synthetic movie. The command refuses to overwrite
an existing output. It renders locally and makes no map/network requests.

## Data contract

Schema: `wings.phylogeography-movie.v1`. This first version accepts one fixed,
rooted, dated tree per segment, geographic traits, and equally weighted histories
after burn-in. Different tree topologies across draws and weighted samples are
not supported. Combine independent converged chains only after applying burn-in.
The viewer cannot assess convergence or effective sample size; assess those in
the inference software before importing.

```json
{
  "schema": "wings.phylogeography-movie.v1",
  "title": "Study location histories",
  "synthetic": false,
  "provenance": {
    "method": "BEAST fixed-tree discrete-trait analysis",
    "inference": "bayesian",
    "uncertainty": "conditional-on-fixed-tree"
  },
  "locations": [
    {"id": "OH", "label": "Ohio", "lat": 40.4, "lon": -82.8},
    {"id": "KY", "label": "Kentucky", "lat": 37.7, "lon": -85.3}
  ],
  "segments": [{
    "id": "HA",
    "nodes": [
      {"id": "root", "parent": null, "date": "2025-01-01"},
      {"id": "tip1", "parent": "root", "date": "2025-04-15",
       "observed_state": "KY", "sample_id": "your-sample-id"}
    ],
    "histories": [
      {"id": "draw0", "root_state": "KY", "jumps": []},
      {"id": "draw1", "root_state": "OH", "jumps": [
        {"branch": "tip1", "date": "2025-03-10T12:30:00Z", "from": "OH", "to": "KY"}
      ]}
    ]
  }]
}
```

The tiny JSON is a schema illustration, not a sufficient posterior sample.
Use `inference: "empirical-bayes"` for maps drawn conditional on fitted rates;
the UI then says *mapping interval*, not Bayesian credible interval. Use
`synthetic: true` with `inference: "synthetic"` for constructed examples.

- Dates are UTC `YYYY-MM-DD` or ISO timestamps ending in `Z`.
- `branch` identifies its child node. Events must be after the parent and at or
  before the child date. Root locations are supplied per history.
- Histories contain **every jump**, including reversals, and must agree with
  observed tip states. All tips require `observed_state`.
- Include zero-jump histories as empty arrays. Omitting them biases counts upward.
- `sample_id` links an actual WINGS sample; omit it for unrelated background tips.
- Coordinates are supplied geographic-state representatives, not inferred
  collection coordinates or actual migration routes.
- Limits: 20 MB upload, 8 segments, 5,000 nodes and 10,000 histories per segment,
  1,000,000 node × history combinations per segment, and 500,000 jumps overall. Subsample posterior draws independently of their
  transition counts when reducing file size.

## Import tab-separated histories

`build_phylogeography_movie.py` packages these four tables and validates the
result with the same validator used in the browser:

| File | Columns |
|---|---|
| `nodes.tsv` | `segment`, `id`, `parent`, `date`; optional `label`, `sample_id`, `observed_state` (required for tips) |
| `histories.tsv` | `segment`, `history`, `root_state`; one row for **every** retained draw |
| `jumps.tsv` | `segment`, `history`, `branch`, `date`, `from`, `to` |
| `locations.tsv` | `id`, `label`, `lat`, `lon` |

Leave the root's parent field blank. Preserve the inference tree's node IDs.
Dates must be derived from the same dated tree and mapped histories. BEAST node
labels alone are insufficient: export complete Markov-jump histories and convert
backward ages to forward calendar dates using that analysis's time origin.
The importer expects these normalized tables; it does not parse arbitrary BEAST
NEXUS files or infer missing transition histories.

```bash
python scripts/build_phylogeography_movie.py \
  --nodes nodes.tsv --histories histories.tsv --jumps jumps.tsv \
  --locations locations.tsv --method "BEAST fixed-tree DTA" \
  --inference bayesian --output reconstruction.json
```

## Interpretation

For each history, WINGS counts jumps into the focal state through the displayed
date. The summary is the arithmetic mean over draws, including zeros; the interval
uses empirical 2.5% and 97.5% quantiles. Re-entry counts as another introduction.
The root already being inside the focal state does not itself count as an entry.
The curve includes the full time range; its cursor marks the movie date.

Counts describe state transitions in the ancestry of sampled sequences, not all
introductions into the population. They are conditional on the tree, model,
geographic grouping, and background sampling. Tree uncertainty is not represented.
Each influenza segment is displayed separately; do not sum across segments.

Map arrows show cumulative expected jumps, or integer jumps in one history.
Node colors become less saturated with greater state uncertainty. The selected
node's full probability distribution is available under Inspect. Long trees are
shown 20 tips at a time; choosing a tip navigates to its page while counts always
use the full imported tree. State-centroid connections are not flight paths.

## Checks

```bash
node --test tests/test_phylogeography_movie.cjs
node tests/test_phylogeography_movie_browser.cjs
```

The browser check requires Playwright/Chromium. Set `WINGS_CHROMIUM` when using a
system browser. Export requires ffmpeg. No inference software is needed to play
an already computed reconstruction.
