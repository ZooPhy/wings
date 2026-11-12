# Explorer navigation

Surveillance Explorer uses a grouped navigator in place of its horizontal tab
row. Overview remains a direct destination; Genomics contains Genome, Amino
acids and Genotype frequencies; Ecological context contains Ecology, Sampling
& Detections and Outbreak context; Integrated evidence contains Concordance.
These groups describe navigation, not inferred biological relationships.

Pipeline Results uses the same navigator for Run Summary, Sample Detail,
Subtype/Genotype Distribution and Genome Coverage. The two top-level choices,
Pipeline Results and Surveillance Explorer, remain unchanged. Pipeline
navigation moves the existing Quarto tab links and panels; it does not recreate
tables, sample links or chart controls. Existing active panels, Bootstrap tab
notifications, keyboard navigation and filter state are retained. The shared
navigator omits the helper sentence and view-count footer.

Groups start expanded. Click a group heading to collapse it. Selecting a view
through another report action automatically opens its group. The active view
has a gold node and button, bold black text and a black outline. The palette is
ASU maroon `#8C1D40`, gold `#FFC627`, black `#000000` and white `#FFFFFF`.

The outer navigation landmark uses `<nav>` because Quarto assigns `<aside>`
elements to its named margin columns with an `!important` rule. The navigator
and report also have explicit grid placement: columns one and two on desktop,
and rows one and two on smaller screens.

Reports containing the Explorer use Quarto's full screen grid span, with a
12-pixel outer gutter. The desktop navigator is 252 pixels wide with a
14-pixel gap; the main report receives the remaining space. The amino view
omits an extra surrounding padding layer because its embedded document
already supplies its own spacing. These layout overrides are scoped to reports
containing the Explorer and do not change standalone sample reports.

On smaller screens, **Explore views** opens the navigator and identifies the
current view. Escape closes it and restores focus. Up/Down (and Left/Right)
move among visible destinations; Home/End select the first/last destination.
Reduced-motion preferences disable the short highlight transitions.

The navigator reuses the existing view panels and selection controller. The
amino iframe remains mounted after its first activation. Navigation changes
do not recalculate analyses or change embedded report evidence.

Edit `scripts/report/explorer-view-navigator.js`, `explorer-tabs.js`, and
`scripts/report/templates/explorer-tabs.css.tpl`, then regenerate with:

```bash
python scripts/build_explorer_assets.py --write
python scripts/build_explorer_assets.py --check
node --test tests/test_explorer_navigation.cjs tests/test_amino_explorer_tab.cjs
```

Pipeline-specific panel wiring is in `scripts/report/pipeline-view-navigator.js`.

Individual sample reports use section links rather than hiding their evidence.
Their navigator groups read processing, sequence evidence, outputs and
provenance. Additional sections from older/newer reports remain accessible.
The legacy standalone IRMA candidate-selection section and its navigation
entry are omitted from the displayed report. Candidate-selection provenance
remains in the existing QC constellation and recorded data.
The standalone sample Interpretation section is also omitted. Consensus and
variant files use a short introduction, with the original Medaka status
definitions retained under a collapsed **Status guide**. Per-segment status
values, files and failure flags remain unchanged.
The sample metadata table is presented as a collection profile with a date
badge, recorded host and specimen, location, sample ID and any additional
metadata fields. Metadata-status and Medaka-status/provenance rows are omitted
from this profile. The redundant Metric/Value summary table is removed; QC,
processing and provenance details remain in their dedicated sections. Dates
are formatted only when they are valid ISO calendar dates; other values stay
as recorded.

GenoFLU uses an eight-segment constellation in maroon, gold, black and white.
It reads the existing segment-call table and recorded genotype label. Missing
segment calls remain unavailable, and an overall **Not assigned** or **Not
run** status is retained independently of how many segment calls are present.
Selecting a segment shows only its recorded call; the overall assignment and
call count stay in the wheel's center. The original result text and table
remain under **Recorded result and segment table**, with existing filters and
downloads preserved. This presentation adds no genotype assignment or other
biological inference.
**Back to run summary** uses the standard relative path from
`<sample>/summary/<sample>.sample_summary.html` to `run_summary/run_summary.html`.
The existing sample tables, filters and section nodes remain intact.

Sample navigation is generated into `sample-navigation.js` and
`sample-navigation.css` from the shared navigator and layout sources. The
sample-report rendering rule copies these assets alongside the other report
resources before Quarto embeds them.

