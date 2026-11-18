'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const m=require('../scripts/report/phylogeography-movie.js');
const clone=x=>JSON.parse(JSON.stringify(x));
function fixture(){return {schema:m.SCHEMA,title:'Test histories',synthetic:false,
  provenance:{method:'Test Bayesian histories',inference:'bayesian',uncertainty:'conditional-on-fixed-tree'},
  locations:[{id:'A',label:'A',lat:35,lon:-80},{id:'B',label:'B',lat:40,lon:-85}],
  segments:[{id:'HA',nodes:[{id:'root',parent:null,date:'2025-01-01'},{id:'tip',parent:'root',date:'2025-04-01',observed_state:'B'}],histories:[
    {id:'zero',root_state:'B',jumps:[]},
    {id:'one',root_state:'A',jumps:[{branch:'tip',date:'2025-02-01',from:'A',to:'B'}]},
    {id:'two',root_state:'A',jumps:[{branch:'tip',date:'2025-01-15',from:'A',to:'B'},{branch:'tip',date:'2025-02-01',from:'B',to:'A'},{branch:'tip',date:'2025-03-01',from:'A',to:'B'}]}
  ]}]};}
test('zero-event histories stay in the posterior and reversals count separately',()=>{
  const s=m.validate(fixture()).segments[0],q=m.summarize(s,s.end,'B');
  assert.deepEqual(q.counts,[0,1,2]);assert.equal(q.mean,1);assert.equal(q.low,0);assert.equal(q.high,2);
  assert.equal(m.summarize(s,Date.parse('2025-02-15'),'B').mean,2/3);
  assert.deepEqual(m.summarize(s,s.start,'B').counts,[0,0,0]);
});
test('sampled history uses its own counts and summary probabilities integrate draws',()=>{
  const s=m.validate(fixture()).segments[0];assert.equal(m.summarize(s,s.end,'B',2).mean,2);
  assert.equal(m.probabilities(s,s.root,s.start)[0].p,2/3);
  assert.equal(m.probabilities(s,s.nodes.get('tip'),s.end)[0].p,1);
  const rs=m.routes(s,s.end);assert.equal(rs.find(r=>r.to==='B').n,1);assert.equal(rs.find(r=>r.to==='A').n,1/3);
});
test('synthetic example validates and segment counts are distinct',()=>{
  const d=m.exampleData(),model=m.validate(d);assert.equal(d.synthetic,true);
  assert.deepEqual(model.segments.map(s=>m.summarize(s,s.end,'KY').mean),[2.25,2.6]);
});
test('rejects contradictory histories, unknown states and out-of-branch times',()=>{
  for(const mutate of [
    d=>d.segments[0].histories[1].jumps[0].from='B',
    d=>d.segments[0].histories[1].jumps[0].to='X',
    d=>d.segments[0].histories[1].jumps[0].date='2024-12-31',
    d=>d.segments[0].histories[1].jumps[0].date='2025-04-02',
    d=>d.segments[0].histories[1].jumps[0].date='2025-02-30',
    d=>d.segments[0].nodes[1].observed_state='A',
    d=>d.segments[0].histories.push(clone(d.segments[0].histories[0])),
    d=>d.segments[0].histories[0].weight=.5,
    d=>d.segments[0].nodes[1].parent='missing',
    d=>d.locations[0].lat=null,
    d=>d.locations[0].lon=NaN,
    d=>d.provenance.uncertainty='joint-tree-posterior',
    d=>delete d.synthetic,
  ]){const d=fixture();mutate(d);assert.throws(()=>m.validate(d));}
});
test('rejects detached cycles and duplicate node IDs',()=>{
  const d=fixture();d.segments[0].nodes.push({id:'x',parent:'y',date:'2025-01-01'},{id:'y',parent:'x',date:'2025-01-01'});assert.throws(()=>m.validate(d),/disconnected|cyclic/);
  const b=fixture();b.segments[0].nodes.push(clone(b.segments[0].nodes[1]));assert.throws(()=>m.validate(b),/Duplicate node/);
});
test('a jump exactly at the child time is included, at the parent time rejected',()=>{
  const d=fixture();d.segments[0].histories[1].jumps[0].date='2025-04-01';assert.doesNotThrow(()=>m.validate(d));
  d.segments[0].histories[1].jumps[0].date='2025-01-01';assert.throws(()=>m.validate(d),/branch interval/);
});
