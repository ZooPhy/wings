# Local public-health interpretation

WINGS can translate its structured genomic, ecological, migration, weather and detection evidence into a concise public-health interpretation using a locally installed Ollama model. This feature is optional and disabled by default. It sends no FASTQ reads, consensus sequences or phylogenetic trees to the model. The evidence dossier contains selected sample metadata and QC, aggregate detection context, analysis readiness and segment-level model results.

## Privacy and model use

The default endpoint is `http://127.0.0.1:11434/api/chat`. Local Ollama inference keeps prompts and responses on the user's computer; inference does not train or fine-tune the model. WINGS calls only the chat and model-information endpoints. It does not create or train models, submit feedback, or use Ollama cloud. Nonlocal endpoints are refused unless `allow_remote: true` is explicitly configured. `host.docker.internal` is treated as local so a containerized WINGS process can reach Ollama on its host.

Ollama and model weights are external dependencies and are not distributed with WINGS. Ollama is MIT-licensed. The recommended `gpt-oss:20b` model is Apache-2.0 licensed. A user selecting another model must review that model's license and terms. WINGS records the model tag, a digest of the locally served model definition, prompt version, prompt hash and evidence hash in the generated artifact.

## Configuration

Install Ollama separately and install the chosen model:

```bash
ollama pull gpt-oss:20b
ollama list
```

Enable the feature in `config.yaml`:

```yaml
public_health_interpretation:
  enabled: true
  provider: ollama
  model: "gpt-oss:20b"
  url: "http://127.0.0.1:11434/api/chat"
  timeout_seconds: 180
  allow_remote: false
```

WINGS never downloads a model automatically. If Ollama is unavailable, the model is missing, output is malformed, citations are invalid, or source-rendered observations are changed or the narrative introduces a prohibited causal claim, the HTML report still builds with the deterministic interpretation.

## Container deployment

Ollama may run in a separate container with a persistent `/root/.ollama` volume. Linux NVIDIA hosts can provide GPUs to that container. Native Ollama is recommended on Apple-silicon Macs because Docker Desktop's Linux VM does not provide the container direct Metal acceleration. If WINGS is containerized while Ollama runs on the Mac host, configure `http://host.docker.internal:11434/api/chat`.

## Interpretation contract

### Simplified panel and explicit sample counts (1.6.2)

The agency brief now ends after its implications and sample-count note; the **Evidence and analysis details** disclosure has been removed. Detailed observations and provenance remain in the saved and embedded interpretation JSON. Different sample counts are written as alternatives, not a numeric range or an average. For example: “Of the 30 samples, 10 were used in most completed comparisons; some comparisons used 9.” Counts come from the completed comparisons, without pooling their sample counts into a new total.

Refresh the saved presentation with `--validate-saved` and rebuild only the HTML, using the commands below. No new model request or upstream analysis is needed.

### Plain-language surveillance brief (1.6.1)

The default view is written for wildlife-health staff interpreting surveillance results. It contains a short headline, up to three practical implications, and one sample-count note. Technical findings, segment names, fit statistics, eligibility explanations, optional QC follow-ups and model provenance are retained under a native **Evidence and analysis details** disclosure, closed by default and operable by keyboard.

For supported host and seasonal-ecology comparisons, the brief explains why changing the mix of sampled bird species could change the genetic picture, and suggests checking whether the seasonal relationship appears again in later surveillance rounds. These are suggestions for reviewing surveillance evidence, not findings that the sampling mix actually changed or that a seasonal association has already been replicated. They do not identify a high-risk species, month or location. When weather and migration comparisons lack support, the brief says that this run has not identified a weather or migration priority; the detailed evidence preserves the distinction between unavailable and nonsignificant results.

This is a presentation update. Statistical thresholds, comparison results, evidence requirements and model selection IDs are unchanged. The visible sample-count note is source-rendered and checked with the rest of the narrative. The saved JSON still contains all four comparison families and their supporting evidence.

After installing this update over 1.6.0, refresh the existing saved selection without calling Ollama:

```bash
python scripts/generate_public_health_interpretation.py \
  --evidence-json results/run_summary/public_health_interpretation.json \
  --host-map resources/ebird_host_codes_2025.tsv \
  --output results/run_summary/public_health_interpretation.json \
  --validate-saved --print-narrative
```

Then use the HTML-only rebuild below. Revalidation preserves the original model response and generation history and records the refreshed presentation separately.

### Analysis results take priority (1.6.0)

When the dossier includes WINGS v3 dyadic concordance results and their method metadata, the summary now leads with those comparisons. Previously, mixed-host tree membership activated a narrower selection contract that could displace the completed models. An older dossier also cannot recover models that were never included in it.

