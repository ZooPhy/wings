# Ecological context in the Surveillance Explorer

Select one WINGS sample to compare three sources along the same calendar-date
axis. Each source retains its own measurement, aggregation, geography, timezone,
and provenance. The ecological display window (±7, ±30, or ±90 days) is separate
from the APHIS date window. It always follows the selected sample's collection
date. Hover does not change the selection.

| Source | Measurement | Geography | Dates |
| --- | --- | --- | --- |
| eBird | Reporting checklists / complete checklists, displayed as a percentage | Existing validated state or radius scope for the host species | Original aggregation period and release |
| BirdCast pilot | Estimated birds crossing a state during the night, birds/night | Selected contiguous-U.S. state; no county inference | Local evening date, sunset to following sunrise; source IANA timezone |
| Weather | Daily mean and min/max temperature at 2 m (°C), precipitation total (mm), maximum wind speed at 10 m (km/h), and daily condition code | ERA5 0.25° grid; requested and returned coordinates shown | Local calendar day; returned IANA timezone |

The green eBird interval represents one aggregate reporting frequency, not
daily measurements. Changing the display window clips that interval visually;
it does not recompute the denominator or interpolate daily values. Existing
validated values and eBird citation/terms are retained. Selecting a sample
shows its associated eBird context; clearing selection restores host-filtered
contexts. Shared contexts are not summed across samples.

When Migration Weave is available, eBird follows its displayed calendar bounds
and selected dates, including weather drags, date fields, Full season, and the
sample-window controls. A translucent teal band marks the selected interval;
the green aggregate and its percentage keep their explicitly labeled **source
period**. The snapshot contains period totals, not daily checklist counts, so
a separate frequency for a different selection is unavailable. For example,
selecting October 1–November 12 does not turn an eBird September 27–November 26
estimate into a frequency for the selected dates. eBird keeps a calendar axis
even when the weave uses migration progress.

BirdCast counts describe aggregate nocturnal migration across species, not the
selected host species. Counts depend on regional extent and should not be
compared as standardized intensity across differently sized regions. The pilot
uses state-level inputs only. It does not infer county or point estimates.
Radar coverage, weather interference, and season affect availability. The
dashboard's regular seasons are March 1–June 15 and August 1–November 15;
missing nights are not automatically labeled zero or out of season.

Weather values are gridded reanalysis estimates, not station measurements at
the collection site. No weather is assigned to a state centroid when a sample
lacks valid coordinates. ERA5 is pinned instead of using a changing best-match
model. Grid-cell elevation is used (downscaling disabled), and cell selection
is nearest. The returned cell can differ from the requested coordinates.

Dates are aligned by their calendar labels, not converted into common instants.
BirdCast's local night and weather's local day can cover different hours.
Neither is assumed to identify the sample's time of collection. The views
provide environmental context, not an infection-risk score or a transmission
link. APHIS state browsing does not change this sample-centered panel.

## Automatic BirdCast acquisition for each run

Merge this block into the run's configuration:

```yaml
ecological_context:
  enabled: true
  auto_birdcast: true
  birdcast_night_offset: -1
  auto_weather: true
  weather_days: 30
  cache_dir: ~/.cache/wings/ecology
  offline: false
```

The workflow reads `results/metadata/validated_metadata.tsv` (under your
configured results directory), deduplicates collection state/night combinations,
and writes `run_summary/ecology/ecological-context.json` beneath that directory.
The Explorer and existing replay-input archive use this run-specific snapshot.
Only region codes and dates are sent to BirdCast; sample IDs stay local.

`birdcast_night_offset: -1` selects the evening before the collection date;
`0` selects the collection-date evening. This is a recorded convention, not an
inference about collection time. Exact ISO dates and a recognized contiguous-U.S.
country/state are required. County and point estimates are not inferred. Each
distinct state/night is fetched once per build, including failed requests.

