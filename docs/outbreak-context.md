# APHIS wild-bird outbreak context

This panel provides descriptive surveillance context. Geographic and temporal
overlap do not imply epidemiological linkage. It does not estimate transmission,
incidence, prevalence, or the probability that a WINGS sample is linked to a
reported detection.

## Source and dates

Source: [USDA APHIS HPAI detections in wild birds](https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza/hpai-detections/wild-birds).

The initial snapshot is the user-provided `hpai-wild-birds(1).csv`, supplied on
2026-09-27 (America/Phoenix), with 19,912 data records. Its latest recorded
detection date is 2026-09-23. The date on which the snapshot was supplied is not
claimed to be an APHIS release or retrieval date.

- Collection dates: 2021-12-30 to 2026-09-16; 277 rows have unknown collection dates.
- Detection dates: 2022-01-12 to 2026-09-23; all 19,912 rows have usable dates.
- There are 7,145 rows identical to an earlier row. All are retained: the CSV
  lacks unique case identifiers, so identical rows cannot safely be deduplicated.
- Counts are source rows, not unique outbreaks or estimates of infection rates.
  This positive-record dataset supplies no testing denominator.

APHIS distinguishes collection date from the date of confirmatory detection.
Collection date is the default time basis. Switching to Date detected changes
both the map and timeline filters. Missing dates are excluded and counted for
the chosen geographic scope; the other date is never silently substituted.
Zero matches describe the loaded snapshot/filter only. Delayed reporting and
incomplete surveillance mean zero does not establish absence of infections.

## Geographic precision

The source has state and county names but no exact coordinates. WINGS displays
state-level polygon aggregates and retains the county names in the record
browser. It does not place a county/state centroid as an exact detection point.

Selecting a WINGS sample matches its recorded U.S. state (full name, abbreviation,
or US-XX code), even without sample coordinates. Matching is state-level even
when the WINGS sample has coordinates. Missing/unrecognized states and missing
or non-U.S. countries are explicitly explained; no national match is silently
substituted. Users can choose a state or All U.S. states manually.

## One map, two layers

WINGS sample points and APHIS state shading share one map. Sample points retain
host colors and cluster selection; APHIS states use a separate teal count scale.
Selecting a sample focuses the timeline and source records on its state, while
all U.S. states keep their counts for the date window, including neighbors.
The color scale is national for that window and does not change when browsing a
different state or panning. It does change when the dates or date basis change.

- Solid burgundy outline: selected WINGS sample's recorded U.S. state.
- Dashed outline: state currently being browsed in the timeline/record list.
  When both are the same state, the solid sample outline takes precedence.
- Click a sample point to select it; click a state to browse APHIS records without
  changing the selected WINGS sample. Selecting a different sample restores
  the timeline/record scope to that sample's state.
- **APHIS state shading** toggles the shading without removing the timeline or
  source records. State-click browsing is active while the shading is shown.
- **Zoom to [state name]** fits the state clicked on the map, or the sample's
  recorded U.S. state when no other state is being browsed. It works even
  when coordinates are missing. No point is invented; the sample is explicitly
  labeled as located only at state level. Panning never changes the selection.
- Host filters affect sample points only. Non-U.S. areas are outside the APHIS
  layer's geographic coverage; they are not zero-detection areas.

Clicking a state also opens an on-map summary with its full name, record count,
date basis, date window, missing-date count, and buttons to zoom or view source
records. The state zoom button works without a WINGS sample selected. Close the
summary with ×; click a state again to reopen it. Labels are placed within visible
state geometry rather than dropped when their original anchor is offscreen.
Narrow regions use abbreviations where full names will not fit; the summary
always shows the full state name.

## Controls

- **Timeline / records → Follow selected sample (state):** match the sample's
  recorded state; with no sample selected, browse all states. This choice does
  not remove neighboring states from the map shading.
- **Lock date window unchecked:** center an inclusive ±7, ±30, ±90, or ±365 day window on
  the WINGS sample's collection date. The default is ±30 days, a user-controlled
  display window, not an epidemiological linkage threshold.
