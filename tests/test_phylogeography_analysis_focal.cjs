'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const m=require('../scripts/report/phylogeography-movie.js');
function fixture(){return {
 schema:m.SCHEMA,title:'Study ancestry regression',synthetic:true,
 provenance:{method:'Synthetic fixture',inference:'synthetic',uncertainty:'conditional-on-fixed-tree'},
 locations:[{id:'A',label:'A',lat:0,lon:0},{id:'B',label:'B',lat:1,lon:1}],
 segments:[{id:'HA',focal_sample_ids:['W1','W2'],nodes:[
  {id:'r',parent:null,date:'2020-01-01'},
  {id:'s',parent:'r',date:'2022-01-01'},
  {id:'a',parent:'s',date:'2024-01-01',sample_id:'W1',observed_state:'A'},
  {id:'b',parent:'s',date:'2024-01-01',sample_id:'W2',observed_state:'B'},
  {id:'ref',parent:'r',date:'2024-01-01',observed_state:'B'}],histories:[
  {id:'1',root_state:'A',jumps:[
   {branch:'s',date:'2021-01-01',from:'A',to:'B'},
   {branch:'ref',date:'2021-01-02',from:'A',to:'B'},
   {branch:'a',date:'2023-01-01',from:'B',to:'A'}]},
  {id:'2',root_state:'B',jumps:[{branch:'a',date:'2023-01-01',from:'B',to:'A'}]}
 ]}]};}
test('study MRCA, stem exclusion and entry counts are preserved',()=>{
 const raw=fixture(),full=m.validate(raw).segments[0],study=m.studyView(full);
 assert.equal(full.focal.mrca,'s');
 assert.deepEqual([...full.focal.branches].sort(),['a','b']);
 assert.equal(study.root.id,'s');
 assert.deepEqual([...study.nodes.keys()].sort(),['a','b','s']);
 assert.deepEqual(study.histories.map(h=>h.root_state),['B','B']);
 assert.deepEqual(m.summarize(full,full.end,'A').counts,[1,1]);
 assert.deepEqual(m.summarize(full,full.end,'B').counts,[0,0]);
 assert.deepEqual(m.summarize(study,study.end,'A').counts,[1,1]);
 assert.equal(m.routes(full,full.end).length,1);
 assert.deepEqual(m.probabilities(study,study.root,study.start).map(x=>[x.id,x.p]),[['B',1]]);
 assert.equal(m.validateForAnalysis(raw).event_count,4);
 assert.equal(raw.segments[0].histories[0].jumps.length,3);
});
test('offline validation retains focal cohort checks',()=>{
 for(const ids of [['W1','W1'],['W1','missing'],['W1']]){
  const raw=fixture();raw.segments[0].focal_sample_ids=ids;
  assert.throws(()=>m.validateForAnalysis(raw),/focal|Focal/);
 }
});
test('focal scope is inferred from study labels when not explicitly declared',()=>{
 const raw=fixture();delete raw.segments[0].focal_sample_ids;
 assert.equal(m.validate(raw).segments[0].focal.mrca,'s');
 assert.equal(m.validateForAnalysis(raw).event_count,4);
});
