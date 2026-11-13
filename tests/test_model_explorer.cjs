'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const api=require('../scripts/report/concordance-model-explorer.js');
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/concordance_model_explorer.json'),'utf8'));
const copy=()=>structuredClone(fixture);
test('OLS agrees with NumPy across every stage and both terminal models',()=>{
  const columns=['temporal_days','geographic_km'];
  for(const [code,name] of [['baseline',null],['host','same_host'],['seasonal','seasonal_profile_distance'],['weather','environmental_distance']]){
    if(name)columns.push(name);const fit=api.fit(fixture.pairs,columns);assert.equal(fit.status,'READY');assert.ok(Math.abs(fit.r2-fixture.expected_r2[code])<1e-12);
  }
  const fit=api.fit(fixture.pairs,['temporal_days','geographic_km','same_host','seasonal_profile_distance','migration_context_distance']);assert.ok(Math.abs(fit.r2-fixture.expected_r2.migration)<1e-12);
});
test('optional per-comparison complete-case paths do not mix cohorts and never require weather for migration',async()=>{
  const input=copy();input.pairs[0].environmental_distance=null;
  const before=JSON.stringify(input),result=await api.analyze(input,{cohort_mode:'per-comparison',factors:['host','seasonal','weather','migration'],permutations:0});
  const weather=result.results.filter(r=>r.segment==='HA'&&r.path==='weather'),migration=result.results.filter(r=>r.segment==='HA'&&r.path==='migration');
  assert.ok(weather.every(r=>r.n_pairs===65));assert.ok(migration.every(r=>r.n_pairs===66));assert.equal(JSON.stringify(input),before);
  assert.ok(result.results.every(r=>r.permutation_p===null&&r.fdr_q===null));
});
test('each factor compares its own reduced and full models on matching eligible pairs',async()=>{
  const result=await api.analyze(copy(),{factors:['host','seasonal','weather','migration'],permutations:0});
  const expected={host:['baseline','host'],seasonal:['host','seasonal'],weather:['seasonal','weather'],migration:['seasonal','migration']};
  for(const [path,stages] of Object.entries(expected)){
    const rows=result.results.filter(r=>r.segment==='HA'&&r.path===path);
    assert.equal(rows.length,2);assert.deepEqual(rows.map(r=>r.comparison_role),['starting','added']);
    assert.deepEqual(rows.map(r=>r.n_pairs),[66,66]);assert.deepEqual(rows[0].eligible_sample_ids,rows[1].eligible_sample_ids);
    for(let i=0;i<2;i++)assert.ok(Math.abs(rows[i].r2-fixture.expected_r2[stages[i]])<1e-12);
    assert.ok(Math.abs(rows[1].delta_r2-(fixture.expected_r2[stages[1]]-fixture.expected_r2[stages[0]]))<1e-12);
  }
});
test('host and seasonal fits and statistical support do not depend on weather or migration availability',async()=>{
  const input=copy();
  for(const row of input.pairs){
    if([row.sample_a,row.sample_b].includes('S00'))row.environmental_distance=null;
    if([row.sample_a,row.sample_b].includes('S01'))row.migration_context_distance=null;
  }
  input.pairs.push(...input.pairs.map(r=>({...r,segment:'NP'})));
  const alone=await api.analyze(input,{cohort_mode:'per-comparison',factors:['host','seasonal'],permutations:19,seed:17});
  const all=await api.analyze(input,{cohort_mode:'per-comparison',factors:['host','seasonal','weather','migration'],permutations:19,seed:17});
  assert.deepEqual(all.results.filter(r=>['host','seasonal'].includes(r.path)),alone.results);
  for(const path of ['host','seasonal'])assert.ok(all.results.filter(r=>r.segment==='HA'&&r.path===path).every(r=>r.n_samples===12&&r.n_pairs===66));
  for(const path of ['weather','migration'])assert.ok(all.results.filter(r=>r.segment==='HA'&&r.path===path).every(r=>r.n_samples===11&&r.n_pairs===55));
  const missing=copy();missing.pairs.forEach(r=>r.seasonal_profile_distance=null);
  const withoutSeasonal=await api.analyze(missing,{cohort_mode:'per-comparison',factors:['host'],permutations:0});
  const withSeasonal=await api.analyze(missing,{cohort_mode:'per-comparison',factors:['host','seasonal'],permutations:0});
  assert.deepEqual(withSeasonal.results.filter(r=>r.path==='host'),withoutSeasonal.results);
});
test('unchecked starting factors are excluded and no factors gives one baseline model',async()=>{
  const result=await api.analyze(copy(),{factors:['seasonal','weather'],permutations:0});
  const rows=result.results.filter(r=>r.segment==='HA');
  assert.deepEqual(rows.map(r=>r.predictors),[
    ['temporal_days','geographic_km'],['temporal_days','geographic_km','seasonal_profile_distance'],
    ['temporal_days','geographic_km','seasonal_profile_distance'],['temporal_days','geographic_km','seasonal_profile_distance','environmental_distance']]);
  const baseline=await api.analyze(copy(),{factors:[],permutations:0});
  assert.equal(baseline.results.filter(r=>r.segment==='HA').length,1);
  assert.equal(baseline.results[0].path,'baseline');
});
test('sample inclusion is applied before fitting and too few samples have no fitted value',async()=>{
  const result=await api.analyze(copy(),{samples:['S00','S01','S02'],factors:['host'],permutations:0});
  const rows=result.results.filter(r=>r.segment==='HA');assert.ok(rows.every(r=>r.n_samples===3&&r.n_pairs===3));assert.ok(rows.every(r=>r.status==='INSUFFICIENT_UNIQUE_SAMPLES'&&r.r2===null));
});
test('constant, dependent, and constant-response fits remain unavailable',()=>{
  let rows=copy().pairs;rows.forEach(r=>r.same_host=1);assert.equal(api.fit(rows,['temporal_days','same_host']).status,'INSUFFICIENT_PREDICTOR_VARIATION');
  rows=copy().pairs;rows.forEach(r=>r.geographic_km=r.temporal_days*2);assert.equal(api.fit(rows,['temporal_days','geographic_km']).status,'INSUFFICIENT_INDEPENDENT_VARIATION');
  rows=copy().pairs;rows.forEach(r=>r.patristic_distance=1);assert.equal(api.fit(rows,['temporal_days']).status,'CONSTANT_GENETIC_DISTANCE');
});
test('migration shared contexts suppress inference; too few settings suppress its terminal fit',async()=>{
  let input=copy();input.sample_features[1].migration_context_key=input.sample_features[0].migration_context_key;
  let result=await api.analyze(input,{factors:['migration'],permutations:19});let row=result.results.find(r=>r.segment==='HA'&&r.code==='migration');
  assert.equal(row.status,'READY');assert.equal(row.n_migration_contexts,11);assert.equal(row.permutation_p,null);assert.match(row.descriptive_reason,/share migration/);
  input=copy();input.sample_features.forEach(s=>s.migration_context_key='US-AZ|2025-10-01');result=await api.analyze(input,{factors:['migration'],permutations:0});row=result.results.find(r=>r.segment==='HA'&&r.code==='migration');assert.equal(row.status,'INSUFFICIENT_MIGRATION_CONTEXTS');assert.equal(row.r2,null);
});
test('sample-label inference is reproducible and FDR is separate by path and step',async()=>{
  const a=await api.analyze(copy(),{factors:['host'],permutations:19,seed:17}),b=await api.analyze(copy(),{factors:['host'],permutations:19,seed:17});assert.deepEqual(a,b);
  const r=a.results.find(r=>r.segment==='HA'&&r.code==='host');assert.equal(r.permutations_valid,19);assert.ok(r.permutation_p>=.05&&r.permutation_p<=1);assert.equal(r.fdr_q,r.permutation_p);
  const rows=[{path:'weather',code:'host',permutation_p:.01},{path:'weather',code:'host',permutation_p:.1},{path:'migration',code:'host',permutation_p:.001},{path:'weather',code:'seasonal',permutation_p:.03}];api.adjust(rows);assert.equal(rows[0].fdr_q,.02);assert.equal(rows[2].fdr_q,.001);assert.equal(rows[3].fdr_q,.03);
});
test('incomplete dyads never become zero residuals and obsolete calculations cancel',async()=>{
  const input=copy();input.pairs.pop();const result=await api.analyze(input,{factors:['host'],permutations:19});const row=result.results.find(r=>r.segment==='HA'&&r.code==='host');assert.ok(row.permutations_valid<19);
  await assert.rejects(api.analyze(copy(),{permutations:19},{alive:()=>false}),/CANCELLED/);
});
test('malformed identities, predictors, and duplicate pairs are rejected',()=>{
  let input=copy();input.pairs.push({...input.pairs[0]});assert.throws(()=>api.validateInputs(input),/Duplicate/);
  input=copy();input.pairs[0].sample_a='missing';assert.throws(()=>api.validateInputs(input),/identity/);
  input=copy();input.pairs[0].temporal_days='1';assert.throws(()=>api.validateInputs(input),/predictor/);
  input=copy();input.pairs[0].patristic_distance=-1;assert.throws(()=>api.validateInputs(input),/genetic/);
});

