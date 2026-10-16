# WINGS publication evaluation: Genome Biology Software route

Status: evaluation plan and evidence inventory, not completed validation.
Initial repository audit: `b7d227e2f4de14e006f45aa87fe9d09a791d123e` (2026-10-15).

## Scientific objective

Evaluate whether WINGS makes genomic surveillance results and their ecological
context more reproducible, inspectable, and usable for a defined research audience.
The intended contribution must be stated in terms that can be tested. Broad
utility is an empirical question; additional supported organisms or additional
visual panels alone do not establish it.

Genome Biology's Software guidance permits pipelines combining existing methods,
but asks for a clear advance over existing tools using the same datasets,
appropriate benchmarking, and utility on real data. Novel biological findings
are helpful but not required. These journal requirements are distinct from the
proposed study design below.

Source, checked 2026-10-15:
https://link.springer.com/journal/13059/submission-guidelines/software

## What already exists and what remains unproven

| Existing component | Evidence needed before a manuscript claim |
| --- | --- |
| Linked Explorer and Genome Braid/Clock | Independent task-based usability evaluation, missing-data interpretation checks, and a reproducible demonstration |
| Exploratory genomic-ecological concordance | Statistical review of dependence, exchangeability, estimability, multiplicity, and sampling assumptions; independent evaluation of the proposed claims |
| Replay and interpretation archives | Reproduction on a clean environment, with documented expected outputs, tolerances, and discrepancies |
| Source snapshots and provenance | Explicit input/version inventory and verification that the recorded artifacts can actually be retrieved and reused |
| Tests and synthetic integer benchmark | Regression tests support implementation checks; the integer benchmark does not validate WINGS's scientific accuracy or runtime |

The source includes statistical guardrails and explanatory text. Their presence
does not demonstrate calibrated inference, broad utility, or a state-of-the-art
advance. The report's exploratory status should remain visible until appropriate
evaluation is complete. Ecological co-occurrence does not establish transmission.

## Prioritized work packages

1. **Freeze a reproducible evaluation release.** Record the evaluated commit,
   source snapshots, dependency versions, configuration, platform, and commands.
   Resolve release/licensing decisions before public archival deposition. No
   repository-level LICENSE or CITATION.cff was found in the audited tree; the
   owner must choose a license consistent with dependencies and data terms.
2. **Define claims and comparisons before collecting headline results.** Choose
   alternatives from a documented literature/tool review. State which tasks and
   outputs are genuinely comparable, preserve the same input cohort, and record
   excluded or unsupported tasks. Declare all attempted runs, including failures.
   Choose endpoints and success criteria before inspecting comparative outcomes.
3. **Validate the original interpretation layer.** Have a statistical collaborator
   review the assumptions of the concordance analysis. Distinguish software
   correctness, statistical validity, and usefulness to a researcher. Preserve
   unavailable and non-estimable outcomes; do not convert them into negative results.
4. **Evaluate reporting and reproducibility with independent users.** Use fixed
   tasks such as finding source evidence, distinguishing missing data from zero,
   reproducing a saved view, and tracing a result to its configuration. Record
   task accuracy, time, help needed, and unsuccessful attempts. Counterbalance
   tool order and account for learning effects; predefine evaluation and consent
   requirements with the institution where applicable.
5. **Assemble the submission evidence.** Archive code and shareable evaluation
   artifacts, document access restrictions, and map every headline claim to an
   actual result. Prepare the presubmission enquiry after the results support a
   clear statement of the advance.

Independent biological samples, users, and repeated software runs answer different
questions. Do not count pairwise rows or repeat executions as additional biological
replicates. A separate dataset must be independent of development/tuning decisions
to support a generalization claim. Any future expansion in scope needs its own
validation and documentation.

## Measurements and comparisons

For performance claims, specify machine, operating system, workload, input hash,
software versions, configuration, cache conditions, repetitions, and measurement
boundaries. Report variability and failures, not only the fastest successful run.
Docker stats describes observed containers; it does not measure native Conda
processes or whole-host memory. Sampled peaks can miss between-sample spikes.
Scheduler memory requests are not measured consumption. Peak RSS values for
sequential stages should not be added and labeled a whole-workflow peak.

For reproducibility, separate byte-identical artifacts from scientifically
equivalent outputs. Predeclare permissible differences such as timestamps and
platform-specific formatting. Keep the original outputs and explain normalization;
do not silently discard differences to make a comparison pass.

For usability and interpretation claims, a feature matrix is descriptive evidence.
It cannot establish faster or more accurate task completion without a study.
Comparators and their versions remain to be selected; this document makes no
claim that existing tools lack any specific capability.

## Evidence inventory validator

`scripts/check_publication_evidence.py` is a Python standard-library utility.
It checks a manually assembled evidence inventory for required roles, full Git
commit format, file existence, nonempty files, unique identifiers/paths, and
SHA-256 integrity. It does not run or change WINGS analyses.

Copy `publication/evidence.template.json` to the root of an evaluation directory.
Replace the placeholders with the actual evaluated commit, artifact paths,
descriptions, and digests. The template intentionally fails validation until real
records are supplied. Five separate artifacts are required:

| Role | Required record |
| --- | --- |
| `comparison` | Comparative results with endpoints and attempted runs |
| `real_data` | Dataset identities, versions, checksums, and selection criteria |
| `reproduction` | Independent reproduction and discrepancy record |
| `environment` | Versions, snapshots, platform, settings, and measurement scope |
| `limitations` | Claims mapped to evidence and acknowledged limitations |

Use relative POSIX paths within the evaluation directory. Files and directories
outside it, including escaping symlinks, are rejected. Additional artifacts may
reuse a role but must have distinct IDs and paths. Sensitive data need not be
copied into the directory: an appropriate access/provenance record can be the
artifact. This validator does not determine whether that record is adequate.

```bash
python scripts/check_publication_evidence.py /path/to/evaluation/evidence.json
```

The root defaults to the manifest's parent. `--root /path/to/evaluation` overrides
it. The command prints JSON to stdout and exits 0 for a complete, internally
consistent inventory or 1 on failure. Redirect stdout to a new filename if a saved
record is needed; shell redirection can overwrite existing files.

**PASS means inventory completeness and file integrity only.** The validator does
not verify that the commit exists, link artifact generation to that commit, inspect
artifact contents for study quality, verify data permissions, establish benchmark
fairness, or certify submission readiness. A reviewer must assess these separately.
SHA-256 checks preserve bytes; they do not establish correctness or authenticity.

Run the focused tests with:

```bash
python -m unittest discover -s tests -p test_publication_evidence.py -v
```

## Manuscript evidence map

| Proposed display | Purpose | Current status |
| --- | --- | --- |
| Figure 1: architecture and evidence flow | Explain inputs, original components, provenance, and interpretation | To prepare against frozen release |
| Figure 2: comparative evaluation | Support the specific advance claimed | Study not completed |
| Figure 3: real-data use case | Demonstrate utility and limitations | Dataset and endpoints to select |
| Figure 4: reproducibility/usability | Support independent use and replay claims | Study not completed |
| Supplement: versions, commands, datasets, failures | Enable inspection and reproduction | Inventory scaffold supplied |

No performance numbers or scientific results are supplied by this scaffold.
