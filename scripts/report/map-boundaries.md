# Offline map boundaries

The Surveillance Explorer uses generalized Natural Earth boundaries embedded in
its HTML report. The portable `.wings` bundle carries that report, so map display
does not require an external map service or network connection.

## Sources and provenance

Retrieved 2026-09-28 from the Natural Earth vector repository:

- Countries: `geojson/ne_110m_admin_0_countries.geojson` (1:110 million).
- U.S. states/DC and Canadian provinces/territories:
  `geojson/ne_50m_admin_1_states_provinces.geojson` (1:50 million).
  Source Git blob: `1a362ae0bfbe1f2768071e58a2905a5561039703`.
- Repository: https://github.com/nvkelso/natural-earth-vector
- Public-domain terms: https://www.naturalearthdata.com/about/terms-of-use/

The asset retains 51 U.S. administrative areas and 13 Canadian areas. Country
polygons for the USA and Canada are replaced by those regional polygons to avoid
overlapping coastlines from different source scales. Other countries retain the
1:110 million geometry. Polygon rings, including holes, are preserved, simplified
with a 0.02-degree tolerance, and rounded to three decimal places. Labels use
source label coordinates; regional labels use names or postal abbreviations
according to the displayed extent. Label collisions are suppressed.

Generated `map-boundaries.js` SHA-256:

`999f0c3fd0e919bac6050360a0ca09fd0e15ee845b447d2b0b28414b63ec5480`

## Display behavior and limitations

- Sample area uses all valid coordinates in the run, with padding; host filtering
  does not change that extent. North America and World provide fixed extents.
- Locations outside a fixed extent are counted in the map summary.
- Missing or invalid coordinates are counted, not inferred from place names.
- State/province boundaries are included for the U.S. and Canada only.
- Natural Earth is a generalized reference basemap: small islands and fine
  coastal features may be omitted. Its boundary conventions are those of the
  source dataset; this is not a legal boundary reference.
- The local equirectangular display adjusts longitude scale for the center
  latitude. Broad/global views have projection distortion. Samples spanning
  the date line use a broad conventional extent rather than a wrapped view.
- This view adds geographic context; proximity alone does not establish linkage.

## Verification

Run `node --test tests/test_surveillance_map.cjs` to check administrative-area
coverage, projection bounds, stable host-filter extents, invalid coordinates,
fixed-view exclusions, cluster selection, empty data, and the Clear-selection
reset. Tests use a minimal DOM and real renderer methods. SVG previews were
rendered for local U.S., Canadian, and global examples. Full Quarto report and
browser rendering should also be checked after rebuilding in the WINGS runtime.
