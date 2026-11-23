# Report and reference guide

[README](../README.md) · [Questions and answers](../faq.md) · [Command-line guide](command-line-guide.md)

This guide connects saved reports, source/reference provenance, and maintenance
procedures. A completed workflow is not a statement that every sequence passed
every QC or annotation check. Review statuses and the evidence behind them.

## Outputs and provenance

Default paths are relative to the analysis working directory; a saved run may
set a different `results_dir`.

| Output | Path |
| --- | --- |
| Sample report | `results/<sample>/summary/<sample>.sample_summary.html` |
| Sample summary | `results/<sample>/summary/<sample>.sample_summary.tsv` |
| Run report | `results/run_summary/run_summary.html` |
| Portable report bundle | `results/wings_report_bundle.wings` |
| Run provenance | `results/run_summary/run_provenance.json` and `.tsv` |
| VADR status table | `results/<sample>/vadr/<sample>.vadr_summary.tsv` |
| VADR execution log | `results/<sample>/vadr/<sample>.vadr.log` |
| Historical comparison | `results/run_summary/interpretation_stability.json` and `.tsv` |

The bundle contains rendered reports, embedded data, and provenance. It does not
replace the full analysis workspace, raw reads, or external reference caches.
Retain those separately. A `.vadr.done` file records completion of the workflow
rule, not that every sequence passed VADR. Missing/QC-excluded inputs and failed
annotation results must be interpreted from their statuses and logs.

See [provenance and accuracy](provenance-accuracy.md),
[Medaka status reporting](medaka-status-reporting.md), and
[public-reference context](public-reference-context.md).

## Report and bundle maintenance

Opening a saved report in a newer app does not update its embedded UI or evidence.
The app viewer, workflow checkout, generated HTML, and downloaded bundle can
have different versions. When a report looks older than expected:

1. Record the generating checkout's commit and inspect the bundle's provenance.
2. Compare the bundle's SHA-256 on the generating host and viewing computer.
3. Check the saved configuration for enabled modules and result paths.
4. Preserve the original bundle before rebuilding presentation or evidence.

For an uncompressed `.wings` bundle, inspect its recorded workflow without
printing the embedded reports:

```bash
python - <<'PY'
import json
from pathlib import Path
path = Path("results/wings_report_bundle.wings")
with path.open(encoding="utf-8") as handle:
    bundle = json.load(handle)
print("Generated:", bundle.get("generated_at"))
print("Samples:", bundle.get("sample_count"))
print(json.dumps(bundle.get("provenance", {}).get("data", {}).get("workflow", {}), indent=2))
PY
```

On Linux use `sha256sum results/wings_report_bundle.wings`; on macOS use
`shasum -a 256 /path/to/downloaded.wings`. Equal hashes establish byte identity,
not that the generating code or analysis configuration was appropriate.

### Rebuild a run report and bundle from existing dependencies

Use the completed run's working directory and saved execution configuration.
The following example assumes a direct CLI run using `config.yaml` and the
default `results/` directory. For a browser-created run, substitute its saved
execution configuration and result paths. First preview the restricted rebuild:

```bash
snakemake results/wings_report_bundle.wings \
  --configfile config.yaml --sdm conda --cores 1 \
  --allowed-rules run_summary_html wings_report_bundle \
  --forcerun run_summary_html wings_report_bundle --dry-run
```

If the plan contains only the intended report and bundle jobs and their existing
inputs are appropriate, repeat without `--dry-run`. This rebuilds the run report
and bundle; it does not refresh existing sample reports, scientific inference,
or upstream Explorer JSON. Missing dependencies require their own reviewed plan.
Do not remove the rule restriction just to bypass an unexplained dependency error.

A viewer asset update may require a dedicated refresh procedure; an upstream
evidence update may require rebuilding its dependent reports. Consult the
specific feature guide. Avoid `--forceall` for a presentation-only change.

## Phylodynamics report maintenance

Phylodynamics reports must match the analyzed study samples, method, reference
selection, and accepted diagnostic results. Refreshing a viewer must not create
missing posterior data, change fitted location assignments, or bypass diagnostic
gates. Preserve the original result and configuration.

The repository provides the isolated
[Snakefile.phylogeography-report](../Snakefile.phylogeography-report) route for
rendering existing saved results. Review and adapt
[config/phylogeography-results.example.yaml](../config/phylogeography-results.example.yaml)
to the actual completed run before using it. Do not use example/synthetic inputs
as a substitute for missing real-run results.