The report preserves four comparison families: host identity, seasonal bird abundance, weather, and migration. Each observed-findings card has 2–3 source-rendered bullets. Public Health Implications explains the reported associations first, followed by what remains unresolved. The local model chooses an available headline and presentation order; it does not estimate effects, write new scientific claims, or invent interventions.

Association wording requires a completed comparison, the expected nested predictors, consistent finite fit statistics, valid permutation results, the minimum sample count, positive ΔR² and FDR-adjusted q < 0.05. This is a reporting threshold, consistent with the deterministic panel. Migration additionally requires the recorded minimum number of distinct contexts. Duplicate segment/comparison rows cannot support an association. Completed nonsignificant results, unestimable comparisons and missing results remain distinct. All four families must appear, so a model cannot select only favorable results.

Counts refer to samples per comparison, not the whole run or independent sample pairs. Fit increments are shown in R² percentage points. The text does not infer the direction of a host coefficient from an increase in fit. Seasonal bird abundance, collection-window weather and matched migration nights retain their separate meanings. These exploratory models describe genetic-distance associations; they do not estimate evolutionary rates, establish adaptation, reconstruct transmission routes, or demonstrate robustness to sampling imbalance.

The evidence now retains the supplied method descriptions, reduced/full predictor definitions and fit status, permutation counts, and migration eligibility details. These values are saved with the report and checked against its rendering. Existing tree-membership summaries remain available when this analysis contract is absent.

To bring completed analyses into the interpretation **without rerunning them**, generate from the existing explorer and concordance files:

```bash
python scripts/generate_public_health_interpretation.py \
  --explorer-json results/run_summary/surveillance_explorer.concordance.json \
  --concordance-json results/run_summary/concordance/concordance.json \
  --host-map resources/ebird_host_codes_2025.tsv \
  --output results/run_summary/public_health_interpretation.json \
  --enabled true --provider ollama --model gpt-oss:20b \
  --url http://127.0.0.1:11434/api/chat \
  --timeout 180 --max-output-tokens 2048 --fail-on-error --print-narrative
```

Use the actual results directory for the run. Do not use `--repair-saved` or `--evidence-json` for this first refresh: they reuse the old dossier and cannot add missing analyses. After generation, rebuild only the HTML:

```bash
snakemake results/run_summary/run_summary.html \
  --cores 1 --use-conda \
  --allowed-rules run_summary_html --forcerun run_summary_html
```

Before invoking the model, WINGS calculates supported within-run tree groups and describes their host, location and collection-period composition. It adds sample-level weather and migration summaries when available, including weather changes from the preceding seven days (days -10 to -4) to the collection-centered window (days -3 to +3) and the count of samples at or above the 75th percentile of nightly migration activity. It identifies purely contextual APHIS overlaps in the same state and within 14 days, and records sampling concentration and missingness. A supported tree group requires an internal-node support value of at least 0.70; WINGS does not manufacture clusters from an arbitrary genetic-distance cutoff. The layer does not claim robustness to imbalance unless a sensitivity analysis was actually performed.

With prompt version 1.5.0, dossiers containing supported mixed-host segment groups use a structured relationship-selection contract. Ollama chooses an available takeaway and up to four supported relationship statements. WINGS renders their factual sentences from individual group memberships and collection dates. The model decides emphasis and selection; it does not write unrestricted scientific prose into this report section. This is a deliberate change from the earlier prose-and-keyword-check approach. Dossiers without these groups retain the earlier observation-selection and draft-prose contract.

Observation counts, dates and host labels are source-rendered: a tree-group observation uses that group's distinct member sample IDs, while a whole-run observation is explicitly labeled as such. A whole-run total cannot be substituted into a group statement. QC and subtype predictions are not rendered as diagnostic positives. Host-label comparisons normalize Unicode hyphens and whitespace, including titles.

The model can select 0–3 optional follow-ups from an evidence-gated catalog of QC or metadata review tasks. Empty recommendations are valid and the HTML omits that section. The model cannot invent new sampling locations, seasons, hosts or interventions. These checks deliberately narrow the output contract; they are not an automated surveillance-planning system.

The report separates Public Health Implications, observed findings and optional follow-up. All interpretation citations must come from the selected evidence. In relationship-selection mode, the headline, observations and review implications must exactly match the current source-rendered presentation; changes to group membership or dates invalidate the earlier rendering. In the legacy prose path, numerical and scientific correctness still require review: a number occurring somewhere in a cited source does not establish that its use in a sentence is correct. Neither path establishes new biological findings or validates upstream phylogenies. Selection quality and public-health significance remain subject to review, recorded as `validation.review_status: UNREVIEWED`.

