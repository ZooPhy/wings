# Metadata-driven surveillance context

Context preparation runs before genomic analysis. Users supply metadata; WINGS
plans the required geographic/date windows, prepares supported sources, and
records sources that cannot be obtained. Preparing context does not run IRMA,
Medaka, or the sample analysis workflow. Paired analysis is not required.

## Local runner

1. Start `python scripts/wings_local_runner.py` in the WINGS environment and open
   its local page. Select your FASTQ files and metadata TSV in the wizard.
2. In **Metadata**, check the source cards to include. An unchecked source is skipped.
3. Select **Prepare context**. Planning and preparation happen in one action. Each
   card shows a brief availability status and counts when available. Missing optional
   context does not block genomic analysis; technical diagnostics stay in saved
   context records and provider logs.
4. Use **Import data** when eBird data is needed, then **Choose folder…** for the
   extracted download. WINGS reuses compatible cached data automatically when no
   download or prepared-data folder is explicitly selected. Advanced settings contain
   matching windows, the supported seasonal reference, and eBird folder selection.
   Prepare again after changing the selection or settings. Selecting **Public genotypes**
   includes the full public reference automatically; there is no separate global
   comparison checkbox. Filter by host, location, and date in the report.
5. Continue through Analysis and launch. WINGS verifies metadata, selected sources,
   and snapshot hashes before copying reads and starting analysis.

The page currently retains its prepared draft only while open. If you reload it,
prepare again; source caches avoid most repeated downloads. Existing run snapshots
remain on disk. Failed or interrupted preparation can be retried with a new draft.
A restarted runner identifies incomplete preparation as interrupted.

## Metadata and matching

`sample_id` is required and unique. Complete `collection_date` values use
`YYYY-MM-DD`; `country`, `state`, `latitude`, `longitude`, and host fields determine
which context can be resolved. WINGS host codes in `host` are mapped using the
bundled host table. Recorded `host_common_name` and `host_species` labels also
participate in optional terminal/API public-genotype matching. The launcher keeps
the full public reference. Unknown taxon labels are not guessed.
Missing fields can be blank. Invalid dates/coordinates fail the production metadata
validator before acquisition. No coordinates are inferred from a state centroid.

Preparation uses the same production metadata validator and sorted sample order as
the main workflow. The original metadata hash binds the selection to the run;
normalized metadata is retained and hashed for phenology/report compatibility.
Multiple libraries can share ecological queries without becoming independent bird
observations or being automatically paired.

| Source | Metadata use | Acquisition and limits |
|---|---|---|
| ERA5 weather | Coordinate/date windows, default ±30 days | Existing Open-Meteo archive adapter; identical queries reuse cache. Recent windows are limited by the adapter's availability lag. |
| BirdCast | Contiguous-US state and previous local evening | Existing state/night and seasonal-context adapter. Unsupported geography, out-of-season nights, and missing records retain explicit status. |
| eBird Status and Trends | Host, geography, reference annual cycle | Existing phenology builder in its own Conda environment. Approved `EBIRDST_ACCESS_KEY` may be needed; the browser offers the supported 2023 reference, released in 2025. A reference annual cycle is not observed migration in the sample year. |
| eBird EBD and sampling effort | Region and date windows | Authorized all-species EBD plus sampling-event download, or a verified portable WINGS package. The page generates the request scope; it does not bypass eBird's account/request process. |
| Public genotype frequencies | Report filters for host, location, and collection month | The launcher includes the full public metadata reference, with a saved source commit/snapshot. It does not discard records outside the input metadata's scope. Terminal/API callers can still request a scoped subset explicitly. |
| Run genotype frequencies | WINGS sample IDs and GenoFLU results | Computed after analysis; no external acquisition. Units remain WINGS samples rather than birds unless the analysis explicitly defines birds. |
| APHIS detections | Run geography and dates for Explorer inspection | Retrieves the official full CSV during preparation when downloads are allowed. A verified cached download, then the bundled snapshot, provide fallback. The card identifies the source and date. Explorer filters the pinned snapshot by geography and date. |

