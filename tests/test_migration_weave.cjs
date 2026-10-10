// Pure calculations plus a small DOM harness for the offline UI callbacks.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element {
  constructor(tag='div') {this.tag=tag;this.children=[];this.attrs={};this.nodes=new Map();this.listeners=new Map();this._html='';this._text='';this.value='';this.capture=false;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  getAttribute(k){return this.attrs[k];}
  set innerHTML(v){this._html=v;this.children=[];this.nodes.clear();this._text='';}
  get innerHTML(){return this._html;}
  set textContent(v){this._text=String(v);this._html='';this.children=[];this.nodes.clear();}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  appendChild(c){this.children.push(c);return c;}
  append(...cs){cs.forEach(c=>this.appendChild(c));}
  addEventListener(k,f){this.listeners.set(k,f);}
  fire(k,extra={}){const f=this.listeners.get(k);assert.ok(f,`Missing listener: ${k}`);return f({target:this,button:0,pointerId:1,preventDefault(){},...extra});}
  querySelector(s){
    if(this.nodes.has(s))return this.nodes.get(s);
    let match;
    if(s.startsWith('.')) match=new RegExp(`<([a-z]+)[^>]*class="[^"]*\\b${s.slice(1)}\\b[^"]*"[^>]*>`).exec(this._html);
    else if(s.startsWith('[')) match=new RegExp(`<([a-z]+)[^>]*${s.slice(1,-1)}[^>]*>`).exec(this._html);
    else match=new RegExp(`<(${s})(?:\\s[^>]*)?>`).exec(this._html);
    if(match){const n=new Element(match[1]);this.nodes.set(s,n);return n;}
    for(const child of this.children){if(child.tag===s)return child;const n=child.querySelector(s);if(n)return n;}
    return null;
  }
  createSVGPoint(){return {x:0,y:0,matrixTransform(){return {x:this.x,y:this.y};}};}
  getScreenCTM(){return {inverse(){return {};}};}
  setPointerCapture(){this.capture=true;}
  hasPointerCapture(){return this.capture;}
  releasePointerCapture(){this.capture=false;}
}
const code=fs.readFileSync(path.join(__dirname,'../scripts/report/surveillance-explorer.js'),'utf8');
const fragment=code.slice(code.indexOf('/* WINGS_MIGRATION_WEAVE_JS_BEGIN */'),code.indexOf('/* WINGS_MIGRATION_WEAVE_JS_END */'));
const context=vm.createContext({document:{createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t)}});
vm.runInContext(fragment,context);
const {render,followWindow,_test:{model,eventsFor,windowStats,viewport,condition,weatherContext,weatherChoices,weatherDays,weatherSummary}}=context.WINGS_MIGRATION_WEAVE;
function season(values=[40,100,100,200]){
  return {schema_version:1,key:'US-KY_2025-10-01_2025-10-04',state_code:'KY',label:'Fall 2025',metric:'cumulative_birds_crossed',start_date:'2025-10-01',end_date:'2025-10-04',
    rows:values.map((n,i)=>({date:`2025-10-0${i+1}`,cumulative_birds:n,mean_birds_aloft:99999})),retrieved_at:'fixture'};
}
function app(s=season()){
  const a={migrationWeaveNode:new Element(),hostFilter:'ALL',selectedSampleId:null,ecologyDays:30,
    samples:[{sample_id:'a',collection_date:'2025-10-03',host:'Duck'},{sample_id:'b',collection_date:'2025-10-03',host:'Duck'},{sample_id:'c',collection_date:'2025-10-04',host:'Goose'}],
    ecology:{states:{KY:'Kentucky'},birdcast:{seasons:[s],night_offset_days:-1,records:[{date:'2025-10-02',state_code:'KY',status:'AVAILABLE',birds_crossed:60}],bindings:{
      a:{night:'2025-10-02',state_code:'KY',status:'AVAILABLE'},b:{night:'2025-10-02',state_code:'KY',status:'AVAILABLE'},c:{night:'2025-10-03',state_code:'KY',status:'AVAILABLE'}}}},
    ecologyWindow(){
      const sample=this.samples.find(s=>s.sample_id===this.selectedSampleId);
      if(!sample)return null;
      const center=Date.parse(sample.collection_date+'T00:00:00Z');
      return {sample,center,start:center-this.ecologyDays*86400000,end:center+this.ecologyDays*86400000};
    },
    selectSample(id){this.selectedSampleId=id;this.selectedCalls=(this.selectedCalls||0)+1;render(this);}};
  return a;
}
const q=(a,s)=>a.migrationWeaveNode.querySelector(s);
const svg=a=>q(a,'.wmw-chart').children[0];
const groups=a=>svg(a).children.filter(n=>n.attrs.class==='wmw-event');

