/* WINGS_SAMPLE_NAVIGATION_V1 — existing section anchors and return link. */
(() => {
  "use strict";
  const GROUPS = [
    {id: "processing", label: "Read processing", sections: [["read-processing", "Read processing"]]},
    {id: "evidence", label: "Sequence evidence", sections: [
      ["segment-qc", "Segment QC"], ["influenza-subtype-evidence", "Influenza subtype evidence"],
      ["blast-top-hits", "BLAST top hits"],
      ["genoflu-genotype", "GenoFLU genotype"], ["vadr-annotation-quality-control", "VADR annotation QC"],
    ]},
    {id: "outputs", label: "Outputs & provenance", sections: [
      ["consensus-and-variant-files", "Consensus & variant files"],
      ["pipeline-provenance", "Pipeline provenance"],
    ]},
  ];

  function mount(main) {
    if (!main) return null;
    if (main.wingsSampleNavigation) return main.wingsSampleNavigation;
    const targets = {}, buttons = {}, groups = [];
    const primary = document.getElementById("sample-metadata") || main;
    if (!primary.id) primary.id = "wings-sample-overview";
    targets.metadata = primary;
    const add = (id, label, target) => {
      const link = document.createElement("a");
      link.className = "wse-app-tab";
      link.id = "wings-sample-section-" + id;
      link.href = "#" + encodeURIComponent(target.id);
      link.textContent = label;
      targets[id] = target;
      buttons[id] = link;
    };
    add("metadata", "Sample metadata", primary);
    for (const group of GROUPS) {
      const views = [];
      for (const [id, label] of group.sections) {
        const target = document.getElementById(id);
        if (!target || !main.contains(target)) continue;
        add(id, label, target);
        views.push(id);
      }
      if (views.length) groups.push({id: group.id, label: group.label, views});
    }
    // Keep any additional headings supplied by a newer or older report.
    const toc = document.getElementById("TOC");
    const extra = [];
    for (const link of toc?.querySelectorAll('a[href^="#"]') || []) {
      let id;
      try { id = decodeURIComponent(link.getAttribute("href").slice(1)); } catch { continue; }
      if (["irma-candidate-selection", "interpretation"].includes(id)) continue;
      if (Object.values(targets).some(target => target.id === id)) continue;
      const target = document.getElementById(id);
      if (!target || !main.contains(target)) continue;
      add(id, link.textContent.trim(), target);
      extra.push(id);
    }
    if (extra.length) groups.push({id: "additional", label: "More details", views: extra});
    const list = document.createElement("div");
    list.className = "wse-app-tabs";
    const navigation = globalThis.WINGS_VIEW_NAVIGATOR.mount(list, buttons, {
      primary: "metadata", groups, mode: "sections", label: "Sample report sections", toggleLabel: "Explore sample",
      kicker: "WINGS / SAMPLE", heading: "Sample report",
    });
    const back = document.createElement("a");
    back.className = "wse-sample-back";
    back.href = "../../run_summary/run_summary.html";
    back.textContent = "← Back to run summary";
    back.setAttribute("data-wings-run-summary", "true");
    navigation.element.prepend(back);
    const workspace = document.createElement("div");
    workspace.className = "wse-explorer-workspace wse-sample-workspace";
    const content = document.createElement("div");
    content.className = "wse-sample-content";
    const existing = Array.from(main.childNodes);
    content.append(...existing);
    workspace.append(navigation.element, content);
    main.append(workspace);
    document.body.classList.add("wings-sample-navigated");
    if (toc) (toc.closest(".sidebar") || toc).hidden = true;
    let active = "metadata";
    const select = (name, keyboard = false) => {
      if (!buttons[name]) return;
      active = name;
      for (const [id, link] of Object.entries(buttons)) {
        if (id === name) link.setAttribute("aria-current", "location"); else link.removeAttribute("aria-current");
      }
      navigation.select(name, keyboard);
    };
    const visit = (name, keyboard = false) => {
      select(name, keyboard);
      targets[name].scrollIntoView({block: "start", behavior: "auto"});
      if (keyboard) buttons[name].focus();
    };
    for (const [name, link] of Object.entries(buttons)) {
      link.addEventListener("click", event => { event.preventDefault(); visit(name); });
      link.addEventListener("keydown", event => {
        const order = navigation.visibleViews(), index = order.indexOf(name);
        let next;
        if (["ArrowDown", "ArrowRight"].includes(event.key)) next = order[(index + 1) % order.length];
        if (["ArrowUp", "ArrowLeft"].includes(event.key)) next = order[(index - 1 + order.length) % order.length];
        if (event.key === "Home") next = order[0];
        if (event.key === "End") next = order[order.length - 1];
        if (next) { event.preventDefault(); visit(next, true); }
      });
    }
    let pending = false;
    globalThis.addEventListener?.("scroll", () => {
      if (pending || typeof requestAnimationFrame !== "function") return;
      pending = true;
      requestAnimationFrame(() => {
        pending = false;
        let name = "metadata", nearest = -Infinity;
        for (const [id, target] of Object.entries(targets)) {
          const top = target.getBoundingClientRect().top;
          if (top <= 140 && top > nearest) { name = id; nearest = top; }
        }
        if (name !== active) select(name, true);
      });
    }, {passive: true});
    select("metadata");
    const api = {navigation, buttons, targets, back, visit, get active() { return active; }};
    main.wingsSampleNavigation = api;
    return api;
  }

  function initialize() {
    mount(document.querySelector("main.content") || document.querySelector("main"));
  }
  globalThis.WINGS_SAMPLE_NAVIGATION = {mount, initialize};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, {once: true});
  else initialize();
})();
