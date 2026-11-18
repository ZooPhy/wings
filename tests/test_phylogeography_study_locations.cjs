'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const api=require('../scripts/report/phylogeography-results.js');
const locations=[['USA:KY','Kentucky'],['USA:OH','Ohio'],['USA:MI','Michigan'],['USA:IN','Indiana'],['FRA:FRA','France'],['DEU:DEU','Germany']].map(([id,label],i)=>({id,label,lat:i,lon:i}));
function data(states){const nodes=[{id:'r',parent:null,date:'2020-01-01'},...states.map((s,i)=>({id:'n'+i,sample_id:'s'+i,parent:'r',date:'2025-01-01',observed_state:s})),{id:'reference',parent:'r',date:'2025-01-01',observed_state:'USA:KY'}];return {locations,nodes,focal_sample_ids:states.map((_,i)=>'s'+i),draws:[]};}
function choices(raw,detail=false,previous=null){const cohort=api.studyLocationCounts(raw);const plan=api.groupPlan(locations,new Set(),detail,undefined,new Set(cohort.keys()));return {plan,...api.locationChoices(raw,[...plan.visible.values()],plan,previous)};}
test('Ohio cohort gets Ohio first; reference Kentucky belongs to U.S. South',()=>{
 const raw=data(['USA:OH','USA:OH']),before=JSON.stringify(raw),x=choices(raw);
 assert.equal(x.selected,'USA:OH');assert.equal(x.options[0].studyCount,2);
 assert.equal(x.plan.assignment.get('USA:KY'),'group:US-South');
 assert.equal(x.plan.visible.get('group:US-South').label,'U.S. South');
 assert.ok(!x.options.some(l=>l.label.includes('Kentucky')));
 assert.equal(x.plan.visible.get('group:US-Midwest').label,'U.S. Midwest (other locations)');
 assert.equal(JSON.stringify(raw),before);
});
test('multiple study locations stay separate and most sampled location is default',()=>{
 const x=choices(data(['USA:OH','USA:MI','USA:MI']));
 assert.equal(x.selected,'USA:MI');assert.deepEqual(x.options.filter(l=>l.studyCount).map(l=>[l.id,l.studyCount]),[['USA:MI',2],['USA:OH',1]]);
 assert.equal(x.plan.assignment.get('USA:OH'),'USA:OH');
 assert.equal(choices(data(['USA:OH','USA:MI'])).selected,'USA:MI');
});
test('Kentucky is separate only when it is a study location',()=>{
 const x=choices(data(['USA:KY']));assert.equal(x.selected,'USA:KY');assert.equal(x.options[0].label,'Kentucky');
});
test('non-US cohorts and reference context selections work',()=>{
 const raw=data(['FRA:FRA','FRA:FRA']),x=choices(raw);
 assert.equal(x.selected,'FRA:FRA');assert.equal(x.plan.assignment.get('DEU:DEU'),'group:Europe');
 assert.equal(x.plan.visible.get('group:Europe').label,'Europe (other locations)');
 assert.equal(choices(raw,false,'group:US-South').selected,'group:US-South');
 assert.equal(choices(raw,false,'not-present').selected,'FRA:FRA');
 assert.ok(choices(raw,true).options.some(l=>l.id==='USA:KY'&&!l.studyCount));
});
test('BEAST tree draws do not multiply sample counts and must agree on tip locations',()=>{
 const raw=data(['USA:OH','USA:MI']);const nodes=raw.nodes;delete raw.nodes;
 raw.draws=[{nodes},{nodes:structuredClone(nodes)}];
 assert.deepEqual([...api.studyLocationCounts(raw)],[['USA:OH',1],['USA:MI',1]]);
 raw.draws[1].nodes[1].observed_state='USA:KY';assert.throws(()=>api.studyLocationCounts(raw),/change across/);
});
test('missing, duplicate and unknown study metadata is rejected rather than defaulting to Kentucky',()=>{
 for(const mutate of [r=>r.focal_sample_ids=['missing'],r=>r.nodes[1].observed_state='unknown',r=>r.nodes.push({...r.nodes[1]}),r=>r.focal_sample_ids=['s0','s0']]){
  const raw=data(['USA:OH']);mutate(raw);assert.throws(()=>api.studyLocationCounts(raw));
 }
});
