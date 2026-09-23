(() => {
  "use strict";

  const US_OUTLINE = [
    [-122.84,49.00],[-95.159,49.00],[-95.156,49.384],[-94.818,49.389],[-94.329,48.671],[-91.64,48.14],[-88.378,48.303],[-84.876,46.90],[-82.551,45.348],[-82.138,43.571],[-83.12,42.08],[-82.69,41.675],[-78.939,42.864],[-79.172,43.466],[-78.720,43.625],[-76.82,43.629],[-74.867,45.000],[-71.505,45.008],[-70.66,45.46],[-69.237,47.448],[-67.79,47.066],[-67.791,45.703],[-66.965,44.81],[-70.116,43.684],[-70.825,42.335],[-70.495,41.805],[-70.08,41.78],[-70.185,42.145],[-69.885,41.923],[-69.965,41.637],[-73.71,40.931],[-71.945,40.93],[-73.952,40.751],[-74.178,39.709],[-74.906,38.94],[-75.528,39.499],[-75.057,38.404],[-75.94,37.217],[-75.722,37.937],[-76.233,38.319],[-76.35,39.15],[-76.329,38.083],[-76.99,38.24],[-76.302,37.918],[-75.727,35.551],[-76.363,34.809],[-79.061,33.494],[-81.336,31.44],[-81.314,30.036],[-80.057,26.88],[-80.381,25.206],[-81.172,25.201],[-81.71,25.87],[-82.855,27.886],[-82.65,28.55],[-83.71,29.937],[-85.109,29.636],[-86.4,30.4],[-89.594,30.16],[-89.408,29.16],[-93.226,29.784],[-94.69,29.48],[-97.14,27.83],[-97.14,25.87],[-97.53,25.84],[-99.02,26.37],[-100.958,29.381],[-102.48,29.76],[-103.11,28.97],[-103.94,29.27],[-106.508,31.755],[-108.24,31.755],[-108.242,31.342],[-111.024,31.335],[-114.721,32.721],[-117.128,32.535],[-118.52,34.028],[-120.623,34.609],[-124.398,40.313],[-124.214,42.0],[-124.533,42.766],[-123.899,45.523],[-124.687,48.184],[-123.12,48.04],[-122.587,47.096],[-122.34,47.36],[-122.84,49.0]
  ];

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
      this.hosts = Array.isArray(payload.hosts) ? payload.hosts : [];
      this.hostColor = new Map(this.hosts.map((host, i) => [host, HOST_COLORS[i % HOST_COLORS.length]]));
      this.segments = (payload.segment_order || []).filter((segment) => payload.trees && payload.trees[segment]);
      this.segment = this.segments.includes("HA") ? "HA" : (this.segments[0] || null);
      this.hostFilter = "ALL";
      this.selectedSampleId = this.samples[0]?.sample_id || null;
      this.hoverSampleId = null;
      this.clusterCursor = new Map();
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
      this.selectedSampleId = sampleId;
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
              <div class="wse-subtitle">Linked collection timeline, geospatial context, and segment-specific phylogeny. Select a sample anywhere to highlight it everywhere.</div>
            </div>
            <div class="wse-heading-accent" aria-hidden="true"></div>
          </div>
          <div class="wse-metrics"></div>
          <div class="wse-controls"></div>
          <div class="wse-selected"></div>
          <section class="wse-panel wse-timeline-panel">
            <div class="wse-panel-heading"><div><span class="wse-panel-kicker">When</span><h3>Collection timeline</h3></div><div class="wse-panel-note">Circle color = host</div></div>
            <div class="wse-timeline"></div>
          </section>
          <div class="wse-main-grid">
            <section class="wse-panel wse-map-panel">
              <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Where</span><h3>Sampling map</h3></div><div class="wse-panel-note wse-map-count"></div></div>
              <div class="wse-map"></div>
              <div class="wse-host-legend"></div>
            </section>
            <section class="wse-panel wse-tree-panel">
              <div class="wse-panel-heading"><div><span class="wse-panel-kicker">How related</span><h3>Segment phylogeny</h3></div><div class="wse-panel-note wse-tree-note"></div></div>
              <div class="wse-segment-tabs" role="group" aria-label="Phylogeny segment"></div>
              <div class="wse-tree"></div>
            </section>
          </div>
          <div class="wse-footer-note">Phylogenies are displayed as supplied and are not inferred, rerooted, or time-calibrated by WINGS. Collection dates come from metadata, not tip labels.</div>
        </div>`;

      this.metricsNode = this.root.querySelector(".wse-metrics");
      this.controlsNode = this.root.querySelector(".wse-controls");
      this.selectedNode = this.root.querySelector(".wse-selected");
      this.timelineNode = this.root.querySelector(".wse-timeline");
      this.mapNode = this.root.querySelector(".wse-map");
      this.mapCountNode = this.root.querySelector(".wse-map-count");
      this.legendNode = this.root.querySelector(".wse-host-legend");
      this.segmentTabsNode = this.root.querySelector(".wse-segment-tabs");
      this.treeNode = this.root.querySelector(".wse-tree");
      this.treeNoteNode = this.root.querySelector(".wse-tree-note");

      this.renderMetrics();
      this.renderControls();
      this.renderSegmentTabs();
      this.renderTimeline();
      this.renderMap();
      this.renderTree();
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
        const active = segment === this.segment;
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

          const select = this.controlsNode.querySelector(".wse-segment-select");
          if (select) select.value = this.segment;

          this.renderSegmentTabs();
          this.renderTree();
          this.updateSelection();
        });
      });
    }

    renderControls() {
      const segmentOptions = (this.payload.segment_order || []).map((segment) => {
        const available = Boolean(this.payload.trees?.[segment]);
        return `<option value="${esc(segment)}" ${segment === this.segment ? "selected" : ""} ${available ? "" : "disabled"}>${esc(segment)}${available ? "" : " — unavailable"}</option>`;
      }).join("");
      const hostOptions = [`<option value="ALL">All hosts</option>`, ...this.hosts.map((host) => `<option value="${esc(host)}">${esc(host)}</option>`)].join("");
      this.controlsNode.innerHTML = `
        <label>Phylogeny segment<select class="wse-segment-select">${segmentOptions}</select></label>
        <label>Host filter<select class="wse-host-select">${hostOptions}</select></label>
        <button type="button" class="wse-reset">Reset selection</button>`;
      this.controlsNode.querySelector(".wse-segment-select")?.addEventListener("change", (event) => {
        this.segment = event.target.value;
        this.renderSegmentTabs();
        this.renderTree();
        this.updateSelection();
      });
      this.controlsNode.querySelector(".wse-host-select")?.addEventListener("change", (event) => {
        this.hostFilter = event.target.value;
        this.renderTimeline();
        this.renderMap();
        this.renderTree();
        this.renderLegend();
        this.updateSelection();
      });
      this.controlsNode.querySelector(".wse-reset")?.addEventListener("click", () => {
        this.hostFilter = "ALL";
        const hostSelect = this.controlsNode.querySelector(".wse-host-select");
        if (hostSelect) hostSelect.value = "ALL";
        this.selectedSampleId = this.samples[0]?.sample_id || null;
        this.renderTimeline();
        this.renderMap();
        this.renderTree();
        this.renderLegend();
        this.updateSelection();
      });
    }

    renderSelected() {
      const sample = this.sampleById.get(this.selectedSampleId);
      if (!sample) {
        this.selectedNode.innerHTML = "";
        return;
      }
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

    renderLegend() {
      const visibleHosts = this.hostFilter === "ALL" ? this.hosts : [this.hostFilter];
      this.legendNode.innerHTML = visibleHosts.map((host) => `<span><i style="background:${this.hostColor.get(host) || "#5F6368"}"></i>${esc(host)}</span>`).join("");
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
      const dates = samples.map((s) => parseDate(s.collection_date).getTime());
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

    renderMap() {
      const allVisible = this.visibleSamples();
      const samples = allVisible.filter((sample) => sample.has_coordinates);
      const missing = allVisible.length - samples.length;
      this.mapCountNode.textContent = `${samples.length} geolocated · ${missing} without coordinates`;
      this.mapNode.innerHTML = "";

      const width = 650, height = 435;
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":"Sampling locations in the contiguous United States"});
      const margin = {left:24,right:24,top:24,bottom:24};
      const lonMin=-126, lonMax=-66, latMin=24, latMax=50;
      const px=(lon)=>margin.left+(lon-lonMin)/(lonMax-lonMin)*(width-margin.left-margin.right);
      const py=(lat)=>margin.top+(latMax-lat)/(latMax-latMin)*(height-margin.top-margin.bottom);

      const outlinePath = US_OUTLINE.map(([lon,lat],i)=>`${i?"L":"M"}${px(lon).toFixed(1)},${py(lat).toFixed(1)}`).join(" ")+" Z";
      svg.appendChild(svgEl("path", {d:outlinePath, class:"wse-us-outline"}));

      if (!samples.length) {
        const label = svgEl("text", {x:width/2,y:height/2,"text-anchor":"middle",class:"wse-map-empty"});
        label.textContent = "No coordinates available for the current filter";
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
        const radius = Math.min(22, 8 + Math.sqrt(members.length) * 3.3);
        const cluster = svgEl("g", {
          class:"wse-map-cluster",
          "data-sample-ids":members.map(s=>s.sample_id).join("|"),
          tabindex:0,
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
          const cursor = this.clusterCursor.get(key) || 0;
          const sample = members[cursor % members.length];
          this.clusterCursor.set(key, (cursor + 1) % members.length);
          this.selectSample(sample.sample_id);
        };
        cluster.addEventListener("click", choose);
        cluster.addEventListener("keydown", (event) => { if(event.key === "Enter" || event.key === " ") choose(); });
        cluster.addEventListener("mouseenter", () => this.setHover(members[0].sample_id));
        cluster.addEventListener("mouseleave", () => this.clearHover());
        svg.appendChild(cluster);
      });

      this.mapNode.appendChild(svg);
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

    renderTree() {
      this.treeNode.innerHTML = "";
      if (!this.segment || !this.payload.trees?.[this.segment]) {
        this.treeNoteNode.textContent = "No supplied phylogeny";
        this.treeNode.innerHTML = `<div class="wse-empty">No segment phylogeny is available.</div>`;
        return;
      }
      const record = this.payload.trees[this.segment];
      const visibleIds = new Set(this.visibleSamples().map(s=>s.sample_id));
      this.treeNoteNode.textContent = `${this.segment} · ${record.tip_count} tips`;
      const tipCount = Math.max(1, record.tip_count || 1);
      const width = 900, height = Math.max(450, tipCount * 25 + 40);
      const root = JSON.parse(JSON.stringify(record.root));
      const layout = this.treeLayout(root, width, height);
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":`${this.segment} phylogeny`});

      const drawBranches = (node) => {
        const children = node.children || [];
        if (children.length) {
          const ys = children.map(c=>c._y);
          svg.appendChild(svgEl("line", {x1:node._x,y1:Math.min(...ys),x2:node._x,y2:Math.max(...ys),class:"wse-tree-branch"}));
          children.forEach((child) => {
            const branch = svgEl("line", {x1:node._x,y1:child._y,x2:child._x,y2:child._y,class:"wse-tree-branch"});
            if (child.sample_id) branch.setAttribute("data-sample-id", child.sample_id);
            svg.appendChild(branch);
            if (child.support != null && Number(child.support) >= 70 && child.children?.length) {
              const support = svgEl("text", {x:(node._x+child._x)/2,y:child._y-4,"text-anchor":"middle",class:"wse-support-label"});
              support.textContent = Number(child.support).toFixed(0);
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
        });
        const dot = svgEl("circle", {cx:leaf._x+7,cy:leaf._y,r:4.8,fill:sample?this.hostColorFor(sample):GRAY,class:"wse-tree-tip-dot"});
        const label = svgEl("text", {x:leaf._x+18,y:leaf._y+4,class:"wse-tree-tip-label"});
        label.textContent = sample ? sample.sample_id : leaf.name;
        group.append(dot,label);
        if (leaf.sample_id) {
          group.addEventListener("click", () => this.selectSample(leaf.sample_id));
          group.addEventListener("mouseenter", () => this.setHover(leaf.sample_id));
          group.addEventListener("mouseleave", () => this.clearHover());
          group.addEventListener("keydown", (event) => { if(event.key === "Enter" || event.key === " ") this.selectSample(leaf.sample_id); });
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
      this.treeNode.appendChild(svg);
    }

    updateSelection() {
      this.renderSelected();
      this.updateEmphasis();
    }

    updateEmphasis() {
      const focus = this.hoverSampleId || this.selectedSampleId;
      this.root.querySelectorAll("[data-sample-id]").forEach((el) => {
        const id = el.getAttribute("data-sample-id");
        el.classList.toggle("is-selected", Boolean(focus && id === focus));
      });
      this.root.querySelectorAll("[data-sample-ids]").forEach((el) => {
        const ids = (el.getAttribute("data-sample-ids") || "").split("|");
        el.classList.toggle("is-selected", Boolean(focus && ids.includes(focus)));
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
