'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const api=require('../scripts/report/genome-braid-clock.js');

function bins(year, peakWeek=10) {
  const out=[];
  let d=new Date(Date.UTC(year,0,1));
  for(let i=0;i<52;i++){
    const s=new Date(d); const e=new Date(d); e.setUTCDate(e.getUTCDate()+(i===51?8:6));
    if(i===51)e.setTime(Date.UTC(year,11,31));
    out.push({start:s.toISOString().slice(0,10),end:e.toISOString().slice(0,10),value:i===peakWeek?10:1});
    d.setUTCDate(d.getUTCDate()+7);
  }
  return out;
}
function profile(sampleId, host='TUVU', year=2025) {
  return {
    profile_id:`p-${sampleId}`, sample_id:sampleId,
    scope:{host,country:'US',state:'KY'}, baseline_kind:'reference_season',
    measure:'relative abundance', unit:'expected individuals',
    season_start:`${year}-01-01`, season_end:`${year}-12-31`, bins:bins(year),
    anchor:{earliest:`${year}-03-05`,latest:`${year}-03-11`,label:'Expected peak',basis:'fixture'},
    provenance:{source:'fixture',citation:'fixture citation',retrieved_on:'2026-09-30',method:'fixture'}
  };
}
function payload(profiles,status=[]) {return {schema_version:'wings.phenology.v1',synthetic:false,profiles,sample_status:status};}

test('sample-specific profile wins even when same host/state has another point profile',()=>{
  const p=api.validatePhenology(payload([profile('A'),profile('B')]));
  const r=api.clockRecord({sample_id:'B',host:'TUVU',country:'US',state:'KY',collection_date:'2025-04-15'},p);
  assert.equal(r.status,'AVAILABLE');
  assert.equal(r.profile.sample_id,'B');
});

test('missing-coordinate status is exposed instead of generic no-match',()=>{
  const p=api.validatePhenology(payload([], [{sample_id:'A',status:'MISSING_COORDINATES',reason:'Sample coordinates are required.'}]));
  const r=api.clockRecord({sample_id:'A',host:'TUVU',country:'US',state:'KY',collection_date:'2025-04-15'},p);
  assert.equal(r.status,'MISSING_COORDINATES');
  assert.match(api.lagText(r),/MISSING_COORDINATES|coordinates|available/i);
});

test('reference-season anchor uses nearest annual occurrence across year boundary',()=>{
  const p0=profile('A','TUVU',2025);
  p0.anchor={earliest:'2025-01-01',latest:'2025-01-07',label:'Expected peak',basis:'fixture'};
  const p=api.validatePhenology(payload([p0]));
  const r=api.clockRecord({sample_id:'A',host:'TUVU',country:'US',state:'KY',collection_date:'2025-12-29'},p);
  assert.equal(r.status,'AVAILABLE');
  assert.equal(r.anchor.year_shift,1);
  assert.ok(Math.abs(r.midpoint) < 10);
});


test('Genome workbench uses neutral div containers to avoid host section/aside layout rules',()=>{
  const fs=require('node:fs');
  const source=fs.readFileSync(require.resolve('../scripts/report/genome-braid-clock.js'),'utf8');
  assert.match(source,/wbc-workbench"><div class="wbc-card wbc-braid-card">/);
  assert.doesNotMatch(source,/wbc-workbench"><section class="wbc-card">/);
  assert.doesNotMatch(source,/<aside class="wbc-card wbc-focus">/);
});

test('Explorer tabs hoist Tree Studio launcher into the shared Genome region',()=>{
  const fs=require('node:fs');
  const path=require('node:path');
  const source=fs.readFileSync(path.join(__dirname,'../scripts/report/explorer-tabs.js'),'utf8');
  assert.match(source,/const placeTreeStudio = \(\) =>/);
  assert.match(source,/shared\.prepend\(launch\)/);
  assert.match(source,/launch\.hidden = active !== "genome"/);
  assert.match(source,/setTimeout\(placeTreeStudio, 0\)/);
});

test('Ecological timing is rendered as human-readable before-after language',()=>{
  assert.equal(api.lagText({status:'AVAILABLE',lower:-100,upper:-94}),'94–100 days before expected peak');
  assert.equal(api.lagText({status:'AVAILABLE',lower:94,upper:100}),'94–100 days after expected peak');
  assert.equal(api.lagText({status:'AVAILABLE',lower:-2,upper:3}),'Overlaps expected peak interval');
});
