'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const crypto=require('node:crypto').webcrypto;
const source=fs.readFileSync(require('node:path').join(__dirname,'../assets/wings-context-setup.js'),'utf8');
class Element {
  constructor(tag='div'){Object.assign(this,{tagName:tag,value:'',checked:false,files:[],children:[],disabled:false,dataset:{},className:'',listeners:{},_text:''});}
  get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
  set textContent(v){this._text=String(v);this.children=[];}
  append(...xs){this.children.push(...xs);}
  replaceChildren(...xs){this._text='';this.children=xs;}
  addEventListener(name,f){this.listeners[name]=f;}
  setAttribute(){}
  querySelectorAll(){return this.children;}
  querySelector(){return new Element();}
  focus(){} scrollIntoView(){}
}
const controls=['contextEcology','contextPhenology','contextGenotypes','contextEbird','contextAphis'];
const ready={status:'READY',providers:{ebird:{status:'READY'}}};
const working={status:'PREPARING',active_provider:'ebird',providers:{ebird:{status:'PREPARING',import_progress:{stage:'observations',rows_processed:1331870000,rows_retained:1231194}}}};
function harness({storage=new Map(),get=async()=>ready,post=async()=>working,requestTimeout=false}={}){
  const elements={};
  const el=id=>elements[id]||(elements[id]=new Element());
  for(const id of ['contextPrepare','contextPrepareHere','contextDays','contextYear','contextPackage','contextSource','contextCoverage','contextNetwork',...controls])el('contextSetup').append(el(id));
  el('contextDays').value='30';el('contextYear').value='2023';el('contextEbird').checked=true;el('contextNetwork').checked=true;
  const metadata='sample_id\thost\tcollection_date\tstate\tcountry\nA\tRNSA\t2026-05-11\tOregon\tUSA\n';
  el('metadataFile').files=[{text:async()=>metadata}];
  const calls=[],delays=[],assertionErrors=[],heartbeats=new Map();let seq=0;
  const response=(body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>body,text:async()=>JSON.stringify(body)});
  const fetch=async(url,opts={})=>{
    calls.push({url,opts});
    if(url.endsWith('/api/context/plan'))return response({ebird_request:{windows:[]}});
    if(url.endsWith('/api/runs'))return response({run_id:'fixture-run'});
    if(url.includes('/files?'))return response({});
    if(url.endsWith('/context'))return opts.method==='POST'?post(response,opts):get(response,opts);
    throw Error('Unexpected request: '+url);
  };
  const sandbox={document:{getElementById:el,createElement:t=>new Element(t)},location:{hostname:'127.0.0.1',origin:'http://127.0.0.1:65146'},window:{},crypto,TextEncoder,console,
    localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},fetch,
    setTimeout:(fn,ms)=>{delays.push(ms);return setTimeout(fn,ms===20000?(requestTimeout?10:2000):1);},clearTimeout,
    setInterval:fn=>{heartbeats.set(++seq,fn);return seq;},clearInterval:id=>heartbeats.delete(id)};
  // Use real abort signals: a hung request must not hold the preparation forever.
  sandbox.AbortController=AbortController;
  // Default callbacks above return JSON payloads for convenience.
  const rawFetch=fetch;sandbox.fetch=async(...args)=>{try{const r=await rawFetch(...args);return r?.json?r:response(r);}catch(e){if(e.code==='ERR_ASSERTION')assertionErrors.push(e);throw e;}};
  vm.runInNewContext(source,sandbox);
  return {check:()=>assert.deepEqual(assertionErrors,[]),ui:sandbox.window.WINGS_CONTEXT_SETUP,el,storage,calls,delays,heartbeats,sandbox};
}
const tick=()=>new Promise(r=>setTimeout(r,5));
async function until(fn){for(let i=0;i<200;i++){if(fn())return;await tick();}throw Error('Timed out waiting for test condition');}

test('HTTP 400, 503, network and malformed JSON recover without another start or losing counters',async()=>{
  let n=0,h;
  h=harness({get:async response=>{
    n++;
    if(n<=4){
      assert.equal(h.el('contextPrepare').disabled,true);
      assert.match(h.el('contextCount-ebird').textContent,/1,331,870,000 records read · 1,231,194 retained/);
      if(n===1)return response({error:'temporary'},400);
      assert.match(h.el('contextStatus').textContent,/Connection interrupted/);
      for(const beat of h.heartbeats.values())beat();
      assert.match(h.el('contextStatus').textContent,/Connection interrupted/,'elapsed timer must not erase reconnect message');
      if(n===2)return response({},503);
      if(n===3)throw Error('network offline');
      return {ok:true,json:async()=>{throw SyntaxError('partial JSON');}};
    }
    return ready;
  }});
  const promise=h.ui.prepareOnly();
  await assert.rejects(h.ui.prepareOnly(),/already running/);
  await promise;h.check();
  assert.equal(n,5);
  assert.equal((await h.ui.readyForRun()).runId,'fixture-run');
  assert.equal(h.calls.filter(c=>c.url.endsWith('/api/runs')).length,1);
  assert.equal(h.calls.filter(c=>c.url.endsWith('/context')&&c.opts.method==='POST').length,1);
  assert.ok(h.delays.includes(15000),'retry delay is capped');
  assert.equal(h.el('contextPrepare').disabled,false);
  assert.equal(h.heartbeats.size,0);
});

