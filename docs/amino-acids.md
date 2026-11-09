# Consensus amino acid comparisons (version 1)

WINGS compares annotated, QC-qualified consensus proteins with a versioned reference panel. The module reports observed protein differences and exact-coordinate literature annotations. It does not estimate within-sample allele frequencies. Its outputs are independent of Medaka's draft-relative VCF calls.

## Setup and use

From the WINGS repository in `snakemake_env`:

```
python scripts/wings_amino_acids.py prepare
python -m unittest discover -s tests -p test_amino_acids.py -v
python tests/integration_amino_acids.py --repo .
snakemake amino_acids_report --cores 2 --use-conda
```

`prepare` downloads NCBI's translated CDS FASTA for eight fixed RefSeq accession versions: NC_007357.1 through NC_007364.1, A/goose/Guangdong/1/1996 (H5N1). It validates the returned accession versions and records source hashes and retrieval time. Existing valid panels are retained; `--replace` explicitly refreshes annotation content. `--fasta PATH` accepts an offline copy of the same NCBI CDS FASTA response. Network errors leave no completed panel. This initial reference fetch was not live-tested in the development environment because outbound access was blocked.

The default panel file is `resources/amino_acids/reference_panel.json`. Keep it for reproducibility. A prepared panel is embedded in each sample's JSON provenance. Acquisition is separate from analysis, and analyses never silently refresh references. Missing panels produce `NEEDS_REFERENCE` in the report. Run `prepare` and rerun the target to populate comparisons.

The new report is a dependency of the normal run summary. Its contents are embedded as an isolated, searchable iframe in `run_summary.html`; the existing bundle builder therefore carries the report in the `.wings` file. Standalone HTML, TSV, and JSON are under `results/run_summary/amino_acids/`. Per-sample JSON is under `results/<sample>/amino_acids/changes.json`. A direct `amino_acids_report` invocation builds the standalone report; rerun the normal workflow to refresh the run summary and bundle.

## Scientific scope

This is an initial H5N1 panel, not a comprehensive influenza or FluSurver replacement. A passing similarity threshold does not identify subtype or clade. All reported coordinates are 1-based positions in the full-length selected reference protein, including signal peptides. H3-equivalent, mature-HA and other conventional numbering systems are not inferred. Extension to these systems requires reviewed residue maps.

VADR's `.vadr.pass.tbl` supplies CDS coordinates; only sequences with passing annotation are analyzed. Joined intervals and reverse-strand intervals are translated in their specified biological order. Separate overlapping CDSs, such as PB1 and PB1-F2, remain separate proteins. Partial CDSs, nonstandard translation tables, translation exceptions, explicit ribosomal slippage, overlapping intervals within one CDS, invalid boundaries, missing starts/stops, and incomplete codons are flagged or rejected. Programmed frameshift products such as PA-X may be unassessed; they are never synthesized from a guessed frame. Failed VADR sequences cannot supply reliable protein calls. Missing or unannotated inputs remain visible in sample JSON and review status.

Comparison uses deterministic global affine-gap alignment: match +2, mismatch -3, gap open -8, gap extension -1. Equally optimal alignment paths or equally scoring references suppress calls for that protein. Default minimum identity and reference coverage are both 0.90. Identity excludes ambiguous residues; positions containing X never generate substitutions. Differences after an internal stop are suppressed. Indels describe differences in the protein alignment; they do not establish the nucleotide mechanism. They are reported residue by residue. Aligned X positions, premature stops and all withheld comparisons retain explicit statuses.

The protein panel is drawn from annotated reference CDS translations. The module does not annotate a new CDS by choosing an arbitrary reading frame. It cannot discover every accessory ORF or resolve complex frameshifts. Validate outputs against independently reviewed influenza sequences before using this first release for interpretation.

## Evidence

`resources/amino_acids/evidence.json` contains a deliberately small, versioned pilot catalog: PB2 E627K and D701N with primary study citations. These entries are context-qualified literature associations, not predictions of the phenotype of a sample. No overall risk or severity score is computed. Unannotated changes have not been assessed for biological effect. This catalog does not cover antiviral resistance or all known surveillance markers.

Matches require the exact reference ID, position, reference residue and alternate residue. Loading evidence checks that its reference residue matches the panel. Matching a site alone does not attach an annotation. If a marker is already present in a selected reference, a comparison-based substitution screen will not identify it as a change; this is not an exhaustive marker-presence screen.

Primary sources:
- Shinya et al. (2004), PB2-627 in H5N1 mouse infection: https://pubmed.ncbi.nlm.nih.gov/15016548/
- Li et al. (2005), PB2-701 in duck H5N1 mouse infection: https://pubmed.ncbi.nlm.nih.gov/16140781/
- NCBI feature-table specification: https://www.ncbi.nlm.nih.gov/genbank/feature_table/
- FluSurver concept and limitations: https://flusurver.bii.a-star.edu.sg/help/faq.html

This release does not redistribute FluSurver's curated database. GenBank occurrence counts, maps, structural models, and alternative numbering are future extensions.

## Configuration

Optional configuration keys (no config file is edited by the installer):

```
run_amino_acids: true
amino_acid_reference_panel: resources/amino_acids/reference_panel.json
amino_acid_evidence: resources/amino_acids/evidence.json
amino_acid_min_identity: 0.90
amino_acid_min_coverage: 0.90
```

`run_vadr: false` produces a VADR_DISABLED result. `run_amino_acids: false` produces DISABLED. Changes to the panel, evidence, script, consensus, VADR outputs or comparison thresholds cause recomputation through declared Snakemake dependencies. Each result includes hashes, alignment settings and reference metadata; exported JSON and the portable report preserve them.

Custom reference panels use JSON `schema_version: 1` and a nonempty `references` list. Each record requires a unique `id`, versioned nucleotide `accession`, `protein_id`, `gene`, `segment`, unambiguous amino acid `sequence`, and `source_url`. Supply `numbering` and `strain` descriptions. Evidence for other reference IDs must be independently mapped and reviewed. Supported segment names are PB2, PB1, PA, HA, NP, NA, MP and NS.

## Validation included

Unit tests exercise splicing, reverse strand, overlapping genes, ambiguous bases, indel numbering, nonunique alignment, premature stops, malformed annotations, evidence/reference agreement, export escaping, embedding, and missing-reference status. The synthetic Snakemake integration test uses the actual production rules and checks reruns after consensus and evidence changes. It never downloads reference data or executes sequencing jobs. Real clinical/field sequence benchmarking is still required; synthetic checks alone do not establish diagnostic performance.