class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.attrs={};this.events={};this.style={};this.className='';this.textContent='';this.value='';this.classList={add(){}};}
  append(...nodes){this.children.push(...nodes);if(this.tagName==='select'&&this.children.length&&this.value==='')this.value=this.children[0].value;}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  addEventListener(k,fn){this.events[k]=fn;}
}
const find=(node,predicate)=>predicate(node)?node:node.children.map(n=>find(n,predicate)).find(Boolean);
const cls=(node,name)=>find(node,n=>n.className.split(' ').includes(name));
test('dashboard filters trigger a refit, preserve the source, and invalidate prior display',async()=>{
  const prior=global.document;global.document={createElement:t=>new Element(t),createElementNS:(_ns,t)=>new Element(t)};
  let controller;
  try{
    const f=copy(),samples=f.sample_features.map((s,i)=>({...s,host:i%2?'A':'B',country:'USA',state:'Arizona',collection_date:'2025-10-01'}));
    const explorer={payload:{samples,genomic_ecological_concordance:{models:[],readiness:{minimum_unique_samples:8},interactive_inputs:f}}};
    const before=JSON.stringify(explorer.payload),root=new Element();controller=api.mount(explorer,root);
    for(let i=0;i<100&&!controller.getResult();i++)await new Promise(r=>setTimeout(r,5));
    assert.ok(controller.getResult());assert.equal(controller.getResult().scope,'browser-refit');
    const controls=cls(root,'wme-controls').children,host=controls[1].children[1],support=controls[5].children[1];
    host.value='A';host.events.change();assert.match(cls(root,'wme-status').textContent,/Selection changed/);assert.equal(cls(root,'wme-chart').children.length,0);
    support.value='0';support.events.change();cls(root,'wme-primary').events.click();
    for(let i=0;i<100&&!cls(root,'wme-status').textContent.startsWith('Comparison updated');i++)await new Promise(r=>setTimeout(r,5));
    const rows=controller.getResult().results.filter(r=>r.segment==='HA');assert.ok(rows.every(r=>r.n_samples===6&&r.status==='INSUFFICIENT_UNIQUE_SAMPLES'));
    assert.equal(JSON.stringify(explorer.payload),before);
  }finally{controller?.cancel();if(prior===undefined)delete global.document;else global.document=prior;}
});
test('legacy summaries show separate saved comparisons and disable unsupported cohort controls',()=>{
  const prior=global.document;global.document={createElement:t=>new Element(t),createElementNS:(_ns,t)=>new Element(t)};
  try{
    const root=new Element(),explorer={payload:{samples:fixture.sample_features,genomic_ecological_concordance:{models:[{segment:'HA',comparison:'host_vs_baseline',status:'READY',reduced_r2:.1,full_r2:.3,delta_r2:.2,n_samples:12,n_pairs:66,permutation_p:.01,fdr_q:.01}],readiness:{minimum_unique_samples:8}}}};
    const controller=api.mount(explorer,root);assert.equal(controller.getResult().scope,'saved-results');assert.equal(cls(root,'wme-primary').disabled,true);assert.match(cls(root,'wme-status').textContent,/Saved comparisons shown/);
  }finally{if(prior===undefined)delete global.document;else global.document=prior;}
});