test('crossings use cumulative increments, never birds aloft or the sum of cumulative totals',()=>{
  const m=model(season());assert.equal(m.total,200);assert.deepEqual(Array.from(m.days,d=>d.value),[40,60,0,100]);
  assert.equal(m.complete,true);assert.equal(m.days[1].phase,.5);
});
test('gaps disable progress and do not become zero or a multi-day pulse',()=>{
  const m=model(season([40,null,100,200]));assert.equal(m.days[1].value,null);assert.equal(m.days[2].value,null);
  assert.equal(m.progressAvailable,false);assert.equal(m.coverage,2);
  assert.equal(windowStats(m,[],'2025-10-01','2025-10-04').share,null);
});
test('unfinished seasons use only the observed denominator and retain a missing tail',()=>{
  const m=model(season([40,100]));assert.equal(m.complete,false);assert.equal(m.total,100);assert.equal(m.days[1].phase,1);
  assert.equal(m.days[2].phase,null);assert.equal(m.progressAvailable,true);
});
test('all-zero passage is available but has no progress denominator',()=>{
  const m=model(season([0,0,0,0]));assert.equal(m.coverage,4);assert.equal(m.complete,true);assert.equal(m.progressAvailable,false);
});
test('invalid dates and nonmonotonic, duplicate or negative values fail closed',()=>{
  for(const value of [-1,true,NaN])assert.equal(model(season([40,value,100,200])),null);
  assert.equal(model(season([40,39,100,200])),null);
  const s=season();s.rows[1].date='2025-10-01';assert.equal(model(s),null);
  s.start_date='2025-99-99';assert.equal(model(s),null);
});
test('same-night samples form one event and stale metadata never supplies a ribbon',()=>{
  const a=app(),m=model(season());assert.equal(eventsFor(a,m).length,2);assert.equal(eventsFor(a,m)[0].samples.length,2);
  a.ecology.birdcast.bindings.b.status='STALE_METADATA';assert.equal(eventsFor(a,m)[0].samples.length,1);
  a.hostFilter='Duck';assert.equal(eventsFor(a,m).length,1);
});
test('window shares count unique events and preserve a genuine zero night',()=>{
  const a=app(),m=model(season()),e=eventsFor(a,m),stats=windowStats(m,e,'2025-10-02','2025-10-03');
  assert.equal(stats.events,2);assert.equal(stats.sum,60);assert.equal(stats.share,.3);assert.equal(stats.available,2);
});
test('calendar/progress controls and scale changes retain the selected date window',()=>{
  const a=app();render(a);const from=q(a,'[data-wmw="from"]'),to=q(a,'[data-wmw="through"]');
  from.value='2025-10-02';to.value='2025-10-03';from.fire('change');
  assert.match(q(a,'.wmw-window-summary').textContent,/30.0%/);
  q(a,'[data-wmw="progress"]').fire('click');assert.equal(a.migrationWeaveState.mode,'progress');
  assert.equal(q(a,'[data-wmw="from"]').value,'2025-10-02');
  const scale=q(a,'[data-wmw="scale"]');scale.value='sqrt';scale.fire('change');
  assert.match(a.migrationWeaveNode.innerHTML,/square-root height/);
  q(a,'[data-wmw="reset"]').fire('click');assert.equal(a.migrationWeaveState.range,null);
});
test('mouse and keyboard event activation link one actual sample through the Explorer',()=>{
  const a=app();render(a);groups(a)[0].fire('keydown',{key:'Enter'});
  assert.equal(a.selectedSampleId,'a');assert.match(q(a,'.wmw-detail').innerHTML,/Collected 2025-10-03 · 2 samples/);
  const select=q(a,'.wmw-detail').querySelector('select');select.value='b';select.fire('change');assert.equal(a.selectedSampleId,'b');
  const calls=a.selectedCalls;groups(a)[0].fire('click');assert.equal(a.selectedCalls,calls); // no accidental toggle off
});
test('pointer brushing follows dates and releases capture',()=>{
  const a=app();render(a);const overlay=svg(a).children.find(n=>n.attrs.fill==='transparent');
  overlay.fire('pointerdown',{clientX:403,clientY:80});overlay.fire('pointermove',{clientX:737,clientY:80});overlay.fire('pointerup',{clientX:737,clientY:80});
  assert.deepEqual(Array.from(a.migrationWeaveState.range),['2025-10-02','2025-10-03']);assert.equal(overlay.capture,false);
  assert.match(q(a,'.wmw-window-summary').textContent,/2 collection events/);
});
test('incomplete progress labels and unplaceable events stay explicit',()=>{
  const a=app(season([40,100]));render(a);q(a,'[data-wmw="progress"]').fire('click');
  assert.match(a.migrationWeaveNode.innerHTML,/observed passage through Oct 2/);
  assert.equal(groups(a).length,1);assert.match(q(a,'.wmw-pagination').textContent,/1 events have no observed progress position/);
});
test('no seasonal data and unrelated external selections cannot leave an old weave',()=>{
  const a=app();render(a);a.selectedSampleId='missing';render(a);assert.match(q(a,'.wmw-detail').textContent,/has no collection event/);
  a.ecology.birdcast.seasons=[];render(a);assert.match(a.migrationWeaveNode.innerHTML,/not included in this snapshot/);assert.equal(q(a,'.wmw-chart'),null);
});
test('untrusted labels and identifiers are escaped in HTML',()=>{
  const a=app();a.ecology.states.KY='<img src=x>';a.samples[0].sample_id='<script>';a.ecology.birdcast.bindings['<script>']=a.ecology.birdcast.bindings.a;
  a.selectedSampleId='<script>';render(a);
  assert.match(a.migrationWeaveNode.innerHTML,/&lt;img src=x&gt;/);assert.doesNotMatch(a.migrationWeaveNode.innerHTML,/<img src=x>/);
  assert.match(q(a,'.wmw-detail').innerHTML,/&lt;script&gt;/);assert.doesNotMatch(q(a,'.wmw-detail').innerHTML,/<script>/);
});

