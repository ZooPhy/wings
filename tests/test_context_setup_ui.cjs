'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const crypto=require('node:crypto').webcrypto;
const path=require('node:path');
class Element {
  constructor(tag='div') {Object.assign(this,{tagName:tag,value:'',checked:false,files:[],children:[],disabled:false,dataset:{},className:'',open:false,listeners:{},attrs:{},_text:''});}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set textContent(value){this._text=String(value);this.children=[];}
  append(...children){for(const child of children){child.parent=this;this.children.push(child);}}
  replaceChildren(...children){this.children=[];this._text='';this.append(...children);}
  addEventListener(type,fn){this.listeners[type]=fn;}
  setAttribute(key,value){this.attrs[key]=value;}
  querySelectorAll(selector){const all=[];const visit=el=>{for(const child of el.children){if(selector==='input,button,select'?['input','button','select'].includes(child.tagName):selector==='details[open]'?child.tagName==='details'&&child.open:selector.startsWith('.')?child.className.split(' ').includes(selector.slice(1)):child.tagName===selector)all.push(child);visit(child);}};visit(this);return all;}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  remove(){this.parent.children=this.parent.children.filter(c=>c!==this);}
  focus(){this.focused=true;}
  scrollIntoView(){this.scrolled=true;}
}
(async()=>{
  const sources=['ecology','phenology','public_genotypes','ebird','outbreak'];
  const controls={ecology:'contextEcology',phenology:'contextPhenology',public_genotypes:'contextGenotypes',ebird:'contextEbird',outbreak:'contextAphis'};
  const ids=['contextSetup','contextDays','contextNetwork','contextYear','contextPackage','contextSource','contextCoverage','contextStatus','contextRequest','contextPrepare','contextAdvanced','contextEbirdImport','metadataFile',...Object.values(controls),...sources.flatMap(s=>['contextState-'+s,'contextCount-'+s,'contextAction-'+s])];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element(id==='contextPrepare'||id.startsWith('contextAction-')?'button':'div')]));
  for(const id of ['contextDays','contextNetwork','contextYear','contextPackage','contextSource','contextCoverage',...Object.values(controls)])elements[id].tagName='input';
  for(const [id,el] of Object.entries(elements))if(id!=='contextSetup'&&id!=='metadataFile')elements.contextSetup.append(el);
  for(const id of ['contextEbirdImport'])elements[id].append(new Element('summary'));
  elements.contextYear.tagName='select';
  elements.contextDays.value='30';elements.contextYear.value='2023';elements.contextNetwork.checked=true;
  for(const id of Object.values(controls))elements[id].checked=true;
  let metadata='sample_id\nA\n';elements.metadataFile.files=[{text:async()=>metadata}];
  const issue='PRIVATE SAMPLE DIAGNOSTIC';
  const windows=[['2025-09-20','2025-11-19'],['2026-03-09','2026-05-08'],['2025-03-16','2025-05-15'],['2025-09-21','2025-11-20'],['2025-09-27','2025-11-26'],['2025-11-11','2026-01-10']].map(([date_from,date_to])=>({country:'US',state:'Kentucky',date_from,date_to}));
  const originalWindows=JSON.stringify(windows);
  const plan={sample_count:30,species:['Canada Goose'],issues:[{sample_id:'A',issue}],ebird_request:{windows},providers:{phenology:{status:'NEEDS_ACCESS',reason:'private diagnostic'}}};
  let responseStatus='READY',counter=0,settings={},poll=false,failRequest=false;
  const calls=[];
  const providers=()=>Object.fromEntries(sources.map(s=>[s,settings.selected_sources.includes(s)?(s==='ecology'?{status:'PARTIAL',weather_ready:10,migration_ready:28,sample_count:30,reason:issue}:s==='ebird'?{status:'NEEDS_IMPORT',reason:'<img src=x onerror=evil()>'}:s==='phenology'?{status:'NEEDS_ACCESS',reason:'secret path'}:{status:'READY',included_runs:10}):{status:'DISABLED',reason:'Not selected'}]));
  const fetch=async(url,opts={})=>{
    calls.push({url,opts});let data={};
    if(failRequest)throw new Error('SECRET /private/local/path stack trace');
    if(url.endsWith('/api/context/plan'))data=plan;
    else if(url.endsWith('/api/runs')){const body=JSON.parse(opts.body);if(sandbox.storageRevision!==undefined)assert.equal(body.storage_revision,sandbox.storageRevision);data={run_id:'draft'+(++counter)};}
    else if(url.includes('/files?'))data={stored:'metadata'};
    else if(url.endsWith('/context')){
      if(opts.body){const body=JSON.parse(opts.body);settings=body.options;if(body.reuse_run_id){data={status:'READY'};return {ok:true,json:async()=>data};}}
      data={status:poll&&opts.body?'PREPARING':responseStatus,providers:providers()};
    }else throw new Error('Unexpected request '+url);
    return {ok:true,json:async()=>data,text:async()=>JSON.stringify(data)};
  };
  const errors=[];
  const sandbox={document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag)},location:{hostname:'localhost',origin:'http://localhost:8765'},window:{},crypto,TextEncoder,fetch,setTimeout:fn=>fn(),console:{error:(...args)=>errors.push(args)}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../assets/wings-context-setup.js'),'utf8'),sandbox);
  const ui=sandbox.window.WINGS_CONTEXT_SETUP;
  const launcher=fs.readFileSync(path.join(__dirname,'../assets/wings-run.js'),'utf8');
  vm.runInNewContext(launcher.slice(launcher.indexOf('  // WINGS_CONTEXT_STORAGE_V2:'),launcher.indexOf('  async function startRun()')),sandbox);
  sandbox.storageRevision='revision-one';
  await assert.rejects(ui.readyForRun(),/prepare context/);
  sandbox.window.WINGS_CONTEXT_PICKER={isBusy:()=>true};
  await assert.rejects(ui.prepareOnly(),/Finish choosing a folder/);assert.equal(calls.length,0);
  delete sandbox.window.WINGS_CONTEXT_PICKER;
  const preparing=ui.prepareOnly();assert.equal(elements.contextYear.disabled,true);await assert.rejects(ui.prepareOnly(),/already running/);await preparing;
  assert.equal((await ui.readyForRun()).runId,'draft1');
  assert.equal(calls.filter(c=>c.url.endsWith('/api/context/plan')).length,1,'One click includes review');
  assert.equal(calls.filter(c=>c.url.endsWith('/api/runs')).length,1);
  assert.equal(calls.filter(c=>c.url.includes('/files?')).length,1);
  assert.equal(calls.filter(c=>c.url.endsWith('/start')).length,0);
  assert.equal(settings.selected_sources.length,5);assert.deepEqual(settings.required,[]);
  assert.equal(settings.days,30);assert.equal(settings.phenology_year,2023);assert.equal(settings.network,true);
  assert.equal(settings.outbreak_file,'','The launcher always uses automatic APHIS acquisition');
  assert.equal(settings.global_genotypes,true,'The launcher includes the full public reference without a separate toggle');
  assert.equal(elements['contextCount-public_genotypes'].textContent,'10 public sequencing runs');
  assert.equal(elements['contextState-ecology'].textContent,'Partial coverage');
  assert.equal(elements['contextCount-ecology'].textContent,'Weather 10/30 · Migration 28/30');
  assert.equal(elements['contextAction-ebird'].hidden,false);elements['contextAction-ebird'].listeners.click();
  assert.equal(elements.contextAdvanced.open,true);assert.equal(elements.contextEbirdImport.open,true);assert.equal(elements.contextSource.focused,true);
  assert.doesNotMatch(elements.contextSetup.textContent,/PRIVATE SAMPLE|secret path|<img|stack trace/);
  assert.match(elements.contextRequest.textContent,/From: March 2025/);
  assert.match(elements.contextRequest.textContent,/To: May 2026/);
  assert.match(elements.contextRequest.textContent,/Regions: US \/ Kentucky/);
  assert.equal((elements.contextRequest.textContent.match(/US \/ Kentucky/g)||[]).length,1);
  assert.deepEqual(elements.contextRequest.querySelectorAll('strong').map(el=>el.textContent),['From: ','To: ']);
  assert.equal(JSON.stringify(windows),originalWindows,'Download guidance must not modify exact sample matching windows');
  await ui.attach('analysis');assert.equal(JSON.parse(calls.at(-1).opts.body).reuse_run_id,'draft1');
  elements.contextEcology.checked=false;elements.contextSetup.listeners.input();
  assert.equal(elements['contextState-ecology'].textContent,'Not selected');assert.equal(elements['contextCount-ecology'].hidden,true);
  await assert.rejects(ui.readyForRun(),/prepare context/);await ui.prepareOnly();assert.equal(settings.selected_sources.includes('ecology'),false);
  for(const id of Object.values(controls))elements[id].checked=false;
  elements.contextSetup.listeners.input();await ui.prepareOnly();assert.deepEqual(settings.selected_sources,[]);assert.equal(settings.phenology,false);
  assert.match(elements.contextStatus.textContent,/No context sources selected/);await ui.readyForRun();
  for(const name of sources)assert.equal(elements['contextState-'+name].textContent,'Not selected');
  sandbox.storageRevision='revision-two';await assert.rejects(ui.readyForRun(),/prepare context/);
  elements.contextEcology.checked=true;poll=true;await ui.prepareOnly();poll=false;
  assert.equal(elements.contextPrepare.disabled,false);assert.equal(elements.contextEcology.disabled,false);
  assert.equal(calls.some(c=>c.url.endsWith('/context')&&!c.opts.body),true,'Preparation progress polled');
  responseStatus='FAILED';await assert.rejects(ui.prepareOnly(),/did not finish/);await assert.rejects(ui.readyForRun(),/prepare context/);
  assert.equal(elements.contextPrepare.disabled,false);assert.equal(elements.metadataFile.disabled,false);
  assert.match(elements.contextStatus.textContent,/Check the runner log/);
  failRequest=true;await elements.contextPrepare.listeners.click();assert.doesNotMatch(elements.contextSetup.textContent,/SECRET|stack trace/);assert.equal(errors.length,1);failRequest=false;
  responseStatus='READY';await ui.prepareOnly();metadata='sample_id\nB\n';await assert.rejects(ui.readyForRun(),/prepare context/);
  elements.metadataFile.listeners.change();assert.match(elements.contextStatus.textContent,/Selection changed/);
  elements.metadataFile.files=[];await elements.contextPrepare.listeners.click();assert.equal(elements.contextStatus.textContent,'Select metadata.tsv first.');
  elements.metadataFile.files=[{text:async()=>metadata}];sandbox.storageRevision=undefined;await ui.prepareOnly();assert.equal(Object.hasOwn(JSON.parse(calls.filter(c=>c.url.endsWith('/api/runs')).at(-1).opts.body),'storage_revision'),false);
  const start=launcher.slice(launcher.indexOf('async function startRun()'),launcher.indexOf('\n  }',launcher.indexOf('async function startRun()')));
  assert.ok(start.indexOf('WINGS_CONTEXT_SETUP.attach')<start.indexOf('"reads", state.reads[i]'));
  const html=fs.readFileSync(path.join(__dirname,'../run.html'),'utf8');
  for(const id of ids)assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,`Unique control ${id}`);
  assert.equal((html.match(/data-context-source=/g)||[]).length,5);
  assert.doesNotMatch(html,/id="contextReview"|id="contextScope"|id="contextGlobal"|Use a global public genotype comparison|data-context-required|Sources required before launch|detailed warnings/);
  assert.match(html,/<select id="contextYear"><option value="2023">2023 — released 2025<\/option><\/select>/);
  assert.match(html,/<strong>Seasonal bird patterns<\/strong>/);
  assert.doesNotMatch(html,/<strong>Reference phenology<\/strong>|WINGS package folder/);
  assert.match(html,/<details id="contextAdvanced" class="context-advanced">/);
  elements.contextAphis.checked=true;
  for(const [source_mode,label] of Object.entries({download:'Ready',cache:'Cached snapshot',bundled:'Bundled snapshot',user:'Your CSV'})) {
    ui.showStatus({status:'READY',providers:{outbreak:{status:'READY',source_mode,refresh_status:'failed',snapshot_date:'2024-10-01',reason:'SECRET diagnostic'}}});
    assert.equal(elements['contextState-outbreak'].textContent,label);
    assert.equal(elements['contextCount-outbreak'].textContent,'Snapshot: 2024-10-01 · Refresh unavailable');
    assert.doesNotMatch(elements.contextSetup.textContent,/SECRET diagnostic/);
  }
  ui.showStatus({status:'READY',providers:{outbreak:{status:'READY',source_mode:'cache',refresh_status:'offline',retrieved_at:'2026-11-01T00:00:00+00:00'}}});
  assert.equal(elements['contextCount-outbreak'].textContent,'Retrieved: 2026-11-01 · Offline');
  ui.showStatus({status:'READY',providers:{outbreak:{status:'READY',source_mode:'user',refresh_status:'override'}}});
  assert.equal(elements['contextCount-outbreak'].textContent,'Snapshot date unknown');
  ui.showStatus({status:'READY',providers:{outbreak:{status:'UNAVAILABLE'}}});
  assert.equal(elements['contextAction-outbreak'].hidden,true);
  elements.contextPhenology.checked=true;
  ui.showStatus({status:'READY',providers:{phenology:{status:'NEEDS_ACCESS'},outbreak:{status:'NEEDS_IMPORT'}}});
  assert.equal(elements['contextAction-outbreak'].hidden,true);
  assert.equal(elements['contextAction-phenology'].hidden,true);
  assert.equal(elements['contextState-phenology'].textContent,'Access key needed');
  assert.doesNotMatch(html,/contextAphisImport|contextOutbreak|contextPhenologyAccess|Use your own APHIS CSV|Seasonal bird data access|data-context-pick="aphis_csv"/);
  assert.doesNotMatch(html,/Public genotype frequencies describe included sequencing runs, not population prevalence\./);
  for(const example of [
    {windows:[],expect:/Provide collection dates and regions/},
    {windows:[{country:'US',state:'Kentucky',date_from:'2025-12-31',date_to:'2026-01-01'},{country:'US',state:'Arizona',date_from:'2025-02-15',date_to:'2025-03-01'}],expect:/From: February 2025To: January 2026Regions: US \/ Arizona; US \/ Kentucky/},
    {windows:[{country:'US',state:'Kentucky',date_from:'2024-02-29',date_to:'2024-02-29'}],expect:/From: February 2024To: February 2024/},
    {windows:[{country:'US',state:'Kentucky',date_from:'2025-02-30',date_to:'2025-03-01'}],expect:/Update collection dates/},
    {windows:[{country:'US',state:'Kentucky',date_from:'2026-01-01',date_to:'2025-12-31'}],expect:/Update collection dates/}
  ]) {
    plan.ebird_request={windows:example.windows};const before=JSON.stringify(plan.ebird_request);
    await ui.review();assert.match(elements.contextRequest.textContent,example.expect);
    assert.equal(JSON.stringify(plan.ebird_request),before);
  }
  plan.ebird_request={windows};
  console.log('PASS: source-card behavior; automatic APHIS acquisition; removed settings panels; fallback labels and dates; safe attachment; no sequencing launches.');
})().catch(e=>{console.error(e);process.exitCode=1;});
