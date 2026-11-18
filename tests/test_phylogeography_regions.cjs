const test=require('node:test'),assert=require('node:assert/strict');
require('./test_phylogeography_study_locations.cjs');
const api=require('../scripts/report/phylogeography-results.js');
require('../scripts/report/map-boundaries.js');
const studyPlan=(locations,expanded=new Set(),detail=false)=>api.groupPlan(locations,expanded,detail,undefined,new Set(['USA:KY']));
const locations=[['USA:KY','Kentucky',-85,38],['USA:OH','Ohio',-83,40],['USA:IN','Indiana',-86,40],['FRA:FRA','France',2,46],['DEU:DEU','Germany',10,51],['CAN:ON','Ontario',-85,50],['CAN:QC','Quebec',-71,53]].map(([id,label,lon,lat])=>({id,label,lon,lat}));
function fixture(method='fast'){
 const nodes=[{id:'r',parent:null,date:'2020-01-01'},...['a','b'].map(id=>({id,parent:'r',date:'2025-01-01',sample_id:id,observed_state:'USA:KY'}))];
 const histories=[['USA:OH','USA:IN'],['USA:IN','USA:OH'],['FRA:FRA','DEU:DEU'],['USA:KY',null]].map(([root,next],i)=>({id:String(i),root_state:root,jumps:next?['a','b'].flatMap(branch=>[{branch,date:'2022-01-01',from:root,to:next},{branch,date:'2023-01-01',from:next,to:'USA:KY'}]):[]}));
 const draws=histories.map((history,i)=>({id:String(i),history,chain:i<2?1:2,state:i%2+1}));
 if(method==='beast')draws.forEach((d,i)=>{d.nodes=structuredClone(nodes);d.nodes[0].date=i%2?'2021-01-01':'2020-01-01';d.focal_mrca='r';});
 return {status:'passed',method,nodes,draws,locations,focal_mrca:'r',focal_sample_ids:['a','b'],prior:{family:'gamma',shape:1,rate:1},tmrca:{median:'2020-01-01',hpd95:null}};
}
test('regional catalog covers US states including Kentucky within South',()=>{
 const regions=global.WINGS_MAP_BOUNDARIES.regions.filter(r=>r.country==='USA');assert.equal(regions.length,51);
 for(const r of regions)assert.match(api.locationRegion({id:'USA:'+r.code,label:r.name}),/^group:US-/);
 assert.equal(api.locationRegion(locations[0]),'group:US-South');assert.equal(api.locationRegion(locations[1]),'group:US-Midwest');
 assert.equal(api.locationRegion({id:'USA:USA',label:'United States'}),null);
});
test('international regions are explicit; unsupported locations are retained separately',()=>{
 assert.equal(api.locationRegion(locations[3]),'group:Europe');assert.equal(api.locationRegion(locations[5]),'group:Northern America');
 assert.equal(api.locationRegion({id:'MEX:MEX'}),'group:Latin America and the Caribbean');assert.equal(api.locationRegion({id:'RUS:RUS'}),'group:Europe');assert.equal(api.locationRegion({id:'TUR:TUR'}),'group:Asia');
 for(const c of global.WINGS_MAP_BOUNDARIES.countries)assert.ok(api.locationRegion({id:c.country+':'+c.country}),c.country);
 const unknown={id:'XXX:mystery',label:'Unclassified',lon:10,lat:10};const p=studyPlan([unknown]);assert.equal(p.assignment.get(unknown.id),unknown.id);assert.equal(p.visible.size,1);
});
test('within-region jumps disappear, Kentucky entry histories stay exactly unchanged',()=>{
 const raw=fixture(),before=JSON.stringify(raw),plan=studyPlan(locations),grouped=api.projectDataset(raw,plan);
 assert.equal(JSON.stringify(raw),before);assert.deepEqual(grouped.prior,raw.prior);assert.deepEqual(grouped.tmrca,raw.tmrca);
 assert.deepEqual(grouped.draws.map(d=>d.history.jumps.length),[2,2,2,0]);
 assert.deepEqual(grouped.draws.map(d=>d.history.jumps.filter(j=>j.to==='USA:KY').length),raw.draws.map(d=>d.history.jumps.filter(j=>j.to==='USA:KY').length));
 assert.ok(grouped.draws.every(d=>d.history.jumps.every(j=>j.from!==j.to)));
 const p=api.prepare(grouped);assert.deepEqual(p.stats.get('r').states,{'group:US-Midwest':.5,'group:Europe':.25,'USA:KY':.25});
 for(const s of p.stats.values())assert.equal(Object.values(s.states).reduce((a,b)=>a+b,0),1);
});
test('chord, timeline and regional entry card share draw-level counts including zeros',()=>{
 const p=api.prepare(api.projectDataset(fixture(),studyPlan(locations))),time=Date.parse('2025-01-01');
 const flows=api.flow(p,time);assert.equal(flows.reduce((a,b)=>a+b.mean,0),1.5);
 const mid=flows.find(f=>f.from==='group:US-Midwest');assert.deepEqual(api.pairSummary(p,mid.pair,time),{mean:1,low:0,high:2,pAny:.5});
 assert.deepEqual(api.cumulative(p,'USA:KY',[time])[0],{time,mean:1.5,low:0,high:2});
 assert.deepEqual(p.data.entries['USA:KY'],{mean:1.5,interval95:[0,2],zero_probability:.25,constant_sample:false});
});
test('group intervals are calculated per history, not by adding member intervals',()=>{
 const raw={locations:[{id:'A'},{id:'B'},{id:'X'}],draws:[{history:{jumps:[{from:'X',to:'A'}]}},{history:{jumps:[{from:'X',to:'B'}]}},{history:{jumps:[{from:'X',to:'A'},{from:'A',to:'B'}]}}]};
 const e=api.groupedEntry(raw,['A','B']);assert.equal(e.mean,1);assert.deepEqual(e.interval95,[1,1]);assert.equal(e.zero_probability,0);
 assert.equal(api.groupedEntry(raw,['absent']),null);
});
test('expansion restores constituent states; full detail recovers all original histories',()=>{
 const raw=fixture(),expanded=api.projectDataset(raw,studyPlan(locations,new Set(['group:US-Midwest'])));
 assert.equal(expanded.draws[0].history.jumps.length,4);assert.equal(expanded.draws[2].history.jumps.length,2);
 const detailed=api.projectDataset(raw,studyPlan(locations,new Set(),true));assert.deepEqual(detailed.draws.map(d=>d.history),raw.draws.map(d=>d.history));
 assert.deepEqual(detailed.entries,api.entrySummaries(raw.draws,locations));
});
test('BEAST grouping retains each tree date, chain identity and equal chain weights',()=>{
 const raw=fixture('beast'),grouped=api.projectDataset(raw,studyPlan(locations));const a=api.prepare(raw),b=api.prepare(grouped);
 assert.deepEqual(a.stats.get('r').interval,b.stats.get('r').interval);assert.equal(a.stats.get('r').median,b.stats.get('r').median);
 assert.deepEqual(grouped.draws.map(d=>[d.chain,d.state,d.nodes[0].date]),raw.draws.map(d=>[d.chain,d.state,d.nodes[0].date]));
});
test('invalid original transitions cannot be concealed by collapsing their region',()=>{
 const raw=fixture();raw.draws[0].history.jumps[0].from='USA:IN';raw.draws[0].history.jumps[0].to='USA:OH';
 assert.throws(()=>api.projectDataset(raw,studyPlan(locations)),/Broken geographic history/);
});
