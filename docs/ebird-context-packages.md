# Portable eBird context packages

WINGS supports an explicit `reuse` mode that separates local data preparation
from analysis. A complete package can be moved between machines and used after
the original downloads are removed. Genomic analysis and pairing settings are
unchanged. This feature handles EBD/SED context; eBird Status and Trends
phenology, BirdCast, weather, and APHIS still use their existing configurations.

## Configure reuse

Use this mapping within your existing run configuration:

```yaml
ebird:
  mode: reuse
  context_dir: /absolute/path/outside/wings/ebird-Aug-2026-context
  required: false
  days: 30
  radius_km: null
  host_map: {}
```

`required: false` explicitly permits genomic analysis to continue when the
package is absent, incomplete, incompatible, corrupt, or outside the requested
geographic/date scope. The Explorer records `UNAVAILABLE` with a reason in its
report warnings and JSON; it does not reuse stale eBird summaries or turn missing
evidence into zero observations. Set `required: true` to stop at preflight
instead. A `READY` package does not guarantee a usable estimate for every sample:
existing host mapping, missing location, and checklist availability statuses
still apply.

`mode: off` records intentional disabling. Configurations without `mode` retain
legacy behavior, including their existing source-file requirements. Reuse mode
never schedules either original-download cache rule and does not require
`sampling_file`, `observations_file`, or `release_dir`. If `release` is supplied,
it must match the package. Existing host mapping and radius options are retained.

For a trial run, the standalone updater's `--write-reuse-config` option creates
`config.ebird-reuse.yaml` from `config.yaml`, points to the existing cache, and
sets context to optional. It does not modify `config.yaml`. An unmigrated cache
will be reported as unavailable, even if its original records remain usable.

## Package contents and identity

Packages are directories containing:

- `observations.txt.gz`, `sampling.txt`, and `species_catalog.tsv`.
- `cache_manifest.json` and `sampling_manifest.json`.
- Original `terms_of_use.txt` and `recommended_citation.txt`.
- `context_manifest.json`, schema `wings.ebird-context.v1`.

The context manifest records release, taxonomy version, acquisition date,
preparation time and software fingerprints, geographic/date scope, counts,
relative package filenames, SHA-256 checksums, and a content-derived package ID.
Original absolute source paths are historical provenance only and are not opened
during reuse. Full package checksums are checked at preflight; large scoped
packages therefore incur read I/O. This is integrity checking, not source
publisher authentication. A summary of the manifest and validation status is
included in the report and run provenance; original EBD/SED records remain in
the external package and are not added to report bundles.

The source download must cover all species and the entire requested
geographic/date scope. `--confirm-all-species` is an explicit user attestation;
software cannot infer the original download selections from missing records.
Source filenames containing release labels are checked for disagreement. The
package cannot claim coverage beyond the release month. The supplied citation
and terms must correspond to that release; their semantic authenticity cannot
be established from hashes alone.

## Prepare from source downloads

The following uses example paths and a synthetic placeholder taxonomy version;
replace them with your actual source paths and provenance before running:

```sh
python scripts/ebird_context_package.py build \
  --observations /data/ebird/ebd_relAug-2026.txt.gz \
  --sampling /data/ebird/ebd_sampling_relAug-2026.txt.gz \
  --documents /data/ebird/release-documents \
  --metadata metadata.tsv \
  --days 30 \
  --release Aug-2026 \
  --taxonomy-version YOUR_SOURCE_TAXONOMY_VERSION \
  --acquired-at YYYY-MM-DD \
  --confirm-all-species \
  --output /data/ebird-Aug-2026-context
```

Preparation uses the production cache builder and validates the resulting row
counts. It retains attribution documents immediately. Original observations and
sampling files are hashed before and after preparation to detect source changes;
this adds sequential I/O to preparation. Both must come from the same release
and compatible download scope. A package is published by renaming a completed
staging directory. Existing output directories are never intentionally replaced.
`unknown` is accepted for taxonomy or acquisition date when those facts are
unavailable, and is recorded explicitly rather than guessed.

## Inspect and migrate an existing cache

Inspecting is read-only and works even when the supporting documents are absent:

```sh
python scripts/ebird_context_package.py inspect \
  --cache /absolute/path/to/ebird_wings_cache
```

Once the original release documents are recovered, copy the cache into a new
package. This does not modify the old cache:

```sh
python scripts/ebird_context_package.py migrate \
  --cache /absolute/path/to/ebird_wings_cache \
  --documents /absolute/path/to/recovered-release-documents \
  --release Aug-2026 \
  --taxonomy-version unknown \
  --acquired-at unknown \
  --confirm-all-species \
  --output /absolute/path/to/ebird-Aug-2026-context
```

Migration requires coherent observation/sampling manifests, valid counts,
coverage scopes, and nonempty documents. It fingerprints the actual cached
files, but cannot reconstruct original source-file hashes or missing release
documents. Missing historical provenance remains explicitly unknown. Existing
caches with inconsistent manifests need review rather than automatic repair.

## Verify and refresh

```sh
python scripts/ebird_context_package.py validate \
  --context-dir /absolute/path/to/ebird-Aug-2026-context \
  --metadata metadata.tsv --days 30
```

Reuse checks coverage by geography and dates rather than requiring identical
sample IDs or a paired-study design. A subset or renamed sample can reuse a
covering package. Conservative scope checks may reject equivalent alternate
state spellings; normalize metadata consistently. New data outside the scope
requires a new package. Refresh explicitly into a new directory and change
`context_dir` only when you intend to adopt that release.

Current scope validation requires each requested window to fit a recorded
window; it does not combine adjacent windows. Packages are designed to be
immutable after preparation. A change detected between preflight and the status
job stops the workflow so that it can be restarted with a consistent DAG.

Historical execution restores the recorded eBird status, summary, and
attribution instead of reopening the external package. This preserves the
recorded context decision, including when it was unavailable.

## Tests

```sh
python -m unittest discover -s tests -p test_ebird_context_package.py -v
python tests/integration_ebird_context.py --self-check
python tests/integration_ebird_context.py
```

The standard-library tests prepare and move a synthetic package, remove its
source downloads, execute the production summary/report builders, and check a
known numerator and denominator. They cover unpaired metadata, corruption,
release and scope mismatch, attribution, legacy migration, and stale-output
suppression. The integration script extracts production configuration and rules
into an isolated Snakemake workflow. It does not execute genomic tools or use
real eBird records. Its full mode requires Snakemake; `--self-check` does not.
The GitHub workflow runs both on Linux and macOS after push.