test('plain-text session rejection remains recoverable and cannot start a duplicate',async()=>{
  let n=0,h;
  h=harness({get:async()=>{
    if(++n===1)return {ok:false,status:401,json:()=>{throw Error('must not parse text as JSON');}};
    assert.match(h.el('contextStatus').textContent,/Open WINGS from the desktop app/);
    assert.equal(h.el('contextPrepare').disabled,true);
    await assert.rejects(h.ui.prepareOnly(),/already running/);
    return ready;
  }});
  await h.ui.prepareOnly();h.check();assert.equal(n,2);
});

test('a hung status request times out then recovers',async()=>{
  let n=0;
  const h=harness({requestTimeout:true,get:async(response,opts)=>{
    if(++n===1)return new Promise((resolve,reject)=>opts.signal.addEventListener('abort',()=>reject(Error('timeout'))));
    return ready;
  }});
  await h.ui.prepareOnly();h.check();assert.equal(n,2);
});

test('a lost start response is reconciled by GET, never a second POST',async()=>{
  const h=harness({post:async()=>{throw Error('response lost');}});
  await h.ui.prepareOnly();
  assert.equal(h.calls.filter(c=>c.url.endsWith('/context')&&c.opts.method==='POST').length,1);
  assert.equal((await h.ui.readyForRun()).runId,'fixture-run');
});

for(const status of ['FAILED','BLOCKED','INTERRUPTED','NOT_PREPARED'])test('confirmed '+status+' stops polling and clears saved recovery',async()=>{
  const h=harness({get:async()=>({status,providers:{}})});
  await assert.rejects(h.ui.prepareOnly(),/did not finish/);
  assert.equal(h.storage.size,0);assert.equal(h.heartbeats.size,0);
  assert.equal(h.el('contextPrepare').disabled,false);
  await assert.rejects(h.ui.readyForRun(),/Prepare selected data/);
});

test('reload reconnects to the same run; original metadata restores readiness; changed metadata cannot attach',async()=>{
  let finish;
  const storage=new Map();
  const first=harness({storage,get:()=>new Promise(r=>{finish=r;})});
  const original=first.ui.prepareOnly();await until(()=>finish);
  const saved=storage.values().next().value;
  assert.doesNotMatch(saved,/RNSA|Oregon|sample_id/,'metadata is not stored in browser storage');
  let release;
  const restored=harness({storage,get:()=>new Promise(r=>{release=r;})});
  restored.el('metadataFile').files=[];
  await until(()=>release);
  await assert.rejects(restored.ui.prepareOnly(),/already running/);
  assert.equal(restored.calls.filter(c=>c.opts.method==='POST').length,0);
  release(ready);await until(()=>!restored.el('metadataFile').disabled);
  await assert.rejects(restored.ui.readyForRun(),/Select metadata/);
  restored.el('metadataFile').files=first.el('metadataFile').files;
  await restored.el('metadataFile').listeners.change();
  assert.equal((await restored.ui.readyForRun()).runId,'fixture-run');
  restored.el('metadataFile').files=[{text:async()=>'different metadata'}];
  await restored.el('metadataFile').listeners.change();
  await assert.rejects(restored.ui.readyForRun(),/Prepare selected data/);
  assert.equal(storage.size,0);
  finish(ready);await original;
});

test('unknown successful response retries instead of declaring failure',async()=>{
  let n=0;
  const h=harness({get:async()=>++n===1?{unexpected:true}:ready});
  await h.ui.prepareOnly();h.check();assert.equal(n,2);
});


test('missing run stops reconnecting without starting a replacement',async()=>{
  const h=harness({get:async response=>response({},404)});
  await assert.rejects(h.ui.prepareOnly(),/did not finish/);
  assert.equal(h.storage.size,0);
  assert.match(h.el('contextStatus').textContent,/original workspace/);
  assert.equal(h.calls.filter(c=>c.url.endsWith('/api/runs')).length,1);
});

test('unavailable local storage does not prevent preparation',async()=>{
  const h=harness();
  h.sandbox.localStorage.setItem=()=>{throw Error('storage blocked');};
  await h.ui.prepareOnly();
  assert.equal((await h.ui.readyForRun()).runId,'fixture-run');
});

test('changed source selection cannot attach a completed context',async()=>{
  const h=harness();await h.ui.prepareOnly();
  h.el('contextDays').value='60';
  await assert.rejects(h.ui.readyForRun(),/Prepare selected data/);
  h.el('contextSetup').listeners.input();
  assert.equal(h.storage.size,0);
});
