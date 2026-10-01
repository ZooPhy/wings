(() => {
  "use strict";

  const VERSION = "0.1.2";

  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const TAB_ORDER = ["overview", "genome", "ecology", "outbreak"];
  const TAB_LABELS = {
    overview: "Overview",
    genome: "Genome",
    ecology: "Ecology",
    outbreak: "Outbreak context",
  };

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

    if (outbreak) {
      panels.outbreak.append(outbreak);
    } else {
      panels.outbreak.append(make("p", "wse-app-empty", "No outbreak-context panel is available for this run."));
    }

    app.append(toolbar, nav, shared, views);
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
      explorer.hostFilter = hostSelect.value || "ALL";
      explorer.renderTimeline?.();
      explorer.renderMap?.();
      explorer.renderLegend?.();
      explorer.renderTrees?.();
      explorer.updateSelection();
    });

    clearButton.addEventListener("click", () => {
      explorer.selectedSampleId = null;
      explorer.selectedReferenceId = null;
      explorer.hoverSampleId = null;
      explorer.updateSelection();
    });

    const sync = () => {
      sampleSelect.value = explorer.selectedSampleId || "";
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
      if (treeDetails.open) requestAnimationFrame(() => explorer.renderTrees?.());
    });

    sync();
    activate("overview");
    // Tree Studio mounts after this function returns; catch that insertion once.
    setTimeout(placeTreeStudio, 0);

    const api = { VERSION, activate, get active() { return active; }, buttons, panels };
    explorer.explorerTabs = api;
    return api;
  }

  globalThis.WINGS_EXPLORER_TABS = { VERSION, TAB_ORDER: [...TAB_ORDER], mount };
})();
