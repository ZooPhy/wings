(() => {
  "use strict";

  const VERSION = "0.4.0";

  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const TAB_ORDER = ["overview", "genome", "amino", "genotypes", "ecology", "coverage", "concordance", "outbreak"];
  const TAB_LABELS = {
    overview: "Overview",
    genome: "Genome",
    amino: "Amino acids",
    genotypes: "Genotype frequencies",
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

  function mountGenotypeDashboard(explorer, panel) {
    const id = explorer.root.dataset.wseGenotypeTemplateId;
    const template = id ? document.getElementById(id) : null;
    const original = template?.content?.querySelector("iframe");
    if (!original) {
      panel.append(make("p", "wse-app-empty", "Public genotype frequencies were not embedded in this report. Rebuild the run summary with a public genotype snapshot."));
      return null;
    }
    const frame = original.cloneNode(true);
    panel.append(frame);
    const refresh = () => frame.contentWindow?.postMessage({type:"wings-genotype-measure"}, "*");
    frame.addEventListener("load", refresh);
    globalThis.addEventListener("message", event => {
      if (event.source !== frame.contentWindow || event.data?.type !== "wings-genotype-height") return;
      const height = event.data.height;
      if (typeof height !== "number" || !Number.isFinite(height) || height < 200 || height > 20000) return;
      frame.style.height = `${Math.max(400, Math.ceil(height))}px`;
    });
    refresh();
    return {refresh};
  }

  // WINGS_AMINO_EXPLORER_TAB_V1
  function mountAminoDashboard(explorer, panel) {
    const id = explorer.root.dataset.wseAminoTemplateId || "wings-amino-acid-dashboard-0";
    const template = document.getElementById(id);
    const legacy = document.getElementById("amino-acid-cohort-demo") || document.querySelector?.('section[aria-label="Amino acid changes"]');
    const original = template?.content?.querySelector("iframe") || legacy?.querySelector("iframe");
    if (!original) {
      panel.append(make("p", "wse-app-empty", "Amino acid results are not embedded in this report. Generate the amino acid report and rebuild the run summary."));
      return null;
    }
    let frame = null;
    const refresh = () => {
      if (!frame) {
        frame = original.cloneNode(true);
        frame.title = "WINGS amino acid landscape";
        frame.style.display = "block";
        frame.style.width = "100%";
        frame.style.height = "1000px";
        frame.style.border = "0";
        frame.setAttribute("loading", "eager");
        frame.addEventListener("load", () => frame.contentWindow?.postMessage({type:"wings-amino-measure"}, "*"));
        panel.append(frame);
      }
      frame.contentWindow?.postMessage({type:"wings-amino-measure"}, "*");
    };
    globalThis.addEventListener("message", event => {
      if (!frame || event.source !== frame.contentWindow || event.data?.type !== "wings-amino-height") return;
      const height = event.data.height;
      if (typeof height !== "number" || !Number.isFinite(height) || height < 200 || height > 30000) return;
      frame.style.height = `${Math.max(400, Math.ceil(height) + 16)}px`;
    });
    // Preserve one copy of the report and its sample/filter state across tab changes.
    if (legacy && original.parentElement) {
      original.remove();
      legacy.remove();
    }
    return {refresh};
  }

  function mount(explorer) {
    if (!explorer || !explorer.root) throw new Error("Explorer instance is required.");
    if (explorer.explorerTabs) return explorer.explorerTabs;

    const root = explorer.root;
    const shell = root.querySelector(".wse-shell");
    if (!shell) throw new Error("WINGS Explorer shell not found.");

    const timeline = shell.querySelector(".wse-timeline-panel");
    const mainGrid = shell.querySelector(".wse-main-grid");
    const subtitle = shell.querySelector(".wse-subtitle");
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
    const sampleLabelText = make("span", "wse-app-control-label", "Sample");
    sampleLabel.append(sampleLabelText);
    const sampleSelect = make("select", "wse-app-sample");
    sampleSelect.setAttribute("aria-label", "Selected WINGS sample");
    sampleSelect.append(new Option("Select a sample…", ""));
    for (const sample of explorer.samples || []) {
      sampleSelect.append(new Option(sample.sample_id, sample.sample_id));
    }
    sampleLabel.append(sampleSelect);

    const hostLabel = make("label", "wse-app-control");
    hostLabel.append(make("span", "wse-app-control-label", "Browse samples by host"));
    const hostSelect = make("select", "wse-app-host");
    hostSelect.setAttribute("aria-label", "Browse samples by host");
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

    const navigation = globalThis.WINGS_VIEW_NAVIGATOR.mount(nav, buttons);

    panels.coverage.append(timeline, mainGrid);

    const shared = make("div", "wse-app-shared");
    shared.hidden = true;
    if (braid) shared.append(braid);

    const treeDetails = make("details", "wse-genome-details");
    const treeSummary = make("summary", "wse-genome-details-summary", "Individual segment trees and QC evidence");
    treeDetails.append(treeSummary, genome);
    panels.genome.append(treeDetails);
    if (genomeFooter) panels.genome.append(genomeFooter);

    panels.ecology.append(ecology);
    const migrationContext = make("div", "wse-ecology-migration-context");
    panels.ecology.append(migrationContext);
    const migrationModule = globalThis.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE;
    if (migrationModule?.mountMigrationContext) {
      explorer.migrationContextController = migrationModule.mountMigrationContext(explorer, migrationContext);
    } else migrationContext.hidden = true;

    const aminoDashboard = mountAminoDashboard(explorer, panels.amino);
    const genotypeDashboard = mountGenotypeDashboard(explorer, panels.genotypes);


    if (panels.concordance) {

      const module = globalThis.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE;

      if (module?.mount) explorer.concordanceController = module.mount(explorer, panels.concordance);

      else panels.concordance.append(make("p", "wse-app-empty", "Genomic–Ecological Concordance is unavailable for this report."));

    }

    if (outbreak) {
      panels.outbreak.append(outbreak);
    } else {
      panels.outbreak.append(make("p", "wse-app-empty", "No outbreak-context panel is available for this run."));
    }

    const workspace = make("div", "wse-explorer-workspace");
    root.insertBefore(workspace, shell);
    workspace.append(navigation.element, shell);
    globalThis.WINGS_EVIDENCE_SYNTHESIS.mount(explorer, app);
    const overviewBrief = app.querySelector(".wse-evidence-synthesis");
    app.append(toolbar);
    if (subtitle) app.append(subtitle);
    app.append(shared, views);
    shell.append(app);

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

    // Keep the existing host control beside the timing table in Ecology.
    // Its permanent dock survives the table's innerHTML refreshes.
    const timingSummary = braid?.querySelector(".wbc-run-seasonal-summary");
    let timingHostDock = null, timingSection = null;
    if (timingSummary) {
      timingSection = make("div", "wse-timing-table-section");
      timingHostDock = make("div", "wse-timing-host-controls");
      timingSummary.parentElement.insertBefore(timingSection, timingSummary);
      timingSection.append(timingHostDock, timingSummary);
    }

    const activate = (name, focus = false) => {
      if (!TAB_ORDER.includes(name)) return;
      active = name;
      root.dataset.wseActiveTab = name;
      const hostAtTable = name === "ecology" && Boolean(timingHostDock);
      if (hostAtTable) timingHostDock.append(hostLabel);
      else toolbar.insertBefore(hostLabel, clearButton);
      if (timingHostDock) timingHostDock.hidden = !hostAtTable;
      // Move the original sample controls below the table only in Ecology.
      // The selected-sample banner stays in its shared position above the app.
      if (hostAtTable) timingSection.append(toolbar);
      else app.insertBefore(toolbar, subtitle || shared);
      toolbar.classList.toggle("wse-host-at-table", hostAtTable);
      sampleLabelText.textContent = hostAtTable ? "Sample for seasonal curve" : "Sample";
      toolbar.hidden = name === "genotypes" || name === "overview";
      if (name === "amino") toolbar.hidden = true;
      if (name === "amino") requestAnimationFrame(() => aminoDashboard?.refresh());
      // Explicit display prevents the toolbar grid rule from overriding hidden.
      toolbar.style.display = toolbar.hidden ? "none" : "";
      if (subtitle) subtitle.hidden = name !== "coverage";
      if (name === "genotypes") requestAnimationFrame(() => genotypeDashboard?.refresh());
      // Keep the run brief above the shared controls, but only on Overview.
      if (overviewBrief) overviewBrief.hidden = name !== "overview";
      for (const key of TAB_ORDER) {
        const selected = key === name;
        buttons[key].setAttribute("aria-selected", String(selected));
        buttons[key].tabIndex = selected ? 0 : -1;
        panels[key].hidden = !selected;
      }
      navigation.select(name, focus);
      if (focus) buttons[name].focus();
      if (name === "coverage") {
        requestAnimationFrame(() => {
          explorer.renderMap?.();
          explorer.updateEmphasis?.();
        });
      }
      const showShared = Boolean(braid) && (name === "genome" || name === "ecology");
      shared.hidden = !showShared;
      if (braid) braid.dataset.wseLens = showShared ? name : "";
      placeTreeStudio();
      if (showShared) {
        requestAnimationFrame(() => explorer.braidClock?.refresh?.());
      }
    };

    for (const [name, button] of Object.entries(buttons)) {
      button.addEventListener("click", () => activate(name));
      button.addEventListener("keydown", (event) => {
        const order = navigation.visibleViews();
        const index = order.indexOf(name);
        let next = null;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") next = order[(index + 1) % order.length];
        if (event.key === "ArrowUp" || event.key === "ArrowLeft") next = order[(index - 1 + order.length) % order.length];
        if (event.key === "Home") next = order[0];
        if (event.key === "End") next = order[order.length - 1];
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

    });

    clearButton.addEventListener("click", () => {
      explorer.selectedSampleId = null;
      explorer.selectedReferenceId = null;
      explorer.selectedTreeTip = null;
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
      clearButton.disabled = !explorer.selectedSampleId && !explorer.selectedReferenceId && !explorer.selectedTreeTip;
      const sample = explorer.selectedSampleId ? explorer.sampleById?.get(explorer.selectedSampleId) : null;
      if (explorer.selectedTreeTip) {
        context.textContent = `Tree tip: ${explorer.selectedTreeTip.name} · ${explorer.selectedTreeTip.segment}`;
      } else if (explorer.selectedReferenceId) {
        const reference = explorer.referenceById?.get(explorer.selectedReferenceId);
        context.textContent = `Public reference: ${reference?.isolate || explorer.selectedReferenceId}${sample ? ` · WINGS comparison: ${sample.sample_id}` : ""}`;
      } else if (sample) {
        const parts = [sample.sample_id, sample.host, sample.collection_date, sample.genotype?.call].filter(Boolean);
        context.textContent = parts.join(" · ");
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

  globalThis.WINGS_EXPLORER_TABS = { VERSION, TAB_ORDER: [...TAB_ORDER], mount, _test:{aggregateCoverageRecords,coverageComparison,mountGenotypeDashboard,mountAminoDashboard} };
})();
