(() => {
  "use strict";

  const VERSION = "0.3.1";
  const SEGMENTS = ["HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS"];
  const FAMILIES = [
    ["host_vs_baseline", "Host effect"],
    ["ecology_vs_host", "Seasonal ecology effect"],
    ["environment_vs_ecology", "Weather effect"],
  ];

  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const finite = value => typeof value === "number" && Number.isFinite(value);
  const signed = value => finite(value) ? `${value >= 0 ? "+" : ""}${value.toFixed(3)}` : "—";
  const qfmt = value => {
    if (!finite(value)) return "—";
    if (value < 0.001) return "<0.001";
    if (value < 0.01) return value.toFixed(4);
    return value.toFixed(3);
  };

  function friendlyStatus(model) {
    const code = model?.display_status || model?.status || "NOT_ESTIMABLE";
    return ({
      READY: "Ready",
      INSUFFICIENT_UNIQUE_SAMPLES: "Too few unique samples",
      INSUFFICIENT_INDEPENDENT_VARIATION: "Not independently estimable",
      INSUFFICIENT_PREDICTOR_VARIATION: "Insufficient predictor variation",
      INSUFFICIENT_COMPLETE_PAIRS: "Too few complete pairs",
      CONSTANT_GENETIC_DISTANCE: "No genetic-distance variation",
      NOT_ESTIMABLE: "Not estimable",
    })[code] || (String(code).includes("RANK_DEFICIENT") ? "Not independently estimable" : "Not estimable");
  }

  function plainDiagnostic(model, comparison) {
    const code = model?.display_status || model?.status || "";
    if (code === "INSUFFICIENT_UNIQUE_SAMPLES" || String(code).includes("INSUFFICIENT_SAMPLES")) {
      return `${model.n_samples || 0} unique samples are available; at least ${model.minimum_unique_samples || 8} are required.`;
    }
    if (code === "INSUFFICIENT_INDEPENDENT_VARIATION" || String(code).includes("RANK_DEFICIENT")) {
      if (comparison === "environment_vs_ecology") {
        return "Environmental distance does not provide independent variation beyond the existing time, geography, host, and seasonal-ecology predictors in this dataset.";
      }
      return "The added predictor does not provide independent variation beyond the predictors already in the model.";
    }
    if (code === "INSUFFICIENT_PREDICTOR_VARIATION") {
      return "The added predictor does not vary enough across the available samples for this comparison.";
    }
    if (code === "INSUFFICIENT_COMPLETE_PAIRS") {
      return "Too few sample pairs have complete data for all predictors in this comparison.";
    }
    if (code === "CONSTANT_GENETIC_DISTANCE") {
      return "The available pairwise genetic distances do not vary enough to fit this comparison.";
    }
    return model?.diagnostic || "This comparison is not estimable for the available data.";
  }

  function modelCell(model, comparison) {
    const td = make("td", "wgec-result-cell");
    if (!model) {
      td.append(make("strong", "wgec-status", "Not available"));
      return td;
    }
    if ((model.display_status || model.status) === "READY") {
      td.append(make("strong", "wgec-delta", `ΔR² ${signed(model.delta_r2)}`));
      const line = make("span", "wgec-statline", `q ${qfmt(model.fdr_q)} · p ${qfmt(model.permutation_p)}`);
      const n = make("span", "wgec-n", `${model.n_samples} samples · ${model.n_pairs} pairs`);
      td.append(line, n);
      return td;
    }
    td.append(make("strong", "wgec-status", friendlyStatus(model)));
    td.append(make("span", "wgec-diagnostic", plainDiagnostic(model, comparison)));
    td.append(make("span", "wgec-n", `${model.n_samples || 0} samples · ${model.n_pairs || 0} pairs`));
    if (model.diagnostic) {
      const details = make("details", "wgec-technical");
      details.append(make("summary", "", "Technical detail"), make("span", "", model.diagnostic));
      td.append(details);
    }
    return td;
  }

  function comparisonSummary(models, comparison) {
    const rows = models.filter(row => row.comparison === comparison);
    const ready = rows.filter(row => (row.display_status || row.status) === "READY");
    const below = ready.filter(row => finite(row.fdr_q) && row.fdr_q < 0.05);
    return {ready: ready.length, below: below.length, total: rows.length};
  }

  function significantSegments(models, comparison) {
    return SEGMENTS.filter(segment => models.some(row => row.segment === segment && row.comparison === comparison &&
      (row.display_status || row.status) === "READY" && finite(row.fdr_q) && row.fdr_q < 0.05));
  }

  function joinSegments(items) {
    if (!items.length) return "none";
    if (items.length === 1) return items[0];
    if (items.length === 2) return `${items[0]} and ${items[1]}`;
    return `${items.slice(0, -1).join(", ")}, and ${items.at(-1)}`;
  }

  function plainLanguageTakeaway(host, ecology, environment) {
    const clauses = [];

    if (host.ready) {
      if (host.below === host.ready) {
        clauses.push("host identity was associated with genomic differences across all analyzable segments");
      } else if (host.below > 0) {
        clauses.push("host identity was associated with genomic differences in some analyzable segments");
      } else {
        clauses.push("host identity did not add information beyond time and geography");
      }
    } else {
      clauses.push("the contribution of host identity could not be evaluated");
    }

    if (ecology.ready) {
      if (ecology.below === ecology.ready) {
        clauses.push("seasonal ecology added information across all analyzable segments");
      } else if (ecology.below > 0) {
        clauses.push("seasonal ecology added information for some segments");
      } else {
        clauses.push("seasonal ecology did not add information beyond host identity");
      }
    } else {
      clauses.push("the contribution of seasonal ecology could not be evaluated");
    }

    if (environment.ready) {
      if (environment.below === environment.ready) {
        clauses.push("local weather added information across all analyzable segments");
      } else if (environment.below > 0) {
        clauses.push("local weather added information for some segments");
      } else {
        clauses.push("local weather did not add information beyond the other factors");
      }
    } else {
      clauses.push("the available data were insufficient to isolate an independent weather signal");
    }

    if (clauses.length === 1) {
      return `Overall, ${clauses[0]}.`;
    }

    if (clauses.length === 2) {
      return `Overall, ${clauses[0]}, and ${clauses[1]}.`;
    }

    return `Overall, ${clauses[0]}, ${clauses[1]}, and ${clauses[2]}.`;
  }

  function summaryBox(data, models) {
    const host = comparisonSummary(models, "host_vs_baseline");
    const ecology = comparisonSummary(models, "ecology_vs_host");
    const environment = comparisonSummary(models, "environment_vs_ecology");
    const hostSegments = significantSegments(models, "host_vs_baseline");
    const ecologySegments = significantSegments(models, "ecology_vs_host");
    const readiness = data.readiness || {};

    const box = make("section", "wgec-plain-summary");
    box.append(make("h4", "wgec-summary-title", "What this run suggests"));
    box.append(
      make(
        "p",
        "wgec-takeaway",
        plainLanguageTakeaway(host, ecology, environment)
      )
    );

    const finding = (label, text) => {
      const row = make("div", "wgec-summary-row");
      row.append(
        make("strong", "wgec-summary-label", label),
        make("span", "wgec-summary-text", text)
      );
      box.append(row);
    };

    if (host.ready) {
      if (host.below) {
        const segments = host.below === host.ready || !hostSegments.length
          ? ""
          : ` (${joinSegments(hostSegments)})`;
        finding(
          "Host identity",
          `Added explanatory value in ${host.below}/${host.ready} analyzable segments beyond time + geography${segments}.`
        );
      } else {
        finding(
          "Host identity",
          `No additional explanatory value in ${host.ready} analyzable segments beyond time + geography.`
        );
      }
    } else {
      finding("Host identity", "Not estimable in this run.");
    }

    if (ecology.ready) {
      if (ecology.below) {
        const segments = ecologySegments.length
          ? ` (${joinSegments(ecologySegments)})`
          : "";
        finding(
          "Seasonal ecology",
          `Added explanatory value in ${ecology.below}/${ecology.ready} analyzable segments beyond host${segments}.`
        );
      } else {
        finding(
          "Seasonal ecology",
          `No additional explanatory value in ${ecology.ready} analyzable segments after host was included.`
        );
      }
    } else {
      finding("Seasonal ecology", "Not estimable in this run.");
    }

    if (environment.ready) {
      const weatherSegments = significantSegments(models, "environment_vs_ecology");
      if (environment.below) {
        const segments = weatherSegments.length
          ? ` (${joinSegments(weatherSegments)})`
          : "";
        finding(
          "Local weather",
          `Added explanatory value in ${environment.below}/${environment.ready} analyzable segments beyond seasonal ecology${segments}.`
        );
      } else {
        finding(
          "Local weather",
          `No additional explanatory value in ${environment.ready} analyzable segments after seasonal ecology was included.`
        );
      }
    } else {
      const weatherSamples = readiness.samples_with_complete_environment_vector;
      const contexts = readiness.distinct_weather_contexts
        ?? readiness.distinct_environment_profiles;

      const detail = weatherSamples != null && contexts != null
        ? ` (${weatherSamples} samples; ${contexts} distinct weather settings).`
        : ".";

      finding(
        "Local weather",
        `Not independently estimable in this run${detail}`
      );
    }

    box.append(
      make(
        "p",
        "wgec-summary-caveat",
        "Exploratory associations only; not evidence of transmission, infection source, reassortment, or causation."
      )
    );

    return box;
  }

  function render(explorer, panel) {
    panel.innerHTML = "";
    panel.classList.add("wgec-panel");
    const data = explorer?.payload?.genomic_ecological_concordance;

    const head = make("header", "wgec-head");
    const titleWrap = make("div");
    titleWrap.append(
      make("div", "wgec-kicker", "Research module"),
      make("h3", "wgec-title", "Genomic–Ecological Concordance"),
      make("p", "wgec-intro", "Tests whether host, seasonal ecology, and local weather explain genomic distance beyond time and geography.")
    );
    head.append(titleWrap, make("span", "wgec-badge", "Exploratory"));
    panel.append(head);

    if (!data || !Array.isArray(data.models)) {
      const empty = make("div", "wgec-empty");
      empty.append(
        make("strong", "", "Concordance analysis is not available for this run."),
        make("p", "", "WINGS will populate this module automatically when segment phylogenies and the required ecological inputs are available.")
      );
      panel.append(empty);
      return;
    }

    const models = data.models;
    panel.append(summaryBox(data, models));

    const readiness = data.readiness || {};
    const metrics = make("div", "wgec-metrics");
    const metric = (label, value, note) => {
      const card = make("div", "wgec-metric");
      card.append(make("span", "wgec-metric-label", label), make("strong", "wgec-metric-value", String(value)));
      if (note) card.append(make("small", "", note));
      return card;
    };
    metrics.append(
      metric("WINGS samples", readiness.total_samples ?? "—", "total in this run"),
      metric("Seasonal ecology data", readiness.samples_with_phenology ?? "—", "samples with eBird seasonal profiles"),
      metric("Samples with weather data", readiness.samples_with_complete_environment_vector ?? "—", "temperature, precipitation, and wind from ERA5"),
      metric("Distinct weather settings", readiness.distinct_weather_contexts ?? readiness.distinct_environment_profiles ?? "—", "unique location-and-time weather profiles"),
      metric("Minimum samples", readiness.minimum_unique_samples ?? "—", "required for analysis")
    );
    panel.append(metrics);



    const wrap = make("div", "wgec-table-wrap");
    const table = make("table", "wgec-table");
    const thead = make("thead");
    const hr = make("tr");
    ["Segment", "Host vs baseline", "Seasonal ecology vs host", "Environment vs ecology"].forEach(text => hr.append(make("th", "", text)));
    thead.append(hr);
    const tbody = make("tbody");
    for (const segment of SEGMENTS) {
      const row = make("tr");
      row.append(make("th", "wgec-segment", segment));
      for (const [family] of FAMILIES) {
        row.append(modelCell(models.find(item => item.segment === segment && item.comparison === family), family));
      }
      tbody.append(row);
    }
    table.append(thead, tbody);
    wrap.append(table);
    panel.append(wrap);

    const method = make("details", "wgec-method");
    const summary = make("summary", "", "Methods and interpretation guardrails");
    const body = make("div", "wgec-method-body");

    const modelList = make("ul");
    [
      ["M0", "Spatiotemporal", "time + geography"],
      ["M1", "Host", "+ same host"],
      ["M2", "Seasonal ecology", "+ eBird annual-profile distance"],
      ["M3", "Environment", "+ standardized ERA5 weather distance"],
    ].forEach(([code, name, predictors]) => {
      modelList.append(make("li", "", `${code} — ${name}: ${predictors}`));
    });

    body.append(
      make("p", "", "Modeling approach: nested ordinary least-squares linear regression models relate segment-specific genomic distance to time, geography, host identity, seasonal ecology, and weather. Each model adds predictors to the previous model, and added explanatory value is measured by the increase in R² (ΔR²)."),
      make("p", "", "Models compared:"),
      modelList,
      make("p", "", "Outcome: segment-specific pairwise patristic distance among unambiguous WINGS sample tips."),
      make("p", "", `Seasonal ecology: ${data.seasonal_profile_metric || "eBird seasonal-profile distance."}`),
      make("p", "", `Weather: ${data.environmental_distance?.method || "standardized ERA5 environmental distance using temperature, precipitation, and wind."}`),
      make("p", "", `Inference: Because pairwise observations share samples, conventional OLS p-values are not used. Statistical evidence is assessed using ${data.permutation_test?.method || "sample-label permutation."} ${data.permutation_test?.multiple_testing || ""}`),
      make("p", "wgec-guardrail", "Pair rows share biological samples and are not independent observations. Unique-sample counts are therefore shown for every comparison. Concordance is not evidence of direct transmission, infection source, reassortment, or causality.")
    );
    const outputs = make("p", "wgec-outputs", `Detailed outputs: ${(data.detailed_outputs || []).join(" · ")}`);
    body.append(outputs);
    method.append(summary, body);
    panel.append(method);
  }

  function mount(explorer, panel) {
    if (!panel) throw new Error("Concordance tab panel is required.");
    render(explorer, panel);
    return {VERSION, refresh: () => render(explorer, panel)};
  }

  globalThis.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE = {VERSION, mount};
})();
