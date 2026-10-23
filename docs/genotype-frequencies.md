# Genotype frequencies in the WINGS portal

Open **Genotype frequencies** from the WINGS home page or run setup page.
The page provides an overall bar chart and, when collection metadata is present,
monthly stacked bars. Choose a host, location, month range, and denominator.
**From month** and **Through month** are dropdown pickers with month names and
years. They include the full calendar between the first and last recorded
collection month, so they work without browser-specific date-input support.
Bounds are inclusive; clear them with **First available month** and **Last
available month**. A year-only collection date is not assigned a month.
Use **Genotype** to show one recorded genotype, including rare labels outside
the default top ten. Its percentage still uses every eligible run matching
the host, location, and date filters. The graph, count table, and CSV show the
selected genotype; a zero means it was absent from the included records in
that period, while an unavailable frequency means there was no denominator.
Download the graph as SVG or all underlying category counts as CSV.
The page and graph use the supplied ASU maroon, gold, black, white, green, blue,
orange, gray, copper, turquoise, and pink values. The ten leading genotypes use
solid colors. Other assigned genotypes and unavailable assignment categories
use distinct patterns in ASU colors, also embedded in downloaded SVG graphs.

The initial snapshot was built from the supplied `genoflu_results.tsv`:
22,784 unique SRA run IDs, 15,840 assigned calls, and 6,944 unassigned calls.
It contains 82 recorded genotype labels. No collection metadata was supplied
with that snapshot, so its initial chart covers all runs without a date axis.
The genotype table's `date` column is not used as a collection date.

## Inside the run dashboard

The Surveillance Explorer has a **Genotype frequencies** tab with a **Data
source** selector: **All** (default), **WINGS**, or **Public Data**. All three
views default to monthly frequencies when collection months are present.
**All** shows one panel per available source on the same monthly axis, with
the same genotype colors. Each source retains its own percentage denominator
and counting unit. A month absent from one source has unavailable frequencies
in that panel; it is not reported as zero. Choosing **Overall frequencies**
includes records without collection months when no date bounds are set.
Changing source updates the available genotypes, hosts, locations, month
pickers, labels, and denominator. Filters are remembered separately for each
source. The standalone portal's **All** view shows its available public records;
WINGS is enabled when run data are available in the completed report. The source
attribution includes a clickable link to the Andersen Lab repository in both
**All** and **Public Data** views.

WINGS counts come from the existing Explorer's `samples` array and recorded
GenoFLU classifications. Each unique sample ID counts once. Identical duplicates
collapse, conflicting duplicates stop the build, and unavailable calls retain
separate not-assigned, not-eligible, skipped, disabled, failed, or missing states.
An assigned-genotype percentage excludes these unavailable calls; **All included
samples** retains them in the denominator. No genotype is inferred or rerun.
Host names use recorded metadata or an unambiguous name already in the Explorer.
Public SRA runs and local samples are never pooled, including in **All**. The
shared top-ten display is ranked by the sum of category counts across sources;
this affects only which labels appear separately, not their denominators.
Select an individual genotype to display it even when it falls outside that
shared top ten. Counts and CSV rows identify the source and counting unit.

The chart code, styles, and both grouped snapshots are inside the HTML; opening
it does not fetch public tables or use a local server. Source hashes and the
public source commit are recorded in the embedded view. SVG and CSV downloads
identify the selected source and its counting unit. The Explorer's shared sample
and host controls are hidden on this tab; use the graph's own filters.

To update a completed run's report and portable bundle using existing outputs:

```bash
snakemake results/wings_report_bundle.wings \
  --cores 1 --use-conda \
  --allowed-rules run_summary_html wings_report_bundle \
  --forcerun run_summary_html wings_report_bundle
```

Then open `results/run_summary/run_summary.html` and select **Surveillance
Explorer → Genotype frequencies**. If using the portal bundle viewer, load the
newly rebuilt `results/wings_report_bundle.wings`. This command requires the
completed sample reports, summary inputs, and run provenance already to exist.
An older HTML or `.wings` file keeps its original contents until rebuilt.

## Automatic public-data refresh

`run_summary_html` calls `scripts/refresh_genotype_frequencies.py` before embedding
the chart. The default maximum age is seven days, measured from a successful
fetch or the snapshot's build time, not its filesystem modification time. Fresh
snapshots are reused. Stale ones download both public metadata tables from one
immutable source commit, validate their join and counts, and atomically replace
the cache. Local sample data are not sent with these requests.

The cache lives in `~/.cache/wings/genotype-frequencies`. A failed fetch or invalid
download leaves the last valid snapshot intact, including its original date.
The rendered source details identify a fallback. If neither the cache nor the
supplied snapshot is valid, the refresh fails rather than reporting empty data.
The exact report copy is saved as
`results/run_summary/public_genotype_frequencies.json` and embedded in the HTML.

This check runs when a report is generated. It does not run in the background,
on installation, when an existing report is opened, or when Snakemake has
nothing to rebuild. Defaults need no configuration changes. An optional section
for `config.yaml` is provided in
[`config/genotype-frequencies.example.yaml`](../config/genotype-frequencies.example.yaml):

```yaml
genotype_frequencies:
  auto_refresh: true
  max_age_days: 7
  cache_dir: "~/.cache/wings/genotype-frequencies"
  snapshot: "assets/data/genotype-frequencies.json"
  ref: "master"
  offline: false
```

