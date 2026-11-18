/* Shared results for a fixed dated tree and checked BEAST dated-tree draws. */
(function(global){
'use strict';
const ms=s=>{const n=Date.parse(s);if(!Number.isFinite(n))throw Error('Invalid date');return n;};
const quantile=(a,p)=>{a=a.slice().sort((x,y)=>x-y);return a[Math.max(0,Math.ceil(p*a.length)-1)];};
function upper(a,x){let l=0,r=a.length;while(l<r){const m=(l+r)>>>1;if(a[m]<=x)l=m+1;else r=m;}return l;}
function validateModel(m){
 if(!m||m.schema!=='wings.phylogeography-results.v1'||!['fast','beast'].includes(m.default_method)||!Array.isArray(m.analyses)||!m.analyses.length)throw Error('Invalid results');
 if(new Set(m.analyses.map(r=>r.id)).size!==m.analyses.length||!m.analyses.some(r=>r.id===m.default_analysis))throw Error('Invalid analysis selection');
 return m;
}
function primaryAnalysisId(model,segment=model.default_analysis.split('/')[0]){
 return segment+'/balanced/replicate_1';
}
function referenceLabel(id){
 const [segment,strategy,replicate]=id.split('/');
 const name={balanced:'Location/time balanced',available:'Random eligible references',diversity:'Diversity-enriched'}[strategy]||strategy;
 return `${segment} · ${name} · Set ${replicate.replace('replicate_','')}`;
}
function indexDraw(d,locations){
 const by=new Map(d.nodes.map(n=>[n.id,n]));if(by.size!==d.nodes.length)throw Error('Duplicate nodes');
 const children=new Map(d.nodes.map(n=>[n.id,[]])),events=new Map(d.nodes.map(n=>[n.id,[]]));
 let root=null;d.nodes.forEach(n=>{ms(n.date);if(n.parent===null){if(root)throw Error('Multiple roots');root=n;}else{if(!by.has(n.parent)||ms(by.get(n.parent).date)>ms(n.date))throw Error('Invalid branch');children.get(n.parent).push(n.id);}});
 if(!root||root.id!==d.focal_mrca||!locations.has(d.history.root_state))throw Error('Missing ancestor or unknown root state');
 d.history.jumps.forEach(j=>{const n=by.get(j.branch);if(!n||n.parent===null||!locations.has(j.from)||!locations.has(j.to)||j.from===j.to||ms(j.date)<=ms(by.get(n.parent).date)||ms(j.date)>ms(n.date))throw Error('Invalid event');events.get(n.id).push(j);});
 events.forEach(a=>a.sort((a,b)=>ms(a.date)-ms(b.date)));
 const ends={},segments=[],seen=new Set(),order=[];
 function visit(id,start){if(seen.has(id))throw Error('Cycle');seen.add(id);order.push(id);const n=by.get(id);let state=start,t=n.parent===null?ms(n.date):ms(by.get(n.parent).date);
  events.get(id).forEach(j=>{if(j.from!==state)throw Error('Broken geographic history');segments.push({state,start:t,end:ms(j.date)});state=j.to;t=ms(j.date);});
  if(n.parent!==null)segments.push({state,start:t,end:ms(n.date)});
  if(n.observed_state&&n.observed_state!==state)throw Error('Observed state mismatch');ends[id]=state;
  children.get(id).forEach(child=>visit(child,state));
 }
 visit(root.id,d.history.root_state);if(seen.size!==by.size)throw Error('Disconnected tree');
 return {by,children,events,ends,segments,order};
}
function prepare(raw){
 if(raw.status!=='passed'||!['fast','beast'].includes(raw.method))throw Error('Method has not passed its checks');
 const data={...raw,draws:raw.draws.map(d=>({...d,nodes:d.nodes||raw.nodes,focal_mrca:d.focal_mrca||raw.focal_mrca}))};
 const locations=new Set(data.locations.map(l=>l.id));if(locations.size!==data.locations.length||!data.draws.length)throw Error('Invalid locations or missing histories');
 const stats=new Map(),pairs=new Map(),occupancy=new Map(data.locations.map(l=>[l.id,{starts:[],ends:[]}])) ,chains=new Map();
 let topology=null,min=Infinity,max=-Infinity;
 data.draws.forEach((d,i)=>{
  const view=indexDraw(d,locations),edges=d.nodes.map(n=>n.id+'|'+n.parent).sort().join(';');if(topology===null)topology=edges;if(topology!==edges)throw Error('Topology changed across draws');
  if(JSON.stringify(d.nodes.filter(n=>n.sample_id).map(n=>n.sample_id).sort())!==JSON.stringify(data.focal_sample_ids.slice().sort()))throw Error('WINGS sample set changed');
  if(data.method==='beast'){if(!chains.has(d.chain))chains.set(d.chain,new Set());if(chains.get(d.chain).has(d.state))throw Error('Repeated posterior tree');chains.get(d.chain).add(d.state);}
  min=Math.min(min,ms(view.by.get(d.focal_mrca).date));d.nodes.forEach(n=>{max=Math.max(max,ms(n.date));if(!stats.has(n.id))stats.set(n.id,{dates:[],states:{}});const s=stats.get(n.id);s.dates.push(ms(n.date));s.states[view.ends[n.id]]=(s.states[view.ends[n.id]]||0)+1;});
  view.segments.forEach(s=>{occupancy.get(s.state).starts.push(s.start);occupancy.get(s.state).ends.push(s.end);});
  d.history.jumps.forEach(j=>{const key=JSON.stringify([j.from,j.to]);if(!pairs.has(key))pairs.set(key,{from:j.from,to:j.to,times:[],byDraw:new Map()});const p=pairs.get(key);p.times.push(ms(j.date));if(!p.byDraw.has(i))p.byDraw.set(i,[]);p.byDraw.get(i).push(ms(j.date));});
 });
 if(data.method==='beast'&&(chains.size<2||new Set([...chains.values()].map(s=>s.size)).size!==1))throw Error('Unequal posterior chain weights');
 occupancy.forEach(o=>{o.starts.sort((a,b)=>a-b);o.ends.sort((a,b)=>a-b);});pairs.forEach(p=>{p.times.sort((a,b)=>a-b);p.byDraw.forEach(t=>t.sort((a,b)=>a-b));});
 const N=data.draws.length;stats.forEach(s=>{s.median=quantile(s.dates,.5);s.interval=[quantile(s.dates,.025),quantile(s.dates,.975)];Object.keys(s.states).forEach(k=>s.states[k]/=N);delete s.dates;});
 return {data,stats,pairs,occupancy,N,min,max,view:indexDraw(data.draws[0],locations)};
}
function pairSummary(pre,p,t){const counts=Array(pre.N).fill(0);p.byDraw.forEach((a,i)=>counts[i]=upper(a,t));return {mean:upper(p.times,t)/pre.N,low:quantile(counts,.025),high:quantile(counts,.975),pAny:counts.filter(x=>x>0).length/pre.N};}
function flow(pre,t){return [...pre.pairs.values()].map(p=>({from:p.from,to:p.to,mean:upper(p.times,t)/pre.N,pair:p})).filter(p=>p.mean>0);}
// One draw is a complete geographic reconstruction, possibly containing many jumps.
function displayFlows(pre,t,draw=null){
 if(!draw)return flow(pre,t);
 const pairs=new Map();draw.history.jumps.filter(j=>ms(j.date)<=t).forEach(j=>{const key=JSON.stringify([j.from,j.to]);if(!pairs.has(key))pairs.set(key,{from:j.from,to:j.to,mean:0});pairs.get(key).mean++;});
 return [...pairs.values()];
}
function mostProbableLocation(states){
 const ranked=Object.entries(states).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));
 if(!ranked.length)throw Error('No posterior location probabilities');
 const [id,probability]=ranked[0];return {id,probability,tied:ranked.filter(([,p])=>Math.abs(p-probability)<1e-12).map(([id])=>id)};
}
function cumulative(pre,target,times){
 const rows=times.map(()=>[]);
 pre.data.draws.forEach(d=>{const events=d.history.jumps.filter(j=>j.to===target).map(j=>ms(j.date)).sort((a,b)=>a-b);let n=0;times.forEach((t,i)=>{while(n<events.length&&events[n]<=t)n++;rows[i].push(n);});});
 return rows.map((a,i)=>({time:times[i],mean:a.reduce((s,x)=>s+x,0)/a.length,low:quantile(a,.025),high:quantile(a,.975)}));
}
// Display groups only. Census regions / UN M49; study locations stay separate.
const US_REGIONS={Northeast:'CT ME MA NH RI VT NJ NY PA',Midwest:'IN IL MI OH WI IA KS MN MO NE ND SD',South:'DE DC FL GA MD NC SC VA WV AL KY MS TN AR LA OK TX',West:'AZ CO ID MT NV NM UT WY AK CA HI OR WA'};
const REGION_INFO={
 'group:US-Northeast':['U.S. Northeast',-73.5,42.5], 'group:US-Midwest':['U.S. Midwest',-92,43],
 'group:US-South':['U.S. South',-86,33], 'group:US-West':['U.S. West',-115,41],
 'group:Northern America':['Northern America (outside U.S.)',-105,58],
 'group:Latin America and the Caribbean':['Latin America & Caribbean',-72,-10],
 'group:Europe':['Europe',15,53], 'group:Asia':['Asia',90,35],
 'group:Africa':['Africa',20,3], 'group:Oceania':['Oceania',145,-22], 'group:Antarctica':['Antarctica',0,-78]
};
const COUNTRY_REGIONS={"DZA":"Africa","EGY":"Africa","LBY":"Africa","MAR":"Africa","SDN":"Africa","TUN":"Africa","ESH":"Africa","IOT":"Africa","BDI":"Africa","COM":"Africa","DJI":"Africa","ERI":"Africa","ETH":"Africa","ATF":"Africa","KEN":"Africa","MDG":"Africa","MWI":"Africa","MUS":"Africa","MYT":"Africa","MOZ":"Africa","REU":"Africa","RWA":"Africa","SYC":"Africa","SOM":"Africa","SSD":"Africa","UGA":"Africa","TZA":"Africa","ZMB":"Africa","ZWE":"Africa","AGO":"Africa","CMR":"Africa","CAF":"Africa","TCD":"Africa","COG":"Africa","COD":"Africa","GNQ":"Africa","GAB":"Africa","STP":"Africa","BWA":"Africa","SWZ":"Africa","LSO":"Africa","NAM":"Africa","ZAF":"Africa","BEN":"Africa","BFA":"Africa","CPV":"Africa","CIV":"Africa","GMB":"Africa","GHA":"Africa","GIN":"Africa","GNB":"Africa","LBR":"Africa","MLI":"Africa","MRT":"Africa","NER":"Africa","NGA":"Africa","SHN":"Africa","SEN":"Africa","SLE":"Africa","TGO":"Africa","AIA":"Latin America and the Caribbean","ATG":"Latin America and the Caribbean","ABW":"Latin America and the Caribbean","BHS":"Latin America and the Caribbean","BRB":"Latin America and the Caribbean","BES":"Latin America and the Caribbean","VGB":"Latin America and the Caribbean","CYM":"Latin America and the Caribbean","CUB":"Latin America and the Caribbean","CUW":"Latin America and the Caribbean","DMA":"Latin America and the Caribbean","DOM":"Latin America and the Caribbean","GRD":"Latin America and the Caribbean","GLP":"Latin America and the Caribbean","HTI":"Latin America and the Caribbean","JAM":"Latin America and the Caribbean","MTQ":"Latin America and the Caribbean","MSR":"Latin America and the Caribbean","PRI":"Latin America and the Caribbean","BLM":"Latin America and the Caribbean","KNA":"Latin America and the Caribbean","LCA":"Latin America and the Caribbean","MAF":"Latin America and the Caribbean","VCT":"Latin America and the Caribbean","SXM":"Latin America and the Caribbean","TTO":"Latin America and the Caribbean","TCA":"Latin America and the Caribbean","VIR":"Latin America and the Caribbean","BLZ":"Latin America and the Caribbean","CRI":"Latin America and the Caribbean","SLV":"Latin America and the Caribbean","GTM":"Latin America and the Caribbean","HND":"Latin America and the Caribbean","MEX":"Latin America and the Caribbean","NIC":"Latin America and the Caribbean","PAN":"Latin America and the Caribbean","ARG":"Latin America and the Caribbean","BOL":"Latin America and the Caribbean","BVT":"Latin America and the Caribbean","BRA":"Latin America and the Caribbean","CHL":"Latin America and the Caribbean","COL":"Latin America and the Caribbean","ECU":"Latin America and the Caribbean","FLK":"Latin America and the Caribbean","GUF":"Latin America and the Caribbean","GUY":"Latin America and the Caribbean","PRY":"Latin America and the Caribbean","PER":"Latin America and the Caribbean","SGS":"Latin America and the Caribbean","SUR":"Latin America and the Caribbean","URY":"Latin America and the Caribbean","VEN":"Latin America and the Caribbean","BMU":"Northern America","CAN":"Northern America","GRL":"Northern America","SPM":"Northern America","USA":"Northern America","ATA":"Antarctica","KAZ":"Asia","KGZ":"Asia","TJK":"Asia","TKM":"Asia","UZB":"Asia","CHN":"Asia","HKG":"Asia","MAC":"Asia","PRK":"Asia","JPN":"Asia","MNG":"Asia","KOR":"Asia","BRN":"Asia","KHM":"Asia","IDN":"Asia","LAO":"Asia","MYS":"Asia","MMR":"Asia","PHL":"Asia","SGP":"Asia","THA":"Asia","TLS":"Asia","VNM":"Asia","AFG":"Asia","BGD":"Asia","BTN":"Asia","IND":"Asia","IRN":"Asia","MDV":"Asia","NPL":"Asia","PAK":"Asia","LKA":"Asia","ARM":"Asia","AZE":"Asia","BHR":"Asia","CYP":"Asia","GEO":"Asia","IRQ":"Asia","ISR":"Asia","JOR":"Asia","KWT":"Asia","LBN":"Asia","OMN":"Asia","QAT":"Asia","SAU":"Asia","PSE":"Asia","SYR":"Asia","TUR":"Asia","ARE":"Asia","YEM":"Asia","BLR":"Europe","BGR":"Europe","CZE":"Europe","HUN":"Europe","POL":"Europe","MDA":"Europe","ROU":"Europe","RUS":"Europe","SVK":"Europe","UKR":"Europe","ALA":"Europe","DNK":"Europe","EST":"Europe","FRO":"Europe","FIN":"Europe","GGY":"Europe","ISL":"Europe","IRL":"Europe","IMN":"Europe","JEY":"Europe","LVA":"Europe","LTU":"Europe","NOR":"Europe","SJM":"Europe","SWE":"Europe","GBR":"Europe","ALB":"Europe","AND":"Europe","BIH":"Europe","HRV":"Europe","GIB":"Europe","GRC":"Europe","VAT":"Europe","ITA":"Europe","MLT":"Europe","MNE":"Europe","MKD":"Europe","PRT":"Europe","SMR":"Europe","SRB":"Europe","SVN":"Europe","ESP":"Europe","AUT":"Europe","BEL":"Europe","FRA":"Europe","DEU":"Europe","LIE":"Europe","LUX":"Europe","MCO":"Europe","NLD":"Europe","CHE":"Europe","AUS":"Oceania","CXR":"Oceania","CCK":"Oceania","HMD":"Oceania","NZL":"Oceania","NFK":"Oceania","FJI":"Oceania","NCL":"Oceania","PNG":"Oceania","SLB":"Oceania","VUT":"Oceania","GUM":"Oceania","KIR":"Oceania","MHL":"Oceania","FSM":"Oceania","NRU":"Oceania","MNP":"Oceania","PLW":"Oceania","UMI":"Oceania","ASM":"Oceania","COK":"Oceania","PYF":"Oceania","NIU":"Oceania","PCN":"Oceania","WSM":"Oceania","TKL":"Oceania","TON":"Oceania","TUV":"Oceania","WLF":"Oceania"};
const COUNTRY_ALPHA2={"DZ":"DZA","EG":"EGY","LY":"LBY","MA":"MAR","SD":"SDN","TN":"TUN","EH":"ESH","IO":"IOT","BI":"BDI","KM":"COM","DJ":"DJI","ER":"ERI","ET":"ETH","TF":"ATF","KE":"KEN","MG":"MDG","MW":"MWI","MU":"MUS","YT":"MYT","MZ":"MOZ","RE":"REU","RW":"RWA","SC":"SYC","SO":"SOM","SS":"SSD","UG":"UGA","TZ":"TZA","ZM":"ZMB","ZW":"ZWE","AO":"AGO","CM":"CMR","CF":"CAF","TD":"TCD","CG":"COG","CD":"COD","GQ":"GNQ","GA":"GAB","ST":"STP","BW":"BWA","SZ":"SWZ","LS":"LSO","NA":"NAM","ZA":"ZAF","BJ":"BEN","BF":"BFA","CV":"CPV","CI":"CIV","GM":"GMB","GH":"GHA","GN":"GIN","GW":"GNB","LR":"LBR","ML":"MLI","MR":"MRT","NE":"NER","NG":"NGA","SH":"SHN","SN":"SEN","SL":"SLE","TG":"TGO","AI":"AIA","AG":"ATG","AW":"ABW","BS":"BHS","BB":"BRB","BQ":"BES","VG":"VGB","KY":"CYM","CU":"CUB","CW":"CUW","DM":"DMA","DO":"DOM","GD":"GRD","GP":"GLP","HT":"HTI","JM":"JAM","MQ":"MTQ","MS":"MSR","PR":"PRI","BL":"BLM","KN":"KNA","LC":"LCA","MF":"MAF","VC":"VCT","SX":"SXM","TT":"TTO","TC":"TCA","VI":"VIR","BZ":"BLZ","CR":"CRI","SV":"SLV","GT":"GTM","HN":"HND","MX":"MEX","NI":"NIC","PA":"PAN","AR":"ARG","BO":"BOL","BV":"BVT","BR":"BRA","CL":"CHL","CO":"COL","EC":"ECU","FK":"FLK","GF":"GUF","GY":"GUY","PY":"PRY","PE":"PER","GS":"SGS","SR":"SUR","UY":"URY","VE":"VEN","BM":"BMU","CA":"CAN","GL":"GRL","PM":"SPM","US":"USA","AQ":"ATA","KZ":"KAZ","KG":"KGZ","TJ":"TJK","TM":"TKM","UZ":"UZB","CN":"CHN","HK":"HKG","MO":"MAC","KP":"PRK","JP":"JPN","MN":"MNG","KR":"KOR","BN":"BRN","KH":"KHM","ID":"IDN","LA":"LAO","MY":"MYS","MM":"MMR","PH":"PHL","SG":"SGP","TH":"THA","TL":"TLS","VN":"VNM","AF":"AFG","BD":"BGD","BT":"BTN","IN":"IND","IR":"IRN","MV":"MDV","NP":"NPL","PK":"PAK","LK":"LKA","AM":"ARM","AZ":"AZE","BH":"BHR","CY":"CYP","GE":"GEO","IQ":"IRQ","IL":"ISR","JO":"JOR","KW":"KWT","LB":"LBN","OM":"OMN","QA":"QAT","SA":"SAU","PS":"PSE","SY":"SYR","TR":"TUR","AE":"ARE","YE":"YEM","BY":"BLR","BG":"BGR","CZ":"CZE","HU":"HUN","PL":"POL","MD":"MDA","RO":"ROU","RU":"RUS","SK":"SVK","UA":"UKR","AX":"ALA","DK":"DNK","EE":"EST","FO":"FRO","FI":"FIN","GG":"GGY","IS":"ISL","IE":"IRL","IM":"IMN","JE":"JEY","LV":"LVA","LT":"LTU","NO":"NOR","SJ":"SJM","SE":"SWE","GB":"GBR","AL":"ALB","AD":"AND","BA":"BIH","HR":"HRV","GI":"GIB","GR":"GRC","VA":"VAT","IT":"ITA","MT":"MLT","ME":"MNE","MK":"MKD","PT":"PRT","SM":"SMR","RS":"SRB","SI":"SVN","ES":"ESP","AT":"AUT","BE":"BEL","FR":"FRA","DE":"DEU","LI":"LIE","LU":"LUX","MC":"MCO","NL":"NLD","CH":"CHE","AU":"AUS","CX":"CXR","CC":"CCK","HM":"HMD","NZ":"NZL","NF":"NFK","FJ":"FJI","NC":"NCL","PG":"PNG","SB":"SLB","VU":"VUT","GU":"GUM","KI":"KIR","MH":"MHL","FM":"FSM","NR":"NRU","MP":"MNP","PW":"PLW","UM":"UMI","AS":"ASM","CK":"COK","PF":"PYF","NU":"NIU","PN":"PCN","WS":"WSM","TK":"TKL","TO":"TON","TV":"TUV","WF":"WLF"};
// Explicit compatibility with the bundled Natural Earth identifiers; no sovereignty changes.
const REGION_ALIASES={SAH:'Africa',PSX:'Asia',SDS:'Africa',CYN:'Asia',TWN:'Asia',SOL:'Africa',KOS:'Europe'};
function locationRegion(l,boundaries=global.WINGS_MAP_BOUNDARIES){
 const parts=l.id.toUpperCase().split(':');let country=parts.length>1?parts[0]:'',state=parts.length>1?parts[1]:'';
 country=COUNTRY_ALPHA2[country]||country;
 if(!country&&boundaries){const region=(boundaries.regions||[]).find(r=>r.code===l.id&&r.name.toLowerCase()===l.label.toLowerCase());if(region){country=region.country;state=region.code;}}
 // Legacy bare state IDs are accepted only where the recorded label identifies that state.
 if(!country&&((l.id==='KY'&&l.label==='Kentucky')||(l.id==='MI'&&l.label==='Michigan'))){country='USA';state=l.id;}
 if(country==='USA'){
  for(const [name,codes] of Object.entries(US_REGIONS))if(codes.split(' ').includes(state))return 'group:US-'+name;
  return null; // Country-only USA or unknown subdivision is never inferred to be a region.
 }
 if(!country)country=COUNTRY_REGIONS[l.id.toUpperCase()]?l.id.toUpperCase():'';
 if(!country)return null;
 const name=REGION_ALIASES[country]||COUNTRY_REGIONS[country];return name?'group:'+name:null;
}
function groupPlan(locations,expanded=new Set(),detail=false,boundaries=global.WINGS_MAP_BOUNDARIES,studyLocations=new Set()){
 const groups=new Map(),assignment=new Map(),source=new Map();
 for(const l of locations){if(source.has(l.id))throw Error('Duplicate location');source.set(l.id,l);const id=studyLocations.has(l.id)?l.id:(locationRegion(l,boundaries)||l.id);
  if(!groups.has(id)){const info=REGION_INFO[id];groups.set(id,{id,label:info?info[0]:l.label,lon:info?info[1]:l.lon,lat:info?info[2]:l.lat,members:[]});}groups.get(id).members.push(l.id);
 }
 // Only groups actually split by this cohort receive an exclusion label.
 const splitRegions=new Set(locations.filter(l=>studyLocations.has(l.id)).map(l=>locationRegion(l,boundaries)).filter(Boolean));
 groups.forEach(g=>{if(splitRegions.has(g.id))g.label+=' (other locations)';});
 groups.forEach(g=>g.members.forEach(id=>assignment.set(id,detail||expanded.has(g.id)?id:g.id)));
 const visible=new Map();source.forEach((l,id)=>{const target=assignment.get(id);if(!visible.has(target))visible.set(target,target===id?{...l,members:[id]}:{...groups.get(target)});});
 return {groups,assignment,visible,source,detail};
}
// Sampling locations come only from identified study tips, never references,
// ancestral-state probabilities, geographic names or the first location entry.
function studyLocationCounts(raw){
 if(!raw)return new Map();
 const focal=raw.focal_sample_ids;
 if(!Array.isArray(focal)||!focal.length||new Set(focal).size!==focal.length)throw Error('Missing or duplicate study sample IDs');
 const wanted=new Set(focal),locations=new Set(raw.locations.map(l=>l.id));
 const trees=[...new Set(raw.draws?.length?raw.draws.map(d=>d.nodes||raw.nodes):(raw.nodes?[raw.nodes]:[]))];
 if(!trees.length)throw Error('Study tip locations are unavailable');
 let first=null;
 for(const nodes of trees){
  if(!Array.isArray(nodes))throw Error('Study tip locations are unavailable');
  const bySample=new Map();
  for(const n of nodes)if(wanted.has(n.sample_id)){
   if(bySample.has(n.sample_id)||!locations.has(n.observed_state))throw Error('Duplicate study tip or missing study location');
   bySample.set(n.sample_id,n.observed_state);
  }
  if(bySample.size!==wanted.size)throw Error('Some study samples have no recorded location');
  if(first){for(const [id,state] of first)if(bySample.get(id)!==state)throw Error('Study locations change across dated trees');}
  else first=bySample;
 }
 const counts=new Map();for(const state of first.values())counts.set(state,(counts.get(state)||0)+1);
 return counts;
}
function locationChoices(raw,locations,plan,previous=null){
 const counts=new Map();
 for(const [id,n] of studyLocationCounts(raw)){
  const key=plan.assignment.get(id);if(!key)throw Error('Study location missing from display plan');
  counts.set(key,(counts.get(key)||0)+n);
 }
 const options=locations.map(l=>({...l,studyCount:counts.get(l.id)||0}));
 options.sort((a,b)=>b.studyCount-a.studyCount||a.label.localeCompare(b.label)||a.id.localeCompare(b.id));
 const selected=options.some(l=>l.id===previous)?previous:(options.find(l=>l.studyCount>0)?.id||null);
 if(selected===null)throw Error('No study location is available for focus');
 return {options,selected};
}
function entrySummaries(draws,locations){
 const by=new Map(locations.map(l=>[l.id,Array(draws.length).fill(0)]));
 draws.forEach((d,i)=>d.history.jumps.forEach(j=>{if(!by.has(j.to))throw Error('Unknown grouped destination');by.get(j.to)[i]++;}));
 return Object.fromEntries([...by].map(([id,a])=>[id,{mean:a.reduce((x,y)=>x+y,0)/a.length,interval95:[quantile(a,.025),quantile(a,.975)],zero_probability:a.filter(x=>x===0).length/a.length,constant_sample:a.every(x=>x===a[0])}]));
}
function projectDataset(raw,plan){
 const states=new Set(raw.locations.map(l=>l.id)),map=id=>{if(!plan.assignment.has(id))throw Error('Location missing from grouping plan');return plan.assignment.get(id);};
 const locations=[...new Set(raw.locations.map(l=>map(l.id)))].map(id=>({...plan.visible.get(id),members:plan.visible.get(id).members.filter(m=>states.has(m))}));
 const nodes=ns=>ns.map(n=>n.observed_state?{...n,observed_state:map(n.observed_state)}:n),shared=raw.nodes?nodes(raw.nodes):null;
 const draws=raw.draws.map(d=>{
  indexDraw({...d,nodes:d.nodes||raw.nodes,focal_mrca:d.focal_mrca||raw.focal_mrca},states);
  const history={...d.history,root_state:map(d.history.root_state),jumps:d.history.jumps.map(j=>({...j,from:map(j.from),to:map(j.to)})).filter(j=>j.from!==j.to)};
  return {...d,nodes:d.nodes?nodes(d.nodes):shared,history};
 });
 return {...raw,nodes:shared||raw.nodes,draws,locations,entries:entrySummaries(draws,locations),display_grouping:!plan.detail};
}
function groupedEntry(raw,members){
 if(!raw)return null;const set=new Set(members),present=raw.locations.filter(l=>set.has(l.id));if(!present.length)return null;
 const a=raw.draws.map(d=>d.history.jumps.filter(j=>set.has(j.to)&&!set.has(j.from)).length);
 return {mean:a.reduce((x,y)=>x+y,0)/a.length,interval95:[quantile(a,.025),quantile(a,.975)],zero_probability:a.filter(x=>x===0).length/a.length,constant_sample:a.every(x=>x===a[0]),represented:present.length,total:members.length};
}

