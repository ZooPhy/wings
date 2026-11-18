'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const m=require('../scripts/report/phylogeography-movie.js');
function large(){
 const start=Date.parse('2025-01-01T00:00:00Z');
 const jumps=Array.from({length:1000},(_,i)=>({branch:'tip',date:new Date(start+(i+1)*1000).toISOString(),from:i%2?'B':'A',to:i%2?'A':'B'}));
 return {schema:m.SCHEMA,title:'Large validation fixture',synthetic:true,
  provenance:{method:'Synthetic validation only',inference:'synthetic',uncertainty:'conditional-on-fixed-tree'},
  locations:[{id:'A',label:'A',lat:0,lon:0},{id:'B',label:'B',lat:1,lon:1}],
  segments:[{id:'HA',nodes:[{id:'root',parent:null,date:'2025-01-01'},{id:'tip',parent:'root',date:'2025-02-01',observed_state:'A'}],
   histories:Array.from({length:501},(_,i)=>({id:String(i),root_state:'A',jumps:i===0?[]:jumps}))}]};
}
test('offline checks preserve all 501000 events and zero-jump draws; browser limit remains',()=>{
 const d=large();d.segments[0].histories.push({id:'last',root_state:'A',jumps:d.segments[0].histories[1].jumps});
 const before=JSON.stringify(d);
 assert.throws(()=>m.validate(d),/500,000-event/);
 const result=m.validateForAnalysis(d);
 assert.equal(result.event_count,501000);
 assert.equal(result.segments[0].history_count,502);
 assert.equal(JSON.stringify(d),before);
});
test('invalid last draw is still rejected after passing the browser event limit',()=>{
 const d=large();
 d.segments[0].histories.push({id:'bad',root_state:'A',jumps:[{branch:'tip',date:'2025-01-10',from:'B',to:'A'}]});
 assert.throws(()=>m.validateForAnalysis(d),/Discontinuous/);
});
test('offline checks reject duplicate IDs, weights, bad dates and observed-state mismatch',()=>{
 for(const mutate of [d=>d.segments[0].histories[1].id='0',d=>d.segments[0].histories[1].weight=2,
  d=>d.segments[0].nodes[1].date='2024-01-01',d=>d.segments[0].nodes[1].observed_state='B']){
  const d=large();d.segments[0].histories=d.segments[0].histories.slice(0,2);mutate(d);
  assert.throws(()=>m.validateForAnalysis(d));
 }
});
test('offline validation is not exposed in browser API',()=>{
 const ctx={};vm.runInNewContext(fs.readFileSync(require.resolve('../scripts/report/phylogeography-movie.js'),'utf8'),ctx);
 assert.equal(typeof ctx.WINGS_PHYLOGEOGRAPHY_MOVIE.validate,'function');
 assert.equal(ctx.WINGS_PHYLOGEOGRAPHY_MOVIE.validateForAnalysis,undefined);
});
