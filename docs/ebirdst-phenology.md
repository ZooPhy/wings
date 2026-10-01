# Metadata-driven Ecological Clock

WINGS derives an expected host seasonal reference from eBird Status & Trends weekly median relative-abundance rasters. The feature is opt-in because Status & Trends raster downloads require the user's own access key when a needed species is not already cached.

## Inputs and taxon resolution

Ordinary WINGS metadata remain the source of sample identity, host, collection date, and geography. WINGS resolves hosts without fuzzy matching against the version-matched `ebirdst::ebirdst_runs` modeled-species reference. Four-letter field codes can be translated through `resources/ebird_host_codes_2025.tsv`; exact common names, scientific names, and eBird species codes can also resolve directly.

The default Status data version is 2023 and the default raster is the 27-km weekly median relative-abundance product. One raster is cached per unique modeled species, not per sample. Large source rasters remain outside the repository and report bundle.

## Spatial hierarchy

WINGS uses the most specific supported geography available:

1. **POINT** — valid sample latitude/longitude. The 52-week profile comes from the Status & Trends raster cell containing the supplied coordinate.
2. **REGIONAL_STATE_MEAN** — U.S. coordinates are missing but a recognized state is supplied and `regional_fallback: state` is enabled. WINGS uses the arithmetic mean of the weekly raster values for raster-cell centers inside that state's official U.S. Census Bureau cartographic boundary.
3. **Unavailable** — geography is insufficient or no supported regional boundary is available.

The state fallback is not a state-centroid substitution. It is a regional summary and is labeled as such in the profile, report, and provenance. Boundary data are cached outside the repository from the U.S. Census Bureau 2024 1:20m state cartographic boundary file.

At 27-km resolution the regional mean is intended as a broad seasonal reference, not a local abundance estimate. Point and regional profiles should not be interpreted as having the same spatial precision.

## Clock interpretation

The 52-week Status & Trends profile is a reference annual cycle. For display, WINGS projects those weekly values onto the collection year so the collection date and annual profile can share a calendar axis. The projected calendar year is not the Status & Trends model version year.

A descriptive anchor is derived as the contiguous interval surrounding the maximum where values remain at least 90% of the maximum. It is a WINGS visualization heuristic, not an eBird-defined migration peak or confidence interval. When the plateau crosses Dec/Jan, WINGS uses the maximum week itself as the display anchor and compares the nearest annual occurrence.

The Ecological Clock defaults to the selected WINGS sample. **Compare samples** is an explicit secondary view to avoid treating repeated host profiles as separate primary signals when the user's task is to interpret one selected specimen.

## Configuration

```yaml
phenology:
  enabled: true
  source: ebird_status_trends
  version_year: 2023
  resolution: 27km
  regional_fallback: state
  cache_dir: null
  host_map_file: resources/ebird_host_codes_2025.tsv
  taxonomy_file: null
```

Set the external cache and access key in the shell:

```bash
export WINGS_EBIRDST_CACHE="$HOME/Documents/ebirdst_wings_cache"
export EBIRDST_ACCESS_KEY='YOUR_KEY'
```

The access key is never written to WINGS outputs. If all required Status & Trends rasters are cached, the key is not required for those raster downloads. The state boundary file is separately cached under the WINGS eBird Status & Trends cache.

## Output

`results/run_summary/phenology/wings_phenology.json` uses schema `wings.phenology.v1`. It includes one status record for every WINGS sample, one profile per `READY` sample, spatial method/provenance, source/citation metadata, taxonomy and metadata hashes, raster checksums, and regional-boundary provenance when used. `surveillance_explorer.json` embeds the compact snapshot as `ecological_clock`; raw rasters and raw boundary files are not bundled.


## UI regression fixes in v0.2.4

The Genome Braid workbench uses neutral `div` containers so Quarto/report-wide `section` and `aside` layout rules cannot collapse the braid card. When WINGS Tree Studio is installed, Explorer Tabs moves its launcher into the shared Genome region above the braid and hides it in the Ecology lens. Signed ecological offsets remain in exported evidence, while the evidence card uses before/after wording for readability.