A rejected response receives one local repair attempt; if that also fails, no model narrative is accepted. Both raw responses and their errors are retained under `diagnostics.attempts` for local inspection, not displayed as findings. Output status is printed, and `--fail-on-error` returns a nonzero exit status for direct CLI use. Default workflow behavior still allows the deterministic report fallback. The accepted narrative is embedded in the portable report; opening a shared report does not invoke the model again.

Version 1.3.1 distinguishes explicit limitations such as "limit the ability to draw robust conclusions" from claims of demonstrated robustness. Common completeness statements such as "most samples had complete genomic data" are checked against the whole-run QC denominator when the selected scope is unambiguous. These wording checks do not validate every possible paraphrase.

Repairs with a synthesis plan send its required cards, retained optional cards, follow-ups and the host glossary. Other repairs send the selected observations and their source facts, the follow-up catalog and its source facts, the host glossary and sampling balance. They omit unrelated evidence and the rejected prose; the complete dossier remains in the saved JSON. If the initial response has no valid observation selections and no synthesis plan, repair instead offers the observation catalog for selection. The request phase, size and completion time are printed. Completed attempts record the actual prompt, generation settings and Ollama timings; a repair timeout preserves the completed initial attempt.

Generation defaults to 2,048 tokens, including model thinking where applicable. For `gpt-oss`, WINGS requests `think: low`. Direct CLI calls can change the cap with `--max-output-tokens`; a response stopped at the cap is rejected rather than accepted as a partial narrative. `--timeout` controls the HTTP socket timeout, not a guaranteed total wall-clock deadline.

Version 1.3.2 asks the model to cite the selected `OBS-` observation IDs in `public_health_meaning.evidence_ids`. WINGS resolves those IDs to their underlying source facts before validation and rendering. Unknown or unselected observations are not resolved. Older responses citing valid source fact IDs remain readable. The model's original response and its observation citations stay unchanged in `diagnostics.attempts`; the accepted narrative contains the resolved source fact IDs.