Use `offline: true` or `auto_refresh: false` to prevent network requests. In
offline mode an explicit valid snapshot takes precedence over a newer cache.
For reproducible comparisons, set `ref` to the exact 40-character public source
commit. A pin never silently falls back to another commit. Historical
re-execution also disables these network requests; supply the archived public
snapshot through `historical_reexecution.frozen_inputs.genotype_frequencies`
and its source commit through `genotype_frequencies.ref`.

For a standalone portal refresh, or a script suitable for your existing job
scheduler, run from the repository root:

```bash
python scripts/refresh_genotype_frequencies.py
```

It updates `assets/data/genotype-frequencies.json` only after selecting a valid
cached or newly fetched dataset. Use `--force` to fetch immediately, `--offline`
to prevent downloads, or `--max-age-days 1` for a daily freshness threshold.
Report builds keep their public copy separate and do not modify this tracked
portal asset. The standalone page displays changes after it is reloaded.

## What the percentages mean

The default denominator is the number of **runs with an assigned genotype** in
the selected period and filters. The alternate denominator is **all included
runs**; unassigned, missing-result, conflicting-call, and unrecognized-label
categories then appear in the graph. Coverage counts remain visible with either
denominator. Monthly percentages are calculated separately for each month.
Months with no eligible runs are gaps, not zero-frequency estimates.
The monthly graph initially shows only months with eligible runs. Its note
identifies omitted months; bar spacing then does not represent elapsed time.
Choose **Show all calendar months** to restore the full calendar, with dashed
columns for unavailable frequencies. This display setting does not change
percentages, run totals, the count table, or the CSV download.

With **All genotypes**, the chart shows the ten most frequent assigned genotypes across the selected
records, with all other assigned labels combined into one bar or stack. The
count table and CSV retain every label, including individual `Minor` labels.

The unit is one SRA run, not an individual animal, specimen, or outbreak.
The source repository covers selected BioProjects and is not a representative
population sample. These percentages describe the included sequencing records;
they are not infection prevalence estimates. The supplied genotype labels are
displayed without inferring biological properties from their names.

## Refresh from both public tables

From the WINGS repository root, run:

```bash
python scripts/build_genotype_frequencies.py --fetch
```

This explicitly downloads the two public metadata tables from
`andersen-lab/avian-influenza`. It resolves `master` to an immutable commit first
and obtains both files from that commit. To reproduce a particular snapshot,
pass `--ref` with its recorded 40-character commit SHA. File SHA-256 hashes,
source URLs, build time, and import counts are saved in the output JSON.
This refresh does not download sequences or run the analysis pipeline.

The output is `assets/data/genotype-frequencies.json`. Reload `genotypes.html`
in the local portal after replacing it. On the published website, commit and
deploy the updated snapshot along with the portal assets. The page does not
automatically fetch the upstream tables or refresh its snapshot.

## Import downloaded tables

For existing downloads:

```bash
python scripts/build_genotype_frequencies.py \
  --genoflu /path/to/genoflu_results.tsv \
  --metadata /path/to/SraRunTable_automated_normalized.tsv \
  --output assets/data/genotype-frequencies.json
```

The source normalizer identifies the metadata key as `Run`, the collection-date
column as `Collection_Date`, the host column as `Host`, and the location column
as `geo_loc_name`. Genotype assignments use `sample` and `Genotype`. Column names
are case-sensitive. Alternate date, host, or location headers can be specified
with `--date-column`, `--host-column`, and `--location-column`.

The importer performs a metadata-left join on `Run` → `sample`. Every unique
metadata run is retained, including runs without a genotype result. Genotype
records absent from metadata are counted in the audit and excluded from the
joined chart. With `--genoflu` alone, the universe is the unique genotype-table
run IDs and only overall frequencies are available.

Repeated run IDs with the same call are counted once. Conflicting genotype calls
are marked explicitly and excluded from the assigned denominator. Conflicting
date, host, or location values for the same metadata run cause the import to
stop rather than multiply rows or choose a record silently. The importer accepts
ISO day and month dates (`YYYY-MM-DD`, `YYYY-MM`); year-only, invalid, and other
date formats remain unavailable for monthly charts. Such records still count
in the unfiltered overall view. It never uses submission or processing dates as
substitutes for collection dates.

`Not assigned...` messages are treated as unassigned statuses rather than
genotype names. Blank labels and labels outside the supported forms such as
`D1.1`, `B3.13`, and `Minor114` are reported separately. Review any unrecognized
labels before changing the accepted vocabulary.

To inspect a different snapshot without changing the website, use **Load an
updated WINGS frequency snapshot**. The JSON file stays in the browser. It
contains grouped counts and source provenance rather than individual run IDs.

## Checks

```bash
python -m unittest discover -s tests -p 'test_genotype*.py'
node --test tests/test_genotype_frequencies.cjs tests/test_genotype_dashboard.cjs tests/test_explorer_tabs.cjs
```

The importer and chart calculations are tested for joins, duplicate IDs,
conflicting records, unavailable assignments, date precision, empty months,
filter-specific denominators, and preservation of rare labels in exports.
Dashboard checks cover offline loading, snapshot escaping, genotype filtering,
and iframe resizing.

Source: [andersen-lab/avian-influenza](https://github.com/andersen-lab/avian-influenza).
Metadata definitions: [metadata normalizer](https://github.com/andersen-lab/avian-influenza/blob/385108c26dd26e115af284ec6f8ef83022ea911b/scripts/metadata_normalizer.py).
