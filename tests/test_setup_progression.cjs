// Exercise production navigation and metadata-validation code without network or sequencing.
'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../assets/wings-run.js'),'utf8');
const Core=require('../assets/wings-metadata-core.js');
const slice=(a,b)=>{const begin=source.indexOf(a),end=source.indexOf(b,begin);assert.ok(begin>=0&&end>begin);return source.slice(begin,end);};
const navigation=slice('  let navigationRequest = 0;', '  async function checkRunner()');
const validation=slice('  function renderCredentialHelp()', '  function renderReads()');
function harness(fetcher){
  const nodes={};const get=id=>nodes[id]??=( {textContent:'',hidden:false,focus(){this.focused=true;}} );
  const state={step:2,reads:[{name:'A.fastq.gz'}],metadata:null,metadataIds:[],metadataError:'',metadataPending:false,metadataValidation:null};
  let ready=true,checks=0;
  const api={readyForRun:async()=>{checks++;if(!ready)throw Error('Prepare selected data or Skip additional data.');}};
  const context={state,$:get,window:{WINGS_CONTEXT_SETUP:api},WINGS_METADATA:Core,
    document:{querySelectorAll:()=>[]},stepMeta:[['Details',''],['Reads',''],['Metadata',''],['Analysis',''],['Preflight','']],
    localMode:true,localOrigin:'http://127.0.0.1:8765',AbortController,setTimeout,clearTimeout,
    renderPreflight(){},checkDocker(){},renderMetadata(){},stripFastq:name=>name.replace(/\.(fastq|fq)(\.gz)?$/i,''),
    fetch:fetcher||(async()=>({ok:true,json:async()=>({ok:true,errors:[],warnings:[]})}))};
  vm.createContext(context);vm.runInContext(validation+navigation,context);
  return {context,state,nodes,get,api,select:async(text='sample_id\tcollection_date\nA\t2026-11-25\n')=>{
    state.metadata={size:Buffer.byteLength(text),text:async()=>text};return context.refreshMetadataValidation();
  },setReady:value=>ready=value,checks:()=>checks};
}
test('date error remains inline and blocks Continue plus both step shortcuts',async()=>{
  const h=harness(async()=>({ok:true,json:async()=>({ok:false,errors:['line 2: collection_date invalid: 25/11/2026'],warnings:[]})}));
  await h.select();assert.match(h.state.metadataError,/line 2: collection_date/);
  for(const [from,to] of [[2,3],[0,3],[1,4]]){h.state.step=from;await h.context.setStep(to);assert.equal(h.state.step,2);assert.match(h.get('setupGateMessage').textContent,/line 2/);}
  assert.equal(h.checks(),0);
});
test('valid metadata needs a preparation decision; optional credentials do not block explicit skip',async()=>{
  const h=harness();await h.select();h.setReady(false);await h.context.setStep(3);assert.equal(h.state.step,2);assert.match(h.get('setupGateMessage').textContent,/Prepare selected/);
  h.setReady(true);await h.context.setStep(3);assert.equal(h.state.step,3);await h.context.setStep(4);assert.equal(h.state.step,4);assert.equal(h.get('setupGateMessage').hidden,true);
});
test('missing or unavailable validator fails closed with an actionable message',async()=>{
  for(const response of [{ok:false,status:404},{ok:true,json:async()=>({})}]){
    const h=harness(async()=>response);await h.select();await h.context.setStep(4);assert.equal(h.state.step,2);assert.equal(h.checks(),0);assert.match(h.state.metadataError,/runner|response/);
  }
});
test('a late response for replaced metadata cannot overwrite the new validation',async()=>{
  let release,requests=0;
  const h=harness(async()=>{const current=++requests;if(current===1)await new Promise(r=>release=r);return {ok:true,json:async()=>({ok:current!==1,errors:[],warnings:[]})};});
  const first=h.select('sample_id\nA\n');while(!release)await Promise.resolve();
  await h.select();release();await first;assert.equal(h.context.metadataReady(),true);await h.context.setStep(3);assert.equal(h.state.step,3);
});
test('a pending check gates navigation and a newer Back action wins',async()=>{
  let release;const h=harness(async()=>{await new Promise(r=>release=r);return {ok:true,json:async()=>({ok:true,errors:[],warnings:[]})};});
  const validation=h.select();while(!release)await Promise.resolve();assert.equal(h.context.metadataReady(),false);
  const forward=h.context.setStep(4);await h.context.setStep(1);release();await validation;await forward;assert.equal(h.state.step,1);
});
test('changed FASTQ sample IDs block progression even with a prepared selection',async()=>{
  const h=harness();await h.select();h.state.reads=[{name:'B.fastq.gz'}];await h.context.setStep(3);assert.equal(h.state.step,2);assert.match(h.get('setupGateMessage').textContent,/missing/);
});
test('credential guidance shows presence only and remains outside the step panels',()=>{
  const h=harness();h.state.runner={desktop_mode:true,phylodynamics_ready:true,ebirdst_key_configured:false};h.context.renderCredentialHelp();assert.match(h.get('credentialStatus').textContent,/NCBI email: Configured/);assert.match(h.get('credentialStatus').textContent,/key: Not configured/);
  const html=fs.readFileSync(path.join(__dirname,'../run.html'),'utf8');assert.match(html,/NCBI &amp; eBird access/);assert.match(html,/Additional surveillance data \(optional\)/);assert.match(html,/id="recheckMetadata"/);
});
