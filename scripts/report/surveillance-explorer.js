/* WINGS_EXPLORER_TABS_JS_BEGIN */
(() => {
  "use strict";

  const VERSION = "0.2.0";

  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const TAB_ORDER = ["overview", "genome", "ecology", "coverage", "concordance", "outbreak"];
  const TAB_LABELS = {
    overview: "Overview",
    genome: "Genome",
    ecology: "Ecology",
    coverage: "Sampling & Detections",
    concordance: "Concordance",
    outbreak: "Outbreak context",
  };


  function coverageNumber(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === "string" && value.trim() === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function coverageFmt(value) {
    const n = coverageNumber(value);
    return n === null ? "Unavailable" : n.toLocaleString("en-US");
  }

  function coveragePct(numerator, denominator) {
    const n = coverageNumber(numerator), d = coverageNumber(denominator);
    return n === null || d === null || d <= 0 ? null : 100 * n / d;
  }

  function coverageChange(current, prior) {
    const c = coverageNumber(current), p = coverageNumber(prior);
    if (c === null || p === null || p === 0) return null;
    return 100 * (c - p) / p;
  }

  function aggregateCoverageRecords(records, hostFilter="ALL") {
    const rows = (records || []).filter(row => hostFilter === "ALL" || String(row.host || "") === hostFilter);
    const fields = ["sampled", "tested", "positive", "sequenced"];
    const total = field => {
      const vals = rows.map(row => coverageNumber(row[field])).filter(v => v !== null);
      return vals.length ? vals.reduce((a,b)=>a+b,0) : null;
    };
    const groups = new Map();
    for (const row of rows) {
      const key = `${row.period_start}|${row.period_end}`;
      if (!groups.has(key)) groups.set(key, {period_start:row.period_start,period_end:row.period_end,rows:[]});
      groups.get(key).rows.push(row);
    }
    const periods = [...groups.values()].sort((a,b)=>a.period_start.localeCompare(b.period_start)).map(group => ({
      period_start:group.period_start,
      period_end:group.period_end,
      ...Object.fromEntries(fields.map(field => {
        const vals = group.rows.map(row=>coverageNumber(row[field])).filter(v=>v!==null);
        return [field, vals.length ? vals.reduce((a,b)=>a+b,0) : null];
      })),
    }));
    return {visibleRows:rows.length, rows, totals:Object.fromEntries(fields.map(field=>[field,total(field)])), periods};
  }

  function coverageComparison(periods) {
    const eligible = (periods || []).filter(p => coverageNumber(p.tested) !== null && coverageNumber(p.positive) !== null);
    if (eligible.length < 2) return null;
    const prior = eligible[eligible.length-2], recent = eligible[eligible.length-1];
    return {
      prior, recent,
      tested_change_pct: coverageChange(recent.tested, prior.tested),
      positive_change_pct: coverageChange(recent.positive, prior.positive),
      prior_positivity_pct: coveragePct(prior.positive, prior.tested),
      recent_positivity_pct: coveragePct(recent.positive, recent.tested),
    };
  }

  function renderCoveragePanel(explorer) {
    const ctx = explorer.payload?.coverage_context || {status:"NOT_CONFIGURED",records:[],genomic_summary:{}};
    const wrap = make("div", "wse-coverage");
    const title = make("div", "wse-coverage-head");
    const heading = make("div");
    heading.append(make("div", "wse-coverage-kicker", "Surveillance lens"), make("h3", "", "Sampling & Detections"));
    title.append(heading);
    wrap.append(title);

    const host = explorer.hostFilter || "ALL";
    const agg = aggregateCoverageRecords(ctx.records || [], host);
    const genomic = ctx.genomic_summary || {};

    if (ctx.status !== "READY") {
      const note = make("p", "wse-coverage-note");
      note.textContent = "Sampling denominator unavailable. WINGS can still show genomic recovery for records in this run, but it will not calculate positivity or normalize detections by testing effort.";
      wrap.append(note);
    }

    const cards = make("div", "wse-coverage-cards");
    const card = (label, value, sub) => {
      const node = make("div", "wse-coverage-card");
      node.append(make("span", "", label), make("strong", "", value), make("small", "", sub));
      return node;
    };
    cards.append(
      card("Sampled", coverageFmt(agg.totals.sampled), "external surveillance denominator"),
      card("Tested", coverageFmt(agg.totals.tested), "external surveillance denominator"),
      card("Positive", coverageFmt(agg.totals.positive), "program-reported detections"),
      card("Sequenced", coverageFmt(agg.totals.sequenced), "program-defined sequencing count")
    );
    wrap.append(cards);

    const funnel = make("section", "wse-coverage-section");
    funnel.append(make("h4", "", "WINGS genomic coverage"));
    const funnelGrid = make("div", "wse-coverage-funnel");
    funnelGrid.append(
      card("WINGS records", coverageFmt(genomic.wings_records), "records entering this run"),
      card("≥1 QC segment", coverageFmt(genomic.at_least_one_qc_segment), "at least one QC-passing segment"),
      card("Complete genomes", coverageFmt(genomic.complete_8_segment_genomes), "8 / 8 QC-passing segments"),
      card("Subtype resolved", coverageFmt(genomic.subtype_resolved), "HA/NA subtype available")
    );
    funnel.append(funnelGrid);
    const caution = make("p", "wse-coverage-caution", "External surveillance totals and WINGS genomic records are shown side by side, not assumed to be one continuous denominator chain.");
    funnel.append(caution);
    wrap.append(funnel);

    const diag = make("section", "wse-coverage-section");
    diag.append(make("h4", "", "Signal-or-Sampling diagnostic"));
    const comp = coverageComparison(agg.periods);
    if (!comp) {
      diag.append(make("p", "wse-coverage-empty", "At least two periods with both tested and positive counts are required for a denominator-aware comparison."));
    } else {
      const pctText = value => value === null ? "not estimable" : `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
      const posPrior = comp.prior_positivity_pct, posRecent = comp.recent_positivity_pct;
      const summary = make("div", "wse-signal-summary");
      summary.append(
        card("Testing effort", pctText(comp.tested_change_pct), `${comp.prior.period_start} → ${comp.recent.period_start}`),
        card("Positive detections", pctText(comp.positive_change_pct), "change in source-record count"),
        card("Positivity", posPrior === null || posRecent === null ? "Unavailable" : `${posPrior.toFixed(1)}% → ${posRecent.toFixed(1)}%`, "positive / tested")
      );
      diag.append(summary);
      const sentence = make("p", "wse-signal-interpretation");
      if (comp.tested_change_pct !== null && comp.positive_change_pct !== null) {
        const delta = comp.positive_change_pct - comp.tested_change_pct;
        sentence.textContent = Math.abs(delta) < 5
          ? "Detection counts changed at approximately the same rate as testing effort in the two most recent comparable periods."
          : delta > 0
            ? "Positive detections changed faster than testing effort in the two most recent comparable periods."
            : "Testing effort changed faster than positive detections in the two most recent comparable periods.";
      } else {
        sentence.textContent = "Counts are shown, but relative change cannot be estimated because a prior value is zero or unavailable.";
      }
      diag.append(sentence, make("p", "wse-coverage-caution", "Descriptive comparison only. It does not establish prevalence, transmission, or whether the difference is biological rather than a change in surveillance design or population mix."));
    }
    wrap.append(diag);

    if (ctx.status === "READY") {
      const tableSection = make("section", "wse-coverage-section");
      tableSection.append(make("h4", "", "Effort by period"));
      const table = document.createElement("table");
      table.className = "wse-coverage-table";
      table.innerHTML = `<thead><tr><th>Period</th><th>Sampled</th><th>Tested</th><th>Positive</th><th>Sequenced</th><th>Positivity</th></tr></thead><tbody></tbody>`;
      const body = table.querySelector("tbody");
      for (const row of agg.periods) {
        const tr = document.createElement("tr");
        const positivity = coveragePct(row.positive, row.tested);
        [ `${row.period_start} – ${row.period_end}`, coverageFmt(row.sampled), coverageFmt(row.tested), coverageFmt(row.positive), coverageFmt(row.sequenced), positivity === null ? "Unavailable" : `${positivity.toFixed(1)}%` ].forEach(value => {
          const td = document.createElement("td"); td.textContent = value; tr.append(td);
        });
        body.append(tr);
      }
      tableSection.append(table);
      wrap.append(tableSection);
    }
    return wrap;
  }

  function mount(explorer) {
    if (!explorer || !explorer.root) throw new Error("Explorer instance is required.");
    if (explorer.explorerTabs) return explorer.explorerTabs;

    const root = explorer.root;
    const shell = root.querySelector(".wse-shell");
    if (!shell) throw new Error("WINGS Explorer shell not found.");

    const timeline = shell.querySelector(".wse-timeline-panel");
    const mainGrid = shell.querySelector(".wse-main-grid");
    const braid = shell.querySelector(".wbc-embedded");
    const genome = shell.querySelector(".wse-genome-panel");
    const genomeFooter = shell.querySelector(".wse-footer-note");
    const ecology = shell.querySelector(".wse-ecology-panel");
    const outbreak = shell.querySelector(".wse-outbreak-panel");

    if (!timeline || !mainGrid || !genome || !ecology) {
      throw new Error("Expected Explorer panels were not found; upstream layout may have changed.");
    }

    shell.classList.add("wse-tabs-mounted");

    const app = make("section", "wse-app-shell");
    app.setAttribute("aria-label", "WINGS Explorer views");

    const toolbar = make("div", "wse-app-toolbar");
    const sampleLabel = make("label", "wse-app-control");
    sampleLabel.append(make("span", "wse-app-control-label", "Sample"));
    const sampleSelect = make("select", "wse-app-sample");
    sampleSelect.setAttribute("aria-label", "Selected WINGS sample");
    sampleSelect.append(new Option("Select a sample…", ""));
    for (const sample of explorer.samples || []) {
      sampleSelect.append(new Option(sample.sample_id, sample.sample_id));
    }
    sampleLabel.append(sampleSelect);

    const hostLabel = make("label", "wse-app-control");
    hostLabel.append(make("span", "wse-app-control-label", "Host"));
    const hostSelect = make("select", "wse-app-host");
    hostSelect.setAttribute("aria-label", "Host filter");
    hostSelect.append(new Option("All hosts", "ALL"));
    for (const host of explorer.hosts || []) hostSelect.append(new Option(host, host));
    hostLabel.append(hostSelect);

    const clearButton = make("button", "wse-app-clear", "Clear selection");
    clearButton.type = "button";

    const context = make("div", "wse-app-context", "No sample selected");
    context.setAttribute("aria-live", "polite");

    toolbar.append(sampleLabel, hostLabel, clearButton, context);

    const nav = make("div", "wse-app-tabs");
    nav.setAttribute("role", "tablist");
    nav.setAttribute("aria-label", "Surveillance Explorer views");

    const views = make("div", "wse-app-views");
    const panels = {};
    const buttons = {};

    TAB_ORDER.forEach((name, index) => {
      const button = make("button", "wse-app-tab", TAB_LABELS[name]);
      button.type = "button";
      button.id = `wse-tab-${name}`;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", `wse-view-${name}`);
      button.setAttribute("aria-selected", index === 0 ? "true" : "false");
      button.tabIndex = index === 0 ? 0 : -1;
      button.dataset.tab = name;
      nav.append(button);
      buttons[name] = button;

      const panel = make("section", "wse-app-view");
      panel.id = `wse-view-${name}`;
      panel.setAttribute("role", "tabpanel");
      panel.setAttribute("aria-labelledby", button.id);
      panel.hidden = index !== 0;
      views.append(panel);
      panels[name] = panel;
    });

    panels.overview.append(timeline, mainGrid);

    const shared = make("div", "wse-app-shared");
    shared.hidden = true;
    if (braid) shared.append(braid);

    const ecologyActions = make("div", "wse-ecology-clock-actions");
    const loadPhenology = make("button", "wse-ecology-clock-action", explorer.payload?.ecological_clock ? "Override phenology" : "Load phenology");
    loadPhenology.type = "button";
    const exportEvidence = make("button", "wse-ecology-clock-action", "Export evidence");
    exportEvidence.type = "button";
    ecologyActions.append(loadPhenology, exportEvidence);
    shared.prepend(ecologyActions);

    const treeDetails = make("details", "wse-genome-details");
    const treeSummary = make("summary", "wse-genome-details-summary", "Individual segment trees and QC evidence");
    treeDetails.append(treeSummary, genome);
    panels.genome.append(treeDetails);
    if (genomeFooter) panels.genome.append(genomeFooter);

    panels.ecology.append(ecology);


    if (panels.concordance) {

      const module = globalThis.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE;

      if (module?.mount) module.mount(explorer, panels.concordance);

      else panels.concordance.append(make("p", "wse-app-empty", "Genomic–Ecological Concordance is unavailable for this report."));

    }
    panels.coverage.append(renderCoveragePanel(explorer));

    if (outbreak) {
      panels.outbreak.append(outbreak);
    } else {
      panels.outbreak.append(make("p", "wse-app-empty", "No outbreak-context panel is available for this run."));
    }

    root.insertBefore(nav, shell);
    app.append(toolbar, shared, views);
    shell.append(app);

    loadPhenology.addEventListener("click", () => {
      braid?.querySelector(".wbc-import-phenology")?.click();
    });
    exportEvidence.addEventListener("click", () => {
      braid?.querySelector(".wbc-export")?.click();
    });

    const duplicateSample = genome.querySelector(".wse-sample-select")?.closest("label");
    if (duplicateSample) duplicateSample.classList.add("wse-duplicate-sample-control");

    let active = "overview";

    // Tree Studio is mounted immediately after Explorer Tabs. Hoist its launcher
    // into the shared Genome/Ecology region so it remains visible above the
    // Genome Braid instead of falling below the long shared component.
    const placeTreeStudio = () => {
      const launch = root.querySelector(".wse-tree-studio-launch");
      if (!launch) return;
      if (launch.parentElement !== shared) shared.prepend(launch);
      launch.hidden = active !== "genome";
    };

    const activate = (name, focus = false) => {
      if (!TAB_ORDER.includes(name)) return;
      active = name;
      for (const key of TAB_ORDER) {
        const selected = key === name;
        buttons[key].setAttribute("aria-selected", String(selected));
        buttons[key].tabIndex = selected ? 0 : -1;
        panels[key].hidden = !selected;
      }
      if (focus) buttons[name].focus();
      if (name === "overview") {
        requestAnimationFrame(() => {
          explorer.renderMap?.();
          explorer.updateEmphasis?.();
        });
      }
      const showShared = Boolean(braid) && (name === "genome" || name === "ecology");
      shared.hidden = !showShared;
      if (braid) braid.dataset.wseLens = showShared ? name : "";
      placeTreeStudio();
      if (name === "coverage") {
        panels.coverage.replaceChildren(renderCoveragePanel(explorer));
      }
      if (showShared) {
        requestAnimationFrame(() => explorer.braidClock?.refresh?.());
      }
    };

    for (const [name, button] of Object.entries(buttons)) {
      button.addEventListener("click", () => activate(name));
      button.addEventListener("keydown", (event) => {
        const index = TAB_ORDER.indexOf(name);
        let next = null;
        if (event.key === "ArrowRight") next = TAB_ORDER[(index + 1) % TAB_ORDER.length];
        if (event.key === "ArrowLeft") next = TAB_ORDER[(index - 1 + TAB_ORDER.length) % TAB_ORDER.length];
        if (event.key === "Home") next = TAB_ORDER[0];
        if (event.key === "End") next = TAB_ORDER[TAB_ORDER.length - 1];
        if (next) {
          event.preventDefault();
          activate(next, true);
        }
      });
    }

    sampleSelect.addEventListener("change", () => {
      explorer.selectedReferenceId = null;
      explorer.selectedSampleId = explorer.sampleById?.has(sampleSelect.value) ? sampleSelect.value : null;
      explorer.hoverSampleId = null;
      explorer.updateSelection();
    });

    hostSelect.addEventListener("change", () => {
      const host = hostSelect.value || "ALL";

      if (typeof explorer.setHostFilter === "function") {
        explorer.setHostFilter(host);
      } else {
        explorer.hostFilter = host;
        explorer.updateSelection();
      }

      panels.coverage.replaceChildren(renderCoveragePanel(explorer));
    });

    clearButton.addEventListener("click", () => {
      explorer.selectedSampleId = null;
      explorer.selectedReferenceId = null;
      explorer.hoverSampleId = null;
      explorer.updateSelection();
    });

    const syncSampleOptions = () => {
      const host = explorer.hostFilter || "ALL";
      const selected = explorer.selectedSampleId || "";

      const samples = (explorer.samples || []).filter(
        sample => host === "ALL" || sample.host === host
      );

      sampleSelect.innerHTML = "";
      sampleSelect.append(new Option("Select a sample…", ""));

      for (const sample of samples) {
        sampleSelect.append(new Option(sample.sample_id, sample.sample_id));
      }

      sampleSelect.value = samples.some(
        sample => sample.sample_id === selected
      ) ? selected : "";
    };

    const sync = () => {
      syncSampleOptions();
      hostSelect.value = explorer.hostFilter || "ALL";
      clearButton.disabled = !explorer.selectedSampleId && !explorer.selectedReferenceId;
      const sample = explorer.selectedSampleId ? explorer.sampleById?.get(explorer.selectedSampleId) : null;
      if (sample) {
        const parts = [sample.sample_id, sample.host, sample.collection_date, sample.genotype?.call].filter(Boolean);
        context.textContent = parts.join(" · ");
      } else if (explorer.selectedReferenceId) {
        context.textContent = `Public reference: ${explorer.selectedReferenceId}`;
      } else {
        context.textContent = "No sample selected";
      }
    };

    const previousUpdateSelection = explorer.updateSelection.bind(explorer);
    explorer.updateSelection = function(...args) {
      const result = previousUpdateSelection(...args);
      sync();
      return result;
    };

    root.addEventListener("click", (event) => {
      const recordsAction = event.target.closest?.('[data-state-action="records"]');
      if (recordsAction) setTimeout(() => activate("outbreak"), 0);
    }, true);

    treeDetails.addEventListener("toggle", () => {
      if (treeDetails.open) requestAnimationFrame(() => {
        explorer.renderTrees?.();
        explorer.updateEmphasis?.();
        explorer.revealSelectedTips?.();
      });
    });

    sync();
    activate("overview");
    // Tree Studio mounts after this function returns; catch that insertion once.
    setTimeout(placeTreeStudio, 0);

    const api = { VERSION, activate, get active() { return active; }, buttons, panels };
    explorer.explorerTabs = api;
    return api;
  }

  globalThis.WINGS_EXPLORER_TABS = { VERSION, TAB_ORDER: [...TAB_ORDER], mount, _test:{aggregateCoverageRecords,coverageComparison} };
})();
/* WINGS_EXPLORER_TABS_JS_END */
/* WINGS_TREE_STUDIO_JS_BEGIN */
(() => {
  "use strict";

  const VERSION = "0.1.9";
  const SEGMENTS = ["PB2", "PB1", "PA", "HA", "NP", "NA", "MP", "NS"];
  const COLORS = ["#8c1d40", "#007c83", "#176b3a", "#6f2da8", "#c45500", "#006dae", "#7d6608", "#37474f", "#b3261e", "#00838f", "#5c1229", "#7a5b00"];
  const NEUTRAL = "#69777d";
  const LIGHT = "#dfe5e7";
  const GOLD = "#ffc627";
  const FILTER_MISSING = "__WINGS_FILTER_MISSING__";
  let sessionCounter = 0;
  const sessions = new Map();

  const POPUP_CSS = String.raw`
:root{--ink:#22363e;--muted:#64777e;--line:#d6dfe1;--panel:#fff;--wash:#f5f8f8;--maroon:#8c1d40;--teal:#007c83;--gold:#ffc627}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);background:#eef3f3}button,select,input{font:inherit}button,select,input[type=text]{border:1px solid #b9c6ca;border-radius:6px;background:#fff;color:var(--ink);min-height:36px;padding:7px 10px}.ts-shell{display:grid;grid-template-rows:auto auto minmax(0,1fr);min-height:100vh}.ts-head{display:flex;gap:20px;align-items:flex-start;justify-content:space-between;padding:16px 20px;background:#fff;border-top:7px solid #000;border-bottom:1px solid var(--line)}.ts-overline{font-size:10px;letter-spacing:.18em;color:var(--maroon);font-weight:800;text-transform:uppercase}.ts-title{font-size:24px;font-weight:800;margin-top:3px;letter-spacing:-.45px}.ts-sub{color:var(--muted);font-size:12px;margin-top:5px}.ts-badge{font-size:10px;border:1px solid #b8cfcc;background:#eaf4f2;color:#246d6b;border-radius:5px;padding:6px 9px;white-space:nowrap}.ts-controls{display:flex;flex-wrap:wrap;gap:10px 12px;align-items:end;padding:10px 16px;background:#f9fbfb;border-bottom:1px solid var(--line)}.ts-control{display:grid;gap:3px}.ts-control>span{font-size:9px;letter-spacing:.08em;font-weight:800;text-transform:uppercase;color:var(--muted)}.ts-search{min-width:210px}.ts-spacer{flex:1}.ts-btn{cursor:pointer;font-weight:700}.ts-btn:hover{border-color:var(--teal);background:#eef7f6}.ts-btn:disabled{cursor:not-allowed;opacity:.45;background:#f4f6f6;border-color:#d7dfe1}.ts-btn[aria-pressed=true]{background:#22363e;color:#fff;border-color:#22363e}.ts-btn[aria-pressed=true]:hover{background:#314a54;border-color:#314a54}.ts-main{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:12px;padding:12px;min-height:0}.ts-canvas-card,.ts-side{background:#fff;border:1px solid var(--line);border-radius:10px;min-width:0;overflow:hidden}.ts-canvas-head{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid var(--line);font-size:12px}.ts-status{color:var(--muted)}.ts-canvas-wrap{position:relative;height:calc(100vh - 185px);min-height:520px;background:#fff;overflow:hidden}.ts-canvas-wrap svg{width:100%;height:100%;display:block;touch-action:none;user-select:none}.ts-canvas-wrap.ts-lasso-active svg{cursor:crosshair}.ts-lasso-path{fill:rgba(0,124,131,.08);stroke:var(--teal);stroke-width:2;stroke-dasharray:7 5;vector-effect:non-scaling-stroke;pointer-events:none}.ts-branch{fill:none;stroke:#6c757b;stroke-width:1.4;vector-effect:non-scaling-stroke}.ts-branch.ts-dim{opacity:.2}.ts-tip{cursor:pointer;outline:none}.ts-tip text{font-size:11px;fill:#24383f}.ts-tip circle{stroke:#fff;stroke-width:1.2;vector-effect:non-scaling-stroke}.ts-tip.ts-selected circle{stroke:var(--gold);stroke-width:4}.ts-tip.ts-selected text{font-weight:800;fill:var(--maroon)}.ts-tip.ts-multi-selected circle{stroke:var(--gold);stroke-width:4}.ts-tip.ts-multi-selected text{font-weight:800;fill:var(--maroon)}.ts-tip.ts-search-hit text{text-decoration:underline;font-weight:800}.ts-tip.ts-dim{opacity:.14}.ts-tip.ts-selected.ts-dim,.ts-tip.ts-multi-selected.ts-dim{opacity:.5}.ts-tip.ts-filter-hit circle{stroke:#40545c;stroke-width:1.8}.ts-tip.ts-filter-hit.ts-selected circle,.ts-tip.ts-filter-hit.ts-multi-selected circle{stroke:var(--gold);stroke-width:4}.ts-support{font-size:8px;fill:#7d898e}.ts-root{fill:#fff;stroke:var(--maroon);stroke-width:2;vector-effect:non-scaling-stroke}.ts-scale{stroke:#202124;stroke-width:2;vector-effect:non-scaling-stroke}.ts-scale-label{font-size:9px;fill:#46545a}.ts-side{padding:14px;overflow:auto;max-height:calc(100vh - 185px)}.ts-side h3{font-size:16px;margin:0 0 10px}.ts-side h4{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:18px 0 7px}.ts-meta{display:grid;gap:6px;font-size:12px}.ts-meta-row{display:grid;grid-template-columns:95px minmax(0,1fr);gap:8px;border-bottom:1px solid #edf0f1;padding-bottom:5px}.ts-meta-row span:first-child{color:var(--muted)}.ts-note{font-size:11px;line-height:1.45;color:var(--muted);padding:8px 9px;background:#f5f8f8;border-left:3px solid var(--teal);margin:10px 0}.ts-warning{border-left-color:#b27617;background:#fbf3df;color:#6a5426}.ts-legend{display:grid;gap:5px}.ts-legend-row{display:flex;align-items:center;gap:7px;font-size:11px}.ts-swatch{width:11px;height:11px;border-radius:50%;flex:0 0 auto}.ts-empty{color:var(--muted);font-size:12px;padding:10px 0}.ts-pills{display:flex;gap:5px;flex-wrap:wrap}.ts-pill{background:#edf4f3;border:1px solid #d3e3e1;color:#216964;border-radius:5px;padding:3px 6px;font-size:10px}.ts-selection-list{display:flex;gap:5px;flex-wrap:wrap;max-height:120px;overflow:auto}.ts-selection-list .ts-pill{background:#fff7df;border-color:#ead18a;color:#654f12}.ts-filter-values{display:flex;flex-wrap:wrap;gap:6px;margin:7px 0 4px}.ts-filter-chip{cursor:pointer;border:1px solid #c8d3d5;background:#fff;color:var(--ink);border-radius:999px;padding:5px 8px;font-size:10px;min-height:0}.ts-filter-chip[aria-pressed=true]{background:#22363e;color:#fff;border-color:#22363e}.ts-filter-chip:hover{border-color:var(--teal)}.ts-filter-summary{font-size:11px;color:var(--muted);line-height:1.45}.ts-filter-clear{margin-top:7px;min-height:30px!important;padding:4px 8px!important;font-size:10px}.ts-help{font-size:10px;color:var(--muted);margin-top:7px}.ts-no-tree{display:grid;place-items:center;height:100%;color:var(--muted);font-weight:700}.ts-footer-note{font-size:10px;color:var(--muted);margin-top:12px;line-height:1.5}@media(max-width:900px){.ts-main{grid-template-columns:1fr}.ts-side{max-height:none}.ts-canvas-wrap{height:65vh;min-height:430px}.ts-head{display:block}.ts-badge{display:inline-block;margin-top:8px}}
`;

  const escHtml = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[ch]));
  const escAttr = value => escHtml(value);
  const clean = (value) => value == null ? "" : String(value).trim();
  const scalarText = value => {
    if (value == null) return "";
    if (["string","number","boolean"].includes(typeof value)) return String(value).trim();
    return "";
  };
  function genotypeText(value) {
    const scalar = scalarText(value);
    if (scalar) return scalar;
    if (!value || typeof value !== "object") return "";
    for (const key of ["call","genotype","label","name","value"]) {
      const nested = genotypeText(value[key]);
      if (nested) return nested;
    }
    return "";
  }

  const US_STATE_CODES = Object.freeze({
    "ALABAMA":"AL","ALASKA":"AK","ARIZONA":"AZ","ARKANSAS":"AR","CALIFORNIA":"CA",
    "COLORADO":"CO","CONNECTICUT":"CT","DELAWARE":"DE","DISTRICT OF COLUMBIA":"DC",
    "FLORIDA":"FL","GEORGIA":"GA","HAWAII":"HI","IDAHO":"ID","ILLINOIS":"IL",
    "INDIANA":"IN","IOWA":"IA","KANSAS":"KS","KENTUCKY":"KY","LOUISIANA":"LA",
    "MAINE":"ME","MARYLAND":"MD","MASSACHUSETTS":"MA","MICHIGAN":"MI","MINNESOTA":"MN",
    "MISSISSIPPI":"MS","MISSOURI":"MO","MONTANA":"MT","NEBRASKA":"NE","NEVADA":"NV",
    "NEW HAMPSHIRE":"NH","NEW JERSEY":"NJ","NEW MEXICO":"NM","NEW YORK":"NY",
    "NORTH CAROLINA":"NC","NORTH DAKOTA":"ND","OHIO":"OH","OKLAHOMA":"OK","OREGON":"OR",
    "PENNSYLVANIA":"PA","RHODE ISLAND":"RI","SOUTH CAROLINA":"SC","SOUTH DAKOTA":"SD",
    "TENNESSEE":"TN","TEXAS":"TX","UTAH":"UT","VERMONT":"VT","VIRGINIA":"VA",
    "WASHINGTON":"WA","WEST VIRGINIA":"WV","WISCONSIN":"WI","WYOMING":"WY",
    "PUERTO RICO":"PR","GUAM":"GU","AMERICAN SAMOA":"AS","NORTHERN MARIANA ISLANDS":"MP",
    "U.S. VIRGIN ISLANDS":"VI","US VIRGIN ISLANDS":"VI","VIRGIN ISLANDS":"VI",
    "WASHINGTON DC":"DC","WASHINGTON, DC":"DC","D.C.":"DC"
  });
  const US_STATE_CODE_SET = new Set(Object.values(US_STATE_CODES));
  function normalizeUSState(value) {
    const raw = clean(value);
    if (!raw) return "";
    let key = raw.toUpperCase().replace(/^US[-_ ]/, "").replace(/\s+/g, " ").trim();
    if (US_STATE_CODES[key]) return US_STATE_CODES[key];
    if (US_STATE_CODE_SET.has(key)) return key;
    return raw;
  }
  const parseDate = value => /^\d{4}-\d{2}-\d{2}$/.test(clean(value)) ? Date.parse(`${value}T00:00:00Z`) : NaN;
  const numericSupport = value => /^[0-9]+(?:\.[0-9]+)?(?:\/[0-9]+(?:\.[0-9]+)?)*$/.test(clean(value));

  function cloneSourceTree(root) {
    let uid = 0, leafOrder = 0;
    const walk = (node, path = "r") => {
      const out = {
        _uid: `n${uid++}`,
        _sourcePath: path,
        name: clean(node.name),
        label: clean(node.label),
        length: Number.isFinite(Number(node.length)) ? Number(node.length) : 0,
        sample_id: clean(node.sample_id),
        reference_id: clean(node.reference_id),
        accession_version: clean(node.accession_version),
      };
      if (Array.isArray(node.children) && node.children.length) {
        out.children = node.children.map((child, i) => walk(child, `${path}.${i}`));
      } else {
        out.children = [];
        out._leafOrder = leafOrder++;
      }
      return out;
    };
    return walk(root);
  }

  function annotateTree(root) {
    const visit = node => {
      if (!node.children?.length) {
        node._leafCount = 1;
        node._minLeafOrder = node._leafOrder ?? Number.MAX_SAFE_INTEGER;
        return node;
      }
      node.children.forEach(visit);
      node._leafCount = node.children.reduce((s, c) => s + c._leafCount, 0);
      node._minLeafOrder = Math.min(...node.children.map(c => c._minLeafOrder));
      return node;
    };
    return visit(root);
  }

  function graphFromTree(root) {
    const nodes = new Map(), adj = new Map();
    const ensure = node => {
      nodes.set(node._uid, node);
      if (!adj.has(node._uid)) adj.set(node._uid, []);
    };
    const walk = node => {
      ensure(node);
      for (const child of node.children || []) {
        ensure(child);
        const length = Math.max(0, Number(child.length) || 0);
        adj.get(node._uid).push({to: child._uid, length});
        adj.get(child._uid).push({to: node._uid, length});
        walk(child);
      }
    };
    walk(root);
    return {nodes, adj, sourceRootId: root._uid};
  }

  function cloneGraph(graph) {
    return {
      nodes: new Map([...graph.nodes].map(([id, n]) => [id, {...n, children: []}])),
      adj: new Map([...graph.adj].map(([id, edges]) => [id, edges.map(e => ({...e}))])),
      sourceRootId: graph.sourceRootId,
    };
  }

  function replaceEdge(adj, a, b, rootId, lenA, lenB) {
    adj.set(a, (adj.get(a) || []).filter(e => e.to !== b));
    adj.set(b, (adj.get(b) || []).filter(e => e.to !== a));
    adj.set(rootId, [{to:a,length:lenA},{to:b,length:lenB}]);
    adj.get(a).push({to:rootId,length:lenA});
    adj.get(b).push({to:rootId,length:lenB});
  }

  function rootedFromGraph(graph, rootId) {
    const build = (id, parent = null, parentLength = 0) => {
      const src = graph.nodes.get(id) || {_uid:id,name:"",label:"",sample_id:"",reference_id:"",accession_version:""};
      const out = {...src, length: parentLength, children: []};
      for (const edge of graph.adj.get(id) || []) {
        if (edge.to === parent) continue;
        out.children.push(build(edge.to, id, edge.length));
      }
      return out;
    };
    const root = build(rootId);
    root.length = 0;
    return annotateTree(root);
  }

  function farthestLeaf(graph, startId) {
    let best = {id:startId, distance:-1};
    const stack = [{id:startId,parent:null,distance:0}];
    while (stack.length) {
      const cur = stack.pop();
      const node = graph.nodes.get(cur.id);
      const degree = (graph.adj.get(cur.id) || []).length;
      const isLeaf = node && (!node.children?.length) && degree <= 1;
      if (isLeaf && cur.distance > best.distance) best = {id:cur.id,distance:cur.distance};
      for (const edge of graph.adj.get(cur.id) || []) if (edge.to !== cur.parent) {
        stack.push({id:edge.to,parent:cur.id,distance:cur.distance + edge.length});
      }
    }
    return best;
  }

  function pathBetween(graph, startId, targetId) {
    const stack = [{id:startId,parent:null}];
    const parent = new Map([[startId, null]]), edgeLen = new Map();
    while (stack.length) {
      const cur = stack.pop();
      if (cur.id === targetId) break;
      for (const edge of graph.adj.get(cur.id) || []) {
        if (parent.has(edge.to)) continue;
        parent.set(edge.to, cur.id);
        edgeLen.set(edge.to, edge.length);
        stack.push({id:edge.to,parent:cur.id});
      }
    }
    if (!parent.has(targetId)) return [];
    const ids = [];
    let id = targetId;
    while (id != null) { ids.push(id); id = parent.get(id); }
    ids.reverse();
    const path = [];
    for (let i=0;i<ids.length;i++) path.push({id:ids[i], lengthFromPrevious:i===0?0:edgeLen.get(ids[i])||0});
    return path;
  }

  function midpointRoot(sourceRoot) {
    const base = annotateTree(cloneSourceTree(sourceRoot));
    const graph = graphFromTree(base);
    const leaves = [...graph.nodes.values()].filter(n => !n.children?.length);
    if (leaves.length < 2) return base;
    const a = farthestLeaf(graph, leaves[0]._uid).id;
    const b = farthestLeaf(graph, a).id;
    const path = pathBetween(graph, a, b);
    const total = path.reduce((s,p)=>s+p.lengthFromPrevious,0);
    const half = total/2;
    let walked = 0;
    for (let i=1;i<path.length;i++) {
      const len = path[i].lengthFromPrevious;
      if (Math.abs(walked + len - half) < 1e-12) return rootedFromGraph(graph, path[i].id);
      if (walked + len > half) {
        const g = cloneGraph(graph);
        const rootId = "midpoint-root";
        g.nodes.set(rootId,{_uid:rootId,name:"",label:"",sample_id:"",reference_id:"",accession_version:"",children:[]});
        g.adj.set(rootId,[]);
        const distFromA = half - walked;
        replaceEdge(g.adj, path[i-1].id, path[i].id, rootId, distFromA, len - distFromA);
        return rootedFromGraph(g, rootId);
      }
      walked += len;
    }
    return rootedFromGraph(graph, graph.sourceRootId);
  }

  function outgroupRoot(sourceRoot, tipKey) {
    const base = annotateTree(cloneSourceTree(sourceRoot));
    const graph = graphFromTree(base);
    const tip = [...graph.nodes.values()].find(n => leafKey(n) === tipKey);
    if (!tip) return base;
    const edges = graph.adj.get(tip._uid) || [];
    if (edges.length !== 1) return base;
    const edge = edges[0];
    const g = cloneGraph(graph);
    const rootId = "outgroup-root";
    g.nodes.set(rootId,{_uid:rootId,name:"",label:"",sample_id:"",reference_id:"",accession_version:"",children:[]});
    g.adj.set(rootId,[]);
    replaceEdge(g.adj, tip._uid, edge.to, rootId, edge.length/2, edge.length/2);
    return rootedFromGraph(g, rootId);
  }

  function leafKey(node) {
    if (node.sample_id) return `s:${node.sample_id}`;
    if (node.reference_id) return `r:${node.reference_id}`;
    return `t:${node.name}`;
  }

  function allLeaves(root) {
    const leaves=[];
    (function walk(node){ if (!node.children?.length) leaves.push(node); else node.children.forEach(walk); })(root);
    return leaves;
  }

  function leafInfo(node, data) {
    if (node.sample_id) {
      const s = data.sampleById.get(node.sample_id) || {};
      return {
        key: leafKey(node), source:"WINGS", id:node.sample_id, tip:node.name,
        label:node.sample_id, host:clean(s.host), genotype:genotypeText(s.genotype),
        country:clean(s.country), state:normalizeUSState(s.state), state_raw:clean(s.state), date:clean(s.collection_date),
        isolate:clean(s.isolate), accession:"", sample_id:node.sample_id, reference_id:"",
      };
    }
    if (node.reference_id) {
      const r = data.referenceById.get(node.reference_id) || {};
      const segmentRec = r.segments?.[data.segment] || {};
      return {
        key:leafKey(node), source:"Public reference", id:node.reference_id, tip:node.name,
        label:clean(r.isolate || r.reference_id || node.reference_id), host:clean(r.host),
        genotype:genotypeText(r.genotype) || genotypeText(r.genotype_call), country:clean(r.country), state:normalizeUSState(r.state), state_raw:clean(r.state),
        date:clean(r.collection_date), isolate:clean(r.isolate),
        accession:clean(segmentRec.accession_version || node.accession_version || r.accession_version),
        sample_id:"", reference_id:node.reference_id,
      };
    }
    return {key:leafKey(node),source:"Unannotated",id:node.name,tip:node.name,label:node.name,host:"",genotype:"",country:"",state:"",state_raw:"",date:"",isolate:"",accession:"",sample_id:"",reference_id:""};
  }

  function traitValue(info, trait) {
    if (trait === "source") return info.source;
    if (trait === "collection_date") return info.date;
    return clean(info[trait]);
  }

  function filterTraitValue(info, trait) {
    const value = traitValue(info, trait);
    return value || FILTER_MISSING;
  }

  function matchesTraitFilter(info, trait, selectedValues) {
    if (!trait || trait === "none" || !Array.isArray(selectedValues) || selectedValues.length === 0) return true;
    return selectedValues.includes(filterTraitValue(info, trait));
  }

  function descendantHasFilterMatch(node, data, trait, selectedValues) {
    if (!trait || trait === "none" || !Array.isArray(selectedValues) || selectedValues.length === 0) return true;
    return allLeaves(node).some(leaf => matchesTraitFilter(leafInfo(leaf, data), trait, selectedValues));
  }

  function sortTree(root, mode, data) {
    const metric = node => {
      const leaves = allLeaves(node);
      if (mode === "ladder-asc" || mode === "ladder-desc") return leaves.length;
      if (mode === "date") {
        const dates = leaves.map(l=>parseDate(leafInfo(l,data).date)).filter(Number.isFinite);
        return dates.length ? Math.min(...dates) : Number.POSITIVE_INFINITY;
      }
      return Math.min(...leaves.map(l=>Number.isFinite(l._minLeafOrder)?l._minLeafOrder:(Number.isFinite(l._leafOrder)?l._leafOrder:Number.MAX_SAFE_INTEGER)));
    };
    const walk = node => {
      node.children?.forEach(walk);
      if (!node.children?.length) return;
      node.children.sort((a,b)=> {
        const av=metric(a), bv=metric(b);
        if (mode === "ladder-desc") return bv-av;
        return av-bv;
      });
    };
    walk(root);
    return root;
  }

  function categoricalColors(values) {
    const unique = [...new Set(values.filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    return new Map(unique.map((v,i)=>[v,COLORS[i%COLORS.length]]));
  }

  function dateColor(value, min, max) {
    const n=parseDate(value);
    if (!Number.isFinite(n) || !Number.isFinite(min) || !Number.isFinite(max)) return "#aeb7bb";
    const t=max===min?0.5:(n-min)/(max-min);
    const hue=215-(195*t);
    return `hsl(${hue} 62% 43%)`;
  }

  function colorContext(root, data, trait) {
    const leaves=allLeaves(root), infos=leaves.map(l=>leafInfo(l,data));
    const values=infos.map(i=>traitValue(i,trait));
    if (trait === "collection_date") {
      const dates=values.map(parseDate).filter(Number.isFinite), min=Math.min(...dates), max=Math.max(...dates);
      return {color:v=>dateColor(v,min,max), values:[...new Set(values.filter(Boolean))].sort(), continuous:true, min, max, missingCount:values.filter(v=>!v).length};
    }
    const map=categoricalColors(values);
    return {color:v=>map.get(v)||"#aeb7bb", values:[...map.keys()], continuous:false, missingCount:values.filter(v=>!v).length};
  }

  function descendantConsensus(node, data, trait) {
    const vals=[...new Set(allLeaves(node).map(l=>traitValue(leafInfo(l,data),trait)).filter(Boolean))];
    return vals.length===1?vals[0]:"";
  }

  function leafLabel(info, mode) {
    if (mode === "tip") return info.tip || info.id;
    if (mode === "accession") return info.accession || info.id;
    if (mode === "isolate") return info.isolate || info.id;
    if (mode === "host") return info.host || info.id;
    if (mode === "genotype") return info.genotype || info.id;
    return info.id || info.tip;
  }

  function layoutRectangular(root, width, height) {
    const leaves=allLeaves(root), top=30, bottom=35, left=35, right=190;
    const yStep=leaves.length>1?(height-top-bottom)/(leaves.length-1):0;
    leaves.forEach((leaf,i)=>leaf._ly=top+i*yStep);
    let maxDist=0,maxDepth=0;
    const setDist=(node,dist=0,depth=0)=>{node._dist=dist;node._depth=depth;maxDist=Math.max(maxDist,dist);maxDepth=Math.max(maxDepth,depth);node.children?.forEach(c=>setDist(c,dist+(Number(c.length)||0),depth+1));};
    setDist(root);
    const usable=Math.max(80,width-left-right);
    const xFor=node=>left+usable*((maxDist>0?node._dist/maxDist:(maxDepth?node._depth/maxDepth:0)));
    const position=node=>{node.children?.forEach(position);node._x=xFor(node);node._y=node.children?.length?node.children.reduce((s,c)=>s+c._y,0)/node.children.length:node._ly;};
    position(root);
    return {leaves,maxDist,left,right,top,bottom};
  }

  function circularMean(angles) {
    if (!angles.length) return 0;
    const x=angles.reduce((s,a)=>s+Math.cos(a),0), y=angles.reduce((s,a)=>s+Math.sin(a),0);
    return Math.atan2(y,x);
  }

  function layoutRadial(root, width, height) {
    const leaves=allLeaves(root), cx=width/2, cy=height/2, margin=120, radius=Math.max(50,Math.min(width,height)/2-margin);
    let maxDist=0,maxDepth=0;
    const setDist=(node,dist=0,depth=0)=>{node._dist=dist;node._depth=depth;maxDist=Math.max(maxDist,dist);maxDepth=Math.max(maxDepth,depth);node.children?.forEach(c=>setDist(c,dist+(Number(c.length)||0),depth+1));};
    setDist(root);
    leaves.forEach((leaf,i)=>leaf._angle=-Math.PI/2+(2*Math.PI*i/Math.max(1,leaves.length)));
    const position=node=>{
      node.children?.forEach(position);
      if (node.children?.length) node._angle=circularMean(node.children.map(c=>c._angle));
      const frac=maxDist>0?node._dist/maxDist:(maxDepth?node._depth/maxDepth:0);
      node._r=radius*frac;node._x=cx+node._r*Math.cos(node._angle);node._y=cy+node._r*Math.sin(node._angle);
    };
    position(root);
    return {leaves,maxDist,cx,cy,radius};
  }

  function treeToNewick(root) {
    const quote = name => {
      const text=clean(name);
      if (!text) return "";
      if (/^[A-Za-z0-9_.|:-]+$/.test(text)) return text;
      return `'${text.replace(/'/g,"''")}'`;
    };
    const walk = (node,isRoot=false) => {
      const body=node.children?.length?`(${node.children.map(c=>walk(c,false)).join(",")})${quote(node.label||node.name)}`:quote(node.name||node.sample_id||node.reference_id);
      return isRoot?body:`${body}:${Math.max(0,Number(node.length)||0).toPrecision(8)}`;
    };
    return walk(root,true)+";";
  }

  function zoomViewBoxToPoint(fullWidth, fullHeight, x, y, currentViewBox=null, minimumZoom=3.2) {
    const fw=Math.max(1,Number(fullWidth)||1), fh=Math.max(1,Number(fullHeight)||1);
    const px=Math.max(0,Math.min(fw,Number(x)||0)), py=Math.max(0,Math.min(fh,Number(y)||0));
    const current=currentViewBox&&Number(currentViewBox.w)>0&&Number(currentViewBox.h)>0?currentViewBox:{x:0,y:0,w:fw,h:fh};
    const currentZoom=Math.max(fw/current.w,fh/current.h);
    const zoom=Math.max(Number(minimumZoom)||3.2,currentZoom);
    const w=fw/zoom,h=fh/zoom;
    const maxX=Math.max(0,fw-w),maxY=Math.max(0,fh-h);
    return {x:Math.max(0,Math.min(maxX,px-w/2)),y:Math.max(0,Math.min(maxY,py-h/2)),w,h};
  }

  function pointInPolygon(point, polygon) {
    const x=Number(point?.x), y=Number(point?.y);
    if (!Number.isFinite(x)||!Number.isFinite(y)||!Array.isArray(polygon)||polygon.length<3) return false;
    let inside=false;
    for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
      const xi=Number(polygon[i]?.x), yi=Number(polygon[i]?.y), xj=Number(polygon[j]?.x), yj=Number(polygon[j]?.y);
      if(![xi,yi,xj,yj].every(Number.isFinite)) continue;
      const intersect=((yi>y)!==(yj>y)) && (x < (xj-xi)*(y-yi)/((yj-yi)||Number.EPSILON)+xi);
      if(intersect) inside=!inside;
    }
    return inside;
  }

  function lassoPath(points) {
    if(!Array.isArray(points)||points.length===0) return "";
    return points.map((p,i)=>`${i?"L":"M"} ${Number(p.x)||0} ${Number(p.y)||0}`).join(" " ) + (points.length>=3?" Z":"");
  }

  function zoomViewBoxToPoints(fullWidth, fullHeight, points, padding=0.22) {
    const fw=Math.max(1,Number(fullWidth)||1), fh=Math.max(1,Number(fullHeight)||1);
    const cleanPoints=(Array.isArray(points)?points:[]).map(p=>({x:Number(p?.x),y:Number(p?.y)})).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
    if(!cleanPoints.length) return {x:0,y:0,w:fw,h:fh};
    if(cleanPoints.length===1) return zoomViewBoxToPoint(fw,fh,cleanPoints[0].x,cleanPoints[0].y,null);
    let minX=Math.min(...cleanPoints.map(p=>p.x)),maxX=Math.max(...cleanPoints.map(p=>p.x)),minY=Math.min(...cleanPoints.map(p=>p.y)),maxY=Math.max(...cleanPoints.map(p=>p.y));
    const minSpanX=Math.max(20,fw*0.025),minSpanY=Math.max(20,fh*0.025);
    let spanX=Math.max(minSpanX,maxX-minX),spanY=Math.max(minSpanY,maxY-minY);
    spanX*=1+Math.max(0,Number(padding)||0)*2; spanY*=1+Math.max(0,Number(padding)||0)*2;
    const aspect=fw/fh;
    if(spanX/spanY>aspect) spanY=spanX/aspect; else spanX=spanY*aspect;
    const cx=(minX+maxX)/2,cy=(minY+maxY)/2;
    const w=Math.min(fw,spanX),h=Math.min(fh,spanY);
    return {x:Math.max(0,Math.min(fw-w,cx-w/2)),y:Math.max(0,Math.min(fh-h,cy-h/2)),w,h};
  }

  function studioBootstrap(payload) {
    "use strict";
    const API = payload.api;
    const data = payload.data;
    const sampleById = new Map(data.samples.map(s=>[s.sample_id,s]));
    const references = data.references || [];
    const referenceById = new Map(references.map(r=>[r.reference_id,r]));
    const state = {
      segment: data.segment_order.includes(payload.initialSegment)?payload.initialSegment:(data.segment_order.includes("HA")?"HA":data.segment_order[0]),
      layout:"rectangular", root:"source", outgroup:"", sort:"original", colorBy:"genotype", filterTrait:"none", filterValues:[], branchColor:"uniform", tipLabel:((data.trees[(data.segment_order.includes(payload.initialSegment)?payload.initialSegment:(data.segment_order.includes("HA")?"HA":data.segment_order[0]))]?.tip_count||0)>120?"focus":"id"), supports:((data.trees[(data.segment_order.includes(payload.initialSegment)?payload.initialSegment:(data.segment_order.includes("HA")?"HA":data.segment_order[0]))]?.tip_count||0)<=120), search:"", selectedSampleId:payload.selectedSampleId||null, selectedReferenceId:payload.selectedReferenceId||null,
      viewBox:null, drag:null, lasso:null, lassoMode:false,
      selectedKeys:new Set([payload.selectedSampleId?`s:${payload.selectedSampleId}`:payload.selectedReferenceId?`r:${payload.selectedReferenceId}`:null].filter(Boolean)),
    };
    const root=document.getElementById("studio");
    root.innerHTML=`<div class="ts-shell"><header class="ts-head"><div><div class="ts-overline">WINGS · phylogenetic exploration</div><div class="ts-title">Tree Studio</div><div class="ts-sub">Interactive display of existing WINGS segment trees. Rerooting and sorting are display transformations; source trees are not modified.</div></div><div class="ts-badge">v${API.VERSION} · offline-capable</div></header><div class="ts-controls"></div><main class="ts-main"><section class="ts-canvas-card"><div class="ts-canvas-head"><strong class="ts-tree-title"></strong><span class="ts-status"></span></div><div class="ts-canvas-wrap"></div></section><aside class="ts-side"></aside></main></div>`;
    const controls=root.querySelector(".ts-controls"), wrap=root.querySelector(".ts-canvas-wrap"), side=root.querySelector(".ts-side"), status=root.querySelector(".ts-status"), title=root.querySelector(".ts-tree-title");
    const options=(arr,val)=>arr.map(([v,l])=>`<option value="${API.escAttr(v)}"${v===val?" selected":""}>${API.escHtml(l)}</option>`).join("");
    controls.innerHTML=`
      <label class="ts-control"><span>Segment</span><select data-c="segment">${options(data.segment_order.map(x=>[x,x]),state.segment)}</select></label>
      <label class="ts-control"><span>Layout</span><select data-c="layout">${options([["rectangular","Rectangular"],["radial","Radial"],["unrooted","Unrooted display"]],state.layout)}</select></label>
      <label class="ts-control"><span>Rooting</span><select data-c="root">${options([["source","As supplied"],["midpoint","Midpoint display root"],["outgroup","Outgroup display root"]],state.root)}</select></label>
      <label class="ts-control"><span>Outgroup</span><select data-c="outgroup"></select></label>
      <label class="ts-control"><span>Sort</span><select data-c="sort">${options([["original","Source order"],["ladder-asc","Ladderize ↑"],["ladder-desc","Ladderize ↓"],["date","Collection date"]],state.sort)}</select></label>
      <label class="ts-control"><span>Tip color</span><select data-c="colorBy">${options([["genotype","Genotype"],["host","Host"],["country","Country"],["state","State"],["collection_date","Collection date"],["source","WINGS / public"]],state.colorBy)}</select></label>
      <label class="ts-control"><span>Filter trait</span><select data-c="filterTrait">${options([["none","None"],["genotype","Genotype"],["host","Host"],["country","Country"],["state","State"],["source","WINGS / public"]],state.filterTrait)}</select></label>
      <label class="ts-control"><span>Branches</span><select data-c="branchColor">${options([["uniform","Uniform"],["consensus","Descendant consensus"]],state.branchColor)}</select></label>
      <label class="ts-control"><span>Tip labels</span><select data-c="tipLabel">${options([["focus","Selected / search only"],["id","Sample / reference ID"],["tip","Tree tip"],["accession","Accession"],["isolate","Isolate"],["host","Host"],["genotype","Genotype"]],state.tipLabel)}</select></label>
      <label class="ts-control"><span>Support</span><select data-c="supports">${options([["yes","Show"],["no","Hide"]],state.supports?"yes":"no")}</select></label>
      <label class="ts-control ts-search"><span>Search tips</span><input type="text" data-c="search" placeholder="sample, accession, host, genotype…"></label>
      <span class="ts-spacer"></span><button class="ts-btn" data-a="lasso" aria-pressed="false" title="Drag a freehand loop around terminal taxa">Lasso select</button><button class="ts-btn" data-a="deselect" disabled>Deselect all</button><button class="ts-btn" data-a="zoom-selected" disabled>Zoom to selected</button><button class="ts-btn" data-a="fit">Fit</button><button class="ts-btn" data-a="svg">SVG</button><button class="ts-btn" data-a="png">PNG</button><button class="ts-btn" data-a="newick">Newick</button><button class="ts-btn" data-a="metadata">Metadata TSV</button>`;

    const c=name=>controls.querySelector(`[data-c="${name}"]`);
    function getTree(){ return data.trees[state.segment]?.root || null; }
    function updateOutgroups(tree){
      const select=c("outgroup"); const old=state.outgroup; select.innerHTML="";
      if (!tree) return;
      const localData={sampleById,referenceById,segment:state.segment};
      const base=API.annotateTree(API.cloneSourceTree(tree));
      const leaves=API.allLeaves(base);
      for(const leaf of leaves){const info=API.leafInfo(leaf,localData);const opt=new Option(info.label||info.id,info.key);select.append(opt);}
      if ([...select.options].some(o=>o.value===old)) select.value=old; else {select.value=select.options[0]?.value||"";state.outgroup=select.value;}
    }
    function displayedTree(){
      const source=getTree(); if(!source) return null;
      let tree;
      if(state.layout==="unrooted" || state.root==="source") tree=API.annotateTree(API.cloneSourceTree(source));
      else if(state.root==="midpoint") tree=API.midpointRoot(source);
      else tree=API.outgroupRoot(source,state.outgroup);
      return API.sortTree(tree,state.sort,{sampleById,referenceById,segment:state.segment});
    }
    function infoMatches(info){const q=state.search.trim().toLowerCase();if(!q)return true;return [info.id,info.tip,info.host,info.genotype,info.country,info.state,info.date,info.isolate,info.accession,info.source].some(v=>String(v||"").toLowerCase().includes(q));}
    function selectedKey(){return state.selectedSampleId?`s:${state.selectedSampleId}`:state.selectedReferenceId?`r:${state.selectedReferenceId}`:"";}
    function selectedKeys(){return state.selectedKeys instanceof Set?state.selectedKeys:new Set();}
    function postSingleSelection(){window.opener?.postMessage({type:"WINGS_TREE_STUDIO_SELECT",session:payload.session,sampleId:state.selectedSampleId,referenceId:state.selectedReferenceId},"*");}
    function clearSelection(sync=true){state.selectedKeys=new Set();state.selectedSampleId=null;state.selectedReferenceId=null;if(sync)window.opener?.postMessage({type:"WINGS_TREE_STUDIO_SELECT",session:payload.session,sampleId:null,referenceId:null,clear:true},"*");}
    function makeSingleSelection(key,sync=true){state.selectedKeys=new Set(key?[key]:[]);state.selectedSampleId=key?.startsWith("s:")?key.slice(2):null;state.selectedReferenceId=key?.startsWith("r:")?key.slice(2):null;if(sync)postSingleSelection();}
    function renderSide(tree,colorCtx){
      const localData={sampleById,referenceById,segment:state.segment};
      const leaves=API.allLeaves(tree);
      const selectedSet=selectedKeys();
      const selectedLeaves=leaves.filter(l=>selectedSet.has(API.leafKey(l)));
      const selected=selectedLeaves.length===1?selectedLeaves[0]:leaves.find(l=>API.leafKey(l)===selectedKey());
      const info=selected?API.leafInfo(selected,localData):null;
      const rootText=state.layout==="unrooted"?"Unrooted equal-angle display; root is not interpreted.":state.root==="source"?"Source tree orientation as supplied; no biological root is inferred.":state.root==="midpoint"?"Display rerooted at the branch-length midpoint.":"Display rerooted on the selected outgroup branch.";
      let html=`<h3>${info?API.escHtml(info.label||info.id):"Tree evidence"}</h3><div class="ts-note${state.root!=="source"||state.layout==="unrooted"?" ts-warning":""}">${API.escHtml(rootText)} Source tree bytes and WINGS analysis outputs are unchanged.</div>`;
      if(selectedLeaves.length>1){
        const infos=selectedLeaves.map(l=>API.leafInfo(l,localData));
        const countBy=field=>{const m=new Map();for(const x of infos){const v=clean(x[field])||"Not recorded";m.set(v,(m.get(v)||0)+1);}return [...m.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));};
        const top=(field,n=4)=>countBy(field).slice(0,n).map(([v,c])=>`${v} · ${c}`).join(", ");
        html+=`<h4>Selected taxa · ${selectedLeaves.length}</h4><div class="ts-meta"><div class="ts-meta-row"><span>Sources</span><span>${API.escHtml(top("source"))}</span></div><div class="ts-meta-row"><span>Hosts</span><span>${API.escHtml(top("host"))}</span></div><div class="ts-meta-row"><span>Genotypes</span><span>${API.escHtml(top("genotype"))}</span></div></div><div class="ts-selection-list">${infos.slice(0,60).map(x=>`<span class="ts-pill">${API.escHtml(x.id||x.tip)}</span>`).join("")}${infos.length>60?`<span class="ts-pill">+ ${infos.length-60} more</span>`:""}</div><div class="ts-help">Multiple selection is local to Tree Studio. Use Deselect all to clear it; Shift-click adds/removes individual tips.</div>`;
      } else if(info){
        const rows=[["Source",info.source],["ID",info.id],["Host",info.host],["Genotype",info.genotype],["Collection",info.date],["Country",info.country],["State",info.state],["State source",info.state_raw && info.state_raw !== info.state ? info.state_raw : ""],["Isolate",info.isolate],["Accession",info.accession]].filter(x=>x[1]);
        html+=`<h4>Selected tip</h4><div class="ts-meta">${rows.map(([k,v])=>`<div class="ts-meta-row"><span>${API.escHtml(k)}</span><span>${API.escHtml(v)}</span></div>`).join("")}</div>`;
      } else html+=`<div class="ts-empty">Click a tip to inspect it, Shift-click to build a multi-selection, or turn on Lasso select and draw a loop around terminal taxa.</div>`;

      if(state.filterTrait!=="none"){
        const counts=new Map();
        for(const leaf of leaves){
          const value=API.filterTraitValue(API.leafInfo(leaf,localData),state.filterTrait);
          counts.set(value,(counts.get(value)||0)+1);
        }
        const items=[...counts.entries()].sort((a,b)=>{
          if(a[0]===FILTER_MISSING)return 1;if(b[0]===FILTER_MISSING)return -1;
          return String(a[0]).localeCompare(String(b[0]));
        });
        const active=new Set(state.filterValues);
        const matching=leaves.filter(l=>API.matchesTraitFilter(API.leafInfo(l,localData),state.filterTrait,state.filterValues)).length;
        const traitLabel={genotype:"Genotype",host:"Host",country:"Country",state:"State",source:"WINGS / public"}[state.filterTrait]||state.filterTrait;
        html+=`<h4>Trait filter · ${API.escHtml(traitLabel)}</h4><div class="ts-filter-summary">${active.size?`${matching} of ${leaves.length} tips match. Nonmatching tips and branches without matching descendants are shaded, not removed.`:"Choose one or more values. Multiple values use OR logic; the full topology stays visible."}</div><div class="ts-filter-values">`;
        html+=items.map(([value,count])=>{const label=value===FILTER_MISSING?"Not recorded / not assigned":value;return `<button type="button" class="ts-filter-chip" data-filter-value="${API.escAttr(value)}" aria-pressed="${active.has(value)?"true":"false"}">${API.escHtml(label)} · ${count}</button>`;}).join("");
        html+=`</div>${active.size?'<button type="button" class="ts-btn ts-filter-clear" data-filter-clear="1">Clear trait filter</button>':""}`;
      }

      html+=`<h4>Color legend</h4><div class="ts-legend">`;
      if(colorCtx.continuous){
        html+=`<div class="ts-legend-row"><span class="ts-swatch" style="background:${colorCtx.color(new Date(colorCtx.min).toISOString().slice(0,10))}"></span><span>${Number.isFinite(colorCtx.min)?new Date(colorCtx.min).toISOString().slice(0,10):"No dated tips"}</span></div><div class="ts-legend-row"><span class="ts-swatch" style="background:${colorCtx.color(new Date(colorCtx.max).toISOString().slice(0,10))}"></span><span>${Number.isFinite(colorCtx.max)?new Date(colorCtx.max).toISOString().slice(0,10):""}</span></div>`;
      } else {
        html+=colorCtx.values.slice(0,18).map(v=>`<div class="ts-legend-row"><span class="ts-swatch" style="background:${colorCtx.color(v)}"></span><span>${API.escHtml(v)}</span></div>`).join("");
        if(colorCtx.values.length>18) html+=`<div class="ts-empty">+ ${colorCtx.values.length-18} additional categories</div>`;
      }
      if(colorCtx.missingCount) html+=`<div class="ts-legend-row"><span class="ts-swatch" style="background:#aeb7bb"></span><span>Not recorded / not assigned (${colorCtx.missingCount})</span></div>`;
      html+=`</div><h4>Display semantics</h4><div class="ts-footer-note">Trait filtering is a display operation: nonmatching observations are shaded rather than deleted, and a branch remains emphasized when at least one descendant tip matches the active filter. Multiple selected trait values use OR logic. Branch coloring by “descendant consensus” is a visual summary: a branch is colored only when all descendant annotated tips share the selected categorical trait. It is not ancestral-state reconstruction. Numeric internal labels are displayed as recorded; rerooting does not recompute support. Collection dates are metadata and are not used to time-calibrate the tree.</div>`;
      side.innerHTML=html;
      side.querySelectorAll("[data-filter-value]").forEach(button=>button.addEventListener("click",()=>{
        const value=button.dataset.filterValue;
        const set=new Set(state.filterValues);
        if(set.has(value))set.delete(value);else set.add(value);
        state.filterValues=[...set];
        render();
      }));
      side.querySelector("[data-filter-clear]")?.addEventListener("click",()=>{state.filterValues=[];render();});
    }
    function render(){
      const source=getTree();
      updateOutgroups(source);
      c("root").disabled=state.layout==="unrooted"; c("outgroup").disabled=state.layout==="unrooted"||state.root!=="outgroup";
      if(!source){wrap.innerHTML='<div class="ts-no-tree">No tree available for this segment.</div>';side.innerHTML="";title.textContent=`${state.segment} · unavailable`;status.textContent="";return;}
      const tree=displayedTree(), localData={sampleById,referenceById,segment:state.segment};
      const leaves=API.allLeaves(tree), colorCtx=API.colorContext(tree,localData,state.colorBy);
      const width=1500, height=Math.max(650,state.layout==="rectangular"?Math.min(1800,80+leaves.length*17):900);
      const layout=state.layout==="rectangular"?API.layoutRectangular(tree,width,height):API.layoutRadial(tree,width,height);
      const searchActive=Boolean(state.search.trim());
      const filterActive=state.filterTrait!=="none"&&state.filterValues.length>0;
      const passesFilter=info=>API.matchesTraitFilter(info,state.filterTrait,state.filterValues);
      const selectedSet=selectedKeys();
      const selected=selectedKey();
      const zoomFactor=state.viewBox?width/state.viewBox.w:1;
      const declutterLabels=leaves.length>120&&state.tipLabel!=="focus"&&zoomFactor<2.8;
      const parts=[];
      const branchColor=node=>{
        if(state.branchColor!=="consensus"||state.colorBy==="collection_date")return NEUTRAL;
        const v=API.descendantConsensus(node,localData,state.colorBy); return v?colorCtx.color(v):NEUTRAL;
      };
      const walkBranches=node=>{
        for(const child of node.children||[]){
          const descendantInfos=API.allLeaves(child).map(l=>API.leafInfo(l,localData));
          const branchHasMatch=descendantInfos.some(info=>(!searchActive||infoMatches(info))&&(!filterActive||passesFilter(info)));
          const dim=(searchActive||filterActive)&&!branchHasMatch;
          const stroke=branchColor(child);
          if(state.layout==="rectangular"){
            parts.push(`<path class="ts-branch${dim?" ts-dim":""}" stroke="${stroke}" d="M ${node._x} ${node._y} L ${node._x} ${child._y} L ${child._x} ${child._y}"/>`);
          } else parts.push(`<line class="ts-branch${dim?" ts-dim":""}" stroke="${stroke}" x1="${node._x}" y1="${node._y}" x2="${child._x}" y2="${child._y}"/>`);
          if(state.supports&&API.numericSupport(child.label)) parts.push(`<text class="ts-support" x="${(node._x+child._x)/2+3}" y="${(node._y+child._y)/2-3}">${API.escHtml(child.label)}</text>`);
          walkBranches(child);
        }
      };
      walkBranches(tree);
      if(state.layout!=="unrooted") parts.push(`<circle class="ts-root" cx="${tree._x}" cy="${tree._y}" r="4"><title>Displayed root</title></circle>`);
      for(const leaf of leaves){
        const info=API.leafInfo(leaf,localData), value=API.traitValue(info,state.colorBy), color=colorCtx.color(value), hit=infoMatches(info), filterMatch=passesFilter(info), isSel=selectedSet.has(info.key), isPrimary=info.key===selected;
        const dim=(searchActive&&!hit)||(filterActive&&!filterMatch);
        const klass=`ts-tip${isPrimary?" ts-selected":""}${isSel&&!isPrimary?" ts-multi-selected":""}${searchActive&&hit?" ts-search-hit":""}${filterActive&&filterMatch?" ts-filter-hit":""}${dim?" ts-dim":""}`;
        let tx=leaf._x+9,ty=leaf._y+4,anchor="start";
        if(state.layout!=="rectangular"){
          const left=Math.cos(leaf._angle)<0; tx=leaf._x+(left?-8:8);ty=leaf._y+3;anchor=left?"end":"start";
        }
        const requestedLabel=state.tipLabel==="focus"?info.id:API.leafLabel(info,state.tipLabel);
        const showLabel=state.tipLabel==="focus"?(isSel||(searchActive&&hit)):(declutterLabels?(isSel||(searchActive&&hit)):true);
        const shownLabel=showLabel?requestedLabel:"";parts.push(`<g class="${klass}" tabindex="0" role="button" data-key="${API.escAttr(info.key)}"><circle cx="${leaf._x}" cy="${leaf._y}" r="4.2" fill="${color}"/><text x="${tx}" y="${ty}" text-anchor="${anchor}">${API.escHtml(shownLabel)}</text><title>${API.escHtml([info.id,info.host,info.genotype,info.date,info.accession].filter(Boolean).join(" · "))}</title></g>`);
      }
      if(state.layout==="rectangular"&&layout.maxDist>0){const x0=40,x1=160,y=height-13;const val=layout.maxDist*((x1-x0)/(width-225));parts.push(`<line class="ts-scale" x1="${x0}" y1="${y}" x2="${x1}" y2="${y}"/><text class="ts-scale-label" x="${(x0+x1)/2}" y="${y-5}" text-anchor="middle">${val.toPrecision(2)} substitutions/site</text>`);}
      const view=state.viewBox||{x:0,y:0,w:width,h:height};
      wrap.classList.toggle("ts-lasso-active",state.lassoMode);
      wrap.innerHTML=`<svg id="tree-svg" data-full-width="${width}" data-full-height="${height}" viewBox="${view.x} ${view.y} ${view.w} ${view.h}" aria-label="Interactive ${API.escAttr(state.segment)} phylogenetic tree" xmlns="http://www.w3.org/2000/svg">${parts.join("")}<path class="ts-lasso-path" d="" hidden/></svg>`;
      const svg=wrap.querySelector("svg");
      const zoomSelectedButton=controls.querySelector('[data-a="zoom-selected"]'), deselectButton=controls.querySelector('[data-a="deselect"]'), lassoButton=controls.querySelector('[data-a="lasso"]');
      const visibleSelected=svg.querySelectorAll(".ts-tip.ts-selected,.ts-tip.ts-multi-selected").length;
      if(zoomSelectedButton) zoomSelectedButton.disabled=visibleSelected===0;
      if(deselectButton) deselectButton.disabled=selectedKeys().size===0;
      if(lassoButton) lassoButton.setAttribute("aria-pressed",String(state.lassoMode));
      svg.querySelectorAll(".ts-tip").forEach(g=>{const choose=(event=null)=>{const key=g.dataset.key;if(event?.shiftKey){const set=new Set(selectedKeys());if(set.has(key))set.delete(key);else set.add(key);state.selectedKeys=set;state.selectedSampleId=null;state.selectedReferenceId=null;render();return;}makeSingleSelection(key,true);render();};g.addEventListener("click",choose);g.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();choose(e);}});});
      svg.addEventListener("wheel",e=>{e.preventDefault();const vb=svg.viewBox.baseVal, rect=svg.getBoundingClientRect(), mx=vb.x+(e.clientX-rect.left)/rect.width*vb.width,my=vb.y+(e.clientY-rect.top)/rect.height*vb.height,f=API.wheelZoomFactor(e.deltaY,e.deltaMode),nw=vb.width*f,nh=vb.height*f;state.viewBox={x:mx-(mx-vb.x)*f,y:my-(my-vb.y)*f,w:nw,h:nh};render();},{passive:false});
      const svgPoint=e=>{const vb=svg.viewBox.baseVal,rect=svg.getBoundingClientRect();return {x:vb.x+(e.clientX-rect.left)/rect.width*vb.width,y:vb.y+(e.clientY-rect.top)/rect.height*vb.height};};
      svg.addEventListener("pointerdown",e=>{
        if(state.lassoMode){
          e.preventDefault();svg.setPointerCapture(e.pointerId);const p=svgPoint(e);state.lasso={pointerId:e.pointerId,points:[p],additive:Boolean(e.shiftKey)};const path=svg.querySelector(".ts-lasso-path");if(path){path.hidden=false;path.setAttribute("d",API.lassoPath(state.lasso.points));}return;
        }
        // Tip clicks are selection actions, not pan gestures. Capturing the
        // pointer on the SVG here would retarget pointerup/click away from the
        // tip group in some browsers, making visible tip nodes appear inert.
        if(e.target.closest?.(".ts-tip")) return;
        svg.setPointerCapture(e.pointerId);
        const vb=svg.viewBox.baseVal;
        state.drag={x:e.clientX,y:e.clientY,vx:vb.x,vy:vb.y,vw:vb.width,vh:vb.height};
      });
      svg.addEventListener("pointermove",e=>{
        if(state.lasso&&e.pointerId===state.lasso.pointerId){const p=svgPoint(e),prev=state.lasso.points[state.lasso.points.length-1];if(!prev||Math.hypot(p.x-prev.x,p.y-prev.y)>2){state.lasso.points.push(p);const path=svg.querySelector(".ts-lasso-path");if(path)path.setAttribute("d",API.lassoPath(state.lasso.points));}return;}
        if(!state.drag)return;const rect=svg.getBoundingClientRect(),dx=(e.clientX-state.drag.x)/rect.width*state.drag.vw,dy=(e.clientY-state.drag.y)/rect.height*state.drag.vh;state.viewBox={x:state.drag.vx-dx,y:state.drag.vy-dy,w:state.drag.vw,h:state.drag.vh};svg.setAttribute("viewBox",`${state.viewBox.x} ${state.viewBox.y} ${state.viewBox.w} ${state.viewBox.h}`);
      });
      const finishPointer=(e,cancelled=false)=>{
        if(state.lasso&&(!e||e.pointerId===state.lasso.pointerId)){const polygon=state.lasso.points,additive=state.lasso.additive;state.lasso=null;if(cancelled||polygon.length<3){render();return;}const keys=[];svg.querySelectorAll(".ts-tip").forEach(g=>{const circle=g.querySelector("circle"),p={x:Number(circle?.getAttribute("cx")),y:Number(circle?.getAttribute("cy"))};if(API.pointInPolygon(p,polygon))keys.push(g.dataset.key);});const set=additive?new Set(selectedKeys()):new Set();keys.forEach(k=>set.add(k));state.selectedKeys=set;state.selectedSampleId=null;state.selectedReferenceId=null;render();return;}state.drag=null;
      };
      svg.addEventListener("pointerup",e=>finishPointer(e,false));svg.addEventListener("pointercancel",e=>finishPointer(e,true));
      title.textContent=`${state.segment} · ${leaves.length} tips`;
      const filterCount=filterActive?leaves.filter(l=>passesFilter(API.leafInfo(l,localData))).length:null;
      status.textContent=`${state.layout}${state.layout!=="unrooted"?` · ${state.root==="source"?"as supplied":state.root+" display root"}`:" · root not interpreted"} · ${state.sort}${filterActive?` · filter ${filterCount}/${leaves.length}`:""}${selectedKeys().size?` · selected ${selectedKeys().size}`:""}${state.lassoMode?" · lasso mode":""}${declutterLabels?" · labels decluttered—zoom in to reveal":""}`;
      renderSide(tree,colorCtx);
    }
    controls.addEventListener("change",e=>{const el=e.target,name=el.dataset.c;if(!name)return;state[name]=name==="supports"?el.value==="yes":el.value;if(name==="filterTrait")state.filterValues=[];if(name==="segment"){state.viewBox=null;state.outgroup="";}if(name==="layout"||name==="root"||name==="sort")state.viewBox=null;render();});
    c("search").addEventListener("input",e=>{state.search=e.target.value;render();});
    controls.addEventListener("click",e=>{const a=e.target.dataset.a;if(!a)return;const tree=displayedTree();if(a==="lasso"){state.lassoMode=!state.lassoMode;state.drag=null;state.lasso=null;render();return;}if(a==="deselect"){clearSelection(true);render();return;}if(a==="fit"){state.viewBox=null;render();return;}if(a==="zoom-selected"){const svg=wrap.querySelector("svg"),tips=[...svg?.querySelectorAll(".ts-tip.ts-selected circle,.ts-tip.ts-multi-selected circle")||[]];if(!svg||!tips.length)return;const fw=Number(svg.dataset.fullWidth)||1500,fh=Number(svg.dataset.fullHeight)||900,points=tips.map(t=>({x:Number(t.getAttribute("cx")),y:Number(t.getAttribute("cy"))}));state.viewBox=points.length===1?API.zoomViewBoxToPoint(fw,fh,points[0].x,points[0].y,state.viewBox):API.zoomViewBoxToPoints(fw,fh,points);render();return;}if(!tree)return;const svg=wrap.querySelector("svg");if(a==="svg")API.downloadText(`${state.segment}_TreeStudio.svg`,new XMLSerializer().serializeToString(svg),"image/svg+xml");if(a==="newick")API.downloadText(`${state.segment}_TreeStudio.newick`,API.treeToNewick(tree),"text/plain");if(a==="metadata"){const localData={sampleById,referenceById,segment:state.segment};const rows=API.allLeaves(tree).map(l=>API.leafInfo(l,localData));const fields=["source","id","tip","host","genotype","collection_date","country","state","state_source","isolate","accession"];const tsv=[fields.join("\t"),...rows.map(r=>fields.map(f=>String(f==="collection_date"?r.date:f==="state_source"?r.state_raw:r[f]||"").replace(/[\t\r\n]/g," ")).join("\t"))].join("\n")+"\n";API.downloadText(`${state.segment}_TreeStudio_metadata.tsv`,tsv,"text/tab-separated-values");}if(a==="png"&&svg){const text=new XMLSerializer().serializeToString(svg), blob=new Blob([text],{type:"image/svg+xml"}),url=URL.createObjectURL(blob),img=new Image();img.onload=()=>{const canvas=document.createElement("canvas");canvas.width=2400;canvas.height=Math.max(1000,Math.round(2400*svg.viewBox.baseVal.height/svg.viewBox.baseVal.width));const ctx=canvas.getContext("2d");ctx.fillStyle="#fff";ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);URL.revokeObjectURL(url);canvas.toBlob(b=>{const u=URL.createObjectURL(b),x=document.createElement("a");x.href=u;x.download=`${state.segment}_TreeStudio.png`;x.click();setTimeout(()=>URL.revokeObjectURL(u),1000);});};img.src=url;}});
    window.addEventListener("message",e=>{const m=e.data||{};if(m.type!=="WINGS_TREE_STUDIO_SYNC"||m.session!==payload.session)return;state.selectedSampleId=m.sampleId||null;state.selectedReferenceId=m.referenceId||null;state.selectedKeys=new Set([state.selectedSampleId?`s:${state.selectedSampleId}`:state.selectedReferenceId?`r:${state.selectedReferenceId}`:null].filter(Boolean));render();});
    updateOutgroups(getTree()); render();
  }

  function safeJson(value) { return JSON.stringify(value).replace(/</g,"\\u003c").replace(/>/g,"\\u003e").replace(/&/g,"\\u0026"); }
  function wheelZoomFactor(deltaY, deltaMode=0) {
    // Trackpads can emit many tiny wheel events while traditional mouse wheels
    // emit much larger deltas. Normalize to an approximate pixel delta, cap a
    // single event, and use an exponential scale so tiny gestures stay gentle.
    const unit = deltaMode === 1 ? 16 : deltaMode === 2 ? 240 : 1;
    const pixels = Math.max(-60, Math.min(60, Number(deltaY || 0) * unit));
    return Math.exp(pixels * 0.002);
  }

  function downloadText(name,text,type="text/plain") { const blob=new Blob([text],{type}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000); }

  function apiForPopup() {
    return {VERSION, escHtml:String(escHtml), escAttr:String(escAttr)};
  }

  function bootstrapSource() {
    const names = [cloneSourceTree,annotateTree,graphFromTree,cloneGraph,replaceEdge,rootedFromGraph,farthestLeaf,pathBetween,midpointRoot,outgroupRoot,leafKey,allLeaves,leafInfo,traitValue,filterTraitValue,matchesTraitFilter,descendantHasFilterMatch,sortTree,categoricalColors,dateColor,colorContext,descendantConsensus,leafLabel,layoutRectangular,circularMean,layoutRadial,treeToNewick,numericSupport,parseDate,clean,scalarText,genotypeText,normalizeUSState,escHtml,escAttr,downloadText,wheelZoomFactor,zoomViewBoxToPoint,pointInPolygon,lassoPath,zoomViewBoxToPoints];
    return names.map(fn=>`const ${fn.name}=${fn.toString()};`).join("\n") + `\nconst SEGMENTS=${JSON.stringify(SEGMENTS)},COLORS=${JSON.stringify(COLORS)},NEUTRAL=${JSON.stringify(NEUTRAL)},LIGHT=${JSON.stringify(LIGHT)},GOLD=${JSON.stringify(GOLD)},FILTER_MISSING=${JSON.stringify(FILTER_MISSING)},US_STATE_CODES=${JSON.stringify(US_STATE_CODES)},US_STATE_CODE_SET=new Set(Object.values(US_STATE_CODES));\nconst API={VERSION:${JSON.stringify(VERSION)},cloneSourceTree,annotateTree,graphFromTree,cloneGraph,replaceEdge,rootedFromGraph,farthestLeaf,pathBetween,midpointRoot,outgroupRoot,leafKey,allLeaves,leafInfo,traitValue,filterTraitValue,matchesTraitFilter,descendantHasFilterMatch,sortTree,categoricalColors,dateColor,colorContext,descendantConsensus,leafLabel,layoutRectangular,circularMean,layoutRadial,treeToNewick,numericSupport,parseDate,clean,normalizeUSState,escHtml,escAttr,downloadText,wheelZoomFactor,zoomViewBoxToPoint,pointInPolygon,lassoPath,zoomViewBoxToPoints};`;
  }

  function openStudio(explorer, opts={}) {
    if (!explorer?.payload) throw new Error("WINGS Explorer instance is required.");
    const key=`tree-studio-${++sessionCounter}`;
    const references=Array.isArray(explorer.referenceContext?.references)?explorer.referenceContext.references:[];
    const payload={
      session:key,
      initialSegment:opts.segment||explorer.segment||"HA",
      selectedSampleId:explorer.selectedSampleId||null,
      selectedReferenceId:explorer.selectedReferenceId||null,
      data:{trees:explorer.payload.trees||{},samples:explorer.samples||[],references,segment_order:(explorer.payload.segment_order||SEGMENTS).filter(s=>explorer.payload.trees?.[s])},
    };
    const popup=window.open("","_blank","popup=yes,width=1500,height=950,resizable=yes,scrollbars=yes");
    if(!popup) throw new Error("Tree Studio pop-out was blocked by the browser.");
    sessions.set(key,{explorer,popup});
    const html=`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WINGS Tree Studio</title><style>${POPUP_CSS}</style></head><body><div id="studio"></div><script>${bootstrapSource()}\nconst payload=${safeJson(payload)};payload.api=API;(${studioBootstrap.toString()})(payload);<\/script></body></html>`;
    popup.document.open(); popup.document.write(html); popup.document.close();
    popup.addEventListener?.("beforeunload",()=>sessions.delete(key));
    return popup;
  }

  function mountExplorer(explorer) {
    if (!explorer?.root) throw new Error("Explorer instance is required.");
    if (explorer.treeStudio) return explorer.treeStudio;
    const genomeView=explorer.explorerTabs?.panels?.genome || explorer.root.querySelector("#wse-view-genome") || explorer.root.querySelector(".wse-genome-panel");
    if (!genomeView) throw new Error("Genome view not found. Install Explorer tabs or retain the genome panel.");
    const toolbar=document.createElement("div");toolbar.className="wse-tree-studio-launch";
    const copy=document.createElement("div");copy.innerHTML='<strong>Tree Studio</strong><span>Pop out any segment for dynamic phylogenetic exploration.</span>';
    const button=document.createElement("button");button.type="button";button.className="wse-tree-studio-open";button.textContent="Open Tree Studio ↗";
    toolbar.append(copy,button);genomeView.prepend(toolbar);
    button.addEventListener("click",()=>{try{openStudio(explorer,{segment:explorer.segment||"HA"});}catch(err){alert(err.message||String(err));}});
    const previous=explorer.updateSelection.bind(explorer);
    explorer.updateSelection=function(...args){const result=previous(...args);for(const [session,entry] of sessions){if(entry.explorer!==explorer||entry.popup.closed)continue;entry.popup.postMessage({type:"WINGS_TREE_STUDIO_SYNC",session,sampleId:explorer.selectedSampleId||null,referenceId:explorer.selectedReferenceId||null},"*");}return result;};
    const api={VERSION,open:(opts={})=>openStudio(explorer,opts),button};
    explorer.treeStudio=api;return api;
  }

  globalThis.window?.addEventListener?.("message", event => {
    const m=event.data||{};
    if(m.type!=="WINGS_TREE_STUDIO_SELECT"||!sessions.has(m.session))return;
    const entry=sessions.get(m.session), e=entry.explorer;
    if(m.clear){e.selectedSampleId=null;e.selectedReferenceId=null;}
    else if(m.sampleId&&e.sampleById?.has(m.sampleId)){e.selectedSampleId=m.sampleId;e.selectedReferenceId=null;}
    else if(m.referenceId&&e.referenceById?.has(m.referenceId)){e.selectedReferenceId=m.referenceId;e.selectedSampleId=null;}
    else return;
    e.hoverSampleId=null;e.updateSelection();
  });

  globalThis.WINGS_TREE_STUDIO={VERSION,open:openStudio,mountExplorer,_test:{cloneSourceTree,annotateTree,graphFromTree,midpointRoot,outgroupRoot,leafKey,allLeaves,sortTree,treeToNewick,layoutRectangular,layoutRadial,leafInfo,colorContext,descendantConsensus,genotypeText,normalizeUSState,filterTraitValue,matchesTraitFilter,descendantHasFilterMatch,wheelZoomFactor,zoomViewBoxToPoint,pointInPolygon,lassoPath,zoomViewBoxToPoints}};
})();
/* WINGS_TREE_STUDIO_JS_END */
/* WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE_UI_BEGIN */
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
/* WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE_UI_END */
/* WINGS_BRAID_CLOCK_JS_BEGIN */
/* WINGS Genome Braid + Ecological Clock v0.2.3. Offline, dependency-free. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.WINGS_BRAID_CLOCK = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const VERSION = '0.2.4';
  const SEGMENTS = ['PB2', 'PB1', 'PA', 'HA', 'NP', 'NA', 'MP', 'NS'];
  const DAY = 86400000;
  const COLORS = ['#8c1d40', '#007f84', '#80601d', '#496ea0', '#7b5a8f', '#417b62', '#b05730'];
  const text = x => x === null || x === undefined ? '' : String(x).trim();
  const keyText = x => text(x).toLowerCase().replace(/\s+/g, ' ');
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
  const pct = x => x === null ? 'Not estimable' : `${Math.round(x * 100)}%`;
  const signed = n => n > 0 ? `+${n}` : String(n);
  function strictDate(s) {
    s = text(s);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
    const [y, m, d] = s.split('-').map(Number);
    if (y < 1000 || y > 9999) return null;
    const n = Date.UTC(y, m - 1, d);
    return new Date(n).toISOString().slice(0, 10) === s ? n / DAY : null;
  }
  function dateInterval(s) {
    s = text(s);
    if (/^\d{4}$/.test(s)) {
      const start = strictDate(`${s}-01-01`), end = strictDate(`${s}-12-31`);
      return start === null ? null : {start, end, precision:'year', raw:s};
    }
    if (/^\d{4}-\d{2}$/.test(s)) {
      const start = strictDate(`${s}-01`);
      if (start === null) return null;
      const [y, m] = s.split('-').map(Number);
      return {start, end:Date.UTC(y, m, 0) / DAY, precision:'month', raw:s};
    }
    const n = strictDate(s);
    return n === null ? null : {start:n, end:n, precision:'day', raw:s};
  }
  const isoDay = d => new Date(Math.round(d) * DAY).toISOString().slice(0, 10);
  const mid = v => (v.start + v.end) / 2;
  function normalizeCountry(s) {
    const v = keyText(s);
    return ['us','usa','u.s.','u.s.a.','united states','united states of america'].includes(v) ? 'usa' : v;
  }
  function genotype(sample) {
    const v = sample.genotype;
    return text(v && typeof v === 'object' ? v.call : v) || 'Not recorded';
  }
  function model(payload) {
    if (!payload || !Array.isArray(payload.samples) || !payload.trees || typeof payload.trees !== 'object' || Array.isArray(payload.trees)) {
      throw new Error('Load a WINGS surveillance_explorer.json with samples[] and trees{}.');
    }
    const entities = new Map(), samples = [], references = [];
    for (const raw of payload.samples) {
      const id = text(raw.sample_id);
      if (!id || entities.has(`s:${id}`)) throw new Error('Sample IDs must be nonempty and unique.');
      const e = {key:`s:${id}`, id, kind:'sample', label:id, host:text(raw.host) || 'Not recorded', raw};
      entities.set(e.key, e); samples.push(e);
    }
    for (const raw of payload.public_reference_context?.references || []) {
      const id = text(raw.reference_id);
      if (!id || entities.has(`r:${id}`)) throw new Error('Public reference IDs must be nonempty and unique.');
      const e = {key:`r:${id}`, id, kind:'reference', label:text(raw.isolate) || id, host:text(raw.host) || 'Not recorded', raw};
      entities.set(e.key, e); references.push(e);
    }
    const bySegment = {}, warnings = [];
    for (const segment of SEGMENTS) {
      const source = payload.trees[segment];
      if (!source?.root) continue;
      const leaves = [], index = new Map();
      let counter = 0;
      const visited = new Set();
      // Independent copy of layout evidence. Never rotate or mutate source trees.
      const walk = (node, path, total, valid) => {
        if (!node || typeof node !== 'object' || visited.has(node)) throw new Error(`Invalid/cyclic tree: ${segment}`);
        visited.add(node);
        const nodeId = counter++;
        if (counter > 100000) throw new Error('Tree exceeds the preview node limit (100,000).');
        const isRoot = !path.length;
        const length = isRoot ? 0 : node.length;
        const edgeValid = isRoot || (finite(length) && length >= 0);
        const cumulative = total + (edgeValid ? length : 0);
        const next = path.concat({id:nodeId, distance:cumulative});
        if (Array.isArray(node.children) && node.children.length) {
          for (const child of node.children) walk(child, next, cumulative, valid && edgeValid);
        } else {
          let id = text(node.sample_id) ? `s:${text(node.sample_id)}` : text(node.reference_id) ? `r:${text(node.reference_id)}` : '';
          if (!entities.has(id)) id = '';
          const leaf = {id, name:text(node.name), order:leaves.length, path:next, distance:cumulative, valid:valid && edgeValid};
          leaves.push(leaf);
          if (id) {
            if (!index.has(id)) index.set(id, []);
            index.get(id).push(leaf);
          }
        }
      };
      walk(source.root, [], 0, true);
      for (const [id, matches] of index) if (matches.length > 1) warnings.push(`${segment}: multiple tips map to ${id}; excluded from one-to-one braid and neighborhood comparisons.`);
      bySegment[segment] = {source, leaves, index};
    }
    return {payload, entities, samples, references, bySegment, warnings};
  }
  function presence(m, id, segment) {
    const tree = m.bySegment[segment];
    if (!tree) return {status:'NO_TREE', count:0};
    const found = tree.index.get(id) || [];
    return {status:found.length === 1 ? 'PRESENT' : found.length > 1 ? 'MULTIPLE_TIPS' : 'ABSENT_FROM_TREE', count:found.length};
  }
  function distance(a, b) {
    if (!a?.valid || !b?.valid) return null;
    let shared = 0;
    for (let i = 0; i < Math.min(a.path.length, b.path.length); i++) {
      if (a.path[i].id !== b.path[i].id) break;
      shared = a.path[i].distance;
    }
    return Math.max(0, a.distance + b.distance - 2 * shared);
  }
  function nearest(tree, focal, common, k) {
    const f = tree.index.get(focal)?.[0];
    const entries = common.map(id => ({id, distance:distance(f, tree.index.get(id)?.[0])}));
    if (entries.some(v => v.distance === null)) return {status:'INVALID_LENGTHS'};
    entries.sort((a,b) => a.distance - b.distance || a.id.localeCompare(b.id));
    if (entries.length <= k) return {status:'TOO_FEW_SHARED'};
    // Reject tied cutoffs rather than resolve ties by identifier or leaf order.
    const a = entries[k-1].distance, b = entries[k].distance;
    if (Math.abs(a-b) <= 1e-10 * Math.max(1, Math.abs(a), Math.abs(b))) return {status:'TIED_CUTOFF'};
    return {status:'AVAILABLE', ids:new Set(entries.slice(0,k).map(v => v.id))};
  }
  function neighborhoodProfile(m, focal, k = 3) {
    if (!Number.isInteger(k) || k < 1) throw new Error('Neighbor count must be a positive integer.');
    if (!focal?.startsWith('s:')) return {status:'SAMPLES_ONLY', mean:null, available:0, pairs:[], k};
    const pairs = [];
    for (let a = 0; a < SEGMENTS.length; a++) for (let b = a+1; b < SEGMENTS.length; b++) {
      const x = SEGMENTS[a], y = SEGMENTS[b], tx=m.bySegment[x], ty=m.bySegment[y];
      const result = {segments:[x,y], status:'FOCAL_UNAVAILABLE', overlap:null, shared:0};
      if (presence(m,focal,x).status === 'PRESENT' && presence(m,focal,y).status === 'PRESENT') {
        const common = m.samples.map(s => s.key).filter(id => id !== focal && presence(m,id,x).status === 'PRESENT' && presence(m,id,y).status === 'PRESENT');
        result.shared = common.length;
        const nx = nearest(tx, focal, common, k), ny = nearest(ty, focal, common, k);
        result.status = nx.status !== 'AVAILABLE' ? nx.status : ny.status;
        if (result.status === 'AVAILABLE') {
          const intersection = [...nx.ids].filter(id => ny.ids.has(id)).length;
          result.overlap = intersection / (2 * k - intersection);
        }
      }
      pairs.push(result);
    }
    const values=pairs.filter(v => v.overlap !== null).map(v => v.overlap);
    return {status:values.length ? 'DESCRIPTIVE' : 'NOT_ESTIMABLE', mean:mean(values), available:values.length, pairs, k};
  }
  function validatePhenology(raw) {
    if (!raw || raw.schema_version !== 'wings.phenology.v1' || !Array.isArray(raw.profiles)) throw new Error('Phenology input requires schema_version "wings.phenology.v1" and profiles[].');
    if (typeof raw.synthetic !== 'boolean') throw new Error('Phenology input must explicitly declare synthetic: true or false.');
    const seen = new Set();
    const profiles = raw.profiles.map(p => {
      if (!text(p.profile_id) || seen.has(p.profile_id)) throw new Error('Phenology profile IDs must be unique.');
      seen.add(p.profile_id);
      for (const f of ['host','country','state']) if (!text(p.scope?.[f])) throw new Error(`${p.profile_id}: exact scope.${f} is required; no inferred location.`);
      for (const f of ['source','citation','retrieved_on','method']) if (!text(p.provenance?.[f])) throw new Error(`${p.profile_id}: provenance.${f} is required.`);
      if (strictDate(p.provenance.retrieved_on) === null) throw new Error('retrieved_on must be a valid ISO day.');
      if (!['reference_season','year_specific'].includes(p.baseline_kind)) throw new Error('baseline_kind must be reference_season or year_specific.');
      if (!text(p.measure) || !text(p.unit)) throw new Error('A phenology measure and unit are required.');
      const start = strictDate(p.season_start), end = strictDate(p.season_end);
      if (start === null || end === null || end < start) throw new Error('Invalid phenology season interval.');
      if (!Array.isArray(p.bins)) throw new Error('Phenology bins must be an array.');
      let previous = start-1;
      const bins = p.bins.map(bin => {
        const s = strictDate(bin.start), e = strictDate(bin.end);
        if (s === null || e === null || s > e || s <= previous || s < start || e > end) throw new Error(`${p.profile_id}: bins must be ordered, nonoverlapping ISO-day intervals inside the season.`);
        if (bin.value !== null && (!finite(bin.value) || bin.value < 0)) throw new Error('Bin value must be a nonnegative number or null.');
        previous = e;
        return {...bin, s, e};
      });
      let anchor;
      if (p.anchor) {
        const early = strictDate(p.anchor.earliest), late = strictDate(p.anchor.latest);
        if (early === null || late === null || early > late || early < start || late > end || !text(p.anchor.label) || !text(p.anchor.basis)) throw new Error('A supplied anchor requires a valid interval, label, and documented basis.');
        anchor={status:'AVAILABLE', start:early, end:late, label:p.anchor.label, basis:p.anchor.basis, method:'supplied'};
      } else anchor=deriveAnchor(bins);
      return {...p, start, end, bins, anchor};
    });
    return {...raw, profiles};
  }
  function deriveAnchor(bins) {
    const valid=bins.filter(b => b.value !== null);
    if (valid.length < 3) return {status:'INSUFFICIENT_BINS'};
    const max=Math.max(...valid.map(b=>b.value));
    if (max <= 0) return {status:'NO_POSITIVE_VALUES'};
    const peaks=valid.filter(b=>Math.abs(b.value-max) < 1e-12);
    if (peaks.length === valid.length) return {status:'FLAT_PROFILE'};
    if (peaks.some((b,i)=>i>0 && b.s !== peaks[i-1].e+1)) return {status:'AMBIGUOUS_PEAK'};
    return {status:'AVAILABLE', start:peaks[0].s, end:peaks.at(-1).e, label:'Peak supplied bin', basis:'Maximum of supplied nonmissing bins; interval is temporal resolution, not a confidence interval.', method:'maximum_bin'};
  }
  function shiftDayYear(day, delta) {
    const d=new Date(Math.round(day)*DAY), y=d.getUTCFullYear()+delta, m=d.getUTCMonth(), dom=d.getUTCDate();
    let shifted=Date.UTC(y,m,dom)/DAY;
    const chk=new Date(Math.round(shifted)*DAY);
    if(chk.getUTCMonth()!==m) shifted=Date.UTC(y,m+1,0)/DAY; // Feb 29 -> Feb 28 in non-leap years.
    return shifted;
  }
  function nearestAnnualAnchor(date, anchor, baselineKind) {
    if (baselineKind !== 'reference_season' || anchor.status !== 'AVAILABLE') return anchor;
    const target=mid(date);
    const candidates=[-1,0,1].map(delta=>({...anchor,start:shiftDayYear(anchor.start,delta),end:shiftDayYear(anchor.end,delta),year_shift:delta}));
    return candidates.reduce((best,candidate)=>Math.abs(mid(candidate)-target)<Math.abs(mid(best)-target)?candidate:best,candidates[0]);
  }
  function phenologyStatusForSample(sample, phenology) {
    const sid=keyText(sample.sample_id || sample.sample);
    if (!sid || !Array.isArray(phenology?.sample_status)) return null;
    return phenology.sample_status.find(r=>keyText(r.sample_id)===sid) || null;
  }
  function clockRecord(sample, phenology) {
    const date=dateInterval(sample.collection_date);
    if (!date) return {status:'NO_COLLECTION_DATE'};
    if (!phenology) return {status:'NO_PHENOLOGY'};
    const sid=keyText(sample.sample_id || sample.sample);
    const direct=phenology.profiles.filter(p => text(p.sample_id) && keyText(p.sample_id)===sid && date.start >= p.start && date.end <= p.end);
    if (direct.length > 1) return {status:'AMBIGUOUS_PROFILE', date};
    let exact=direct;
    if (!exact.length) {
      exact=phenology.profiles.filter(p => !text(p.sample_id) && keyText(p.scope.host) === keyText(sample.host) && normalizeCountry(p.scope.country) === normalizeCountry(sample.country) && keyText(p.scope.state) === keyText(sample.state) && date.start >= p.start && date.end <= p.end);
    }
    if (!exact.length) {
      const supplied=phenologyStatusForSample(sample,phenology);
      return supplied ? {status:supplied.status||'NO_MATCHING_PROFILE', reason:supplied.reason||'', date, supplied} : {status:'NO_MATCHING_PROFILE', date};
    }
    if (exact.length !== 1) return {status:'AMBIGUOUS_PROFILE', date};
    const profile=exact[0], anchor=nearestAnnualAnchor(date,profile.anchor,profile.baseline_kind);
    if (anchor.status !== 'AVAILABLE') return {status:anchor.status, date, profile};
    const lower=date.start-anchor.end, upper=date.end-anchor.start;
    return {status:'AVAILABLE', date, profile, anchor, lower, upper, midpoint:(lower+upper)/2};
  }
  function lagText(record) {
    if (record.status !== 'AVAILABLE') return record.status.toLowerCase().replace(/_/g,' ');
    if (record.upper < 0) { const near=Math.abs(record.upper), far=Math.abs(record.lower); return near===far ? `${near} days before expected peak` : `${near}–${far} days before expected peak`; }
    if (record.lower > 0) { const near=Math.abs(record.lower), far=Math.abs(record.upper); return near===far ? `${near} days after expected peak` : `${near}–${far} days after expected peak`; }
    return 'Overlaps expected peak interval';
  }
  function svg(name, attrs, contents) {
    const n=document.createElementNS('http://www.w3.org/2000/svg',name);
    for (const [k,v] of Object.entries(attrs || {})) n.setAttribute(k,String(v));
    if (contents !== undefined) n.textContent=String(contents);
    return n;
  }
  function buttonNode(n, label, action) {
    n.setAttribute('role','button'); n.setAttribute('tabindex','0'); n.setAttribute('aria-label',label);
    n.addEventListener('click', action);
    n.addEventListener('keydown', e => {if (e.key==='Enter'||e.key===' ') {e.preventDefault();action();}});
    n.appendChild(svg('title',{},label));
    return n;
  }
  class Dashboard {
    constructor(root, payload, options={}) {
      this.root=root; this.options=options; this.payload=payload; this.m=model(payload);
      this.selected=null; this.selectedReference=null; this.host='ALL'; this.includeReferences=false; this.mode='calendar'; this.clockView='selected'; this.k=3;
      this.phenology=payload.ecological_clock ? validatePhenology(payload.ecological_clock) : null;
      this.cache=new Map(); this.notice='';
      this.build(); this.refresh();
    }
    color(e) { return e.kind === 'reference' ? '#00828a' : COLORS[this.m.samples.map(s=>s.host).filter((h,i,a)=>a.indexOf(h)===i).indexOf(e.host)%COLORS.length]; }
    build() {
      this.root.classList.add('wbc');
      this.root.innerHTML=`
        <header class="wbc-masthead"><div><span class="wbc-overline">WINGS / OBSERVATORY</span><h2>Eight segments. One ecological story.</h2><p>Follow the same record through the genome. Read its collection date against the bird's seasonal clock.</p></div><span class="wbc-release">RESEARCH PREVIEW <b>v${VERSION}</b></span></header>
        <div class="wbc-banner" role="status"></div>
        <div class="wbc-tools"><label>Focus sample<select class="wbc-sample" aria-label="Braid focus sample"></select></label><label>Host<select class="wbc-host" aria-label="Braid host filter"></select></label><button type="button" class="wbc-clear">Clear focus</button><div class="wbc-file-tools"><label class="wbc-file-button" tabindex="0">Load / override phenology<input class="wbc-import-phenology" type="file" accept=".json,application/json"></label><button type="button" class="wbc-export">Export evidence</button></div></div>
        <div class="wbc-stats"></div>
        <div class="wbc-workbench"><div class="wbc-card wbc-braid-card"><div class="wbc-card-title"><div><span class="wbc-kicker">01 / GENOME BRAID</span><h3>One identity, eight views</h3></div><label class="wbc-checkbox"><input type="checkbox" class="wbc-references"> Show public links</label></div><div class="wbc-braid-scroll"><div class="wbc-braid"></div></div><div class="wbc-braid-caption"></div><details class="wbc-method"><summary>What the braid does and does not mean</summary><p>Vertical position follows tip order in each supplied tree, restricted to displayed identities. Rotating a tree can change crossings without changing its relationships. Crossings are not a reassortment statistic or a route of transmission. Lines only join adjacent lanes with one unambiguous tip; gaps remain gaps.</p><p>Public records are joined only by supplied reference_id. A metadata-derived linkage remains a candidate, not verified common-specimen identity. Public groups do not enter the sample-neighborhood metric.</p></details></div>
        <div class="wbc-card wbc-focus"><span class="wbc-kicker">EVIDENCE / SELECT A RECORD</span><div class="wbc-evidence" aria-live="polite"></div></div></div>
        <section class="wbc-card wbc-clock-card"><div class="wbc-card-title"><div><span class="wbc-kicker">02 / ECOLOGICAL CLOCK</span><h3>Same observation. A different time axis.</h3></div><div><div class="wbc-switch" role="group" aria-label="Clock time axis"><button type="button" data-wbc-mode="calendar" aria-pressed="true">Calendar</button><button type="button" data-wbc-mode="ecological" aria-pressed="false">Ecological time</button></div><div class="wbc-switch" role="group" aria-label="Clock records" style="margin-top:.45rem"><button type="button" data-wbc-clock-view="selected" aria-pressed="true">Selected sample</button><button type="button" data-wbc-clock-view="compare" aria-pressed="false">Compare samples</button></div></div></div><p class="wbc-clock-subtitle"></p><div class="wbc-clock-scroll"><div class="wbc-clock"></div></div><div class="wbc-clock-caption"></div><details class="wbc-method"><summary>Phenology matching, precision, and provenance</summary><p>The clock uses an exact supplied host, country, state, and season match. No species is inferred from a host code. Missing or ambiguous profiles remain unavailable. Collection date is not infection date. Expected seasonal profiles are labeled separately from year-specific estimates.</p><p>Offset interval = [collection start - anchor latest, collection end - anchor earliest]. An interval from a weekly peak bin describes temporal resolution, not a statistical confidence interval. Empty bins are not zero; curves are never extended through missing observations.</p><div class="wbc-provenance"></div></details></section>
        <details class="wbc-card wbc-audit"><summary>Inspect the evidence table</summary><div class="wbc-evidence-table"></div></details>
        <footer class="wbc-footer">Exploratory description, not a risk score. No transmission, reassortment, infection timing, or causal climate effect is inferred. Files stay in this browser; no data are uploaded.</footer>`;
      const q=s=>this.root.querySelector(s);
      q('.wbc-sample').innerHTML='<option value="">Select a sample</option>'+this.m.samples.map(e=>`<option value="${esc(e.id)}">${esc(e.id)}</option>`).join('');
      q('.wbc-host').innerHTML='<option value="ALL">All hosts</option>'+[...new Set(this.m.samples.map(e=>e.host))].map(h=>`<option>${esc(h)}</option>`).join('');
      q('.wbc-sample').addEventListener('change',e=>this.choose(e.target.value ? `s:${e.target.value}` : null, false));
      q('.wbc-host').addEventListener('change',e=>{this.host=e.target.value;this.options.onHost?.(this.host);this.refresh();});
      q('.wbc-clear').addEventListener('click',()=>this.choose(null,false));
      q('.wbc-references').addEventListener('change',e=>{this.includeReferences=e.target.checked;this.refresh();});
      this.root.querySelectorAll('[data-wbc-mode]').forEach(b=>b.addEventListener('click',()=>{this.mode=b.dataset.wbcMode;this.renderClock();}));
      this.root.querySelectorAll('[data-wbc-clock-view]').forEach(b=>b.addEventListener('click',()=>{this.clockView=b.dataset.wbcClockView;this.renderClock();}));
      q('.wbc-import-phenology').addEventListener('change',async e=>{
        const f=e.target.files[0]; if (!f) return;
        try {if(f.size>20000000) throw new Error('Phenology file exceeds the 20 MB preview limit.');this.phenology=validatePhenology(JSON.parse(await f.text()));this.notice=`Loaded ${f.name} locally. This import is session-only in an embedded Explorer.`;this.refresh();}
        catch(error){this.notice=`Phenology not loaded: ${error.message}`;this.renderBanner();}
        e.target.value='';
      });
      q('.wbc-file-button').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();q('.wbc-import-phenology').click();}});
      q('.wbc-export').addEventListener('click',()=>this.exportEvidence());
    }
    choose(id, toggle=true) {
      if (id && !this.m.entities.has(id)) return;
      if (this.options.onSelect) {this.options.onSelect(id, toggle);return;}
      if (id?.startsWith('r:')) this.selectedReference=toggle && this.selectedReference===id ? null : id;
      else {this.selected=toggle&&this.selected===id?null:id;this.selectedReference=null;}
      this.refresh();
    }
    sync(state) {
      this.selected=state.sample ? `s:${state.sample}` : null;
      this.selectedReference=state.reference ? `r:${state.reference}` : null;
      this.host=state.host || 'ALL'; this.refresh();
    }
    profile(id) {if (!this.cache.has(`${id}|${this.k}`)) this.cache.set(`${id}|${this.k}`,neighborhoodProfile(this.m,id,this.k));return this.cache.get(`${id}|${this.k}`);}
    visible() {return this.m.samples.filter(e=>this.host==='ALL'||e.host===this.host);}
    renderBanner() {
      const synthetic=this.payload.synthetic===true || this.phenology?.synthetic===true;
      const node=this.root.querySelector('.wbc-banner');
      node.classList.toggle('wbc-is-synthetic',synthetic);
      node.textContent=[synthetic ? 'SYNTHETIC DEMONSTRATION - illustrative tree geometry and/or seasonal profiles; not surveillance findings.' : 'Local Explorer data - existing trees are displayed without rerooting or reinference.',this.notice].filter(Boolean).join(' ');
    }
    refresh() {
      this.renderBanner();
      this.root.querySelector('.wbc-sample').value=this.selected?.slice(2)||'';
      this.root.querySelector('.wbc-host').value=this.host;
      const mapped=this.m.samples.filter(e=>clockRecord(e.raw,this.phenology).status==='AVAILABLE').length;
      const pairInfo=this.selected ? this.profile(this.selected):null;
      this.root.querySelector('.wbc-stats').innerHTML=[['LOCAL SAMPLES',this.m.samples.length,'Identities, not deduplicated specimens'],['SEGMENT TREES',`${Object.keys(this.m.bySegment).length} / 8`,'Supplied tree geometry'],['PHENOLOGY MATCHES',`${mapped} / ${this.m.samples.length}`,'Point or regional seasonal profile'],['SHARED-NEIGHBOR OVERLAP',pairInfo?.mean!==null&&pairInfo ? pct(pairInfo.mean):'Select a sample',pairInfo ? `${pairInfo.available} / 28 available comparisons`:'Descriptive; local sample cohort only']].map(([a,b,c])=>`<div><span>${esc(a)}</span><strong>${esc(b)}</strong><small>${esc(c)}</small></div>`).join('');
      this.renderBraid();this.renderEvidence();this.renderClock();this.renderTable();
    }
    renderBraid() {
      const target=this.root.querySelector('.wbc-braid');target.replaceChildren();
      let ids=this.visible().map(e=>e.key);
      if (this.selected&&!ids.includes(this.selected)) ids.push(this.selected);
      // Bound rendering without sampling the analytical cohort. Always retain focus.
      const totalLocal=ids.length;
      ids=ids.slice(0,60);
      if (this.selected&&!ids.includes(this.selected)) ids.push(this.selected);
      if (this.includeReferences) ids.push(...this.m.references.slice(0,36).map(e=>e.key));
      if (this.selectedReference&&!ids.includes(this.selectedReference)) ids.push(this.selectedReference);
      const W=980,H=Math.max(320,Math.min(620,ids.length*12+105)),left=45,right=45,top=58,bottom=34;
      const el=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'group','aria-label':'Genome Braid. Lines connect the same supplied identity across segment trees.'});
      const positions={};
      SEGMENTS.forEach((segment,i)=>{
        const x=left+i*(W-left-right)/7,tree=this.m.bySegment[segment];
        const lane=svg('g',{});
        lane.append(svg('line',{x1:x,y1:top-8,x2:x,y2:H-bottom,stroke:'#d7dce1','stroke-dasharray':tree?'none':'4 4'}));
        lane.append(svg('text',{x,y:24,'text-anchor':'middle',class:'wbc-lane-label'},segment));
        const inLane=ids.filter(id=>presence(this.m,id,segment).status==='PRESENT').sort((a,b)=>tree.index.get(a)[0].order-tree.index.get(b)[0].order);
        positions[segment]=new Map(inLane.map((id,j)=>[id,{x,y:top+(j+0.5)*(H-top-bottom)/Math.max(inLane.length,1)}]));
        lane.append(svg('text',{x,y:42,'text-anchor':'middle',class:'wbc-small'},tree?`${inLane.length} shown`:'No tree'));
        el.append(lane);
      });
      const focused=this.selectedReference||this.selected;
      const ordered=ids.slice().sort((a,b)=>Number(a===focused)-Number(b===focused));
      for(const id of ordered){
        const e=this.m.entities.get(id);if(!e)continue;
        const active=id===this.selected||id===this.selectedReference;
        const group=svg('g',{'data-wbc-entity':id,class:`wbc-strand${active?' wbc-active':''}`,'aria-pressed':String(active)});
        for(let i=0;i<7;i++){
          const a=positions[SEGMENTS[i]].get(id),b=positions[SEGMENTS[i+1]].get(id);if(!a||!b)continue;
          const dx=(b.x-a.x)*0.43;
          group.append(svg('path',{d:`M ${a.x} ${a.y} C ${a.x+dx} ${a.y}, ${b.x-dx} ${b.y}, ${b.x} ${b.y}`,fill:'none',stroke:this.color(e),'stroke-width':active?3.5:e.kind==='reference'?1.1:1.6,opacity:focused&&!active?0.15:e.kind==='reference'?0.38:0.62}));
        }
        for(const segment of SEGMENTS){const p=positions[segment].get(id);if(!p)continue;
          const attrs={fill:this.color(e),stroke:active?'#fff':'none','stroke-width':1.6};
          group.append(e.kind==='reference'?svg('rect',{x:p.x-4,y:p.y-4,width:8,height:8,...attrs}):svg('circle',{cx:p.x,cy:p.y,r:active?5:3,...attrs}));
        }
        buttonNode(group,`${e.kind==='sample'?'Sample':'Public reference'} ${e.label}. ${SEGMENTS.filter(s=>presence(this.m,id,s).status==='PRESENT').length} of 8 segment trees.`,()=>this.choose(id));
        el.append(group);
      }
      target.append(el);
      const outside=this.selected&&this.host!=='ALL'&&this.m.entities.get(this.selected)?.host!==this.host;
      this.root.querySelector('.wbc-braid-caption').innerHTML=`<span class="wbc-dot"></span> Circles: WINGS samples &nbsp; <span class="wbc-square"></span> Squares: public groups as supplied. Gaps: no unambiguous tip.<br><small>${esc(outside?'Selected sample is outside the host filter and remains visible. ': '')}${totalLocal>60?`Showing up to 60 of ${totalLocal} local samples plus focus. `:''}${this.includeReferences?`Showing up to 36 public groups in source order, plus focus. `:''}Tip order is a layout choice, not evolutionary distance.</small>`;
    }
    renderEvidence() {
      const id=this.selectedReference||this.selected,e=this.m.entities.get(id),target=this.root.querySelector('.wbc-evidence');
      if(!e){target.innerHTML='<div class="wbc-empty-focus"><span class="wbc-focus-icon">8</span><h3>Follow one record</h3><p>Select a strand or use the sample menu. The braid and clock share one focus.</p><p>Nothing is scored simply because two strands cross.</p></div>';return;}
      const c=e.kind==='sample'?clockRecord(e.raw,this.phenology):{status:'PUBLIC_CLOCK_NOT_COMPUTED'}, p=e.kind==='sample'?this.profile(id):null;
      const count=SEGMENTS.filter(s=>presence(this.m,id,s).status==='PRESENT').length;
      const matrix=SEGMENTS.map(a=>`<tr><th>${a}</th>${SEGMENTS.map(b=>{if(a===b)return '<td class="wbc-diagonal">-</td>';const pair=p?.pairs.find(v=>v.segments.includes(a)&&v.segments.includes(b));return `<td title="${esc(pair?`${pair.status}; ${pair.shared} shared comparison samples`:'Not computed')}">${pair?.overlap!==null&&pair?.overlap!==undefined?Math.round(pair.overlap*100):'&middot;'}</td>`;}).join('')}</tr>`).join('');
      target.innerHTML=`<h3 class="wbc-focus-name">${esc(e.label)}</h3><p>${esc(e.host)}<br>${esc(e.raw.collection_date||'Date not recorded')} &middot; ${esc(e.raw.state||e.raw.country||'Place not recorded')}</p><div class="wbc-chips"><span>${esc(e.kind==='sample'?genotype(e.raw):'Public group')}</span><span>${count} / 8 trees</span></div><div class="wbc-presence">${SEGMENTS.map(s=>`<span class="${presence(this.m,id,s).status==='PRESENT'?'wbc-present':''}" title="${esc(presence(this.m,id,s).status)}">${s}</span>`).join('')}</div><h4>Ecological timing</h4><div class="wbc-lag">${esc(c.status==='AVAILABLE'?lagText(c):'Unavailable')}</div><p class="wbc-muted">${esc(c.status==='AVAILABLE'?`Relative to ${c.anchor.label.toLowerCase()}. ${c.profile.baseline_kind==='reference_season'?'Expected seasonal reference; not realized migration timing.':'Year-specific supplied profile.'}`:lagText(c))}</p>${p?`<h4>Shared-neighbor overlap</h4><strong class="wbc-score">${pct(p.mean)}</strong><p class="wbc-muted">${p.available} of 28 segment-pair comparisons available. Three nearest other WINGS samples, evaluated on the shared identities for each pair.</p><details><summary>Comparison matrix (%)</summary><div class="wbc-matrix-scroll"><table class="wbc-matrix"><thead><tr><th></th>${SEGMENTS.map(s=>`<th>${s}</th>`).join('')}</tr></thead><tbody>${matrix}</tbody></table></div><p class="wbc-muted">Mean Jaccard overlap; unavailable and tied-cutoff pairs are omitted, not scored zero. This is descriptive, not a support probability, validated concordance score, or reassortment test. No tree-support threshold is applied.</p></details>`:`<p class="wbc-muted">Linkage basis: ${esc(e.raw.linkage_basis||'Not recorded')}. Public groups are not included in the sample-neighborhood score.</p>`}`;
    }
    renderClock() {
      this.root.querySelectorAll('[data-wbc-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.wbcMode===this.mode)));
      this.root.querySelectorAll('[data-wbc-clock-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.wbcClockView===this.clockView)));
      const target=this.root.querySelector('.wbc-clock');target.replaceChildren();
      const subtitle=this.root.querySelector('.wbc-clock-subtitle'),caption=this.root.querySelector('.wbc-clock-caption');
      const visible=this.visible(),allRecords=visible.map(e=>({entity:e,c:clockRecord(e.raw,this.phenology)}));
      if(this.selected&&!visible.some(e=>e.key===this.selected)){const e=this.m.entities.get(this.selected);if(e)allRecords.push({entity:e,c:clockRecord(e.raw,this.phenology)});}
      let records=allRecords;
      if(this.clockView==='selected'){
        if(!this.selected||this.selectedReference){
          subtitle.textContent='Select a WINGS sample to place its collection date on the host seasonal curve.';
          target.innerHTML='<div class="wbc-no-data"><h4>Select a sample</h4><p>The default clock shows one WINGS sample at a time. Use Compare samples when you want to inspect multiple profiles together.</p></div>';
          caption.textContent='No sample is currently selected. Nothing is inferred from the cohort until you choose Compare samples.';
          this.renderProvenance([]);return;
        }
        const selectedEntity=this.m.entities.get(this.selected);
        records=selectedEntity?[{entity:selectedEntity,c:clockRecord(selectedEntity.raw,this.phenology)}]:[];
      }
      const available=records.filter(r=>r.c.status==='AVAILABLE');
      const profiles=[...new Map(available.map(r=>[r.c.profile.profile_id,r.c.profile])).values()];
      if(!profiles.length){
        const r=records[0];
        const detail=r?.c?.reason||lagText(r?.c||{status:'NO_MATCHING_PROFILE'});
        subtitle.textContent=this.mode==='calendar'?(this.clockView==='selected'&&r?`${r.entity.id} · ${r.entity.raw.collection_date||'date unavailable'} · phenology unavailable (${detail}).`:'Collection dates remain visible without a seasonal anchor.'):'Ecological time is unavailable until a matching phenology profile is supplied.';
        if(this.mode==='calendar'&&records.length)this.renderCalendarOnly(target,records);
        else target.innerHTML='<div class="wbc-no-data"><h4>No defensible seasonal anchor yet</h4><p>A matching Status & Trends profile is required. Missing geography or model coverage remains explicitly unavailable rather than being converted into a synthetic point estimate.</p></div>';
        caption.textContent=`${records.length} sample record${records.length===1?'':'s'}; 0 assigned an ecological offset. Missing information is not zero.`;
        this.renderProvenance([]);return;
      }
      const spatialText=p=>p.spatial?.method==='POINT'?'point-specific 27-km cell':p.spatial?.method==='REGIONAL_STATE_MEAN'?'state regional mean':'supplied spatial profile';
      const versionText=p=>text(p.status_version_year)||(text(p.provenance?.source).match(/(?:Version\s*)?(\d{4})/)||[])[1]||'version not recorded';
      if(this.clockView==='selected'){
        const r=available[0],p=r.profile||r.c.profile;
        subtitle.textContent=`${r.entity.id} · collection ${r.entity.raw.collection_date} · Status week ${p.collection?.status_week??'not available'} · ${spatialText(p)}.`;
      } else {
        subtitle.textContent=this.mode==='calendar'?'Compare collection dates against expected seasonal profiles.':'Compare samples after centering each profile on its own expected seasonal anchor.';
      }
      let shown=this.clockView==='selected'?profiles.slice(0,1):profiles.slice(0,8);
      const focus=records.find(r=>r.entity.key===this.selected)?.c.profile;
      if(this.clockView==='compare'&&focus&&!shown.includes(focus)){shown=shown.slice(0,7).concat(focus);}
      const W=1340,left=310,right=40,rowH=106,top=36,H=top+shown.length*rowH+48;
      const ranges=shown.flatMap(p=>this.mode==='calendar'?[p.start,p.end]:[p.start-mid(p.anchor),p.end-mid(p.anchor)]);
      let low=Math.min(...ranges),high=Math.max(...ranges);if(high===low)high++;
      const x=n=>left+(n-low)/(high-low)*(W-left-right);
      const el=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'group','aria-label':`Ecological Clock, ${this.mode} axis, ${this.clockView} view`});
      for(let i=0;i<=5;i++){const v=low+(high-low)*i/5;const label=this.mode==='calendar'?isoDay(v):`${signed(Math.round(v))} d`;el.append(svg('line',{x1:x(v),x2:x(v),y1:top-10,y2:H-35,stroke:'#e4e8eb'}),svg('text',{x:x(v),y:H-12,'text-anchor':'middle',class:'wbc-tick'},label));}
      shown.forEach((p,i)=>{
        const y=top+i*rowH,base=y+66;
        const anchorMid=mid(p.anchor),off=this.mode==='calendar'?0:anchorMid;
        const peakX=x(p.anchor.start-off),peakEnd=x(p.anchor.end-off);
        el.append(svg('rect',{x:peakX,y:y-7,width:Math.max(2,peakEnd-peakX),height:80,fill:'#efddb1',opacity:.55}));
        const common=text(p.species?.common_name)||p.scope.host;
        const place=text(p.spatial?.state_name)||p.scope.state;
        const basis=p.spatial?.method==='POINT'?`${place} · point-specific expected season`:p.spatial?.method==='REGIONAL_STATE_MEAN'?`${place} · state regional mean`:`${place} · expected season`;
        el.append(svg('text',{x:14,y:y+14,class:'wbc-row-title'},common),svg('text',{x:14,y:y+33,class:'wbc-small'},`${p.scope.host} · ${basis}`));
        el.append(svg('text',{x:14,y:y+51,class:'wbc-small'},`eBird S&T ${versionText(p)} · median weekly relative abundance`));
        const max=Math.max(1e-10,...p.bins.filter(b=>b.value!==null).map(b=>b.value));
        for(const b of p.bins){if(b.value===null)continue;const height=b.value/max*45;const rect=svg('rect',{x:x(b.s-off),y:base-height,width:Math.max(1,x(b.e+1-off)-x(b.s-off)-1),height,fill:'#70b0b2',opacity:.48});rect.append(svg('title',{},`${b.start} to ${b.end}: ${b.value} ${p.unit}`));el.append(rect);}
        el.append(svg('line',{x1:left,x2:W-right,y1:base,y2:base,stroke:'#a9b4bd'}));
        const cohort=available.filter(r=>r.c.profile.profile_id===p.profile_id);
        cohort.forEach((r,j)=>{
          const c=r.c,s=this.mode==='calendar'?c.date.start:c.lower,e=this.mode==='calendar'?c.date.end:c.upper;
          const yy=base+13+(j%2)*9,active=r.entity.key===this.selected;
          const mark=svg('g',{'data-wbc-clock-sample':r.entity.id,class:active?'wbc-clock-active':''});
          mark.append(svg('line',{x1:x(s),x2:x(e),y1:yy,y2:yy,stroke:this.color(r.entity),'stroke-width':3}));
          mark.append(svg('circle',{cx:x((s+e)/2),cy:yy,r:active?7:4.5,fill:this.color(r.entity),stroke:active?'#f4c652':'#fff','stroke-width':active?3:1}));
          buttonNode(mark,`${r.entity.id}: ${r.entity.raw.collection_date}; Status week ${p.collection?.status_week??'not available'}; ${spatialText(p)}; ${lagText(c)} relative to ${c.anchor.label}`,()=>this.choose(r.entity.key));el.append(mark);
        });
      });
      if(this.mode==='ecological'&&low<=0&&high>=0)el.append(svg('line',{x1:x(0),x2:x(0),y1:15,y2:H-35,stroke:'#8f691e','stroke-dasharray':'4 5'}),svg('text',{x:x(0),y:12,'text-anchor':'middle',class:'wbc-anchor-label'},'Seasonal anchor'));
      target.append(el);
      if(this.clockView==='selected'){
        const p=shown[0];
        caption.textContent=`Selected-sample view. ${spatialText(p)}. Bars are scaled within this profile. Gold band is the WINGS-derived expected relative-abundance peak interval, not an infection window or confidence interval.`;
      } else {
        caption.textContent=`${available.length} / ${records.length} visible sample records have an exact profile match. ${records.length-available.length} remain unavailable in ecological time. ${profiles.length>8?'Showing at most 8 profile rows plus selected focus. ':''}Bars are scaled within each profile; heights are not comparable abundance between hosts. Gold bands show anchor intervals, not infection windows.`;
      }
      this.renderProvenance(shown);
    }
    renderCalendarOnly(target,records) {
      const dated=records.filter(r=>r.c.date||dateInterval(r.entity.raw.collection_date));
      if(!dated.length){target.innerHTML='<div class="wbc-no-data">No valid collection dates are available.</div>';return;}
      const data=dated.map(r=>({...r,date:r.c.date||dateInterval(r.entity.raw.collection_date)})),W=1100,H=120,left=32,right=32;
      const low=Math.min(...data.map(r=>r.date.start))-7,high=Math.max(...data.map(r=>r.date.end))+7,x=n=>left+(n-low)/(high-low)*(W-left-right);
      const el=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'group','aria-label':'Collection dates without phenology anchors'});
      el.append(svg('line',{x1:left,x2:W-right,y1:65,y2:65,stroke:'#bec8ce'}));
      data.forEach((r,i)=>{const y=40+(i%3)*13,g=svg('g',{});g.append(svg('line',{x1:x(r.date.start),x2:x(r.date.end),y1:y,y2:y,stroke:this.color(r.entity),'stroke-width':3}),svg('circle',{cx:x(mid(r.date)),cy:y,r:5,fill:this.color(r.entity)}));buttonNode(g,`${r.entity.id}; ${r.date.raw}`,()=>this.choose(r.entity.key));el.append(g);});
      for(let i=0;i<=4;i++){const d=low+(high-low)*i/4;el.append(svg('text',{x:x(d),y:97,'text-anchor':'middle',class:'wbc-small'},isoDay(d)));}
      target.append(el);
    }
    renderProvenance(profiles) {
      this.root.querySelector('.wbc-provenance').innerHTML=profiles.length?profiles.map(p=>`<p><b>${esc(p.profile_id)}</b> &middot; ${esc(p.provenance.source)}<br>${esc(p.provenance.citation)}<br>Retrieved ${esc(p.provenance.retrieved_on)}. ${esc(p.provenance.method)}<br>Anchor: ${esc(p.anchor.label)} (${isoDay(p.anchor.start)} to ${isoDay(p.anchor.end)}). ${esc(p.anchor.basis)}</p>`).join(''):'<p>No matching phenology source has been loaded. No seasonal timing has been inferred.</p>';
    }
    evidenceRows() {
      return this.m.samples.map(e=>{const c=clockRecord(e.raw,this.phenology);return {sample_id:e.id,host:e.host,collection_date:text(e.raw.collection_date),genotype:genotype(e.raw),tree_presence:Object.fromEntries(SEGMENTS.map(s=>[s,presence(this.m,e.key,s).status])),clock_status:c.status,profile_id:c.profile?.profile_id||null,baseline_kind:c.profile?.baseline_kind||null,offset_min_days:c.lower??null,offset_max_days:c.upper??null};});
    }
    renderTable() {
      this.root.querySelector('.wbc-evidence-table').innerHTML='<table><thead><tr><th>Sample</th><th>Host</th><th>Collection date</th><th>Clock status</th><th>Offset interval (days)</th></tr></thead><tbody>'+this.evidenceRows().map(r=>`<tr><td>${esc(r.sample_id)}</td><td>${esc(r.host)}</td><td>${esc(r.collection_date)}</td><td>${esc(r.clock_status)}</td><td>${r.offset_min_days===null?'Not available':`${signed(r.offset_min_days)} to ${signed(r.offset_max_days)}`}</td></tr>`).join('')+'</tbody></table>';
    }
    exportEvidence() {
      const report={schema_version:'wings.braid-clock-evidence.v1',version:VERSION,input_provenance:this.payload.braid_clock_build||null,synthetic:this.payload.synthetic===true||this.phenology?.synthetic===true,samples:this.evidenceRows(),focused_neighborhood:this.selected?this.profile(this.selected):null,tree_sources:Object.fromEntries(Object.entries(this.m.bySegment).map(([s,t])=>[s,{file:t.source.source_file||null,sha256:t.source.source_sha256||null}])),phenology:this.phenology?{synthetic:this.phenology.synthetic,profiles:this.phenology.profiles.map(p=>({profile_id:p.profile_id,provenance:p.provenance,anchor:p.anchor}))}:null,warnings:this.m.warnings,limitations:['Descriptive overlap is not a reassortment test, support probability, or risk score.','Phenology offsets concern collection timing, not infection timing.','Source identities are not automatically deduplicated biological specimens.']};
      const blob=new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='wings-braid-clock-evidence.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
  }
  function mount(root,payload,options) {return new Dashboard(root,payload,options);}
  function mountExplorer(explorer) {
    if(explorer.braidClock)return explorer.braidClock;
    const parent=explorer.root.querySelector('.wse-shell')||explorer.root;
    const host=document.createElement('section');host.className='wbc-embedded';
    parent.insertBefore(host,parent.querySelector('.wse-genome-panel'));
    const update=explorer.updateSelection.bind(explorer);
    const app=mount(host,explorer.payload,{
      onSelect:(id,toggle)=>{
        if(!id){explorer.selectedSampleId=null;explorer.selectedReferenceId=null;}
        else if(id.startsWith('s:')){const sid=id.slice(2);explorer.selectedSampleId=toggle&&explorer.selectedSampleId===sid?null:sid;explorer.selectedReferenceId=null;}
        else {const rid=id.slice(2);explorer.selectedReferenceId=toggle&&explorer.selectedReferenceId===rid?null:rid;}
        explorer.hoverSampleId=null;explorer.updateSelection();
      },
      onHost:host=>{explorer.hostFilter=host;explorer.renderTimeline();explorer.renderMap();explorer.renderLegend();explorer.renderTrees();explorer.updateSelection();}
    });
    explorer.updateSelection=function(...args){const result=update(...args);app.sync({sample:this.selectedSampleId,reference:this.selectedReferenceId,host:this.hostFilter});return result;};
    explorer.braidClock=app;
    app.sync({sample:explorer.selectedSampleId,reference:explorer.selectedReferenceId,host:explorer.hostFilter});
    return app;
  }
  return {VERSION,SEGMENTS,strictDate,dateInterval,model,presence,distance,nearest,neighborhoodProfile,deriveAnchor,validatePhenology,clockRecord,lagText,mount,mountExplorer};
});
/* WINGS_BRAID_CLOCK_JS_END */
(() => {
  "use strict";

  const HOST_COLORS = ["#8C1D40", "#006DAE", "#176B3A", "#6F2DA8", "#C45500", "#00838F", "#5C1229", "#7D6608", "#37474F"];
  const GOLD = "#FFC627";
  const RED = "#B3261E";
  const GREEN = "#176B3A";
  const GRAY = "#AEB4BC";
  const INK = "#202124";

  const svgEl = (name, attrs = {}) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
    return el;
  };

  const esc = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  const formatNumber = (value, digits = 0) => {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString(undefined, {maximumFractionDigits: digits}) : "NA";
  };

  const parseDate = (value) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return null;
    const [y, m, d] = value.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d));
  };

  const dateLabel = (value) => {
    const d = parseDate(value);
    return d ? d.toLocaleDateString(undefined, {year:"numeric", month:"short", day:"numeric", timeZone:"UTC"}) : String(value || "Unknown");
  };

  const monthLabel = (d) => d.toLocaleDateString(undefined, {year:"2-digit", month:"short", timeZone:"UTC"});

  const statusClass = (status) => {
    const s = String(status || "").toUpperCase();
    if (s === "DETECTED") return "is-detected";
    if (s === "NOT_DETECTED") return "is-clear";
    return "is-indeterminate";
  };

  class Explorer {
    constructor(root, payload) {
      this.root = root;
      this.payload = payload;
      this.samples = Array.isArray(payload.samples) ? payload.samples : [];
      this.sampleById = new Map(this.samples.map((sample) => [sample.sample_id, sample]));
      this.referenceContext = payload.public_reference_context || null;
      this.references = Array.isArray(this.referenceContext?.references) ? this.referenceContext.references : [];
      this.referenceById = new Map(this.references.map(ref => [ref.reference_id, ref]));
      this.selectedReferenceId = null;
      this.ebirdContexts = Array.isArray(payload.ebird_contexts) ? payload.ebird_contexts : [];
      this.ebirdAttribution = payload.ebird_attribution || null;
      this.ecology = payload.ecological_context || null;
      this.ecologyDays = 30;
      this.hosts = [...new Set([
        ...(Array.isArray(payload.hosts) ? payload.hosts : []),
        ...this.samples.map((sample) => sample.host).filter(Boolean),
      ])];
      this.hostColor = new Map(this.hosts.map((host, i) => [host, HOST_COLORS[i % HOST_COLORS.length]]));
      this.segments = (payload.segment_order || []).filter((segment) => payload.trees && payload.trees[segment]);
      this.segment = this.segments.includes("HA") ? "HA" : (this.segments[0] || null);
      this.treeMode = "all";
      this.hostFilter = "ALL";
      this.selectedSampleId = null;
      this.hoverSampleId = null;
      this.clusterCursor = new Map();
      this.mapView = "samples";
      this.mapViewport = null;
      this.mapBoundaries = globalThis.WINGS_MAP_BOUNDARIES || null;
      this.outbreakContext = payload.outbreak_context || null;
      this.outbreakLayerEnabled = true;
      this.outbreakScope = "sample";
      this.outbreakBasis = "collection_date";
      this.outbreakFollow = true;
      this.outbreakDays = 30;
      this.outbreakStart = "";
      this.outbreakEnd = "";
      this.outbreakPage = 0;
      this.outbreakSelectedStart = "";
      this.outbreakSelectedEnd = "";
      this.render();
    }

    visibleSamples() {
      return this.samples.filter((sample) => this.hostFilter === "ALL" || sample.host === this.hostFilter);
    }

    hostColorFor(sample) {
      return this.hostColor.get(sample.host) || "#5F6368";
    }

    selectSample(sampleId) {
      if (!this.sampleById.has(sampleId)) return;
      this.selectedReferenceId = null;
      this.selectedSampleId = this.selectedSampleId === sampleId ? null : sampleId;
      this.hoverSampleId = null;
      this.updateSelection();
    }

    selectReference(referenceId) {
      if (!this.referenceById.has(referenceId)) return;
      this.selectedReferenceId = this.selectedReferenceId === referenceId ? null : referenceId;
      this.hoverSampleId = null;
      this.updateSelection();
    }

    setHover(sampleId) {
      this.hoverSampleId = sampleId;
      this.updateEmphasis();
    }

    clearHover() {
      this.hoverSampleId = null;
      this.updateEmphasis();
    }

    render() {
      this.root.innerHTML = `
        <div class="wse-shell">
          <div class="wse-heading">
            <div>
              <div class="wse-eyebrow">Run-level genomic surveillance</div>
              <div class="wse-title">WINGS Surveillance Explorer</div>
              <div class="wse-subtitle">Linked collection timeline, geospatial context, and segment-specific phylogeny. Click any sample on the timeline, map, or phylogeny to select it and highlight it across all views.</div>
            </div>
            <div class="wse-heading-accent" aria-hidden="true"></div>
          </div>
          <div class="wse-metrics"></div>
          <div class="wse-selected" aria-live="polite" hidden></div>
          <section class="wse-panel wse-timeline-panel">
            <div class="wse-panel-heading"><div><span class="wse-panel-kicker">When</span><h3>Collection timeline</h3></div><div class="wse-panel-note">Circle color = host</div></div>
            <div class="wse-timeline"></div>
          </section>
          <div class="wse-main-grid">
            <section class="wse-panel wse-map-panel">
              <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Where</span><h3>Samples and outbreak context</h3></div><div class="wse-panel-note wse-map-count"></div></div>
              <div class="wse-map-toolbar"><label>Map extent <select class="wse-map-view"><option value="samples">Sample area</option><option value="north-america">North America</option><option value="world">World</option><option value="custom" disabled>Custom view</option></select></label><div class="wse-map-navigation" role="group" aria-label="Map navigation"><button type="button" class="wse-map-zoom-in" aria-label="Zoom in">+</button><button type="button" class="wse-map-zoom-out" aria-label="Zoom out">−</button><button type="button" class="wse-map-reset">Reset view</button><button type="button" class="wse-map-show-state" disabled>Select a state to zoom</button></div><span class="wse-map-help">Drag to pan. Focus the map for arrow keys, +/−, or 0 to reset.</span></div>
              <div class="wse-map-layers" hidden><label><input type="checkbox" class="wse-aphis-layer-toggle" checked> APHIS state shading</label><span>Points = WINGS samples · Shading = APHIS source records</span></div>
              <div class="wse-map-frame">
                <div class="wse-map" tabindex="0" role="group" aria-label="Interactive sampling map. Drag to pan; arrow keys move the view; plus and minus zoom; zero resets."></div>
                <div class="wse-map-state-card" aria-live="polite" hidden></div>
              </div>
              <div class="wse-map-layer-legend" aria-live="polite" hidden></div>
              <div class="wse-map-selection" aria-live="polite" aria-atomic="true"></div>
              <div class="wse-map-attribution">Country outlines worldwide; U.S. states and Canadian provinces/territories. Generalized boundaries from <a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener noreferrer">Natural Earth</a>. Sample-area extent stays fixed when filtering hosts.</div>
              <div class="wse-host-legend"></div>
              <div class="wse-outbreak-panel" hidden></div>
            </section>
          </div>
          <section class="wse-panel wse-genome-panel">
            <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Linked evidence</span><h3>Eight-segment genome explorer</h3></div><div class="wse-panel-note">One sample selection across all available trees</div></div>
            <div class="wse-genome-controls"></div>
            <div class="wse-genome-evidence"></div>
            <div class="wse-reference-details" aria-live="polite"></div>
            <div class="wse-segment-tabs" role="group" aria-label="Phylogeny segment"></div>
            <div class="wse-tree-note wse-panel-note"></div>
            <div class="wse-tree"></div>
            <div class="wse-tree-grid"></div>
          </section>
          <div class="wse-footer-note">When the optional phylogeny stage is enabled, WINGS infers segment trees from QC-passing consensus sequences. Otherwise, the Explorer displays available external trees. Trees are displayed without rerooting or time calibration. Collection dates come from metadata, not tip labels.</div>
          <section class="wse-panel wse-ecology-panel">
            <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Ecological context</span><h3>Host reporting, migration, and weather</h3></div><label>Display window ± <select class="wse-ecology-days"><option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option></select></label></div>
            <div class="wse-ecology-intro" aria-live="polite"></div>
            <section class="wse-ecology-source wse-ebird-panel">
              <h4>eBird · Host reporting frequency</h4>
              <div class="wse-ebird"></div>
              <div class="wse-ecology-ebird-charts"></div>
            </section>
            <section class="wse-ecology-source"><h4>BirdCast · Nocturnal migration pilot</h4><div class="wse-ecology-birdcast"></div></section>
            <section class="wse-ecology-source"><h4>Weather · Historical reanalysis</h4><div class="wse-ecology-weather"></div></section>
            <div class="wse-ecology-provenance"></div>
          </section>
        </div>`;

      this.ecologyNode = this.root.querySelector(".wse-ecology-panel");
      this.ecologyNode.querySelector(".wse-ecology-days").addEventListener("change", event => {
        this.ecologyDays = Number(event.target.value);
        this.renderEcology();
      });
      this.outbreakNode = this.root.querySelector(".wse-outbreak-panel");
      this.bindOutbreakControls();
      this.metricsNode = this.root.querySelector(".wse-metrics");
      this.selectedNode = this.root.querySelector(".wse-selected");
      this.timelineNode = this.root.querySelector(".wse-timeline");
      this.ebirdPanelNode = this.root.querySelector(".wse-ebird-panel");
      this.ebirdNode = this.root.querySelector(".wse-ebird");
      this.mapNode = this.root.querySelector(".wse-map");
      this.mapSelectionNode = this.root.querySelector(".wse-map-selection");
      this.mapLayerLegendNode = this.root.querySelector(".wse-map-layer-legend");
      this.mapStateCardNode = this.root.querySelector(".wse-map-state-card");
      this.mapStateCardNode.addEventListener("click", event => {
        const action = event.target.closest("[data-state-action]")?.dataset.stateAction;
        if (action === "zoom") this.showSelectedState();
        if (action === "close") { this.mapStateCardDismissed = true; this.mapStateCardNode.hidden = true; }
        if (action === "records") {
          const records = this.outbreakNode.querySelector(".wse-outbreak-records");
          if (records) { records.open = true; records.scrollIntoView({behavior:"smooth", block:"start"}); records.querySelector("summary")?.focus({preventScroll:true}); }
        }
      });
      this.mapStateButtonNode = this.root.querySelector(".wse-map-show-state");
      this.mapStateButtonNode.addEventListener("click", () => this.showSelectedState());
      this.root.querySelector(".wse-map-layers").hidden = this.outbreakContext?.status !== "READY";
      this.root.querySelector(".wse-aphis-layer-toggle").addEventListener("change", event => {
        this.outbreakLayerEnabled = event.target.checked;
        this.renderMap();
        this.updateEmphasis();
      });
      this.root.querySelector(".wse-map-view").addEventListener("change", event => {
        this.mapView = event.target.value;
        this.mapViewport = null;
        this.refreshMapView();
      });
      this.mapCountNode = this.root.querySelector(".wse-map-count");
      this.root.querySelector(".wse-map-zoom-in").addEventListener("click", () => this.zoomMap(1 / 1.5));
      this.root.querySelector(".wse-map-zoom-out").addEventListener("click", () => this.zoomMap(1.5));
      this.root.querySelector(".wse-map-reset").addEventListener("click", () => this.resetMapView());
      this.bindMapNavigation();
      this.legendNode = this.root.querySelector(".wse-host-legend");
      this.segmentTabsNode = this.root.querySelector(".wse-segment-tabs");
      this.treeNode = this.root.querySelector(".wse-tree");
      this.treeNoteNode = this.root.querySelector(".wse-tree-note");
      this.treeGridNode = this.root.querySelector(".wse-tree-grid");
      this.referenceNode = this.root.querySelector(".wse-reference-details");
      this.evidenceNode = this.root.querySelector(".wse-genome-evidence");
      this.genomeControlsNode = this.root.querySelector(".wse-genome-controls");

      this.renderMetrics();
      this.renderGenomeControls();
      this.renderSegmentTabs();
      this.renderTimeline();
      this.renderEbird();
      this.renderEcology();
      this.renderMap();
      this.renderTrees();
      this.renderLegend();
      this.updateSelection();
    }

    renderMetrics() {
      const s = this.payload.summary || {};
      const treeCount = Object.keys(this.payload.trees || {}).length;
      this.metricsNode.innerHTML = [
        ["Samples", formatNumber(s.sample_count ?? this.samples.length)],
        ["Geolocated", `${formatNumber(s.geolocated_count ?? 0)} / ${formatNumber(s.sample_count ?? this.samples.length)}`],
        ["Collection dates", formatNumber(s.date_count ?? 0)],
        ["Host groups", formatNumber(s.host_count ?? this.hosts.length)],
        ["Segment trees", `${formatNumber(treeCount)} / 8`],
      ].map(([label, value]) => `<div class="wse-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
    }

    renderSegmentTabs() {
      if (!this.segmentTabsNode) return;

      const order = this.payload.segment_order || [];
      this.segmentTabsNode.innerHTML = order.map((segment) => {
        const available = Boolean(this.payload.trees?.[segment]);
        const active = this.treeMode === "single" && segment === this.segment;
        return `<button
          type="button"
          class="wse-segment-tab${active ? " is-active" : ""}"
          data-segment="${esc(segment)}"
          aria-pressed="${active ? "true" : "false"}"
          ${available ? "" : "disabled"}
        >${esc(segment)}</button>`;
      }).join("");

      this.segmentTabsNode.querySelectorAll(".wse-segment-tab").forEach((button) => {
        button.addEventListener("click", () => {
          if (button.disabled) return;

          this.segment = button.dataset.segment;
          this.treeMode = "single";
          this.genomeControlsNode.querySelector(".wse-view-select").value = "single";
          this.renderSegmentTabs();
          this.renderTrees();
          this.updateSelection();
        });
      });
    }

    renderGenomeControls() {
      this.genomeControlsNode.innerHTML = `
        <label>Sample<select class="wse-sample-select" aria-label="Selected sample"><option value="">Select a sample…</option>${this.samples.map(sample => `<option value="${esc(sample.sample_id)}">${esc(sample.sample_id)}</option>`).join("")}</select></label>
        <label>Public reference<select class="wse-reference-select" aria-label="Selected public reference" ${this.references.length ? "" : "disabled"}><option value="">${this.references.length ? "Select a public reference…" : "No reference manifest loaded"}</option>${this.references.map(ref => `<option value="${esc(ref.reference_id)}">${esc(ref.isolate || ref.reference_id)}</option>`).join("")}</select></label>
        <label>Tree view<select class="wse-view-select"><option value="all">All eight segments</option><option value="single">Single segment</option></select></label>
        <button type="button" class="wse-clear-selection">Clear selection</button>`;
      this.genomeControlsNode.querySelector(".wse-sample-select").addEventListener("change", event => {
        this.selectedReferenceId = null;
        this.selectedSampleId = this.sampleById.has(event.target.value) ? event.target.value : null;
        this.hoverSampleId = null;
        this.updateSelection();
      });
      this.genomeControlsNode.querySelector(".wse-reference-select")?.addEventListener("change", event => {
        this.selectedReferenceId = this.referenceById.has(event.target.value) ? event.target.value : null;
        this.hoverSampleId = null;
        this.updateSelection();
      });
      this.genomeControlsNode.querySelector(".wse-view-select").addEventListener("change", event => {
        this.treeMode = event.target.value;
        this.renderSegmentTabs();
        this.renderTrees();
        this.updateSelection();
      });
      this.genomeControlsNode.querySelector(".wse-clear-selection").addEventListener("click", () => {
        this.selectedReferenceId = null;
        this.selectedSampleId = null;
        this.hoverSampleId = null;
        this.treeMode = "all";
        this.genomeControlsNode.querySelector(".wse-view-select").value = "all";
        this.renderSegmentTabs();
        this.renderTrees();
        this.updateSelection();
      });
    }

    setHostFilter(host) {
      this.hostFilter = host || "ALL";

      const selected = this.sampleById.get(this.selectedSampleId);

      if (
        selected &&
        this.hostFilter !== "ALL" &&
        selected.host !== this.hostFilter
      ) {
        this.selectedSampleId = null;
        this.selectedReferenceId = null;
        this.hoverSampleId = null;
        this.outbreakSelectedStart = "";
        this.outbreakSelectedEnd = "";
      }

      this.renderTimeline();
      this.renderEbird();
      this.renderEcology();
      this.renderMap();
      this.renderTrees();
      this.renderLegend();
      this.updateSelection();
    }

    renderSelected() {
      const sample = this.sampleById.get(this.selectedSampleId);
      if (!sample) {
        this.selectedNode.hidden = true;
        this.selectedNode.innerHTML = "";
        return;
      }
      this.selectedNode.hidden = false;
      const location = sample.has_coordinates
        ? `${sample.state}, ${sample.country} · ${Number(sample.latitude).toFixed(3)}, ${Number(sample.longitude).toFixed(3)}`
        : `${sample.state}, ${sample.country} · coordinates unavailable`;
      const tags = [];
      if (sample.potential_subtype && sample.potential_subtype !== "Undetermined") {
        tags.push(`<span>${esc(sample.potential_subtype)}</span>`);
      }
      if (sample.h5_status && sample.h5_status !== "NOT_RECORDED") {
        tags.push(`<span class="${statusClass(sample.h5_status)}">H5 ${esc(String(sample.h5_status).replaceAll("_", " "))}</span>`);
      }
      if (sample.segments_pass != null) {
        tags.push(`<span>${esc(`${sample.segments_pass}/8`)} segments pass</span>`);
      }
      this.selectedNode.innerHTML = `
        <div class="wse-selected-color" style="--host-color:${this.hostColorFor(sample)}"></div>
        <div class="wse-selected-main">
          <span class="wse-selected-kicker">Selected sample</span>
          <strong>${esc(sample.sample_id)}</strong>
          <small>${esc(sample.host)} · ${esc(dateLabel(sample.collection_date))} · ${esc(location)}</small>
        </div>
        <div class="wse-selected-tags">${tags.join("")}</div>
        <a class="wse-report-link" href="${esc(sample.report_href)}">Open sample report →</a>`;
    }

    renderEbird() {
      if (!this.ebirdPanelNode) return;
      this.ebirdPanelNode.hidden = false;
      if (!this.ebirdContexts.length) {
        this.ebirdNode.innerHTML = '<p class="wse-ebird-note">No validated eBird reporting frequency is available in this report. Missing or unmatched data are not zero frequency.</p>';
        return;
      }
      const contexts = this.ebirdContexts.filter((item) =>
        (this.hostFilter === "ALL" || item.host === this.hostFilter) &&
        (!this.selectedSampleId || (item.sample_ids || []).includes(this.selectedSampleId)));
      const attribution = this.ebirdAttribution;
      const sourceUrl = "https://ebird.org/data/download";
      const legalNotice = attribution ? `
        <div class="wse-ebird-legal">
          <strong>Data source and citation</strong>
          <p>${esc(attribution.citation)}</p>
          <p>Derived eBird data in this report are subject to the eBird Data Access Terms of Use. Cornell Lab of Ornithology does not endorse this WINGS report. <a href="${sourceUrl}" target="_blank" rel="noopener noreferrer">Get the original data from eBird</a>.</p>
          <details><summary>eBird Data Access Terms of Use (full text)</summary><pre>${esc(attribution.terms)}</pre></details>
        </div>` : "";
      if (!contexts.length) {
        this.ebirdNode.innerHTML = '<p class="wse-ebird-note">No eBird context is available for this selection.</p>' + legalNotice;
        return;
      }
      this.ebirdNode.innerHTML = `
        <p class="wse-ebird-note">These are complete eBird checklist reporting frequencies, not bird abundance, infection prevalence, or measurements at the sampled birds. Records sharing the same location and date window are displayed once; sample counts must not be added together.</p>
        <div class="wse-ebird-grid">${contexts.map((item) => {
          const ids = Array.isArray(item.sample_ids) ? item.sample_ids : [];
          const count = Number(item.complete_checklists);
          const positives = Number(item.reporting_checklists);
          const percent = count > 0 ? 100 * positives / count : NaN;
          const scope = item.radius_km == null ? `${item.state}, ${item.country} · state-wide` :
            `${item.state}, ${item.country} · ${formatNumber(item.radius_km, 1)} km radius`;
          const isSelected = ids.includes(this.selectedSampleId);
          return `<article class="wse-ebird-card${isSelected ? " is-selected" : ""}">
            <div class="wse-ebird-card-heading"><strong>${esc(item.species)}</strong><span>${Number.isFinite(percent) ? percent.toFixed(1) + "%" : "NA"}</span></div>
            <div class="wse-ebird-track"><span style="width:${Number.isFinite(percent) ? Math.min(100, Math.max(0, percent)) : 0}%"></span></div>
            <div>${esc(`${formatNumber(positives)} of ${formatNumber(count)} complete checklists reported this species`)}</div>
            <small>${esc(scope)} · ${esc(dateLabel(item.date_from))}–${esc(dateLabel(item.date_to))}</small>
            <small>Source: eBird Basic Dataset${item.release ? ` · ${esc(item.release)}` : ""}</small>
          </article>`;
        }).join("")}</div>${legalNotice}`;
    }

    ecologyWindow() {
      const sample = this.sampleById.get(this.selectedSampleId);
      const center = this.outbreakEpoch(sample?.collection_date);
      return center === null ? null : {sample, start: center - this.ecologyDays * 86400000, end: center + this.ecologyDays * 86400000, center};
    }

    ecologyState(sample) {
      if (!sample || !["US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"].includes(String(sample.country || "").trim().toUpperCase())) return null;
      const value = String(sample.state || "").trim().toUpperCase().replace(/^US-/, "");
      const states = this.ecology?.states || this.outbreakContext?.states || {};
      const code = Object.keys(states).find(code => code === value || states[code].toUpperCase() === value);
      const region = this.mapBoundaries?.regions.find(item => item.country === "USA" && (item.code === value || String(item.name || "").toUpperCase() === value));
      return code || region?.code || null;
    }

    ecologyLink(url, label) {
      // Only ordinary HTTPS source links can be emitted from imported metadata.
      return /^https:\/\/[^\s/]+(?:\/|$)/i.test(String(url || "")) ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : esc(label);
    }

    renderEcology() {
      if (!this.ecologyNode) return;
      const node = selector => this.ecologyNode.querySelector(selector);
      const window = this.ecologyWindow();
      const sample = this.sampleById.get(this.selectedSampleId);
      const bird = this.ecology?.birdcast;
      const provenance = this.ecology ? `<details><summary>Ecological snapshot provenance</summary><p>Snapshot built: ${esc(this.ecology.created_at)} · Cached window: ±${esc(this.ecology.window_days)} days. Changing the display window does not download more data.</p><p>File: ${esc(this.ecology.source_file)}<br>SHA-256: <code>${esc(this.ecology.snapshot_sha256)}</code></p><p>Sources retain their own scales and dates. This offline snapshot stays fixed in saved bundles.</p></details>` : '<p>No BirdCast or weather snapshot is loaded. The existing eBird results remain available.</p>';
      node(".wse-ecology-provenance").innerHTML = provenance;
      const birdNode = node(".wse-ecology-birdcast"), weatherNode = node(".wse-ecology-weather");
      const ebirdCharts = node(".wse-ecology-ebird-charts");
      ebirdCharts.innerHTML = "";
      if (!window) {
        node(".wse-ecology-intro").textContent = sample ? `Selected WINGS sample: ${sample.sample_id}. A valid collection date is required for aligned ecological views.` : "Select a WINGS sample on the map, timeline, or tree to align these views around its collection date.";
        birdNode.innerHTML = `<p>${bird?.status === "READY" ? "A BirdCast pilot snapshot is loaded. Select a dated sample to view regional migration." : "BirdCast pilot data are not loaded."} ${this.ecologyLink("https://dashboard.birdcast.org/", "Open BirdCast dashboard")}</p>`;
        weatherNode.textContent = "Select a dated sample with valid coordinates to view cached weather. No state-centroid weather is substituted.";
        return;
      }
      const from = new Date(window.start).toISOString().slice(0, 10), through = new Date(window.end).toISOString().slice(0, 10);
      node(".wse-ecology-intro").innerHTML = `<p><strong>Selected WINGS sample: ${esc(sample.sample_id)}</strong> · Collected: ${esc(sample.collection_date)} · Display: ${from} through ${through}</p><p>All charts share this calendar-date axis; dashed burgundy lines mark the sample collection date. eBird retains its original aggregation window, BirdCast uses the local evening date, and weather uses local calendar days. Different units and geographic scales are shown separately; these signals do not establish infection risk or epidemiological linkage.</p>`;
      const contexts = this.ebirdContexts.filter(item => (item.sample_ids || []).includes(sample.sample_id) && (this.hostFilter === "ALL" || item.host === this.hostFilter));
      contexts.forEach(item => {
        const caption = document.createElement("p");
        caption.textContent = `${item.species}: ${item.date_from} through ${item.date_to} is one aggregate window. Its original checklist denominator is unchanged; the displayed portion is clipped to the shared axis, not recomputed.`;
        ebirdCharts.appendChild(caption);
        const start = this.outbreakEpoch(item.date_from), end = this.outbreakEpoch(item.date_to);
        if (start !== null && end !== null && end >= window.start && start <= window.end) this.renderEcologyChart(ebirdCharts, window, [{date:item.date_from, end:item.date_to, value:100 * item.reporting_checklists / item.complete_checklists}], "Complete-checklist reporting frequency (%)", "#176B3A", true);
        else { const missing = document.createElement("p"); missing.textContent = "The eBird aggregation window does not overlap this display window."; ebirdCharts.appendChild(missing); }
      });
      const state = this.ecologyState(sample);
      const stateName = this.ecology?.states?.[state] || this.outbreakContext?.states?.[state] || sample.state;
      const dashboard = state && !["AK", "HI"].includes(state) ? `https://dashboard.birdcast.org/region/US-${state}` : "https://dashboard.birdcast.org/";
      const birdLink = this.ecologyLink(dashboard, "Open BirdCast dashboard (online)");
      if (!state || ["AK", "HI"].includes(state)) {
        birdNode.innerHTML = `<p>This state-level pilot requires a recognized state in the contiguous United States. Sample geography: ${esc(sample.state)}, ${esc(sample.country)}. ${birdLink}</p>`;
      } else if (bird?.status !== "READY") {
        birdNode.innerHTML = `<p>${esc(stateName)} · State-level migration. No BirdCast pilot snapshot is loaded; this is unavailable data, not zero migration. ${birdLink}</p>`;
      } else {
        const records = bird.records.filter(row => row.state_code === state && this.outbreakEpoch(row.date) >= window.start && this.outbreakEpoch(row.date) <= window.end);
        const available = records.filter(row => row.status === "AVAILABLE" && typeof row.birds_crossed === "number" && Number.isFinite(row.birds_crossed));
        const nights = Math.round((window.end - window.start) / 86400000) + 1;
        const zones = [...new Set(records.map(row => row.timezone))];
        birdNode.innerHTML = `<p><strong>${esc(stateName)} · State-level radar-derived estimate</strong><br>Estimated birds crossing the state per night (birds/night). Aggregate nocturnal migration across species; this does not measure movement of the sample's host species. Counts depend on regional extent.</p><p>Night = local evening date, sunset to following sunrise. Timezone(s): ${esc(zones.join(", ") || "No nights loaded for this window")}. ${available.length} of ${nights} nights have estimates. Missing nights are gaps, not zero; seasonal and radar coverage can limit availability.</p><p>${birdLink} · Imported: ${esc(bird.retrieved_on)}</p><div class="wse-ecology-chart"></div><details><summary>Nightly values and missing-data reasons</summary><div class="wse-ecology-table"><table><thead><tr><th>Night</th><th>Timezone</th><th>Estimated birds</th><th>Status / reason</th></tr></thead><tbody>${records.map(row => `<tr><td>${esc(row.date)}</td><td>${esc(row.timezone)}</td><td>${row.status === "AVAILABLE" && row.birds_crossed != null ? formatNumber(row.birds_crossed, 2) : "Unavailable"}</td><td>${esc(row.status)} ${esc(row.reason)}</td></tr>`).join("") || '<tr><td colspan="4">No imported records match this state and window.</td></tr>'}</tbody></table></div><p>Nights absent from the imported file have no estimate or recorded reason.</p></details><details><summary>BirdCast source and provenance</summary><p>${esc(bird.citation)}</p><p>Source: ${this.ecologyLink(bird.source_url, "Imported source")} · Retrieved: ${esc(bird.retrieved_on)}<br>Reuse basis: ${esc(bird.reuse_basis)}<br>CSV SHA-256: <code>${esc(bird.sha256)}</code></p></details>`;
        this.renderEcologyChart(birdNode.querySelector(".wse-ecology-chart"), window, available.map(row => ({date:row.date, value:row.birds_crossed})), "Estimated birds crossing state / night", "#006DAE");
      }
      const binding = this.ecology?.bindings?.[sample.sample_id];
      const weather = binding?.status === "READY" ? this.ecology.weather?.[binding.weather_key] : null;
      if (!weather) {
        const reason = !this.validMapCoordinates(sample) ? "Valid sample coordinates are required; no state-centroid weather is substituted." : binding?.reason || "No weather snapshot is loaded for this sample.";
        weatherNode.innerHTML = `<p>${esc(reason)}</p><p>Weather uses ERA5 gridded reanalysis: daily mean temperature at 2 m (°C), daily precipitation total (mm), and daily maximum wind speed at 10 m (km/h).</p>`;
        return;
      }
      const weatherRows = weather.rows.filter(row => this.outbreakEpoch(row.date) >= window.start && this.outbreakEpoch(row.date) <= window.end);
      const columns = [ ["temperature_2m_mean", "Daily mean temperature at 2 m (°C)", "#B45309"], ["precipitation_sum", "Daily precipitation total (mm)", "#006DAE"], ["wind_speed_10m_max", "Daily maximum wind speed at 10 m (km/h)", "#6F2DA8"] ];
      const countDays = Math.round((window.end - window.start) / 86400000) + 1;
      weatherNode.innerHTML = `<p><strong>ERA5 · ${esc(weather.resolution)} · Gridded reanalysis estimate</strong><br>Requested location: ${esc(sample.latitude)}, ${esc(sample.longitude)}. Returned grid location: ${esc(weather.grid_latitude)}, ${esc(weather.grid_longitude)}. Local daily timezone: ${esc(weather.timezone)}.</p><p>Cached dates: ${esc(weather.rows[0]?.date || "Unavailable")} through ${esc(weather.rows.at(-1)?.date || "Unavailable")}. ${weatherRows.length} of ${countDays} displayed days have source rows; null values remain gaps. These are model-assisted estimates, not measurements at the collection site. ${this.ecologyLink(weather.source_url, "Source documentation")}</p>${columns.map(([key, label]) => `<div data-weather-chart="${key}"></div>`).join("")}<details><summary>Daily weather values</summary><div class="wse-ecology-table"><table><thead><tr><th>Local date</th><th>Mean temperature (°C)</th><th>Precipitation (mm)</th><th>Maximum wind (km/h)</th></tr></thead><tbody>${weatherRows.map(row => `<tr><td>${esc(row.date)}</td>${columns.map(([key]) => `<td>${row[key] == null ? "Unavailable" : formatNumber(row[key], 2)}</td>`).join("")}</tr>`).join("") || '<tr><td colspan="4">No cached weather rows in this window.</td></tr>'}</tbody></table></div></details><details><summary>Weather source and provenance</summary><p>${esc(weather.provider)} · ${esc(weather.license)}<br>Retrieved: ${esc(weather.retrieved_at)}<br>Raw response SHA-256: <code>${esc(weather.raw_sha256)}</code></p><p>${this.ecologyLink(weather.request_url, "Original weather request (online)")}</p></details>`;
      columns.forEach(([key, label, color]) => {
        const rows = weatherRows.map(row => ({date:row.date, value:row[key]}));
        const target = weatherNode.querySelector(`[data-weather-chart="${key}"]`);
        const heading = document.createElement("p");
        heading.textContent = `${label} · ${rows.filter(row => typeof row.value === "number" && Number.isFinite(row.value)).length}/${countDays} days with values`;
        target.appendChild(heading);
        this.renderEcologyChart(target, window, rows, label, color);
      });
    }

    renderEcologyChart(target, window, rows, title, color, aggregate = false) {
      if (!target) return;
      const width = 900, height = 180, left = 76, right = 875, top = 20, bottom = 115;
      const values = rows.filter(row => typeof row.value === "number" && Number.isFinite(row.value));
      const min = Math.min(0, ...values.map(row => row.value));
      const max = aggregate ? 100 : Math.max(1, ...values.map(row => row.value));
      const x = time => left + (time - window.start) / (window.end - window.start + 86400000) * (right - left);
      const y = value => bottom - (value - min) / (max - min) * (bottom - top);
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":title, class:"wse-ecology-plot"});
      const label = (text, px, py, anchor="middle") => { const el=svgEl("text", {x:px,y:py,"text-anchor":anchor,class:"wse-outbreak-axis"}); el.textContent=text; svg.appendChild(el); };
      [...new Set([min, max, 0])].forEach(value => {
        svg.appendChild(svgEl("line", {x1:left,x2:right,y1:y(value),y2:y(value),class:"wse-outbreak-gridline"}));
        const tick = Math.abs(value) >= 10000 ? value.toLocaleString(undefined, {notation:"compact", maximumFractionDigits:1}) : formatNumber(value, 1);
        if (value !== 0 || value === min || value === max || (Math.abs(y(0) - y(min)) >= 16 && Math.abs(y(0) - y(max)) >= 16)) label(tick,left-8,y(value)+4,"end");
      });
      values.forEach(row => {
        const start = this.outbreakEpoch(row.date), end = this.outbreakEpoch(row.end || row.date);
        if (start === null || end === null || end < window.start || start > window.end) return;
        const from = Math.max(start, window.start), through = Math.min(end + 86400000, window.end + 86400000);
        const valueY = y(row.value), zeroY = y(0);
        const mark = row.value === 0 ? svgEl("line", {x1:x(from),x2:x(through)-1,y1:zeroY,y2:zeroY,stroke:color,"stroke-width":3}) : svgEl("rect", {x:x(from),y:Math.min(valueY,zeroY),width:Math.max(1,x(through)-x(from)-1),height:Math.max(1,Math.abs(zeroY-valueY)),fill:color,opacity:aggregate?0.4:0.85});
        const tip = svgEl("title"); tip.textContent = `${row.date}${row.end ? " through " + row.end + " (one aggregate)" : ""}: ${formatNumber(row.value, 2)} · ${title}`; mark.appendChild(tip); svg.appendChild(mark);
      });
      svg.appendChild(svgEl("line", {x1:x(window.center+43200000),x2:x(window.center+43200000),y1:top-4,y2:bottom,class:"wse-outbreak-sample-date"}));
      label(new Date(window.start).toISOString().slice(0,10),left,bottom+24,"start");
      label(window.sample.collection_date,x(window.center+43200000),bottom+24);
      label(new Date(window.end).toISOString().slice(0,10),right,bottom+24,"end");
      label(title,(left+right)/2,height-9);
      if (!values.length) label("No values available in this window",(left+right)/2,65);
      target.appendChild(svg);
    }


    renderLegend() {
      const counts = new Map(this.hosts.map((host) => [host, 0]));
      this.samples.forEach((sample) => counts.set(sample.host, (counts.get(sample.host) || 0) + 1));
      const ranked = [...counts.keys()].filter((host) => counts.get(host) > 0)
        .sort((a, b) => counts.get(b) - counts.get(a) || a.localeCompare(b));
      const maxCount = Math.max(1, ...ranked.map((host) => counts.get(host)));

      this.legendNode.innerHTML = `
        <div class="wse-host-distribution-title">Host distribution</div>
        ${ranked.length ? ranked.map((host) => {
          const count = counts.get(host);
          const color = this.hostColor.get(host) || "#5F6368";
          const active = this.hostFilter === host;
          return `<button type="button" class="wse-host-row${active ? " is-active" : ""}"
            data-host="${esc(host)}" aria-pressed="${active ? "true" : "false"}"
            aria-label="Filter by ${esc(host)}: ${count} samples">
            <span class="wse-host-label"><i style="background:${color}"></i>${esc(host)}</span>
            <span class="wse-host-track"><span class="wse-host-fill" style="width:${100 * count / maxCount}%;background:${color}"></span></span>
            <strong>${formatNumber(count)}</strong>
          </button>`;
        }).join("") : '<div class="wse-empty">No host data available.</div>'}`;

      this.legendNode.querySelectorAll(".wse-host-row").forEach((button) => {
        button.addEventListener("click", () => {
          this.setHostFilter(this.hostFilter === button.dataset.host ? "ALL" : button.dataset.host);
        });
      });
    }

    renderTimeline() {
      const samples = this.visibleSamples().filter((sample) => parseDate(sample.collection_date));
      this.timelineNode.innerHTML = "";
      if (!samples.length) {
        this.timelineNode.innerHTML = `<div class="wse-empty">No dated samples are available for the current filter.</div>`;
        return;
      }
      const width = 1100, height = 210, left = 52, right = 24, top = 22, bottom = 45;
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":"Collection timeline"});
      // Keep the same axis when a host filter changes the visible samples.
      const dates = this.samples.map((s) => parseDate(s.collection_date))
        .filter((date) => date).map((date) => date.getTime());
      let min = Math.min(...dates), max = Math.max(...dates);
      const pad = Math.max((max - min) * 0.035, 86400000 * 10);
      min -= pad; max += pad;
      const x = (ms) => left + (ms - min) / Math.max(1, max - min) * (width - left - right);
      const baselineY = height - bottom;

      const axis = svgEl("line", {x1:left, y1:baselineY, x2:width-right, y2:baselineY, class:"wse-axis-line"});
      svg.appendChild(axis);

      const minDate = new Date(min), maxDate = new Date(max);
      const tick = new Date(Date.UTC(minDate.getUTCFullYear(), minDate.getUTCMonth(), 1));
      while (tick <= maxDate) {
        const tx = x(tick.getTime());
        svg.appendChild(svgEl("line", {x1:tx, y1:baselineY, x2:tx, y2:baselineY+6, class:"wse-axis-tick"}));
        const label = svgEl("text", {x:tx, y:baselineY+25, "text-anchor":"middle", class:"wse-axis-label"});
        label.textContent = monthLabel(tick);
        svg.appendChild(label);
        tick.setUTCMonth(tick.getUTCMonth() + 2);
      }

      const grouped = new Map();
      samples.forEach((sample) => {
        const key = sample.collection_date;
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(sample);
      });

      grouped.forEach((group, date) => {
        const tx = x(parseDate(date).getTime());
        group.forEach((sample, index) => {
          const col = index % 2;
          const row = Math.floor(index / 2);
          const cx = tx + (col ? 7 : -7);
          const cy = baselineY - 16 - row * 16;
          const circle = svgEl("circle", {
            cx, cy, r:6.2,
            fill:this.hostColorFor(sample),
            class:"wse-sample-mark wse-timeline-mark",
            "data-sample-id":sample.sample_id,
            tabindex:0,
          });
          circle.addEventListener("click", () => this.selectSample(sample.sample_id));
          circle.addEventListener("mouseenter", () => this.setHover(sample.sample_id));
          circle.addEventListener("mouseleave", () => this.clearHover());
          circle.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") this.selectSample(sample.sample_id); });
          const title = svgEl("title");
          title.textContent = `${sample.sample_id}\n${sample.host} · ${dateLabel(sample.collection_date)}`;
          circle.appendChild(title);
          svg.appendChild(circle);
        });
      });
      this.timelineNode.appendChild(svg);
    }

    validMapCoordinates(sample) {
      const valid = value => value !== null && value !== undefined && String(value).trim() !== "" && Number.isFinite(Number(value));
      return Boolean(sample.has_coordinates && valid(sample.longitude) && valid(sample.latitude) &&
        Math.abs(Number(sample.longitude)) <= 180 && Math.abs(Number(sample.latitude)) <= 90);
    }

    mapBounds() {
      if (this.mapViewport) return [...this.mapViewport];
      if (this.mapView === "world") return [-180, 180, -90, 90];
      const northAmerica = [-180, -45, 5, 85];
      if (this.mapView === "north-america") return northAmerica;
      // Use the entire run so host filtering never shifts the geographic frame.
      const points = this.samples.filter(sample => this.validMapCoordinates(sample));
      if (!points.length) return northAmerica;
      const lons = points.map(sample => Number(sample.longitude));
      const lats = points.map(sample => Number(sample.latitude));
      const lonMin = Math.min(...lons), lonMax = Math.max(...lons);
      const latMin = Math.min(...lats), latMax = Math.max(...lats);
      const lonPad = Math.max(5, (lonMax - lonMin) * .15);
      const latPad = Math.max(3, (latMax - latMin) * .15);
      return [Math.max(-180, lonMin - lonPad), Math.min(180, lonMax + lonPad),
        Math.max(-90, latMin - latPad), Math.min(90, latMax + latPad)];
    }

    constrainMapBounds(bounds) {
      const width = Math.max(.05, Math.min(360, bounds[1] - bounds[0]));
      const height = Math.max(.025, Math.min(180, bounds[3] - bounds[2]));
      const x = Math.max(-180 + width / 2, Math.min(180 - width / 2, (bounds[0] + bounds[1]) / 2));
      const y = Math.max(-90 + height / 2, Math.min(90 - height / 2, (bounds[2] + bounds[3]) / 2));
      return [x - width / 2, x + width / 2, y - height / 2, y + height / 2];
    }

    refreshMapView() {
      const select = this.root.querySelector(".wse-map-view");
      if (select) select.value = this.mapView;
      this.renderMap();
      this.renderMapSelection();
      this.updateEmphasis();
    }

    setMapViewport(bounds) {
      this.mapViewport = this.constrainMapBounds(bounds);
      this.mapView = "custom";
      this.refreshMapView();
    }

    zoomMap(factor) {
      const [left, right, bottom, top] = this.mapBounds();
      const x = (left + right) / 2, y = (bottom + top) / 2;
      const dx = (right - left) * factor / 2, dy = (top - bottom) * factor / 2;
      this.setMapViewport([x - dx, x + dx, y - dy, y + dy]);
    }

    resetMapView() {
      this.mapViewport = null;
      this.mapView = "samples";
      this.refreshMapView();
    }

    shiftedMapBounds(bounds, dx, dy) {
      const {px, py} = this.mapProjection(bounds);
      const lon = dx / (px(1) - px(0));
      const lat = dy / (py(1) - py(0));
      return this.constrainMapBounds([bounds[0] - lon, bounds[1] - lon, bounds[2] - lat, bounds[3] - lat]);
    }

    bindMapNavigation() {
      const node = this.mapNode;
      let drag = null, suppressClick = false;
      const restore = () => {
        if (!drag) return;
        const current = drag;
        drag = null;
        current.svg.style.transform = "";
        node.classList.remove("is-panning");
        if (node.hasPointerCapture(current.id)) node.releasePointerCapture(current.id);
      };
      node.addEventListener("pointerdown", event => {
        if (drag || event.button !== 0 || event.isPrimary === false) return;
        suppressClick = false;
        const svg = node.querySelector("svg");
        const matrix = svg?.getScreenCTM();
        if (!matrix || !matrix.a || !matrix.d) return;
        drag = {id: event.pointerId, x: event.clientX, y: event.clientY,
          sx: matrix.a, sy: matrix.d, svg, bounds: this.mapBounds(), moved: false};
      });
      node.addEventListener("pointermove", event => {
        if (!drag || event.pointerId !== drag.id) return;
        const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
        if (!drag.moved && Math.hypot(dx, dy) < 5) return;
        drag.moved = true;
        suppressClick = true;
        node.setPointerCapture(drag.id);
        node.classList.add("is-panning");
        drag.svg.style.transform = `translate(${dx}px, ${dy}px)`;
        event.preventDefault();
      });
      node.addEventListener("pointerup", event => {
        if (!drag || event.pointerId !== drag.id) return;
        const bounds = drag.moved ? this.shiftedMapBounds(drag.bounds,
          (event.clientX - drag.x) / drag.sx, (event.clientY - drag.y) / drag.sy) : null;
        restore();
        if (bounds) { event.preventDefault(); this.setMapViewport(bounds); }
      });
      node.addEventListener("pointercancel", event => { if (drag?.id === event.pointerId) restore(); });
      node.addEventListener("lostpointercapture", () => restore());
      node.addEventListener("pointerleave", () => { if (drag && !drag.moved) restore(); });
      // A drag that starts on a sample must never select/cycle that sample.
      node.addEventListener("click", event => {
        if (suppressClick) { suppressClick = false; event.preventDefault(); event.stopImmediatePropagation(); }
      }, true);
      node.addEventListener("keydown", event => {
        if (event.target !== node || event.ctrlKey || event.metaKey || event.altKey) return;
        suppressClick = false;
        const moves = {ArrowLeft: [90, 0], ArrowRight: [-90, 0], ArrowUp: [0, 60], ArrowDown: [0, -60]};
        if (moves[event.key]) this.setMapViewport(this.shiftedMapBounds(this.mapBounds(), ...moves[event.key]));
        else if (event.key === "+" || event.key === "=") this.zoomMap(1 / 1.5);
        else if (event.key === "-") this.zoomMap(1.5);
        else if (event.key === "0") this.resetMapView();
        else return;
        event.preventDefault();
      });
    }

    mapProjection(bounds, width = 900, height = 460) {
      const [lonMin, lonMax, latMin, latMax] = bounds;
      const centerLon = (lonMin + lonMax) / 2, centerLat = (latMin + latMax) / 2;
      const cosLat = Math.max(.15, Math.cos(centerLat * Math.PI / 180));
      const scale = Math.min((width - 64) / ((lonMax - lonMin) * cosLat), (height - 64) / (latMax - latMin));
      return {px: lon => width / 2 + (lon - centerLon) * cosLat * scale,
        py: lat => height / 2 - (lat - centerLat) * scale};
    }

    visibleMapLabel(feature, projected, anchor, width, height) {
      // Clip each outer ring to the viewport before choosing its label position.
      const clip = (ring, axis, edge, keepGreater) => {
        const inside = point => keepGreater ? point[axis] >= edge : point[axis] <= edge;
        const output = [];
        if (!ring.length) return output;
        let previous = ring[ring.length - 1];
        for (const current of ring) {
          if (inside(current) !== inside(previous)) {
            const ratio = (edge - previous[axis]) / (current[axis] - previous[axis]);
            output.push([previous[0] + ratio * (current[0] - previous[0]), previous[1] + ratio * (current[1] - previous[1])]);
          }
          if (inside(current)) output.push(current);
          previous = current;
        }
        return output;
      };
      const contains = (point, ring) => {
        let inside = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          const [x, y] = ring[i], [xx, yy] = ring[j];
          if ((y > point[1]) !== (yy > point[1]) && point[0] < (xx - x) * (point[1] - y) / (yy - y) + x) inside = !inside;
        }
        return inside;
      };
      const pieces = projected.map(polygon => {
        let ring = polygon[0];
        for (const [axis, edge, greater] of [[0, 8, true], [0, width - 8, false], [1, 8, true], [1, height - 8, false]]) ring = clip(ring, axis, edge, greater);
        let twiceArea = 0, cx = 0, cy = 0;
        for (let i = 0; i < ring.length; i++) {
          const a = ring[i], b = ring[(i + 1) % ring.length], cross = a[0] * b[1] - b[0] * a[1];
          twiceArea += cross; cx += (a[0] + b[0]) * cross; cy += (a[1] + b[1]) * cross;
        }
        return {ring, polygon, area: Math.abs(twiceArea / 2), center: [cx / (3 * twiceArea), cy / (3 * twiceArea)]};
      }).filter(piece => piece.area >= 35).sort((a, b) => b.area - a.area);
      if (!pieces.length) return null;
      const piece = pieces[0], xs = piece.ring.map(p => p[0]), ys = piece.ring.map(p => p[1]);
      const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
      const within = point => point.every(Number.isFinite) && contains(point, piece.ring) && !piece.polygon.slice(1).some(hole => contains(point, hole));
      const grid = [];
      for (let y = 1; y < 8; y++) for (let x = 1; x < 8; x++) grid.push([minX + (maxX - minX) * x / 8, minY + (maxY - minY) * y / 8]);
      grid.sort((a,b) => Math.hypot(a[0]-piece.center[0],a[1]-piece.center[1]) - Math.hypot(b[0]-piece.center[0],b[1]-piece.center[1]));
      return {area: piece.area, span: maxX - minX, within, points: [anchor, piece.center, ...grid].filter(within)};
    }

    drawMapBoundaries(svg, bounds, px, py, width, height) {
      if (!this.mapBoundaries) return false;
      const labels = [];
      const draw = (feature, regional) => {
        const projected = feature.polygons.map(polygon => polygon.map(ring => ring.map(([lon, lat]) => [px(lon), py(lat)])));
        const coordinates = projected.flat(2), xs = coordinates.map(p => p[0]), ys = coordinates.map(p => p[1]);
        if (Math.max(...xs) < 0 || Math.min(...xs) > width || Math.max(...ys) < 0 || Math.min(...ys) > height) return;
        const d = projected.map(polygon => polygon.map(ring => ring.map(([x,y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ") + " Z").join(" ")).join(" ");
        const path = svgEl("path", {d, class: regional ? "wse-region-boundary" : "wse-country-boundary", "fill-rule": "evenodd"});
        if (regional) { path.setAttribute("data-region-code", feature.code); path.setAttribute("data-region-country", feature.country); }
        const fullName = regional && feature.country === "USA" && feature.code === "DC" ? "District of Columbia" : feature.name;
        const title = svgEl("title"); title.textContent = `${fullName} (${feature.country})`; path.appendChild(title); svg.appendChild(path);
        const placement = this.visibleMapLabel(feature, projected, [px(feature.label[0]), py(feature.label[1])], width, height);
        if (placement) labels.push({feature, regional, fullName, ...placement});
      };
      (this.mapBoundaries.countries || []).forEach(feature => draw(feature, false));
      (this.mapBoundaries.regions || []).forEach(feature => draw(feature, true));
      const occupied = this.visibleSamples().filter(sample => this.validMapCoordinates(sample)).map(sample => {
        const x = px(Number(sample.longitude)), y = py(Number(sample.latitude));
        return {left:x-22, right:x+22, top:y-22, bottom:y+22};
      });
      labels.sort((a,b) => Number(b.regional) - Number(a.regional) || b.area - a.area).forEach(item => {
        const {feature, regional, fullName, span, points} = item;
        const texts = regional ? (feature.code === "DC" ? [feature.code] : [fullName, feature.code]) : [fullName];
        for (const text of texts) {
          if (!text || text.length * 6.5 > span * 1.2) continue;
          const halfWidth = text.length * 3.6 + 4;
          for (const [x,y] of points) {
            const box = {left:x-halfWidth, right:x+halfWidth, top:y-12, bottom:y+5};
            if (![[x-halfWidth+2,y-5],[x+halfWidth-2,y-5],[x,y-11],[x,y+3]].every(item.within)) continue;
            if (box.left < 8 || box.right > width - 8 || box.top < 8 || box.bottom > height - 8) continue;
            if (occupied.some(other => box.left < other.right && box.right > other.left && box.top < other.bottom && box.bottom > other.top)) continue;
            occupied.push(box);
            const label = svgEl("text", {x, y, "text-anchor":"middle", class:"wse-map-region-label", "data-label-region":regional ? feature.code : "", "aria-label":fullName});
            label.textContent = text; svg.appendChild(label); return;
          }
        }
      });
      return true;
    }

    renderMap() {
      const allVisible = this.visibleSamples();
      const geolocated = allVisible.filter(sample => this.validMapCoordinates(sample));
      const invalid = allVisible.filter(sample => sample.has_coordinates && !this.validMapCoordinates(sample)).length;
      const missing = allVisible.length - geolocated.length - invalid;
      const bounds = this.mapBounds();
      const [lonMin, lonMax, latMin, latMax] = bounds;
      const samples = geolocated.filter(sample => Number(sample.longitude) >= lonMin && Number(sample.longitude) <= lonMax &&
        Number(sample.latitude) >= latMin && Number(sample.latitude) <= latMax);
      const outside = geolocated.length - samples.length;
      this.mapCountNode.textContent = `${geolocated.length} geolocated · ${missing} without coordinates` +
        (invalid ? ` · ${invalid} invalid coordinates` : "") + (outside ? ` · ${outside} outside this view` : "");
      this.mapNode.innerHTML = "";

      const width = 900, height = 460;
      const extentLabel = this.mapView === "custom" ? "Custom view" : this.mapView === "world" ? "World" : this.mapView === "north-america" ? "North America" : "Sample area";
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"group", "aria-label":`Sampling locations: ${extentLabel}`});
      const {px, py} = this.mapProjection(bounds, width, height);
      if (!this.drawMapBoundaries(svg, bounds, px, py, width, height)) {
        const note = document.createElement("p");
        note.className = "wse-map-attribution";
        note.textContent = "Boundary data unavailable. Rebuild the report with map-boundaries.js.";
        this.mapNode.appendChild(note);
      }

      this.applyOutbreakLayer(svg);

      if (!samples.length && this.outbreakContext?.status !== "READY") {
        const label = svgEl("text", {x:width/2,y:height/2,"text-anchor":"middle",class:"wse-map-empty"});
        label.textContent = outside ? "No sample locations in this map extent; select Sample area or World" : "No valid coordinates available for the current filter";
        svg.appendChild(label);
        this.mapNode.appendChild(svg);
        return;
      }

      const groups = new Map();
      samples.forEach((sample) => {
        const key = `${Number(sample.latitude).toFixed(5)},${Number(sample.longitude).toFixed(5)}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(sample);
      });

      groups.forEach((members, key) => {
        const first = members[0];
        const cx = px(Number(first.longitude));
        const cy = py(Number(first.latitude));
        const radius = Math.min(18, 6 + Math.sqrt(members.length) * 2.5);
        const cluster = svgEl("g", {
          class:"wse-map-cluster",
          "data-sample-ids":members.map(s=>s.sample_id).join("|"),
          tabindex:0,
          role:"button",
          "aria-pressed":"false",
          "aria-label":`Select a sample at ${Number(first.latitude).toFixed(3)}, ${Number(first.longitude).toFixed(3)}; ${members.length} sample(s)`,
        });
        const halo = svgEl("circle", {cx,cy,r:radius+5,class:"wse-map-halo"});
        const bubble = svgEl("circle", {cx,cy,r:radius,fill:this.hostColorFor(first),class:"wse-map-bubble"});
        cluster.append(halo,bubble);
        if (members.length > 1) {
          const count = svgEl("text", {x:cx,y:cy+5,"text-anchor":"middle",class:"wse-map-cluster-count"});
          count.textContent = String(members.length);
          cluster.appendChild(count);
        }
        const title = svgEl("title");
        title.textContent = `${members.length} sample${members.length===1?"":"s"} at ${Number(first.latitude).toFixed(3)}, ${Number(first.longitude).toFixed(3)}\n` + members.map(s=>`${s.sample_id} · ${s.host}`).join("\n");
        cluster.appendChild(title);
        const choose = () => {
          const current = members.findIndex(sample => sample.sample_id === this.selectedSampleId);
          const next = current < 0 ? 0 : (current + 1) % members.length;
          this.selectSample(members[next].sample_id);
        };
        cluster.addEventListener("click", choose);
        cluster.addEventListener("keydown", (event) => { if(event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } });
        cluster.addEventListener("mouseenter", () => this.setHover(members[0].sample_id));
        cluster.addEventListener("mouseleave", () => this.clearHover());
        svg.appendChild(cluster);
      });

      this.mapNode.appendChild(svg);
    }

    renderMapSelection() {
      if (!this.mapSelectionNode) return;
      const sample = this.sampleById.get(this.selectedSampleId);
      if (!sample) {
        this.mapSelectionNode.innerHTML = '<p>Click a point to select a sample. A number shows how many samples share that location.</p>';
        return;
      }
      const key = item => `${Number(item.latitude).toFixed(5)},${Number(item.longitude).toFixed(5)}`;
      const colocated = this.validMapCoordinates(sample) ? this.visibleSamples().filter(item =>
        this.validMapCoordinates(item) && key(item) === key(sample)) : [];
      const bounds = this.mapBounds();
      const outside = this.validMapCoordinates(sample) && (Number(sample.longitude) < bounds[0] || Number(sample.longitude) > bounds[1] || Number(sample.latitude) < bounds[2] || Number(sample.latitude) > bounds[3]);
      const notice = this.hostFilter !== "ALL" && sample.host !== this.hostFilter
        ? "Selected sample is outside the current host filter."
        : !this.validMapCoordinates(sample) ? (this.selectedOutbreakState() ? `Sample location available at state level: ${this.outbreakContext.states[this.selectedOutbreakState()]}. No sample point is plotted; use the Zoom to state button to locate the outline.` : "Selected sample has no valid map coordinates.")
        : outside ? "Selected sample is outside this map view. Reset view to return to the sample area."
        : colocated.length > 1 ? `${colocated.length} samples share this point. Choose a sample below, or click the point again to cycle through them.`
        : "Selected on the linked timeline and available segment trees. Click this point again to clear selection.";
      this.mapSelectionNode.innerHTML = `
        <div class="wse-map-selection-heading">Selected sample: <strong>${esc(sample.sample_id)}</strong></div>
        <p>${esc(sample.host)} · ${esc(dateLabel(sample.collection_date))}</p>
        <p>${esc(notice)}</p>
        ${colocated.length > 1 ? `<div class="wse-map-sample-choices" role="group" aria-label="Samples at this location">${colocated.map(item =>
          `<button type="button" class="wse-map-sample-choice" data-sample-id="${esc(item.sample_id)}" aria-pressed="${item.sample_id === sample.sample_id}">${esc(item.sample_id)}</button>`
        ).join("")}</div>` : ""}
        ${sample.report_href ? `<a class="wse-map-report-link" href="${esc(sample.report_href)}">Open sample report →</a>` : ""}`;
      this.mapSelectionNode.querySelectorAll(".wse-map-sample-choice").forEach(button => {
        button.addEventListener("click", () => {
          this.selectedReferenceId = null;
          this.selectedSampleId = button.getAttribute("data-sample-id");
          this.hoverSampleId = null;
          this.updateSelection();
          const active = [...this.mapSelectionNode.querySelectorAll(".wse-map-sample-choice")]
            .find(item => item.getAttribute("data-sample-id") === this.selectedSampleId);
          if (active) active.focus({preventScroll: true});
        });
      });
    }

    outbreakEpoch(value) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
      const time = Date.parse(`${value}T00:00:00Z`);
      return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? time : null;
    }

    outbreakStateCode(value) {
      const text = String(value || "").trim().toLowerCase().replace(/^us-/, "");
      return Object.entries(this.outbreakContext?.states || {}).find(([code, name]) =>
        code.toLowerCase() === text || name.toLowerCase() === text)?.[0] || null;
    }

    syncOutbreakDates() {
      if (!this.outbreakFollow) return;
      const sample = this.sampleById.get(this.selectedSampleId);
      const time = this.outbreakEpoch(sample?.collection_date);
      const range = this.outbreakContext?.date_ranges?.[this.outbreakBasis] || {};
      this.outbreakStart = time === null ? range.min || "" : new Date(time - this.outbreakDays * 86400000).toISOString().slice(0, 10);
      this.outbreakEnd = time === null ? range.max || "" : new Date(time + this.outbreakDays * 86400000).toISOString().slice(0, 10);
    }

    outbreakView(scope = this.outbreakScope) {
      const context = this.outbreakContext;
      const sample = this.sampleById.get(this.selectedSampleId);
      let code = null, blocked = false, scopeLabel = "All U.S. states";
      if (scope === "sample" && sample) {
        const country = String(sample.country || "").trim().toUpperCase();
        if (!["US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"].includes(country)) {
          blocked = true;
          scopeLabel = "No automatic geographic match: sample country is outside the U.S. or not recorded. Choose a state or All U.S. states to browse.";
        } else {
          code = this.outbreakStateCode(sample.state);
          blocked = !code;
          scopeLabel = code ? `${context.states[code]} — state-level match to ${sample.sample_id}${this.validMapCoordinates(sample) ? "" : "; sample coordinates unavailable"}.` : "No automatic geographic match: sample state is missing or unrecognized. Choose a state to browse.";
        }
      } else if (scope !== "all" && scope !== "sample") {
        code = scope;
        scopeLabel = `${context.states[code] || code} — manually selected state`;
      } else if (scope === "sample") {
        scopeLabel = "All U.S. states — select a WINGS sample for state-level context.";
      }
      const scoped = blocked ? [] : context.records.filter(row => !code || row.state_code === code);
      const start = this.outbreakEpoch(this.outbreakStart), end = this.outbreakEpoch(this.outbreakEnd);
      const validWindow = start !== null && end !== null && start <= end;
      const undated = scoped.filter(row => !row[this.outbreakBasis]).length;
      const rows = validWindow ? scoped.filter(row => row[this.outbreakBasis] && row[this.outbreakBasis] >= this.outbreakStart && row[this.outbreakBasis] <= this.outbreakEnd) : [];
      rows.sort((a, b) => b[this.outbreakBasis].localeCompare(a[this.outbreakBasis]) || a.source_row - b.source_row);
      const counts = new Map();
      rows.forEach(row => { if (row.state_code) counts.set(row.state_code, (counts.get(row.state_code) || 0) + 1); });
      const range = context.date_ranges[this.outbreakBasis] || {};
      const outsideSnapshot = validWindow && range.min && range.max && (this.outbreakEnd < range.min || this.outbreakStart > range.max);
      return {rows, code, blocked, scopeLabel, start, end, validWindow, undated, counts, outsideSnapshot};
    }

    bindOutbreakControls() {
      if (!this.outbreakNode) return;
      this.outbreakNode.addEventListener("change", event => {
        const key = event.target.dataset.outbreakControl;
        if (!key) return;
        this.outbreakSelectedStart = "";
        this.outbreakSelectedEnd = "";
        if (key === "scope") { this.outbreakScope = event.target.value; this.mapStateCardDismissed = false; }
        if (key === "basis") this.outbreakBasis = event.target.value;
        if (key === "days") this.outbreakDays = Number(event.target.value);
        if (key === "lock") this.outbreakFollow = !event.target.checked;
        if (key === "start" || key === "end") {
          this.outbreakFollow = false;
          if (key === "start") this.outbreakStart = event.target.value;
          else this.outbreakEnd = event.target.value;
        }
        this.outbreakPage = 0;
        this.renderOutbreak();
      });
      this.outbreakNode.addEventListener("click", event => {
        const clearPeriod = event.target.closest("[data-outbreak-clear-period]");
        if (clearPeriod) {
          this.outbreakSelectedStart = "";
          this.outbreakSelectedEnd = "";
          this.outbreakPage = 0;
          this.renderOutbreak();
          return;
        }

        const button = event.target.closest("[data-outbreak-page]");
        if (!button) return;
        this.outbreakPage += Number(button.dataset.outbreakPage);
        this.renderOutbreak(true);
        this.outbreakNode.querySelector(".wse-outbreak-records summary")?.focus({preventScroll: true});
      });
    }

    renderOutbreak(forceRecordsOpen = false) {
      if (!this.outbreakNode) return;
      const context = this.outbreakContext;
      this.outbreakNode.hidden = context?.status !== "READY";
      if (this.outbreakNode.hidden) return;
      if (this.outbreakLastSampleId !== this.selectedSampleId) {
        this.mapStateCardDismissed = false;
        this.outbreakPage = 0;
        this.outbreakSelectedStart = "";
        this.outbreakSelectedEnd = "";
        if (this.outbreakLastSampleId !== undefined) this.outbreakScope = "sample";
        this.outbreakLastSampleId = this.selectedSampleId;
      }
      this.syncOutbreakDates();
      const view = this.outbreakView();
      const focusedControl = document.activeElement?.dataset?.outbreakControl;
      const recordsOpen = forceRecordsOpen || Boolean(this.outbreakNode.querySelector(".wse-outbreak-records")?.open);
      const advancedOpen = Boolean(this.outbreakNode.querySelector(".wse-outbreak-advanced")?.open);
      const aboutOpen = Boolean(this.outbreakNode.querySelector(".wse-outbreak-about")?.open);
      const selectedPeriodActive = Boolean(
        this.outbreakSelectedStart && this.outbreakSelectedEnd
      );

      const resultRows = selectedPeriodActive
        ? view.rows.filter(row => {
            const date = row[this.outbreakBasis];
            return date &&
              date >= this.outbreakSelectedStart &&
              date <= this.outbreakSelectedEnd;
          })
        : view.rows;

      const pages = Math.max(1, Math.ceil(resultRows.length / 25));
      this.outbreakPage = Math.max(0, Math.min(this.outbreakPage, pages - 1));
      const rows = resultRows.slice(
        this.outbreakPage * 25,
        (this.outbreakPage + 1) * 25
      );
      const option = (value, label, active) => `<option value="${esc(value)}"${value === active ? " selected" : ""}>${esc(label)}</option>`;
      const basisLabel = this.outbreakBasis === "collection_date" ? "collection date" : "detection date";

      const prettyOutbreakDate = value => {
        const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!match) return value || "";
        const [, year, month, day] = match;
        return new Intl.DateTimeFormat("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
          timeZone: "UTC",
        }).format(new Date(Date.UTC(
          Number(year),
          Number(month) - 1,
          Number(day)
        )));
      };
      const sample = this.sampleById.get(this.selectedSampleId);
      const sampleDate = this.outbreakEpoch(sample?.collection_date);
      const markerVisible = view.validWindow && sampleDate !== null && sampleDate >= view.start && sampleDate <= view.end;
      const sampleState = this.selectedOutbreakState();
      let sampleDateLabel = "No WINGS sample selected; no collection-date marker shown.";
      if (sample) {
        sampleDateLabel = `Selected WINGS sample: ${sample.sample_id} · Collected: ${sampleDate === null ? "unavailable" : sample.collection_date}`;
        if (sampleState) sampleDateLabel += ` · Sample state: ${context.states[sampleState]}`;
        sampleDateLabel += markerVisible ? ". Dashed line = this sample's collection date." : sampleDate === null ? ". No collection-date marker shown." : view.validWindow ? ". Collection date is outside the displayed window; no marker shown." : ". Enter a valid date window to show the marker.";
        if (view.code && view.code !== sampleState) {
          sampleDateLabel += sampleState
            ? ` Records shown are for ${context.states[view.code] || view.code}, a different state from the selected sample.`
            : ` Records shown are for ${context.states[view.code] || view.code}; the selected sample has no confirmed U.S. state match.`;
        }
      }
      const missingSampleDate = this.outbreakFollow && sample && sampleDate === null;
      const range = context.date_ranges[this.outbreakBasis] || {};

      let outbreakTakeaway;

      if (!view.validWindow) {
        outbreakTakeaway = "Choose a valid date range to view APHIS wild-bird records.";
      } else if (view.blocked && sample) {
        outbreakTakeaway = `Sample ${sample.sample_id} does not have a usable U.S. state match. Choose a state or All U.S. states to browse APHIS records.`;
      } else if (selectedPeriodActive) {
        const geography = view.code
          ? ` in ${esc(context.states[view.code] || view.code)}`
          : " nationwide";

        const period = this.outbreakSelectedStart === this.outbreakSelectedEnd
          ? ` on ${prettyOutbreakDate(this.outbreakSelectedStart)}`
          : ` from ${prettyOutbreakDate(this.outbreakSelectedStart)} through ${prettyOutbreakDate(this.outbreakSelectedEnd)}`;

        outbreakTakeaway = `<strong>${formatNumber(resultRows.length)} APHIS wild-bird records</strong>${geography}${period}.`;
      } else if (
        sample &&
        this.outbreakScope === "sample" &&
        sampleState &&
        sampleDate !== null &&
        this.outbreakFollow
      ) {
        outbreakTakeaway = `<strong>${formatNumber(view.rows.length)} APHIS wild-bird records</strong> in ${esc(context.states[sampleState] || sampleState)} within ±${this.outbreakDays} days of ${esc(sample.sample_id)}'s collection date (${prettyOutbreakDate(sample.collection_date)}).`;
      } else if (view.code) {
        outbreakTakeaway = `<strong>${formatNumber(view.rows.length)} APHIS wild-bird records</strong> in ${esc(context.states[view.code] || view.code)} from ${prettyOutbreakDate(this.outbreakStart)} through ${prettyOutbreakDate(this.outbreakEnd)}.`;
      } else {
        outbreakTakeaway = `<strong>${formatNumber(view.rows.length)} APHIS wild-bird records</strong> nationwide from ${prettyOutbreakDate(this.outbreakStart)} through ${prettyOutbreakDate(this.outbreakEnd)}.${sample ? "" : " Select a WINGS sample to focus on its state and collection date."}`;
      }

      this.outbreakNode.innerHTML = `
        <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Outbreak context</span><h3>APHIS wild-bird detections</h3></div><a href="${esc(context.source_url)}" target="_blank" rel="noopener noreferrer">Open APHIS source table ↗</a></div>
        <div class="wse-outbreak-body">
          <p class="wse-outbreak-caution"><strong>Context only:</strong> date and place overlap do not imply epidemiological linkage. Counts are APHIS source records, not unique outbreaks or prevalence.</p>

          <p class="wse-outbreak-takeaway" aria-live="polite">${outbreakTakeaway}</p>

          <div class="wse-outbreak-primary-controls">
            <label>Geography
              <select data-outbreak-control="scope">
                ${option("sample", "Follow selected sample (state)", this.outbreakScope)}
                ${option("all", "All U.S. states", this.outbreakScope)}
                ${Object.entries(context.states).sort((a,b) => a[1].localeCompare(b[1])).map(([code, name]) => option(code, name, this.outbreakScope)).join("")}
              </select>
            </label>
            <label>Window ±
              <select data-outbreak-control="days"${this.outbreakFollow ? "" : " disabled"}>
                ${[7,30,90,365].map(days => option(String(days), `${days} days`, String(this.outbreakDays))).join("")}
              </select>
            </label>
          </div>

          ${selectedPeriodActive ? `
            <div class="wse-outbreak-period-filter">
              <span>
                Source records filtered to
                <strong>${this.outbreakSelectedStart === this.outbreakSelectedEnd
                  ? prettyOutbreakDate(this.outbreakSelectedStart)
                  : `${prettyOutbreakDate(this.outbreakSelectedStart)} – ${prettyOutbreakDate(this.outbreakSelectedEnd)}`}</strong>.
                The timeline remains unchanged.
              </span>
              <button type="button" data-outbreak-clear-period>Show all dates</button>
            </div>
          ` : ""}

          <details class="wse-outbreak-advanced"${advancedOpen ? " open" : ""}>
            <summary>Advanced</summary>
            <div class="wse-outbreak-controls">
              <label>Date basis <select data-outbreak-control="basis">${option("collection_date", "Collection date", this.outbreakBasis)}${option("detected_date", "Date detected", this.outbreakBasis)}</select></label>
              <label><input type="checkbox" data-outbreak-control="lock"${this.outbreakFollow ? "" : " checked"}> Lock date window</label>
              <label>From <input type="date" data-outbreak-control="start" value="${esc(this.outbreakStart)}"></label>
              <label>Through <input type="date" data-outbreak-control="end" value="${esc(this.outbreakEnd)}"></label>
            </div>
          </details>

          ${view.outsideSnapshot ? '<p class="wse-outbreak-caution">This window is outside the date range represented in this snapshot. Zero matches do not establish absence of detections.</p>' : ""}

          <div class="wse-outbreak-timeline"></div>

          <details class="wse-outbreak-about"${aboutOpen ? " open" : ""}>
            <summary>About this context</summary>
            <div class="wse-outbreak-about-body">
              <p>${esc(view.scopeLabel)} ${missingSampleDate ? "Sample collection date unavailable; displaying the snapshot's full date range." : this.outbreakFollow && !sample ? "No selected sample; displaying the snapshot's full date range." : ""}</p>
              <p>${formatNumber(view.undated)} records in this geographic scope lack a usable ${basisLabel} and are excluded.</p>
              <p>Source precision: county/state. Map: state-level aggregates; shaded areas are not exact detection locations. State matching also applies when sample coordinates are absent. No distance-based linkage is calculated.</p>
              <p>The shared map shades all U.S. states for the chosen dates, including neighboring states. This timeline and the source records follow the geographic choice above. Click a shaded state to browse its records without changing the selected WINGS sample. Host filters affect sample points only.</p>
              <p>${markerVisible ? '<span class="wse-outbreak-sample-swatch" aria-hidden="true"></span>' : ""}${esc(sampleDateLabel)}</p>
              <p>${this.outbreakBasis === "collection_date" ? "Collection date is the sample collection date reported by APHIS." : "Date detected is the date of APHIS confirmatory testing; it can be later than collection."} Click a bar to filter the source records while keeping the full timeline visible. A dashed line marks the selected WINGS sample's collection date when it falls in this window.</p>
            </div>
          </details>
          <details class="wse-outbreak-records"${recordsOpen ? " open" : ""}><summary>Source records (${formatNumber(resultRows.length)})</summary>
            <p>CSV data-record numbers refer to this snapshot. APHIS supplies no unique record IDs or record-specific URLs; each source link opens the APHIS table. Repeated rows are retained.</p>
            <div class="wse-outbreak-table-wrap"><table><thead><tr><th>CSV record</th><th>State / county</th><th>Bird species</th><th>Collection date</th><th>Date detected</th><th>Source details</th></tr></thead><tbody>${rows.map(row => `
              <tr><td>${row.source_row}</td><td>${esc(row.state)} / ${esc(row.county || "Not recorded")}<small>Source precision: ${esc(row.geographic_precision)}</small></td><td>${esc(row.species)}</td><td>${esc(row.collection_date_raw)}</td><td>${esc(row.detected_date_raw)}</td><td><details><summary>Details</summary><p>Strain: ${esc(row.strain)}<br>Classification: ${esc(row.classification)}<br>Sampling method: ${esc(row.sampling_method)}<br>Submitting agency: ${esc(row.submitting_agency)}</p><p>Snapshot reference: ${esc(context.sha256.slice(0,12))}:${row.source_row}</p></details><a href="${esc(context.source_url)}" target="_blank" rel="noopener noreferrer" aria-label="Open APHIS source table for CSV record ${row.source_row}">APHIS table ↗</a></td></tr>`).join("") || '<tr><td colspan="6">No dated records match these filters in this snapshot.</td></tr>'}</tbody></table></div>
            <div class="wse-outbreak-pagination"><button type="button" data-outbreak-page="-1"${this.outbreakPage === 0 ? " disabled" : ""}>Previous</button><span>Page ${this.outbreakPage + 1} of ${pages}</span><button type="button" data-outbreak-page="1"${this.outbreakPage >= pages - 1 ? " disabled" : ""}>Next</button></div>
          </details>
          <details class="wse-outbreak-provenance"><summary>Snapshot and source provenance</summary><p>${formatNumber(context.record_count)} source rows; ${formatNumber(context.repeated_rows_retained)} identical repeat rows retained. Snapshot supplied: ${esc(context.snapshot_supplied_date || "Not recorded")} (${esc(context.snapshot_date_basis)}). This is an offline snapshot, not a live feed.</p><p>${esc(basisLabel)} range: ${esc(range.min || "Unavailable")} to ${esc(range.max || "Unavailable")}. Latest detection date in file: ${esc(context.date_ranges.detected_date.max || "Unavailable")}.</p><p>File: ${esc(context.source_file)}<br>SHA-256: <code>${esc(context.sha256)}</code></p>${context.unmapped_states.length ? `<p>States that cannot be mapped: ${esc(context.unmapped_states.join(", "))}. Their records remain available in All U.S. states.</p>` : ""}<p>Reporting can lag collection. No matching records does not mean no infections or no surveillance activity. The positive-record CSV does not provide a testing denominator.</p></details>
        </div>`;
      this.renderOutbreakTimeline(this.outbreakNode.querySelector(".wse-outbreak-timeline"), view);
      if (this.mapNode) {
        const focused = this.mapNode.contains?.(document.activeElement) ? document.activeElement : null;
        const sampleIds = focused?.getAttribute("data-sample-ids");
        const stateCode = focused?.getAttribute("data-region-code");
        this.renderMap();
        this.updateEmphasis();
        if (focused) {
          const match = [...this.mapNode.querySelectorAll("[data-sample-ids], [data-region-code]")].find(node =>
            sampleIds ? node.getAttribute("data-sample-ids") === sampleIds : stateCode && node.getAttribute("data-region-code") === stateCode);
          (match || this.mapNode).focus({preventScroll: true});
        }
      }
      if (focusedControl) this.outbreakNode.querySelector(`[data-outbreak-control="${focusedControl}"]`)?.focus({preventScroll: true});
    }

    selectedOutbreakState() {
      const sample = this.sampleById.get(this.selectedSampleId);
      if (!sample || !["US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"].includes(String(sample.country || "").trim().toUpperCase())) return null;
      return this.outbreakStateCode(sample.state);
    }

    mapFocusState() {
      return this.outbreakContext?.states?.[this.outbreakScope] ? this.outbreakScope : this.selectedOutbreakState();
    }

    showSelectedState() {
      const code = this.mapFocusState();
      const region = this.mapBoundaries?.regions.find(item => item.country === "USA" && item.code === code);
      if (!region) return;
      const points = region.polygons.flat(2), xs = points.map(point => point[0]), ys = points.map(point => point[1]);
      this.setMapViewport([Math.min(...xs) - 2, Math.max(...xs) + 2, Math.min(...ys) - 2, Math.max(...ys) + 2]);
    }

    renderMapStateCard(view) {
      if (!this.mapStateCardNode) return;
      const code = view.code;
      this.mapStateCardNode.hidden = !code || Boolean(this.mapStateCardDismissed);
      if (this.mapStateCardNode.hidden) return;
      const basis = this.outbreakBasis === "collection_date" ? "Collection date" : "Date detected";
      this.mapStateCardNode.innerHTML = `
        <button type="button" class="wse-state-card-close" data-state-action="close" aria-label="Close state summary">×</button>
        <strong>${esc(this.outbreakContext.states[code] || code)}</strong>
        <div class="wse-state-card-value">${view.validWindow ? `${formatNumber(view.rows.length)} APHIS source records` : "Choose a valid date window"}</div>
        <p>${esc(basis)}<br>${esc(this.outbreakStart)} through ${esc(this.outbreakEnd)}</p>
        <p>State-level aggregate. ${formatNumber(view.undated)} records excluded for missing ${basis.toLowerCase()}.</p>
        ${view.outsideSnapshot ? '<p>Window outside snapshot coverage; zero matches do not establish absence.</p>' : ""}
        <p>Context only; no implied epidemiological linkage.</p>
        <div class="wse-state-card-actions"><button type="button" data-state-action="zoom">Zoom to state</button><button type="button" data-state-action="records">View records</button></div>`;
    }

    applyOutbreakLayer(svg) {
      if (this.outbreakContext?.status !== "READY") return;
      this.syncOutbreakDates();
      // State browsing filters the timeline/records, never the neighboring map states.
      const view = this.outbreakView("all"), details = this.outbreakView();
      const selectedCode = this.selectedOutbreakState();
      const focusCode = this.mapFocusState();
      if (this.mapStateButtonNode) {
        this.mapStateButtonNode.disabled = !focusCode;
        this.mapStateButtonNode.textContent = focusCode ? `Zoom to ${this.outbreakContext.states[focusCode]}` : "Select a state to zoom";
        this.mapStateButtonNode.title = focusCode ? "Fit this state in the map without changing the selected WINGS sample" : "Click a state or select a WINGS sample with a recorded U.S. state";
      }
      this.renderMapStateCard(details);
      const max = Math.max(1, ...view.counts.values());
      const active = this.outbreakLayerEnabled && view.validWindow;
      svg.querySelectorAll('[data-region-country="USA"]').forEach(path => {
        const code = path.getAttribute("data-region-code"), count = view.counts.get(code) || 0;
        path.setAttribute("data-sample-state", String(code === selectedCode));
        path.setAttribute("data-context-state", String(code === details.code));
        if (!active) return;
        path.style.fill = count ? `hsl(178 48% ${88 - 53 * Math.log1p(count) / Math.log1p(max)}%)` : "#f1f3f4";
        path.classList.add("wse-outbreak-state");
        path.setAttribute("tabindex", "0"); path.setAttribute("role", "button");
        path.setAttribute("aria-label", `${this.outbreakContext.states[code] || code}: ${count} matching source records; state aggregate${code === selectedCode ? "; selected WINGS sample state" : ""}`);
        path.setAttribute("aria-pressed", String(code === details.code));
        const title = path.querySelector("title");
        if (title) title.textContent = `${this.outbreakContext.states[code] || code}: ${count} matching source records\nState-level aggregate; no exact detection locations${code === selectedCode ? "\nSelected WINGS sample state" : ""}`;
        const choose = () => {
          this.outbreakScope = code;
          this.mapStateCardDismissed = false;
          this.outbreakPage = 0;
          this.outbreakSelectedStart = "";
          this.outbreakSelectedEnd = "";
          this.renderOutbreak();
          this.outbreakNode.querySelector('[data-outbreak-control="scope"]')?.focus({preventScroll: true});
        };
        path.addEventListener("click", choose);
        path.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } });
      });
      // Redraw outlines above neighboring polygons so shared borders remain visible.
      const regionPaths = [...svg.querySelectorAll('[data-region-country="USA"]')];
      for (const [code, kind] of [[details.code !== selectedCode ? details.code : null, "context"], [selectedCode, "sample"]]) {
        const path = code && regionPaths.find(item => item.getAttribute("data-region-code") === code);
        if (path) svg.appendChild(svgEl("path", {d: path.getAttribute("d"), class: `wse-${kind}-state-outline`, "pointer-events": "none", "aria-hidden": "true"}));
      }
      if (this.mapLayerLegendNode) {
        this.mapLayerLegendNode.hidden = false;
        const basis = this.outbreakBasis === "collection_date" ? "Collection date" : "Date detected";
        this.mapLayerLegendNode.innerHTML = `
          <div><strong>WINGS samples:</strong> host-colored points; numbers show samples sharing coordinates. ${selectedCode ? `Solid burgundy outline = selected sample state (${esc(this.outbreakContext.states[selectedCode])}).` : ""}</div>
          <div><strong>APHIS:</strong> ${!this.outbreakLayerEnabled ? "State shading hidden; timeline and records remain available." : !view.validWindow ? "Enter a valid date window below to display state shading." : `<span class="wse-aphis-gradient" aria-hidden="true"></span> 0 (gray) to ${formatNumber(Math.max(0, ...view.counts.values()))} records (darkest teal). National relative scale; all U.S. states retain their counts.`}</div>
          <div>${esc(basis)} · ${esc(this.outbreakStart)} through ${esc(this.outbreakEnd)} · ${this.outbreakFollow ? "Following sample date" : "Date window locked"}. State-level context; no implied epidemiological linkage.</div>
          <div>Timeline / records: ${esc(details.scopeLabel)} Dashed outline = state being browsed. Non-U.S. areas are outside this APHIS layer's coverage; gray U.S. states have no matching dated records in this snapshot, not evidence of absence.</div>
          ${view.validWindow && view.outsideSnapshot ? '<div class="wse-outbreak-caution">Date window is outside the snapshot range; zero matches do not establish absence of detections.</div>' : ""}`;
      }
    }

    renderOutbreakTimeline(target, view) {
      if (!view.validWindow) { target.textContent = "Timeline unavailable until a valid date window is entered."; return; }
      const width = 900, height = 200, left = 65, right = 870, top = 25, bottom = 140;
      const svg = svgEl("svg", {viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": `APHIS records by ${this.outbreakBasis === "collection_date" ? "collection date" : "detection date"}`});
      const daily = (view.end - view.start) / 86400000 <= 90;
      const bins = new Map();
      view.rows.forEach(row => { const key = row[this.outbreakBasis].slice(0, daily ? 10 : 7); bins.set(key, (bins.get(key) || 0) + 1); });
      const max = Math.max(1, ...bins.values());
      const x = time => left + (time - view.start) / (view.end - view.start + 86400000) * (right - left);
      const label = (text, px, py, anchor = "middle") => { const node = svgEl("text", {x: px, y: py, "text-anchor": anchor, class: "wse-outbreak-axis"}); node.textContent = text; svg.appendChild(node); };
      [0, max].forEach(count => {
        const y = bottom - count / max * (bottom - top);
        svg.appendChild(svgEl("line", {x1:left, x2:right, y1:y, y2:y, class:"wse-outbreak-gridline"}));
        label(String(count), left - 8, y + 4, "end");
      });
      [...bins.entries()].sort().forEach(([key, count]) => {
        const start = this.outbreakEpoch(daily ? key : `${key}-01`);
        const date = new Date(start);
        const end = daily ? start + 86400000 : Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1);
        const from = Math.max(start, view.start), through = Math.min(end, view.end + 86400000);
        const binStart = new Date(from).toISOString().slice(0, 10);
        const binEnd = new Date(through - 86400000).toISOString().slice(0, 10);
        const selected =
          this.outbreakSelectedStart === binStart &&
          this.outbreakSelectedEnd === binEnd;

        const bar = svgEl("rect", {
          x:x(from),
          y:bottom - count / max * (bottom - top),
          width:Math.max(1, x(through) - x(from) - 1),
          height:count / max * (bottom - top),
          class:`wse-outbreak-bar${selected ? " is-selected" : ""}`,
          tabindex:0,
          role:"button",
          "aria-pressed":String(selected),
          "aria-label":`${key}: ${count} source records; ${selected ? "selected" : "filter source records to this period"}`
        });
        const title = svgEl("title"); title.textContent = `${key}: ${count} source records`; bar.appendChild(title);
        const choose = () => {
          if (selected) {
            this.outbreakSelectedStart = "";
            this.outbreakSelectedEnd = "";
          } else {
            this.outbreakSelectedStart = binStart;
            this.outbreakSelectedEnd = binEnd;
          }

          this.outbreakPage = 0;
          this.renderOutbreak(true);
          this.outbreakNode
            .querySelector(".wse-outbreak-records summary")
            ?.focus({preventScroll: true});
        };
        bar.addEventListener("click", choose);
        bar.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } });
        svg.appendChild(bar);
      });
      const sampleDate = this.outbreakEpoch(this.sampleById.get(this.selectedSampleId)?.collection_date);
      if (sampleDate !== null && sampleDate >= view.start && sampleDate <= view.end) {
        const line = svgEl("line", {x1:x(sampleDate + 43200000), x2:x(sampleDate + 43200000), y1:top - 6, y2:bottom, class:"wse-outbreak-sample-date"});
        const title = svgEl("title"); title.textContent = `Selected WINGS sample: ${this.selectedSampleId} · Collected: ${this.sampleById.get(this.selectedSampleId).collection_date}`; line.appendChild(title); svg.appendChild(line);
      }
      label(this.outbreakStart, left, bottom + 25, "start");
      label(this.outbreakEnd, right, bottom + 25, "end");
      label(`Source records per ${daily ? "day" : "month"} · ${this.outbreakBasis === "collection_date" ? "collection date" : "detection date"}`, (left + right) / 2, height - 8);
      if (!view.rows.length) label("No dated records match this window in the loaded snapshot", (left + right) / 2, 80);
      target.appendChild(svg);
    }

    treeLayout(root, width, height) {
      const leaves = [];
      let maxDistance = 0;
      const walk = (node, distance, depth) => {
        node._distance = distance;
        node._depth = depth;
        maxDistance = Math.max(maxDistance, distance);
        const children = node.children || [];
        if (!children.length) leaves.push(node);
        children.forEach((child) => walk(child, distance + Number(child.length || 0), depth + 1));
      };
      walk(root, 0, 0);
      const maxDepth = Math.max(1, ...leaves.map((leaf) => leaf._depth));
      const left = 22, right = 220, top = 20, bottom = 22;
      leaves.forEach((leaf, i) => { leaf._y = top + (i + 0.5) / leaves.length * (height - top - bottom); });
      const placeInternal = (node) => {
        const children = node.children || [];
        if (children.length) {
          children.forEach(placeInternal);
          node._y = children.reduce((sum,c)=>sum+c._y,0)/children.length;
        }
        const usable = width - left - right;
        node._x = left + (maxDistance > 0 ? node._distance / maxDistance : node._depth / maxDepth) * usable;
      };
      placeInternal(root);
      return {leaves, maxDistance, left, right, top, bottom};
    }

    segmentEvidence(sample, segment) {
      if (sample?.segments?.[segment]) return sample.segments[segment];
      const tree = this.payload.trees?.[segment];
      const tips = [];
      const visit = (node, parent) => {
        if (node.children?.length) node.children.forEach(child => visit(child, node));
        else if (node.sample_id === sample?.sample_id) {
          tips.push({name: node.name, parent_support: parent?.support == null ? null : String(parent.support)});
        }
      };
      if (tree?.root) visit(tree.root, null);
      return {record_status: "NOT_RECORDED", overall_status: "NOT_RECORDED", tips,
        tree_status: !tree ? "NO_TREE" : tips.length ? "PRESENT" : "ABSENT_FROM_TREE"};
    }

    treePresence(record) {
      if (record.tree_status === "NO_TREE") return "Tree unavailable";
      if (record.tree_status === "ABSENT_FROM_TREE") return "Sample absent from tree";
      const count = record.tips?.length || 0;
      return count > 1 ? `${count} matching tips — all highlighted` : "Sample present";
    }

    renderGenomeEvidence() {
      const sample = this.sampleById.get(this.selectedSampleId);
      if (!sample) {
        this.evidenceNode.innerHTML = this.samples.length
          ? '<p class="wse-empty">Select a sample to view its recorded genotype and highlight it across the segment trees.</p>'
          : '<p class="wse-empty">No samples are available.</p>';
        this.treeGridNode.querySelectorAll(".wse-tree-presence").forEach(node => { node.textContent = ""; });
        return;
      }
      const status = value => String(value || "NOT_RECORDED").replaceAll("_", " ");
      const genotype = sample.genotype || {status: "NOT_RECORDED", reason: "Rebuild the explorer data to include the recorded genotype."};
      const filtered = this.hostFilter !== "ALL" && sample.host !== this.hostFilter;
      this.evidenceNode.innerHTML = `
        <div class="wse-genotype"><strong>Recorded genotype: ${esc(genotype.call || status(genotype.status))}</strong><span>${esc(genotype.reason || "")}</span></div>
        ${filtered ? '<p class="wse-filter-notice">The selected sample is outside the host filter. Its genotype and tree highlights remain visible.</p>' : ""}
        `;
      this.treeGridNode.querySelectorAll(".wse-segment-tree").forEach(card => {
        card.querySelector(".wse-tree-presence").textContent = this.treePresence(this.segmentEvidence(sample, card.dataset.segment));
      });
    }

    referenceStatus(status) {
      return ({PRESENT: "Present in tree", NO_TREE: "Tree unavailable", NOT_IN_MANIFEST: "No metadata record for this segment", ABSENT_FROM_TREE: "Record supplied; tip absent from tree"})[status] || "Not recorded";
    }

    referenceLink(accession) {
      return /^[A-Z]{1,6}_?\d{5,12}\.\d+$/.test(accession || "")
        ? `<a href="https://www.ncbi.nlm.nih.gov/nuccore/${esc(accession)}" target="_blank" rel="noopener noreferrer">${esc(accession)} ↗</a>`
        : "Accession not recorded";
    }

    renderReferenceDetails() {
      if (!this.referenceNode) return;
      const context = this.referenceContext;
      if (!context) {
        this.referenceNode.innerHTML = '<p class="wse-reference-empty">Public reference metadata are not loaded. Existing tree tips are unchanged.</p>';
        return;
      }
      const ref = this.referenceById.get(this.selectedReferenceId);
      const known = value => esc(value || "Not recorded");
      const provenance = `<details class="wse-reference-provenance"><summary>Public reference provenance · ${this.references.length} reference groups · ${esc(context.record_count)} records</summary><p>Retrieved: ${known(context.retrieved_on)} · Manifest: ${known(context.source_file)}</p><p>Selection: ${known(context.selection_notes)}</p><p>Citation: ${known(context.citation)}</p><p>${esc(context.records_without_displayed_tips || 0)} manifest records have no displayed tip.</p><p>Manifest SHA-256: <code>${known(context.manifest_sha256)}</code></p>${Object.entries(this.payload.trees || {}).map(([segment, tree]) => `<p>${esc(segment)} tree: ${known(tree.source_file)} · SHA-256: <code>${known(tree.source_sha256)}</code></p>`).join("")}<p>Checksums identify the supplied files; they do not verify the submitter's metadata.</p></details>`;
      const legend = '<p class="wse-reference-legend">● WINGS sample (host color) · ■ Public reference (teal) · Gray circle: unannotated tip. Selecting a reference retains the selected WINGS sample for comparison. Tree proximity alone does not establish transmission.</p>';
      if (!ref) {
        this.referenceNode.innerHTML = legend + '<p>Select a teal square or choose a public reference to see its record and linked segments.</p>' + provenance;
        return;
      }
      const order = this.payload.segment_order || ["HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS"];
      this.referenceNode.innerHTML = legend + `<article class="wse-reference-card"><h4>Public reference · ${known(ref.isolate || ref.reference_id)}</h4><p>Reference ID: ${known(ref.reference_id)} · Host: ${known(ref.host)} · Location: ${known([ref.state, ref.country].filter(Boolean).join(", "))}</p><p>Collection date: ${known(ref.collection_date)} · Precision: ${known(ref.collection_date_precision)} · Segment linkage: ${known(ref.linkage_basis || "Single record; cross-segment identity not established")}</p><p>Public record metadata; WINGS raw-read QC and coverage are not available for this reference.</p><div class="wse-reference-segments">${order.map(segment => {
        const record = ref.segments?.[segment] || {};
        return `<div><strong>${esc(segment)}</strong><span>${esc(this.referenceStatus(record.status))}</span>${record.accession_version ? this.referenceLink(record.accession_version) : ""}${(record.tips || []).map(tip => `<small>Tip: ${esc(tip.name)}<br>Parent-node support (as recorded): ${known(tip.parent_support)}</small>`).join("")}</div>`;
      }).join("")}</div></article>` + provenance;
    }

    revealSelectedTips() {
      // Scroll inside each tree only; do not move the report viewport.
      this.root.querySelectorAll(".wse-tree").forEach(container => {
        if (container.hidden) return;
        const tip = [...container.querySelectorAll(".wse-tree-tip")].find(el => this.selectedReferenceId ? el.dataset.referenceId === this.selectedReferenceId : this.selectedSampleId && el.dataset.sampleId === this.selectedSampleId);
        if (!tip) return;
        const box = tip.getBoundingClientRect(), viewport = container.getBoundingClientRect();
        if (box.top < viewport.top || box.bottom > viewport.bottom) {
          container.scrollTop += box.top - viewport.top - container.clientHeight / 2;
        }
        if (box.left < viewport.left || box.right > viewport.right) {
          container.scrollLeft += box.left - viewport.left - container.clientWidth / 3;
        }
      });
    }

    renderTrees() {
      const all = this.treeMode === "all";
      this.treeNode.hidden = all;
      this.treeNoteNode.hidden = all;
      this.treeGridNode.hidden = !all;
      this.treeGridNode.innerHTML = "";
      if (!all) {
        this.renderTree(this.segment, this.treeNode, this.treeNoteNode);
        return;
      }
      this.treeNode.innerHTML = "";
      (this.payload.segment_order || ["HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS"]).forEach(segment => {
        const card = document.createElement("article");
        card.className = "wse-segment-tree";
        card.dataset.segment = segment;
        card.innerHTML = `<div class="wse-panel-heading"><h4>${esc(segment)}</h4><span class="wse-panel-note"></span></div><p class="wse-tree-presence"></p><div class="wse-tree" tabindex="0" role="region" aria-label="${esc(segment)} tree, scroll to explore"></div>`;
        this.treeGridNode.appendChild(card);
        this.renderTree(segment, card.querySelector(".wse-tree"), card.querySelector(".wse-panel-note"));
      });
    }

    renderTree(segment, target, note) {
      target.innerHTML = "";
      if (!segment || !this.payload.trees?.[segment]) {
        note.textContent = "Tree unavailable";
        target.innerHTML = `<div class="wse-empty">No segment phylogeny was supplied.</div>`;
        return;
      }
      const record = this.payload.trees[segment];
      const visibleIds = new Set(this.visibleSamples().map(s=>s.sample_id));
      note.textContent = `${segment} · ${record.tip_count} tips · ${record.source_file || "Source not recorded"}`;
      const tipCount = Math.max(1, record.tip_count || 1);
      const width = this.treeMode === "all" ? 640 : 900;
      const height = Math.max(this.treeMode === "all" ? 220 : 450, tipCount * 25 + 40);
      const root = JSON.parse(JSON.stringify(record.root));
      const layout = this.treeLayout(root, width, height);
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"group", "aria-label":`${segment} phylogeny`});

      const drawBranches = (node) => {
        const children = node.children || [];
        if (children.length) {
          const ys = children.map(c=>c._y);
          svg.appendChild(svgEl("line", {x1:node._x,y1:Math.min(...ys),x2:node._x,y2:Math.max(...ys),class:"wse-tree-branch"}));
          children.forEach((child) => {
            const branch = svgEl("line", {x1:node._x,y1:child._y,x2:child._x,y2:child._y,class:"wse-tree-branch"});
            if (child.sample_id) branch.setAttribute("data-sample-id", child.sample_id);
            if (child.reference_id) branch.setAttribute("data-reference-id", child.reference_id);
            svg.appendChild(branch);
            if (child.label && /^[0-9]+(?:\.[0-9]+)?(?:\/[0-9]+(?:\.[0-9]+)?)*$/.test(child.label) && child.children?.length) {
              const support = svgEl("text", {x:(node._x+child._x)/2,y:child._y-4,"text-anchor":"middle",class:"wse-support-label"});
              support.textContent = child.label;
              svg.appendChild(support);
            }
            drawBranches(child);
          });
        }
      };
      drawBranches(root);

      layout.leaves.forEach((leaf) => {
        const sample = this.sampleById.get(leaf.sample_id);
        const reference = this.referenceById.get(leaf.reference_id);
        const visible = !sample || visibleIds.has(leaf.sample_id);
        const group = svgEl("g", {
          class:`wse-tree-tip${reference ? " wse-public-tip" : ""}${visible ? "" : " is-filtered"}`,
          "data-sample-id":leaf.sample_id || "",
          "data-reference-id":reference ? leaf.reference_id : "",
          tabindex: sample || reference ? 0 : -1,
          role: sample || reference ? "button" : "img",
          "aria-label": sample ? `Select ${sample.sample_id}; tip ${leaf.name}` : reference ? `Select public reference ${reference.reference_id}; accession ${leaf.accession_version}` : `Unannotated tip ${leaf.name}`,
        });
        const dot = reference ? svgEl("rect", {x:leaf._x+2,y:leaf._y-5,width:10,height:10,fill:"#007C83",class:"wse-tree-tip-dot"}) : svgEl("circle", {cx:leaf._x+7,cy:leaf._y,r:4.8,fill:sample?this.hostColorFor(sample):GRAY,class:"wse-tree-tip-dot"});
        const label = svgEl("text", {x:leaf._x+18,y:leaf._y+4,class:"wse-tree-tip-label"});
        label.textContent = sample ? sample.sample_id : reference ? leaf.accession_version : leaf.name;
        group.append(dot,label);
        if (leaf.sample_id) {
          group.addEventListener("click", () => this.selectSample(leaf.sample_id));
          group.addEventListener("mouseenter", () => this.setHover(leaf.sample_id));
          group.addEventListener("mouseleave", () => this.clearHover());
          group.addEventListener("keydown", (event) => { if(event.key === "Enter" || event.key === " ") { event.preventDefault(); this.selectSample(leaf.sample_id); } });
        }
        if (reference) {
          group.addEventListener("click", () => this.selectReference(leaf.reference_id));
          group.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); this.selectReference(leaf.reference_id); } });
        }
        const title = svgEl("title");
        title.textContent = sample ? `${sample.sample_id}\n${sample.host} · ${dateLabel(sample.collection_date)}\nTip: ${leaf.name}` : reference ? `Public reference: ${reference.reference_id}\n${leaf.accession_version}\n${reference.host || "Host not recorded"} · ${reference.collection_date || "Date not recorded"}\nTip: ${leaf.name}` : `Unannotated tip: ${leaf.name}`;
        group.appendChild(title);
        svg.appendChild(group);
      });

      if (layout.maxDistance > 0) {
        const scaleY = height - 10;
        const x0 = layout.left, x1 = layout.left + Math.min(120, width - layout.left - layout.right);
        svg.appendChild(svgEl("line", {x1:x0,y1:scaleY,x2:x1,y2:scaleY,class:"wse-tree-scale"}));
        const scaleValue = layout.maxDistance * ((x1-x0)/(width-layout.left-layout.right));
        const text = svgEl("text", {x:(x0+x1)/2,y:scaleY-5,"text-anchor":"middle",class:"wse-tree-scale-label"});
        text.textContent = `${scaleValue.toPrecision(2)} substitutions/site`;
        svg.appendChild(text);
      }
      target.appendChild(svg);
    }

    updateSelection() {
      const select = this.genomeControlsNode.querySelector(".wse-sample-select");
      if (select) select.value = this.selectedSampleId || "";
      this.renderSelected();
      this.renderMapSelection();
      this.renderOutbreak();
      this.renderGenomeEvidence();
      this.renderReferenceDetails();
      const refSelect = this.genomeControlsNode.querySelector(".wse-reference-select");
      if (refSelect) refSelect.value = this.selectedReferenceId || "";
      this.renderEbird();
      this.renderEcology();
      this.updateEmphasis();
      this.revealSelectedTips();
    }

    updateEmphasis() {
      const focus = this.selectedSampleId;
      this.root.querySelectorAll("[data-sample-id]").forEach((el) => {
        const id = el.getAttribute("data-sample-id");
        el.classList.toggle("is-selected", Boolean(focus && id === focus));
        el.classList.toggle("is-hovered", Boolean(this.hoverSampleId && id === this.hoverSampleId));
        if (el.classList.contains("wse-tree-tip") && id) el.setAttribute("aria-pressed", String(id === focus));
      });
      this.root.querySelectorAll("[data-reference-id]").forEach(el => {
        const id = el.getAttribute("data-reference-id");
        if (!id) return;
        const selected = Boolean(this.selectedReferenceId && id === this.selectedReferenceId);
        el.classList.toggle("is-selected", selected);
        if (el.classList.contains("wse-tree-tip")) el.setAttribute("aria-pressed", String(selected));
      });
      this.root.querySelectorAll("[data-sample-ids]").forEach((el) => {
        const ids = (el.getAttribute("data-sample-ids") || "").split("|");
        el.classList.toggle("is-selected", Boolean(focus && ids.includes(focus)));
        el.setAttribute("aria-pressed", String(Boolean(focus && ids.includes(focus))));
      });
    }
  }

  const initialize = () => {
    document.querySelectorAll(".wings-surveillance-explorer").forEach((root, index) => {
      if (root.dataset.wseRendered === "true") return;
      const dataId = root.dataset.wseDataId || `wings-surveillance-data-${index}`;
      const script = document.getElementById(dataId);
      if (!script) return;
      let payload;
      try { payload = JSON.parse(script.textContent || "{}"); } catch (error) {
        root.innerHTML = `<div class="wse-error">Surveillance Explorer data could not be parsed.</div>`;
        return;
      }
      root.dataset.wseRendered = "true";
      const explorer = new Explorer(root, payload);
      // WINGS_BRAID_CLOCK_HOOK_BEGIN
      try {
        globalThis.WINGS_BRAID_CLOCK.mountExplorer(explorer);
        // WINGS_EXPLORER_TABS_HOOK_BEGIN
        globalThis.WINGS_EXPLORER_TABS.mount(explorer);
        // WINGS_EXPLORER_TABS_HOOK_END
        // WINGS_TREE_STUDIO_HOOK_BEGIN
        globalThis.WINGS_TREE_STUDIO.mountExplorer(explorer);
        // WINGS_TREE_STUDIO_HOOK_END
      } catch (error) {
        const notice = document.createElement("p");
        notice.className = "wbc-preview-error";
        notice.setAttribute("role", "status");
        notice.textContent = "Genome Braid / Ecological Clock unavailable: " + error.message;
        root.appendChild(notice);
        console.error("WINGS optional observatory preview:", error);
      }
      // WINGS_BRAID_CLOCK_HOOK_END
    });
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, {once:true});
  else initialize();
})();