For scoped terminal/API comparisons, public host matching is conservative: punctuation/case normalization and recorded
common/scientific labels, not fuzzy taxonomy. Public records with missing month or
unmatched host/region are excluded from a scoped comparison, with the source audit
retained. Counts describe records in that source, not prevalence or complete
surveillance coverage. The report labels scoped comparisons.

## First-time eBird setup

Open [eBird data access](https://ebird.org/data/download) from the preparation panel.
Request **all species** and include every listed region. Under **Choose date range**,
enter the single **From** and **To** month/year shown by WINGS. These inclusive
months span the earliest start and latest end across all sample matching windows,
including gaps between them. For example, windows from 2025-03-16 through
2026-05-08 require **March 2025 → May 2026** on eBird's form.
Include **sampling event data**, and retain the downloaded terms and citation.
WINGS still filters the download using the original per-sample date windows;
the broader download range does not change analysis windows or package coverage.
The source release must cover the requested dates. Do not change a release label
to make old data appear current.

Extract one release into a folder containing one `ebd_…relMon-YYYY…txt[.gz]`
observation file, one sampling `.txt[.gz]` file, and the matching
`terms_of_use.txt` / `recommended_citation.txt`. Enter that folder's path on the
runner computer and confirm all-species and geographic/date coverage. WINGS
filters and seals a reusable package outside the checkout. Large imports can take
time; they are separate from sequencing analysis. WINGS validates internal scope,
release and checksums; coverage of the original custom download is a user
attestation, not something inferable from absence of observations.

Alternatively, enter an existing package folder. Packages prepared through this
interface are discovered automatically under the context cache. Legacy caches
without original attribution need migration; see
[portable eBird packages](ebird-context-packages.md). Missing EBD files do not stop
analysis in the browser workflow. Terminal users can explicitly require sources. Status and Trends uses separate access
and caches; EBD approval does not imply a phenology key is present.

## Storage, network, and reproducibility

Context cache: `~/.cache/wings/context`, configurable via `WINGS_CONTEXT_CACHE`.
Phenology raster cache: `~/.cache/wings/ebirdst`, or `WINGS_EBIRDST_CACHE`.
Both must be outside the checkout. Phenology preparation retains the run’s saved
Conda package-cache setting and uses the launcher’s native-platform checks. Its
Conda environment prefix stays outside context snapshots, so copying prepared
context does not copy or relocate installed environments. Run selections live under each local run's
`context/snapshots/<id>/`, with metadata, provider statuses, artifacts, and hashes.
A new preparation creates a new snapshot instead of overwriting the prior one.
Full public genotype source aggregates are retained beside the selected subset.

FASTQ and the complete metadata file stay local. When enabled, provider requests
can disclose selected coordinates, dates, regions, or species. Credentials are
read from the runner environment, never entered into the page or written to the
selection. Context logs may contain local paths. The Explorer embeds a reduced
status record with query scopes rather than the complete selection/settings.

Offline preparation uses cached weather/BirdCast and a valid public genotype seed,
and can verify/import local eBird packages. It does not invoke the phenology
downloader: reuse an already prepared selection for offline phenology. Offline
with missing sources is explicit unavailability. Optional failures do not become
zero biological measurements. A schema-valid empty public comparison is labeled
unavailable when no source/matching records exist.

The main workflow verifies prepared selections, artifact hashes, configured paths,
and sample IDs before scheduling. Resumes verify their saved configuration and
artifacts. Public snapshot acquisition is a separate Snakemake rule; HTML rendering
does not refresh a prepared source. Context status and the selected public
snapshot are tracked as replay inputs. Historical re-execution prefers archived
context inputs and does not recontact providers for them.

## Terminal use without genomic processing

From the repository, inspect a plan:

```bash
python scripts/context_setup.py plan --metadata metadata.tsv
```

Optionally create an options JSON file. This example matches the launcher's online
acquisition and full-reference behavior; EBD remains a guided import:

```json
{
  "selected_sources": ["ecology", "phenology", "public_genotypes", "ebird", "outbreak"],
  "days": 30,
  "network": true,
  "phenology": true,
  "phenology_year": 2023,
  "ebird_package": "",
  "ebird_source": "",
  "all_species_confirmed": false,
  "outbreak_file": "",
  "global_genotypes": true,
  "required": []
}
```

`selected_sources` controls acquisition; an empty list skips all external sources.
Omitting it preserves legacy defaults (including the `phenology` toggle). The terminal
`required` option remains supported; a required source must also be selected.
For existing terminal/API workflows, omitting `global_genotypes` retains the legacy
scoped default. Set it to `true` to retain the full reference, as the launcher does.
The full reference covers the upstream dataset's included SRA runs; it is not an
exhaustive worldwide genotype collection or a population prevalence estimate.

Prepare context and write a **new** configuration overlay (existing files are not
overwritten):

```bash
python scripts/context_setup.py prepare --metadata metadata.tsv --options context-options.json --output-dir "$HOME/.wings/context-demo" --config-out config.context-prepared.yaml
```

This command does not start the main workflow. When ready, use the overlay with
your usual Snakemake command. A dry-run inspects the resulting job plan:

```bash
snakemake --cores 1 --use-conda --configfile config.context-prepared.yaml --dry-run
```

Do not launch a full rerun merely to validate this update. Existing result sets
may require substantial recomputation depending on their intermediate files.
For the launcher, restart only when no analysis is running, then reload its local
page to load the updated scripts.

## Validation

```bash
python -m unittest discover -s tests -p 'test_context*.py' -v
node tests/test_context_setup_ui.cjs
python tests/integration_context_setup.py
```

The integration test runs extracted production snapshot and metadata rules on
synthetic files in a temporary directory, without Conda downloads or sequencing
jobs. Other checks cover metadata binding, source matching, unavailable sources,
required-source blocking, offline commands, snapshot integrity, local API
concurrency, resume validation, and UI behavior using a simulated DOM/network.
These checks do not establish live provider availability, browser visual rendering,
or successful Conda creation on every platform. Provider endpoints and reference
versions still require periodic maintenance and live smoke tests.

## Folder selection and seasonal reference

**Choose folder…** opens a native chooser on a local Mac. Linux, SSH sessions,
and Macs without an available graphical chooser use a dialog listing folders on
the runner computer. The launcher obtains APHIS data automatically. Selection returns only the
path; no directory contents are uploaded or imported until context preparation.
Cancel leaves the previous value unchanged. Manual paths remain available.

The browser starts from accessible Home, Downloads, Documents, project, project-parent,
run-storage and common mount locations. Set `WINGS_BROWSE_ROOTS` before starting the
runner to add locations (separate paths with the operating system's path separator,
colon on macOS/Linux). Hidden paths and symlinks leaving a selected browser root are
not listed. Browsing endpoints require a same-origin loopback JSON request. They
return directory names and CSV names, never file contents.

**Previously prepared eBird data** means a reusable WINGS eBird context package,
with observations, sampling effort, terms, citation and integrity/scope records.
It is separate from a `.wings` report bundle. A selected download overrides automatic
cache reuse; an explicitly selected prepared folder overrides the download selection.
The UI keeps these two choices mutually exclusive and resets coverage attestation
when the download changes. Confirm the new download's scope before importing.

**Seasonal bird patterns** describes phenology: changes in bird abundance through
the annual cycle. The browser currently offers **2023 — released 2025**, matching
the version-pinned species reference in WINGS. It is not labeled as the latest release,
and is not an observation of migration during the sample year. The core phenology
builder retains its existing advanced support for supplied taxonomy and caches.

See [automatic APHIS acquisition](aphis-acquisition.md) for download, fallback,
offline, cache, and provenance behavior.
