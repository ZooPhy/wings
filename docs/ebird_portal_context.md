# eBird context for the public WINGS portal

Status: design for review. Do not publish the derived dataset until the proposed
public use is confirmed with the Cornell Lab of Ornithology.

WINGS has two ways to display ecological context:

- The existing local EBD + sampling-event stage calculates checklist reporting
  frequency in the sample's configured geographic and date window. Original
  observations, checklists, and cache stay on the researcher's computer.
- An optional portal dataset provides previously computed **state-month-species**
  context. It supports public exploration without requiring visitors to download
  eBird files. A portal value is not a recalculation for an individual sample's
  date window or radius; label it "regional monthly context" wherever shown.

## Portal record contract (v1)

`schemas/ebird_portal_context.schema.json` specifies a single JSON record. A
portal export may contain an array of those records, together with the complete
release `terms_of_use.txt`, the release's `recommended_citation.txt`, and
machine-readable provenance. Do not include original observation or checklist
rows, sampling-event identifiers, precise eBird coordinates, observer IDs,
or other fields from the original downloads.

| Field | Meaning |
| --- | --- |
| `schema_version` | Literal `1`. |
| `ebird_release` | Shared observation and sampling-event release (for example `Aug-2026`). |
| `source` | Literal `eBird Basic Dataset`. |
| `country_code`, `state_code` | Region used to count checklists, such as `US`, `US-KY`. |
| `month` | Calendar month, `YYYY-MM`, in the checklist's local date. |
| `common_name`, `scientific_name` | Exact taxon labels from the source release; don't guess from four-letter codes. |
| `complete_checklists` | Number of distinct complete checklist groups in this region/month. |
| `reporting_checklists` | Number of those groups with at least one matching taxon report. |
| `reporting_frequency` | `reporting_checklists / complete_checklists`; undefined with no complete checklists, so omit that record. |

Keep the counts as well as the frequency: a rate without its denominator is
misleading. Deduplicate shared checklists by group before counting. Count a
species once per checklist irrespective of `OBSERVATION COUNT`. Only call a
missing species report a nondetection when the EBD observation coverage and
sampling-event population match; review whether provisional checklists require
their separate observation file before generating an absence-based denominator.

No record should assert bird abundance, infection prevalence, virus presence,
or a causal link to sequenced specimens. A sample's host and collection date
can select the corresponding portal species/month/region for display, but the
portal dataset itself contains no WINGS sample data.

## Publication gates

1. Validate local WINGS outputs: the Snakemake dry run should schedule
   `ebird_sampling_cache` and `ebird_summary`, not `ebird_observation_cache`
   when reusing the observation cache. Confirm the sampling-cache manifest,
   status counts, and one manual numerator/denominator spot check.
2. Confirm with Cornell that the existing data-access purpose covers generating
   and publicly distributing a state-month-species derived summary through a
   noncommercial research/education portal. If it does not, seek written
   approval before publishing the data.
3. Store only the derived records and attach the same eBird Data Access Terms
   and the release citation to each public dataset/package and visible report.
   Provide a link to the source and identify the eBird release. Never ship the
   original downloads or the local cache with the repository or report bundle.
4. Validate taxonomic matches and regional/monthly completeness for the release
   before activating the portal dataset. Expose missing or inapplicable context
   as such instead of substituting zero observations.

Data access terms: https://www.birds.cornell.edu/home/ebird-data-access-terms-of-use/

## Draft request to Cornell (do not send automatically)

Subject: Confirming public use of derived eBird summaries in WINGS

Hello eBird team,

We are developing WINGS, an open-source workflow and proposed noncommercial
public health and science community portal for avian influenza genomics and
wild-bird surveillance. We have access to the eBird Basic Dataset and matching
sampling-event data for the same release. We would like to derive and display
state-by-month-by-species summaries of the proportion of complete checklists
reporting each species. Public outputs would contain only regional aggregate
numerators and denominators, release provenance, the recommended citation,
and the eBird Data Access Terms. We would not redistribute observation-level
or checklist-level records or our filtered raw-data cache. The figures would
be described as ecological reporting context, not infection or abundance
estimates.

Would publicly sharing those derived summaries through WINGS be within the
purpose of our current eBird data access? If additional written approval or
conditions are needed, please let us know before we publish the dataset.

Thank you,
Matthew Scotch
