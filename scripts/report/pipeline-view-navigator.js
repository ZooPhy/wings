/* WINGS_PIPELINE_NAVIGATION_V1 — reuse existing Quarto panels and controls. */
(() => {
  "use strict";
  const DEFINITIONS = [
    ["summary", "Run Summary"],
    ["samples", "Sample Detail"],
    ["distribution", "Subtype/Genotype Distribution"],
    ["coverage", "Genome Coverage"],
  ];
  const normalized = text => text.trim().replace(/\s+/g, " ").toLowerCase();

  function mount(tabset) {
    if (!tabset) return null;
    if (tabset.wingsPipelineNavigation) return tabset.wingsPipelineNavigation;
    const nativeNav = Array.from(tabset.children).find(node => node.classList.contains("nav-tabs"));
    const content = Array.from(tabset.children).find(node => node.classList.contains("tab-content"));
    if (!nativeNav || !content) return null;
    const originalLinks = Array.from(nativeNav.querySelectorAll('[role="tab"]'));
    if (originalLinks.length !== DEFINITIONS.length) return null;
    const buttons = {}, panels = {};
    for (const [name, label] of DEFINITIONS) {
      const link = originalLinks.find(node => normalized(node.textContent) === normalized(label));
      if (!link) return null;
      const panel = Array.from(content.children).find(node => node.id === link.getAttribute("aria-controls"));
      if (!panel) return null;
      buttons[name] = link;
      panels[name] = panel;
    }
    const nav = document.createElement("div");
    nav.className = "wse-app-tabs";
    nav.setAttribute("role", "tablist");
    nav.setAttribute("aria-label", "Pipeline Results views");
    for (const [name] of DEFINITIONS) {
      buttons[name].classList.add("wse-app-tab");
      panels[name].setAttribute("aria-labelledby", buttons[name].id);
    }
    const navigation = globalThis.WINGS_VIEW_NAVIGATOR.mount(nav, buttons, {
      primary: "summary",
      groups: [{id: "results", label: "Results", views: ["samples", "distribution", "coverage"]}],
      label: "Pipeline Results navigation",
      toggleLabel: "Explore results",
      kicker: "WINGS / RESULTS",
      heading: "Pipeline Results",
    });
    const workspace = document.createElement("div");
    workspace.className = "wse-explorer-workspace wse-pipeline-workspace";
    tabset.insertBefore(workspace, nativeNav);
    content.classList.add("wse-pipeline-content");
    workspace.append(navigation.element, content);
    nativeNav.remove();
    let active = DEFINITIONS.find(([name]) => panels[name].classList.contains("active"))?.[0] || "summary";

    function activate(name, keyboard = false) {
      if (!buttons[name]) return;
      active = name;
      workspace.dataset.wingsPipelineView = name;
      for (const [key] of DEFINITIONS) {
        const selected = key === name;
        buttons[key].setAttribute("aria-selected", String(selected));
        buttons[key].classList.toggle("active", selected);
        buttons[key].tabIndex = selected ? 0 : -1;
        panels[key].hidden = !selected;
        panels[key].classList.toggle("active", selected);
        panels[key].classList.toggle("show", selected);
      }
      navigation.select(name, keyboard);
      if (keyboard) buttons[name].focus();
      // Resize existing charts after their panel becomes visible.
      if (typeof globalThis.requestAnimationFrame === "function") requestAnimationFrame(() => {
        if (typeof globalThis.dispatchEvent === "function") globalThis.dispatchEvent(new Event("resize"));
        if (globalThis.Plotly?.Plots?.resize) {
          for (const plot of panels[name].querySelectorAll(".js-plotly-plot")) globalThis.Plotly.Plots.resize(plot);
        }
      });
    }
    for (const [name] of DEFINITIONS) {
      buttons[name].addEventListener("click", event => { event.preventDefault(); activate(name); });
      // Preserve compatibility with Quarto/Bootstrap and links targeting tabs.
      buttons[name].addEventListener("shown.bs.tab", () => activate(name));
      buttons[name].addEventListener("keydown", event => {
        const order = navigation.visibleViews(), index = order.indexOf(name);
        let next;
        if (["ArrowDown", "ArrowRight"].includes(event.key)) next = order[(index + 1) % order.length];
        if (["ArrowUp", "ArrowLeft"].includes(event.key)) next = order[(index - 1 + order.length) % order.length];
        if (event.key === "Home") next = order[0];
        if (event.key === "End") next = order[order.length - 1];
        if (next) { event.preventDefault(); activate(next, true); }
      });
    }
    activate(active);
    const api = {activate, buttons, panels, navigation, get active() { return active; }};
    tabset.wingsPipelineNavigation = api;
    return api;
  }

  function initialize() {
    const overview = document.getElementById?.("overview");
    const tabset = overview?.closest(".panel-tabset");
    mount(tabset);
  }
  globalThis.WINGS_PIPELINE_NAVIGATION = {mount, initialize};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, {once: true});
  else initialize();
})();