The importer reads the literal data embedded in a dated dashboard page, e.g.
`https://dashboard.birdcast.org/region/US-AZ?night=2026-10-08`. This is an
**undocumented dashboard interface**, not a supported public API. A restricted
parser reads Nuxt/devalue literals without evaluating JavaScript. It verifies
region, date, timezone, numeric estimates, and within-night timestamps; live
incomplete nights and changed/missing payloads are unavailable, never zero.
No dashboard API key is copied or required by the importer.

Successful records are cached under `cache_dir/birdcast/` with source URL,
retrieval timestamp, page checksum, normalized-record checksum, and within-night
birds-aloft counts. Page scripts and embedded credentials are not retained.
The exported snapshot retains source attribution and these per-record details.
Source terms still apply; accessibility does not establish redistribution rights.

Only metadata-matched nights are requested; the full ±7/30/90-day display window
is not requested night by night. Seasonal arrays embedded in those same pages
are also captured for Migration Weave (below). Missing metadata and unavailable requests have explicit
statuses. Unavailable requests are retried when acquisition is run again;
successful historical records are reused. The report labels the matched night
and links to its dated dashboard. Speed/height fields are not imported until
their units are independently verified.

`offline: true` uses existing caches without network access. `auto_weather: false`
disables new weather requests; an optional `snapshot:` can preserve valid weather
bindings from an existing ecological snapshot. With `auto_birdcast` omitted or
false, the previous supplied-snapshot workflow remains unchanged.

To prepare a snapshot directly:

```bash
python scripts/build_ecological_context.py \
  --metadata results/metadata/validated_metadata.tsv \
  --output results/run_summary/ecology/ecological-context.json \
  --cache-dir ~/.cache/wings/ecology \
  --fetch-birdcast --birdcast-night-offset -1
```

Use `--birdcast-cache` instead of `--fetch-birdcast` for an offline build.
Add `--refresh-birdcast` with `--fetch-birdcast` to replace successful cached
records explicitly. CSV import remains supported, but cannot be combined with
automatic BirdCast acquisition. Merely opening an exported report never fetches.

## Migration Weave

The Ecology view includes an offline SVG visualization of the seasonal migration
pulse. It is bundled in the existing Explorer JavaScript; no CDN, additional
package, or new configuration switch is required. When a validated seasonal
series is available, Migration Weave is the display for BirdCast and weather;
the duplicate standalone source panels below it are hidden and not rendered.
The eBird host-reporting section remains separate. Matched-night estimates,
weather values, and source details remain available in the weave. Older snapshots
without seasonal context retain the original source panels as a fallback.

- **Calendar / Migration progress:** switch between local evening dates and
  cumulative share of observed seasonal passage. The axis changes, while the
  selected date window is retained.
- **Display window / Full season:** changing the panel's ±7/30/90-day dropdown
  zooms the weave around the selected collection date and updates the other
  ecological plots. The weave clips that interval to the available season;
  its date labels, pulse, event ribbons, and coverage counts follow the displayed
  dates. The seasonal crossing total and migration-progress denominator remain
  fixed. Select Full season to restore the overview, or Sample ±N days to resume
  following the selected collection. A dated sample is required for the dropdown.
  Selecting a different season manually restores that season's overview.
- **Collection ribbons:** link the pulse to metadata collections. Samples sharing
  a state and collection date form one event, labeled with the sample count.
  Ribbon width is fixed and carries no quantitative meaning. Select a ribbon
  with a mouse or keyboard; choose any member of that event in the sample menu
  to update the existing Explorer selection. The active host filter applies.
  Keyboard focus uses a small ring around the collection marker. Selected date
  intervals have a translucent teal band behind the plotted values and thin
  boundary lines. The highlight follows dragging or date-field changes in the
  migration, weather, and eBird charts and clears with Reset selection.
- **Window selection:** drag across the pulse or weather chart, or enter
  start/end dates in the controls above the charts, to see
  unique collection events, coverage, known crossings, and their share of the
  seasonal denominator. Shares are withheld if any selected night lacks a
  derivable estimate. Reset selection restores the currently displayed range;
  Full season restores the complete seasonal axis. These controls use cached
  data and do not fetch weather or fill missing days.
