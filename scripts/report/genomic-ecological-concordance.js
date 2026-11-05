(() => {
  "use strict";

  const VERSION = "0.3.1";
  const SEGMENTS = ["HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS"];
  const FAMILIES = [
    ["host_vs_baseline", "Host effect"],
    ["ecology_vs_host", "Seasonal ecology effect"],
    ["environment_vs_ecology", "Weather effect"],
    ["migration_vs_ecology", "Migration context"],
  ];

  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const finite = value => typeof value === "number" && Number.isFinite(value);
  const signed = value => finite(value) ? `${value >= 0 ? "+" : ""}${value.toFixed(3)}` : "—";
  const qfmt = value => {
    if (!finite(value)) return "—";
    if (value < 0.001) return "<0.001";
    if (value < 0.01) return value.toFixed(4);
    return value.toFixed(3);
  };

  function friendlyStatus(model) {
    const code = model?.display_status || model?.status || "NOT_ESTIMABLE";
    return ({
      READY: "Ready",
      INSUFFICIENT_UNIQUE_SAMPLES: "Too few unique samples",
      INSUFFICIENT_INDEPENDENT_VARIATION: "Not independently estimable",
      INSUFFICIENT_PREDICTOR_VARIATION: "Insufficient predictor variation",
      INSUFFICIENT_COMPLETE_PAIRS: "Too few complete pairs",
      CONSTANT_GENETIC_DISTANCE: "No genetic-distance variation",
      NOT_ESTIMABLE: "Not estimable",
      INSUFFICIENT_MIGRATION_CONTEXTS: "Too few migration contexts",
      DESCRIPTIVE: "Descriptive added fit",
    })[code] || (String(code).includes("RANK_DEFICIENT") ? "Not independently estimable" : "Not estimable");
  }

  function plainDiagnostic(model, comparison) {
    const code = model?.display_status || model?.status || "";
    if (comparison === "migration_vs_ecology" && code === "INSUFFICIENT_MIGRATION_CONTEXTS") return model.diagnostic;
    if (code === "INSUFFICIENT_UNIQUE_SAMPLES" || String(code).includes("INSUFFICIENT_SAMPLES")) {
      return `${model.n_samples || 0} unique samples are available; at least ${model.minimum_unique_samples || 8} are required.`;
    }
    if (code === "INSUFFICIENT_INDEPENDENT_VARIATION" || String(code).includes("RANK_DEFICIENT")) {
      if (comparison === "environment_vs_ecology") {
        return "Environmental distance does not provide independent variation beyond the existing time, geography, host, and seasonal-ecology predictors in this dataset.";
      }
      return "The added predictor does not provide independent variation beyond the predictors already in the model.";
    }
    if (code === "INSUFFICIENT_PREDICTOR_VARIATION") {
      return "The added predictor does not vary enough across the available samples for this comparison.";
    }
    if (code === "INSUFFICIENT_COMPLETE_PAIRS") {
      return "Too few sample pairs have complete data for all predictors in this comparison.";
    }
    if (code === "CONSTANT_GENETIC_DISTANCE") {
      return "The available pairwise genetic distances do not vary enough to fit this comparison.";
    }
    return model?.diagnostic || "This comparison is not estimable for the available data.";
  }

  function modelCell(model, comparison) {
    const td = make("td", "wgec-result-cell");
    if (!model) {
      td.append(make("strong", "wgec-status", "Not available"));
      return td;
    }
    if (["READY", "DESCRIPTIVE"].includes(model.display_status || model.status)) {
      td.append(make("strong", "wgec-delta", `ΔR² ${signed(model.delta_r2)}`));
      const line = make("span", "wgec-statline", model.display_status === "DESCRIPTIVE" ? "Descriptive · p/q withheld" : `q ${qfmt(model.fdr_q)} · p ${qfmt(model.permutation_p)}`);
      const n = make("span", "wgec-n", `${model.n_samples} samples · ${model.n_pairs} pairs`);
      td.append(line, n);
      if (comparison === "migration_vs_ecology") td.append(make("span", "wgec-n", `${model.n_migration_contexts || 0} distinct state–night contexts`));
      if (model.display_status === "DESCRIPTIVE") td.append(make("span", "wgec-diagnostic", model.diagnostic));
      return td;
    }
    td.append(make("strong", "wgec-status", friendlyStatus(model)));
    td.append(make("span", "wgec-diagnostic", plainDiagnostic(model, comparison)));
    td.append(make("span", "wgec-n", `${model.n_samples || 0} samples · ${model.n_pairs || 0} pairs`));
    if (model.diagnostic) {
      const details = make("details", "wgec-technical");
      details.append(make("summary", "", "Technical detail"), make("span", "", model.diagnostic));
      td.append(details);
    }
    return td;
  }

  function comparisonSummary(models, comparison) {
    const rows = models.filter(row => row.comparison === comparison);
    const ready = rows.filter(row => (row.display_status || row.status) === "READY");
    const below = ready.filter(row => finite(row.fdr_q) && row.fdr_q < 0.05);
    return {ready: ready.length, below: below.length, total: rows.length};
  }

  function significantSegments(models, comparison) {
    return SEGMENTS.filter(segment => models.some(row => row.segment === segment && row.comparison === comparison &&
      (row.display_status || row.status) === "READY" && finite(row.fdr_q) && row.fdr_q < 0.05));
  }

  function joinSegments(items) {
    if (!items.length) return "none";
    if (items.length === 1) return items[0];
    if (items.length === 2) return `${items[0]} and ${items[1]}`;
    return `${items.slice(0, -1).join(", ")}, and ${items.at(-1)}`;
  }

  function plainLanguageTakeaway(host, ecology, environment) {
    const clauses = [];

    if (host.ready) {
      if (host.below === host.ready) {
        clauses.push("host identity was associated with genomic differences across all analyzable segments");
      } else if (host.below > 0) {
        clauses.push("host identity was associated with genomic differences in some analyzable segments");
      } else {
        clauses.push("host identity did not add information beyond time and geography");
      }
    } else {
      clauses.push("the contribution of host identity could not be evaluated");
    }

    if (ecology.ready) {
      if (ecology.below === ecology.ready) {
        clauses.push("seasonal ecology added information across all analyzable segments");
      } else if (ecology.below > 0) {
        clauses.push("seasonal ecology added information for some segments");
      } else {
        clauses.push("seasonal ecology did not add information beyond host identity");
      }
    } else {
      clauses.push("the contribution of seasonal ecology could not be evaluated");
    }

    if (environment.ready) {
      if (environment.below === environment.ready) {
        clauses.push("local weather added information across all analyzable segments");
      } else if (environment.below > 0) {
        clauses.push("local weather added information for some segments");
      } else {
        clauses.push("local weather did not add information beyond the other factors");
      }
    } else {
      clauses.push("the available data were insufficient to isolate an independent weather signal");
    }

    if (clauses.length === 1) {
      return `Overall, ${clauses[0]}.`;
    }

    if (clauses.length === 2) {
      return `Overall, ${clauses[0]}, and ${clauses[1]}.`;
    }

    return `Overall, ${clauses[0]}, ${clauses[1]}, and ${clauses[2]}.`;
  }

  function summaryBox(data, models) {
    const host = comparisonSummary(models, "host_vs_baseline");
    const ecology = comparisonSummary(models, "ecology_vs_host");
    const environment = comparisonSummary(models, "environment_vs_ecology");
    const hostSegments = significantSegments(models, "host_vs_baseline");
    const ecologySegments = significantSegments(models, "ecology_vs_host");
    const readiness = data.readiness || {};

    const box = make("section", "wgec-plain-summary");
    box.append(make("h4", "wgec-summary-title", "What this run suggests"));
    box.append(
      make(
        "p",
        "wgec-takeaway",
        plainLanguageTakeaway(host, ecology, environment)
      )
    );

    const finding = (label, text) => {
      const row = make("div", "wgec-summary-row");
      row.append(
        make("strong", "wgec-summary-label", label),
        make("span", "wgec-summary-text", text)
      );
      box.append(row);
    };

    if (host.ready) {
      if (host.below) {
        const segments = host.below === host.ready || !hostSegments.length
          ? ""
          : ` (${joinSegments(hostSegments)})`;
        finding(
          "Host identity",
          `Added explanatory value in ${host.below}/${host.ready} analyzable segments beyond time + geography${segments}.`
        );
      } else {
        finding(
          "Host identity",
          `No additional explanatory value in ${host.ready} analyzable segments beyond time + geography.`
        );
      }
    } else {
      finding("Host identity", "Not estimable in this run.");
    }

    if (ecology.ready) {
      if (ecology.below) {
        const segments = ecologySegments.length
          ? ` (${joinSegments(ecologySegments)})`
          : "";
        finding(
          "Seasonal ecology",
          `Added explanatory value in ${ecology.below}/${ecology.ready} analyzable segments beyond host${segments}.`
        );
      } else {
        finding(
          "Seasonal ecology",
          `No additional explanatory value in ${ecology.ready} analyzable segments after host was included.`
        );
      }
    } else {
      finding("Seasonal ecology", "Not estimable in this run.");
    }

    if (environment.ready) {
      const weatherSegments = significantSegments(models, "environment_vs_ecology");
      if (environment.below) {
        const segments = weatherSegments.length
          ? ` (${joinSegments(weatherSegments)})`
          : "";
        finding(
          "Local weather",
          `Added explanatory value in ${environment.below}/${environment.ready} analyzable segments beyond seasonal ecology${segments}.`
        );
      } else {
        finding(
          "Local weather",
          `No additional explanatory value in ${environment.ready} analyzable segments after seasonal ecology was included.`
        );
      }
    } else {
      const weatherSamples = readiness.samples_with_complete_environment_vector;
      const contexts = readiness.distinct_weather_contexts
        ?? readiness.distinct_environment_profiles;

      const detail = weatherSamples != null && contexts != null
        ? ` (${weatherSamples} samples; ${contexts} distinct weather settings).`
        : ".";

      finding(
        "Local weather",
        `Not independently estimable in this run${detail}`
      );
    }

    if (data.migration_context) {
      const migration = comparisonSummary(models,"migration_vs_ecology");
      const descriptive = models.filter(row=>row.comparison === "migration_vs_ecology" && row.display_status === "DESCRIPTIVE").length;
      const migrationSamples = readiness.samples_with_migration_context || 0;
      const migrationSettings = readiness.distinct_migration_contexts || 0;
      const minimumSettings = readiness.minimum_unique_samples ?? 8;
      let explanation;
      if (migration.ready) {
        explanation = `${migration.below}/${migration.ready} analyzable segments showed added explanatory value beyond host and seasonal ecology. Weather is assessed separately.`;
      } else if (descriptive) {
        explanation = `Descriptive added fit is available for ${descriptive} segments; p/q values are withheld. ${migrationSettings} distinct state–night settings. See segment diagnostics below.`;
      } else if (!migrationSamples) {
        explanation = "No samples have both a matched BirdCast night and a complete spring/fall season for their state and year. Concordance analysis is unavailable; see segment diagnostics below.";
      } else if (migrationSettings < minimumSettings) {
        explanation = `Migration data available for ${migrationSamples} samples across ${migrationSettings} distinct settings; concordance analysis withheld because the configured minimum is ${minimumSettings}.`;
      } else {
        explanation = `Migration data available for ${migrationSamples} samples across ${migrationSettings} distinct settings; no segment comparison meets all analysis requirements. See segment diagnostics below.`;
      }
      finding("Migration context", explanation);
      finding("Reading migration settings", "One setting is one state + matched night. Samples sharing it use the same BirdCast estimate. A complete spring/fall season for that state and year lets WINGS compare nightly activity and seasonal progress.");
    }

    box.append(
      make(
        "p",
        "wgec-summary-caveat",
        "Exploratory associations only; not evidence of transmission, infection source, reassortment, or causation."
      )
    );

    return box;
  }

  function migrationMap(explorer, data) {
    const section=make("section","wgec-migration");
    const style=make("style");
    style.textContent='.wgec-migration{margin:24px 0;padding:20px 0;border-top:1px solid #d8e2e2;border-bottom:1px solid #d8e2e2}.wgec-migration svg{width:100%;height:auto;display:block}.wgec-migration text{font:12px system-ui,sans-serif;fill:#53686d}.wgec-migration .wgec-migration-point{cursor:pointer;outline:none!important}.wgec-migration .wgec-migration-focus{opacity:0;pointer-events:none}.wgec-migration .wgec-migration-point:focus-visible .wgec-migration-focus{opacity:1}.wgec-migration select{max-width:100%;margin:8px 0;padding:7px}.wgec-migration-readout{min-height:3em;font-size:13px;color:#185c62}.wgec-migration details{font-size:12px}';
    style.textContent += '\n.wgec-migration{border-top:8px solid #111;border-radius:20px;padding:24px;background:#fff;color:#111}.wgec-migration h4{font-size:28px;color:#111}.wgec-migration .wm-context-header{background:#111;color:#fff;border-top:6px solid #ffc627;border-radius:16px;padding:22px;margin:20px 0}.wm-context-header strong{display:block;font-size:22px;margin:8px 0}.wm-context-kicker{color:#ffc627;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.wm-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.wm-metric{padding:24px;border-radius:18px;background:#111;color:white;border-top:6px solid #ffc627}.wm-metric:nth-child(2){background:#8c1d40}.wm-metric h5{color:#ffc627;font-size:18px;text-transform:uppercase;margin:0 0 12px}.wm-metric strong{font-size:34px;display:block}.wm-metric p{font-size:18px;line-height:1.5;color:#fff}.wm-track{height:12px;background:#dedede;border-radius:20px;position:relative;margin:16px 0}.wm-fill{display:block;height:100%;border-radius:20px;background:#ffc627}.wm-marker{position:absolute;top:-5px;width:5px;height:22px;background:#ffc627;transform:translateX(-50%)}.wm-scale{display:flex;justify-content:space-between;font-size:16px}.wm-context-list{display:grid;gap:10px;margin:22px 0}.wm-context-row{display:grid;grid-template-columns:minmax(170px,1fr) 1fr 1fr;gap:20px;align-items:center;width:100%;padding:18px;text-align:left;background:white;color:#111;border:1px solid #ddd;border-left:6px solid #747474;border-radius:12px;font:inherit;cursor:pointer}.wm-context-row[aria-pressed="true"]{border-left-color:#8c1d40;outline:3px solid #ffc627}.wm-context-row:focus-visible{outline:3px solid #ffc627}.wm-context-row .wm-fill{background:#747474}.wm-context-row[aria-pressed="true"] .wm-fill{background:#8c1d40}.wm-context-row .wm-marker{background:#8c1d40}.wgec-migration details{font-size:16px;margin-top:18px}.wgec-migration summary{font-weight:700;color:#8c1d40;cursor:pointer}.wgec-migration .wgec-migration-readout{font-size:16px;color:#333}.wm-hover{font-size:16px;color:#333;min-height:3em}@media(max-width:650px){.wm-metrics{grid-template-columns:1fr}.wm-context-row{grid-template-columns:1fr;gap:8px}.wgec-migration{padding:16px}}\n';
    section.append(style,make("h4","","Nightly migration context by state"),make("p","","Compare nightly activity and seasonal progress. Select a context below to highlight its linked samples."));
    const svgNode=(name,attrs={},text)=>{const node=document.createElementNS("http://www.w3.org/2000/svg",name);Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,String(v)));if(text!==undefined)node.textContent=text;return node;};
    const migrationModels=(data.models || []).filter(row=>row.comparison === "migration_vs_ecology");
    const hasMigrationFit = migrationModels.some(row => finite(row.delta_r2));
    if (hasMigrationFit) {
      section.append(make("h5","","Added fit by segment"),make("p","","Select a segment row to show the collections eligible for that comparison. Each change in R² compares the same pairs with and without migration context."));
      const fitChart=svgNode("svg",{viewBox:"0 0 900 255",role:"group","aria-label":"Migration added fit by segment"});
      const maximum=Math.max(.05,...migrationModels.map(row=>finite(row.delta_r2)?row.delta_r2:0));
      for(let i=0;i<SEGMENTS.length;i++){
        const segment=SEGMENTS[i],row=migrationModels.find(r=>r.segment === segment),yy=24+i*27,active=explorer.migrationConcordanceSegment === segment;
        const line=svgNode("g",{class:"wgec-migration-point",role:"button",tabindex:0,"aria-pressed":active,"aria-label":`${segment}: ${row && finite(row.delta_r2)?"added fit "+row.delta_r2.toFixed(3):friendlyStatus(row)}. Show eligible collections.`});
        line.append(svgNode("text",{x:30,y:yy+4},segment),svgNode("line",{x1:105,x2:600,y1:yy,y2:yy,stroke:"#e3e9e9"}),svgNode("circle",{class:"wgec-migration-focus",cx:84,cy:yy,r:6,fill:"none",stroke:"#bd811f","stroke-width":2}));
        if(row && finite(row.delta_r2)){
          const xx=105+Math.max(0,row.delta_r2)/maximum*495;
          line.append(svgNode("line",{x1:105,x2:xx,y1:yy,y2:yy,stroke:active?"#8c1d40":"#147d83","stroke-width":4}),svgNode("circle",{cx:xx,cy:yy,r:5,fill:active?"#8c1d40":"#747474"}),svgNode("text",{x:622,y:yy+4},`ΔR² ${signed(row.delta_r2)} · ${row.display_status === "DESCRIPTIVE"?"descriptive":`q ${qfmt(row.fdr_q)}`}`));
        }else line.append(svgNode("text",{x:622,y:yy+4},friendlyStatus(row)));
        line.append(svgNode("title",{},`${segment}: ${row?.diagnostic || "Comparison unavailable."}`));
        const choose=()=>{explorer.migrationConcordanceSegment=active?null:segment;explorer.concordanceController?.refresh();};
        line.addEventListener("click",choose);line.addEventListener("keydown",event=>{if(["Enter"," "].includes(event.key)){event.preventDefault();choose();}});fitChart.append(line);
      }
      section.append(fitChart);
    } else {
      const reasons = [...new Set(migrationModels.map(friendlyStatus))];
      const message = reasons.length === 1 ? reasons[0] : "Insufficient eligible data for the migration comparisons";
      section.append(make("p", "wgec-migration-unavailable", `Migration comparisons unavailable: ${message.charAt(0).toLowerCase() + message.slice(1)}.`));
      explorer.migrationConcordanceSegment = null;
    }
    const all=Array.isArray(data.migration_samples)?data.migration_samples:[];
    const model=migrationModels.find(row=>row.segment === explorer.migrationConcordanceSegment);
    const eligible=model && Array.isArray(model.eligible_sample_ids)?new Set(model.eligible_sample_ids):null;
    const samples=all.filter(row=>(!eligible || eligible.has(row.sample_id)) && (explorer.hostFilter === "ALL" || !explorer.hostFilter || row.host === explorer.hostFilter || row.sample_id === explorer.selectedSampleId));
    if(model)section.append(make("p","",`${model.segment}: ${model.n_samples || 0} eligible samples · ${model.n_migration_contexts || 0} distinct state–night contexts. ${model.diagnostic || ""} Select the same row again to restore all collections.`));
    const selected=all.find(row=>row.sample_id === explorer.selectedSampleId);
    const readout=make("p","wgec-migration-readout");readout.setAttribute("aria-live","polite");
    const describe=row=>row?.migration_available?`${row.sample_id} · matched night ${row.migration_night} · ${row.migration_state} · ${row.migration_season_label}. Activity percentile ${(100*row.migration_intensity_percentile).toFixed(1)}%; seasonal progress ${(100*row.migration_progress).toFixed(1)}%.` : row ? `${row.sample_id}: ${row.migration_reason || "Migration context unavailable."}` : "Select a point or collection to inspect its fixed migration context.";
    readout.textContent=describe(selected);
    const groups=new Map();
    for(const row of samples){if(!row.migration_available || !finite(row.migration_intensity_percentile) || !finite(row.migration_progress) || row.migration_progress<0 || row.migration_progress>1 || row.migration_intensity_percentile<0 || row.migration_intensity_percentile>1)continue;
      if(!groups.has(row.migration_context_key))groups.set(row.migration_context_key,[]);groups.get(row.migration_context_key).push(row);}
    const percent=value=>(100*value).toFixed(1);
    const bar=(value,marker=false)=>{
      const track=make("div","wm-track");track.setAttribute("aria-hidden","true");
      const fill=make("span",marker?"wm-marker":"wm-fill");
      fill.style[marker?"left":"width"]=`${100*value}%`;track.append(fill);return track;
    };
    const selectedGroup=[...groups.values()].find(members=>members.some(row=>row.sample_id===explorer.selectedSampleId));
    const heading=make("div","wm-context-header");
    heading.append(make("div","wm-context-kicker","Selected migration context"));
    if(selectedGroup){
      const row=selectedGroup.find(row=>row.sample_id===explorer.selectedSampleId);
      heading.append(make("strong","",`${row.migration_state} · ${row.migration_night} · ${row.migration_season_label}`),make("span","",`${row.sample_id} · ${selectedGroup.length} samples share this context`));
      section.append(heading);
      const metrics=make("div","wm-metrics");
      for(const [title,value,marker,description,left,right] of [
        ["Nightly activity",row.migration_intensity_percentile,true,`Busier than about ${Math.round(100*row.migration_intensity_percentile)}% of nights in this state's source season.`,"Quiet","Busy"],
        ["Seasonal progress",row.migration_progress,false,`About ${Math.round(100*row.migration_progress)}% of the season's total migration passage had accumulated by this night.`,"Season start","Season total"]]){
        const card=make("div","wm-metric"),scale=make("div","wm-scale");
        scale.append(make("span","",left),make("span","",right));
        card.append(make("h5","",title),make("strong","",marker?`${percent(value)} / 100 rank`:`${percent(value)}%`),bar(value,marker),scale,make("p","",description));metrics.append(card);
      }
      section.append(metrics);
    }else{heading.append(make("strong","",explorer.selectedSampleId?"Migration context unavailable for the selected sample":"Select a nightly context below"));section.append(heading);}
    if(groups.size){
      section.append(make("h5","","Compare nightly contexts"));
      const list=make("div","wm-context-list");
      for(const members of [...groups.values()].sort((a,b)=>String(a[0].migration_night).localeCompare(String(b[0].migration_night)))){
        const row=members[0],active=members.some(s=>s.sample_id===explorer.selectedSampleId);
        const button=make("button","wm-context-row");button.type="button";button.setAttribute("aria-pressed",String(active));
        button.append(make("strong","",`${row.migration_state} · ${row.migration_night} · ${members.length} samples`));
        const activity=make("div"),progress=make("div");
        activity.append(make("span","",`Activity rank: ${percent(row.migration_intensity_percentile)} / 100`),bar(row.migration_intensity_percentile,true));
        progress.append(make("span","",`Seasonal progress: ${percent(row.migration_progress)}%`),bar(row.migration_progress));
        button.append(activity,progress);button.addEventListener("click",()=>{if(!active)explorer.selectSample(row.sample_id);});list.append(button);
      }
      section.append(list);
    }
    const hoverReadout=make("p","wm-hover","Hover over or focus a point to inspect it. The selected context stays above.");
    if(groups.size){
      const svg=(name,attrs={},text)=>{const node=document.createElementNS("http://www.w3.org/2000/svg",name);Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,String(v)));if(text!==undefined)node.textContent=text;return node;};
      const chart=svg("svg",{viewBox:"0 0 900 300",role:"group","aria-label":"BirdCast activity percentile versus seasonal migration progress"});
      const x=value=>70+value*790,y=value=>235-value*190;
      for(const tick of [0,.25,.5,.75,1]){
        chart.append(svg("line",{x1:70,x2:860,y1:y(tick),y2:y(tick),stroke:"#e3e9e9","stroke-dasharray":"3 5"}),svg("text",{x:58,y:y(tick)+4,"text-anchor":"end"},`${100*tick}%`),svg("text",{x:x(tick),y:259,"text-anchor":"middle"},`${100*tick}%`));
      }
      chart.append(svg("text",{x:70,y:20},"Nightly activity percentile within the source season"),svg("text",{x:465,y:289,"text-anchor":"middle"},"Seasonal progress · cumulative share of complete-season passage"));
      for(const members of groups.values()){
        const row=members[0],active=members.some(s=>s.sample_id === explorer.selectedSampleId),cx=x(row.migration_progress),cy=y(row.migration_intensity_percentile),r=active?8:6;
        const point=svg("g",{class:"wgec-migration-point",tabindex:0,role:"button","aria-pressed":active,"aria-label":`${row.migration_state}, ${row.migration_night}, ${members.length} samples. Select linked collection.`,"data-migration-context":row.migration_context_key});
        point.append(svg("circle",{cx,cy,r,fill:active?"#8c1d40":"#747474",stroke:"white","stroke-width":2}),svg("circle",{class:"wgec-migration-focus",cx,cy,r:r+5,fill:"none",stroke:"#bd811f","stroke-width":2,"aria-hidden":"true"}),svg("title",{},`${row.migration_night} · ${row.migration_season_label} · ${members.length} samples · ${(100*row.migration_intensity_percentile).toFixed(1)}% activity percentile · ${(100*row.migration_progress).toFixed(1)}% seasonal progress`));
        if(members.length>1)point.append(svg("text",{x:cx+11,y:cy-8},String(members.length)));
        const inspect=()=>{const member=members.find(s=>s.sample_id === explorer.selectedSampleId)||row;hoverReadout.textContent=describe(member)+` ${members.length} samples share this nightly migration context.`;};
        const choose=()=>{const member=members.find(s=>s.sample_id === explorer.selectedSampleId)||row;if(member.sample_id !== explorer.selectedSampleId)explorer.selectSample(member.sample_id);else inspect();};
        point.addEventListener("pointerenter",inspect);point.addEventListener("focus",inspect);point.addEventListener("click",choose);point.addEventListener("keydown",event=>{if(["Enter"," "].includes(event.key)){event.preventDefault();choose();}});chart.append(point);
      }
      const comparison=make("details");
      comparison.append(make("summary","","Compare activity and seasonal progress"),make("p","wgec-migration-legend","Maroon: selected context. Gray: other contexts. Numbers show samples sharing a context."),chart,hoverReadout);
      section.append(comparison);
    }else section.append(make("p","","No completed-season migration contexts are available for this display. Matched nightly estimates may still be available in Migration Weave."));
    section.append(readout,make("p","",`${groups.size} distinct nightly migration contexts by state shown. Host filtering changes this display; model comparisons use the fixed run inputs. Date brushing in Migration Weave does not refit the models.`));
    const unavailable=samples.filter(row=>!row.migration_available);
    if(unavailable.length){const details=make("details"),list=make("ul");details.append(make("summary","",`${unavailable.length} collections without analytical migration context`));for(const row of unavailable)list.append(make("li","",`${row.sample_id} · ${row.collection_date}: ${row.migration_reason || "Unavailable"}`));details.append(list);section.append(details);}
    return section;
  }

  function render(explorer, panel) {
    panel.innerHTML = "";
    panel.classList.add("wgec-panel");
    const data = explorer?.payload?.genomic_ecological_concordance;

    const head = make("header", "wgec-head");
    const titleWrap = make("div");
    titleWrap.append(
      make("div", "wgec-kicker", "Research module"),
      make("h3", "wgec-title", "Genomic–Ecological Concordance"),
      make("p", "wgec-intro", "Tests whether host, seasonal ecology, migration context, and local weather explain genomic distance beyond time and geography.")
    );
    head.append(titleWrap, make("span", "wgec-badge", "Exploratory"));
    panel.append(head);

    if (!data || !Array.isArray(data.models)) {
      const empty = make("div", "wgec-empty");
      empty.append(
        make("strong", "", "Concordance analysis is not available for this run."),
        make("p", "", "WINGS will populate this module automatically when segment phylogenies and the required ecological inputs are available.")
      );
      panel.append(empty);
      return;
    }

    const models = data.models;
    panel.append(summaryBox(data, models));

    const readiness = data.readiness || {};
    const metrics = make("div", "wgec-metrics");
    const metric = (label, value, note) => {
      const card = make("div", "wgec-metric");
      card.append(make("span", "wgec-metric-label", label), make("strong", "wgec-metric-value", String(value)));
      if (note) card.append(make("small", "", note));
      return card;
    };
    metrics.append(
      metric("WINGS samples", readiness.total_samples ?? "—", "total in this run"),
      metric("Seasonal ecology data", readiness.samples_with_phenology ?? "—", "samples with eBird seasonal profiles"),
      metric("Samples with weather data", readiness.samples_with_complete_environment_vector ?? "—", "temperature, precipitation, and wind from ERA5"),
      metric("Distinct weather settings", readiness.distinct_weather_contexts ?? readiness.distinct_environment_profiles ?? "—", "unique location-and-time weather profiles"),
      metric("Configured minimum", readiness.minimum_unique_samples ?? "—", "samples per comparison; migration also requires this many distinct settings")
    );
    if(data.migration_context) metrics.append(
      metric("Samples with migration data", readiness.samples_with_migration_context ?? "—", "matched night and complete spring/fall season for the state and year"),
      metric("Distinct migration settings", readiness.distinct_migration_contexts ?? "—", "unique state + night combinations; samples sharing a night count once")
    );
    panel.append(metrics);

    if(data.migration_context) panel.append(migrationMap(explorer,data));



    const wrap = make("div", "wgec-table-wrap");
    const table = make("table", "wgec-table");
    const thead = make("thead");
    const hr = make("tr");
    ["Segment", "Host vs baseline", "Seasonal ecology vs host", "Environment vs ecology", "Migration vs seasonal ecology"].forEach(text => hr.append(make("th", "", text)));
    thead.append(hr);
    const tbody = make("tbody");
    for (const segment of SEGMENTS) {
      const row = make("tr");
      row.append(make("th", "wgec-segment", segment));
      for (const [family] of FAMILIES) {
        row.append(modelCell(models.find(item => item.segment === segment && item.comparison === family), family));
      }
      tbody.append(row);
    }
    table.append(thead, tbody);
    wrap.append(table);
    const method = make("details", "wgec-method");
    const summary = make("summary", "", "Methods and interpretation guardrails");
    const body = make("div", "wgec-method-body");

    const modelList = make("ul");
    [
      ["M0", "Spatiotemporal", "time + geography"],
      ["M1", "Host", "+ same host"],
      ["M2", "Seasonal ecology", "+ eBird annual-profile distance"],
      ["M3", "Environment", "+ standardized ERA5 weather distance"],
      ["M2 + migration", "Migration context", "+ normalized BirdCast context distance (separate addition to M2)"],
    ].forEach(([code, name, predictors]) => {
      modelList.append(make("li", "", `${code} — ${name}: ${predictors}`));
    });

    body.append(
      make("p", "", "Modeling approach: nested ordinary least-squares linear regression models relate segment-specific genomic distance to time, geography, host identity, seasonal ecology, migration context, and weather. Weather and migration are separate additions to the seasonal-ecology model. Added fit is measured by the increase in R² (ΔR²)."),
      make("p", "", "Models compared:"),
      modelList,
      make("p", "", "Outcome: segment-specific pairwise patristic distance among unambiguous WINGS sample tips."),
      make("p", "", `Seasonal ecology: ${data.seasonal_profile_metric || "eBird seasonal-profile distance."}`),
      make("p", "", `Weather: ${data.environmental_distance?.method || "standardized ERA5 environmental distance using temperature, precipitation, and wind."}`),
      ...(data.migration_context ? [make("p", "", `Migration: ${data.migration_context.method} ${data.migration_context.coverage} ${data.migration_context.inference} ${data.migration_context.window}`)] : []),
      make("p", "", `Inference: Because pairwise observations share samples, conventional OLS p-values are not used. Statistical evidence is assessed using ${data.permutation_test?.method || "sample-label permutation."} ${data.permutation_test?.multiple_testing || ""}`),
      make("p", "wgec-guardrail", "Pair rows share biological samples and are not independent observations. Unique-sample counts are therefore shown for every comparison. Concordance is not evidence of direct transmission, infection source, reassortment, or causality.")
    );
    const outputs = make("p", "wgec-outputs", `Detailed outputs: ${(data.detailed_outputs || []).join(" · ")}`);
    body.append(outputs);
    method.append(summary, body);
    const link = make("a", "wgec-statistics-link", "View detailed statistical comparisons ↗");
    link.href = "about:blank";
    link.target = "_blank";
    link.rel = "noopener";
    link.style.cssText = "display:inline-block;margin:20px 0;padding:14px 20px;background:#8c1d40;color:white;border-top:5px solid #ffc627;border-radius:12px;font-size:18px;font-weight:700;text-decoration:none";
    const notice = make("p", "wgec-statistics-notice");
    notice.setAttribute("role", "status");
    link.addEventListener("click", event => {
      event.preventDefault();
      const win = window.open("about:blank", "_blank");
      if (!win) { notice.textContent = "Allow this report to open a new tab, then select the link again."; return; }
      win.opener = null;
      const doc = win.document;
      doc.title = "WINGS · Detailed statistical comparisons";
      doc.documentElement.lang = "en";
      const meta = doc.createElement("meta");meta.name = "viewport";meta.content = "width=device-width, initial-scale=1";
      const style = doc.createElement("style");
      style.textContent = `*{box-sizing:border-box}body{margin:0;background:#f6f6f6;color:#111;font:18px/1.55 system-ui,sans-serif}main{max-width:1600px;margin:32px auto;padding:0 24px}header{background:#111;color:white;border-top:7px solid #ffc627;border-radius:18px;padding:28px}header p{color:#ffc627;font-weight:800;letter-spacing:.08em;margin:0}h1{font-size:32px;line-height:1.2;margin:12px 0}h2{font-size:23px}.definitions,.wgec-method{background:white;border:1px solid #ddd;border-radius:16px;padding:24px;margin:24px 0}.wgec-table-wrap{overflow:auto;background:white;border:1px solid #ddd;border-radius:16px;margin:24px 0}table{width:100%;min-width:1050px;border-collapse:collapse;font-size:16px}th,td{padding:20px;text-align:left;vertical-align:top;border-bottom:1px solid #ddd}thead th{background:#8c1d40;color:white}tbody th{color:#8c1d40}tbody tr:nth-child(even){background:#fafafa}td p{margin:8px 0}.wgec-n{display:block;color:#555;margin-top:8px}summary{cursor:pointer;color:#8c1d40;font-weight:700}details{margin-top:12px}a{color:#8c1d40}.wgec-guardrail{border-left:5px solid #ffc627;padding-left:16px}@media(max-width:650px){main{padding:0 12px;margin:12px auto}header{padding:20px}h1{font-size:26px}}`;
      style.textContent += `.wgec-result-cell .wgec-status,.wgec-result-cell .wgec-delta{display:block;margin:0 0 10px;line-height:1.4}.wgec-result-cell .wgec-statline,.wgec-result-cell .wgec-diagnostic{display:block;margin:0 0 10px;line-height:1.55}.wgec-result-cell .wgec-n{display:block;margin:10px 0;line-height:1.5}.wgec-technical{margin-top:14px}.wgec-technical>summary{margin-bottom:8px}.wgec-technical>span{display:block;line-height:1.55}`;
      doc.head.append(meta, style);
      const main = doc.createElement("main");
      const header = make("header");
      header.append(make("p", "", "WINGS · CONCORDANCE"), make("h1", "", "Detailed statistical comparisons"), make("div", "", "Results from the report open in the original tab."));
      const definitions = make("section", "definitions");
      definitions.append(make("h2", "", "Reading the results"));
      const list = make("ul");
      ["ΔR²: additional variation explained when predictors are added to the comparison model.", "p: permutation-based statistical evidence before adjustment for multiple comparisons.", "q: the adjusted value reported after correction for multiple comparisons.", "Sample and pair counts show the observations included. Pairs sharing samples are not independent.", "Unavailable results include the reason a comparison could not be estimated."].forEach(text => list.append(make("li", "", text)));
      definitions.append(list);
      for (const node of [header, definitions, wrap, method]) main.append(doc.importNode(node, true));
      main.querySelector(".wgec-method").open = true;
      doc.body.replaceChildren(main);
      notice.textContent = "Detailed comparisons opened in a new tab.";
    });
    panel.append(link, notice);
  }

  function mount(explorer, panel) {
    if (!panel) throw new Error("Concordance tab panel is required.");
    render(explorer, panel);
    return {VERSION, refresh: () => render(explorer, panel)};
  }

  globalThis.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE = {VERSION, mount};
})();