const api={validateModel,primaryAnalysisId,referenceLabel,prepare,indexDraw,upper,pairSummary,flow,displayFlows,mostProbableLocation,cumulative,locationRegion,groupPlan,studyLocationCounts,locationChoices,entrySummaries,projectDataset,groupedEntry};global.WingsPhylogeographyResults=api;if(typeof module==='object'&&module.exports)module.exports=api;
if(typeof document==='undefined')return;
const app=document.getElementById('app');if(!app)return;
try{start(validateModel(JSON.parse(document.getElementById('results-data').textContent)));}catch(e){app.textContent='Results withheld: '+e.message;}
function start(model){
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const date=t=>new Date(t).toLocaleDateString('en-US',{timeZone:'UTC',year:'numeric',month:'short',day:'numeric'});
 const color=id=>{let h=0;for(const c of id)h=(h*31+c.charCodeAt(0))>>>0;return `hsl(${h%360} 46% 39%)`;};
 const universe=[...new Map(model.analyses.flatMap(r=>Object.values(r.methods).flatMap(d=>d.locations)).map(l=>[l.id,l])).values()];
 let geography='regions',plan=groupPlan(universe),revision=0,cohortSignature=null;
 const segments=[...new Set(model.analyses.map(r=>r.id.split('/')[0]))];let segment=model.default_analysis.split('/')[0];
 const cache=new Map();let key=primaryAnalysisId(model,segment),method=model.default_method,pre=null,target=null,time=null,drawIndex=0,viewMode='summary',selectedNode=null,playing=false,timer=null,curve=[];
 // WINGS_MAP_EXPLORER_V1: display controls never alter posterior data.
 let mapAll=false,mapZoom=1,mapX=0,mapY=0,mapDrag=null,mapSuppressClick=false,mapExpanded=false,mapFocus={x:360,y:210};
 const el=id=>document.getElementById(id);const create=(tag,attrs,text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs||{}).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;};
 const add=(parent,tag,attrs,text)=>{const n=create(tag,attrs,text);parent.appendChild(n);return n;};
 app.innerHTML=`<header><div><p class="eyebrow">WINGS / PHYLODYNAMICS</p><h1>Avian influenza spread through time</h1><p>Reconstructed ancestry and geographic spread of WINGS samples.</p></div><span id="method-badge" class="badge"></span></header>
 <section class="toolbar"><div class="tabs" role="group" aria-label="Inference method"><button id="fast">Fast</button><button id="beast">BEAST</button></div><label id="segment-control" ${segments.length===1?'hidden':''}>Segment <select id="segment">${segments.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('')}</select></label><label>Geographic detail <select id="geography" aria-label="Geographic detail"><option value="regions">Regions</option><option value="locations">States and countries</option></select></label><div class="focus-control"><label for="target">Focus location</label><div class="focus-field"><select id="target" aria-describedby="focus-hint"></select><small id="focus-hint">Explore entries and connected routes</small></div></div><span id="status" role="status"></span></section>
 <div class="result-context"><span id="reference-label"></span><button id="return-primary" hidden>Return to primary result</button></div>
 <div id="blocked" class="blocked" hidden></div><div id="results">
 <section class="group-controls"><span id="grouping-note"></span><details id="region-members"><summary id="region-member-title"></summary><div id="region-member-list"></div></details></section>
 <section class="metrics"><article><span>WINGS common ancestor</span><strong id="tmrca"></strong><small id="date-interval"></small></article><article><span id="entry-label"></span><strong id="entry-value"></strong><small id="entry-interval"></small></article><article><span>Study ancestry</span><strong id="sample-count"></strong><small id="history-count"></small></article></section>
 <section class="player"><button id="play">Play</button><label class="sr-only" for="time">Calendar time</label><input id="time" type="range" min="0" max="1000" value="1000"><output id="current-date"></output><label>Speed <select id="speed"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></label><button id="full-time">Latest date</button></section>
 <p id="view-summary" class="view-summary" role="status"></p>
 <details id="uncertainty-controls" class="uncertainty-controls"><summary>Advanced → Explore uncertainty</summary><p>Each posterior draw is one complete geographic reconstruction containing zero or more Markov jumps.</p><section class="view-controls"><label>Display <select id="view"><option value="summary">Posterior summary</option><option value="history">One posterior draw</option></select></label><div id="draw-controls" hidden><button id="previous" aria-label="Previous posterior draw">←</button><label>Posterior draw <input id="draw" type="number" min="1" value="1" aria-describedby="draw-source"></label><button id="next" aria-label="Next posterior draw">→</button><span id="draw-source"></span></div></section></details>
 <style id="wpg-map-layout-style">
 #ancestry-views{grid-template-columns:minmax(0,1fr)}
 #map-panel .map-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
 #map-panel .map-controls button{font-size:13px;padding:7px 12px}
 #map-panel .map-controls #map-expand{margin-left:auto}
 #map-panel #map{width:100%;height:auto;max-height:none;aspect-ratio:12/7;background:#f5f8f8;border-radius:12px;touch-action:pan-y;cursor:grab}
 #map-panel #map[data-zoomed="true"]{touch-action:none}
 #map-panel #map:active{cursor:grabbing}
 #map-panel .map-stage{width:100%;max-width:1200px;margin:0 auto}
 #map-panel #map-route-detail{min-height:20px;margin:8px 0;color:#263d47}
 #map-panel .wpg-route-piece{transition:opacity .12s}
 #map-panel .wpg-route-piece:focus{outline:none}
 #map-panel .wpg-route-piece:focus-visible .wpg-map-route{stroke-width:5}
 #map-panel #map-help{margin:4px 0 12px}
 #map-dialog{width:96vw;max-width:1680px;max-height:94vh;padding:0;border:0;border-radius:14px;color:#263d47}
 #map-dialog::backdrop{background:rgba(20,38,47,.55)}
 #map-dialog #map-panel{border:0;max-height:94vh;overflow:auto}
 #map-dialog .map-stage{max-width:none}
 #map-dialog #map{height:calc(94vh - 260px);min-height:240px;aspect-ratio:auto}
 #map-dialog #legend{max-height:55px}
 @media(max-width:600px){#map-panel .map-controls #map-expand{margin-left:0}#map-panel .map-controls{gap:6px}#map-panel .map-controls button{font-size:12px}#map-dialog{width:98vw}#map-dialog #map{height:calc(94vh - 320px)}}
 @media(prefers-reduced-motion:reduce){#map-panel .wpg-route-piece{transition:none}}
 </style>
 <div class="views" id="ancestry-views"><section class="panel" id="map-panel"><h2>Geographic reconstruction <span id="map-kind"></span></h2>
 <div class="map-controls"><button id="map-routes" aria-pressed="false">Show all routes</button><button id="map-zoom-in" aria-label="Zoom in on map">+</button><button id="map-zoom-out" aria-label="Zoom out of map">−</button><button id="map-reset">Reset view</button><button id="map-expand" aria-expanded="false" aria-controls="map-dialog">Expand map</button></div>
 <p id="map-help">Zoom with + / −, then drag to pan. Hover over a route, or use Tab, to inspect its direction and count.</p>
 <div class="map-stage"><svg id="map" viewBox="0 0 720 420" tabindex="0" role="img" aria-describedby="map-help" aria-label="Ancestral locations and directed geographic transitions"></svg></div><p id="map-route-detail" aria-live="polite">Hover over a route to highlight it.</p><p id="map-caption"></p><div id="legend"></div></section>
 <section class="panel"><h2>WINGS dated ancestry <span id="tree-kind"></span></h2><div class="tree-scroll"><svg id="tree" role="img" aria-label="Dated tree with WINGS samples and ancestral locations"></svg></div><p id="tree-caption"></p></section></div>
 <dialog id="map-dialog" aria-label="Expanded geographic reconstruction"></dialog>
 <div class="views second"><section class="panel"><h2>Directed Markov jumps <span id="chord-kind"></span></h2><svg id="chord" viewBox="0 0 660 510" role="img" aria-label="Directed chord diagram of Markov jump counts"></svg><p id="chord-caption"></p><p class="note">The model has one symmetric rate. Directional jump counts can still differ.</p></section>
 <section class="panel"><h2 id="node-title">Location of the WINGS ancestor</h2><p id="node-draw-state" class="node-draw-state" hidden></p><p id="probability-label" class="probability-label">Across all posterior draws</p><div id="node-probabilities"></div><p id="node-caption"></p><h2 class="spaced" id="curve-title"></h2><svg id="counts" viewBox="0 0 650 240" role="img" aria-label="Cumulative entries and pointwise posterior intervals"></svg><p>Across all posterior draws · line: mean · band: pointwise 95% interval. Zero-entry draws remain included.</p></section></div>

 <details><summary>Methods, priors and diagnostics</summary><p id="scope"></p><ul><li id="prior"></li><li>Counts cover WINGS ancestry from its common ancestor to the study samples; the ancestral stem and reference-only branches are excluded.</li><li>Geographic states are recorded sampling locations. These inferred changes are not observed movements or transmission events.</li><li id="checks"></li></ul><a href="results.json" download>Download results and diagnostics</a></details></div>
 <details id="reference-controls" class="panel reference-controls"><summary>Advanced → Reference sampling</summary><p>Compare reference sets to assess sampling sensitivity. The primary set was chosen in advance, not ranked by its results.</p><div class="reference-toolbar"><label>Reference set <select id="analysis"></select></label></div><p class="reference-help">Balanced sets favor underrepresented locations and collection periods; random sets sample the eligible pool. Both retain reserved close relatives. Set numbers identify different selections, not performance ranks.</p><h2>Reference-sampling sensitivity <span id="sensitivity-method"></span></h2><p id="sensitivity-context"></p><div class="table-scroll"><table><thead><tr><th>Reference set</th><th>Mean entries</th><th>95% interval</th><th>P(0 entries)</th><th>Status</th></tr></thead><tbody id="sensitivity"></tbody></table></div><p>Across all posterior draws within each reference set. Replicate posteriors are not pooled.</p></details>`;
 const loc=id=>pre.data.locations.find(l=>l.id===id);const currentRow=()=>model.analyses.find(r=>r.id===key);
 function stop(){playing=false;clearInterval(timer);el('play').textContent='Play';}
 function referenceControls(){
  const primary=primaryAnalysisId(model,segment),ids=[...new Set([primary,...model.analyses.filter(r=>r.id.split('/')[0]===segment).map(r=>r.id)])];
  el('analysis').innerHTML=ids.map(id=>`<option value="${esc(id)}">${esc(referenceLabel(id))}${id===primary?' · Primary':''}${model.analyses.some(r=>r.id===id)?'':' · Not included'}</option>`).join('');
  el('analysis').value=key;el('segment').value=segment;
  el('reference-label').textContent=key===primary?'Primary result · '+segment:'Comparison result · '+referenceLabel(key);
  el('reference-label').title=key===primary?referenceLabel(primary)+' · Predeclared primary':referenceLabel(key);
  el('return-primary').hidden=key===primary;
 }

 function choose(preserve=false){const oldTime=time,oldDraw=drawIndex,oldNode=selectedNode,oldMembers=pre?.data.locations.find(l=>l.id===target)?.members||[target];stop();if(!preserve){viewMode='summary';el('view').value='summary';el('uncertainty-controls').open=false;}referenceControls();el('fast').classList.toggle('active',method==='fast');el('beast').classList.toggle('active',method==='beast');el('fast').setAttribute('aria-pressed',method==='fast');el('beast').setAttribute('aria-pressed',method==='beast');el('method-badge').textContent=method==='fast'?'FAST · FIXED DATED TREE':'BEAST · DATE UNCERTAINTY';
  const row=currentRow(),data=row?.methods[method];
  if(!data){pre=null;el('results').hidden=true;el('blocked').hidden=false;el('blocked').textContent=(key===primaryAnalysisId(model,segment)?'Primary result':'Comparison result')+' unavailable for '+(method==='beast'?'BEAST':'Fast')+': '+(row?.unavailable[method]||'The selected reference set is not included in this report')+'. No alternative has been selected automatically. Other saved sets are available under Advanced → Reference sampling.';el('target').replaceChildren();el('target').disabled=true;el('status').textContent='Unavailable';renderTable();return;}
  const cohort=studyLocationCounts(data),signature=JSON.stringify([...cohort].sort());
  if(signature!==cohortSignature){cohortSignature=signature;target=null;revision++;plan=groupPlan(universe,new Set(),geography==='locations',undefined,new Set(cohort.keys()));}
  const id=key+'|'+method+'|'+revision;if(!cache.has(id)){const projected=projectDataset(data,plan);cache.set(id,prepare(projected));if(cache.size>2)cache.delete(cache.keys().next().value);}pre=cache.get(id);el('target').disabled=false;el('results').hidden=false;el('blocked').hidden=true;el('status').textContent=model.demo?'Illustrative demo data':'Source checks passed';
  if(preserve&&!pre.data.locations.some(l=>l.id===target))target=plan.assignment.get(oldMembers[0]);
  const focus=locationChoices(data,pre.data.locations,plan,target);target=focus.selected;
  const option=l=>`<option value="${esc(l.id)}" ${l.id===target?'selected':''}>${esc(l.label)}${l.studyCount?' · '+l.studyCount+' study sample'+(l.studyCount===1?'':'s'):''}</option>`;
  const study=focus.options.filter(l=>l.studyCount),context=focus.options.filter(l=>!l.studyCount);
  el('focus-hint').textContent='Study locations appear first. Default: most study samples; alphabetical order breaks ties. Explore entries and connected routes.';
  el('target').innerHTML='<optgroup label="Study sample locations">'+study.map(option).join('')+'</optgroup>'+(context.length?'<optgroup label="Reference context">'+context.map(option).join('')+'</optgroup>':'');time=preserve&&oldTime!==null?Math.max(pre.min,Math.min(pre.max,oldTime)):pre.max;drawIndex=preserve?Math.min(pre.N-1,oldDraw):0;selectedNode=preserve&&pre.stats.has(oldNode)?oldNode:pre.data.focal_mrca;
  el('tmrca').textContent=date(ms(data.tmrca.median));el('date-interval').textContent=data.tmrca.hpd95?'95% HPD '+data.tmrca.hpd95.map(x=>date(ms(x))).join(' – '):'Point estimate · dates held fixed';
  el('sample-count').textContent=data.focal_sample_ids.length+' WINGS samples';el('history-count').textContent=pre.N.toLocaleString()+' posterior draws';
  el('scope').textContent=data.scope+(row.methods.fast&&row.methods.beast&&JSON.stringify(row.methods.fast.prior)!==JSON.stringify(row.methods.beast.prior)?' Fast and BEAST use different geographic priors in this comparison.':'');const p=data.prior;el('prior').textContent=(p.family==='lognormal'?`Lognormal prior: median ${p.median}, log SD ${p.log_sd}`:`Gamma prior: shape ${p.shape}, rate ${p.rate}`)+` on the ${p.parameter==='exit_rate'?'total exit':'per-destination transition'} rate per year. Uniform root-location prior over the original fitted locations; symmetric equal-rate model. Display grouping does not change this prior or refit geography.`;
  el('checks').textContent=model.demo?'Simulated demonstration only; these are not validated biological results.':method==='beast'?'BEAST results require passing chain, internal-date, ESS/R-hat and geographic-precision gates.':'Fast results require passing temporal-signal, history-validity, numerical-integration and Monte Carlo precision checks. No MCMC ESS is reported for direct conditional draws.';
  el('draw').max=pre.N;setTarget();
 }
 function setTarget(){if(!pre)return;groupControls();const e=pre.data.entries[target];el('entry-label').textContent='Entries into '+loc(target).label;el('entry-value').textContent=e.mean.toFixed(2);el('entry-interval').textContent=e.constant_sample?`Posterior mean · full ancestry · 95% interval ${e.interval95[0]}–${e.interval95[1]} · no sampled variation`:`Posterior mean · full ancestry · 95% interval ${e.interval95[0]}–${e.interval95[1]}`;
  curve=cumulative(pre,target,Array.from({length:121},(_,i)=>pre.min+(pre.max-pre.min)*i/120));renderTable();render();
 }
 function pathArc(cx,cy,r,a,b){const p=[cx+r*Math.cos(a),cy+r*Math.sin(a)],q=[cx+r*Math.cos(b),cy+r*Math.sin(b)];return `M${p} A${r},${r} 0 ${b-a>Math.PI?1:0},1 ${q}`;}
 function tooltip(n,text){add(n,'title',{},text);}
 function pie(svg,cx,cy,r,dist,opacity=1){let angle=-Math.PI/2;Object.entries(dist).sort((a,b)=>b[1]-a[1]).forEach(([state,p])=>{const end=angle+p*2*Math.PI;if(p>.999999){add(svg,'circle',{cx,cy,r,fill:color(state),opacity});}else{const a=[cx+r*Math.cos(angle),cy+r*Math.sin(angle)],b=[cx+r*Math.cos(end),cy+r*Math.sin(end)];add(svg,'path',{d:`M${cx},${cy} L${a} A${r},${r} 0 ${p>.5?1:0},1 ${b} Z`,fill:color(state),opacity});}angle=end;});}
 function map(draw,view){const s=el('map');s.replaceChildren();applyMapCamera();const locations=pre.data.locations,x0=Math.max(-180,Math.min(...locations.map(l=>l.lon))-12),x1=Math.min(180,Math.max(...locations.map(l=>l.lon))+12),y0=Math.max(-85,Math.min(...locations.map(l=>l.lat))-9),y1=Math.min(85,Math.max(...locations.map(l=>l.lat))+9);
  const project=(lon,lat)=>[25+(lon-x0)/(x1-x0)*670,390-(lat-y0)/(y1-y0)*360];add(s,'rect',{x:0,y:0,width:720,height:420,rx:14,fill:'#f5f8f8'});const defs=add(s,'defs');const clip=add(defs,'clipPath',{id:'map-clip'});add(clip,'rect',{x:15,y:15,width:690,height:390});const land=add(s,'g',{'clip-path':'url(#map-clip)'});const boundaries=global.WINGS_MAP_BOUNDARIES;
  if(boundaries)[...(boundaries.countries||[]),...(boundaries.regions||[])].forEach(region=>(region.polygons||[]).forEach(poly=>add(land,'path',{d:poly.map(ring=>'M'+ring.map(p=>project(p[0],p[1])).join('L')+'Z').join(''),fill:'#edf2f1',stroke:'#c8d6d9','stroke-width':.65})));
  const focusPoint=project(loc(target).lon,loc(target).lat);mapFocus={x:focusPoint[0],y:focusPoint[1]};
  const routes=displayFlows(pre,time,viewMode==='history'?draw:null);
  const connected=routes.filter(p=>p.from===target||p.to===target).sort((a,b)=>b.mean-a.mean||a.from.localeCompare(b.from)||a.to.localeCompare(b.to));
  const shown=mapAll?connected:connected.slice(0,6);
  el('map-routes').textContent=connected.length<=6?`All ${connected.length} routes shown`:mapAll?'Show six strongest':`Show all ${connected.length} routes`;el('map-routes').disabled=connected.length<=6;el('map-routes').setAttribute('aria-pressed',String(mapAll));
  el('map-route-detail').textContent='Hover over a route to highlight it.';
  const pieces=[];
  const highlight=index=>{pieces.forEach((parts,i)=>parts.forEach(n=>n.style.opacity=index===null||i===index?'1':'.15'));el('map-route-detail').textContent=index===null?'Hover over a route to highlight it.':pieces[index].description;};
  // Map arrows use screen-pixel sizing so direction remains readable in narrow panels.
  const arrowheads=[];
  const matrix=s.getScreenCTM(),arrowScale=matrix?1/Math.max(.001,Math.hypot(matrix.a,matrix.b)):1; 
  shown.forEach((p,index)=>{
   const from=loc(p.from),to=loc(p.to),a=project(from.lon,from.lat),b=project(to.lon,to.lat),dx=b[0]-a[0],dy=b[1]-a[1],norm=Math.max(1,Math.hypot(dx,dy)),bend=Math.min(48,Math.max(18,norm*.16)),c=[(a[0]+b[0])/2-dy/norm*bend,(a[1]+b[1])/2+dx/norm*bend];
   const path=`M${a} Q${c} ${b}`,width=1.4+Math.min(2.6,Math.sqrt(p.mean)*.9);
   const description=`${from.label} → ${to.label}: ${p.mean.toFixed(2)} ${viewMode==='summary'?'mean jumps':'jumps'} through this date`;
   const group=add(s,'g',{class:'wpg-route-piece',tabindex:0,role:'img','aria-label':description});pieces[index]=[group];pieces[index].description=description;
   group.onmouseenter=()=>highlight(index);group.onmouseleave=()=>highlight(null);group.onfocus=()=>highlight(index);group.onblur=()=>highlight(null);
   add(group,'path',{d:path,fill:'none',stroke:'#fff','stroke-width':width+1.4,'stroke-linecap':'round','vector-effect':'non-scaling-stroke',opacity:.9,'pointer-events':'none'});
   const line=add(group,'path',{class:'wpg-map-route',d:path,fill:'none',stroke:color(p.from),'stroke-width':width,'stroke-linecap':'round','vector-effect':'non-scaling-stroke',opacity:.9});tooltip(line,description);
   const hit=add(group,'path',{d:path,fill:'none',stroke:'transparent','stroke-width':Math.max(10,width+5),'vector-effect':'non-scaling-stroke','pointer-events':'stroke'});tooltip(hit,description);
   const t=.62,u=1-t,at=[u*u*a[0]+2*u*t*c[0]+t*t*b[0],u*u*a[1]+2*u*t*c[1]+t*t*b[1]],angle=Math.atan2(u*(c[1]-a[1])+t*(b[1]-c[1]),u*(c[0]-a[0])+t*(b[0]-c[0]));
   const head=Math.min(11,Math.max(7,norm/arrowScale*.20))*arrowScale;
   arrowheads.push({index,attributes:{class:'wpg-map-arrow',d:`M${at[0]},${at[1]} l${-head*Math.cos(angle-.5)},${-head*Math.sin(angle-.5)} l${head*Math.cos(angle-.5)-head*Math.cos(angle+.5)},${head*Math.sin(angle-.5)-head*Math.sin(angle+.5)} Z`,fill:color(p.from),stroke:'#fff','stroke-width':.9,'stroke-linejoin':'round','vector-effect':'non-scaling-stroke'},description});
  });
  // Draw heads above every route so crossing routes cannot cover the direction.
  arrowheads.forEach(({index,attributes,description})=>{const group=add(s,'g',{class:'wpg-route-piece','pointer-events':'none'});pieces[index].push(group);tooltip(add(group,'path',attributes),description);});
  locations.forEach(l=>{const pt=project(l.lon,l.lat),o=pre.occupancy.get(l.id);let n=(upper(o.starts,time)-upper(o.ends,time))/pre.N;
   if(viewMode==='history')n=view.segments.filter(q=>q.state===l.id&&q.start<=time&&time<q.end).length;
   const circle=add(s,'circle',{cx:pt[0],cy:pt[1],r:5+Math.min(11,Math.sqrt(n)*3),fill:color(l.id),stroke:l.id===target?'#ffc627':'#fff','stroke-width':l.id===target?4:2,tabindex:0,role:'button','aria-label':'Select '+l.label});tooltip(circle,`${l.label}${l.members.length>1?' ('+l.members.length+' represented locations)':''}: ${n.toFixed(2)} ${viewMode==='summary'?'expected active lineages':'active lineages'}`);circle.onclick=()=>selectLocation(l.id);circle.onkeydown=e=>{if(e.key==='Enter')selectLocation(l.id);};
  });
  el('map-kind').textContent=viewMode==='summary'?'Posterior mean jumps':'Posterior draw '+(drawIndex+1);el('map-caption').textContent=`Showing ${shown.length} of ${connected.length} directed routes connected to ${loc(target).label}, accumulated through this date.${!mapAll&&connected.length>6?' Ranked by '+(viewMode==='summary'?'posterior mean jumps':'jump count')+'.':''} The display limit does not change entry counts or other results. Circle size shows active lineages. Regional markers are display anchors; arcs are inferred changes, not flight paths.`;
  el('legend').replaceChildren();locations.forEach(l=>{const item=document.createElement('button');item.className='legend-item';item.innerHTML=`<i style="background:${color(l.id)}"></i>${esc(l.label)}`;item.onclick=()=>selectLocation(l.id);el('legend').appendChild(item);});
 }
 function tree(draw,view){const s=el('tree');s.replaceChildren();const base=viewMode==='summary'?pre.view:view,root=pre.data.focal_mrca,ys={},nodeDate=id=>viewMode==='summary'?pre.stats.get(id).median:ms(base.by.get(id).date);let cursor=30;
  function layout(id){const kids=base.children.get(id);ys[id]=kids.length?kids.map(layout).reduce((a,b)=>a+b,0)/kids.length:(cursor+=27);return ys[id];}layout(root);s.setAttribute('viewBox',`0 0 840 ${cursor+35}`);s.style.width='100%';s.style.minWidth='730px';s.style.height=(cursor+35)+'px';/* WINGS_TREE_FIT_HEIGHT_V1 */s.parentElement.style.height='auto';s.parentElement.style.maxHeight='min(490px, 65vh)';const x=t=>25+(t-pre.min)/(pre.max-pre.min)*470;
  if(pre.data.tmrca.hpd95){const b=pre.data.tmrca.hpd95.map(ms);const band=add(s,'rect',{x:x(b[0]),y:24,width:Math.max(1,x(b[1])-x(b[0])),height:cursor,fill:'#fff0ba',opacity:.65});tooltip(band,'WINGS ancestor · 95% HPD: '+b.map(date).join(' – '));}
  base.order.forEach(id=>{const n=base.by.get(id),t=nodeDate(id),y=ys[id];if(n.parent!==null){const start=nodeDate(n.parent);add(s,'line',{x1:x(start),x2:x(start),y1:ys[n.parent],y2:y,stroke:'#acbcc3','stroke-width':1.5});
    if(viewMode==='summary')add(s,'line',{x1:x(start),x2:x(t),y1:y,y2:y,stroke:'#acbcc3','stroke-width':1.8,opacity:start<=time?1:.3});
    else{let a=start,state=base.ends[n.parent];[...base.events.get(id),{date:n.date,to:null}].forEach(j=>{const b=ms(j.date);add(s,'line',{x1:x(a),x2:x(b),y1:y,y2:y,stroke:color(state),'stroke-width':2.4,opacity:a<=time?1:.2});a=b;state=j.to;});}
   }
   if(n.sample_id){add(s,'rect',{x:x(t)-4,y:y-4,width:8,height:8,fill:'#ffc627',stroke:'#8c1d40',opacity:t<=time?1:.35});add(s,'text',{x:514,y:y+4,fill:'#253e48','font-size':12,'font-weight':650},n.label||n.sample_id);}
   else{const best=mostProbableLocation(pre.stats.get(id).states),state=viewMode==='summary'?best.id:base.ends[id];const mark=add(s,'circle',{cx:x(t),cy:y,r:id===root?7:4.5,fill:color(state),opacity:t<=time?1:.3,'data-node-id':id,'data-location':state});const hit=add(s,'circle',{cx:x(t),cy:y,r:8,fill:'transparent',stroke:selectedNode===id?'#ffc627':'transparent','stroke-width':2,tabindex:0,role:'button','aria-label':id===root?'WINGS common ancestor':'Inspect ancestor'});const probs=Object.entries(pre.stats.get(id).states).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`${loc(k).label}: ${(v*100).toFixed(1)}%`).join('\n');tooltip(hit,date(t)+'\n'+(viewMode==='history'?'This draw: '+loc(state).label+'\nAcross all posterior draws:\n':(best.tied.length>1?'Tied most-probable locations; displayed '+loc(state).label+'\n':'Most probable: '+loc(state).label+' ('+(100*best.probability).toFixed(1)+'%)\n'))+probs);hit.onclick=()=>{selectedNode=id;render();};hit.onkeydown=e=>{if(e.key==='Enter'){selectedNode=id;render();}};}
  });
  add(s,'line',{x1:x(time),x2:x(time),y1:25,y2:cursor+12,stroke:'#8c1d40','stroke-dasharray':'4 4',opacity:.6});add(s,'text',{x:25,y:16,'font-size':11,fill:'#566e78'},date(pre.min));add(s,'text',{x:495,y:16,'text-anchor':'end','font-size':11,fill:'#566e78'},date(pre.max));el('tree-kind').textContent=viewMode==='summary'?(method==='beast'?'Median dates · most probable locations':'Fixed dates · most probable locations'):'Posterior draw '+(drawIndex+1);el('tree-caption').textContent=(viewMode==='summary'?'Node colors: most probable location at each ancestor. Click for probabilities. Gray branches do not show jump paths.':'Node colors: locations in this draw. Branch-color changes: Markov jumps.')+' Gold tips: WINGS samples. Pale yellow band, when shown: ancestor 95% HPD.';
 }
 function chord(draw){const s=el('chord');s.replaceChildren();const routes=displayFlows(pre,time,viewMode==='history'?draw:null),locations=pre.data.locations.filter(l=>routes.some(p=>p.from===l.id||p.to===l.id));
  el('chord-kind').textContent=viewMode==='summary'?'Posterior mean jumps':'Posterior draw '+(drawIndex+1);el('chord-caption').textContent=viewMode==='summary'?'Ribbon width: mean jumps across all draws through this date. Hover for 95% intervals. Arrowheads indicate destination.':'Ribbon width: number of jumps in this draw through this date. Arrowheads indicate destination.';
  if(!routes.length){add(s,'text',{x:330,y:250,'text-anchor':'middle',fill:'#657d87','font-size':16},'No jumps before this date');return;}
  const totals=new Map(locations.map(l=>[l.id,routes.filter(p=>p.from===l.id||p.to===l.id).reduce((a,p)=>a+p.mean,0)])),sum=[...totals.values()].reduce((a,b)=>a+b,0),gap=Math.min(.055,.6/locations.length),usable=2*Math.PI-gap*locations.length,cx=330,cy=250,r=168,segments=new Map();let a=-Math.PI/2;
  locations.forEach(l=>{const b=a+usable*totals.get(l.id)/sum;segments.set(l.id,{start:a,end:b,cursor:a});a=b+gap;});
  const slots=[];routes.sort((a,b)=>b.mean-a.mean).forEach(p=>{const from=segments.get(p.from),to=segments.get(p.to),width=usable*p.mean/sum;slots.push({...p,a0:from.cursor,a1:from.cursor+width,b0:to.cursor,b1:to.cursor+width});from.cursor+=width;to.cursor+=width;});
  const point=(angle,radius=r)=>[cx+radius*Math.cos(angle),cy+radius*Math.sin(angle)];
  slots.forEach(p=>{const a0=point(p.a0),a1=point(p.a1),b0=point(p.b0,r-16),b1=point(p.b1,r-16),tip=point((p.b0+p.b1)/2,r);const path=add(s,'path',{d:`M${a0} A${r},${r} 0 ${p.a1-p.a0>Math.PI?1:0},1 ${a1} Q${cx},${cy} ${b0} L${tip} L${b1} Q${cx},${cy} ${a0} Z`,fill:color(p.from),opacity:p.from===target||p.to===target?.68:.18,tabindex:0,role:'button','aria-label':loc(p.from).label+' to '+loc(p.to).label});
   let loaded=false;const show=()=>{if(loaded)return;loaded=true;if(viewMode==='history'){tooltip(path,`${loc(p.from).label} → ${loc(p.to).label}\n${p.mean} jumps in posterior draw ${drawIndex+1} through this date`);return;}const q=pairSummary(pre,p.pair,time);tooltip(path,`${loc(p.from).label} → ${loc(p.to).label}\nMean ${q.mean.toFixed(2)} · 95% interval ${q.low}–${q.high}\nP(at least one jump): ${(100*q.pAny).toFixed(1)}%\nPosterior counts, not asymmetric rate estimates`);};path.onmouseenter=show;path.onfocus=show;path.onclick=()=>selectLocation(p.to);path.onkeydown=e=>{if(e.key==='Enter')selectLocation(p.to);};
  });
  locations.forEach(l=>{const seg=segments.get(l.id),mid=(seg.start+seg.end)/2,p=point(mid,r+24);const arc=add(s,'path',{d:pathArc(cx,cy,r+9,seg.start,seg.end),fill:'none',stroke:color(l.id),'stroke-width':13,tabindex:0,role:'button','aria-label':'Select '+l.label});arc.onclick=()=>selectLocation(l.id);arc.onkeydown=e=>{if(e.key==='Enter')selectLocation(l.id);};tooltip(arc,l.label+': '+(viewMode==='summary'?totals.get(l.id).toFixed(2)+' mean':totals.get(l.id))+' incoming + outgoing jumps');add(s,'text',{x:p[0],y:p[1]+4,'text-anchor':Math.cos(mid)>.15?'start':Math.cos(mid)<-.15?'end':'middle','font-size':locations.length>16?9:12,fill:'#29414a','font-weight':l.id===target?750:450},l.id==='group:US-South'?'U.S. South':l.id==='group:Northern America'?'Northern America':l.id==='group:Latin America and the Caribbean'?'Latin America / Caribbean':l.label);});
 }
 function nodeProbabilities(view){const stat=pre.stats.get(selectedNode)||pre.stats.get(pre.data.focal_mrca);el('node-title').textContent=selectedNode===pre.data.focal_mrca?'Location of the WINGS ancestor':'Location of the selected ancestor';el('node-draw-state').hidden=viewMode!=='history';el('node-draw-state').textContent=viewMode==='history'?'This draw: '+loc(view.ends[selectedNode]||view.ends[pre.data.focal_mrca]).label:'';el('node-probabilities').replaceChildren();const entries=Object.entries(stat.states).sort((a,b)=>b[1]-a[1]);entries.forEach(([id,p])=>{const row=document.createElement('button');row.className='probability-row';row.innerHTML=`<span>${esc(loc(id).label)}</span><span class="probability-track"><i style="width:${p*100}%;background:${color(id)}"></i></span><strong>${(p*100).toFixed(1)}%</strong>`;row.onclick=()=>selectLocation(id);el('node-probabilities').appendChild(row);});el('node-caption').textContent='Probabilities across all posterior draws. The most probable location at each node does not define a single joint migration history.';}
 function counts(){const s=el('counts');s.replaceChildren();el('curve-title').textContent='Posterior mean entries into '+loc(target).label+' through time';const high=Math.max(1,...curve.map(p=>p.high)),x=t=>44+(t-pre.min)/(pre.max-pre.min)*582,y=v=>190-v/high*160;
  [0,high/2,high].forEach(v=>{add(s,'line',{x1:44,x2:626,y1:y(v),y2:y(v),stroke:'#e1e7e9'});add(s,'text',{x:35,y:y(v)+4,'text-anchor':'end','font-size':12,fill:'#5d737d'},v.toFixed(v%1?1:0));});
  const points=(rows,key)=>rows.map(p=>`${x(p.time)},${y(p[key])}`).join('L');add(s,'path',{d:'M'+points(curve,'high')+'L'+points(curve.slice().reverse(),'low')+'Z',fill:'#8c1d40',opacity:.13});add(s,'path',{d:'M'+points(curve,'mean'),fill:'none',stroke:'#8c1d40','stroke-width':2.5});add(s,'line',{x1:x(time),x2:x(time),y1:20,y2:190,stroke:'#586f79'});add(s,'text',{x:44,y:220,'font-size':11,fill:'#5d737d'},date(pre.min));add(s,'text',{x:626,y:220,'text-anchor':'end','font-size':11,fill:'#5d737d'},date(pre.max));
 }
 function renderTable(){
  const body=el('sensitivity');body.replaceChildren();el('sensitivity-method').textContent=method==='fast'?'Fast · separate reference sets':'BEAST · separate reference sets';
  const focus=plan.visible.get(target),members=focus?.members;el('sensitivity-context').textContent=focus?'Entries into '+focus.label:'Entry estimates appear when a focus location is available.';
  const primary=primaryAnalysisId(model,segment),rows=model.analyses.filter(r=>r.id.split('/')[0]===segment);
  if(!rows.some(r=>r.id===primary))rows.unshift({id:primary,methods:{},unavailable:{}});
  rows.forEach(r=>{const d=r.methods[method],e=members?groupedEntry(d,members):null,row=document.createElement('tr');if(r.id===key)row.className='selected-row';const label=document.createElement('td'),button=document.createElement('button');button.className='text-button';button.textContent=referenceLabel(r.id)+(r.id===primary?' · Primary':'');button.onclick=()=>{key=r.id;choose();};label.appendChild(button);row.appendChild(label);
   [e?e.mean.toFixed(2):'—',e?`${e.interval95[0]}–${e.interval95[1]}`:'—',e?(100*e.zero_probability).toFixed(1)+'%':'—',d?(e?(e.represented<e.total?`Passed · ${e.represented}/${e.total} member locations represented`:'Passed'):(members?'Location unavailable':'Passed · select a focus location')):'Unavailable'].forEach(value=>{const td=document.createElement('td');td.textContent=value;row.appendChild(td);});body.appendChild(row);
  });
 }

 function groupControls(){
  const l=loc(target),members=l.members;el('geography').value=geography;
  el('grouping-note').textContent=geography==='locations'?'Original fitted locations · same posterior draws':'Study locations stay separate · other locations grouped · within-group jumps excluded';
  el('region-members').hidden=geography==='locations'||members.length<=1;
  el('region-member-title').textContent=l.label+' · '+members.length+' represented '+(members.length===1?'location':'locations');
  el('region-member-list').textContent=members.map(id=>plan.source.get(id).label).join(' · ');
 }
 function refreshGroups(){revision++;plan=groupPlan(universe,new Set(),geography==='locations',undefined,new Set(studyLocationCounts(currentRow()?.methods[method]).keys()));choose(true);}

 function selectLocation(id){target=id;el('target').value=id;setTarget();}
 function render(){if(!pre)return;const draw=pre.data.draws[drawIndex],view=viewMode==='history'?indexDraw(draw,new Set(pre.data.locations.map(l=>l.id))):pre.view;el('current-date').textContent=date(time);el('time').value=Math.round((time-pre.min)/(pre.max-pre.min)*1000);el('draw').value=drawIndex+1;el('draw-controls').hidden=viewMode!=='history';el('previous').disabled=drawIndex===0;el('next').disabled=drawIndex===pre.N-1;el('draw-source').textContent=`of ${pre.N.toLocaleString()} · `+(method==='beast'?`Chain ${draw.chain} · state ${draw.state.toLocaleString()}`:'Conditional on the fixed dated tree');el('view-summary').textContent=viewMode==='summary'?'Posterior summary · node colors show most probable locations; map and chords show mean jumps.':`Posterior draw ${drawIndex+1} of ${pre.N.toLocaleString()} · map, tree and chords show this reconstruction. Probability bars, entry summaries and reference comparisons use all draws.`;map(draw,view);tree(draw,view);chord(draw);nodeProbabilities(view);counts();}
 // Camera and route controls affect only this map.
 function applyMapCamera(){
  const w=720/mapZoom,h=420/mapZoom;mapX=Math.max(0,Math.min(720-w,mapX));mapY=Math.max(0,Math.min(420-h,mapY));
  el('map').setAttribute('viewBox',`${mapX} ${mapY} ${w} ${h}`);el('map').dataset.zoomed=String(mapZoom>1);
  el('map-zoom-out').disabled=mapZoom<=1;el('map-zoom-in').disabled=mapZoom>=8;el('map-reset').disabled=mapZoom===1&&mapX===0&&mapY===0;
 }
 function redrawMap(){if(pre){const draw=pre.data.draws[drawIndex];map(draw,viewMode==='history'?indexDraw(draw,new Set(pre.data.locations.map(l=>l.id))):pre.view);}}
 function zoomMap(factor,point=null){
  const next=Math.max(1,Math.min(8,mapZoom*factor));point=point||mapFocus;
  mapX=point.x-(point.x-mapX)*mapZoom/next;mapY=point.y-(point.y-mapY)*mapZoom/next;mapZoom=next;redrawMap();
 }
 const mapPoint=e=>{const point=el('map').createSVGPoint();point.x=e.clientX;point.y=e.clientY;return point.matrixTransform(el('map').getScreenCTM().inverse());};
 el('map-routes').onclick=()=>{mapAll=!mapAll;redrawMap();};
 el('map-zoom-in').onclick=()=>zoomMap(1.5);el('map-zoom-out').onclick=()=>zoomMap(1/1.5);
 el('map-reset').onclick=()=>{mapZoom=1;mapX=mapY=0;redrawMap();};
 const closeMap=()=>{el('ancestry-views').prepend(el('map-panel'));el('map-dialog').close();mapExpanded=false;el('map-expand').textContent='Expand map';el('map-expand').setAttribute('aria-expanded','false');redrawMap();el('map-expand').focus();};
 el('map-expand').onclick=()=>{if(mapExpanded){closeMap();return;}stop();el('map-dialog').appendChild(el('map-panel'));el('map-dialog').showModal();mapExpanded=true;el('map-expand').textContent='Close map';el('map-expand').setAttribute('aria-expanded','true');redrawMap();el('map-expand').focus();};
 el('map-dialog').oncancel=e=>{e.preventDefault();closeMap();};
 el('map').onkeydown=e=>{
  if(e.target!==el('map'))return;
  if(e.key==='+'||e.key==='='){e.preventDefault();zoomMap(1.5);}
  else if(e.key==='-'){e.preventDefault();zoomMap(1/1.5);}
  else if(e.key==='0'){e.preventDefault();mapZoom=1;mapX=mapY=0;redrawMap();}
  else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)&&mapZoom>1){e.preventDefault();const step=40/mapZoom;mapX+=e.key==='ArrowLeft'?-step:e.key==='ArrowRight'?step:0;mapY+=e.key==='ArrowUp'?-step:e.key==='ArrowDown'?step:0;applyMapCamera();}
 };
 el('map').addEventListener('wheel',e=>{if(!(mapExpanded||e.ctrlKey||e.metaKey))return;e.preventDefault();zoomMap(e.deltaY<0?1.15:1/1.15,mapPoint(e));},{passive:false});
 el('map').onpointerdown=e=>{if(mapZoom<=1||e.button!==0)return;const matrix=el('map').getScreenCTM();mapDrag={id:e.pointerId,x:e.clientX,y:e.clientY,startX:mapX,startY:mapY,scale:Math.hypot(matrix.a,matrix.b),moved:false};};
 el('map').onpointermove=e=>{if(!mapDrag||mapDrag.id!==e.pointerId)return;const dx=e.clientX-mapDrag.x,dy=e.clientY-mapDrag.y;if(!mapDrag.moved&&Math.hypot(dx,dy)>5){mapDrag.moved=true;el('map').setPointerCapture(e.pointerId);}if(mapDrag.moved){mapX=mapDrag.startX-dx/mapDrag.scale;mapY=mapDrag.startY-dy/mapDrag.scale;applyMapCamera();}};
 const endPan=e=>{if(!mapDrag||mapDrag.id!==e.pointerId)return;mapSuppressClick=mapDrag.moved;mapDrag=null;if(el('map').hasPointerCapture(e.pointerId))el('map').releasePointerCapture(e.pointerId);setTimeout(()=>mapSuppressClick=false,0);};
 el('map').onpointerup=endPan;el('map').onpointercancel=endPan;
 el('map').addEventListener('click',e=>{if(mapSuppressClick){e.preventDefault();e.stopImmediatePropagation();}},{capture:true});
 el('geography').onchange=e=>{geography=e.target.value;refreshGroups();};
 el('fast').onclick=()=>{method='fast';choose();};el('beast').onclick=()=>{method='beast';choose();};el('analysis').onchange=e=>{key=e.target.value;choose();};el('segment').onchange=e=>{segment=e.target.value;key=primaryAnalysisId(model,segment);choose();};el('return-primary').onclick=()=>{key=primaryAnalysisId(model,segment);choose();};el('target').onchange=e=>selectLocation(e.target.value);el('view').onchange=e=>{viewMode=e.target.value;render();};el('uncertainty-controls').ontoggle=()=>{if(!el('uncertainty-controls').open&&viewMode!=='summary'){viewMode='summary';el('view').value='summary';render();}};
 const chooseDraw=n=>{if(!pre)return;drawIndex=Math.max(0,Math.min(pre.N-1,Number.isFinite(n)?n:0));render();};el('previous').onclick=()=>chooseDraw(drawIndex-1);el('next').onclick=()=>chooseDraw(drawIndex+1);el('draw').onchange=e=>chooseDraw(Math.round(Number(e.target.value))-1);
 el('time').oninput=e=>{if(!pre)return;stop();time=pre.min+(pre.max-pre.min)*Number(e.target.value)/1000;render();};el('full-time').onclick=()=>{if(pre){stop();time=pre.max;render();}};
 el('play').onclick=()=>{if(!pre)return;if(playing){stop();return;}if(time>=pre.max)time=pre.min;playing=true;el('play').textContent='Pause';timer=setInterval(()=>{time=Math.min(pre.max,time+(pre.max-pre.min)/140*Number(el('speed').value));render();if(time>=pre.max)stop();},150);};
 // Recompute only drawing geometry when the map panel changes width.
 if(typeof ResizeObserver!=='undefined'){
  let mapSize='';const observer=new ResizeObserver(entries=>{const {width,height}=entries[0].contentRect,size=Math.round(width)+'x'+Math.round(height);if(width>0&&height>0&&size!==mapSize){mapSize=size;redrawMap();}});observer.observe(el('map'));
 }
 choose();
}
})(typeof globalThis!=='undefined'?globalThis:this);