- **Season and height controls:** switch among available state/seasons; choose
  linear or explicitly labeled square-root height to inspect smaller pulses.
  The view shows eight event ribbons per page when many collection dates exist.
- **Weather:** enable the optional strip for the selected geolocated sample.
  Daily mean temperature, a shaded min/max range, precipitation bars, and maximum
  wind share the weave's date positions. Hover either chart to inspect both, or
  use the keyboard-accessible Inspect day menu. Dragging either chart updates
  one shared date range, its boundary lines, both summaries, and the date fields.
  The weather summary reports the number of available daily values. Dragging
  does not change the linked sample or fill days without cached weather.
  Weather follows the selected sample's grid cell; it is not statewide weather.
  The Weather sample menu lists collections with cached weather in this season
  and host filter. Choosing one explicitly changes the linked Explorer sample;
  samples lacking coordinates never silently borrow another location's weather.
  Samples sharing a collection date and weather context share one menu entry.
- **Conditions and smoothing:** condition icons appear across the visible dates,
  with spacing to prevent overlap; hover or Inspect day provides the condition
  for any date whose icon is omitted for space. The source code describes the most
  severe condition during that local calendar day, not conditions throughout
  the migration night. The optional seven-day temperature mean uses that date
  and the six preceding calendar dates, requiring all seven finite values.
  It uses cached days before the visible window when available. Missing values
  break the line; switching to migration progress does not change the averaging
  interval. Daily values, units, condition descriptions, and source details
  remain accessible in Weather values and source.

The importer distinguishes `currentSeasonSeries.totalBirds` (cumulative seasonal
crossings) from `currentSeasonSeries.numAloft` (nightly mean birds aloft). Neither
is treated directly as nightly crossings. The displayed crossing pulse uses
successive cumulative differences, requiring adjacent valid calendar dates. A
zero baseline is used only on the source's first season date. Gaps remain gaps,
and the importer rejects decreasing cumulative totals, ambiguous dates, region
mismatches, unfinished nights, and substantial disagreement with the matched
nightly total. Rounding can explain small differences between the derived pulse
and the independent nightly figure in the existing table.

Migration progress is cumulative crossings divided by the latest observed
seasonal cumulative total. A season is marked complete only when every night
through its stated end has valid adjacent values. Partial seasons explicitly
say **observed passage through [date]**: 100% means the available observations,
not completion of the migration season. Progress is disabled for gaps or a
zero denominator. Pending dates remain visible in Calendar; events without a
progress position are counted and explained rather than placed at an invented
position. No interpolation or species-specific inference is introduced.

Seasonal context is validated and stored with its source URL, retrieval time,
and source page checksum. Arrays are deduplicated by state/season in the saved
snapshot. The longest observed series is selected, with retrieval time breaking
ties; a season always comes from one coherent source snapshot. Different
revisions are never spliced together. Seasonal payload validation is repeated
when a report loads its ecological snapshot.

An online build upgrades pre-Weave nightly caches once, by rereading their dated
pages. Offline builds keep their available nightly estimates and explain when
seasonal data are absent. A failed cache upgrade retains the validated nightly
estimate; it can be retried on the next online build. An unavailable seasonal
series does not erase an otherwise valid nightly total. Use `--refresh-birdcast`
with `--fetch-birdcast` to update an already-upgraded snapshot, for example after
an ongoing season ends or a source schema issue is resolved. Report interactions
never retrieve additional data.

This is a descriptive alignment of ecological context and collection timing.
It does not add a BirdCast term to the concordance calculation. Statewide
crossings combine species and depend on regional extent; they do not measure
the sampled host's movements.

Focused checks:

```bash
python -m unittest discover -s tests -p 'test_birdcast_data.py' -v
python -m unittest discover -s tests -p 'test_migration_weave.py' -v
python -m unittest discover -s tests -p 'test_ecological_context.py' -v
python -m unittest discover -s tests -p 'test_migration_weather.py' -v
node --test tests/test_ecological_context.cjs tests/test_migration_weave.cjs
```