function fallApp(){
  const s=season();s.start_date='2025-08-01';s.end_date='2025-11-15';s.key='US-KY_2025-08-01_2025-11-15';
  s.rows=Array.from({length:107},(_,i)=>({date:new Date(Date.parse(s.start_date+'T00:00:00Z')+i*86400000).toISOString().slice(0,10),cumulative_birds:100*(i+1)}));
  const a=app(s);['2025-10-20','2025-10-21','2025-10-27'].forEach((date,i)=>{
    a.samples[i].collection_date=date;
    a.ecology.birdcast.bindings[a.samples[i].sample_id].night=new Date(Date.parse(date+'T00:00:00Z')-86400000).toISOString().slice(0,10);
  });
  a.selectedSampleId='c';return a;
}
test('sample window changes the actual chart dates and ribbons; Full season restores both',()=>{
  const a=fallApp();render(a);assert.equal(groups(a).length,3);
  a.ecologyDays=7;followWindow(a);render(a);
  assert.equal(q(a,'[data-wmw="from"]').value,'2025-10-20');
  assert.equal(q(a,'[data-wmw="through"]').value,'2025-11-03');assert.equal(groups(a).length,2);
  assert.ok(svg(a).children.some(n=>n.textContent==='Oct 20'));assert.ok(svg(a).children.some(n=>n.textContent==='Nov 3'));
  assert.match(a.migrationWeaveNode.innerHTML,/15 \/ 15/);
  q(a,'[data-wmw="whole"]').fire('click');assert.equal(groups(a).length,3);
  assert.equal(q(a,'[data-wmw="from"]').value,'2025-08-01');assert.equal(a.ecologyDays,7);
});
test('7, 30 and 90 day ranges use the collection date and clip at season bounds',()=>{
  const a=fallApp(),m=model(a.ecology.birdcast.seasons[0]);
  for(const [days,start,end,count] of [[7,'2025-10-20','2025-11-03',15],[30,'2025-09-27','2025-11-15',50],[90,'2025-08-01','2025-11-15',107]]){
    a.ecologyDays=days;const v=viewport(a,m,'sample');
    assert.equal(v.days[0].date,start);assert.equal(v.days.at(-1).date,end);assert.equal(v.days.length,count);
  }
});
test('progress zoom retains seasonal percentages and the same window share',()=>{
  const a=fallApp();a.ecologyDays=7;followWindow(a);render(a);
  const before=q(a,'.wmw-window-summary').textContent;
  q(a,'[data-wmw="progress"]').fire('click');
  assert.equal(q(a,'.wmw-window-summary').textContent,before);assert.match(before,/14.0% of full-season passage/);
  const labels=svg(a).children.filter(n=>n.tag==='text').map(n=>n.textContent);
  assert.ok(labels.includes('75.7%'));assert.ok(labels.includes('88.8%'));assert.ok(!labels.includes('100%'));
});
test('following another collection recenters and clears an old brush selection',()=>{
  const a=fallApp();a.ecologyDays=7;followWindow(a);render(a);
  a.migrationWeaveState.range=['2025-10-26','2025-10-28'];a.selectSample('a');
  assert.equal(q(a,'[data-wmw="from"]').value,'2025-10-13');assert.equal(q(a,'[data-wmw="through"]').value,'2025-10-27');
  assert.equal(a.migrationWeaveState.range,null);
});
test('no overlapping dates or stale metadata shows an explicit empty view with a working reset',()=>{
  const a=fallApp();a.samples[2].collection_date='2025-12-20';a.ecology.birdcast.bindings.c.night='2025-12-19';a.ecologyDays=7;
  followWindow(a);render(a);assert.match(a.migrationWeaveNode.innerHTML,/does not overlap this season/);assert.equal(q(a,'.wmw-chart'),null);
  q(a,'[data-wmw="whole"]').fire('click');assert.ok(svg(a));
  a.ecology.birdcast.bindings.c.status='STALE_METADATA';followWindow(a);render(a);assert.match(a.migrationWeaveNode.innerHTML,/current BirdCast metadata/);
});
test('a zoom entirely beyond observed passage keeps gaps and disables progress safely',()=>{
  const a=fallApp();a.ecology.birdcast.seasons[0].rows=a.ecology.birdcast.seasons[0].rows.slice(0,10);
  a.ecologyDays=7;followWindow(a);a.migrationWeaveState.mode='progress';render(a);
  assert.equal(a.migrationWeaveState.mode,'calendar');assert.match(a.migrationWeaveNode.innerHTML,/0 \/ 15/);
  assert.match(q(a,'.wmw-window-summary').textContent,/share unavailable/);
  for(const n of svg(a).children)assert.doesNotMatch(JSON.stringify(n.attrs),/NaN|Infinity/);
});

