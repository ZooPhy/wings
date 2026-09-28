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
| Weather | Daily mean temperature at 2 m (°C), daily precipitation total (mm), daily maximum wind speed at 10 m (km/h) | ERA5 0.25° grid; requested and returned coordinates shown | Local calendar day; returned IANA timezone |

The eBird shaded interval represents one aggregate reporting frequency, not
daily measurements. Changing the display window clips that interval visually;
it does not recompute the denominator or interpolate daily values. Existing
validated values and eBird citation/terms are retained. Selecting a sample
shows its associated eBird context; clearing selection restores host-filtered
contexts. Shared contexts are not summed across samples.

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

Without `--fetch-weather`, the builder is offline and only reads existing
cache files. Rebuilding a report or opening a `.wings` bundle never initiates
requests. Changing sample dates or locations invalidates their old weather
bindings; rebuild the cache to update them. The command preserves an existing
BirdCast import unless a replacement is supplied or `--clear-birdcast` is used.

## BirdCast state pilot

No supported automatic BirdCast data feed has been established for this pilot.
The initial integration accepts locally supplied estimates with documented
source and reuse basis. The dashboard link remains available even without an
import. This release includes no real BirdCast numeric snapshot and does not
scrape the dashboard or infer values from map colors.

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

```bash
python -m unittest discover -s tests -p test_ecological_context.py -v
node --test tests/test_ecological_context.cjs
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
