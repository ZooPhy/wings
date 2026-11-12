/* Browser-only metadata preparation. File contents never leave this wizard. */
(() => {
  "use strict";
  const Core=globalThis.WINGS_METADATA;
  const launch=document.getElementById("openMetadataWizard");
  if(!Core || !launch)return;
  const referenceURL=new URL("wings-metadata-reference.json?v=1",document.currentScript.src);
  const STEPS=["Import","Match samples","Hosts","Collection details","Review & export"];
  const LABELS={sample_id:"Sample ID",host:"Host name or WINGS code",specimen_type:"Specimen type",collection_date:"Collection date",state:"State / province / territory",country:"Country",latitude:"Latitude",longitude:"Longitude"};
  const PAGE_SIZE=50;
  const model={step:0,page:0,rows:[],fields:[...Core.FIELDS],parsed:null,pending:null,revision:0,audit:[],dateFormat:"ask",acknowledged:false};
  let dialog,reference,index,referencePromise;
  const make=(tag,cls,value)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(value!==undefined)node.textContent=value;return node;};
  const button=(label,action,cls="btn btn-secondary")=>{const node=make("button",cls,label);node.type="button";node.dataset.action=action;return node;};
  const reads=()=>[...(document.getElementById("readsFiles")?.files || [])].map(file=>file.name);
  const validation=()=>Core.validate(model.rows,reads(),index);
  const get=id=>dialog.querySelector("#"+id);
  function changed(){model.revision++;model.pending=null;model.acknowledged=false;}
  function message(value){get("mwMessage").textContent=value;}
  function download(name,content,type="text/tab-separated-values;charset=utf-8") {
    const url=URL.createObjectURL(new Blob([content],{type}));
    const link=document.createElement("a");link.href=url;link.download=name;link.hidden=true;document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function auditDownload(items=model.audit) {
    download("metadata-changes.tsv",Core.toTSV(["sample_id","row","field","before","after","action"],items));
  }
  function applyParsed(parsed){model.parsed=parsed;model.pending=null;model.step=0;model.page=0;render();}
  function applyMapping() {
    if(!model.parsed)throw new Error("Load a table first, or start from the selected FASTQs.");
    const mapping=[...get("mwMapping").querySelectorAll("select")].map((select,i)=>select.value==="__keep__"?model.parsed.headers[i]:select.value);
    const mapped=Core.mapTable(model.parsed,mapping);model.rows=mapped.rows;model.fields=mapped.fields;model.audit=[];
    mapping.forEach((field,i)=>{if(field!==model.parsed.headers[i])model.audit.push({sample_id:"",row:"",field:model.parsed.headers[i],before:model.parsed.headers[i],after:field,action:"column mapping"});});
    changed();model.step=1;model.page=0;render();
  }
  function starter(fromReads) {
    const files=reads();if(fromReads && !files.length)throw new Error("Select sequencing files in the run form first.");
    model.fields=[...Core.FIELDS];model.rows=(fromReads?files:[""]).map(filename=>Object.fromEntries(Core.FIELDS.map(field=>[field,field==="sample_id"?Core.stripFastq(filename):""])));
    model.parsed=null;model.audit=[];changed();model.step=1;model.page=0;render();
  }
  function mount() {
    dialog=make("dialog","wings-metadata-wizard");dialog.id="metadataWizard";dialog.setAttribute("aria-labelledby","mwTitle");
    dialog.innerHTML=`<header class="mw-heading"><div><span class="mw-kicker">WINGS / METADATA</span><h2 id="mwTitle">Create or fix metadata</h2></div><button type="button" class="mw-close" data-action="close" aria-label="Close metadata wizard">×</button></header>
      <nav class="mw-steps" aria-label="Metadata preparation steps"></nav>
      <div class="mw-content"><p class="mw-privacy">Preparation stays in this browser. The wizard uses FASTQ filenames and does not read sequencing contents.</p><p id="mwMessage" class="mw-message" role="status" aria-live="polite"></p><div id="mwBody"></div><div id="mwProposals"></div><div id="mwIssues"></div></div>
      <footer class="mw-footer"><button type="button" class="btn btn-secondary" data-action="back">Back</button><span id="mwSummary" role="status"></span><button type="button" class="btn btn-primary" data-action="next">Next</button><button type="button" class="btn btn-secondary" data-action="download">Download TSV</button><button type="button" class="btn btn-primary" data-action="use">Use this metadata</button></footer>`;
    document.body.append(dialog);
    dialog.addEventListener("click",event=>{
      const target=event.target.closest("[data-action]");if(!target)return;
      event.preventDefault();Promise.resolve(act(target.dataset.action,target)).catch(error=>message(error.message));
    });
    dialog.addEventListener("change",event=>{
      const target=event.target;
      if(target.id==="mwImport"){
        const file=target.files[0];if(!file)return;
        if(file.size>10*1024*1024){message("The wizard accepts metadata files up to 10 MB.");return;}
        file.text().then(value=>applyParsed(Core.parseTable(value))).catch(error=>message(error.message));return;
      }
      if(target.id==="mwDateFormat"){model.dateFormat=target.value;model.pending=null;get("mwProposals").replaceChildren();return;}
      if(target.id==="mwAcknowledge"){model.acknowledged=target.checked;updateSummary();return;}
      if(target.dataset.field!==undefined) {
        const rowIndex=Number(target.dataset.row),field=target.dataset.field,row=model.rows[rowIndex],before=row[field] || "";
        if(before!==target.value){row[field]=target.value;model.audit.push({sample_id:row.sample_id,row:rowIndex+1,field,before,after:target.value,action:"manual edit"});changed();}
        if(field==="host")target.parentElement.querySelector("small").textContent=Core.hostMatch(row.host,index)?.name || "Not recognized / not recorded";
        get("mwProposals").replaceChildren();renderIssues();updateSummary();
      }
    });
    const lists=[['mwCountryList',reference.countries.map(country=>[country.alpha3,country.name])],['mwRegionList',reference.regions.map(region=>[region.name,`${region.code} · ${region.country}`])]];
    for(const [id,values] of lists){const list=make("datalist");list.id=id;for(const [value,label] of values){const option=make("option");option.value=value;option.label=label;list.append(option);}dialog.append(list);}
    const hostNames=make("datalist");hostNames.id="mwHostNames";const seen=new Set();
    for(const host of reference.hosts){for(const value of [host.code,host.name]){if(seen.has(value))continue;seen.add(value);const option=make("option");option.value=value;option.label=`${host.code} · ${host.name}`;hostNames.append(option);}}
    dialog.append(hostNames);
  }
  function renderImport(body) {
    body.append(make("h3","","Import a table or start a new one"));
    const actions=make("div","mw-actions"),input=make("input");input.type="file";input.id="mwImport";input.accept=".csv,.tsv,text/csv,text/tab-separated-values,text/plain";input.setAttribute("aria-label","Import metadata CSV or TSV");
    const fromReads=button("Start from selected FASTQs","starter");fromReads.disabled=!reads().length;
    actions.append(input,fromReads,button("Start blank","blank"));body.append(actions);
    const label=make("label","mw-field-label","Or paste a table copied from a spreadsheet");label.htmlFor="mwPaste";
    const paste=make("textarea");paste.id="mwPaste";paste.rows=4;paste.placeholder="Sample ID\tBird\tCollection date\tState\tCountry";
    body.append(label,paste,button("Load pasted table","paste"));
    if(model.rows.length)body.append(make("p","mw-note",`${model.rows.length} draft rows are retained. Applying another import replaces the draft.`));
    if(!model.parsed)return;
    body.append(make("h3","",`Map ${model.parsed.headers.length} columns · ${model.parsed.rows.length} sample rows`));
    body.append(make("p","mw-note","Map known columns to WINGS fields. Additional columns are retained. If two columns map to one field, keep one as an extra column."));
    const mapping=make("div","mw-mapping");mapping.id="mwMapping";
    model.parsed.headers.forEach(header=>{
      const line=make("label","mw-map-row");line.append(make("span","",header));const select=make("select");select.setAttribute("aria-label","Output field for "+header);
      for(const field of Core.FIELDS){const option=make("option","",LABELS[field]+" ("+field+")");option.value=field;select.append(option);}
      const extra=make("option","","Keep original column: "+header);extra.value="__keep__";select.append(extra);
      const suggested=Core.suggestHeader(header);select.value=Core.FIELDS.includes(suggested)?suggested:"__keep__";line.append(select);mapping.append(line);
    });
    body.append(mapping);
    if(model.parsed.warnings.length)body.append(make("p","mw-note",model.parsed.warnings.join(" ")));
    body.append(button("Apply column mapping","map","btn btn-primary"));
  }
  function tableShell(headers) {
    const shell=make("div","mw-table-scroll"),table=make("table","mw-table"),head=make("thead"),row=make("tr"),body=make("tbody");
    for(const header of headers){const cell=make("th","",header);cell.scope="col";row.append(cell);}head.append(row);table.append(head,body);shell.append(table);return {shell,body};
  }
  function editableCell(rowIndex,field,readonly=false) {
    const cell=make("td");if(readonly){cell.append(make("strong","",model.rows[rowIndex][field] || "—"));return cell;}
    const input=make("input");input.type="text";input.value=model.rows[rowIndex][field] || "";input.dataset.row=String(rowIndex);input.dataset.field=field;input.setAttribute("aria-label",`${LABELS[field] || field}, row ${rowIndex+1}`);
    if(field==="host")input.setAttribute("list","mwHostNames");
    if(field==="state")input.setAttribute("list","mwRegionList");
    if(field==="country")input.setAttribute("list","mwCountryList");
    if(field==="sample_id")input.setAttribute("list","mwSampleList");
    if(field==="latitude" || field==="longitude")input.inputMode="decimal";
    if(field==="collection_date")input.placeholder="YYYY-MM-DD";
    cell.append(input);
    if(field==="host")cell.append(make("small","",Core.hostMatch(model.rows[rowIndex].host,index)?.name || "Not recognized / not recorded"));
    return cell;
  }
  function renderEditor(body) {
    const titles={1:"Confirm sample IDs and file matches",2:"Normalize bird names and host codes",3:"Normalize collection details"};
    body.append(make("h3","",titles[model.step]));
    const actions=make("div","mw-actions");
    if(model.step===1){actions.append(button("Review ID whitespace fixes","normalize"),button("Add missing FASTQ rows","missing"),button("Add sample","add"));body.append(make("p","mw-note","IDs must match FASTQ filenames exactly after removing .fastq.gz, .fq.gz, .fastq, or .fq. Suggested matches require your confirmation."));}
    if(model.step===2){actions.append(button("Review host standardization","normalize"));body.append(make("p","mw-note","Enter a common name or an accepted WINGS host code. Existing accepted aliases are preserved; a name is converted to a recognized code only after review."));}
    if(model.step===3){
      const label=make("label","mw-date-format","Source date format "),select=make("select");select.id="mwDateFormat";
      for(const [value,name] of [["ask","Ask for ambiguous dates"],["DMY","Day / month / year"],["MDY","Month / day / year"]]){const option=make("option","",name);option.value=value;select.append(option);}select.value=model.dateFormat;label.append(select);
      actions.append(label,button("Review collection standardization","normalize"));
      body.append(make("p","mw-note","Countries use ISO three-letter codes; US states and Canadian provinces/territories use full names. Other regions retain their text. Coordinates are validated; locations are not geocoded or filled with guessed coordinates."));
    }
    body.append(actions);
    const fields=model.step===1?["sample_id"]:model.step===2?["sample_id","host"]:["sample_id","specimen_type","collection_date","state","country","latitude","longitude"];
    const headers=fields.map(field=>LABELS[field]);if(model.step===1)headers.push("FASTQ match","Action");
    const table=tableShell(headers),readIDs=new Set(reads().map(Core.stripFastq));
    const start=model.page*PAGE_SIZE,end=Math.min(start+PAGE_SIZE,model.rows.length);
    for(let i=start;i<end;i++){
      const tr=make("tr");for(const field of fields)tr.append(editableCell(i,field,field==="sample_id" && model.step!==1));
      if(model.step===1){
        const match=make("td");match.append(make("span",readIDs.has(model.rows[i].sample_id)?"mw-match":"mw-missing",readIDs.has(model.rows[i].sample_id)?"Exact match":reads().length?"No exact match":"FASTQ matching pending"));
        const suggestions=Core.suggestIds(model.rows[i].sample_id,reads(),model.rows[i].barcode);
        for(const suggested of suggestions.slice(0,5)){if(suggested===model.rows[i].sample_id)continue;const use=button("Use "+suggested,"suggest","mw-link");use.dataset.row=String(i);use.dataset.value=suggested;match.append(use);}
        if(suggestions.length>5)match.append(make("small","",`${suggestions.length} possible matches; choose the correct ID.`));
        const action=make("td"),remove=button("Remove row","remove","mw-link");remove.dataset.row=String(i);action.append(remove);tr.append(match,action);
      }
      table.body.append(tr);
    }
    body.append(table.shell);renderPager(body);
  }
  function renderPager(body) {
    const pages=Math.max(1,Math.ceil(model.rows.length/PAGE_SIZE)),pager=make("div","mw-pager");
    const previous=button("Previous rows","previousRows"),next=button("Next rows","nextRows");previous.disabled=model.page===0;next.disabled=model.page+1>=pages;
    pager.append(previous,make("span","",model.rows.length?`Rows ${model.page*PAGE_SIZE+1}–${Math.min((model.page+1)*PAGE_SIZE,model.rows.length)} of ${model.rows.length}`:"No sample rows"),next);body.append(pager);
  }
  function renderReview(body) {
    body.append(make("h3","","Review the WINGS metadata file"),make("p","mw-note","Only sample_id is required by the metadata schema. Dates and coordinates must be valid when supplied. Missing collection details and unrecognized values remain visible as warnings."));
    const result=validation(),cards=make("div","mw-review-cards");
    for(const [label,value] of [["Sample rows",model.rows.length],["Blocking errors",result.errors.length],["Warnings",result.warnings.length],["Collection-complete rows",`${result.complete} / ${result.total}`]]){const card=make("div");card.append(make("span","",label),make("strong","",value));cards.append(card);}body.append(cards);
    const table=tableShell(model.fields.map(field=>LABELS[field] || field));
    for(const row of model.rows.slice(model.page*PAGE_SIZE,(model.page+1)*PAGE_SIZE)){const tr=make("tr");for(const field of model.fields)tr.append(make("td","",row[field] || "—"));table.body.append(tr);}body.append(table.shell);renderPager(body);
    if(result.warnings.length){const label=make("label","mw-ack"),input=make("input");input.type="checkbox";input.id="mwAcknowledge";input.checked=model.acknowledged;label.append(input,make("span","","I reviewed the warnings and any unresolved values."));body.append(label);}
    body.append(button("Download change log","audit"),button("Download validation report","validation"));
  }
  function renderProposals() {
    const area=get("mwProposals");area.replaceChildren();if(!model.pending)return;
    area.append(make("h3","",`${model.pending.changes.length} proposed changes`));
    if(!model.pending.changes.length){area.append(make("p","mw-note","No recognized values need standardization in this step."));return;}
    const table=tableShell(["Sample row","Field","Original","Proposed"]);
    for(const change of model.pending.changes.slice(0,100)){const row=make("tr");for(const value of [change.row,LABELS[change.field] || change.field,change.before || "—",change.after || "—"])row.append(make("td","",value));table.body.append(row);}area.append(table.shell);
    if(model.pending.changes.length>100)area.append(make("p","mw-note",`Showing the first 100 of ${model.pending.changes.length} changes. Download the proposed change log to inspect every change before applying.`));
    area.append(button("Download proposed changes","proposedAudit"),button("Apply proposed changes","apply","btn btn-primary"));
  }
  function renderIssues() {
    const area=get("mwIssues");area.replaceChildren();if(!model.rows.length)return;
    const result=validation();
    for(const [title,issues] of [["Errors to resolve",result.errors],["Warnings to review",result.warnings]]) {
      if(!issues.length)continue;
      const details=make("details","mw-issue-list"),summary=make("summary","",`${title} (${issues.length})`);details.open=title.startsWith("Errors");details.append(summary);const list=make("ul");
      for(const issue of issues.slice(0,100)){const item=make("li");item.append(make("span","",`${issue.row?"Row "+issue.row+" · ":""}${LABELS[issue.field] || issue.field}: ${issue.message}`));if(issue.row){const edit=button("Edit","editIssue","mw-link");edit.dataset.row=String(issue.row-1);edit.dataset.field=issue.field;item.append(edit);}list.append(item);}details.append(list);
      if(issues.length>100)details.append(make("p","mw-note",`Showing 100 of ${issues.length}. The validation report contains every issue.`));area.append(details);
    }
  }
  function updateSummary() {
    const result=validation(),ready=model.rows.length && !result.errors.length && (!result.warnings.length || model.acknowledged);
    get("mwSummary").textContent=`${model.rows.length} rows · ${result.errors.length} errors · ${result.warnings.length} warnings`;
    for(const action of ["download","use"]){const node=dialog.querySelector(`[data-action="${action}"]`);node.hidden=model.step!==4;node.disabled=!ready || (action==="use" && !result.exactMatch);}
    const next=dialog.querySelector('[data-action="next"]');next.hidden=model.step===4;next.disabled=!model.rows.length && model.step===0;
    dialog.querySelector('[data-action="back"]').disabled=model.step===0;
    if(model.step===4 && !reads().length)message("You can download valid metadata now. Select FASTQs in the run form to enable Use this metadata.");
  }
  function render() {
    message("");const tabs=dialog.querySelector(".mw-steps");tabs.replaceChildren();
    STEPS.forEach((label,i)=>{const tab=button(`${i+1}  ${label}`,"step","mw-step");tab.dataset.step=String(i);tab.disabled=i>0 && !model.rows.length;if(i===model.step)tab.setAttribute("aria-current","step");tabs.append(tab);});
    get("mwSampleList")?.remove();const sampleList=make("datalist");sampleList.id="mwSampleList";
    for(const filename of reads()){const option=make("option");option.value=Core.stripFastq(filename);sampleList.append(option);}dialog.append(sampleList);
    const body=get("mwBody");body.replaceChildren();
    if(model.step===0)renderImport(body);else if(model.step===4)renderReview(body);else renderEditor(body);
    renderProposals();renderIssues();updateSummary();
  }
  function logIssueReport() {
    const result=validation();download("metadata-validation.tsv",Core.toTSV(["severity","row","field","message"],[...result.errors.map(issue=>({...issue,severity:"ERROR"})),...result.warnings.map(issue=>({...issue,severity:"WARNING"}))]));
  }
  async function act(action,target) {
    if(action==="close"){dialog.close();return;}
    if(action==="map"){applyMapping();return;}
    if(action==="paste"){applyParsed(Core.parseTable(get("mwPaste").value));return;}
    if(action==="starter" || action==="blank"){starter(action==="starter");return;}
    if(action==="audit"){auditDownload();return;}
    if(action==="validation"){logIssueReport();return;}
    if(action==="proposedAudit"){auditDownload(model.pending?.changes || []);return;}
    if(action==="normalize"){
      const phase=model.step===1?"ids":model.step===2?"hosts":"collection";
      model.pending={...Core.normalizeRows(model.rows,index,phase,{dateFormat:model.dateFormat}),revision:model.revision};renderProposals();get("mwProposals").scrollIntoView({block:"nearest"});return;
    }
    if(action==="apply"){
      if(!model.pending || model.pending.revision!==model.revision)throw new Error("Review the proposed changes again after editing the table.");
      const pending=model.pending;model.rows=pending.rows;
      model.audit.push(...pending.changes.map(change=>({...change,sample_id:model.rows[change.row-1].sample_id,action:"standardization"})));changed();render();message(`Applied ${pending.changes.length} reviewed changes.`);return;
    }
    if(action==="download" || action==="use"){
      const result=validation();if(result.errors.length || (result.warnings.length && !model.acknowledged))throw new Error("Resolve errors and acknowledge remaining warnings before exporting.");
      const output=Core.toTSV(model.fields,model.rows);Core.inspectIds(output);
      if(action==="download"){download("metadata.tsv",output);return;}
      if(!result.exactMatch)throw new Error("Select FASTQs and confirm an exact match for every sample ID first.");
      try {
        const transfer=new DataTransfer();transfer.items.add(new File([output],"metadata.tsv",{type:"text/tab-separated-values"}));
        const input=document.getElementById("metadataFile");input.files=transfer.files;input.dispatchEvent(new Event("change",{bubbles:true}));
      } catch {throw new Error("This browser cannot select the generated file automatically. Download TSV, then choose metadata.tsv in the run form.");}
      dialog.close();document.getElementById("metadataSummary")?.scrollIntoView({block:"nearest"});return;
    }
    if(action==="suggest"){
      const row=model.rows[Number(target.dataset.row)],before=row.sample_id;row.sample_id=target.dataset.value;
      model.audit.push({sample_id:row.sample_id,row:Number(target.dataset.row)+1,field:"sample_id",before,after:row.sample_id,action:"confirmed filename match"});changed();
    } else if(action==="remove"){
      const i=Number(target.dataset.row),row=model.rows[i];model.audit.push({sample_id:row.sample_id,row:i+1,field:"row",before:JSON.stringify(row),after:"",action:"removed row"});model.rows.splice(i,1);changed();
    } else if(action==="add" || action==="missing"){
      if(action==="missing" && !reads().length){message("Select FASTQ files in the Sequences step of the run form first, then reopen the wizard to add their metadata rows.");return;}
      const ids=[...new Set(action==="add"?[""]:validation().missingReads)];
      if(!ids.length){message("No rows added: every selected FASTQ already has a metadata row. Review any ID errors shown below.");return;}
      const first=model.rows.length;
      for(const id of ids){
        const row=Object.fromEntries(model.fields.map(field=>[field,field==="sample_id"?id:""]));model.rows.push(row);
        model.audit.push({sample_id:id,row:model.rows.length,field:"row",before:"",after:JSON.stringify(row),action:action==="missing"?"added missing FASTQ row":"added sample row"});
      }
      changed();model.step=1;model.page=Math.floor(first/PAGE_SIZE);render();
      const input=dialog.querySelector(`input[data-row="${first}"][data-field="sample_id"]`);
      input?.focus();input?.scrollIntoView({block:"nearest"});
      message(action==="missing"?`Added ${ids.length} missing FASTQ metadata ${ids.length===1?"row":"rows"}. Showing the first added row; complete its host and collection details in the next steps.`:"Added a sample row. Enter its sample ID.");return;
    } else if(action==="editIssue"){
      const field=target.dataset.field;model.step=field==="sample_id"?1:field==="host"?2:3;model.page=Math.floor(Number(target.dataset.row)/PAGE_SIZE);render();
      dialog.querySelector(`[data-row="${target.dataset.row}"][data-field="${field==="coordinates"?"latitude":field}"]`)?.focus();return;
    } else if(action==="step" || action==="next" || action==="back"){
      model.step=action==="step"?Number(target.dataset.step):Math.max(0,Math.min(4,model.step+(action==="next"?1:-1)));model.page=0;model.pending=null;
    } else if(action==="previousRows")model.page=Math.max(0,model.page-1);
    else if(action==="nextRows")model.page++;
    model.page=Math.min(model.page,Math.max(0,Math.ceil(model.rows.length/PAGE_SIZE)-1));render();
  }
  async function open() {
    launch.disabled=true;const status=document.getElementById("metadataWizardStatus");if(status)status.textContent="Loading metadata reference…";
    try {
      if(!referencePromise)referencePromise=fetch(referenceURL,{cache:"no-cache"}).then(response=>{if(!response.ok)throw new Error("Could not load the metadata reference.");return response.json();}).catch(error=>{referencePromise=null;throw error;});
      reference=await referencePromise;
      if(reference.schema!=="wings.metadata-reference.v1")throw new Error("Reload the page to load the current metadata wizard.");
      index=Core.buildIndex(reference);if(!dialog)mount();
      if(!model.rows.length && !model.parsed){const selected=document.getElementById("metadataFile")?.files[0];if(selected)model.parsed=Core.parseTable(await selected.text(),"\t");}
      render();dialog.showModal();if(status)status.textContent="";
    } catch(error){if(status)status.textContent=error.message+" The existing metadata upload remains available.";}
    finally {launch.disabled=false;}
  }
  launch.addEventListener("click",open);
  globalThis.WINGS_METADATA_WIZARD={open};
})();
