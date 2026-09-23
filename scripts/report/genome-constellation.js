(() => {
  "use strict";

  const COLORS = {
    maroon: "#8C1D40",
    pass: "#176B3A",
    maroonDark: "#5C1229",
    gold: "#FFC627",
    black: "#000000",
    white: "#FFFFFF",
    fail: "#B3261E",
    missing: "#AEB4BC",
    muted: "#5F6368",
  };

  const SEGMENT_ORDER = ["PB2", "PB1", "PA", "HA", "NP", "NA", "MP", "NS"];
  const SVG_NS = "http://www.w3.org/2000/svg";

  const fmt = (value, digits = 0) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return "Not available";
    return number.toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  };

  const pct = (value, digits = 1) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return "Not available";
    return `${fmt(number * 100, digits)}%`;
  };

  const safe = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  const statusText = (value) => {
    const text = String(value ?? "REVIEW").trim().toUpperCase();
    if (!text || ["NA", "N/A", "NONE", "NAN"].includes(text)) return "REVIEW";
    if (text === "WARNING") return "REVIEW";
    return text;
  };

  const statusColor = (value) => {
    switch (statusText(value)) {
      case "PASS": return COLORS.pass;
      case "FAIL":
      case "ERROR": return COLORS.fail;
      case "MISSING": return COLORS.missing;
      default: return COLORS.gold;
    }
  };

  const statusInk = (value) => (
    statusText(value) === "REVIEW" ? COLORS.black : COLORS.white
  );

  const polar = (cx, cy, radius, angle) => [
    cx + radius * Math.cos(angle - Math.PI / 2),
    cy + radius * Math.sin(angle - Math.PI / 2),
  ];

  const annularArcPath = (cx, cy, innerRadius, outerRadius, start, end) => {
    const [x1, y1] = polar(cx, cy, outerRadius, start);
    const [x2, y2] = polar(cx, cy, outerRadius, end);
    const [x3, y3] = polar(cx, cy, innerRadius, end);
    const [x4, y4] = polar(cx, cy, innerRadius, start);
    const largeArc = end - start > Math.PI ? 1 : 0;

    return [
      `M ${x1} ${y1}`,
      `A ${outerRadius} ${outerRadius} 0 ${largeArc} 1 ${x2} ${y2}`,
      `L ${x3} ${y3}`,
      `A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${x4} ${y4}`,
      "Z",
    ].join(" ");
  };

  const makeSvg = (tag, attrs = {}) => {
    const element = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  };

  const normalizeData = (payload) => {
    const lookup = new Map(
      (payload.segments || []).map((record) => [
        String(record.segment || "").trim().toUpperCase(),
        record,
      ]),
    );

    return SEGMENT_ORDER.map((segment) => lookup.get(segment) || {
      segment,
      contig: "",
      subtype_label: "",
      overall_status: "MISSING",
      coverage_status: "MISSING",
      length_status: "MISSING",
      n_content_status: "MISSING",
      median_depth: null,
      mean_depth: null,
      breadth_covered: null,
      n_fraction: null,
      length: null,
      candidate_count: 0,
      selection_status: "MISSING",
      selection_reason: "",
      consensus_source: "",
      medaka_consensus_status: "",
      medaka_variant_status: "",
      blast_status: "",
      blast_top_hit: "",
    });
  };

  const detailMarkup = (record, payload) => {
    const overall = statusText(record.overall_status);
    const subtype = String(record.subtype_label || "").trim();
    const candidateCount = Number(record.candidate_count || 0);
    const selectionStatus = String(record.selection_status || "").trim() || "Not recorded";
    const selectionReason = String(record.selection_reason || "").trim();
    const consensusSource = String(record.consensus_source || "").trim() || "Not recorded";
    const medakaConsensus = String(record.medaka_consensus_status || "").trim() || "Not recorded";
    const medakaVariants = String(record.medaka_variant_status || "").trim() || "Not recorded";
    const blastStatus = String(record.blast_status || "").trim() || "Not recorded";
    const blastHit = String(record.blast_top_hit || "").trim() || "No hit recorded";

    const nFraction = Number(record.n_fraction);
    const nContent = Number.isFinite(nFraction) ? pct(nFraction) : "Not available";
    const length = Number(record.length);

    const row = (label, value) => `<div><dt>${label}</dt><dd>${value}</dd></div>`;
    const section = (label, body, extra = "") => `
      <section class="escape-constellation-detail-section">
        <div class="escape-constellation-section-label">${label}</div>
        <dl>${body}</dl>
        ${extra}
      </section>`;

    const qcRows = [
      row("Coverage QC", safe(statusText(record.coverage_status))),
      row("Length QC", safe(statusText(record.length_status))),
      row("N-content QC", safe(statusText(record.n_content_status))),
    ].join("");

    const sequenceRows = [
      row("Median depth", `${fmt(record.median_depth, 1)}x`),
      row("Mean depth", `${fmt(record.mean_depth, 1)}x`),
      row(`Breadth at ≥${fmt(payload.threshold, 0)}x`, pct(record.breadth_covered)),
      row("Consensus length", Number.isFinite(length) ? `${fmt(length)} nt` : "Not available"),
      row("N content", nContent),
    ].join("");

    const provenanceRows = [
      row("Consensus source", safe(consensusSource)),
      row("Medaka consensus", safe(medakaConsensus)),
      row("Medaka variants", safe(medakaVariants)),
      row("IRMA candidates", `${fmt(candidateCount)} · ${safe(selectionStatus)}`),
    ].join("");

    const provenanceDetails = selectionReason ? `
      <details class="escape-constellation-more">
        <summary>IRMA selection details</summary>
        <p>${safe(selectionReason)}</p>
      </details>` : "";

    const identificationRows = [
      row("Contig", safe(record.contig || "Unknown")),
      row("BLAST status", safe(blastStatus)),
      row("Top BLAST hit", safe(blastHit)),
    ].join("");

    return `
      <div class="escape-detail-kicker">Selected genome segment</div>
      <div class="escape-constellation-detail-heading">
        <div class="escape-constellation-detail-title">
          <span>${safe(record.segment)}</span>
          ${subtype ? `<small>${safe(subtype)}</small>` : ""}
        </div>
        <span class="escape-detail-badge" style="background:${statusColor(overall)};color:${statusInk(overall)}">
          ${safe(overall)}
        </span>
      </div>

      <div class="escape-constellation-detail-sections">
        ${section("QC", qcRows)}
        ${section("Sequence", sequenceRows)}
        ${section("Provenance", provenanceRows, provenanceDetails)}
        ${section("Identification", identificationRows)}
      </div>

      <p class="escape-constellation-disclaimer">
        Evidence shown here was already generated by WINGS; the constellation adds no new subtype,
        genotype, reassortment, or transmission inference.
      </p>`;
  };

  const renderConstellation = (root) => {
    if (root.dataset.wingsConstellationRendered === "true") return;

    let payload;
    try {
      payload = JSON.parse(root.dataset.wingsConstellation || "{}");
    } catch (error) {
      root.innerHTML = '<p class="escape-constellation-error">Genome constellation data could not be parsed.</p>';
      return;
    }

    root.dataset.wingsConstellationRendered = "true";
    const data = normalizeData(payload);
    root.innerHTML = "";

    const layout = document.createElement("div");
    layout.className = "escape-constellation-layout";

    const stage = document.createElement("div");
    stage.className = "escape-constellation-stage";

    const detail = document.createElement("div");
    detail.className = "escape-constellation-detail";
    detail.setAttribute("aria-live", "polite");

    layout.append(stage, detail);
    root.appendChild(layout);

    const svg = makeSvg("svg", {
      viewBox: "0 0 600 600",
      class: "escape-constellation-svg",
      role: "img",
      "aria-label": "Interactive eight-segment influenza A genome constellation",
    });

    const cx = 300;
    const cy = 300;
    const innerRadius = 126;
    const outerRadius = 250;
    const labelRadius = 190;
    const markerRadius = 267;
    const gap = 0.032;
    const tau = Math.PI * 2;

    // Decorative inner halo.
    svg.appendChild(makeSvg("circle", {
      cx,
      cy,
      r: 109,
      fill: "none",
      stroke: "#E4E4E4",
      "stroke-width": 2,
    }));

    const center = makeSvg("circle", {
      cx,
      cy,
      r: 94,
      fill: COLORS.black,
      stroke: COLORS.gold,
      "stroke-width": 8,
    });
    svg.appendChild(center);

    const passCount = Number(payload.segments_pass || 0);
    const centerCount = makeSvg("text", {
      x: cx,
      y: cy - 14,
      "text-anchor": "middle",
      class: "escape-constellation-center-count",
    });
    centerCount.textContent = `${passCount}/8`;
    svg.appendChild(centerCount);

    const centerLabel = makeSvg("text", {
      x: cx,
      y: cy + 17,
      "text-anchor": "middle",
      class: "escape-constellation-center-label",
    });
    centerLabel.textContent = "SEGMENTS PASS";
    svg.appendChild(centerLabel);

    const h5 = String(payload.h5_status || "UNKNOWN").replaceAll("_", " ");
    const centerH5 = makeSvg("text", {
      x: cx,
      y: cy + 46,
      "text-anchor": "middle",
      class: "escape-constellation-center-h5",
    });
    centerH5.textContent = `H5: ${h5}`;
    svg.appendChild(centerH5);

    const groups = [];

    const selectRecord = (record, group) => {
      groups.forEach((item) => item.classList.remove("is-selected"));
      if (group) group.classList.add("is-selected");
      detail.innerHTML = detailMarkup(record, payload);
    };

    data.forEach((record, index) => {
      const start = (index / data.length) * tau + gap;
      const end = ((index + 1) / data.length) * tau - gap;
      const mid = (start + end) / 2;
      const overall = statusText(record.overall_status);

      const group = makeSvg("g", {
        class: "escape-constellation-segment",
        tabindex: "0",
        role: "button",
        "aria-label": `${record.segment} segment, ${overall}`,
      });

      const wedge = makeSvg("path", {
        d: annularArcPath(cx, cy, innerRadius, outerRadius, start, end),
        fill: statusColor(overall),
        class: "escape-constellation-wedge",
      });
      group.appendChild(wedge);

      const [labelX, labelY] = polar(cx, cy, labelRadius, mid);
      const hasSubtype = Boolean(String(record.subtype_label || "").trim());
      const label = makeSvg("text", {
        x: labelX,
        y: labelY - (hasSubtype ? 10 : 0),
        "text-anchor": "middle",
        "dominant-baseline": "middle",
        class: `escape-constellation-segment-label ${overall === "REVIEW" ? "is-dark" : ""}`,
      });
      label.textContent = record.segment;
      group.appendChild(label);

      if (hasSubtype) {
        const subtype = makeSvg("text", {
          x: labelX,
          y: labelY + 22,
          "text-anchor": "middle",
          "dominant-baseline": "middle",
          class: `escape-constellation-subtype-label ${overall === "REVIEW" ? "is-dark" : ""}`,
        });
        subtype.textContent = record.subtype_label;
        group.appendChild(subtype);
      }

      // Surface IRMA ambiguity without changing the QC call.
      if (Number(record.candidate_count || 0) > 1) {
        const [mx, my] = polar(cx, cy, markerRadius, mid);
        const badge = makeSvg("circle", {
          cx: mx,
          cy: my,
          r: 14,
          fill: COLORS.gold,
          stroke: COLORS.black,
          "stroke-width": 2,
          class: "escape-constellation-ambiguity",
        });
        const badgeText = makeSvg("text", {
          x: mx,
          y: my + 1,
          "text-anchor": "middle",
          "dominant-baseline": "middle",
          class: "escape-constellation-ambiguity-label",
        });
        badgeText.textContent = String(record.candidate_count);
        group.append(badge, badgeText);
      }

      const activate = () => selectRecord(record, group);
      group.addEventListener("click", activate);
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });

      groups.push(group);
      svg.appendChild(group);
    });

    stage.appendChild(svg);

    const legend = document.createElement("div");
    legend.className = "escape-constellation-legend";

    const statusLegend = document.createElement("div");
    statusLegend.className = "escape-constellation-legend-status";
    [
      ["PASS", COLORS.pass],
      ["REVIEW", COLORS.gold],
      ["FAIL", COLORS.fail],
      ["MISSING", COLORS.missing],
    ].forEach(([label, color]) => {
      const item = document.createElement("span");
      item.innerHTML = `<i style="background:${color}"></i>${label}`;
      statusLegend.appendChild(item);
    });

    const ambiguityLegend = document.createElement("div");
    ambiguityLegend.className = "escape-constellation-legend-ambiguity";
    ambiguityLegend.innerHTML = '<span><i class="escape-constellation-legend-count">#</i>IRMA candidates</span>';

    legend.append(statusLegend, ambiguityLegend);
    stage.appendChild(legend);

    if (groups.length) selectRecord(data[0], groups[0]);
  };

  const initialize = () => {
    document.querySelectorAll(".escape-constellation-viz").forEach(renderConstellation);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
