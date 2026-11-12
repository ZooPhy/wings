/* WINGS_SAMPLE_PRESENTATION_V1 — display recorded results; do not infer calls. */
(() => {
  "use strict";
  const ORDER = ["PB2", "PB1", "PA", "HA", "NP", "NA", "MP", "NS"];
  const MISSING = new Set(["", "not available", "not recorded", "na", "n/a", "missing"]);
  const make = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const svgNode = (tag, attrs, text) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  // Same ring geometry as the sample's genome-QC constellation.
  const polar = (radius, angle) => [300 + radius * Math.sin(angle), 300 - radius * Math.cos(angle)];
  const arc = (start, end) => {
    const a = polar(250, start), b = polar(250, end), c = polar(126, end), d = polar(126, start);
    return `M${a}A250,250 0 0 1 ${b}L${c}A126,126 0 0 0 ${d}Z`;
  };

  function tableEntries(table, heading) {
    const headers = Array.from((table.querySelector("thead") || table).querySelectorAll("th")).map(cell => cell.textContent.trim().toLowerCase());
    if (headers.length !== 2 || headers[0] !== heading || headers[1] !== "value") return null;
    return Array.from((table.querySelector("tbody") || table).querySelectorAll("tr")).flatMap(row => {
      const cells = row.querySelectorAll("td");
      return cells.length === 2 ? [{label: cells[0].textContent.trim(), value: cells[1].textContent.trim()}] : [];
    });
  }
  const fieldKey = value => value.toLowerCase().replace(/[_\s]+/g, " ").trim();
  const hostKey = value => String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const hostAliases = {blkvul: "BLVU", snogoo: "SNGO", turvul: "TUVU", cangoo: "CANG", cago: "CANG", rethaw: "RTHA"};
  const hostArtwork = new Map();
  for (const bird of globalThis.WINGS_HOST_ARTWORK || []) {
    hostArtwork.set(hostKey(bird.name), bird);
    if (bird.code) hostArtwork.set(hostKey(bird.code), bird);
  }
  function resolveHost(host) {
    const key = hostKey(host);
    const direct = hostArtwork.get(key) || hostArtwork.get(hostKey(hostAliases[key]));
    if (direct) return direct;
    // Metadata may include both a species name and its code, in either order.
    const candidates = String(host).split(/[()·\/|,]/).map(hostKey).filter(Boolean);
    const matches = candidates.map(key => hostArtwork.get(key) || hostArtwork.get(hostKey(hostAliases[key]))).filter(Boolean);
    return matches.length && matches.every(bird => bird === matches[0]) ? matches[0] : null;
  }
  function populateHostCard(card, host) {
    card.append(make("span", "wsp-label", "HOST"));
    const bird = resolveHost(host);
    if (!bird) { card.append(make("strong", "wsp-host-value", host)); return; }
    const drawing = make("img", "wsp-host-artwork");
    drawing.src = bird.src;
    drawing.alt = "";
    drawing.width = 120; drawing.height = 100;
    drawing.addEventListener("error", () => drawing.remove(), {once: true});
    card.append(drawing, make("strong", "wsp-host-name", bird.name));
    // Retain the exact recorded value alongside the display name.
    if (hostKey(host) !== hostKey(bird.name)) card.append(make("span", "wsp-host-code", host));
  }
  const stateArtwork = new Map();
  const regionKey = value => hostKey(String(value || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, ""));
  const regionFields = ["state", "province", "territory", "province/territory", "state/province", "province territory", "state province"];
  for (const state of globalThis.WINGS_STATE_ARTWORK || []) {
    const country = state.country || "US";
    stateArtwork.set(country + ":" + regionKey(state.name), state);
    stateArtwork.set(country + ":" + regionKey(state.code), state);
  }
  function resolveState(state, country) {
    const key = regionKey(country);
    const nation = ["us", "usa", "unitedstates", "unitedstatesofamerica"].includes(key) ? "US" : ["ca", "can", "canada"].includes(key) ? "CA" : null;
    return nation ? stateArtwork.get(nation + ":" + regionKey(state)) || null : null;
  }
  function populateLocationCard(card, state, country) {
    card.append(make("span", "wsp-label", "COLLECTION LOCATION"));
    const artwork = resolveState(state, country);
    if (artwork) {
      const drawing = make("img", "wsp-state-artwork");
      drawing.src = artwork.src;
      drawing.alt = "";
      drawing.width = 120; drawing.height = 100;
      drawing.addEventListener("error", () => drawing.remove(), {once: true});
      card.append(drawing);
    }
    const location = [state, country].filter(value => value !== "Not recorded").join(" · ") || "Not recorded";
    card.append(make("strong", "wsp-location", location));
  }
  function tableContainer(table) {
    const panel = table.closest(".report-panel");
    return panel?.querySelectorAll("table").length === 1 ? panel : table.closest(".escape-table-shell") || table;
  }
  function removeTable(table) {
    const container = tableContainer(table);
    let parent = container.parentElement;
    container.remove();
    while (parent && ["cell", "cell-output", "cell-output-display"].some(cls => parent.classList.contains(cls)) && !parent.children.length && !parent.textContent.trim()) {
      const next = parent.parentElement;parent.remove();parent = next;
    }
  }

  function mountSampleProfile(main) {
    if (!main) return null;
    if (main.wingsSampleProfile) return main.wingsSampleProfile;
    const tables = Array.from(main.querySelectorAll("table"));
    const source = tables.map(table => ({table, entries: tableEntries(table, "field")})).find(item => item.entries?.some(row => ["sample id", "sample"].includes(fieldKey(row.label))));
    if (!source) return null;
    const excluded = new Set(["metadata status", "medaka status", "medaka provenance"]);
    const entries = source.entries.filter(row => !excluded.has(fieldKey(row.label)));
    const find = (...keys) => entries.find(row => keys.includes(fieldKey(row.label)))?.value || "Not recorded";
    const sample = find("sample id", "sample"), host = find("host"), specimen = find("specimen type", "specimen"), date = find("collection date"), state = find(...regionFields), country = find("country");
    const profile = make("article", "wings-sample-profile");
    profile.setAttribute("aria-label", "Sample collection profile");
    const heading = make("header", "wsp-heading");
    heading.append(make("div", "wsp-kicker", "SAMPLE RECORD"), make("div", "wsp-sample-id", sample));
    const layout = make("div", "wsp-layout"), dateCard = make("div", "wsp-date");
    dateCard.append(make("span", "wsp-date-label", "COLLECTED"));
    const parsed = /^\d{4}-\d{2}-\d{2}$/.test(date) ? new Date(date + "T00:00:00Z") : null;
    if (parsed && Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === date) {
      const time = make("time", "wsp-calendar");time.setAttribute("datetime", date);
      const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
      time.append(make("strong", "wsp-day", String(parsed.getUTCDate())), make("span", "wsp-month", months[parsed.getUTCMonth()] + " " + parsed.getUTCFullYear()));
      dateCard.append(time);
    } else dateCard.append(make("strong", "wsp-date-raw", date));
    const hostCard = make("div", "wsp-card wsp-host");
    populateHostCard(hostCard, host);
    const specimenCard = make("div", "wsp-card wsp-specimen-card");
    specimenCard.append(make("span", "wsp-label", "SPECIMEN TYPE"), make("strong", "wsp-specimen", specimen));
    const locationCard = make("div", "wsp-card wsp-location-card");
    populateLocationCard(locationCard, state, country);
    const coordinates = entries.filter(row => ["latitude", "longitude"].includes(fieldKey(row.label)));
    if (coordinates.length) {
      const list = make("dl", "wsp-coordinates");
      for (const row of coordinates) {
        const item = make("div");
        item.append(make("dt", "", row.label), make("dd", "", row.value || "Not recorded"));
        list.append(item);
      }
      locationCard.append(list);
    }
    layout.append(dateCard, hostCard, specimenCard, locationCard);profile.append(heading, layout);
    const standard = new Set(["sample id", "sample", "host", "specimen type", "specimen", "collection date", ...regionFields, "country", "latitude", "longitude"]);
    const extra = entries.filter(row => !standard.has(fieldKey(row.label)));
    if (extra.length) {
      const list = make("dl", "wsp-extra");
      for (const row of extra) { const item = make("div");item.append(make("dt", "", row.label), make("dd", "", row.value || "Not recorded"));list.append(item); }
      profile.append(list);
    }
    const container = tableContainer(source.table);
    container.parentElement.insertBefore(profile, container);container.remove();
    for (const table of tables) {
      const metrics = tableEntries(table, "metric");
      if (metrics?.some(row => fieldKey(row.label) === "segments detected") && metrics.some(row => fieldKey(row.label) === "segments passing segment qc")) removeTable(table);
    }
    const api = {profile, sample, host, specimen, date, state, country};
    main.wingsSampleProfile = api;
    return api;
  }

  function trimMetricZeros(value) {
    const match = String(value).match(/^([+-]?[0-9][0-9,]*)\.([0-9]+)([eE][+-]?[0-9]+)?$/);
    if (!match) return value;
    const decimals = match[2].replace(/0+$/, "");
    return match[1] + (decimals ? "." + decimals : "") + (match[3] || "");
  }

  function mountSegmentOrder(table) {
    if (!table) return null;
    if (table.wingsSegmentOrder) return table.wingsSegmentOrder;
    const headers = Array.from(table.querySelector("thead")?.querySelectorAll("th") || []);
    const segmentIndex = headers.findIndex(cell => cell.textContent.trim().toLowerCase() === "segment");
    if (segmentIndex < 0) return null;
    const bodies = Array.from(table.querySelectorAll("tbody"));
    const segmentHeader = headers[segmentIndex];
    function sortSegments(descending = false) {
      for (const body of bodies) {
        const rows = Array.from(body.querySelectorAll("tr"));
        const rank = row => {
          const index = ORDER.indexOf(row.querySelectorAll("td")[segmentIndex]?.textContent.trim().toUpperCase());
          return index < 0 ? ORDER.length : index;
        };
        rows.sort((a, b) => {
          const left = rank(a), right = rank(b);
          if (left === ORDER.length || right === ORDER.length) return left === right ? 0 : left === ORDER.length ? 1 : -1;
          return (left - right) * (descending ? -1 : 1);
        });
        body.append(...rows);
      }
      for (const header of headers) header.setAttribute("aria-sort", "none");
      segmentHeader.setAttribute("aria-sort", descending ? "descending" : "ascending");
    }
    const toggleSort = event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      sortSegments(segmentHeader.getAttribute("aria-sort") === "ascending");
    };
    // Capture overrides the older report's alphabetical sorter in saved bundles.
    segmentHeader.addEventListener("click", toggleSort, true);
    segmentHeader.addEventListener("keydown", event => {
      if (["Enter", " "].includes(event.key)) toggleSort(event);
    }, true);
    segmentHeader.setAttribute("tabindex", "0");
    segmentHeader.setAttribute("title", "Sort by segment order");
    sortSegments();
    const api = {sortSegments, segmentHeader};
    table.wingsSegmentOrder = api;
    return api;
  }

  function mountBlastTable(table) {
    if (!table) return null;
    if (table.wingsBlastPresentation) return table.wingsBlastPresentation;
    const labels = Array.from(table.querySelector("thead")?.querySelectorAll("th") || []).map(cell => cell.textContent.trim().toLowerCase());
    const hitIndex = labels.indexOf("top blast hit");
    if (!labels.includes("segment") || hitIndex < 0) return null;
    const numeric = labels.map((label, index) => [label, index]).filter(([label]) => ["identity (%)", "query coverage (%)", "e-value", "bit score"].includes(label)).map(([, index]) => index);
    const sentinel = /^(?:SKIPPED(?:[_\s-].*)?|NO[_\s-]?HITS?|NOT[_\s-]?(?:AVAILABLE|RECORDED)|N\/?A|FAILED|ERROR|MISSING)$/i;
    for (const body of table.querySelectorAll("tbody")) {
      for (const row of body.querySelectorAll("tr")) {
        const cells = row.querySelectorAll("td");
        for (const link of cells[hitIndex]?.querySelectorAll("a") || []) {
          if (sentinel.test(link.textContent.trim())) link.replaceWith(make("span", "", link.textContent));
        }
        for (const index of numeric) {
          const cell = cells[index];
          if (!cell) continue;
          const recorded = cell.textContent.trim(), display = trimMetricZeros(recorded);
          if (display !== recorded) {
            cell.setAttribute("data-wings-recorded-value", recorded);
            cell.textContent = display;
          }
        }
      }
    }
    const api = mountSegmentOrder(table);
    table.wingsBlastPresentation = api;
    return api;
  }

  function removeExpectedLengthTables(main) {
    const ids = new Set(), parents = [];
    let removed = 0;
    if (!main) return {removed, ids};
    for (const table of Array.from(main.querySelectorAll("table"))) {
      const headers = Array.from(table.querySelector("thead")?.querySelectorAll("th") || []).map(cell => cell.textContent.trim().toLowerCase().replace(/\s+/g, " "));
      if (headers.length !== 2 || headers[0] !== "segment" || !["expected complete length", "expected segment length", "expected length"].includes(headers[1])) continue;
      const fileWrap = table.closest(".file-download-table-wrap");
      const container = (fileWrap?.querySelectorAll("table").length === 1 ? fileWrap : null) || table.closest(".escape-table-wrapper") || table.closest(".escape-table-shell") || table;
      parents.push(container.parentElement);
      if (container.id) ids.add(container.id);
      container.remove();removed++;
    }
    if (!removed) return {removed, ids};
    for (const tag of ["h2", "h3", "h4", "h5", ".file-download-title"]) {
      for (const heading of Array.from(main.querySelectorAll(tag))) {
        if (!/^expected\s+segment[\s-]*length\s+ranges$/i.test(heading.textContent.trim().replace(/#$/, "").trim())) continue;
        parents.push(heading.parentElement);
        if (heading.id) ids.add(heading.id);
        heading.remove();
      }
    }
    // Remove empty presentation shells, preserving panels with other evidence.
    for (let parent of parents) {
      while (parent && parent !== main && !parent.children.length && !parent.textContent.trim() &&
        (parent.tagName === "SECTION" || ["cell", "cell-output", "cell-output-display", "report-panel", "escape-table-shell", "file-download-table-wrap"].some(cls => parent.classList.contains(cls)))) {
        if (parent.id) ids.add(parent.id);
        const next = parent.parentElement;parent.remove();parent = next;
      }
    }
    return {removed, ids};
  }

  function readCalls(table) {
    const calls = new Map();
    const rows = (table.querySelector("tbody") || table).querySelectorAll("tr");
    for (const row of rows) {
      const cells = row.querySelectorAll("td");
      if (cells.length < 2) continue;
      const segment = cells[0].textContent.trim().toUpperCase();
      if (!ORDER.includes(segment)) continue;
      if (calls.has(segment)) return null;
      const text = cells[1].textContent.trim();
      calls.set(segment, MISSING.has(text.toLowerCase()) || cells[1].querySelector(".file-unavailable") ? null : text);
    }
    if (!calls.size) return null;
    return ORDER.map(segment => ({segment, call: calls.get(segment) ?? null}));
  }

  function mountGenoFLU(section) {
    if (!section) return null;
    if (section.wingsGenofluConstellation) return section.wingsGenofluConstellation;
    const table = section.querySelector("table.genoflu-table");
    if (!table) return null;
    const records = readCalls(table);
    if (!records) return null;
    const panel = table.closest(".report-panel") || section;
    const status = panel.querySelector(".download-status")?.textContent.trim() || "Not available";
    const count = records.filter(record => record.call !== null).length;
    const root = make("div", "wings-genoflu-constellation");
    root.setAttribute("aria-label", "Recorded GenoFLU segment calls");
    root.dataset.genofluStatus = status;
    const layout = make("div", "wgc-layout"), stage = make("div", "wgc-stage"), detail = make("div", "wgc-detail");
    detail.setAttribute("aria-live", "polite");
    layout.append(stage, detail);
    root.append(layout);
    const svg = svgNode("svg", {viewBox: "0 0 600 600", class: "wgc-svg", role: "group", "aria-label": "Eight-segment GenoFLU constellation"});
    svg.append(svgNode("circle", {cx: 300, cy: 300, r: 99, fill: "#000000", stroke: "#FFC627", "stroke-width": 8}));
    svg.append(svgNode("text", {x: 300, y: 270, class: "wgc-center-kicker", "text-anchor": "middle"}, "GENOTYPE"));
    const lines = status.length > 16 && status.includes(" ") ? [status.slice(0, status.lastIndexOf(" ")), status.slice(status.lastIndexOf(" ") + 1)] : [status];
    lines.forEach((line, index) => svg.append(svgNode("text", {x: 300, y: (lines.length === 1 ? 310 : 296) + index * 27, class: "wgc-center-status", "text-anchor": "middle"}, line)));
    svg.append(svgNode("text", {x: 300, y: 352, class: "wgc-center-count", "text-anchor": "middle"}, `${count}/8 calls recorded`));
    const groups = {};
    function select(segment, focus = false) {
      const record = records.find(record => record.segment === segment);
      if (!record) return;
      for (const [name, group] of Object.entries(groups)) {
        group.classList.toggle("is-selected", name === segment);
        group.setAttribute("aria-pressed", String(name === segment));
      }
      detail.replaceChildren(make("div", "wgc-kicker", "SELECTED GENOME SEGMENT"), make("h3", "wgc-segment-title", segment));
      const definition = make("dl", "wgc-facts");
      for (const [label, value, cls] of [
        ["Recorded GenoFLU call", record.call ?? "Not available", "wgc-call-value"],
      ]) {
        const row = make("div");row.append(make("dt", "", label), make("dd", cls, value));definition.append(row);
      }
      detail.append(definition);
      if (focus) groups[segment].focus();
    }
    records.forEach((record, index) => {
      const start = index * Math.PI / 4 + .032, end = (index + 1) * Math.PI / 4 - .032, mid = (start + end) / 2;
      const group = svgNode("g", {class: "wgc-segment", tabindex: "0", role: "button", "aria-label": `${record.segment}: ${record.call ?? "No recorded call"}`, "aria-pressed": "false"});
      group.append(svgNode("title", {}, `${record.segment}: ${record.call ?? "Not available"}`));
      group.append(svgNode("path", {d: arc(start, end), class: "wgc-wedge", fill: record.call === null ? "#FFFFFF" : "#8C1D40"}));
      const [x, y] = polar(188, mid);
      group.append(svgNode("text", {x, y: y - 9, "text-anchor": "middle", "dominant-baseline": "middle", class: "wgc-segment-label", fill: record.call === null ? "#000000" : "#FFFFFF"}, record.segment));
      const label = record.call === null ? "No call" : record.call.length > 12 ? record.call.slice(0, 10) + "…" : record.call;
      group.append(svgNode("text", {x, y: y + 23, "text-anchor": "middle", "dominant-baseline": "middle", class: "wgc-call-label", fill: record.call === null ? "#000000" : "#FFC627"}, label));
      group.addEventListener("click", () => select(record.segment));
      group.addEventListener("keydown", event => {
        if (["Enter", " "].includes(event.key)) { event.preventDefault(); select(record.segment); }
        if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
          event.preventDefault();select(ORDER[(index + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : 7)) % 8], true);
        }
      });
      groups[record.segment] = group;svg.append(group);
    });
    stage.append(svg);
    const legend = make("div", "wgc-legend");
    legend.append(make("span", "wgc-legend-recorded", "Recorded call"), make("span", "wgc-legend-missing", "No recorded call"));
    stage.append(legend);
    const tableWrap = table.closest(".file-download-table-wrap") || table;
    const container = tableWrap.parentElement;
    const originalResult = Array.from(panel.children).find(node => node.tagName === "P" && node.textContent.trim().startsWith("GenoFLU result:"));
    const details = make("details", "wgc-recorded-output");
    details.append(make("summary", "", "Recorded result and segment table"));
    container.insertBefore(root, tableWrap);
    container.insertBefore(details, tableWrap);
    if (originalResult) details.append(originalResult);
    details.append(tableWrap);
    select("PB2");
    const api = {root, records, status, count, groups, detail, details, table, select};
    section.wingsGenofluConstellation = api;
    return api;
  }

  function compactFileExplanation(section) {
    if (!section) return null;
    if (section.wingsMedakaStatusGuide) return section.wingsMedakaStatusGuide;
    const introductory = [];
    for (const node of Array.from(section.children)) {
      if (node.classList.contains("cell") || node.tagName === "TABLE") break;
      if (["P", "UL", "OL"].includes(node.tagName)) introductory.push(node);
    }
    if (!introductory.length || !introductory.some(node => /Medaka/i.test(node.textContent))) return null;
    const intro = make("p", "wse-sample-file-intro", "Files and processing status are listed by segment. Unpolished IRMA fallbacks and variant failures are flagged.");
    const guide = make("details", "wse-sample-status-guide");
    guide.append(make("summary", "", "Status guide"));
    section.insertBefore(intro, introductory[0]);
    section.insertBefore(guide, introductory[0]);
    guide.append(...introductory);
    section.wingsMedakaStatusGuide = guide;
    return guide;
  }

  function initialize() {
    const main = document.querySelector?.("main.content") || document.querySelector?.("main");
    const removedLengths = removeExpectedLengthTables(main);
    mountSampleProfile(main);
    for (const id of ["irma-candidate-selection", "interpretation"]) {
      const section = document.getElementById(id);
      if (section?.tagName === "SECTION") section.remove();
    }
    const toc = document.getElementById("TOC");
    for (const link of toc?.querySelectorAll('a[href^="#"]') || []) {
      const href = link.getAttribute("href");
      if (["#irma-candidate-selection", "#interpretation"].includes(href) || removedLengths.ids.has(href.slice(1))) (link.closest("li") || link).remove();
    }
    compactFileExplanation(document.getElementById("consensus-and-variant-files"));
    for (const table of document.getElementById("blast-top-hits")?.querySelectorAll("table") || []) mountBlastTable(table);
    for (const id of ["vadr-annotation-quality-control", "consensus-and-variant-files"]) {
      for (const table of document.getElementById(id)?.querySelectorAll("table") || []) mountSegmentOrder(table);
    }
    mountGenoFLU(document.getElementById("genoflu-genotype"));
  }
  globalThis.WINGS_SAMPLE_PRESENTATION = {initialize, mountGenoFLU, readCalls, compactFileExplanation, mountSampleProfile, resolveHost, populateHostCard, resolveState, populateLocationCard, mountBlastTable, trimMetricZeros, mountSegmentOrder, removeExpectedLengthTables};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, {once: true});
  else initialize();
})();
