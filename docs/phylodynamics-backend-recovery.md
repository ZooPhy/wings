# Phylodynamics backend recovery

This package restores missing source files needed by the installed Phylodynamics
submission interface. It contains both example configurations, the reference
retrieval/selection and inference modules, workflow rules, environments, tests,
report builders and the optional BEAST/posterior modules.

The scientific modules were recovered from saved installers. Their hashes match
the prerequisites recorded by the posterior and shared-results integration
updates. The standalone comparison stylesheet was reconstructed. The sensitivity
rule explicitly calls the existing comparison builder to produce its declared
outputs, and includes the dating, posterior and shared-results rules.

Existing source files are preserved. The installer stages the combined files and
checks compatibility before adding missing files. It does not modify config.yaml,
run data, existing reports, caches, demo bundles, credentials or reference data.
It does not turn on BEAST or start an analysis. Use the separate BEAST submission
update if its method selector has not yet been installed.

Install from the repository with the Python environment used for WINGS:

```bash
python ~/Downloads/wings_restore_phylodynamics_backend.py --repo . --apply
```

Validation needs NumPy, SciPy, PyYAML, Node.js and Snakemake. The installer runs
offline numerical and display tests and a synthetic workflow dry-run. Java/BEAST,
ArviZ, MAFFT, IQ-TREE, TreeTime and live Nextclade/NCBI execution are checked in
their workflow environments; their absence during installation is reported.
The existing convergence, temporal-signal and numerical publication gates remain
in place. Passing installation checks does not establish model adequacy.

After installation, restart the native local runner with NCBI_EMAIL set, reload
the submission page and retry. Fast Phylodynamics builds its own HA tree and does
not require the separate Phylogenetics checkbox.

The backup manifest lists all required source paths to commit, including newly
created files. Commit these files to make other checkouts reproducible. No
biological result files are included in that list.
