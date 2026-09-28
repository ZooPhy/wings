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
      this.ebirdContexts = Array.isArray(payload.ebird_contexts) ? payload.ebird_contexts : [];
      this.ebirdAttribution = payload.ebird_attribution || null;
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
      this.selectedSampleId = this.selectedSampleId === sampleId ? null : sampleId;
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
            <div class="wse-segment-tabs" role="group" aria-label="Phylogeny segment"></div>
            <div class="wse-tree-note wse-panel-note"></div>
            <div class="wse-tree"></div>
            <div class="wse-tree-grid"></div>
          </section>
          <div class="wse-footer-note">When the optional phylogeny stage is enabled, WINGS infers segment trees from QC-passing consensus sequences. Otherwise, the Explorer displays available external trees. Trees are displayed without rerooting or time calibration. Collection dates come from metadata, not tip labels.</div>
          <section class="wse-panel wse-ebird-panel" hidden>
            <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Ecological context</span><h3>eBird reporting frequency</h3></div></div>
            <div class="wse-ebird"></div>
          </section>
        </div>`;

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
      this.evidenceNode = this.root.querySelector(".wse-genome-evidence");
      this.genomeControlsNode = this.root.querySelector(".wse-genome-controls");

      this.renderMetrics();
      this.renderGenomeControls();
      this.renderSegmentTabs();
      this.renderTimeline();
      this.renderEbird();
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
        <label>Tree view<select class="wse-view-select"><option value="all">All eight segments</option><option value="single">Single segment</option></select></label>
        <button type="button" class="wse-clear-selection">Clear selection</button>`;
      this.genomeControlsNode.querySelector(".wse-sample-select").addEventListener("change", event => {
        this.selectedSampleId = this.sampleById.has(event.target.value) ? event.target.value : null;
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
      this.hostFilter = host;
      this.renderTimeline();
      this.renderEbird();
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
      this.ebirdPanelNode.hidden = !this.ebirdContexts.length;
      if (!this.ebirdContexts.length) return;
      const contexts = this.ebirdContexts.filter((item) =>
        this.hostFilter === "ALL" || item.host === this.hostFilter);
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
        this.ebirdNode.innerHTML = '<p class="wse-ebird-note">No eBird context is available for this host.</p>' + legalNotice;
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
      if (this.outbreakLastSampleId !== this.selectedSampleId) { this.mapStateCardDismissed = false; this.outbreakPage = 0; if (this.outbreakLastSampleId !== undefined) this.outbreakScope = "sample"; this.outbreakLastSampleId = this.selectedSampleId; }
      this.syncOutbreakDates();
      const view = this.outbreakView();
      const focusedControl = document.activeElement?.dataset?.outbreakControl;
      const recordsOpen = forceRecordsOpen || Boolean(this.outbreakNode.querySelector(".wse-outbreak-records")?.open);
      const pages = Math.max(1, Math.ceil(view.rows.length / 25));
      this.outbreakPage = Math.max(0, Math.min(this.outbreakPage, pages - 1));
      const rows = view.rows.slice(this.outbreakPage * 25, (this.outbreakPage + 1) * 25);
      const option = (value, label, active) => `<option value="${esc(value)}"${value === active ? " selected" : ""}>${esc(label)}</option>`;
      const basisLabel = this.outbreakBasis === "collection_date" ? "collection date" : "detection date";
      const sample = this.sampleById.get(this.selectedSampleId);
      const missingSampleDate = this.outbreakFollow && sample && this.outbreakEpoch(sample.collection_date) === null;
      const range = context.date_ranges[this.outbreakBasis] || {};
      this.outbreakNode.innerHTML = `
        <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Outbreak context</span><h3>APHIS wild-bird detections</h3></div><a href="${esc(context.source_url)}" target="_blank" rel="noopener noreferrer">Open APHIS source table ↗</a></div>
        <div class="wse-outbreak-body">
          <p class="wse-outbreak-caution">Date and place overlap provide context only; they do not imply epidemiological linkage. Counts are source records, not unique outbreaks, incidence, or prevalence.</p>
          <div class="wse-outbreak-controls">
            <label>Timeline / records <select data-outbreak-control="scope">${option("sample", "Follow selected sample (state)", this.outbreakScope)}${option("all", "All U.S. states", this.outbreakScope)}${Object.entries(context.states).sort((a,b) => a[1].localeCompare(b[1])).map(([code, name]) => option(code, name, this.outbreakScope)).join("")}</select></label>
            <label>Date basis <select data-outbreak-control="basis">${option("collection_date", "Collection date", this.outbreakBasis)}${option("detected_date", "Date detected", this.outbreakBasis)}</select></label>
            <label><input type="checkbox" data-outbreak-control="lock"${this.outbreakFollow ? "" : " checked"}> Lock date window</label>
            <label>Window ± <select data-outbreak-control="days"${this.outbreakFollow ? "" : " disabled"}>${[7,30,90,365].map(days => option(String(days), `${days} days`, String(this.outbreakDays))).join("")}</select></label>
            <label>From <input type="date" data-outbreak-control="start" value="${esc(this.outbreakStart)}"></label>
            <label>Through <input type="date" data-outbreak-control="end" value="${esc(this.outbreakEnd)}"></label>
          </div>
          <p class="wse-outbreak-scope">${esc(view.scopeLabel)} ${missingSampleDate ? "Sample collection date unavailable; displaying the snapshot's full date range." : this.outbreakFollow && !sample ? "No selected sample; displaying the snapshot's full date range." : ""}</p>
          <p class="wse-outbreak-summary" aria-live="polite">${view.validWindow ? `<strong>${formatNumber(view.rows.length)} matching source records</strong> · ${esc(this.outbreakStart)} through ${esc(this.outbreakEnd)} by ${basisLabel}.` : "Enter a valid date range with From on or before Through."} ${formatNumber(view.undated)} records in this geographic scope lack a usable ${basisLabel} and are excluded.</p>
          ${view.outsideSnapshot ? '<p class="wse-outbreak-caution">This window is outside the date range represented in this snapshot. Zero matches do not establish absence of detections.</p>' : ""}
          <p class="wse-outbreak-precision">Source precision: county/state. Map: state-level aggregates; shaded areas are not exact detection locations. State matching also applies when sample coordinates are absent. No distance-based linkage is calculated.</p>
          <p class="wse-outbreak-map-key">The shared map shades all U.S. states for the chosen dates, including neighboring states. This timeline and the source records follow the geographic choice above. Click a shaded state to browse its records without changing the selected WINGS sample. Host filters affect sample points only.</p>
          <div class="wse-outbreak-timeline"></div>
          <p class="wse-outbreak-timeline-note">${this.outbreakBasis === "collection_date" ? "Collection date is the sample collection date reported by APHIS." : "Date detected is the date of APHIS confirmatory testing; it can be later than collection."} Click a bar to narrow the date window. A dashed line marks the selected WINGS sample's collection date when it falls in this window.</p>
          <details class="wse-outbreak-records"${recordsOpen ? " open" : ""}><summary>Source records (${formatNumber(view.rows.length)})</summary>
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
        const bar = svgEl("rect", {x:x(from), y:bottom - count / max * (bottom - top), width:Math.max(1, x(through) - x(from) - 1), height:count / max * (bottom - top), class:"wse-outbreak-bar", tabindex:0, role:"button", "aria-label":`${key}: ${count} source records; filter to this period`});
        const title = svgEl("title"); title.textContent = `${key}: ${count} source records`; bar.appendChild(title);
        const choose = () => { this.outbreakStart = new Date(from).toISOString().slice(0, 10); this.outbreakEnd = new Date(through - 86400000).toISOString().slice(0, 10); this.outbreakFollow = false; this.outbreakPage = 0; this.renderOutbreak(true); this.outbreakNode.querySelector('[data-outbreak-control="start"]')?.focus({preventScroll: true}); };
        bar.addEventListener("click", choose);
        bar.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } });
        svg.appendChild(bar);
      });
      const sampleDate = this.outbreakEpoch(this.sampleById.get(this.selectedSampleId)?.collection_date);
      if (sampleDate !== null && sampleDate >= view.start && sampleDate <= view.end) {
        const line = svgEl("line", {x1:x(sampleDate + 43200000), x2:x(sampleDate + 43200000), y1:top - 6, y2:bottom, class:"wse-outbreak-sample-date"});
        const title = svgEl("title"); title.textContent = `WINGS sample collection: ${this.sampleById.get(this.selectedSampleId).collection_date}`; line.appendChild(title); svg.appendChild(line);
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

    revealSelectedTips() {
      // Scroll inside each tree only; do not move the report viewport.
      this.root.querySelectorAll(".wse-tree").forEach(container => {
        if (container.hidden) return;
        const tip = [...container.querySelectorAll(".wse-tree-tip")].find(el => el.dataset.sampleId === this.selectedSampleId);
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
        const visible = !sample || visibleIds.has(leaf.sample_id);
        const group = svgEl("g", {
          class:`wse-tree-tip${visible ? "" : " is-filtered"}`,
          "data-sample-id":leaf.sample_id || "",
          tabindex: leaf.sample_id ? 0 : -1,
          role: leaf.sample_id ? "button" : "img",
          "aria-label": sample ? `Select ${sample.sample_id}; tip ${leaf.name}` : leaf.name,
        });
        const dot = svgEl("circle", {cx:leaf._x+7,cy:leaf._y,r:4.8,fill:sample?this.hostColorFor(sample):GRAY,class:"wse-tree-tip-dot"});
        const label = svgEl("text", {x:leaf._x+18,y:leaf._y+4,class:"wse-tree-tip-label"});
        label.textContent = sample ? sample.sample_id : leaf.name;
        group.append(dot,label);
        if (leaf.sample_id) {
          group.addEventListener("click", () => this.selectSample(leaf.sample_id));
          group.addEventListener("mouseenter", () => this.setHover(leaf.sample_id));
          group.addEventListener("mouseleave", () => this.clearHover());
          group.addEventListener("keydown", (event) => { if(event.key === "Enter" || event.key === " ") { event.preventDefault(); this.selectSample(leaf.sample_id); } });
        }
        const title = svgEl("title");
        title.textContent = sample ? `${sample.sample_id}\n${sample.host} · ${dateLabel(sample.collection_date)}\nTip: ${leaf.name}` : leaf.name;
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
      this.renderEbird();
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
      new Explorer(root, payload);
    });
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, {once:true});
  else initialize();
})();
