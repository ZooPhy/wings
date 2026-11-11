/* WINGS_VIEW_NAVIGATOR_V1 — navigation groups, not biological relationships. */
(() => {
  "use strict";
  const GROUPS = [
    {id: "genomics", label: "Genomics", views: ["genome", "amino", "genotypes"]},
    {id: "context", label: "Ecological context", views: ["ecology", "coverage", "outbreak"]},
    {id: "evidence", label: "Integrated evidence", views: ["concordance"]},
  ];
  const make = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const svg = (tag, attrs) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };

  function mount(nav, buttons, options = {}) {
    if (!globalThis.d3?.hierarchy) throw new Error("Bundled D3 hierarchy is unavailable.");
    const primary = options.primary || "overview";
    const groups = options.groups || GROUPS;
    // Quarto assigns aside elements to named margin grid columns with
    // !important. A navigation landmark avoids inheriting that placement.
    const element = make("nav", "wse-view-navigator");
    element.setAttribute("aria-label", options.label || "Explorer navigation");
    const toggle = make("button", "wse-nav-toggle");
    toggle.type = "button";
    const current = make("span", "wse-nav-current", buttons[primary].textContent);
    toggle.append(make("span", "", options.toggleLabel || "Explore views"), current);
    toggle.setAttribute("aria-expanded", "false");
    const content = make("div", "wse-nav-content");
    content.id = `${buttons[primary].id}-navigation`;
    toggle.setAttribute("aria-controls", content.id);
    const header = make("header", "wse-nav-header");
    header.append(make("span", "wse-nav-kicker", options.kicker || "WINGS / EXPLORE"),
      make("h3", "", options.heading || "Follow the evidence"));
    nav.classList.add("wse-nav-tree");
    if (options.mode !== "sections") nav.setAttribute("aria-orientation", "vertical");
    content.append(header, nav);
    element.append(toggle, content);
    const collapsed = new Set();
    const headings = {};
    let active = primary;

    for (const group of groups) {
      const heading = make("button", "wse-nav-group", group.label);
      heading.type = "button";
      heading.setAttribute("aria-label", `${group.label} navigation group`);
      heading.addEventListener("click", () => {
        if (collapsed.has(group.id)) collapsed.delete(group.id); else collapsed.add(group.id);
        render();
        heading.focus();
      });
      headings[group.id] = heading;
    }

    function render() {
      const hierarchy = globalThis.d3.hierarchy({id: "root", children: [
        {view: primary},
        ...groups.map(group => ({...group, children: collapsed.has(group.id) ? [] : group.views.map(view => ({view}))})),
      ]});
      let row = 12;
      // Preorder spacing keeps each group label above its destinations.
      hierarchy.eachBefore(node => {
        node.x = node.depth * 18;
        if (!node.depth) { node.y = 0; return; }
        if (node.data.views) row += 14;
        node.y = row + 22;
        row += node.data.views ? 44 : buttons[node.data.view].textContent.trim().length > 23 ? 66 : 46;
      });
      const diagram = svg("svg", {class: "wse-nav-connectors", width: "100%", height: row + 12, "aria-hidden": "true", focusable: "false"});
      for (const link of hierarchy.links()) {
        const {source, target} = link;
        const onPath = target.data.view === active || target.data.views?.includes(active);
        diagram.append(svg("path", {
          d: `M${source.x},${source.y}V${target.y - 12}Q${source.x},${target.y} ${source.x + 12},${target.y}H${target.x}`,
          class: `wse-nav-link${onPath ? " is-active" : ""}`,
        }));
      }
      nav.replaceChildren(diagram);
      for (const button of Object.values(buttons)) button.hidden = true;
      hierarchy.eachBefore(node => {
        if (!node.depth) return;
        const view = node.data.view;
        const button = view ? buttons[view] : headings[node.data.id];
        button.hidden = false;
        button.style.top = `${node.y - 21}px`;
        button.style.left = `${node.x + 14}px`;
        button.style.width = `calc(100% - ${node.x + 22}px)`;
        if (!view) button.setAttribute("aria-expanded", String(!collapsed.has(node.data.id)));
        nav.append(button);
        const selected = view === active;
        diagram.append(svg("circle", {cx: node.x, cy: node.y, r: selected ? 7 : view ? 4 : 5,
          class: `wse-nav-node${selected ? " is-selected" : ""}${view ? "" : " is-group"}`}));
      });
      nav.style.height = `${row + 12}px`;
    }

    toggle.addEventListener("click", () => {
      const open = element.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    element.addEventListener("keydown", event => {
      if (event.key === "Escape" && element.classList.contains("is-open")) {
        element.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });

    function select(name, keyboard = false) {
      const restoreFocus = document.activeElement === buttons[name];
      active = name;
      const group = groups.find(group => group.views.includes(name));
      if (group) collapsed.delete(group.id);
      current.textContent = buttons[name].textContent;
      render();
      if (!keyboard) {
        element.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        if (globalThis.matchMedia?.("(max-width: 1050px)").matches && restoreFocus) toggle.focus();
      }
    }
    render();
    return {element, select, visibleViews: () => [primary, ...groups.flatMap(group => collapsed.has(group.id) ? [] : group.views)]};
  }

  globalThis.WINGS_VIEW_NAVIGATOR = {mount, GROUPS};
})();
