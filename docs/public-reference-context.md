# Public reference context in the Surveillance Explorer

This optional display feature annotates **pre-existing contextual segment trees**
with reviewed GenBank record metadata. It does not download sequences, select
biological references automatically, align sequences, or infer contextual trees.
Your current sample-only trees will remain sample-only until contextual trees
are supplied. The input trees must already contain the desired sample and public
reference tips.

## What a reviewer sees

- WINGS samples retain host-colored circles and their local QC evidence.
- Public references have teal squares, accession.version links, and a separate
  selector. Selecting a reference highlights its explicitly linked records in
  all available trees while retaining the selected WINGS sample for comparison.
- Choosing a WINGS sample clears the reference selection. Clear selection resets
  both selections and restores all eight segment panels.
- Public metadata display host, isolate, location, collection date and precision,
  segment availability, and the parent-node support label as supplied. No support
  method, probability, transmission link, or raw-read QC is inferred.
- Unannotated tips remain gray. Missing metadata, missing trees, and absent tips
  have distinct explanations. Public reference tips are independent of the local
  sample host filter, map, and ecological windows.
- A provenance disclosure records manifest and tree SHA-256 values, retrieval
  date, selection notes, and citation. These identify inputs; they do not certify
  the biological correctness or completeness of the underlying records.

## Reviewed metadata input

Use a UTF-8, tab-delimited file with the header in
`resources/references/manifest-template.tsv`. One row identifies one public tip
in one segment. The template intentionally contains no biological records.

| Column | Meaning |
| --- | --- |
| `reference_id` | Reviewer-assigned identity shared only by records known to represent the same biological sample. Blank uses accession.version and does not link across segments. |
| `segment` | HA, NA, PB2, PB1, PA, NP, MP, or NS. |
| `tip_label` | Exact leaf label in that segment's supplied Newick file. Use labels distinct from WINGS sample IDs and their underscore-prefixed forms. |
| `accession_version` | Versioned NCBI nucleotide accession; e.g. the accession and version supplied in the source metadata. |
| `isolate`, `host`, `country`, `state` | Submitted metadata, or blank when unknown. Do not fill unknown locations from related records. |
| `collection_date` | YYYY, YYYY-MM, YYYY-MM-DD, or blank. Partial dates retain their original precision. |
| `linkage_basis` | Documented basis for common sample identity, such as a verified shared BioSample identifier. Required and identical for records sharing a reference_id. |

Each reference group can have at most one record per segment. Duplicate
accession versions and duplicate segment/tip pairs are rejected. Conflicting
nonempty host, isolate, date, or location fields within a linked group are
rejected for review. Matching isolate strings alone does not establish common
sample identity; the importer relies on the reviewer's documented linkage basis.

NCBI metadata describe submitted records and can be incomplete or revised.
Relevant official documentation:
[NCBI influenza metadata](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/how-tos/virus/influenza-metadata/)
and [NCBI Virus help](https://www.ncbi.nlm.nih.gov/labs/virus/vssi/docs/help/).
Record the actual source, snapshot date, and selection rationale. A bounded
reference panel reflects its selection criteria and public sampling biases.

## Provenance input

Create `resources/references/provenance.json` for the reviewed manifest:

```json
{
  "manifest_sha256": "REPLACE_WITH_SHA256_OF_THE_EXACT_TSV_BYTES",
  "retrieved_on": "YYYY-MM-DD",
  "selection_notes": "Describe the actual reviewed source and inclusion/exclusion criteria",
  "citation": "Citation for the source snapshot and relevant records"
}
```

The checksum and full ISO retrieval date are validated. To print the checksum:

```bash
python -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("resources/references/manifest.tsv").read_bytes()).hexdigest())'
```

Changing the TSV requires updating its recorded checksum after review. Use a
new dated snapshot when refreshing public records so prior runs remain auditable.

## Configuration and report rebuild

Merge `config/public-references.example.yaml` into your active `config.yaml`,
set `enabled: true`, and point to the reviewed manifest, provenance, and supplied
tree directory. `{segment}_Tree.newick` is the default filename pattern; filenames
must retain a segment token the existing tree loader recognizes (for example,
`HA_Tree.newick`). Use MP for the matrix segment.

`tree_dir` overrides the Explorer's displayed trees only. Missing segment files
remain unavailable; this mode does not fill gaps from a different analysis.
An empty directory is an error. Omit `tree_dir` to annotate the normal report
trees when those already contain public tips. Only the first Newick tree in
each file is displayed, without rerooting or time calibration.

Regenerate all three report artifacts to avoid using stale embedded JavaScript
or metadata (adjust result paths if your configuration uses a different directory):

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

CLI callers of `scripts/build_surveillance_explorer.py` can supply
`--reference-manifest` and `--reference-provenance` alongside the existing
`--metadata`, repeated `--tree`, and `--output` arguments. No new Python package
or API key is required. Internet access is needed only when the reviewer opens a
GenBank link; report selection and highlighting work offline.

## Public repository and validation

Commit code, the blank template, documentation, configuration example, and
synthetic tests. The default reference snapshots/trees are gitignored to avoid
silently publishing run-specific material. If a reviewed reference dataset is
intentionally published separately, include source attribution, provenance,
selection criteria, and any applicable reuse conditions. The report bundle
contains the displayed public metadata and tree geometry, so review these along
with local sample metadata before sharing it.

Run the focused checks with:

```bash
python -m unittest discover -s tests -p test_public_reference_context.py -v
node --test tests/test_public_reference_context.cjs
```

The fixtures use synthetic metadata, placeholder accession strings, and toy tree
geometry. They contain no nucleotide sequences and are not a real reference panel.