function weatherApp(){
  const a=fallApp();a.ecologyDays=7;
  a.samples.forEach(s=>{s.latitude=38.49;s.longitude=-84.58;});
  const rows=Array.from({length:61},(_,i)=>({date:new Date(Date.UTC(2025,8,27)+i*86400000).toISOString().slice(0,10),
    temperature_2m_mean:8+Math.sin(i/3)*5,temperature_2m_min:4+Math.sin(i/3)*5,temperature_2m_max:12+Math.sin(i/3)*5,
    precipitation_sum:i%6===0?8:0,wind_speed_10m_max:10+i%5,weather_code:[0,1,2,3,63,45][i%6]}));
  a.ecology.weather={w:{dataset:'ERA5',units:{temperature_2m_mean:'°C',temperature_2m_min:'°C',temperature_2m_max:'°C',precipitation_sum:'mm',wind_speed_10m_max:'km/h',weather_code:'wmo code'},rows,
    grid_latitude:38.5,grid_longitude:-84.5,timezone:'America/New_York',retrieved_at:'synthetic fixture',raw_sha256:'fixture'}};
  a.ecology.bindings=Object.fromEntries(a.samples.map(s=>[s.sample_id,{status:'READY',weather_key:'w'}]));
  followWindow(a);render(a);q(a,'[data-wmw="weather"]').fire('click');return a;
}
const weatherRoot=a=>q(a,'.wmw-weather');
const weatherSVG=a=>weatherRoot(a).querySelector('.wmw-weather-chart').children[0];
const weatherQ=(a,s)=>weatherRoot(a).querySelector(s);
test('weather toggle renders min/max, precipitation, wind, and offline vector icons',()=>{
  const a=weatherApp(),chart=weatherSVG(a);
  for(const field of ['temperature-range','temperature-mean','precipitation','wind'])assert.ok(chart.children.some(n=>n.attrs['data-weather']===field));
  assert.ok(chart.children.some(n=>n.attrs.role==='img'));assert.match(weatherRoot(a).innerHTML,/Daily weather at the selected collection location/);
  q(a,'[data-wmw="weather"]').fire('click');assert.equal(weatherRoot(a).innerHTML,'');
});
test('weather codes preserve clear sky zero and never infer sunshine from missing codes',()=>{
  assert.equal(condition(0)[1],'sun');assert.equal(condition(63)[1],'rain');assert.equal(condition(75)[1],'snow');
  for(const c of [null,undefined,'0',4,NaN])assert.equal(condition(c)[1],null);
  const a=weatherApp();for(const r of a.ecology.weather.w.rows)delete r.weather_code;
  render(a);assert.ok(!weatherSVG(a).children.some(n=>n.attrs.role==='img'));assert.match(weatherRoot(a).innerHTML,/no weather icons are inferred/);
});
test('seven-day averages require calendar continuity and use cached days before the visible window',()=>{
  const a=weatherApp(),m=model(a.ecology.birdcast.seasons[0]),days=viewport(a,m,'sample').days;
  let rows=weatherDays(a.ecology.weather.w,days);
  const first=Date.parse(rows[0].date+'T00:00:00Z');
  const expected=a.ecology.weather.w.rows.filter(r=>Date.parse(r.date+'T00:00:00Z')>=first-6*86400000 && Date.parse(r.date+'T00:00:00Z')<=first).reduce((n,r)=>n+r.temperature_2m_mean,0)/7;
  assert.equal(rows[0].average7,expected);
  a.ecology.weather.w.rows=a.ecology.weather.w.rows.filter(r=>r.date!==rows[0].date);
  rows=weatherDays(a.ecology.weather.w,days);assert.equal(rows[0].average7,null);assert.equal(rows[6].average7,null);assert.ok(Number.isFinite(rows[7].average7));
});
test('temperature smoothing adds a separate line and is stable across calendar/progress axes',()=>{
  const a=weatherApp(),checkbox=weatherQ(a,'[data-wmw="average7"]');checkbox.checked=true;checkbox.fire('change');
  assert.ok(weatherSVG(a).children.some(n=>n.attrs['data-weather']==='average7'));
  const day=weatherQ(a,'[data-wmw="weather-day"]');day.value='2025-10-27';day.fire('change');
  const before=weatherQ(a,'.wmw-weather-readout').textContent;
  q(a,'[data-wmw="progress"]').fire('click');assert.equal(weatherQ(a,'.wmw-weather-readout').textContent,before);
});
test('weather hover and keyboard date selection update the migration tooltip for exactly that date',()=>{
  const a=weatherApp();
  weatherSVG(a).children.find(n=>n.attrs.fill==='transparent').fire('pointermove',{clientX:70,clientY:120});
  assert.match(q(a,'.wmw-tip').textContent,/2025-10-20/);assert.match(weatherQ(a,'.wmw-weather-readout').textContent,/2025-10-20/);
  const select=weatherQ(a,'[data-wmw="weather-day"]');select.value='2025-10-28';select.fire('change');
  assert.match(q(a,'.wmw-tip').textContent,/2025-10-28/);
  svg(a).children.find(n=>n.attrs.fill==='transparent').fire('pointermove',{clientX:1070,clientY:100});
  assert.match(weatherQ(a,'.wmw-weather-readout').textContent,/2025-11-03/);
});
test('brushing updates weather summaries and preserves missing versus zero precipitation',()=>{
  const a=weatherApp();a.ecology.weather.w.rows.find(r=>r.date==='2025-10-20').precipitation_sum=null;render(a);
  const from=q(a,'[data-wmw="from"]'),through=q(a,'[data-wmw="through"]');from.value='2025-10-20';through.value='2025-10-21';from.fire('change');
  assert.match(weatherQ(a,'.wmw-weather-summary').textContent,/known precipitation 8 mm \(1\/2\)/);
  const m=model(a.ecology.birdcast.seasons[0]),days=weatherDays(a.ecology.weather.w,m.days);
  const summary=weatherSummary(days,'2025-10-22','2025-10-22');assert.equal(summary.precipitation,0);assert.equal(summary.precipitationDays,1);
});
test('stale or missing coordinates and different states never reuse the previous weather strip',()=>{
  const a=weatherApp();a.ecology.bindings.c={status:'STALE_METADATA',reason:'Rebuild changed metadata'};render(a);
  assert.match(weatherRoot(a).innerHTML,/Rebuild changed metadata/);assert.equal(weatherRoot(a).querySelector('.wmw-weather-chart'),null);
  a.ecology.bindings.c={status:'READY',weather_key:'w'};a.samples[2].latitude=null;render(a);assert.match(weatherRoot(a).innerHTML,/no valid coordinates/);
  a.samples[2].latitude=38.49;a.ecology.birdcast.bindings.c.state_code='AZ';
  assert.match(weatherContext(a,model(a.ecology.birdcast.seasons[0])).reason,/different region/);
});
test('changing collection uses its own weather context while keeping the layer enabled',()=>{
  const a=weatherApp();a.ecology.weather.other=JSON.parse(JSON.stringify(a.ecology.weather.w));
  a.ecology.weather.other.rows.forEach(r=>{r.temperature_2m_mean=20;r.temperature_2m_min=18;r.temperature_2m_max=23;});
  a.ecology.bindings.a={status:'READY',weather_key:'other'};a.selectSample('a');
  assert.equal(a.migrationWeaveState.weather,true);assert.match(weatherQ(a,'.wmw-weather-readout').textContent,/Mean 20 °C/);
});
test('legacy weather displays available values without invented min/max or icons',()=>{
  const a=weatherApp();a.ecology.weather.w.rows.forEach(r=>{delete r.temperature_2m_min;delete r.temperature_2m_max;delete r.weather_code;});
  render(a);assert.match(weatherRoot(a).innerHTML,/min\/max values are not present/);
  assert.ok(!weatherSVG(a).children.some(n=>n.attrs['data-weather']==='temperature-range'));
  assert.match(weatherQ(a,'.wmw-weather-readout').textContent,/Min Unavailable \/ max Unavailable/);
});
test('all missing weather and negative temperatures produce no invalid chart coordinates',()=>{
  const a=weatherApp();a.ecology.weather.w.rows.forEach(r=>{r.temperature_2m_min=-10;r.temperature_2m_mean=-5;r.temperature_2m_max=-1;});render(a);
  assert.match(weatherQ(a,'.wmw-weather-readout').textContent,/Mean -5 °C/);
  a.ecology.weather.w.rows=[];render(a);assert.match(weatherQ(a,'.wmw-weather-readout').textContent,/Precipitation Unavailable/);
  for(const n of weatherSVG(a).children)assert.doesNotMatch(JSON.stringify(n.attrs),/NaN|Infinity/);
});