Generation now sends an explicit [Ollama JSON schema](https://docs.ollama.com/capabilities/structured-outputs) in the API's `format` field. It defines the response fields and restricts selection and citation IDs to the available observation catalog. For a repair, it restricts them to the repaired selection: required contextual observations first, then existing selections up to the four-card limit. Local validation checks that this selection is retained. The actual schema is recorded with each completed attempt's prompt. A schema controls structure and allowed IDs, not whether prose is scientifically supported or useful.

## Public Health Implications and concise findings

Presentation version `public-health-implications-v1` places **Public Health Implications** first. For relationship selections it renders 2–3 suggested surveillance-review steps from the selected claims: review records across their observed host combinations, organize comparisons by collection timing, and reconcile public-detection context with individual records. Timing suggestions use the selected groups' own dates. Detection suggestions distinguish all, some, or no eligible samples matching; absent detection context produces no detection-specific suggestion.

These are WINGS-defined editorial review suggestions, not model-generated discoveries, automated risk rankings, or validated intervention recommendations. Each item stores its triggering claim IDs and evidence IDs in `public_health_meaning.items`. They remain separate from the model's optional `recommended_actions`. The general emphasis on integrating genomic findings with epidemiological records follows the [WHO Global genomic surveillance strategy, 2022–2032](https://www.who.int/initiatives/genomic-surveillance-strategy); the wording and trigger rules are WINGS implementation choices, not WHO-endorsed recommendations for an individual run.

Host-group, collection-timing, public-detection and run-QC cards have 2–3 source-rendered bullets. Distinct host combinations remain separate, repeated segment memberships are identified, and dates remain specific to each host. The full observation text, scope and evidence IDs stay in the saved JSON. Other observation types retain their existing text rendering.

Refresh an existing native relationship selection offline, then rebuild only the HTML:

```bash
python scripts/generate_public_health_interpretation.py \
  --evidence-json results/run_summary/public_health_interpretation.json \
  --host-map resources/ebird_host_codes_2025.tsv \
  --output results/run_summary/public_health_interpretation.json \
  --validate-saved --print-narrative &&
snakemake results/run_summary/run_summary.html \
  --cores 1 --use-conda \
  --allowed-rules run_summary_html --forcerun run_summary_html
```

This preserves the model selection, prompt, generation version, attempt history and source facts. It refreshes the rendered narrative and observations, recording the presentation version and prior narrative hash in the validation review. No Ollama request is made. Older prose responses still require the existing migration to relationship selection. The model prompt version stays at 1.5.0 because the selection contract has not changed.

## Source-checked relationship selection (1.5.0)

Each available group statement records the specific group ID, segment, distinct member sample IDs, authoritative hosts, and dates by sample. Dates are classified within that group as `same_date`, `multiple_dates`, or `incomplete_dates`; a whole-run date range cannot substitute for group dates. Missing member records prevent generation. Missing dates are described as incomplete and cannot support a headline claiming shared or differing dates. Reused samples remain separate memberships in different segment groups, not independent observations.

The model returns only `takeaway_id`, `claim_ids`, and optional source-defined follow-up IDs. The schema contains no free-text headline or interpretation field. Selected claims must include at least one mixed-host group and the public-detection context when available. A headline about groups occurring both within and across dates requires selected groups demonstrating both patterns. QC is optional supporting detail. The public-detection statement is calculated from matched and eligible sample counts; a uniform binary overlap is described as shared context, never as identified case linkage.

WINGS retains one source-rendered sentence per selected group and the selected contextual statements in `narrative.grounding.claims`. The `narrative.grounding` object preserves the model's selection, a catalog hash, the exact statements, source evidence IDs and each statement's scope. The current display uses these claims to produce the review implications described above. Validation regenerates the expected narrative from the evidence and compares the entire result. A model cannot substitute an unsupported comparison such as "clusters by segment rather than by host" because it is neither an available takeaway nor a supported statement. This prevents that output through a bounded claim contract; it is not a general semantic verifier of arbitrary natural language.

The existing HTML narrative fields remain compatible. `--repair-saved` migrates older prose responses to relationship selection for eligible dossiers, retaining the old attempts in diagnostics; it does not lock in earlier QC card choices. `--validate-saved` can recheck native relationship selections without contacting Ollama. An older free-prose response in a relationship dossier must be regenerated with `--repair-saved`, even if its older wording checks passed. Other dossiers retain the legacy prose path, explicitly recorded as `validation.mode: legacy_prose_checks`.

This update uses already saved relationships. It does not add migration or weather association results, rerun trees, or derive transmission, causation, host specificity or population-level risk from group composition.

## Context-first interpretation (1.4.0)

The observation catalog now includes the recorded weather-change and public-detection context of each selected segment-tree group. Additional source-rendered observations describe groups containing different hosts, host-specific collection dates, state/date detection overlap across the run, and which context actually reached the dossier. Group counts are not unique birds, independent weather observations or outbreaks. The host-group summary describes the existing selected segment-tree groups; it does not calculate new trees or infer whole-genome lineages.

Weather-change summaries obtained from ecological context are distinct from concordance environmental features. A zero count for the latter does not imply that all weather data are absent. Saved weather-change summaries are displayed as recorded; their daily coverage cannot be reconstructed from the summary alone. The catalog reports missing model rows as an input gap, not as a negative association result. When `--concordance-json` supplies a full analysis record, its `models` and `readiness` now take precedence over the embedded explorer values; earlier code used that file for sample features but ignored these two fields.

The initial prompt sends the source-rendered observation texts and glossary without duplicating every raw fact and source-row list. The complete facts and source references remain in the output JSON. It presents contextual relationships before QC and asks for the main takeaway from the combination. This ordering is not a statistical ranking of findings. The output schema constrains JSON fields and IDs only. The number-word regex from 1.3.3 has been removed because it encouraged malformed strings such as `thirtysamples`. Normal numerical prose is allowed; source-exact cards and draft narrative have different validation guarantees.

A fresh generation or `--repair-saved` can use the updated synthesis plan. Version 1.4.1 adds omitted required context to a saved selection before rewriting the narrative. Reusing a saved dossier cannot recover missing migration features or model results: those require the appropriate existing explorer/concordance inputs. This patch does not rerun upstream analyses or download context.

## Synthesis selection and host-specificity correction (1.4.1)

When the catalog contains a cross-host segment-group observation, WINGS creates an explicit synthesis plan containing that observation plus collection-timing and public-detection observations when available. The model must select and cite those observations and explain their contribution in the meaning paragraph. QC can occupy the remaining optional card. Without a cross-host grouping observation, selection remains open. This is a presentation rule, not a statistical importance ranking or a requirement to invent absent context.

The host-group card no longer leads with the fraction of mixed groups. Its full counts remain in the saved scope, but the text describes observed sample membership, the group-selection procedure, and reuse of samples across segments. Single-host membership does not establish biological host specificity. A targeted wording check rejects positive host-specificity claims, including Unicode-hyphen variants, while accepting explicit statements that specificity was not established. Citation and topic-coverage checks also catch the reported QC-only paragraph even if context IDs are added without corresponding discussion. These are regression checks, not a general verifier of scientific truth or prose quality.

Both automatic repair and `--repair-saved` add omitted synthesis-plan observations before preserving other selections, with a maximum of four cards. They do not recompute data or silently alter the saved model response. Earlier attempts remain in diagnostics; the current required IDs are recorded in `validation.required_observation_ids`. Repairs with a synthesis plan send a compact card catalog rather than all raw source facts. An optional `--print-narrative` prints the accepted headline, meaning and selected cards after generation; rejected drafts are not printed as accepted findings.

## Preserve individual group memberships (1.4.2)

The cross-host summary now includes each selected group's ID, segment, host names and recorded collection dates by host. The same membership rows are supplied as `group_memberships` in the compact model prompt. The glossary remains a naming reference; it is not evidence that every represented species occurs in the same group. Group rows are built from distinct member sample IDs and do not merge memberships across segments.

Public-detection wording describes external records overlapping sample state/date windows. It does not identify samples as those records or cases. Whole-run date differences also do not establish an individual group's timing or rule out sampling-event effects. The prompt states these scope distinctions and asks for ordinary sentence endings.

Validation now reports the matched term and field for the existing claim-language checks. Additional targeted checks catch the reported sample-to-record linkage, exclusion of a sampling-event explanation, a viral-host-range assertion, and JSON closing delimiters inside prose. Named-host assertions about the same/shared group are compared against the supplied memberships, with any explicitly named segment retained. Independent clauses can describe different groups. These checks address observed regressions; they do not establish full semantic correctness or replace review of the model's prose. The existing rejection of unsupported circulation language is retained.

## Refresh only the interpretation

### Precaution wording and separate host combinations (1.4.4)

The wording check now accepts the reported qualification ending "before drawing conclusions about viral circulation." It masks only that bounded phrase, leaving separate positive assertions available for checking. The earlier 1.4.3 change recognized explicit non-inferences but missed this precaution form.

The reported draft also combined different host pairings into a single list that "clustered together" across several segments. Named-host membership checks now recognize this wording and require support in each explicitly named segment, while permitting separate clauses for separate combinations. The prompt asks for each group's own dates, distinguishes groups sharing a date from groups spanning dates, and asks for the contextual takeaway in the headline rather than a QC tally. These remain targeted checks and instructions, not a general semantic validator.

Common unqualified completeness claims of "half" are checked as exact fractions against run-level QC when the selected scope is unambiguous. Explicitly approximate wording such as "about half" is not treated as exact. This addresses the reported headline for 14 of 30 samples without banning natural numerical prose or changing the source counts. QC terminology should describe segments passing QC rather than imply independent verification of genome completeness.

For the reported draft, use `--repair-saved` after applying this update: its host/segment wording and exact-half headline need rewriting even though its circulation qualification is allowed. Offline validation never rewrites a draft.

### Recheck an existing response without Ollama (1.4.3)

The claim check now recognizes explicit limits such as "these observations do not establish circulation" and "circulation cannot be inferred." It retains checks for positive assertions, claims of absence, and positive claims in another clause. These bounded wording rules do not understand every paraphrase or verify scientific entailment. The earlier incorrect all-hosts membership paragraph remains rejected.

Use `--validate-saved` to apply the current checks to the latest completed response already in the JSON. It makes no model or model-information request and does not rewrite its prose:

```bash
python scripts/generate_public_health_interpretation.py \
  --evidence-json results/run_summary/public_health_interpretation.json \
  --host-map resources/ebird_host_codes_2025.tsv \
  --output results/run_summary/public_health_interpretation.json \
  --validate-saved --print-narrative
```

On success it prints `REVALIDATED`, resolves the selected source cards, and saves the narrative with status `GENERATED` for report compatibility. It preserves the original model, prompt, prompt version, runtime and attempt history. A separate entry in `diagnostics.validation_reviews` records the response index and hash, validation version, evidence hashes and prior error. The validation timestamp is not a new generation timestamp; review status remains `UNREVIEWED`.

On failure it returns exit code 1, prints the errors and a clearly labeled rejected draft, and leaves both input and output files unchanged. It does not fall back to an earlier good response when the latest saved response is invalid. `--validate-saved` requires `--evidence-json` and cannot be combined with `--repair-saved`. No `--enabled`, model or endpoint arguments are needed. Normal generation with `--print-narrative` also prints a rejected saved draft when available, so another diagnostic command is unnecessary.

### Generate a new interpretation

If the saved dossier already contains all intended analyses, it can be reused without upstream work. If model results are missing, use the fresh-source command under **Analysis results take priority (1.6.0)** instead:

```bash
python scripts/generate_public_health_interpretation.py \
  --evidence-json results/run_summary/public_health_interpretation.json \
  --host-map resources/ebird_host_codes_2025.tsv \
  --output results/run_summary/public_health_interpretation.json \
  --enabled true --provider ollama --model gpt-oss:20b \
  --url http://127.0.0.1:11434/api/chat --timeout 180 --fail-on-error
```

This updates the presentation contract using existing facts; it does not refresh source data, add missing concordance evidence, or rerun analyses. The file is read completely before an atomic replacement. `--explorer-json` remains supported for normal workflow generation, including `--concordance-json` when configured. Use plain URLs, not Markdown links.

If an earlier response needs revision, add `--repair-saved`. For relationship dossiers this requests the new structured selection; for other dossiers it reuses the earlier observation selections with omitted synthesis-plan context added. This makes exactly one generation request using the compact repair prompt and preserves the earlier attempts. It requires a saved response in `diagnostics.attempts` and the same model tag recorded in the file:

```bash
python scripts/generate_public_health_interpretation.py \
  --evidence-json results/run_summary/public_health_interpretation.json \
  --host-map resources/ebird_host_codes_2025.tsv \
  --output results/run_summary/public_health_interpretation.json \
  --enabled true --provider ollama --model gpt-oss:20b \
  --url http://127.0.0.1:11434/api/chat \
  --repair-saved --timeout 180 --max-output-tokens 2048 --fail-on-error --print-narrative
```

After `GENERATED`, first dry-run the HTML-only rule:

```bash
snakemake results/run_summary/run_summary.html --cores 1 --dry-run \
  --allowed-rules run_summary_html --forcerun run_summary_html
```

Only proceed without `--dry-run` if exactly the HTML rule is scheduled and its inputs are available. Missing report inputs need to be located, not reconstructed by an unrestricted full-workflow command. Use the reporting environment configured for your installation.

## Staged agency briefing (v1.7.0)

The workflow now defaults to `mode: staged` when interpretation is enabled.
The standalone generator keeps `--mode legacy` as its default for compatibility;
pass `--mode staged` explicitly to generate the new briefing.

The local model receives the existing evidence facts, including successful,
non-significant and unavailable comparisons, eligibility, methods, host/date
metadata and contextual summaries. It does not receive raw FASTQ reads or added
sequence data. Optional context text and references are also sent to the chosen
endpoint. Existing local-endpoint restrictions still apply.

Three calls assess the evidence, write a brief, and review both against the
original evidence. An invalid initial assessment receives one repair attempt
before briefing. One later repair (of both drafts) and one further review are
allowed. Prompts aim below the hard word limits; length errors report the actual
word count. A run makes at most seven model calls, including one optional brevity edit.
Timeout and output-token limits apply separately to each call. A failed stage
keeps completed responses and prompts in diagnostics but does not publish a
narrative. The HTML shows that the staged briefing is unavailable instead of
substituting the older generic conclusions.

The displayed brief has a headline and three bullets: **What we learned**, **Why
it matters**, and **What this informs**. The model writes these in plain language;
it is no longer restricted to selecting canned implications. It should prioritize
a useful decision supported by the evidence rather than force a change in
surveillance priorities. Detailed sources stay in the interpretation JSON.

Programmatic checks enforce structure, length and valid citation IDs. The model
review checks claim support, numerical scope, alternative explanations and the
proportionality of a proposed decision. This is the same local model in a separate
call, not independent scientific validation. Citation existence does not prove
entailment; expert review remains necessary. The record retains human review
status `UNREVIEWED`. No new ecological analysis, historical baseline or risk model
is calculated by this module.

Configuration under `public_health_interpretation`:

```yaml
  mode: staged
  audience: wildlife  # wildlife, animal_health, public_health
  decision_question: "What can this collection tell our surveillance team?"
  # context_json: resources/briefing_context.json
```

Optional context file (supply actual reviewed information; omit unknown fields):

```json
{
  "collection_purpose": "Describe why and how these specimens were collected.",
  "additional_sources": [
    {
      "id": "CONTEXT-HISTORY",
      "kind": "historical_comparison",
      "text": "Insert an actual comparison, its population, period and limitations.",
      "reference": "Identify the reviewed report or source."
    }
  ]
}
```

Context is explicitly labeled user supplied and not independently verified.
References are recorded, not fetched. Do not include sensitive information that
should not be sent to the configured endpoint. Without supplied historical,
exposure or investigation comparisons the model must not invent them.

Example using current analyses, without rerunning the sequencing workflow:

```bash
python scripts/generate_public_health_interpretation.py \
  --explorer-json results/run_summary/surveillance_explorer.concordance.json \
  --concordance-json results/run_summary/concordance/concordance.json \
  --host-map resources/ebird_host_codes_2025.tsv \
  --output results/run_summary/public_health_interpretation.staged.json \
  --mode staged --audience wildlife \
  --enabled true --provider ollama --model 'gpt-oss:20b' \
  --url http://127.0.0.1:11434/api/chat \
  --max-output-tokens 2048 --timeout 180 --fail-on-error --print-narrative
```

Use `--brief-context-json PATH` and/or `--decision-question TEXT` when appropriate.
Saved evidence can be reused with `--evidence-json` instead of the explorer and
concordance inputs. Staged mode always creates a fresh assessment and review;
legacy `--repair-saved` and `--validate-saved` do not apply.

After a successful generation, copy the `.staged.json` file over
`public_health_interpretation.json` and rebuild only `run_summary_html` with
`--allowed-rules run_summary_html --forcerun run_summary_html --use-conda`.


### Brief length handling (v1.7.2)

The displayed briefing still targets at most 170 words across three bullets.
Length alone prevents acceptance only above 250 words. Briefings of 171–250
words proceed to the same source-based review; the saved validation record marks
`presentation.target_exceeded` and records the actual word count. This is an
editorial tolerance, not a relaxation of citation or evidence-review checks.


### Separate editing and evidence review (v1.7.3)

Supersedes the v1.7.2 briefing length gate: 170 words remains the writing target,
but brief length and headline length are editorial diagnostics, not evidence
validation errors. A structurally valid draft above the target receives one
shortening call before review. If that edit has invalid structure or citations,
the original draft is reviewed instead. A still-long draft can be accepted only
following the same evidence review; its word count and target overrun are saved.
The existing output-token limit still bounds each response.

The evidence packet now includes a comparison inventory taken from WINGS's
existing validated observation scopes. It preserves each family's supported,
tested and unavailable segments, per-comparison sample counts and source IDs.
It does not calculate new effects or generate recommended sampling locations.
Prompts and review instructions explicitly distinguish added model fit from
effect direction, host association from transmission or adaptation, and absence
of evidence for a surveillance change from evidence favoring current coverage.
They also require separate consideration of seasonal abundance, measured
migration and short-term weather. These instructions reduce known failure modes;
they do not guarantee that the same-model review will catch every false claim.

Regenerate using the existing staged-mode command. The old saved draft has not
passed review and is not made acceptable by this update. A fresh assessment and
briefing are generated and reviewed; no sequencing steps are rerun.


### Plain-language prompt (v1.7.4)

The system prompt now explicitly targets wildlife surveillance practitioners
without genetics or statistics training. Writing and editing prompts emphasize
three distinct jobs: state the finding, explain why it matters, and name the
supported use of the information. Each bullet targets one or two short sentences.

Displayed prose should omit segment-code lists, statistical notation, model-fit
percentages and methods jargon. Useful sample counts may remain when their scope
and denominator matter. Wording examples are explicitly conditional on supporting
evidence; they are not preset findings. The prompt requires the model to preserve
uncertainty and subset scope while simplifying the language. The underlying
sources, citation checks and evidence-review process are unchanged. These are
prompt instructions, not a guarantee that every model response will meet the
writing standard. Regenerate the briefing to apply them to the HTML report.


### Internal assessment length (v1.7.5)

The internal assessment now follows the same separation of editing and factual
validation as the displayed briefing. Its 250-word prompt target is not an
acceptance gate; the former 450-word cutoff is removed. Assessment word counts
are retained in diagnostics and final validation metadata. Output-token limits,
required fields, nonempty text, valid source citations and the review of both
assessment and briefing remain in effect. A long assessment proceeds to the
briefing writer and evidence review; it is not displayed directly in the HTML.
This supersedes earlier documentation describing a hard assessment word limit.


### Plain-language edit trigger (v1.7.6)

The editing step now also runs for statistical notation, segment codes and
specified methods terminology in the displayed headline or bullets, even when
the draft is short. It recognizes Unicode notation such as ΔR² and p‑values.
Counts such as “10 of 30 samples” remain allowed. Sources and citation IDs are
not rewritten. The editor rewrites meaning; code does not strip pieces of a
sentence. Remaining flagged prose enters the existing bounded repair step and
cannot be published as a successful briefing if still unresolved. Every accepted
edit still undergoes evidence review. This style check does not establish the
scientific validity of a claim or catch all possible jargon.


## Focused writing inputs (v1.8.0)

Assessment, writing, editing and repair now receive a compact factual packet.
All four available comparison families are represented, with separate completed,
associated, non-associated and unavailable counts, plus sample scope. The cards
are derived from WINGS's validated observation scopes. They contain no fit
statistics, p-values, coefficient interpretation or segment-code lists. Small QC,
sampling, host-label and coverage facts and explicitly supplied context remain
available. Cards summarize findings, not a finished interpretation or prescribed
sampling action. The model still writes original meaning and practical relevance.

The briefing writer no longer receives an unchecked model assessment. It writes
directly from the factual packet. This avoids carrying an unsupported assessment
claim into every later draft. The reviewer still sees both drafts, all original
source facts and the derivation links for every new BRIEF- citation. Same-model
review remains fallible; successful structural tests are not evidence of factual
accuracy in a live model response.

The record saves `writing_brief` separately from `evidence_brief`, and records each
attempt's evidence scope. The original `evidence` is retained. Writing packets
above 24 KB produce an explicit error rather than silently truncating context.
Small dossiers without comparison summaries can still be used; a large dossier
without those summaries must be rebuilt from current explorer/concordance inputs.

Run the existing staged generation command to apply this change. No existing
rejected draft is promoted, and no biological analysis is rerun. Inline source IDs
in displayed prose now trigger editing; citations belong in structured fields.


## Recorded subtype and genotype (v1.8.1)

The evidence builder now preserves per-sample HA/NA calls and the existing
`genotype` object (status, call, explanation and source). The writing packet adds
BRIEF-TYPING, summarizing potential subtype annotations, H5 screening status,
recorded genotype calls and the separate unassigned, indeterminate, failed or
missing states. Only a RECORDED status with a nonempty call counts as an assigned
genotype. Inconsistent status/call combinations are counted separately. Original
sample records remain available to the reviewer; no sequences are analyzed anew.

The prompt leads with recorded virus identity when present. Labels such as H5N1,
D1.1 and Minor114 remain exact and can appear in the plain-language briefing.
Genotype is introduced as a genetic group. Different labels are not automatically
new introductions, reassortment events, higher risk, or rare types. Historical
comparisons or clade results are not inferred. Potential subtype annotations are
not automatically confirmed diagnoses, especially when screening is indeterminate.

**For the first generation after this update, use --explorer-json and
--concordance-json instead of --evidence-json.** Older saved evidence omitted
these genotype fields and cannot recover them. This reloads existing report data;
it does not rerun sequencing or genotyping. Subsequent records retain the fields.


### Fixed review fields (v1.8.2)

The reviewer now returns an object with nine required named fields, rather than
an array of freely named sections. Each field requires a boolean support judgment
and an explanation; unknown fields are disallowed. This moves section coverage
into the structured-output schema. Local validation still checks all keys,
judgment types and negative findings. The same full evidence is reviewed; missing
reviews are not assumed to pass. Regenerate with the existing command to use the
new schema. Earlier saved reviewer lists are retained in old records but are not
promoted or silently converted into successful new reviews.


### Location in the briefing (v1.8.3)

Prompts now anchor the learned finding in recorded collection geography before
subtype/genotype details. Country/state coverage is read from the existing
SAMPLING-BALANCE location counts; coordinate completeness is used only when it
changes geographic interpretation. Collection periods are included only when
explicitly available to the writer, never inferred from filenames or seasons.

The instructions distinguish collection coverage from statewide prevalence,
infection locations, hotspots or migration routes. Genotype-by-location claims
require joint records, except that all samples sharing one state establishes that
state as the collection scope. Missing coordinates do not mean missing state
information. The brief should state a location limitation once, with its practical
consequence. This update changes prompts, not the underlying geographic analysis.
Use the existing generation-and-rebuild command to refresh the report.


### Citation display and repeated text (v1.8.4)

Pure parenthesized/bracketed groups of known writing-packet evidence IDs are
moved from bullet prose into `evidence_ids` before validation and review. Raw
responses remain in diagnostics, alongside a log of every normalized field.
Parentheses containing facts, unknown IDs or other prose are never stripped.
All registered source IDs are now checked, including SAMPLING-BALANCE and
GENOME-SUMMARY, rather than relying only on a list of prefixes.

A labeled briefing pasted inside a bullet (Headline/Learned/Meaning/Decision),
or a long paragraph repeated across fields, triggers editing and bounded repair.
Code does not extract a guessed decision or silently remove a substantive claim.
A narrow source-aware check also rejects wording that weather/migration do not
explain differences when their supplied comparison family has no completed
comparisons. This is not a complete semantic validator; full evidence review
remains required and can still miss unsupported claims.

Regenerate using the existing command, then rebuild HTML after success. This
patch does not revise an already-rendered report or retroactively approve it.


### Integrated public-detection, migration and weather context (v1.8.5)

The focused writer now receives BRIEF-CONTEXT, derived from existing detection,
coverage, readiness and method facts. It preserves the public detection source
name and status; the same-state date-window matching rule, eligible sample count
and overlap count; migration coverage and run-level context counts; and weather
coverage/window. Missing values remain missing, rather than becoming zero. The
full original sources remain available to the reviewer. No new external records
are fetched and no ecological analyses are rerun.

Writing and review prompts explicitly require the meaning bullet to integrate
public detections, migration and weather when this card is available. Seasonal
bird abundance remains distinct from measured migration. Coverage is not an
association; failed/unavailable comparisons remain unanswered questions rather
than negative findings. State/date overlap is not a link to a specific case.
USDA wild-bird detections are not relabeled as poultry or human cases. The prompts
also reject key-carrier or reservoir claims based only on host sample counts.

This is a richer factual input and a prompt change, not a guarantee of model
compliance. Scientific review remains necessary. Run the existing staged
command and HTML-only rebuild to refresh the report.