- **Lock date window checked:** keep the displayed dates when changing samples.
- **From / Through:** select an inclusive custom date range. Editing either date
  locks the window and turns off automatic date following. Missing sample dates use the full source
  date range with an explicit explanation.
- Click a state to select it. Click a timeline bar to narrow the date window.
  Bins are daily for windows up to 90 days apart, monthly for larger windows.
- The dashed timeline line marks the selected WINGS sample's collection date;
  it does not assert a relationship to APHIS records.
- Host filters in the existing WINGS sample views do not filter APHIS records.
- Source records are paginated in groups of 25 and expose both original dates,
  county/state, species, strain, sampling method, classification, and agency.

State shading uses a logarithmic relative color scale with the displayed maximum
across all U.S. states for the chosen date window. It is a count display, not a
rate or risk map. Gray U.S. states have no matching dated records in that snapshot
window; this does not establish absence of infections. Natural Earth boundaries
are generalized reference geometry.

## Provenance and source links

Each loaded snapshot has a full SHA-256 digest. Source rows use a one-based
CSV data-record number (header excluded), qualified by that snapshot's digest.
The browser displays a shortened digest for convenience; the full hash appears
in provenance. These references are local snapshot references, not APHIS IDs.

The export has no record-specific web URLs. Links explicitly open the APHIS
source table. The record's state, county, dates, and species provide the lookup
context. They are not invented deep links to unique APHIS cases.

The original CSV bytes are installed alongside a matching provenance JSON file.
Reports embed the normalized records in the existing explorer JSON/HTML, so the
context is available in the `.wings` bundle offline. Following external APHIS
links requires an internet connection. Builds never fetch or refresh live data.

## Configuration and refresh

With no `outbreak_context` configuration, the default local snapshot is detected
at `resources/aphis/hpai-wild-birds.csv`. Explicit configuration:

```yaml
outbreak_context:
  enabled: true
  csv: resources/aphis/hpai-wild-birds.csv
  provenance: resources/aphis/hpai-wild-birds.provenance.json
```

Set `enabled: false` to exclude it. A missing explicitly configured CSV or
provenance file fails the build. A provenance hash mismatch also fails rather
than applying old provenance to new records. With no provenance file configured
or found, an unprovenanced CSV can be loaded but its acquisition date is labeled
not recorded.

Download a new CSV from APHIS, then run:

```bash
python scripts/import_aphis_snapshot.py /path/to/new-export.csv
```

The importer validates headers and row structure, preserves the CSV bytes, and
writes matching provenance. Its date is labeled local import date, not APHIS
release date. `--output` changes the destination; `--snapshot-date YYYY-MM-DD`
sets the locally recorded snapshot date.

Force each artifact separately to avoid reusing embedded assets from an older
report. From the WINGS repository:

```bash
snakemake results/run_summary/surveillance_explorer.json \
  --configfile config.yaml --sdm conda --cores 4 \
  --resources mem_mb=90000 kaleido=1 --force &&
snakemake results/run_summary/run_summary.html \
  --configfile config.yaml --sdm conda --cores 4 \
  --resources mem_mb=90000 kaleido=1 --force &&
snakemake results/wings_report_bundle.wings \
  --configfile config.yaml --sdm conda --cores 4 \
  --resources mem_mb=90000 kaleido=1 --force
```

Standalone builder callers can pass `--aphis-csv` and `--aphis-provenance`.
Older callers and reports without APHIS context continue to work.

## Validation

```bash
python -m unittest discover -s tests -p test_outbreak_context.py -v
node --test tests/test_outbreak_context.cjs
```

Tests cover repeated rows, source hashes, both dates, missing/invalid data,
state fallback, non-U.S./missing geography, inclusive date windows, manual
filters, independent host filters, state/timeline count reconciliation, source
references, and HTML escaping. Existing linked-genome/map checks remain in CI.
The supplied file reconciles to 19,635 dated collection records or 19,912 dated
detection records. Full Snakemake/Quarto rendering and browser interaction must
also be checked in the WINGS runtime; these were unavailable during preparation.