## First weather snapshot

Run from the WINGS repository in the existing Python environment:

```bash
python scripts/build_ecological_context.py \
  --metadata results/metadata/validated_metadata.tsv \
  --days 90 --fetch-weather
```

This sends only coordinates and date windows to the documented Open-Meteo
Historical Weather API. It sends no sample identifiers, hosts, reads, or
sequences. The default public endpoint is intended for noncommercial use;
commercial deployments should review the provider's access terms.

The output is `resources/ecology/ecological-context.json`. Raw response caches
are under `resources/ecology/cache/weather/`, keyed by the complete request.
Locations and date windows shared by samples reuse one request. Valid existing
caches are reused. `--refresh-weather` with `--fetch-weather` explicitly
refreshes them. Requests have a timeout; failed downloads are reported and
represented as unavailable, so inspect the command output before sharing.
Recent requests are limited to approximately five days before the build date
because ERA5 is delayed. The actual cached dates and missing values are shown.

The automatic workflow caches ±30 days around each collection by default.
Set `ecological_context.weather_days: 90` for wider coverage (allowed: 1–365);
the direct command uses `--days`. Changing the report's display window only
changes the view, so a ±90-day view can show gaps if only ±30 days were cached.
New requests include min/max temperatures and condition codes. They have a
different cache key from the older three-field requests and leave those original
responses intact. No new configuration is required for the default upgrade.

An offline build, or a failed online upgrade, can reuse one validated overlapping
cache response with the same coordinates, model, units, timezone request, and
grid settings. Its original dates and provenance are preserved; responses from
different locations or revisions are never stitched together. Older snapshots
remain usable: absent min/max values and condition codes stay unavailable, and
icons are not inferred from rainfall or temperature. Online retries can supply
the additional fields and dates later.

Without `--fetch-weather`, the builder is offline and only reads existing
cache files. Opening a `.wings` bundle never initiates requests; an automatic
workflow rebuild can fetch when `auto_weather` is enabled and `offline` is false.
Changing sample dates or locations invalidates their old weather
bindings; rebuild the cache to update them. The command preserves an existing
BirdCast import unless a replacement is supplied or `--clear-birdcast` is used.

## Optional BirdCast CSV import

Locally supplied estimates with documented source and reuse basis remain an
alternative to automatic dashboard acquisition. The dashboard link remains
available without imported or fetched data. No real BirdCast numeric snapshot
is distributed with the repository, and values are never inferred from map colors.

Use `resources/ecology/birdcast-template.csv` as the header for a WINGS input
CSV. This is a WINGS format, not an official BirdCast export. Populate one row
per state and night from data you are authorized to reuse:

| Column | Required meaning |
| --- | --- |
| `state` | Two-letter code, `US-XX`, or full name; contiguous U.S. states and DC |
| `night` | ISO `YYYY-MM-DD`, local date on which the night begins |
| `timezone` | IANA timezone used by the source, such as `America/Chicago`; do not guess from the state |
| `birds_crossed` | Finite nonnegative estimate for **birds crossing the state during that night**; not birds aloft, a seasonal cumulative count, or migration traffic rate |
| `status` | `AVAILABLE`, `UNAVAILABLE`, or `OUT_OF_SEASON` |
| `reason` | Required explanation for an unavailable or out-of-season row |

An available zero is permitted. An unavailable value must be blank. Missing
rows stay missing. Duplicate state/night rows, invalid dates or timezones, and
nonfinite or negative estimates are rejected. Nightly values, missing reasons,
and source provenance are available in expandable tables.

Create a matching provenance JSON beside the CSV:

```json
{
  "source_url": "https://dashboard.birdcast.org/",
  "retrieved_on": "YYYY-MM-DD",
  "citation": "Actual citation for the source product and dates used",
  "reuse_basis": "Actual applicable terms or permission for these values",
  "sha256": "SHA-256 of the exact CSV bytes"
}
```

