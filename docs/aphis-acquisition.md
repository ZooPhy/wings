# Automatic APHIS context

Select **APHIS detections** and **Allow context downloads**, then select
**Prepare context**. No file selection is needed. Clear any previous CSV override
to use automatic retrieval. No sample metadata is sent to APHIS.

WINGS retrieves the full CSV once per preparation from
https://www.aphis.usda.gov/sites/default/files/hpai-wild-birds.csv.
This URL is the `data-csv-url` in the official wild-bird detections page saved on
2026-11-06. It is a file download, not a streaming feed or a guaranteed API.
HTTP failures, including 403 responses, are handled without replacing valid data.

| Card | Meaning |
| --- | --- |
| Downloaded | This preparation retrieved and validated the official CSV. |
| Cached snapshot | Uses a previously validated download; original retrieval date remains visible. |
| Bundled snapshot | Uses the repository snapshot; its recorded import date remains visible. |
| Your CSV | Uses the explicit file selected in Advanced settings; no download occurs. |
| Unavailable | No usable source was found. Optional APHIS context does not block sequencing. |

With downloads disabled, preparation makes no APHIS request. WINGS tries a valid
cache first, then the bundled snapshot. Failed online refreshes show **Refresh
unavailable** beside the original snapshot date. Dates describe retrieval or
local import, never an inferred APHIS release date or completeness guarantee.
Missing local import dates remain unknown. Collection and detection date ranges
are recorded separately. Identical source rows are retained.

Cache entries live under `$WINGS_CONTEXT_CACHE/aphis` (default
`~/.cache/wings/context/aphis`). Each entry pairs immutable CSV bytes with hashed
provenance. An atomic pointer selects the most recently completed valid download.
Invalid, truncated, HTML, empty, or incompatible downloads do not advance that
pointer. An invalid cache is ignored. Concurrent preparations have separate
entries. Cache write failures do not discard a successful download.

Each prepared context snapshot contains `aphis.csv` and
`aphis.provenance.json`, both covered by the context selection's file hashes.
Provenance includes source/download URLs, SHA-256, byte and record counts,
retrieval time, HTTP metadata when available, date ranges, source mode, refresh
outcome, and any fallback reason. A failed refresh never changes the original
retrieval date. The Explorer payload carries acquisition metadata; the run's
configuration pins these files. Reusing prepared context does not refresh it.

**Advanced settings → Use your own APHIS CSV** remains available for offline or
historical work. A supplied provenance sidecar must match the CSV hash. A missing
or invalid explicit override is reported rather than silently replaced. User CSVs
never replace the official-download cache.

The ordinary terminal workflow still consumes the configured pinned CSV. To use
automatic acquisition from the terminal, run the metadata-driven context
preparation described in [context setup](context-setup.md), then use its generated
configuration overlay.

Portable tests use synthetic CSVs and simulated HTTP responses. They cover
download, offline and HTTP-403 fallback, cache corruption, concurrent publication,
explicit overrides, immutable run evidence, and report/launcher integration.
No network access is required by these regression tests.
