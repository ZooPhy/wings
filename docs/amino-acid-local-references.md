# Automatic references from the existing flu_db

`assign_amino_references.py` reads saved amino acid sample JSONs, searches their stored segment consensus sequences against the existing local nucleotide database, and retrieves annotated records for the shortlisted versioned NCBI accessions. It validates the database FASTA checksum against database_manifest.tsv and checks each retrieved nucleotide sequence against its corresponding local FASTA sequence (either orientation).

Default shortlist: 3 nucleotide hits per stored segment consensus, at least 70% nucleotide identity and 80% query coverage. The final selection uses the existing global protein-alignment score among validated same-gene candidates in that shortlist. This is not an exhaustive protein search across all database records. Increase `--candidates` to broaden it. The available reference strains depend on the database snapshot; modern dates and exact FluSurver matches are not guaranteed.

NCBI CDS annotations supply complete translations. Spliced products are extracted from annotated join/complement locations, not from whole-segment frame guesses. Provided translations must match the translated reference nucleotide CDS. Partial, unsupported, pseudo, exception-containing or ambiguous reference products are excluded, and rejection reasons are recorded. Different proteins can select different accessions. Identical proteins tied across references retain equivalent accession metadata; nonidentical top-score ties remain withheld.

The first run downloads public NCBI reference annotations by accession and caches them in resources/amino_acids/ncbi_annotation_cache. Sample sequences are not submitted to NCBI. Use `--offline` after the required annotations are cached. Reference fetching errors and cache misses stop the run without writing result files. All samples are computed before writing the new result outputs; downloaded annotation cache files may remain after a failed run.

BLAST is located on PATH, in .snakemake/conda/*/bin/blastn, or via the ncbi/blast-static:2.17.0 Docker image. Docker Desktop must be running for Docker use. Container searches mount only the local DB and temporary query directory read-only and run without container network access. You may pass `--blastn /absolute/path/to/blastn` explicitly.

```bash
python scripts/assign_amino_references.py \
  --inputs results_amino_resolved/*/changes.json \
  --output-dir results_amino_auto

python scripts/wings_amino_acids.py report \
  --inputs results_amino_auto/*/changes.json \
  --html results_amino_auto/amino_acid_landscape.html \
  --tsv results_amino_auto/amino_acid_landscape.tsv \
  --json results_amino_auto/amino_acid_landscape.json
```

Each new sample directory contains changes.json and its exact reference_panel.json. Provenance includes source-result hash, previous panel, new panel checksum, database manifest and index checksums, BLAST version/settings/hits, rejected candidates and selected versioned accession/protein metadata. Original input JSONs and the database are preserved. No raw reads, Porechop, IRMA, Medaka, VADR jobs or normal Snakemake workflow are rerun.

HA processing regions are taken from explicit sig_peptide/mat_peptide features in the selected nucleotide reference and projected through its annotated HA CDS. The displayed coordinate ranges and source links follow that reference. Missing region annotations are not guessed; the pinned 1996 fallback remains limited to its matching accession. Existing region colors and selected-reference grouping are preserved. Mutation-effect evidence is attached only for exact reference/residue matches; old annotations are not transferred to a new strain solely by residue number.

The current reassignment command is a standalone post-processing action. It does not change the default panel used by the normal workflow's `prepare` command. Use the new result directory for the automatically selected-reference report.

Validation uses synthetic GenBank records and a mocked BLAST executable for offline CLI/report integration, plus location, manifest, tie-handling and UI tests. Production NCBI connectivity and the user's database contents must be checked on the user's machine.