Replace every descriptive value with the actual information. On macOS, obtain
the digest using `shasum -a 256 /path/to/birdcast.csv`. The checksum is verified
before import; it establishes file identity, not independent source validation.
Do not submit the empty template as an observation file.

```bash
python scripts/build_ecological_context.py \
  --metadata results/metadata/validated_metadata.tsv \
  --days 90 --fetch-weather \
  --birdcast-csv /path/to/birdcast.csv \
  --birdcast-provenance /path/to/birdcast.provenance.json
```

## Configuration and rebuilding

The standard snapshot is automatically detected when present. To override its
location or disable it, merge `config/ecological-context.example.yaml` into
your existing `config.yaml`. `enabled: false` ignores a stale snapshot. An
explicitly enabled but missing snapshot is a missing input error. The existing
eBird display remains available without an ecological snapshot.

After applying the code patch and building/importing context, force each output
in dependency order:

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

Reopen the rebuilt bundle. The bundle contains the normalized ecological
snapshot with source hashes, not the raw cache files. Saved bundles retain
their original snapshot. Preserve the input CSV/provenance and raw weather
cache alongside your run for audit. Do not commit sample-specific caches or
reports to a public repository without reviewing their contents.

## Validation

### Migration in Concordance

Concordance adds BirdCast migration context as a separate comparison against
M2 (time, geography, host, and eBird seasonal ecology). Weather availability
does not gate this comparison. The reduced and full fits use the same complete
pair set. Existing host, ecology, and weather comparisons retain their inputs.

Each sample uses the snapshot's fixed collection-to-night offset. State and
collection-date bindings are checked against current metadata. No season is
assigned to a summer or winter coverage gap. A nightly estimate can be shown
without coordinates, but the full comparison still requires its geographic
predictor; no centroids are introduced.

The migration distance combines two coordinates, each in [0,1]: the matched
night's crossing-intensity midrank percentile within its state/season, and its
cumulative fraction of full-season passage. The percentile uses the coherent
seasonal increments, which can differ slightly from rounded matched-night
totals. Euclidean distance divided by sqrt(2) gives equal weight to the two
coordinates. Raw totals across states are not compared. A complete, nonzero,
monotonic source season is required; gaps, unfinished seasons, and unavailable
nightly values remain missing. This normalization is retrospective.

The configured minimum unique-sample count also applies to distinct state–night
contexts. Repeated samples sharing one context do not inflate this count. If
there are enough contexts but some are shared, added fit is descriptive and
p/q values are withheld. Sample-label permutations are used only when every
eligible sample has a distinct context. FDR correction is within the migration
comparison family across segments. These checks do not establish causality or
remove all ecological and sampling confounding.

The Concordance view includes a contribution plot by segment and a migration
context map. Selecting a segment restricts the map to its eligible collections;
selecting a point or collection links the actual sample to the existing
Explorer and Migration Weave. Shared state–night contexts appear once, with
their sample count. Host filtering changes the display, and weave date brushing
does not refit models. Missing-context reasons and source-season labels remain
visible. Older v2 reports continue to load; new reports include v3 migration
metadata in the compact bundle and detailed TSV outputs.

The Genome Braid suppresses the browser's rectangular SVG-group focus outline.
Keyboard focus uses a small ring at the first available segment marker.

```bash
python -m unittest discover -s tests -p test_ecological_context.py -v
node --test tests/test_ecological_context.cjs
python -m unittest discover -s tests -p '*concordance*.py' -v
node --test tests/test_concordance_migration_ui.cjs
```

Tests cover zero versus missing values, pinned units/models, shared caches,
checksums, stale metadata, missing coordinates, state matching, timezone and
date validation, common chart bounds, retained eBird denominators, and escaped
source text. Source data in tests and `preview.html` are explicitly synthetic.

## Sources

- [BirdCast dashboard interpretation](https://birdcast.org/migration-tools/migration-dashboard/)
- [BirdCast dashboard](https://dashboard.birdcast.org/)
- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
- [Open-Meteo terms](https://open-meteo.com/en/terms)
- [ERA5 single-level data, Copernicus Climate Change Service](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels)
