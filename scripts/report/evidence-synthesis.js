(() => {
  "use strict";
  const VERSION = "1.0.0";
  const FAMILIES = [
    ["host_vs_baseline", "Host", "time and geographic distance"],
    ["ecology_vs_host", "Seasonal ecology", "host and baseline covariates"],
    ["environment_vs_ecology", "Local weather", "host, seasonal ecology and baseline covariates"],
    ["migration_vs_ecology", "Migration context", "host, seasonal ecology and baseline covariates"]
  ];
  const numeric = value => typeof value === "number" && Number.isFinite(value);
  const count = value => Number.isInteger(value) && value >= 0;
  const list = value => Array.isArray(value) ? value : [];
  const object = value => value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const segments = new Set(["HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS"]);

  function localInterpretation(explorer) {
    const id = explorer?.root?.dataset?.wseInterpretationId;
    const node = id ? document.getElementById(id) : null;
    if (!node) return null;
    try {
      const record = JSON.parse(node.textContent || "{}");
      if (record.generation_mode === "staged" && record.status !== "GENERATED") return {unavailable: true};
      const narrative = record.narrative;
      if (record.status !== "GENERATED" || record.schema_version !== "wings.public-health-interpretation.v1" ||
          !narrative || typeof narrative.headline !== "string" || !Array.isArray(narrative.what_we_know) ||
          !narrative.public_health_meaning || !Array.isArray(narrative.recommended_actions)) return null;
      return record;
    } catch (_) {
      return null;
    }
  }

  function summarize(input) {
    const payload = object(input);
    const samples = list(payload.samples).map(object);
    const data = object(payload.genomic_ecological_concordance);
    const readiness = object(data.readiness);
    const models = list(data.models).map(object);
    const minimum = count(readiness.minimum_unique_samples) && readiness.minimum_unique_samples > 0
      ? readiness.minimum_unique_samples : 8;
    const findings = [];
    const add = (id, status, title, text, tab, evidence) => findings.push({id, status, title, text, tab, evidence});
    const known = samples.filter(s => count(s.segments_pass) && s.segments_pass <= 8);
    const complete = known.filter(s => s.segments_pass === 8).length;
    add("genome-completeness", samples.length ? "descriptive" : "unavailable", "Genomic evidence",
      `${samples.length} samples; ${complete} have all eight segments passing QC; ${known.length - complete} have fewer than eight; ${samples.length - known.length} lack a valid segment QC count. Completeness alone does not establish relatedness.`, "genome",
      {pointer: "/samples", records: samples.map(s => ({sample_id:s.sample_id ?? null, segments_pass:s.segments_pass ?? null, review_flags:s.review_flags ?? null}))});

    let supported = 0;
    let tested = 0;
    const supportedFamilies = [];
    for (const [family, label, adjustment] of FAMILIES) {
      const rows = models.map((row, index) => ({row, index})).filter(item => item.row.comparison === family);
      const valid = [];
      const excluded = [];
      for (const {row, index} of rows) {
        const required = count(row.minimum_unique_samples) && row.minimum_unique_samples > 0 ? Math.max(minimum, row.minimum_unique_samples) : minimum;
        let reason = "";
        if (row.status !== "READY" || (row.display_status && row.display_status !== "READY")) reason = String(row.display_status || row.status || "Missing analysis status");
        else if (!segments.has(row.segment) || rows.filter(item => item.row.segment === row.segment).length !== 1) reason = "Invalid or duplicated segment comparison";
        else if (!count(row.n_samples) || row.n_samples < required) reason = `Fewer than ${required} valid unique samples`;
        else if (!numeric(row.fdr_q) || row.fdr_q < 0 || row.fdr_q > 1 || !numeric(row.delta_r2) || row.delta_r2 < 0 || row.delta_r2 > 1) reason = "Missing or invalid q value or added fit";
        else if (family === "migration_vs_ecology" && (!count(readiness.distinct_migration_contexts) || readiness.distinct_migration_contexts < required)) reason = `Fewer than ${required} documented independent migration settings`;
        if (reason) excluded.push({index, reason, record:row});
        else valid.push({index, record:row});
      }
      const hits = valid.filter(item => item.record.fdr_q < 0.05 && item.record.delta_r2 > 0);
      supported += hits.length;
      tested += valid.length;
      if (hits.length) supportedFamilies.push(label.toLowerCase());
      const status = hits.length ? "association" : valid.length ? "inconclusive" : "unavailable";
      const text = valid.length
        ? `${hits.length} of ${valid.length} eligible segment comparisons show an exploratory association with ${label.toLowerCase()} beyond ${adjustment} (FDR q < 0.05 and positive added fit)${hits.length ? `: ${hits.map(item => item.record.segment).join(", ")}` : ""}. ${valid.length - hits.length} do not meet that criterion; this does not establish absence of an association. ${excluded.length} comparisons withheld.`
        : `No eligible ${label.toLowerCase()} comparison is available. ${excluded.length} supplied comparisons withheld; this is not a negative finding.`;
      add(family, status, label, text, "concordance", {pointer:"/genomic_ecological_concordance", minimum_unique_samples:minimum, readiness, included:valid, excluded});
    }
    const outbreak = object(payload.outbreak_context);
    const records = list(outbreak.records);
    const available = outbreak.status === "READY" && records.length > 0;
    add("detection-context", available ? "descriptive" : "unavailable", "Reported detections",
      available ? `${records.length} APHIS source rows are available as US wild-bird detection context. These are not counts of unique outbreaks. This summary has not matched detections to the samples by place and date or established epidemiological links.`
        : "No usable APHIS detection snapshot is available. Missing detection context does not mean no detections occurred.", "outbreak",
      {pointer:"/outbreak_context", status:outbreak.status ?? null, source_name:outbreak.source_name ?? null, sha256:outbreak.sha256 ?? null, source_file:outbreak.source_file ?? null, record_count:records.length, date_ranges:outbreak.date_ranges ?? null});
    const completeShare = samples.length ? complete / samples.length : 0;
    const genomeKnowledge = !samples.length
      ? "No sample results are available to interpret."
      : complete === samples.length
        ? `All ${samples.length} samples produced complete eight-segment genomes, providing a strong genomic foundation for this run.`
        : complete
          ? `${complete} of ${samples.length} samples produced complete eight-segment genomes. Interpret comparisons with the remaining incomplete or unknown genomes in view of their QC evidence.`
          : `None of the ${samples.length} samples produced a documented complete eight-segment genome, so the run cannot yet support a strong run-level genomic interpretation.`;
    const explanationKnowledge = supported
      ? `Genomic differences align most clearly with ${supportedFamilies.join(", ")} in the eligible segment comparisons. This is the leading explanation supported by this run.`
      : tested
        ? "The tested host, seasonal, weather and migration factors do not provide a clear leading explanation for the genomic differences in this run."
        : "The run does not contain enough eligible comparisons to identify what best explains the genomic differences.";
    const detectionKnowledge = available
      ? "Reported US wild-bird detections provide background context, but this run has not yet connected them to these samples by place and time."
      : "Reported-detection context is not available in this run, so the genomic findings cannot yet be placed against known US wild-bird detections.";
    let action;
    if (!samples.length) action = "Add sample results before using this report for surveillance decisions.";
    else if (!tested) action = `Add enough comparable samples and complete host, collection date, location and environmental metadata to meet the ${minimum}-sample analysis threshold. Use the current genomes for sample-level review and descriptive surveillance in the meantime.`;
    else if (supported) action = `Prioritize review and follow-up sampling around contrasts in ${supportedFamilies.join(", ")}, focusing first on the implicated segments. Then check whether those samples overlap reported detections in place and time.`;
    else action = "Do not prioritize a host or ecological driver from this run alone. Broaden sampling across hosts, places, dates and environmental conditions, then repeat the comparison.";
    const headline = supported
      ? `The clearest signal in this run is that genomic variation tracks with ${supportedFamilies.join(", ")}.`
      : tested
        ? "This run does not identify a clear ecological driver of the observed genomic variation."
        : completeShare === 1 && samples.length
          ? "The run produced complete genomes, but there is not yet enough comparative evidence to explain their differences."
          : "The run does not yet contain enough complete, comparable evidence for a run-level surveillance conclusion.";
    return {schema_version:"wings.evidence-synthesis.v1", rules_version:VERSION, scope:"Whole embedded run; independent of interactive filters and subsequently imported context", threshold:{fdr_q_less_than:0.05, positive_delta_r2:true}, headline,
      limitations:[
        "Exploratory associations are not evidence of transmission, infection source, causation or reassortment.",
        "Weather measurements describe local conditions, not a demonstrated climate effect. Seasonal ecology profiles do not track individual birds.",
        "Migration and weather comparisons are assessed separately; this is not a joint causal model. Segments and contextual sources are not independent votes.",
        "APHIS coverage is US wild birds. Applicability to each sample's place and date requires review; absence from this source is not evidence of absence.",
        "Segment QC counts do not replace sample review flags or segment-specific diagnostics. Statistical eligibility is not a guarantee of adequate power."
      ], findings,
      knowledge:{genomes:genomeKnowledge, explanation:explanationKnowledge, detections:detectionKnowledge, action},
      next_questions:["Which samples and segments have sufficient QC and metadata for the comparison?", "Do contextual sources cover the samples' actual locations and collection dates?", "Do the reported associations remain under alternative sampling and model assumptions?"]};
  }

  function mount(explorer, panel) {
    const result = summarize(explorer.payload);
    const generated = localInterpretation(explorer);
    const brief = ["analysis_selection", "staged_briefing"].includes(generated?.narrative?.grounding?.mode);
    const make = (tag, text, className) => {
      const node = document.createElement(tag);
      if (text !== undefined) node.textContent = text;
      if (className) node.className = className;
      return node;
    };
    const appendBullets = (parent, bullets) => {
      const list = make("ul", undefined, "wse-evidence-bullets");
      for (const text of bullets) list.append(make("li", text));
      parent.append(list);
    };
    const box = make("section", undefined, "wse-evidence-synthesis");
    box.setAttribute("aria-label", "Knowledge for public health action");
    if (!generated || generated.unavailable) {
      box.setAttribute("aria-label", "Run snapshot");
      box.append(make("p", "RUN SNAPSHOT", "wse-evidence-kicker"), make("h2", "Recorded results at a glance"));
      const samples = Array.isArray(explorer.payload.samples) ? explorer.payload.samples : [];
      const hosts = new Set(samples.map(s => s.host).filter(Boolean));
      const dates = samples.map(s => s.collection_date).filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d || "")).sort();
      const detected = samples.filter(s => s.h5_status === "DETECTED").length;
      const indeterminate = samples.filter(s => s.h5_status === "INDETERMINATE").length;
      const complete = samples.filter(s => s.segments_pass === 8).length;
      const located = samples.filter(s => s.has_coordinates === true).length;
      appendBullets(box, [
        `${samples.length} samples across ${hosts.size} recorded host groups.`,
        dates.length ? `Collection dates: ${dates[0]} to ${dates[dates.length-1]}.` : "Collection dates not recorded.",
        `H5 screen: ${detected} detected; ${indeterminate} indeterminate; ${samples.filter(s => s.h5_status === "NOT_DETECTED").length} not detected.`,
        `${complete} samples have all eight segments passing QC.`,
        `${located} of ${samples.length} samples have coordinates.`
      ]);
      const actions = make("div");
      actions.style.cssText = "display:flex;gap:12px;flex-wrap:wrap;margin:16px 0";
      for (const [tab, label] of [["coverage", "Explore samples"], ["genome", "View genomes"], ["concordance", "Compare context"]]) {
        const button = make("button", label, "wse-ecology-clock-action");
        button.type = "button";
        button.addEventListener("click", () => explorer.root.querySelector(`[data-tab="${tab}"]`)?.click());
        actions.append(button);
      }
      box.append(actions, make("p", "No generated surveillance briefing is included in this report."));
      panel.append(box);
      return result;
    }
    const headline = generated ? generated.narrative.headline : result.headline;
    box.append(make("p", "KNOWLEDGE FOR ACTION", "wse-evidence-kicker"), make("h2", headline));
    if (generated) {
      const meaning=make("section",undefined,"wse-evidence-meaning");
      const implication=generated.narrative.public_health_meaning;
      meaning.append(make("h3","Public Health Implications"));
      if (Array.isArray(implication.items) && implication.items.length && implication.items.every(item => typeof item.title === "string" && typeof item.text === "string")) {
        const items=make("ul",undefined,"wse-evidence-bullets");
        for (const entry of implication.items) {
          const item=make("li");
          item.append(make("strong",entry.title + ": "),make("span",entry.text));
          items.append(item);
        }
        meaning.append(items);
      } else {
        meaning.append(make("p",implication.text));
      }
      if (typeof implication.note === "string" && implication.note.trim()) {
        meaning.append(make("p",implication.note,"wse-evidence-scope"));
      }
      box.append(meaning);
    }
    // The agency brief ends here. Detailed evidence remains in the embedded
    // interpretation record rather than an additional section in this panel.
    if (brief) {
      panel.append(box);
      return result;
    }
    if (generated) box.append(make("h3","Observed findings","wse-evidence-findings-title"));
    const story = make("div", undefined, "wse-evidence-story");
    const storyItems = generated
      ? generated.narrative.what_we_know
      : [{title:"What the genomes show",text:result.knowledge.genomes},{title:"What best explains the pattern",text:result.knowledge.explanation},{title:"How confirmed detections fit",text:result.knowledge.detections}];
    for (const entry of storyItems) {
      const item=make("section");
      item.append(make("h3",entry.title));
      if (Array.isArray(entry.bullets) && entry.bullets.length >= 2 && entry.bullets.length <= 3 && entry.bullets.every(text => typeof text === "string" && text.trim())) {
        appendBullets(item,entry.bullets);
      } else {
        item.append(make("p",entry.text));
      }
      story.append(item);
    }
    const action=make("section",undefined,"wse-evidence-action");
    if (generated) {
      const actions=make("ul");
      for (const item of generated.narrative.recommended_actions) actions.append(make("li",item.text));
      if (generated.narrative.recommended_actions.length) action.append(make("h3","Suggested follow-up"),actions);
    } else {
      action.append(make("h3","What public health can do next"),make("p",result.knowledge.action));
    }
    box.append(story);
    if (!generated || generated.narrative.recommended_actions.length) box.append(action);
    if (generated) {
      const origin = generated.narrative.grounding?.mode === "analysis_selection"
        ? "Local model selection; WINGS analysis summary"
        : generated.narrative.grounding?.presentation_version ? "Local model selection; WINGS review suggestions" : "Local draft";
      box.append(make("small", `${origin} · ${generated.model} · scientific review pending · evidence ${String(generated.evidence_sha256).slice(0,12)}…`));
    }
    panel.append(box);
    return result;
  }
  globalThis.WINGS_EVIDENCE_SYNTHESIS = {VERSION, summarize, mount};
})();