test('numeric metadata strings show weather; empty, nonnumeric and out-of-range coordinates do not',()=>{
  const a=weatherApp(),s=a.samples[2];s.latitude='38.49';s.longitude='-84.58';s.has_coordinates=true;render(a);
  assert.ok(weatherSVG(a));assert.match(weatherQ(a,'.wmw-weather-readout').textContent,/Mean/);
  for(const bad of [null,undefined,'','  ',true,{},'no location','Infinity',NaN,91,-91]){
    s.latitude=bad;render(a);assert.equal(weatherRoot(a).querySelector('.wmw-weather-chart'),null);
  }
  s.latitude=38.49;s.longitude=181;render(a);assert.equal(weatherRoot(a).querySelector('.wmw-weather-chart'),null);
  s.longitude=0;s.latitude='0';render(a);assert.ok(weatherSVG(a));
  s.has_coordinates=false;render(a);assert.equal(weatherRoot(a).querySelector('.wmw-weather-chart'),null);
});
test('a sample without coordinates can switch directly to an explicitly chosen cached weather collection',()=>{
  const a=weatherApp();a.samples[2].latitude=null;a.ecology.bindings.c={status:'MISSING_COORDINATES'};render(a);
  assert.match(weatherRoot(a).innerHTML,/Sample c has no valid coordinates/);
  assert.equal(a.selectedSampleId,'c'); // No silent reassignment to another location.
  const picker=q(a,'[data-wmw="weather-sample"]');picker.value='a';picker.fire('change');
  assert.equal(a.selectedSampleId,'a');assert.equal(a.migrationWeaveState.weather,true);assert.ok(weatherSVG(a));
  assert.match(a.migrationWeaveNode.innerHTML,/Zoomed to 2025-10-13 through 2025-10-27/);
});
test('weather choices retain the selected member and exclude stale, wrong-season and host-filtered data',()=>{
  const a=weatherApp(),m=model(a.ecology.birdcast.seasons[0]);
  a.samples[1].collection_date=a.samples[0].collection_date;a.selectedSampleId='b';
  let choices=weatherChoices(a,m);assert.equal(choices.length,2);assert.equal(choices[0].count,2);assert.equal(choices[0].sample.sample_id,'b');
  a.ecology.bindings.a.status='STALE_METADATA';choices=weatherChoices(a,m);assert.equal(choices[0].count,1);
  a.ecology.birdcast.bindings.b.night='2026-04-07';assert.equal(weatherChoices(a,m).length,1);
  a.hostFilter='Duck';assert.equal(weatherChoices(a,m).length,0);
  render(a);assert.match(a.migrationWeaveNode.innerHTML,/No samples with cached weather/);
});
test('full-season weather remains visible with spaced condition icons and range boundaries clear on reset',()=>{
  const a=weatherApp();q(a,'[data-wmw="whole"]').fire('click');assert.ok(weatherSVG(a).children.some(n=>n.attrs.role==='img'));
  const from=q(a,'[data-wmw="from"]'),through=q(a,'[data-wmw="through"]');from.value='2025-10-20';through.value='2025-10-27';from.fire('change');
  const migrationMark=svg(a).children.find(n=>n.attrs['data-wmw']==='range-boundaries');
  const weatherMark=weatherSVG(a).children.find(n=>n.attrs['data-weather']==='range-boundaries');
  assert.ok(migrationMark.attrs.d);assert.ok(weatherMark.attrs.d);
  q(a,'[data-wmw="reset"]').fire('click');assert.equal(migrationMark.attrs.d,'');assert.equal(weatherMark.attrs.d,'');
});

