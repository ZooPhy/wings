# Metadata preparation wizard

The Metadata step in `run.html` has a **Create or fix metadata** button. It opens
a browser-only editor and reuses filenames selected in the Sequences step. It
does not read FASTQ contents, start sequencing, or send metadata to an external
normalization service. The existing TSV upload remains available.

The five steps are import/column mapping, sample matching, host normalization,
collection normalization, and review/export. CSV, TSV, semicolon-delimited tables,
and pasted spreadsheet data are supported. The wizard accepts up to 10 MB and
10,000 sample rows. It displays 50 rows at a time and exports every row. Extra
columns and quoted/multiline values are preserved. Excel workbooks should be
exported to CSV/TSV before importing.

`sample_id` is the required schema column. IDs must be unique and match the
selected FASTQ basenames exactly after stripping `.fastq.gz`, `.fq.gz`, `.fastq`,
or `.fq`. WINGS requires one file per sample and a consistent extension. Filename
suggestions require confirmation; matching does not rename files. Users can add
missing rows and explicitly remove unwanted rows.

Host names use the repository's `resources/ebird_host_codes_2025.tsv` dictionary.
Bird codes are labeled WINGS host codes, not ISO codes. Accepted aliases such as
CAGO and CANG are retained. Exact common-name matches propose an accepted code;
unrecognized names remain visible for review. No fuzzy species assignment occurs.

Countries are normalized to ISO alpha-3. Country labels/codes are bundled from
the pycountry project's ISO 3166-1 database, credited in the reference JSON.
US state/DC and Canadian province/territory names and postal codes are normalized
within their recorded country. Other regions retain their text. Quebec/Québec
both match. Latitude and longitude are checked for finite values and legal
ranges. Coordinates are not geocoded or inferred from a state centroid.

Dates use `YYYY-MM-DD`. Ambiguous dates require an explicit day/month or month/day
choice. Invalid calendar dates remain errors. Proposed changes are shown before
application; users can download the full proposed change log. Manual edits and
accepted standardizations are also available as a change log.

Review separates blocking errors, warnings, and collection-complete row counts.
Optional unknown fields may remain blank. Warnings must be acknowledged before
export. A valid file can be downloaded before FASTQs are selected, but **Use this
metadata** requires exact FASTQ matching. It selects a generated `metadata.tsv`
through the existing file input and change event, so the ordinary run form and
context setup observe the same file. Browsers without programmatic file selection
can download the TSV and choose it manually.

The run form uses the shared quoted-TSV parser when available, including for
multiline extra fields. Its legacy fallback remains for an older cached page.
Existing uploads retain the runner's 25 MB size allowance and have no wizard row
limit. The backend metadata validator and execution workflow are unchanged.
Importing through the wizard removes a UTF-8 BOM; exports have no BOM, as required
by the runner's current metadata-ID reader.

Checks:

```bash
python scripts/build_metadata_reference.py --check
node --test tests/test_metadata_wizard.cjs
python -m unittest discover -s tests -p test_metadata_wizard_contract.py
node tests/test_metadata_wizard_browser.cjs
```

The browser check requires Playwright and Chromium. GitHub's Metadata wizard
workflow installs them and checks the full import/export/handoff, duplicate-ID
gating, mobile dialog sizing, and BLAST/VADR/Medaka table styling with synthetic
fixtures. Reference data is served from the same site as the wizard; importing
does not upload sample data. Rebuild and refresh demo report assets separately
to update the VADR and consensus/variant table styles in saved bundles.

After editing the host-code TSV, run `python scripts/build_metadata_reference.py`
and commit the refreshed reference JSON. Country labels/codes and US/Canada
region records are maintained in that JSON with source attribution.