test('shared eligibility defaults to identical pairs and samples across all selected models',async()=>{
  const input=copy();
  for(const r of input.pairs){
    if([r.sample_a,r.sample_b].includes('S00'))r.environmental_distance=null;
    if([r.sample_a,r.sample_b].includes('S01'))r.migration_context_distance=null;
  }
  // A missing pair, as well as missing samples, must restrict every model.
  input.pairs.find(r=>r.sample_a==='S02'&&r.sample_b==='S03').environmental_distance=null;
  input.pairs.push(...copy().pairs.map(r=>({...r,segment:'NP'})));
  const original=JSON.stringify(input),factors=['host','seasonal','weather','migration'];
  const result=await api.analyze(input,{factors,permutations:0});
  assert.equal(result.options.cohort_mode,'shared');
  const keys=['temporal_days','geographic_km','same_host','seasonal_profile_distance','environmental_distance','migration_context_distance','patristic_distance'];
  for(const segment of ['HA','NP']){
    const expected=input.pairs.filter(r=>r.segment===segment&&keys.every(k=>Number.isFinite(r[k])));
    const ids=[...new Set(expected.flatMap(r=>[r.sample_a,r.sample_b]))].sort();
    const rows=result.results.filter(r=>r.segment===segment);assert.equal(rows.length,8);
    for(const r of rows){
      assert.equal(r.n_pairs,expected.length);assert.deepEqual([...r.eligible_sample_ids].sort(),ids);
      const fitted=api.fit(expected,r.predictors);assert.equal(r.status,fitted.status);
      assert.ok(Math.abs(r.r2-fitted.r2)<1e-12);
    }
    // Weather and Migration start from exactly the same model on the same data.
    assert.equal(rows.find(r=>r.path==='weather').r2,rows.find(r=>r.path==='migration').r2);
  }
  assert.equal(result.results.find(r=>r.segment==='HA').n_pairs,44);
  assert.equal(result.results.find(r=>r.segment==='NP').n_pairs,66);
  assert.equal(JSON.stringify(input),original);
  const fewer=await api.analyze(input,{factors:['host','seasonal'],permutations:0});
  assert.equal(fewer.results.find(r=>r.segment==='HA').n_samples,12);
  assert.equal(fewer.results.find(r=>r.segment==='HA').n_pairs,66);
  const empty=copy();empty.pairs.forEach(r=>r.environmental_distance=null);
  const none=await api.analyze(empty,{factors:['host','weather'],permutations:0});
  assert.ok(none.results.every(r=>r.n_samples===0&&r.n_pairs===0&&r.r2===null));
  await assert.rejects(api.analyze(copy(),{cohort_mode:'invalid'}),/eligibility mode/);
});