test('dragging weather selects the same dates in both charts and updates date inputs and summaries',()=>{
  const a=weatherApp();
  const overlay=weatherSVG(a).children.find(n=>n.attrs.fill==='transparent');
  overlay.fire('pointerdown',{clientX:70,clientY:60});
  overlay.fire('pointermove',{clientX:570,clientY:190});
  overlay.fire('pointerup',{clientX:570,clientY:230});
  assert.deepEqual(Array.from(a.migrationWeaveState.range),['2025-10-20','2025-10-27']);
  assert.equal(q(a,'[data-wmw="from"]').value,'2025-10-20');assert.equal(q(a,'[data-wmw="through"]').value,'2025-10-27');
  assert.match(weatherQ(a,'.wmw-weather-summary').textContent,/Selected dates 2025-10-20–2025-10-27/);
  assert.match(q(a,'.wmw-window-summary').textContent,/8\/8 nights/);
  assert.ok(svg(a).children.find(n=>n.attrs['data-wmw']==='range-boundaries').attrs.d);
  assert.ok(weatherSVG(a).children.find(n=>n.attrs['data-weather']==='range-boundaries').attrs.d);
  assert.equal(overlay.capture,false);
});

test('either chart selects exact dates on a nonlinear progress axis with weather and smoothing enabled',()=>{
  for(const source of [svg,weatherSVG]){
    const a=weatherApp();a.ecology.birdcast.seasons[0].rows.forEach((r,i)=>{r.cumulative_birds=(i+1)**3;});
    a.migrationWeaveState.mode='progress';a.migrationWeaveState.weatherAverage=true;render(a);
    const m=model(a.ecology.birdcast.seasons[0]),days=viewport(a,m,'sample').days;
    const px=date=>70+(m.byDate.get(date).phase-days[0].phase)/(days.at(-1).phase-days[0].phase)*1000;
    const overlay=source(a).children.find(n=>n.attrs.fill==='transparent');
    overlay.fire('pointerdown',{clientX:px('2025-10-29'),clientY:80});
    overlay.fire('pointermove',{clientX:px('2025-10-23'),clientY:150});
    overlay.fire('pointerup',{clientX:px('2025-10-23'),clientY:150});
    assert.deepEqual(Array.from(a.migrationWeaveState.range),['2025-10-23','2025-10-29']);
    assert.match(weatherQ(a,'.wmw-weather-summary').textContent,/2025-10-23–2025-10-29/);
    q(a,'[data-wmw="weather"]').fire('click');q(a,'[data-wmw="weather"]').fire('click');
    assert.deepEqual(Array.from(a.migrationWeaveState.range),['2025-10-23','2025-10-29']);
  }
});
test('weather drag handles scaling, outside edges and missing days without changing the selected location',()=>{
  const a=weatherApp();a.ecology.weather.w.rows=a.ecology.weather.w.rows.filter(r=>r.date<'2025-10-21' || r.date>'2025-10-24');render(a);
  const chart=weatherSVG(a);chart.createSVGPoint=()=>({x:0,y:0,matrixTransform(){return {x:(this.x-120)/1.5,y:this.y};}});
  const overlay=chart.children.find(n=>n.attrs.fill==='transparent');
  overlay.fire('pointerdown',{clientX:120+1070*1.5,clientY:90});
  overlay.fire('pointerleave');assert.equal(overlay.capture,true);
  overlay.fire('pointermove',{clientX:-100,clientY:500});overlay.fire('pointerup',{clientX:-100,clientY:500});
  assert.deepEqual(Array.from(a.migrationWeaveState.range),['2025-10-20','2025-11-03']);
  assert.match(weatherQ(a,'.wmw-weather-summary').textContent,/11\/15 days/);
  assert.equal(a.selectedSampleId,'c');assert.equal(overlay.capture,false);
});
test('secondary pointers, cancellation and capture loss cannot leave a weather drag active',()=>{
  const a=weatherApp(),overlay=weatherSVG(a).children.find(n=>n.attrs.fill==='transparent');
  overlay.fire('pointerdown',{button:2,clientX:70,clientY:80});assert.equal(a.migrationWeaveState.range,null);
  overlay.fire('pointerdown',{pointerId:3,clientX:70,clientY:80});
  overlay.fire('pointermove',{pointerId:4,clientX:1070,clientY:80});assert.deepEqual(Array.from(a.migrationWeaveState.range),['2025-10-20','2025-10-20']);
  overlay.fire('pointercancel',{pointerId:3});assert.equal(overlay.capture,false);
  overlay.fire('pointermove',{pointerId:3,clientX:1070,clientY:80});assert.deepEqual(Array.from(a.migrationWeaveState.range),['2025-10-20','2025-10-20']);
  overlay.fire('pointerdown',{pointerId:7,clientX:570,clientY:80});overlay.releasePointerCapture(7);overlay.fire('lostpointercapture',{pointerId:7});
  overlay.fire('pointermove',{pointerId:7,clientX:1070,clientY:80});assert.deepEqual(Array.from(a.migrationWeaveState.range),['2025-10-27','2025-10-27']);
});

module.exports={Element,render,model,app,svg,groups,weatherApp,weatherSVG};
