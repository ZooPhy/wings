/* Source cards: checked means include; preparation never starts sequencing. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const origin = ['localhost','127.0.0.1'].includes(location.hostname) ? location.origin : 'http://127.0.0.1:8765';
  const sources = ['ecology','phenology','public_genotypes','ebird','outbreak'];
  const controls = {ecology:'contextEcology',phenology:'contextPhenology',public_genotypes:'contextGenotypes',ebird:'contextEbird',outbreak:'contextAphis'};
  let createSettings = () => ({});
  let validateMetadata = async () => {};
  function setMetadataValidation(check) { validateMetadata = check; }
  function unavailableSources() { return sources.filter(name => $(controls[name]).checked && records[name]?.status !== 'READY'); }
  function isReady() { return Boolean(prepared && !preparing && (!unavailableSources().length || $('contextAcceptUnavailable')?.checked)); }
  function notifyReadiness() {
    const row = $('contextUnavailableReview'), message = $('contextUnavailableMessage');
    const missing = unavailableSources();
    if (row) row.hidden = !prepared || preparing || !missing.length;
    if (message && missing.length) {
      const names={ecology:'weather and migration',phenology:'seasonal bird patterns',public_genotypes:'public genotypes',ebird:'eBird observations',outbreak:'APHIS detections'};
      message.textContent = 'Unavailable or incomplete: ' + missing.map(name=>names[name]).join(', ') + '. I reviewed the source messages and want to continue with available data.';
    }
    if (typeof document.dispatchEvent === 'function') document.dispatchEvent(new Event('wings-context-change'));
  }
  function clearAcknowledgment() { if ($('contextAcceptUnavailable')) $('contextAcceptUnavailable').checked = false; }
  let prepared = null;
  let preparing = false;
  let connectionMessage = '';
  const recoveryKey = 'wings-context-preparation-v1';
  // Save only the run reference and setup options, never metadata or credentials.
  function remember(value) {
    try {
      if(value)localStorage.setItem(recoveryKey,JSON.stringify(value));
      else localStorage.removeItem(recoveryKey);
    } catch(_) { /* Polling still works when browser storage is unavailable. */ }
  }
  function recalled() {
    try {
      const value=JSON.parse(localStorage.getItem(recoveryKey));
      if(value && typeof value.runId==='string' && /^[A-Za-z0-9_-]+$/.test(value.runId) &&
         typeof value.signature==='string' && /^[a-f0-9]{64}$/.test(value.signature) &&
         value.settings && Array.isArray(value.settings.selected_sources))return value;
    } catch(_) {}
    return null;
  }
  let records = {};
  let folderCheckRequest=0;
  let recaching=false;
  let progressStarted=0,progressTimer=null,progressView=null,progressKey='',progressChanged=0;
  function elapsed(seconds){seconds=Math.max(0,Math.floor(seconds));return seconds>=60?`${Math.floor(seconds/60)}m ${seconds%60}s`:`${seconds}s`;}
  function renderProgress() {
    if(connectionMessage){
      $('contextStatus').textContent=connectionMessage;
      const note=$('contextProgressNote');
      if(note){note.hidden=false;note.textContent='Last confirmed counts are shown. WINGS is checking the same run; no new preparation has been started.';}
      return;
    }
    if(!progressView)return;
    const names={ecology:'weather and migration',phenology:'seasonal bird patterns',public_genotypes:'public genotypes',ebird:'eBird observations',outbreak:'APHIS detections'};
    const active=progressView.active_provider || sources.find(name=>records[name]?.status==='PREPARING');
    const detail=active==='ebird'?records.ebird?.import_progress:null;
    $('contextStatus').textContent=`Preparing ${names[active] || 'selected sources'}${detail?.message?' — '+detail.message:''} · ${elapsed((Date.now()-progressStarted)/1000)} elapsed`;
    const note=$('contextProgressNote');if(note){
      note.hidden=false;
      const gap=detail?Math.floor((Date.now()-progressChanged)/1000):0;
      note.textContent=active==='ebird'?'Large downloads are scanned in full. Keep the runner running. '+(gap>=20?`Last processing update ${elapsed(gap)} ago; waiting for the next count.`:'Record counts update as files are processed.'): 'Surveillance-data preparation is running separately from sequencing.';
    }
  }
  function stopProgress(){if(progressTimer!==null && typeof clearInterval==='function')clearInterval(progressTimer);progressTimer=null;progressView=null;progressStarted=0;progressKey='';if($('contextProgressNote'))$('contextProgressNote').hidden=true;}
  async function checkEbirdFolder() {
    const area=$('contextFolderCheck');if(!area)return;
    const token=++folderCheckRequest,path=$('contextSource').value.trim() || $('contextPackage').value.trim();
    area.replaceChildren();$('contextDownloadHelp').hidden=false;
    if(!$('contextEbird').checked){area.textContent='Select eBird observations and effort above to check this folder.';return;}
    if(!path){area.textContent='No folder selected. WINGS will look for compatible cached observations during preparation.';return;}
    if(!$('metadataFile').files[0]){area.textContent='Select metadata first, then check this folder against its regions and dates.';return;}
    area.textContent='Checking folder contents and metadata coverage on the runner…';
    try {
      const value=await input();
      const plan=await request('/api/context/plan',{metadata:value.metadata,options:value.settings});
      const current=await input();
      if(token!==folderCheckRequest || current.metadata!==value.metadata || ['days','ebird_source','ebird_package'].some(key=>current.settings[key]!==value.settings[key]) || current.settings.selected_sources.includes('ebird')!==value.settings.selected_sources.includes('ebird'))return;
      showRequest(plan.ebird_request || {});area.replaceChildren();
      const found=plan.ebird_folder;
      if(!found){area.textContent='This runner does not yet support folder checks. Restart the updated runner.';return;}
      const label=document.createElement('strong');
      label.textContent=found.kind==='prepared'?'WINGS-prepared observations dataset':found.kind==='download'?'Extracted eBird observations download':'Folder not recognized';
      const detail=document.createElement('p');detail.textContent=found.message;
      area.append(label,detail);
      if(found.files?.length){const list=document.createElement('ul');for(const file of found.files){const item=document.createElement('li');item.textContent=file;list.append(item);}area.append(list);}
      $('contextDownloadHelp').hidden=found.kind==='prepared';
      $('contextCoverageRow').hidden=found.kind!=='download' || found.status==='INVALID';
      if(found.kind==='prepared')$('contextCoverage').checked=false;
      return found;
    } catch(error){if(token===folderCheckRequest)area.textContent='Folder check failed: '+error.message;}
  }
  async function rebuildEbirdCache() {
    if(recaching || preparing)return;
    if(window.WINGS_CONTEXT_PICKER?.isBusy()){$('contextRecacheStatus').textContent='Finish choosing the original download first.';return;}
    recaching=true;$('contextRecacheRun').disabled=true;
    const status=$('contextRecacheStatus');status.textContent='Checking the original download…';
    try {
      if(!$('metadataFile').files[0])throw new Error('Select metadata.tsv first.');
      if(!$('contextEbird').checked)throw new Error('Select eBird observations and effort above.');
      const found=await checkEbirdFolder();
      if(found?.kind!=='download' || found.status!=='RECOGNIZED')throw new Error('Choose the original extracted eBird download, including observations, sampling-event data, terms and citation files. A prepared cache cannot be expanded on its own.');
      if(!$('contextCoverage').checked)throw new Error('Confirm the original download covers all species, required regions and dates before rebuilding.');
      status.textContent='Building a new observations cache for the current metadata…';
      await prepareOnly();
      if(records.ebird?.status!=='READY')throw new Error(records.ebird?.reason || 'eBird cache could not be rebuilt. Check the download coverage and try again.');
      status.textContent='New eBird cache prepared for this metadata. Your previous dataset is unchanged. Additional data are ready for the selected available sources.';
    }catch(error){status.textContent=error.message;}
    finally{recaching=false;$('contextRecacheRun').disabled=false;}
  }
  function setCreateSettings(provider) {
    if (typeof provider !== 'function') throw new Error('Context run settings must be a function');
    createSettings = provider;
  }
  const options = () => ({
    selected_sources:sources.filter(name => $(controls[name]).checked),
    days:Number($('contextDays').value),network:$('contextNetwork').checked,
    phenology:$('contextPhenology').checked,phenology_year:Number($('contextYear').value),
    ebird_package:$('contextPackage').value.trim(),ebird_source:$('contextSource').value.trim(),
    all_species_confirmed:$('contextCoverage').checked,outbreak_file:'',
    // Keep the full public reference available; users filter it in the report.
    global_genotypes:true,required:[]
  });
  async function input() {
    await validateMetadata();
    const file = $('metadataFile').files[0];
    if (!file) throw new Error('Select metadata.tsv first.');
    const metadata = await file.text();
    const settings = options();
    const bytes = new TextEncoder().encode(metadata+'\n'+JSON.stringify(settings)+'\n'+JSON.stringify(createSettings()));
    const hash = await crypto.subtle.digest('SHA-256',bytes);
    const signature = [...new Uint8Array(hash)].map(n=>n.toString(16).padStart(2,'0')).join('');
    return {file,metadata,settings,signature};
  }
  async function request(path,body,timeout=0) {
    const controller=timeout && typeof AbortController==='function'?new AbortController():null;
    const timer=controller?setTimeout(()=>controller.abort(),timeout):null;
    try {
      const response=await fetch(origin+path,{
        ...(body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
        ...(controller?{signal:controller.signal}:{})
      });
      if(!response.ok){
        // Authentication failures can be plain text. Preserve the HTTP status
        // without trying to interpret a sign-in page as preparation JSON.
        const error=new Error('Context request failed');error.status=response.status;throw error;
      }
      return await response.json();
    } finally {if(timer!==null)clearTimeout(timer);}
  }
  async function followPreparation(runId,progress) {
    let failures=0;
    if(progress && !['PREPARING','READY','FAILED','BLOCKED','INTERRUPTED','NOT_PREPARED'].includes(progress.status))progress=null;
    while(!progress || progress.status==='PREPARING') {
      if(progress)showStatus(progress);
      await new Promise(resolve=>setTimeout(resolve,failures?Math.min(15000,1000*2**Math.min(failures,4)):1000));
      try {
        const next=await request(`/api/runs/${encodeURIComponent(runId)}/context`,undefined,20000);
        if(!next || !['PREPARING','READY','FAILED','BLOCKED','INTERRUPTED','NOT_PREPARED'].includes(next.status))
          throw new Error('Invalid context status response');
        progress=next;failures=0;connectionMessage='';
      } catch(error) {
        if(error.status===404){connectionMessage='';return {status:'NOT_FOUND',providers:{}};}
        failures++;
        connectionMessage=[401,403].includes(error.status)
          ? 'Session access interrupted. Open WINGS from the desktop app to reconnect; preparation may still be running.'
          : 'Connection interrupted; checking preparation status… Keep the runner running.';
        renderProgress();
      }
    }
    connectionMessage='';
    return progress;
  }
  function openSettings(id,focusId) {
    $('contextAdvanced').open=true;
    $(id).open=true;
    const focus = focusId ? $(focusId) : $(id).querySelector('summary');
    focus.focus();focus.scrollIntoView({block:'nearest',behavior:'smooth'});
  }
  function countText(name,record) {
    const number = key => Number.isInteger(record[key]) && record[key]>=0;
    if(name==='ebird' && record.import_progress){
      const p=record.import_progress;
      if(Number.isInteger(p.rows_processed))return `${p.rows_processed.toLocaleString('en-US')} records read · ${p.rows_retained.toLocaleString('en-US')} retained`;
      if(Number.isFinite(p.bytes_processed) && p.total_bytes>0)return `${Math.floor(100*p.bytes_processed/p.total_bytes)}% of this file read (${(p.bytes_processed/1048576).toFixed(1)} / ${(p.total_bytes/1048576).toFixed(1)} MiB)`;
      return p.message || '';
    }
    if(name==='ecology' && number('weather_ready') && number('migration_ready') && number('sample_count')) return `Weather ${record.weather_ready}/${record.sample_count} · Migration ${record.migration_ready}/${record.sample_count}`;
    if(name==='phenology' && number('ready_profiles') && number('sample_count')) return `${record.ready_profiles}/${record.sample_count} profiles available`;
    if(name==='public_genotypes' && number('included_runs')) return `${record.included_runs} public sequencing runs`;
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
        state.textContent=({download:'Ready',cache:'Cached snapshot',bundled:'Bundled snapshot',user:'Your CSV'})[record.source_mode] || 'Ready';
        if(record.source_mode==='cache' || record.source_mode==='bundled')state.dataset.tone='attention';
      }
      const count=$('contextCount-'+name);count.textContent=countText(name,record);count.hidden=!count.textContent;
      const action=$('contextAction-'+name);action.hidden=true;
      if(name==='ebird' && selected && !preparing && record.status==='NEEDS_IMPORT') {
        action.textContent='Import data';action.hidden=false;
      }
    }
  }
  function showStatus(data) {
    records={...records,...(data.providers || {})};
    renderCards();
    const next=$('contextNextAction');if(next){
      next.textContent=data.status==='PREPARING'?'Preparing context. Wait for preparation to finish, then continue to Analysis.':
        data.status==='READY'?($('contextEbird').checked && records.ebird?.status!=='READY'?'eBird observations are unavailable. Review the folder details or continue to Analysis with the other available sources.':'Surveillance-data preparation finished. Continue to Analysis to choose analysis options.'):
        'Click Prepare selected data to build or reuse data. Continue to Analysis only changes the setup step.';
    }
    const status=$('contextStatus');
    if(data.status==='PREPARING'){
      if(!progressStarted)progressStarted=Date.now();progressView=data;
      const key=JSON.stringify(records.ebird?.import_progress || null);if(key!==progressKey){progressKey=key;progressChanged=Date.now();}
      renderProgress();
      if(progressTimer===null && typeof setInterval==='function')progressTimer=setInterval(renderProgress,1000);
      return;
    }
    stopProgress();
    if(data.status==='READY') {
      const chosen=sources.filter(name=>$(controls[name]).checked);
      const count=chosen.filter(name=>records[name]?.status==='READY').length;
      status.textContent=chosen.length ? (count===chosen.length ? 'Additional surveillance data saved. Continue to Analysis.' : 'Context saved with available data. Continue to Analysis.') : 'No additional surveillance sources selected. Continue to Analysis.';
    } else if(data.status==='REVIEW') status.textContent='Checking selected sources…';
    else if(data.status==='STALE') status.textContent='Selection changed. Prepare selected data again.';
    else if(data.status==='NOT_FOUND') status.textContent='Saved preparation was not found on this runner. Check that WINGS is using the original workspace.';
    else if(data.status==='NOT_PREPARED') status.textContent='Preparation was not started on the runner. Check your settings, then prepare again.';
    else if(['FAILED','BLOCKED','INTERRUPTED'].includes(data.status)) status.textContent='Preparation could not finish. Check the runner log, then try again.';
  }
  function showRequest(request) {
    const target=$('contextRequest');target.replaceChildren();
    const windows=Array.isArray(request.windows)?request.windows:[];
    const text=document.createElement('p');target.append(text);
    if(!windows.length) {
      text.textContent='Provide collection dates and regions to plan an eBird request.';
      return;
    }
    const validDate=value=>typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
      Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10)===value;
    if(windows.some(w=>!w || !validDate(w.date_from) || !validDate(w.date_to) || w.date_from>w.date_to)) {
      text.textContent='Update collection dates and prepare selected data again to plan an eBird download.';
      return;
    }
    // eBird accepts one inclusive month/year range. Keep exact matching windows unchanged.
    const first=windows.reduce((date,w)=>w.date_from<date?w.date_from:date,windows[0].date_from);
    const last=windows.reduce((date,w)=>w.date_to>date?w.date_to:date,windows[0].date_to);
    const months=['January','February','March','April','May','June','July','August','September','October','November','December'];
    const monthLabel=date=>`${months[Number(date.slice(5,7))-1]} ${date.slice(0,4)}`;
    text.textContent='On eBird, select “Choose date range”:';
    const dates=document.createElement('div');dates.className='context-settings-grid';
    for(const [label,date] of [['From',first],['To',last]]) {
      const row=document.createElement('p');
      const title=document.createElement('strong');title.textContent=label+': ';
      const value=document.createElement('span');value.textContent=monthLabel(date);
      row.append(title,value);dates.append(row);
    }
    const regions=[...new Set(windows.map(w=>[w.country,w.state].filter(v=>typeof v==='string' && v.trim()).join(' / ')))].filter(Boolean).sort();
    const places=document.createElement('p');places.textContent='Regions: '+regions.join('; ');
    const note=document.createElement('p');note.className='context-note';
    note.textContent='WINGS filters the download to each sample’s original matching window.';
    target.append(dates,places,note);
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
    if(preparing)throw new Error('Surveillance-data preparation is already running.');
    if(window.WINGS_CONTEXT_PICKER?.isBusy())throw new Error('Finish choosing a folder first.');
    preparing=true;prepared=null;clearAcknowledgment();notifyReadiness();
    const unlock=lockInputs();
    $('contextPrepare').textContent='Preparing…';
    if($('contextPrepareHere'))$('contextPrepareHere').textContent='Preparing…';
    let progress;
    try {
      if($('contextEbird').checked && ($('contextSource').value.trim() || $('contextPackage').value.trim()))await checkEbirdFolder();
      const value=await review();
      showStatus({status:'PREPARING'});
      const run=await request('/api/runs',{...createSettings(),name:'Surveillance-data preparation',options:{context_setup:true}});
      const upload=await fetch(`${origin}/api/runs/${encodeURIComponent(run.run_id)}/files?kind=metadata&filename=metadata.tsv`,{method:'PUT',body:value.file});
      if(!upload.ok)throw new Error(await upload.text());
      remember({runId:run.run_id,signature:value.signature,settings:value.settings});
      try {
        progress=await request(`/api/runs/${encodeURIComponent(run.run_id)}/context`,{options:value.settings},20000);
      } catch(error) {
        // The POST may have reached the worker even if its response was lost.
        // Recover via GET; never repeat the start request automatically.
        connectionMessage='Connection interrupted; checking preparation status… Keep the runner running.';
        renderProgress();
      }
      progress=await followPreparation(run.run_id,progress);
      if(progress.status!=='READY')throw new Error('Surveillance-data preparation did not finish.');
      if((await input()).signature!==value.signature)throw new Error('Inputs changed during preparation.');
      prepared={runId:run.run_id,signature:value.signature};
      showStatus(progress);
    } catch(error) {
      remember(null);
      showStatus({...(progress || {}),status:progress?.status || 'FAILED'});
      throw error;
    } finally {
      preparing=false;unlock();renderCards();notifyReadiness();
      $('contextPrepare').textContent='Prepare selected data';
      if($('contextPrepareHere'))$('contextPrepareHere').textContent='Prepare selected data';
    }
  }
  async function recoverPreparation() {
    const saved=recalled();
    if(!saved || preparing)return;
    preparing=true;prepared=null;clearAcknowledgment();notifyReadiness();
    // Restore the options used by this job; the metadata file must be selected
    // again before attaching results. Its signature is checked by readyForRun.
    const settings=saved.settings;
    for(const name of sources)$(controls[name]).checked=settings.selected_sources.includes(name);
    for(const [id,key] of [['contextDays','days'],['contextYear','phenology_year'],['contextPackage','ebird_package'],['contextSource','ebird_source']])
      if(settings[key]!==undefined)$(id).value=settings[key];
    $('contextNetwork').checked=!!settings.network;
    $('contextCoverage').checked=!!settings.all_species_confirmed;
    const unlock=lockInputs();
    $('contextPrepare').textContent='Reconnecting…';
    if($('contextPrepareHere'))$('contextPrepareHere').textContent='Reconnecting…';
    connectionMessage='Reconnecting to the saved context preparation…';renderProgress();
    try {
      const progress=await followPreparation(saved.runId,null);
      showStatus(progress);
      if(progress.status==='READY'){
        prepared={runId:saved.runId,signature:saved.signature};
        $('contextStatus').textContent='Prepared context recovered. Select the original metadata file to use it; matching settings and metadata are required.';
      } else remember(null);
    } finally {
      preparing=false;unlock();renderCards();notifyReadiness();
      $('contextPrepare').textContent='Prepare selected data';
      if($('contextPrepareHere'))$('contextPrepareHere').textContent='Prepare selected data';
    }
  }
  async function readyForRun() {
    const value=await input();
    if(preparing || !prepared || prepared.signature!==value.signature)throw new Error('In Metadata, click Prepare selected data or Skip additional data before continuing.');
    if(!isReady())throw new Error('Review the unavailable sources in Metadata, then acknowledge continuing with available data or change the selection and prepare again.');
    return prepared;
  }
  async function attach(runId) {
    const ready=await readyForRun();const value=await input();
    const result=await request(`/api/runs/${encodeURIComponent(runId)}/context`,{reuse_run_id:ready.runId,options:value.settings});
    if(result.status!=='READY')throw new Error('Prepared context could not be attached to this run.');
  }
  function report(error) {
    console.error('WINGS context:',error);
    $('contextStatus').textContent=error.setupValidation ? error.message : ['Select metadata.tsv first.','Finish choosing a folder first.'].includes(error.message) ? error.message : 'Preparation could not finish. Check the runner log, then try again.';
  }
  function invalidate(event) {
    if(preparing)return;
    if(event?.target?.id==='contextAcceptUnavailable'){notifyReadiness();return;}
    if(event?.target?.id!=='contextCoverage'){
      folderCheckRequest++;
      if($('contextFolderCheck'))$('contextFolderCheck').textContent='Selection changed. Check the folder again to confirm its contents and metadata coverage.';
      if($('contextDownloadHelp'))$('contextDownloadHelp').hidden=false;
    }
    prepared=null;clearAcknowledgment();remember(null);records={};showStatus({status:'STALE'});notifyReadiness();
  }
  $('contextSkip')?.addEventListener('click', async () => {
    if (preparing) return;
    try {
      await validateMetadata();
      for (const name of sources) $(controls[name]).checked = false;
      invalidate();
      await prepareOnly();
    } catch(error) { report(error); }
  });
  $('contextAcceptUnavailable')?.addEventListener('change', notifyReadiness);
  $('contextSetup').addEventListener('input',invalidate);
  $('metadataFile').addEventListener('change',async()=>{
    if(preparing)return;
    const previous = prepared; prepared = null; clearAcknowledgment(); notifyReadiness();
    await Promise.resolve(); // Let the launcher register validation for the newly selected file.
    if(previous){
      try {if((await input()).signature===previous.signature){prepared=previous;showStatus({status:'READY',providers:records});notifyReadiness();return;}}catch(_){}
    }
    invalidate();$('contextRequest').textContent='Prepare selected data to determine the required regions and dates.';
  });
  $('contextAction-ebird').addEventListener('click',()=>openSettings('contextEbirdImport','contextSource'));
  $('contextCheckFolder')?.addEventListener('click',()=>checkEbirdFolder());
  $('contextRecache')?.addEventListener('click',()=>{
    $('contextRecachePanel').hidden=!$('contextRecachePanel').hidden;
    if(!$('contextRecachePanel').hidden){$('contextRecacheStatus').textContent='Choose the original download above, then confirm its coverage and rebuild.';$('contextRecachePanel').scrollIntoView({block:'nearest'});}
  });
  $('contextRecacheRun')?.addEventListener('click',()=>rebuildEbirdCache());
  $('contextSource').addEventListener('change',()=>checkEbirdFolder());
  $('contextPrepare').addEventListener('click',()=>prepareOnly().catch(report));
  $('contextPrepareHere')?.addEventListener('click',()=>prepareOnly().catch(report));
  renderCards();
  window.WINGS_CONTEXT_SETUP={readyForRun,attach,review,prepareOnly,showStatus,setCreateSettings,checkEbirdFolder,rebuildEbirdCache,recoverPreparation,isReady,setMetadataValidation};
  recoverPreparation().catch(report);
})();
