(() => {
  "use strict";

  const normalize = (value) => String(value ?? "").trim().toLowerCase();

  const parseComparable = (value) => {
    const text = normalize(value);
    if (!text) return { type: "text", value: "" };

    const numericText = text
      .replace(/,/g, "")
      .replace(/^[^0-9.+-]*/, "")
      .replace(/[^0-9.eE+-].*$/, "");
    const number = Number(numericText);

    if (numericText && Number.isFinite(number)) {
      return { type: "number", value: number };
    }
    return { type: "text", value: text };
  };

  const compareValues = (a, b) => {
    const left = parseComparable(a);
    const right = parseComparable(b);

    if (left.type === "number" && right.type === "number") {
      return left.value - right.value;
    }
    return String(left.value).localeCompare(String(right.value), undefined, {
      numeric: true,
      sensitivity: "base",
    });
  };

  const enhanceTable = (table, tableIndex) => {
    if (table.dataset.escapeEnhanced === "true") return;
    table.dataset.escapeEnhanced = "true";
    table.classList.add("escape-data-table");

    const wrapper = document.createElement("div");
    wrapper.className = "escape-table-wrapper";
    table.parentNode.insertBefore(wrapper, table);
    wrapper.appendChild(table);

    const controls = document.createElement("div");
    controls.className = "escape-table-controls";

    const label = document.createElement("label");
    const searchId = `escape-table-search-${tableIndex}`;
    label.setAttribute("for", searchId);
    label.textContent = "Search table";

    const search = document.createElement("input");
    search.id = searchId;
    search.type = "search";
    search.placeholder = "Type to filter rows";
    search.setAttribute("aria-label", "Search this table");

    const count = document.createElement("span");
    count.className = "escape-table-count";
    count.setAttribute("aria-live", "polite");

    controls.append(label, search, count);
    wrapper.insertBefore(controls, table);

    const bodies = Array.from(table.tBodies);
    const rows = bodies.flatMap((body) => Array.from(body.rows));

    const updateCount = () => {
      const visible = rows.filter((row) => !row.hidden).length;
      count.textContent = `${visible} of ${rows.length} rows`;
    };

    search.addEventListener("input", () => {
      const query = normalize(search.value);
      rows.forEach((row) => {
        row.hidden = Boolean(query) && !normalize(row.innerText).includes(query);
      });
      updateCount();
    });
    updateCount();

    const headers = Array.from(table.querySelectorAll("thead th"));
    headers.forEach((header, columnIndex) => {
      header.tabIndex = 0;
      header.classList.add("escape-sortable");
      header.setAttribute("role", "button");
      header.setAttribute("aria-sort", "none");
      header.setAttribute("title", "Sort this column");

      const sortColumn = () => {
        const ascending = header.getAttribute("aria-sort") !== "ascending";
        headers.forEach((item) => item.setAttribute("aria-sort", "none"));
        header.setAttribute("aria-sort", ascending ? "ascending" : "descending");

        bodies.forEach((body) => {
          const bodyRows = Array.from(body.rows);
          bodyRows.sort((a, b) => {
            const comparison = compareValues(
              a.cells[columnIndex]?.innerText,
              b.cells[columnIndex]?.innerText,
            );
            return ascending ? comparison : -comparison;
          });
          bodyRows.forEach((row) => body.appendChild(row));
        });
      };

      header.addEventListener("click", sortColumn);
      header.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          sortColumn();
        }
      });
    });
  };


  const ASU = { maroon: "#8C1D40", gold: "#FFC627", black: "#000000", white: "#FFFFFF" };
  const fmt = (v, digits = 0) => Number(v).toLocaleString(undefined, {minimumFractionDigits: digits, maximumFractionDigits: digits});
  const pct = (v, digits = 1) => `${fmt(Number(v) * 100, digits)}%`;
  const makeButton = (label, value, active = false) => {
    const b = document.createElement("button"); b.type = "button"; b.textContent = label; b.dataset.value = value;
    b.className = `escape-viz-toggle${active ? " is-active" : ""}`; return b;
  };

  const fitValueSize = (label, preferred = 42) => {
    const length = String(label ?? "").length;
    if (length >= 16) return 25;
    if (length >= 14) return 28;
    if (length >= 12) return 31;
    if (length >= 10) return 35;
    return preferred;
  };

  const renderReadViz = (root) => {
    let data; try { data = JSON.parse(root.dataset.escapeRead || "{}"); } catch { return; }
    root.innerHTML = "";
    const controls = document.createElement("div"); controls.className = "escape-viz-controls";
    const chart = document.createElement("div"); chart.className = "escape-read-chart";
    const metrics = document.createElement("div"); metrics.className = "escape-read-metrics";
    root.append(controls, chart, metrics);
    ["reads","bases","q20","q30"].forEach((m,i)=>controls.appendChild(makeButton(m.toUpperCase(),m,i===0)));

    const draw = (mode) => {
      controls.querySelectorAll("button").forEach(b=>b.classList.toggle("is-active", b.dataset.value===mode));
      const d=data[mode]; const quality=mode.startsWith("q");
      const before=Number(d.before||0), after=Number(d.after||0);
      const ratio=quality ? (after || 0) : (before ? after/before : 0);
      const delta=(after-before)*100;
      const beforeLabel=quality?pct(before):fmt(before), afterLabel=quality?pct(after):fmt(after);
      const beforeSize=fitValueSize(beforeLabel), afterSize=fitValueSize(afterLabel);
      const centerLabel=quality ? `${delta>=0?"+":""}${fmt(delta,1)} pp` : `${fmt(ratio*100,0)}%`;
      const centerCaption=quality ? "change" : "retained";
      chart.innerHTML = `
        <svg viewBox="0 0 960 275" role="img" aria-label="${mode} before and after filtering">
          <defs>
            <filter id="asuShadow"><feDropShadow dx="0" dy="5" stdDeviation="7" flood-opacity=".14"/></filter>
          </defs>
          <rect x="20" y="50" width="360" height="170" rx="20" fill="${ASU.black}" filter="url(#asuShadow)"/>
          <text x="52" y="90" fill="${ASU.gold}" font-size="17" font-weight="800">BEFORE</text>
          <text x="52" y="151" fill="${ASU.white}" font-size="${beforeSize}" font-weight="800">${beforeLabel}</text>
          <text x="52" y="187" fill="#d6d6d6" font-size="16">${quality?"quality rate":"input total"}</text>

          <line x1="398" y1="135" x2="562" y2="135" stroke="${ASU.maroon}" stroke-width="6" stroke-linecap="round"/>
          <path d="M548 122 L568 135 L548 148 Z" fill="${ASU.maroon}"/>
          <circle cx="480" cy="135" r="45" fill="${ASU.gold}" stroke="${ASU.white}" stroke-width="6"/>
          <text x="480" y="131" text-anchor="middle" fill="${ASU.black}" font-size="20" font-weight="900">${centerLabel}</text>
          <text x="480" y="154" text-anchor="middle" fill="${ASU.black}" font-size="12" font-weight="800" letter-spacing=".7">${centerCaption.toUpperCase()}</text>

          <rect x="580" y="50" width="360" height="170" rx="20" fill="${ASU.maroon}" filter="url(#asuShadow)"/>
          <text x="612" y="90" fill="${ASU.gold}" font-size="17" font-weight="800">AFTER FILTERING</text>
          <text x="612" y="151" fill="${ASU.white}" font-size="${afterSize}" font-weight="800">${afterLabel}</text>
          <text x="612" y="187" fill="#f2dfe6" font-size="16">${quality ? `${delta>=0?"+":""}${fmt(delta,1)} percentage points` : `${pct(ratio)} retained`}</text>
        </svg>`;
      metrics.innerHTML = `
        <div><span>Reads retained</span><strong>${pct(data.reads.retention)}</strong></div>
        <div><span>Bases retained</span><strong>${pct(data.bases.retention)}</strong></div>
        <div><span>Adapter-positive reads</span><strong>${fmt(data.adapters.count)}</strong><small>${pct(data.adapters.fraction)} of input</small></div>
        <div><span>Q20 improvement</span><strong>${fmt((data.q20.after-data.q20.before)*100,1)} pp</strong></div>`;
    };
    controls.addEventListener("click", e=>{ const b=e.target.closest("button"); if(b) draw(b.dataset.value); });
    draw("reads");
  };

  const renderSegmentViz = (root) => {
    let payload;
    try { payload = JSON.parse(root.dataset.escapeSegments || "{}"); } catch { return; }

    const data = payload.segments || [];
    const threshold = Number(payload.threshold || 0);
    const breadthThreshold = Number(payload.breadth_threshold ?? 0.95);
    const maxNFraction = Number(payload.max_n_fraction ?? 0.01);

    root.innerHTML = "";

    const controls = document.createElement("div");
    controls.className = "escape-viz-controls escape-comparison-controls";

    const chart = document.createElement("div");
    chart.className = "escape-segment-chart escape-comparison-chart";

    root.append(controls, chart);

    [
      ["Median depth", "depth"],
      ["Breadth at depth", "breadth"],
      ["N content", "ncontent"],
      ["QC status", "status"],
    ].forEach((item, index) => {
      controls.appendChild(makeButton(item[0], item[1], index === 0));
    });

    const statusText = (value) => {
      const status = String(value ?? "REVIEW").toUpperCase();
      return status === "WARNING" ? "REVIEW" : status;
    };

    const statusColor = (value) => {
      const status = statusText(value);
      if (status === "PASS") return "#176B3A";
      if (status === "FAIL" || status === "ERROR") return "#B3261E";
      if (status === "MISSING") return "#AEB4BC";
      return ASU.gold;
    };

    const draw = (mode) => {
      controls.querySelectorAll("button").forEach((button) => {
        button.classList.toggle("is-active", button.dataset.value === mode);
      });

      const maxDepth = Math.max(
        ...data.map((record) => Number(record.median_depth) || 0),
        threshold,
        1,
      );

      chart.innerHTML = "";

      data.forEach((record) => {
        const row = document.createElement("div");
        row.className = "escape-segment-row escape-comparison-row";

        let label = "";
        let width = 0;
        let color = "#AEB4BC";
        let marker = "";

        if (mode === "depth") {
          const value = Number(record.median_depth) || 0;
          width = Math.max(2, Math.log10(value + 1) / Math.log10(maxDepth + 1) * 100);
          label = `${fmt(value, 1)}x`;
          color = statusColor(record.coverage_status);
          marker = `<span class="escape-threshold-marker" style="left:${Math.log10(threshold + 1) / Math.log10(maxDepth + 1) * 100}%"></span>`;
        } else if (mode === "breadth") {
          const value = Number(record.breadth_covered) || 0;
          width = Math.max(2, Math.min(100, value * 100));
          label = pct(value);
          color = statusColor(record.coverage_status);
          marker = `<span class="escape-threshold-marker" style="left:${Math.min(100, breadthThreshold * 100)}%"></span>`;
        } else if (mode === "ncontent") {
          const value = record.n_fraction == null ? NaN : Number(record.n_fraction);
          const finite = Number.isFinite(value);
          const denominator = maxNFraction > 0 ? maxNFraction : 1;
          width = finite ? Math.max(2, Math.min(100, value / denominator * 100)) : 2;
          label = finite ? pct(value) : "NA";
          color = statusColor(record.n_content_status);
          marker = '<span class="escape-threshold-marker" style="left:100%"></span>';
        } else {
          const status = statusText(record.overall_status);
          width = 100;
          label = status;
          color = statusColor(status);
        }

        row.innerHTML = `
          <span class="escape-segment-name">${record.segment}</span>
          <span class="escape-segment-track">
            <span class="escape-segment-fill" style="--bar-width:${width}%;--bar-color:${color}"></span>
            ${marker}
          </span>
          <span class="escape-segment-value">${label}</span>`;

        chart.appendChild(row);
      });
    };

    controls.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (button) draw(button.dataset.value);
    });

    draw("depth");
  };

  const initialize = () => {
    document.querySelectorAll("table").forEach(enhanceTable);
    document.querySelectorAll(".escape-read-viz").forEach(renderReadViz);
    document.querySelectorAll(".escape-segment-viz").forEach(renderSegmentViz);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
