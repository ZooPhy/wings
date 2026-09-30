# Genome Braid and Ecological Clock: research preview v0.1.0

This is an additive, offline visualization and descriptive-analysis module. It
consumes an existing `surveillance_explorer.json`. It does not run sequencing,
genotyping, reference selection, tree inference, weather retrieval, or eBird
retrieval. It does not change the supplied tree topology or branch lengths.

## What is implemented

**Genome Braid.** Eight lanes use the existing annotated tree leaves. A strand
connects the same explicit sample identity across adjacent available segments.
Public groups use their supplied `reference_id`, and squares distinguish them
from samples. Missing trees, absent tips, and multiple tips per identity remain
distinct. No strand bridges a missing lane. The source JSON is not mutated.

Positions follow supplied tip order after restricting to displayed records.
Rotating a tree can change its braid crossings without changing phylogeny. Do
not interpret crossings as inferred reassortment, movement, or transmission.
Up to 60 local samples and 36 public groups are drawn, plus selected focus. The
cap is a visual bound in source order, not an analytical reference-selection
method. The neighborhood metric uses the full local sample cohort, not this cap.

**Descriptive shared-neighbor overlap.** For a selected WINGS sample and each
pair of segment trees, compare its three nearest other local WINGS samples using
path-length distances within each tree. The comparison uses only identities
with exactly one tip present in both trees. Public groups are excluded from the
metric because their cross-segment identity can be algorithmic rather than
independently established. Distances are ranked within trees, never pooled across
segments. Report the Jaccard overlap of the two size-three sets and an unweighted
mean over available pairs (maximum 28).

A boundary tie, missing/negative branch length, unavailable focal sample, or
fewer than four other shared samples makes a pair unavailable. It is not scored
zero. No threshold based on support labels is used: support methods are not
assumed comparable. This is NOT a calibrated probability, phylogenetic discordance
test, reassortment detector, clade assignment, or biological-risk score. Small
comparison cohorts have a high chance-overlap baseline, which v0.1 does not
calibrate. Treat it as a diagnostic, not a finding. Reference-panel sensitivity,
bootstrap uncertainty, and repeat-specimen handling require further development.

**Ecological Clock.** Calendar and ecological-time views share the selected
sample with the braid. Each documented host/region/season profile can use an
explicit supplied anchor interval or the interval containing the maximum
supplied bin. With an inferred bin anchor, at least three nonmissing bins are
required; a zero/flat profile or separated equal maxima leaves the anchor
unavailable. A contiguous maximum plateau retains its entire date interval.
This is the *peak of the supplied bins*, not a claim about the true biological
peak, arrival, infection, or introduction date.

Let a collection date occupy [c0,c1] and an anchor occupy [a0,a1]. The displayed
offset interval is [c0-a1, c1-a0], in UTC calendar days. Partial month/year dates
retain their width. Weekly-bin width is temporal resolution, not a confidence
interval. An expected seasonal reference is distinguished from year-specific
estimates. Curves use individual bin rectangles; missing bins are not zero,
interpolated, or extrapolated. Profile bar heights are normalized within rows
and must not be compared as abundance across species or different measurements.

The initial scope match is host + country + state + full collection-date interval
within the supplied season. Whitespace/case are normalized and common USA names
are aliased, but no host taxonomy, state-code mapping, centroid, nearest season,
or annual recurrence is inferred. More than one match remains ambiguous. Use
reviewed keys explicitly when supplying profiles. Unknown bird settings are
not automatically labeled wild. Specimen identity is not deduplicated here.

## Standalone report from real WINGS data

After installation, from the WINGS root:

```bash
python scripts/build_braid_clock_report.py \
  --explorer results/run_summary/surveillance_explorer.json \
  --output results/run_summary/braid_clock.html
open results/run_summary/braid_clock.html
```

This uses existing report data; no genomic rerun is necessary. Without phenology,
the braid works, calendar dates remain visible, and ecological offsets display
unavailable. The browser also accepts an Explorer JSON through its local file
picker. The generated HTML embeds all CSS/JavaScript and has a content-security
policy preventing network requests. Nothing is uploaded.

## Supplying phenology

Start with `config/phenology-clock.example.json` (intentionally empty). The
fixture in `tests/fixtures/braid_clock/synthetic_phenology.json` illustrates the
schema but must not be passed off as real data. A real file requires:

- `schema_version: "wings.phenology.v1"`, `synthetic: false`, and `profiles`;
- per-profile host/country/state keys, inclusive season dates, baseline type,
  measurement and units;
- ordered, nonoverlapping bins with ISO start/end dates and a numeric value or
  explicit null;
- source, citation, actual retrieval date, and analytical method;
- optional reviewed anchor `earliest`, `latest`, `label`, and `basis`.

The formal shape is in `schemas/phenology-clock.schema.json`; runtime adds
calendar and cross-field validation. The schema identifier does not imply a
new public web service has been deployed.

```bash
python scripts/build_braid_clock_report.py \
  --explorer results/run_summary/surveillance_explorer.json \
  --phenology /absolute/path/to/reviewed_phenology.json \
  --output results/run_summary/braid_clock.html
```

The first provider adapter is intentionally not built here. WINGS' existing
eBird interval aggregates are not enough to infer a seasonal peak. A dated,
reusable regional seasonal product or a separately validated effort-aware
phenology estimate is needed. For eBird products, inspect source coverage,
taxonomy, units, data release, and reuse requirements, and retain the source
citation. An annual expected pattern is not a realized arrival date in another
year. Source guidance: https://science.ebird.org/en/status-and-trends/faq

Climate and BirdCast are not silently turned into phenology inputs. This module
does not need a 149 GB ERA5 download. Real climate integration and causal
attribution are outside this version.

## Embedded Explorer integration

`install_braid_clock.py` adds source modules and prepends a bundled copy of the
JS module to `scripts/report/surveillance-explorer.js`; CSS is appended to the
existing stylesheet. One guarded initialization hook mounts the panels before
the existing eight-tree Explorer. This uses the existing report's tracked CSS/JS
inputs, so no Snakefile or Quarto dependency changes are required in this version.
Repeated installs update only the tagged blocks. The normal Explorer continues
working if the optional module fails, with an explicit error notice.

Sample selection is synchronized in both directions. A public-reference focus
retains the WINGS sample selection. Host changes are shared with the existing
Explorer, while an out-of-filter selected sample remains explicit. Hover does
not change selection.

Use the package installer in dry-run mode first, then `--apply`. It checks the
initialization anchor and backs up replaced files outside the repository. It
never modifies README (including the AI statement), config.yaml, Snakefile, raw
sources, trees, or results. It never commits or pushes. New source-module edits
must be rebundled by rerunning `python scripts/install_braid_clock.py --repo .
--apply` before an ordinary report rebuild. A later version can replace this
small bundling adapter with separate build-system assets.

For the embedded Explorer, importing phenology through the browser is
**session-only**. To save it in a standalone HTML, use `--phenology` above. An
automatic phenology dependency in the normal `.wings` bundle is NOT wired yet.
If upstream Explorer JSON already contains `ecological_clock` in this schema,
the module will use it. No synthetic data are injected into production JSON.

After reviewing a dry run for unintended upstream work, rebuild the existing
HTML report and bundle using the usual WINGS commands. No forced JSON refresh
is needed for this UI-only change:

```bash
snakemake results/wings_report_bundle.wings \
  --configfile config.yaml --sdm conda --cores 4 \
  --resources mem_mb=90000 kaleido=1 -n
```

Inspect the plan before removing `-n`. Existing unrelated changes or stale
outputs may affect the plan. Opening an old saved bundle will not show new UI.

## Tests and known limits

```bash
node --test tests/test_genome_braid_clock.cjs
python -m unittest discover -s tests -p test_braid_clock_report.py -v
```

The package also contains a browser smoke test for developers with Python
Playwright and Chromium. It exercises linked selection, keyboard interaction,
filters, local import/export, missing phenology, hostile label escaping, and
mobile overflow. It does not require real pathogen sequence data.

The repository integration hook was developed against WINGS main commit
`689fccdb7a4fb043bcad4bacecd1578dfdaceaf0`. The complete existing WINGS regression
suite and a real local `.wings` report were not run in the build environment.
Run existing WINGS UI tests after installation, then inspect a regenerated report.
A working visualization does not validate the new descriptive metrics.

Next research work: fixed-panel neighborhood sensitivity; annotated support
uncertainty; verified specimen/reference linkage; taxonomy-aware provider
adapters; validated seasonal anchors; and explicit sampling-process modeling.
No forecast, geographic prioritization, pathogen fitness inference, or variant
function assessment is implemented.