D3 hierarchy 3.1.2 is bundled locally, including its ISC license, under
`scripts/report/vendor/`. It comes from the official D3 website repository
(`d3/d3.github.com`, `d3-hierarchy.v3.min.js`). No CDN or internet connection is
required. D3 builds the hierarchy and links; native HTML buttons provide the
interactive labels. Already generated HTML reports and `.wings` bundles must
be explicitly refreshed to use the new assets.

The bundled D3 UMD loader runs in a local wrapper that shadows AMD/CommonJS
loader names. This ensures sample reports that load RequireJS still receive
the browser D3 object. Existing RequireJS functions and CommonJS globals are
left intact; no anonymous D3 module is registered with the report's loader.

To update a saved report tree without rerunning analyses:

```bash
python scripts/refresh_saved_explorer_ui.py --repo . \
  --input-dir results/ebird-refresh-20261110-fixed \
  --output-dir results/ebird-refresh-20261110-navigator
```

The updater validates the new script, preserves embedded evidence and sample
HTML, verifies the bundle round-trip and writes a separate output tree. The
input HTML must match the input bundle. Serve the new output directory with a
local web server to avoid Safari's restrictions on navigation between local
files. A navigation-refresh record is written separately from the original
analysis provenance.

To update sample pages and remove the visible context-refresh banner, add
`--refresh-samples --remove-refresh-notice`. Sample HTML files must also match
their bundled copies. The updater modifies their presentation and updates both
the individual files and bundle; original analysis provenance and embedded
evidence remain. Refresh provenance remains recorded in JSON after the banner
is removed. Without these options, sample files retain their original bytes.

Collection metadata uses four compact rounded cards: date, host, specimen, and
location. Recorded latitude and longitude stay together inside the location
card, without rounding or duplication. The cards wrap based on the report
content width. Additional metadata remains in smaller cards.

Host cards include the matching drawing from `assets/birds/`, with the species
name and exact recorded host value. The offline catalog supports all 173 supplied
drawings, four-letter host codes, common names, and the five current eBird taxon
codes. Unknown or conflicting host values keep their text without a guessed image.
Original SVG bytes, including metadata, are preserved. The generated catalog is
embedded in sample navigation, so portable reports need no external image requests.

After changing drawings, rebuild and verify both asset layers:

```bash
python scripts/build_bird_assets.py
python scripts/build_bird_assets.py --check
python scripts/build_explorer_assets.py --write
python scripts/build_explorer_assets.py --check
```

The bundle viewer covers the iframe with “Preparing report…” during each report
load and reveals it after the load event and two animation frames. This applies
to the demo, samples, and return navigation. Pending reveal callbacks cannot
uncover a newer report load. Standalone HTML reports do not use this viewer cover.

Collection-location cards also embed matching drawings from `assets/states/`,
named like `Kentucky_KY.svg`, `New_York_NY.svg`, and `Ontario_ON.svg`. US state
names and postal codes match when the recorded country is US, USA, United States,
or United States of America. All 13 Canadian provinces and territories match
when the recorded country is CA, CAN, or Canada. Country-specific lookup prevents
matching a Canadian drawing to a US location or vice versa. Quebec and Québec
both match QC. Metadata may use State, Province, Territory, Province/Territory,
or State/Province as its region field. Punctuation and case do not affect matching. Missing or unsupported
locations keep their recorded text. Coordinates are unchanged. Drawings are
decorative; location text remains available if an image cannot be displayed.

Build the state catalog before rebuilding the report assets:

```bash
python scripts/build_state_assets.py
python scripts/build_state_assets.py --check
python scripts/build_explorer_assets.py --write
python scripts/build_explorer_assets.py --check
python scripts/refresh_demo_navigation.py --repo . --apply
python scripts/refresh_demo_navigation.py --repo . --check
```

Commit the SVG sources, generated `assets/states/state-artwork.js`, and regenerated
sample-navigation JS/CSS together. Existing saved reports can use the same
`refresh_saved_explorer_ui.py --refresh-samples` process as bird artwork.

To make the published demo use the current summary navigation and sample cards:

```bash
python scripts/refresh_demo_navigation.py --repo . --apply
python scripts/refresh_demo_navigation.py --repo . --check
```

This supports the tracked `demo/wings_demo.wings.gz` on its own and updates an
uncompressed copy too if one exists. Original demo files are backed up outside
the repository. Sample data, embedded evidence, provenance and original report
dates are preserved; only presentation assets and visible refresh notices are
updated. Reload the refreshed demo bundle in the viewer to see the changes.
