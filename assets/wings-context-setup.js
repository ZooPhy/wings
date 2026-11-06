/* Source cards: checked means include; preparation never starts sequencing. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const origin = ['localhost','127.0.0.1'].includes(location.hostname) ? location.origin : 'http://127.0.0.1:8765';
  const sources = ['ecology','phenology','public_genotypes','ebird','outbreak'];
  const controls = {ecology:'contextEcology',phenology:'contextPhenology',public_genotypes:'contextGenotypes',ebird:'contextEbird',outbreak:'contextAphis'};
  let createSettings = () => ({});
  let prepared = null;
  let preparing = false;
  let records = {};
  function setCreateSettings(provider) {
    if (typeof provider !== 'function') throw new Error('Context run settings must be a function');
    createSettings = provider;
  }
  const options = () => ({
    selected_sources:sources.filter(name => $(controls[name]).checked),
    days:Number($('contextDays').value),network:$('contextNetwork').checked,
    phenology:$('contextPhenology').checked,phenology_year:Number($('contextYear').value),
    ebird_package:$('contextPackage').value.trim(),ebird_source:$('contextSource').value.trim(),
    all_species_confirmed:$('contextCoverage').checked,outbreak_file:$('contextOutbreak').value.trim(),
    global_genotypes:$('contextGlobal').checked,required:[]
  });
  async function input() {
    const file = $('metadataFile').files[0];
    if (!file) throw new Error('Select metadata.tsv first.');
    const metadata = await file.text();
    const settings = options();
    const bytes = new TextEncoder().encode(metadata+'\n'+JSON.stringify(settings)+'\n'+JSON.stringify(createSettings()));
    const hash = await crypto.subtle.digest('SHA-256',bytes);
    const signature = [...new Uint8Array(hash)].map(n=>n.toString(16).padStart(2,'0')).join('');
    return {file,metadata,settings,signature};
  }
  async function request(path,body) {
    const response = await fetch(origin+path,body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Context request failed');
    return data;
  }
  function openSettings(id,focusId) {
    $('contextAdvanced').open=true;
    $(id).open=true;
    const focus = focusId ? $(focusId) : $(id).querySelector('summary');
    focus.focus();focus.scrollIntoView({block:'nearest',behavior:'smooth'});
  }
  function countText(name,record) {
    const number = key => Number.isInteger(record[key]) && record[key]>=0;
    if(name==='ecology' && number('weather_ready') && number('migration_ready') && number('sample_count')) return `Weather ${record.weather_ready}/${record.sample_count} · Migration ${record.migration_ready}/${record.sample_count}`;
    if(name==='phenology' && number('ready_profiles') && number('sample_count')) return `${record.ready_profiles}/${record.sample_count} profiles available`;
    if(name==='public_genotypes' && number('included_runs')) return `${record.included_runs} public SRA records`;
    if(name==='outbreak' && record.status==='READY') {
      const date=/^\d{4}-\d{2}-\d{2}/.exec(record.retrieved_at || record.snapshot_date || '')?.[0];
      const basis=record.retrieved_at?'Retrieved':'Snapshot';
      const when=date?`${basis}: ${date}`:'Snapshot date unknown';
      const availability=record.refresh_status==='failed'?' · Refresh unavailable':record.refresh_status==='offline'?' · Offline':'';
      return when+availability;
    }
    return '';
  }
  function renderCards() {
    const labels={READY:'Ready',PARTIAL:'Partial coverage',NEEDS_IMPORT:'Import needed',NEEDS_ACCESS:'Access key needed',UNAVAILABLE:'Unavailable',PREPARING:'Preparing…',PLANNED:'Waiting',DISABLED:'Not selected'};
    for(const name of sources) {
      const selected=$(controls[name]).checked;
      const record=selected ? (records[name] || {}) : {status:'DISABLED'};
      const state=$('contextState-'+name);state.textContent=labels[record.status] || 'Not prepared';
      state.dataset.tone=record.status==='READY'?'ready':['PARTIAL','NEEDS_IMPORT','NEEDS_ACCESS','UNAVAILABLE'].includes(record.status)?'attention':'neutral';
      if(name==='outbreak' && record.status==='READY') {
        state.textContent=({download:'Downloaded',cache:'Cached snapshot',bundled:'Bundled snapshot',user:'Your CSV'})[record.source_mode] || 'Ready';
        if(record.source_mode==='cache' || record.source_mode==='bundled')state.dataset.tone='attention';
      }
      const count=$('contextCount-'+name);count.textContent=countText(name,record);count.hidden=!count.textContent;
      const action=$('contextAction-'+name);action.hidden=true;
      if(selected && !preparing && ['NEEDS_IMPORT','NEEDS_ACCESS'].includes(record.status)) {
        if(name==='ebird'){action.textContent='Import data';action.hidden=false;}
        if(name==='outbreak'){action.textContent='Supply snapshot';action.hidden=false;}
        if(name==='phenology'){action.textContent='Set up access';action.hidden=false;}
      }
      if(name==='outbreak' && selected && !preparing && record.status==='UNAVAILABLE') {
        action.textContent='Use your CSV';action.hidden=false;
      }
    }
  }
  function showStatus(data) {
    records={...records,...(data.providers || {})};
    renderCards();
    const status=$('contextStatus');
    if(data.status==='PREPARING') status.textContent='Preparing selected sources…';
    else if(data.status==='READY') {
      const chosen=sources.filter(name=>$(controls[name]).checked);
      const count=chosen.filter(name=>records[name]?.status==='READY').length;
      status.textContent=chosen.length ? (count===chosen.length ? 'Context saved. Continue to Analysis.' : 'Context saved with available data. Continue to Analysis.') : 'No context sources selected. Continue to Analysis.';
    } else if(data.status==='REVIEW') status.textContent='Checking selected sources…';
    else if(data.status==='STALE') status.textContent='Selection changed. Prepare context again.';
    else if(['FAILED','BLOCKED','INTERRUPTED'].includes(data.status)) status.textContent='Preparation could not finish. Check the runner log, then try again.';
  }
  function showRequest(request) {
    const groups=new Map();
    for(const w of request.windows || []) {
      const key=JSON.stringify([w.country,w.state]);
      if(!groups.has(key))groups.set(key,[]);
      groups.get(key).push({...w});
    }
    const windows=[];
    for(const list of groups.values()) {
      list.sort((a,b)=>a.date_from.localeCompare(b.date_from));let current;
      for(const w of list) {
        if(current && Date.parse(w.date_from)<=Date.parse(current.date_to)+86400000) {
          if(w.date_to>current.date_to)current.date_to=w.date_to;
        } else {current={...w};windows.push(current);}
      }
    }
    const target=$('contextRequest');target.replaceChildren();
    const text=document.createElement('p');text.textContent=windows.length?'Required regions and dates:':'Provide collection dates and regions to plan an eBird request.';target.append(text);
    const list=document.createElement('ul');
    for(const w of windows){const item=document.createElement('li');item.textContent=`${w.country} / ${w.state}: ${w.date_from} through ${w.date_to}`;list.append(item);}
    target.append(list);
  }
  async function review() {
    const value=await input();
    const plan=await request('/api/context/plan',{metadata:value.metadata,options:value.settings});
    if((await input()).signature!==value.signature)throw new Error('Inputs changed during preparation.');
    showRequest(plan.ebird_request || {});
    // A plan is not evidence of access or coverage. Only preparation sets final badges.
    records=Object.fromEntries(sources.map(name=>[name,{status:value.settings.selected_sources.includes(name)?'PLANNED':'DISABLED'}]));
    showStatus({status:'REVIEW'});
    return value;
  }
  function lockInputs() {
    const elements=[...$('contextSetup').querySelectorAll('input,button,select'),$('metadataFile')];
    const previous=elements.map(el=>[el,el.disabled]);
    for(const [el] of previous)el.disabled=true;
    return ()=>{for(const [el,disabled] of previous)el.disabled=disabled;};
  }
  async function prepareOnly() {
    if(preparing)throw new Error('Context preparation is already running.');
    if(window.WINGS_CONTEXT_PICKER?.isBusy())throw new Error('Finish choosing a folder first.');
    preparing=true;prepared=null;
    const unlock=lockInputs();
    $('contextPrepare').textContent='Preparing…';
    let progress;
    try {
      const value=await review();
      showStatus({status:'PREPARING'});
      const run=await request('/api/runs',{...createSettings(),name:'Context preparation',options:{context_setup:true}});
      const upload=await fetch(`${origin}/api/runs/${encodeURIComponent(run.run_id)}/files?kind=metadata&filename=metadata.tsv`,{method:'PUT',body:value.file});
      if(!upload.ok)throw new Error(await upload.text());
      progress=await request(`/api/runs/${encodeURIComponent(run.run_id)}/context`,{options:value.settings});
      while(progress.status==='PREPARING') {
        showStatus(progress);
        await new Promise(resolve=>setTimeout(resolve,1000));
        progress=await request(`/api/runs/${encodeURIComponent(run.run_id)}/context`);
      }
      if(progress.status!=='READY')throw new Error('Context preparation did not finish.');
      if((await input()).signature!==value.signature)throw new Error('Inputs changed during preparation.');
      prepared={runId:run.run_id,signature:value.signature};
      showStatus(progress);
    } catch(error) {
      showStatus({...(progress || {}),status:'FAILED'});
      throw error;
    } finally {
      preparing=false;unlock();renderCards();
      $('contextPrepare').textContent='Prepare context';
    }
  }
  async function readyForRun() {
    const value=await input();
    if(!prepared || prepared.signature!==value.signature)throw new Error('In Metadata, prepare context for the current selection before launching.');
    return prepared;
  }
  async function attach(runId) {
    const ready=await readyForRun();const value=await input();
    const result=await request(`/api/runs/${encodeURIComponent(runId)}/context`,{reuse_run_id:ready.runId,options:value.settings});
    if(result.status!=='READY')throw new Error('Prepared context could not be attached to this run.');
  }
  function report(error) {
    console.error('WINGS context:',error);
    $('contextStatus').textContent=['Select metadata.tsv first.','Finish choosing a folder first.'].includes(error.message) ? error.message : 'Preparation could not finish. Check the runner log, then try again.';
  }
  function invalidate() {
    if(preparing)return;
    prepared=null;records={};showStatus({status:'STALE'});
  }
  $('contextSetup').addEventListener('input',invalidate);
  $('metadataFile').addEventListener('change',()=>{invalidate();$('contextRequest').textContent='Prepare context to determine the required regions and dates.';});
  $('contextAction-ebird').addEventListener('click',()=>openSettings('contextEbirdImport','contextSource'));
  $('contextAction-phenology').addEventListener('click',()=>openSettings('contextPhenologyAccess'));
  $('contextAction-outbreak').addEventListener('click',()=>openSettings('contextAphisImport','contextOutbreak'));
  $('contextPrepare').addEventListener('click',()=>prepareOnly().catch(report));
  renderCards();
  window.WINGS_CONTEXT_SETUP={readyForRun,attach,review,prepareOnly,showStatus,setCreateSettings};
})();
