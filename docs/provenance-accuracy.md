# Provenance accuracy and regression checks

The effective configuration is serialized into a Snakemake rule parameter.
With the normal rerun triggers, changing a nested setting or a command-line
override regenerates `effective_config.json` and dependent provenance records.
Using `--rerun-triggers mtime` disables parameter-based change detection; retain
the default triggers for this behavior.

The BLAST manifest defaults to `database_manifest.tsv` beside the configured
`blast_db` prefix. For a manifest stored elsewhere, set an explicit path:

```yaml
blast_db: /project/references/influenza/fluA_db
blast_db_manifest: /project/reference-records/influenza-manifest.tsv
```

The manifest must describe the selected database. WINGS does not fabricate a
missing manifest. The provenance record now also includes `blast.database_prefix`
and `blast.database_files`, with SHA-256 and byte size for each file matching the
prefix. Hashing large databases adds disk reads when provenance regenerates.
These are hashes of the actual index files, not a replacement for the source
and database-build information in the manifest.

`conda_environment_files` includes all thirteen rule-environment definitions,
including phylogeny and phenology, with the appropriate reporting definition
for the host platform. These are definition-file hashes. They do not claim that
disabled tools ran, or provide a lockfile for resolved packages. Enabled features
remain recorded in the effective configuration. Existing provenance JSON fields
and the schema-version value remain compatible; the BLAST fields are additive.

Run checks from the WINGS repository:

```bash
python -m unittest discover -s tests -p test_provenance_accuracy.py -v
python tests/integration_provenance.py --repo .
python tests/integration_missing_segments.py --repo .
```

The integration tests require Snakemake on PATH. They create isolated temporary
workflows with synthetic data, never read real FASTQ files, and never solve
rule-specific Conda environments or retrieve ecological inputs. Their logs and
summaries remain in the printed temporary directories. The missing-segment test
uses production status rules and the bundle builder, with fixture assembly
outputs and HTML. It includes an expected-failure control using the old inputs.
It does not test biological accuracy or production Quarto rendering.

The provenance test executes the production effective-config and provenance
rules. It checks initial recording, a nested configuration change with unchanged
configuration-file timestamp, changed environment definitions, changed database
index content, and an explicit manifest override. All must pass.

The `provenance-regression.yml` GitHub Actions workflow runs these checks on Linux
and macOS for pushes and pull requests to `main`, and supports manual dispatch.
It retains synthetic test evidence for fourteen days. It becomes active after
the workflow and corresponding source/test changes are committed and pushed.
