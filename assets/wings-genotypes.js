/* Descriptive frequencies of recorded WINGS samples or public runs. */
(function (root) {
  "use strict";
  const SCHEMA = "wings.genotype-frequencies.v1";
  const STATUS = {unassigned:"Not assigned", no_result:"No genotype result", missing_call:"Missing genotype label", conflicting_calls:"Conflicting calls", unrecognized_call:"Unrecognized genotype label", not_eligible:"Not eligible for GenoFLU", not_run:"Skipped / not run", disabled:"GenoFLU disabled", failed:"Genotyping failed"};
  const ASU = {maroon:"#8C1D40", gold:"#FFC627", black:"#000000", white:"#FFFFFF", green:"#78BE20", blue:"#00A3E0", orange:"#FF7F32", gray:"#747474", copper:"#AF674B", turquoise:"#4AB7C4", pink:"#E74973"};
  const PALETTE = [ASU.maroon, ASU.gold, ASU.blue, ASU.green, ASU.orange, ASU.copper, ASU.turquoise, ASU.pink, ASU.black, ASU.gray];
  const PATTERNS = {
    other: {id:"gf-other", ink:ASU.black, path:"M-2 2L2 -2M0 8L8 0M6 10L10 6"},
    "status:unassigned": {id:"gf-unassigned", ink:ASU.gray, path:"M-2 6L2 10M0 0L8 8M6 -2L10 2"},
    "status:no_result": {id:"gf-no-result", ink:ASU.gray, dots:true},
    "status:missing_call": {id:"gf-missing-call", ink:ASU.black, path:"M0 4H8"},
    "status:conflicting_calls": {id:"gf-conflicting-calls", ink:ASU.maroon, path:"M0 0L8 8M0 8L8 0"},
    "status:unrecognized_call": {id:"gf-unrecognized-call", ink:ASU.black, path:"M4 0V8"},
    "status:not_eligible": {id:"gf-not-eligible", ink:ASU.gray, path:"M0 2H8M0 6H8"},
    "status:not_run": {id:"gf-not-run", ink:ASU.copper, path:"M0 4H8"},
    "status:disabled": {id:"gf-disabled", ink:ASU.gray, path:"M2 0V8M6 0V8"},
    "status:failed": {id:"gf-failed", ink:ASU.maroon, dots:true}
  };
  const count = n => n.toLocaleString("en-US");
  const percent = n => (n * 100).toFixed(1) + "%";
  const isMonth = value => typeof value === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(value) && Number(value.slice(0, 4)) > 0;
  const keyOf = group => group.status === "assigned" ? "call:" + group.genotype : "status:" + group.status;
  const labelOf = key => key === "other" ? "Other assigned genotypes" : key.startsWith("call:") ? key.slice(5) : STATUS[key.slice(7)];
  // Normalize only known country aliases; preserve state and county boundaries.
  const locationParts = value => {
    const parts = value.split("/").map(part => part.trim()).filter(Boolean);
    if (parts.length && ["usa", "us", "u.s.", "u.s.a.", "united states", "united states of america"].includes(parts[0].toLowerCase())) parts[0] = "United States";
    return parts;
  };
  const locationLabel = value => locationParts(value).join(" / ") || "Not recorded";
  const locationMatches = (recorded, selected) => {
    const actual = locationParts(recorded), wanted = locationParts(selected);
    return wanted.length > 0 && wanted.length <= actual.length && wanted.every((part, i) => part.toLowerCase() === actual[i].toLowerCase());
  };
  const locationChoices = groups => [...new Set(groups.flatMap(group => {
    const parts = locationParts(group.location);
    return parts.map((_, i) => parts.slice(0, i + 1).join(" / "));
  }))].sort();
  const units = data => data.unit === "Source comparison" ? {source:"all", name:"All", noun:"records", singular:"record"} : data.unit === "WINGS sample" ? {source:"wings", name:"WINGS", noun:"samples", singular:"WINGS sample"} : {source:"public", name:"Public Data", noun:"runs", singular:"SRA run"};
  const monthLabel = value => `${["January","February","March","April","May","June","July","August","September","October","November","December"][Number(value.slice(5))-1]} ${value.slice(0,4)}`;
  function availableMonths(data) {
    const months = data.groups.map(g => g.month).filter(isMonth).sort();
    return months.length ? monthRange(months[0], months.at(-1)) : [];
  }

  function validate(data) {
    if (!data || data.schema_version !== SCHEMA || !["SRA run", "WINGS sample"].includes(data.unit) || typeof data.has_metadata !== "boolean" || !Array.isArray(data.groups) || data.groups.length > 100000) throw Error("Choose a WINGS genotype-frequency JSON snapshot.");
    let total = 0;
    for (const group of data.groups) {
      if (!group || !Number.isSafeInteger(group.n) || group.n <= 0 || !["assigned", ...Object.keys(STATUS)].includes(group.status) || ![group.host, group.location].every(v => typeof v === "string" && v.length <= 1000) || !(group.month === null || isMonth(group.month)) || (group.status === "assigned" ? typeof group.genotype !== "string" || !group.genotype.trim() || group.genotype.length > 100 : group.genotype !== null)) throw Error("Snapshot contains an invalid count, category, or collection month.");
      if (!data.has_metadata && group.month !== null) throw Error("Collection months require metadata.");
      total += group.n;
    }
    if (!Number.isSafeInteger(total)) throw Error("Snapshot total is too large.");
    const noun = units(data).noun;
    if (!data.audit || data.audit[`included_${noun}`] !== total || data.audit[`assigned_${noun}`] !== data.groups.filter(g => g.status === "assigned").reduce((sum, g) => sum + g.n, 0)) throw Error("Snapshot counts do not reconcile with its audit totals.");
    return data;
  }

  function monthRange(first, last) {
    const ordinal = value => Number(value.slice(0, 4)) * 12 + Number(value.slice(5)) - 1;
    const start = ordinal(first), end = ordinal(last);
    if (end - start > 1200) throw Error("Choose a collection period of 100 years or less.");
    const result = [];
    for (let i = start; i <= end; i++) result.push(String(Math.floor(i / 12)).padStart(4, "0") + "-" + String(i % 12 + 1).padStart(2, "0"));
    return result;
  }

  function summarize(data, options = {}) {
    if (data.unit === "Source comparison") return summarizeComparison(data, options);
    const {view = "overall", denominator = "assigned", genotype = "", host = "", location = "", from = "", through = ""} = options;
    if (typeof genotype !== "string" || (genotype && !data.groups.some(g => g.status === "assigned" && g.genotype === genotype))) throw Error("Choose a recorded genotype.");
    if (!["overall", "monthly"].includes(view) || !["assigned", "all"].includes(denominator)) throw Error("Invalid chart selection.");
    if ((from && !isMonth(from)) || (through && !isMonth(through)) || (from && through && from > through)) throw Error("Choose a valid month range, with From no later than Through.");
    if (view === "monthly" && !data.has_metadata) throw Error("Collection metadata is needed for monthly frequencies.");
    const matched = data.groups.filter(g => (!host || g.host === host) && (!location || locationMatches(g.location, location)));
    const needsDates = view === "monthly" || from || through;
    const excludedDates = needsDates ? matched.filter(g => g.month === null).reduce((s, g) => s + g.n, 0) : 0;
    const included = matched.filter(g => (!needsDates || g.month !== null) && (!from || g.month >= from) && (!through || g.month <= through));
    const buckets = new Map(), totals = new Map();
    for (const group of included) {
      const period = view === "monthly" ? group.month : "Overall";
      if (!buckets.has(period)) buckets.set(period, {period, total:0, assigned:0, counts:new Map()});
      const bucket = buckets.get(period), key = keyOf(group);
      bucket.total += group.n;
      if (group.status === "assigned") bucket.assigned += group.n;
      bucket.counts.set(key, (bucket.counts.get(key) || 0) + group.n);
      if (group.status === "assigned") totals.set(key, (totals.get(key) || 0) + group.n);
    }
    const ranked = [...totals].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    const top = ranked.slice(0, 10).map(([key]) => key);
    const series = genotype ? ["call:" + genotype] : [...top];
    if (!genotype && ranked.length > 10) series.push("other");
    if (!genotype && denominator === "all") for (const key of Object.keys(STATUS)) if (included.some(g => g.status === key)) series.push("status:" + key);
    const periods = [...buckets.keys()].sort();
    if (view === "monthly" && periods.length) for (const period of monthRange(from || periods[0], through || periods.at(-1))) if (!buckets.has(period)) buckets.set(period, {period, total:0, assigned:0, counts:new Map()});
    const rows = [...buckets.values()].sort((a, b) => a.period.localeCompare(b.period)).map(bucket => {
      const n = denominator === "assigned" ? bucket.assigned : bucket.total;
      return {...bucket, denominator:n, values:series.map(key => {
        const value = key === "other" ? ranked.slice(10).reduce((s, [k]) => s + (bucket.counts.get(k) || 0), 0) : bucket.counts.get(key) || 0;
        return {key, n:value, share:n ? value / n : null};
      })};
    });
    return {view, denominator, genotype, host, location, from, through, series, rows, excludedDates, unit:data.unit, ...units(data),
      genotypeRuns:genotype ? totals.get("call:" + genotype) || 0 : null,
      total:included.reduce((s, g) => s + g.n, 0), assigned:included.filter(g => g.status === "assigned").reduce((s, g) => s + g.n, 0),
      distinctGenotypes:ranked.length};
  }

  function combineSources(datasets) {
    // Control choices use the union; frequency denominators remain source-specific.
    const checked = datasets.map(validate);
    const keys = checked.map(d => units(d).source);
    if (!checked.length || new Set(keys).size !== keys.length) throw Error("Choose distinct data sources.");
    return {unit:"Source comparison", has_metadata:checked.some(d => d.has_metadata),
      datasets:checked, groups:checked.flatMap(d => d.groups)};
  }

  function summarizeComparison(data, options) {
    const genotype = options.genotype || "";
    if (typeof genotype !== "string" || (genotype && !data.groups.some(g => g.status === "assigned" && g.genotype === genotype))) throw Error("Choose a recorded genotype.");
    const parts = data.datasets.map(d => summarize({...d, has_metadata:true}, {...options, genotype:""}));
    const totals = new Map();
    for (const part of parts) for (const row of part.rows) for (const [key,n] of row.counts) if (key.startsWith("call:")) totals.set(key,(totals.get(key)||0)+n);
    const ranked = [...totals].sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0]));
    const top = ranked.slice(0,10).map(([key]) => key);
    const series = genotype ? ["call:"+genotype] : [...top];
    if (!genotype && ranked.length > 10) series.push("other");
    if (!genotype && options.denominator === "all") for (const status of Object.keys(STATUS)) {
      const key = "status:"+status;
      if (parts.some(p => p.rows.some(row => row.counts.has(key)))) series.push(key);
    }
    let periods = [...new Set(parts.flatMap(p => p.rows.map(r => r.period)))].sort();
    if (parts[0].view === "monthly" && periods.length) periods = monthRange(periods[0],periods.at(-1));
    for (const part of parts) {
      const rows = new Map(part.rows.map(r => [r.period,r]));
      part.genotype = genotype;
      part.series = series;
      part.genotypeRuns = genotype ? part.rows.reduce((n,r) => n+(r.counts.get("call:"+genotype)||0),0) : null;
      part.rows = periods.map(period => {
        const row = rows.get(period) || {period,total:0,assigned:0,denominator:0,counts:new Map()};
        return {...row,values:series.map(key => {
          const n = key === "other" ? [...row.counts].filter(([k]) => k.startsWith("call:") && !top.includes(k)).reduce((sum,[,count]) => sum+count,0) : row.counts.get(key)||0;
          return {key,n,share:row.denominator ? n/row.denominator : null};
        })};
      });
    }
    const {view,denominator,host,location,from,through} = parts[0];
    return {view,denominator,host,location,from,through,...units(data),unit:data.unit,parts,series,genotype,
      rows:periods.map((period,i) => ({period,cohorts:parts.map(p => p.rows[i])})),
      total:parts.reduce((n,p) => n+p.total,0), distinctGenotypes:ranked.length};
  }

  function countEntries(row, summary) {
    const key = "call:" + summary.genotype;
    return summary.genotype ? [[key, row.counts.get(key) || 0]] : [...row.counts].sort();
  }

  function csvExport(summary) {
    if (summary.source === "all") {
      const lines = [["period","category","record_count","denominator","denominator_records","percent","data_source","unit"]];
      for (const part of summary.parts) for (const row of part.rows) for (const [key,n] of countEntries(row,part)) {
        const eligible = part.denominator === "all" || key.startsWith("call:");
        lines.push([row.period,labelOf(key),n,part.denominator === "assigned" ? `Assigned ${part.noun}` : `All included ${part.noun}`,row.denominator,eligible && row.denominator ? (100*n/row.denominator).toFixed(6) : "",part.name,part.unit]);
      }
      return encodeCsv(lines);
    }
    const local = summary.source === "wings";
    const lines = [["period", "category", local ? "sample_count" : "run_count", "denominator", local ? "denominator_samples" : "denominator_runs", "percent", "data_source", "unit"]];
    for (const row of summary.rows) for (const [key, n] of countEntries(row, summary)) {
      const eligible = summary.denominator === "all" || key.startsWith("call:");
      lines.push([row.period, labelOf(key), n, summary.denominator === "assigned" ? `Assigned ${summary.noun}` : `All included ${summary.noun}`, row.denominator, eligible && row.denominator ? (100 * n / row.denominator).toFixed(6) : "", summary.name, summary.unit]);
    }
    return encodeCsv(lines);
  }

  function encodeCsv(lines) {
    const cell = value => '"' + String(value).replace(/^[=+@-]/, c => "'" + c).replaceAll('"', '""') + '"';
    return lines.map(row => row.map(cell).join(",")).join("\r\n") + "\r\n";
  }

  function chartRows(summary, showAllMonths = false) {
    return summary.view === "monthly" && !showAllMonths ? summary.rows.filter(row => summary.source === "all" ? row.cohorts.some(c => c.denominator > 0) : row.denominator > 0) : summary.rows;
  }

  const api = {validate, summarize, csvExport, monthRange, chartRows, availableMonths, monthLabel, combineSources};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.WINGS_GENOTYPE_FREQUENCIES = api;
  if (typeof document === "undefined") return;

  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const svgNode = (tag, attrs = {}, text) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const color = (key, series) => PATTERNS[key] ? `url(#${PATTERNS[key].id})` : PALETTE[series.indexOf(key) % PALETTE.length];
  function patternDefinitions() {
    const defs = svgNode("defs");
    for (const pattern of Object.values(PATTERNS)) {
      const node = svgNode("pattern", {id:pattern.id, width:8, height:8, patternUnits:"userSpaceOnUse"});
      node.append(svgNode("rect", {width:8, height:8, fill:ASU.white}));
      node.append(pattern.dots ? svgNode("circle", {cx:4, cy:4, r:1.5, fill:pattern.ink}) : svgNode("path", {d:pattern.path, fill:"none", stroke:pattern.ink, "stroke-width":1.5}));
      defs.append(node);
    }
    return defs;
  }
  const save = (content, type, filename) => {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const a = element("a"); a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  function draw(summary, showAllMonths = false) {
    const chart = document.getElementById("gf-chart"); chart.replaceChildren();
    document.getElementById("gf-legend").replaceChildren();
    const parts = summary.parts || [summary];
    if (!parts.some(p => p.rows.some(row => row.denominator > 0))) {
      chart.append(element("p", `No eligible ${summary.noun} match these selections.`, "gf-empty"));
      return null;
    }
    const monthly = summary.view === "monthly";
    const periods = chartRows(summary, showAllMonths).map(row => row.period);
    const omitted = summary.rows.length - periods.length;
    const calendarNote = omitted ? `${omitted} months without eligible records omitted. Spacing between bars does not represent elapsed time.` : "";
    const width = monthly ? Math.max(900, periods.length * 42 + 140) : 980;
    const panelHeight = monthly ? 370 : 105 + summary.series.length * 34;
    const height = 85 + parts.length * panelHeight;
    const svg = svgNode("svg", {viewBox:`0 0 ${width} ${height}`, width, height, role:"img", "aria-labelledby":"gf-svg-title gf-svg-desc"});
    const title = `${summary.name}: ${summary.genotype || "genotype"} frequencies${monthly ? " by collection month" : ""}`;
    const description = parts.map(p => `${p.name}: percent of ${p.denominator === "assigned" ? "assigned" : "included"} ${p.noun}. One record per ${p.singular}.`).join(" ") + (summary.source === "all" ? " Sources share the time axis and genotype colors; each source has its own denominator." : "") + ` ${summary.host || "All hosts"}; ${summary.location ? locationLabel(summary.location) : "All locations"}.`;
    svg.append(svgNode("title", {id:"gf-svg-title"}, title), svgNode("desc", {id:"gf-svg-desc"}, description), patternDefinitions(), svgNode("rect", {width,height,fill:ASU.white}));
    svg.append(svgNode("text", {x:monthly ? 65 : 185,y:24,fill:ASU.black,"font-size":17,"font-weight":650}, title));
    parts.forEach((part, panelIndex) => {
      const offset = 38 + panelIndex * panelHeight;
      const left = monthly ? 65 : 185;
      svg.append(svgNode("text", {x:left,y:offset+16,fill:ASU.black,"font-size":13,"font-weight":650}, `${part.name} · Percent of ${part.denominator === "assigned" ? "assigned" : "included"} ${part.noun}`));
      if (!monthly) {
        const row = part.rows[0], plotWidth = 600, top = offset+38, bottom = offset+panelHeight-28;
        if (!row?.denominator) {
          svg.append(svgNode("text", {x:left,y:top+20,fill:ASU.gray,"font-size":13}, `No eligible ${part.noun} in this selection.`));
          return;
        }
        for (const tick of [0,.25,.5,.75,1]) {
          const x = left + tick*plotWidth;
          svg.append(svgNode("line", {x1:x,x2:x,y1:top-8,y2:bottom,stroke:ASU.gray}));
          svg.append(svgNode("text", {x,y:bottom+18,fill:ASU.black,"text-anchor":"middle","font-size":12}, `${tick*100}%`));
        }
        row.values.forEach((value,index) => {
          const y = top+index*34;
          svg.append(svgNode("text", {x:left-12,y:y+17,"text-anchor":"end",fill:ASU.black,"font-size":13}, value.key === "other" ? "Other assigned" : labelOf(value.key)));
          const bar = svgNode("rect", {x:left,y,width:value.share*plotWidth,height:24,rx:3,fill:color(value.key,summary.series)});
          bar.append(svgNode("title", {}, `${part.name} · ${labelOf(value.key)}: ${count(value.n)} / ${count(row.denominator)} ${part.noun} (${percent(value.share)})`));
          svg.append(bar,svgNode("text", {x:left+value.share*plotWidth+9,y:y+17,fill:ASU.black,"font-size":12}, `${percent(value.share)}  (${count(value.n)})`));
        });
      } else {
        const indexed = new Map(part.rows.map(r => [r.period,r]));
        const rows = periods.map(period => indexed.get(period));
        const top=offset+38, bottom=offset+276, step=(width-100)/rows.length, barWidth=Math.min(48,step*.74);
        for (const tick of [0,.25,.5,.75,1]) {
          const y=bottom-tick*(bottom-top);
          svg.append(svgNode("line", {x1:left,x2:width-25,y1:y,y2:y,stroke:ASU.gray}));
          svg.append(svgNode("text", {x:left-9,y:y+4,"text-anchor":"end",fill:ASU.black,"font-size":12}, `${tick*100}%`));
        }
        rows.forEach((row,i) => {
          const x=left+i*step+(step-barWidth)/2;
          let bottomY=bottom;
          if (!row.denominator) {
            const gap=svgNode("rect", {x,y:top,width:barWidth,height:bottom-top,fill:ASU.white,stroke:ASU.gray,"stroke-dasharray":"3 3"});
            gap.append(svgNode("title", {}, `${part.name} · ${row.period}: no eligible ${part.noun}; frequency unavailable`));svg.append(gap);
          }
          for (const value of row.values) if (value.n) {
            const h=value.share*(bottom-top);bottomY-=h;
            const label=`${part.name} · ${row.period}, ${labelOf(value.key)}: ${count(value.n)} of ${count(row.denominator)} ${part.noun}, ${percent(value.share)}`;
            const bar=svgNode("rect", {x,y:bottomY,width:barWidth,height:h,fill:color(value.key,summary.series),tabindex:0,"aria-label":label});
            bar.append(svgNode("title", {}, label));svg.append(bar);
          }
          svg.append(svgNode("text", {x:x+barWidth/2,y:bottom+17,"text-anchor":"middle",fill:ASU.black,"font-size":10}, row.denominator ? `n=${row.denominator}` : "—"));
          svg.append(svgNode("text", {x:x+barWidth/2,y:bottom+35,transform:`rotate(45 ${x+barWidth/2} ${bottom+35})`,fill:ASU.black,"font-size":11}, row.period));
        });
      }
    });
    if (calendarNote || (monthly && parts.some(p => p.rows.some(r => !r.denominator)))) svg.append(svgNode("text", {x:65,y:height-12,fill:ASU.black,"font-size":12}, calendarNote || "Dashed columns: no eligible records in that source; frequency unavailable."));
    if (monthly) for (const key of summary.series) {
      const label=element("span"), swatch=svgNode("svg", {viewBox:"0 0 12 12",width:12,height:12,class:"gf-swatch","aria-hidden":"true"});
      swatch.append(svgNode("rect", {width:12,height:12,fill:color(key,summary.series)}));
      label.append(swatch,document.createTextNode(labelOf(key)));document.getElementById("gf-legend").append(label);
    }
    chart.append(svg);
    return svg;
  }

  function mount() {
    let snapshot = null, summary = null, chart = null;
    const sources = new Map(), selections = new Map();
    const $ = id => document.getElementById("gf-" + id);
    const selectors = ["view", "denominator", "genotype", "host", "location", "from", "through"];
    const status = (message, error = false) => { $("status").textContent = message; $("status").classList.toggle("error", error); };
    const render = () => {
      if (!snapshot) return;
      try {
        summary = summarize(snapshot, Object.fromEntries(selectors.map(id => [id, $(id).value])));
        const noun = summary.noun, comparison = summary.source === "all", parts = summary.parts || [summary];
        const calendarControl = $("calendar-control"), calendarToggle = $("show-empty");
        calendarControl.hidden = summary.view !== "monthly";
        calendarControl.replaceChildren(calendarToggle, document.createTextNode(comparison
          ? " Show all calendar months (including months empty in both sources)"
          : " Show all calendar months (including months without eligible records)"));
        let calendarHelp = $("calendar-help");
        if (!calendarHelp) {
          calendarHelp = element("p");
          calendarHelp.id = "gf-calendar-help";
          calendarControl.after(calendarHelp);
        }
        calendarHelp.hidden = summary.view !== "monthly";
        calendarToggle.setAttribute("aria-describedby", "gf-calendar-help");
        const emptyMonthCount = summary.rows.length - chartRows(summary, false).length;
        calendarHelp.textContent = comparison
          ? (emptyMonthCount
            ? `Unchecked: omit ${count(emptyMonthCount)} months with no eligible records in either source. A month stays visible in both panels when either source has data.`
            : "Every month in this range has eligible records in at least one source, so this toggle does not change the graph. Select WINGS to hide months without eligible WINGS records.")
          : (emptyMonthCount
            ? `Unchecked: omit ${count(emptyMonthCount)} months without eligible records. Checked: show the full calendar span.`
            : "Every month in this range has eligible records, so this toggle does not change the graph.");
        chart = draw(summary, calendarToggle.checked);
        $("chart-title").textContent = summary.view === "monthly" ? "Frequency by collection month" : "Frequency by genotype";
        $("denominator-note").textContent = (comparison ? `Each panel uses its own ${summary.denominator === "assigned" ? "assigned-genotype" : "included-record"} denominator for the selected period. The panels share the same months and genotype colors.` : summary.denominator === "assigned" ? `Each percentage uses ${noun} with an assigned genotype in the selected period. Unassigned and missing results are counted separately below.` : `Each percentage uses all included ${noun} in the selected period, including unavailable assignments.`) + (summary.genotype ? ` Showing ${summary.genotype}; the denominator includes the other genotypes matching your host, location, and date filters.` : "");
        $("stats").replaceChildren();
        const cards = comparison ? [["WINGS samples",parts.find(p=>p.source==="wings")?.total ?? "Not loaded"],["Public runs",parts.find(p=>p.source==="public")?.total ?? "Not loaded"],summary.genotype ? ["Genotype shown",summary.genotype] : ["Recorded genotypes",summary.distinctGenotypes]] : [[`Included ${noun}`, summary.total], ["Assigned genotype", summary.assigned], summary.genotype ? [summary.genotype + " " + noun, summary.genotypeRuns] : ["Recorded genotypes", summary.distinctGenotypes]];
        for (const [title, n] of cards) {
          const card = element("div", undefined, "gf-stat"); card.append(element("span", title), element("strong", typeof n === "number" ? count(n) : n)); $("stats").append(card);
        }
        $("coverage").textContent = parts.map(p => `${comparison ? p.name+": " : ""}${count(p.total-p.assigned)} included ${p.noun} have no usable genotype assignment. ${p.excludedDates ? count(p.excludedDates)+` ${p.noun} without a usable collection month are excluded from this date-based view. ` : ""}`).join(" ") + (!summary.genotype && summary.distinctGenotypes > 10 ? "The graph shows the ten most frequent genotypes; Other assigned combines the remaining genotypes. Exact counts are available below." : "");
        const table = element("table"), head = element("thead"), heading = element("tr"), body = element("tbody");
        for (const title of [...(comparison ? ["Source","Unit"] : []),"Period", "Genotype / status", comparison ? "Count" : noun === "samples" ? "Samples" : "Runs", "Denominator", "Percent"]) heading.append(element("th", title));
        head.append(heading);
        let displayed = 0;
        for (const part of parts) for (const row of part.rows) for (const [key, n] of countEntries(row, part)) {
          if (displayed++ >= 500) continue;
          const tr = element("tr"), eligible = part.denominator === "all" || key.startsWith("call:");
          for (const value of [...(comparison ? [part.name,part.unit] : []),row.period, labelOf(key), count(n), count(row.denominator), eligible ? row.denominator ? percent(n / row.denominator) : "Unavailable" : "Excluded"]) tr.append(element("td", value));
          body.append(tr);
        }
        table.append(head, body); $("table").replaceChildren(table);
        if (displayed > 500) $("table").append(element("p", "Showing the first 500 rows. Download includes every row."));
        $("export-svg").disabled = !chart; $("export-csv").disabled = !summary.total;
        $("export-csv").textContent = summary.genotype ? "Download selected genotype counts" : "Download all genotype counts";
        status(comparison ? `${parts.map(p=>p.name).join(" and ")} loaded. Counts and percentages are calculated separately for each source.${parts.length === 1 ? " Open a completed run report to view its WINGS samples alongside public data." : ""}` : summary.source === "wings" ? "Recorded genotypes from this WINGS run. Counts use unique sample IDs." : snapshot.has_metadata ? "Collection metadata loaded. Counts use unique SRA run IDs." : "Overall public frequencies. Collection metadata is needed for monthly frequencies.");
      } catch (error) {
        chart = null; summary = null;
        $("chart").replaceChildren(); $("legend").replaceChildren(); $("table").replaceChildren(); $("stats").replaceChildren(); $("coverage").textContent = "";
        $("export-svg").disabled = true; $("export-csv").disabled = true; status(error.message, true);
      }
    };
    const activate = key => {
      if (!sources.has(key)) return;
      if (snapshot) selections.set(units(snapshot).source, Object.fromEntries([...selectors.map(id => [id, $(id).value]), ["showEmpty", $("show-empty").checked]]));
      snapshot = sources.get(key);
      const info = units(snapshot), local = key === "wings", comparison = key === "all", months = availableMonths(snapshot);
      // Start comparisons at the WINGS collection span; preserve user selections.
      const wingsMonths = key !== "public" && sources.has("wings")
        ? availableMonths(sources.get("wings")) : [];
      const remembered = selections.get(key) || (wingsMonths.length
        ? {from: wingsMonths[0], through: wingsMonths.at(-1)} : {});
      $("source").value = key;
      $("view").value = remembered.view || (months.length ? "monthly" : "overall");
      $("view").querySelector('[value="monthly"]').disabled = !months.length;
      if (!months.length) $("view").value = "overall";
      $("denominator").replaceChildren(new Option(`${comparison ? "Records" : local ? "Samples" : "Runs"} with an assigned genotype`, "assigned"), new Option(`All included ${info.noun}`, "all"));
      $("denominator").value = remembered.denominator || "assigned";
      const populate = (id, label, values, display = value => value) => {
        $(id).replaceChildren(new Option(label, ""));
        for (const value of values) $(id).append(new Option(display(value), value));
        $(id).value = values.includes(remembered[id]) ? remembered[id] : "";
      };
      populate("genotype", "All genotypes", [...new Set(snapshot.groups.filter(g => g.status === "assigned").map(g => g.genotype))].sort((a,b) => a.localeCompare(b, undefined, {numeric:true})));
      for (const field of ["host", "location"]) {
        populate(field, field === "host" ? "All hosts" : "All locations", field === "location" ? locationChoices(snapshot.groups) : [...new Set(snapshot.groups.map(g => g[field]))].sort(), field === "location" ? locationLabel : value => value);
        $(field).disabled = !snapshot.has_metadata;
      }
      populate("from", "First available month", months, monthLabel);
      populate("through", "Last available month", months, monthLabel);
      $("from").disabled = !months.length; $("through").disabled = !months.length;
      $("show-empty").checked = remembered.showEmpty || false;
      $("eyebrow").textContent = comparison ? "WINGS and public sequencing context" : local ? "This WINGS run" : "Public sequencing context";
      $("description").textContent = comparison ? "Compare recorded genotype frequencies across WINGS and public data on the same time axis." : local ? "See how often each recorded genotype occurs among the samples in this run." : "See how often each recorded genotype occurs in the public sequencing dataset.";
      $("unit-note").textContent = comparison ? "WINGS counts samples; Public Data counts SRA runs. Each panel uses its own denominator." : local ? "Each record is one WINGS sample. Percentages use this run's samples only." : "Each record is one public SRA run. Multiple runs may come from the same specimen.";
      const datasets = comparison ? snapshot.datasets : [snapshot];
      const attribution = $("source-description"); attribution.replaceChildren();
      if (datasets.some(d=>units(d).source==="wings")) attribution.append(document.createTextNode("Recorded GenoFLU results and collection metadata from this run's Surveillance Explorer. "));
      if (datasets.some(d=>units(d).source==="public")) {
        const link=element("a","andersen-lab/avian-influenza");
        link.setAttribute("href","https://github.com/andersen-lab/avian-influenza");
        link.setAttribute("target","_blank");link.setAttribute("rel","noopener noreferrer");
        attribution.append(document.createTextNode("Public genotype assignments and collection metadata from "),link,document.createTextNode("."));
      }
      $("source-info").textContent = datasets.map(d => {
        const refresh=d.report_refresh;
        return `${units(d).name}: ${d.built_at ? "Snapshot built: "+d.built_at+". " : ""}${d.source_commit ? "Source commit: "+d.source_commit+". " : ""}Files: ${(d.sources||[]).map(s=>s.name).join(", ")||"Not recorded"}.${d.report_snapshot?.sha256 ? " Embedded snapshot SHA-256: "+d.report_snapshot.sha256+"." : ""}${d.unit === "WINGS sample" && d.sources?.[0]?.sha256 ? " Explorer SHA-256: "+d.sources[0].sha256+"." : ""}${refresh ? " Public refresh: "+refresh.status+". "+(refresh.note||"") : ""}`;
      }).join("\n");
      $("controls").hidden = false; render();
    };
    const register = data => {
      const checked = validate(data), key = units(checked).source;
      availableMonths(checked);
      sources.set(key, checked);
      const option = $("source").querySelector(`[value="${key}"]`);
      option.disabled = false; option.textContent = units(checked).name;
      sources.set("all",combineSources(["wings","public"].filter(k=>sources.has(k)).map(k=>sources.get(k))));
      $("source").querySelector('[value="all"]').disabled = false;
      return key;
    };
    for (const key of ["all", "wings", "public"]) $("source").querySelector(`[value="${key}"]`).disabled = true;
    $("source").addEventListener("change", () => activate($("source").value));
    for (const id of selectors) $(id).addEventListener("change", render);
    $("show-empty").addEventListener("change", render);
    $("export-csv").addEventListener("click", () => { if (summary) save(csvExport(summary), "text/csv;charset=utf-8", `wings-genotype-frequencies-${summary.source}.csv`); });
    $("export-svg").addEventListener("click", () => { if (chart && summary) save(new XMLSerializer().serializeToString(chart), "image/svg+xml", `wings-genotype-frequencies-${summary.source}.svg`); });
    $("file").addEventListener("change", async event => {
      const file = event.target.files[0]; if (!file) return;
      try {
        if (file.size > 25_000_000) throw Error("Choose a snapshot under 25 MB.");
        const key = register(JSON.parse(await file.text()));
        if (snapshot && units(snapshot).source === key) snapshot = null;
        selections.delete(key); activate(key);
      } catch (error) { status("Snapshot was not loaded: " + error.message + (snapshot ? " The previous chart is still displayed." : ""), true); }
    });
    const local = document.getElementById("wings-genotype-local-data");
    let localError = "";
    if (local) {
      try {
        const data = JSON.parse(local.textContent);
        if (data.unit !== "WINGS sample") throw Error("Invalid WINGS sample source.");
        register(data);
      } catch (error) { localError = " WINGS samples unavailable: " + error.message; }
    }
    const embedded = document.getElementById("wings-genotype-frequency-data");
    const initial = embedded
      ? Promise.resolve().then(() => JSON.parse(embedded.textContent))
      : fetch("assets/data/genotype-frequencies.json", {cache:"no-cache"}).then(response => { if (!response.ok) throw Error(`HTTP ${response.status}`); return response.json(); });
    initial.then(data => {
      if (data.unit !== "SRA run") throw Error("Invalid public source.");
      register(data); activate("all");
      if (localError) status($("status").textContent + localError, true);
    }).catch(error => {
      if (sources.has("all")) activate("all");
      status("Could not load the public snapshot. Choose a frequency JSON file below. " + error.message + localError, true);
    });
  }
  document.addEventListener("DOMContentLoaded", mount);
})(typeof globalThis !== "undefined" ? globalThis : this);