See [saved-result rendering](phylogeography-results.md),
[primary-result presentation](phylogeography-primary-result.md),
[posterior-summary presentation](phylogeography-summary-view.md),
[Bayesian dating](bayesian-dating.md), and
[posterior geographic reconstruction](posterior-phylogeography.md).
These guides distinguish inference changes from display changes. A Fast/BEAST
button in a completed report selects available results; it does not run inference.

## Optional local public-health briefing

The Knowledge for action panel is a run-level interpretation of recorded
evidence. Enable it only with the intended Ollama endpoint and installed model.
On the desktop, use the app's Ollama settings; on a cluster, provision the service
in the compute environment and use a reachable endpoint. Host and container
loopback addresses are not interchangeable.

Use [local model interpretation](local-llm-interpretation.md) for configuration,
generation, evidence rebuilding, and presentation-only refresh options. A model
listed by the service does not establish enough memory or a successful generation.
The saved JSON includes diagnostic/evidence information; inspect it when a panel
is unavailable. Generated statements still require scientific review.

Decide whether you intend to regenerate the narrative using new evidence, or
only rerender an existing narrative. A presentation-only operation must not be
represented as a new evidence analysis. Rebuild the affected report and bundle
after the intended JSON update, using the original run configuration.

## eBird Status & Trends phenology: access key required for downloads

Status & Trends modeled relative abundance is separate from EBD checklist
reporting. Uncached raster downloads require the user's Status & Trends access
key; a general eBird API token is not sufficient. Cached rasters can be reused.
Use the [Status & Trends download page](https://science.ebird.org/status-and-trends/download-data)
and [phenology guide](ebirdst-phenology.md) for product and configuration details.

In native mode, set `EBIRDST_ACCESS_KEY` in the environment that launches WINGS.
A shell variable set elsewhere does not update an already-running native server.
In desktop mode, use the corresponding Settings action. Do not put the key into
shared configurations, logs, screenshots, or reports.

An unavailable phenology result can be a completed workflow output. After
restoring access, an ordinary resume may therefore reuse it. With the affected
run stopped, use its original saved configuration and first preview a targeted
rebuild with `--forcerun ebirdst_phenology --dry-run`, targeting the desired run
report or bundle. Inspect the planned downstream jobs before executing. Preserve
the raster cache and unrelated outputs. Do not use a bare repository config when
the result came from a separate browser-run execution configuration.

Check `results/run_summary/phenology/phenology.log` and
`results/run_summary/phenology/wings_phenology.json` for sample statuses and
download provenance. Missing abundance is unavailable, not zero abundance.

## Optional eBird reporting context

EBD reporting frequency uses observations plus matching sampling-event data,
with complete checklists as its denominator. It is not modeled abundance or
infection prevalence. Match release, geography, dates, and host mappings before
comparing samples. Shared checklist context must not be summed repeatedly for
samples with the same context window.

See [eBird reporting context](ebird_portal_context.md),
[portable eBird packages](ebird-context-packages.md), and
[ecological context](ecological-context.md). Keep large source files and raw
records outside Git and report bundles. Preserve terms, citations, scopes, and
provenance when building reusable caches; missing denominators must remain
explicit rather than being filled with zero.

## Other reference and context panels

| Panel or source | Guide | Interpretation boundary |
| --- | --- | --- |
| Public genotype comparison | [Genotype frequencies](genotype-frequencies.md) | WINGS samples and public SRA runs have different denominators; neither is population prevalence. |
| Amino-acid evidence | [Amino-acid views](amino-acids.md) | Retain reference accession and coordinate conventions; missing coverage is not a reference call. |
| APHIS detections | [Outbreak context](outbreak-context.md) | Space/time overlap does not establish transmission or genomic linkage. |
| Joint evidence displays | [Genomic/ecological concordance](genomic-ecological-concordance.md) | Inspect eligibility, missingness, model scope, and diagnostics before interpreting a comparison. |
| Context preparation | [Context setup](context-setup.md) | Use metadata-matched scopes and record source versions rather than silently substituting unrelated data. |

Keep configured reference databases and their manifests with the run provenance.
A reference update changes analytical inputs; it is not merely a cosmetic report
refresh. Use [command-line setup](command-line-guide.md#install-references-and-vadr-models)
for BLAST and VADR resources.
