# Combined evidence interpretation, version 1

The Overview tab now presents a deterministic **Knowledge for action** brief. It leads with the most important conclusion, explains what the genomes show, identifies the leading explanation supported by the eligible comparisons, relates that interpretation to reported detections, and recommends the next public-health step. It uses existing concordance model results; it does not fit new models or use an LLM. It is unchanged by sample selection, display filters, or subsequently imported phenology. Rebuild the report to interpret changed analytical inputs.

The brief appears above the sample and host controls so it frames the run before users explore individual results. Technical results and diagnostics remain in their corresponding report tabs. The deterministic synthesis object retains its rule IDs, thresholds, supporting model rows and original row indices, readiness, sample QC counts, and detection snapshot identity for programmatic inspection. The report retains its embedded source payload.

## Rules

- Segment completeness is descriptive: counts of eight passing segments, fewer than eight, and unknown/invalid counts are separate. Review flags remain visible in the evidence record. This is not a relatedness test.
- A model row must have READY status (and no conflicting display status), a recognized unique segment, a valid integer sample count meeting the configured minimum (default eight), numeric q in [0,1], and numeric added fit in [0,1]. Migration additionally requires the configured minimum number of documented distinct migration settings. Eight is an eligibility guardrail, not a power calculation.
- Positive added fit with FDR q < 0.05 is labeled an exploratory association. Eligible tests outside this criterion are inconclusive, never proof of no association. Withheld rows preserve their status and reason; missing analyses are unavailable.
- Host, seasonal ecology, weather and migration remain distinct comparison families. Weather and migration are separately adjusted comparisons, not a joint model. No overall risk score or independent-vote count is computed.
- APHIS rows are descriptive US wild-bird detections, not unique outbreaks, prevalence or incidence. Version 1 does not link these records to samples by place/date or infer transmission.

The headline summarizes supported comparison families and explicitly states the missing integration with detections. This first version cannot establish the full epidemiological story; it makes that boundary inspectable. It does not infer causation, infection source, reassortment, individual bird movements or a climate effect.

## Validation and remaining work

Run `node --test tests/test_evidence_synthesis.cjs` and `node --check scripts/report/surveillance-explorer.js`.

Tests cover missing and malformed inputs, insufficient sample sizes, q thresholds, duplicate segments, migration settings, mixed results, foreign sample context, reproducibility, and safe DOM rendering/navigation. Browser appearance and a freshly rendered real report still require review. This is a proposed interpretation layer, not yet validated against expert adjudication or user comprehension. Before manuscript claims, use independently reviewed expected conclusions, including incomplete and contradictory evidence scenarios.

Future place/time matching should preserve source scope, both detection and collection dates, geographic uncertainty, source provenance and missingness. Merely overlapping records must not become causal or transmission claims.
