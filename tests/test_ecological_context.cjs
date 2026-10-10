const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
class Element {
  constructor(name='div') { this.name=name; this.children=[]; this.attributes={}; this.nodes=new Map(); this.textContent=''; this.html=''; }
  setAttribute(k,v) { this.attributes[k]=String(v); }
  appendChild(n) { this.children.push(n); }
  addEventListener(k,f) { (this.listeners ||= {})[k]=f; }
  set innerHTML(s) { this.html=s; this.children=[]; this.nodes.clear(); this.textContent=''; }
  get innerHTML() { return this.html; }
  querySelector(s) { if (!this.nodes.has(s)) this.nodes.set(s,new Element()); return this.nodes.get(s); }
  fire(k,extra={}) { assert.ok(this.listeners?.[k],`Missing listener: ${k}`); this.listeners[k]({target:this,button:0,pointerId:1,preventDefault(){},...extra}); }
  createSVGPoint() { return {x:0,y:0,matrixTransform(){return {x:this.x,y:this.y};}}; }
  getScreenCTM() { return {inverse(){return {};}}; }
  setPointerCapture() { this.capture=true; }
  hasPointerCapture() { return this.capture; }
  releasePointerCapture() { this.capture=false; }
}
const sandbox=vm.createContext({document:{readyState:'complete',querySelectorAll:()=>[],createElement:n=>new Element(n),createElementNS:(_,n)=>new Element(n)}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../scripts/report/surveillance-explorer.js'),'utf8').replace('  const initialize = () => {','  globalThis.ExplorerForTest = Explorer;\n  const initialize = () => {'),sandbox);
const Explorer=sandbox.ExplorerForTest; Explorer.prototype.render=function(){};
function app() {
  const a=new Explorer({}, {samples:[{sample_id:'s',country:'US',state:'Arizona',collection_date:'2025-04-02',latitude:33.45,longitude:-112.07,has_coordinates:true,host:'Host A'}],
    ebird_contexts:[{sample_ids:['s'],host:'Host A',species:'Fixture host',reporting_checklists:2,complete_checklists:10,date_from:'2025-03-01',date_to:'2025-05-01',state:'AZ',country:'US',release:'fixture'}],
    ecological_context:{states:{AZ:'Arizona',TN:'Tennessee'},created_at:'fixture',window_days:30,bindings:{s:{status:'READY',weather_key:'w'}},
      weather:{w:{dataset:'ERA5',resolution:'0.25°',timezone:'America/Phoenix',grid_latitude:33.5,grid_longitude:-112.0,source_url:'https://open-meteo.com/',rows:[
        {date:'2025-04-01',temperature_2m_mean:-2,precipitation_sum:0,wind_speed_10m_max:5},
        {date:'2025-04-02',temperature_2m_mean:null,precipitation_sum:null,wind_speed_10m_max:null},
        {date:'2025-04-03',temperature_2m_mean:20,precipitation_sum:2,wind_speed_10m_max:8}]}},
      birdcast:{status:'READY',source_url:'https://dashboard.birdcast.org/',records:[
        {state_code:'AZ',date:'2025-04-01',timezone:'America/Phoenix',birds_crossed:0,status:'AVAILABLE'},
        {state_code:'AZ',date:'2025-04-02',timezone:'America/Phoenix',birds_crossed:null,status:'UNAVAILABLE',reason:'Radar gap'},
        {state_code:'TN',date:'2025-04-01',timezone:'America/Chicago',birds_crossed:999999,status:'AVAILABLE'}]}}});
  a.ecologyNode=new Element(); a.ebirdPanelNode=new Element(); a.ebirdNode=new Element();
  a.selectedSampleId='s'; a.ecologyDays=7;
  return a;
}
test('automatic BirdCast binding links to its matched night and rejects stale metadata',()=>{
  const a=app();
  a.ecology.birdcast.night_offset_days=-1;
  a.ecology.birdcast.bindings={s:{status:'AVAILABLE',night:'2025-04-01'}};
  a.renderEcology();
  const node=a.ecologyNode.querySelector('.wse-ecology-birdcast');
  assert.match(node.innerHTML,/US-AZ\?night=2025-04-01/);
  assert.match(node.innerHTML,/preceding collection date/);
  a.ecology.birdcast.bindings.s={status:'STALE_METADATA',reason:'Rebuild snapshot'};
  a.renderEcology();
  assert.match(node.innerHTML,/Rebuild snapshot/);
  assert.doesNotMatch(node.innerHTML,/wse-ecology-chart/);
});
test('selected sample aligns axes and retains the original eBird denominator/window',()=>{
  const a=app(); a.renderEbird(); a.renderEcology();
  assert.match(a.ebirdNode.innerHTML,/2 of 10/);
  assert.match(a.ebirdNode.innerHTML,/20.0%/);
  assert.match(a.ecologyNode.querySelector('.wse-ecology-intro').innerHTML,/2025-03-26 through 2025-04-09/);
  const ebird=a.ecologyNode.querySelector('.wse-ecology-ebird-charts');
  assert.match(ebird.children[0].textContent,/2025-03-01 through 2025-05-01 is one aggregate window/);
  const weather=a.ecologyNode.querySelector('.wse-ecology-weather');
  const bird=a.ecologyNode.querySelector('.wse-ecology-birdcast');
  const charts=[ebird.children.find(n=>n.name==='svg'),bird.querySelector('.wse-ecology-chart').children[0],weather.querySelector('[data-weather-chart="temperature_2m_mean"]').children.find(n=>n.name==='svg')];
  const markers=charts.map(svg=>svg.children.find(n=>n.attributes.class==='wse-outbreak-sample-date').attributes.x1);
  assert.equal(new Set(markers).size,1);
  for (const chart of charts) assert.equal(chart.children.find(n=>n.textContent==='2025-03-26').attributes.x,'76');
});
test('BirdCast state matching excludes other states and preserves zero and gaps',()=>{
  const a=app(); a.renderEcology(); const bird=a.ecologyNode.querySelector('.wse-ecology-birdcast');
  assert.match(bird.innerHTML,/1 of 2 imported nights/);
  assert.match(bird.innerHTML,/Radar gap/);
  assert.doesNotMatch(bird.innerHTML,/999,999|999999/);
  const svg=bird.querySelector('.wse-ecology-chart').children[0];
  assert.equal(svg.children.filter(n=>n.attributes.stroke==='#006DAE').length,1);
  assert.equal(svg.children.filter(n=>n.name==='rect').length,0);
});
test('weather labels distinguish units, returned grid, timezone and missing values',()=>{
  const a=app(); a.renderEcology(); const weather=a.ecologyNode.querySelector('.wse-ecology-weather');
  assert.match(weather.innerHTML,/Returned grid location: 33.5, -112/);
  assert.match(weather.innerHTML,/America\/Phoenix/);
  assert.match(weather.innerHTML,/Unavailable/);
  const target=weather.querySelector('[data-weather-chart="temperature_2m_mean"]');
  assert.match(target.children[0].textContent,/2\/15 days with values/);
  assert.equal(target.children[1].children.filter(n=>n.name==='rect').length,2);
});
test('state-only samples retain migration while explaining absent point weather',()=>{
  const a=app(); const sample=a.samples[0]; sample.has_coordinates=false; sample.latitude=sample.longitude=null;
  a.ecology.bindings.s={status:'MISSING_COORDINATES',reason:'Valid sample coordinates are required.'}; a.renderEcology();
  assert.match(a.ecologyNode.querySelector('.wse-ecology-birdcast').innerHTML,/State-level radar/);
  assert.match(a.ecologyNode.querySelector('.wse-ecology-weather').innerHTML,/no state-centroid/);
});
test('no selection, invalid date and stale weather cannot leave old plots visible',()=>{
  const a=app(); a.renderEcology(); a.selectedSampleId=null; a.renderEcology();
  assert.match(a.ecologyNode.querySelector('.wse-ecology-intro').textContent,/Select a WINGS sample/);
  assert.equal(a.ecologyNode.querySelector('.wse-ecology-birdcast').nodes.size,0);
  a.selectedSampleId='s'; a.samples[0].collection_date='2025-02-30'; a.renderEcology();
  assert.match(a.ecologyNode.querySelector('.wse-ecology-intro').textContent,/valid collection date/);
  a.samples[0].collection_date='2025-04-02'; a.ecology.bindings.s={status:'STALE_METADATA',reason:'Sample date or location changed; rebuild.'}; a.renderEcology();
  assert.match(a.ecologyNode.querySelector('.wse-ecology-weather').innerHTML,/rebuild/);
});
test('Canada and Alaska are explicitly outside this state pilot',()=>{
  const a=app(); a.samples[0].country='Canada'; a.renderEcology();
  assert.match(a.ecologyNode.querySelector('.wse-ecology-birdcast').innerHTML,/contiguous United States/);
  a.samples[0].country='US'; a.samples[0].state='AK'; a.ecology.states.AK='Alaska'; a.renderEcology();
  assert.match(a.ecologyNode.querySelector('.wse-ecology-birdcast').innerHTML,/contiguous United States/);
});
test('imported labels are escaped and source links reject executable schemes',()=>{
  const a=app(); a.ecology.birdcast.citation='<img src=x>'; a.ecology.birdcast.source_url='javascript:alert(1)'; a.renderEcology();
  const html=a.ecologyNode.querySelector('.wse-ecology-birdcast').innerHTML;
  assert.match(html,/&lt;img src=x&gt;/); assert.doesNotMatch(html,/<img|javascript:/);
});
test('Display window follows Migration Weave and eBird while duplicate source panels stay hidden',()=>{
  const a=app();a.migrationWeaveNode=new Element();
  a.renderEcology();
  assert.equal(a.ecologyNode.querySelector('.wse-ecology-weather-panel').hidden,false);
  assert.match(a.ecologyNode.querySelector('.wse-ecology-weather').innerHTML,/ERA5/);
  a.ecology.birdcast.bindings={s:{status:'AVAILABLE',state_code:'AZ',night:'2025-04-01'}};
  a.ecology.birdcast.seasons=[{key:'spring',state_code:'AZ',label:'Spring 2025',metric:'cumulative_birds_crossed',start_date:'2025-03-01',end_date:'2025-06-15',
    rows:Array.from({length:107},(_,i)=>({date:new Date(Date.UTC(2025,2,1)+i*86400000).toISOString().slice(0,10),cumulative_birds:(i+1)*100}))}];
  a.setEcologyDays(7);
  for(const source of ['birdcast','weather']){
    assert.equal(a.ecologyNode.querySelector(`.wse-ecology-${source}-panel`).hidden,true);
    assert.equal(a.ecologyNode.querySelector(`.wse-ecology-${source}`).innerHTML,'');
  }
  assert.ok(a.ecologyNode.querySelector('.wse-ecology-ebird-charts').children.length);
  assert.match(a.migrationWeaveNode.innerHTML,/Zoomed to 2025-03-26 through 2025-04-09/);
  assert.match(a.ecologyNode.querySelector('.wse-ecology-intro').innerHTML,/2025-03-26 through 2025-04-09/);
  a.setEcologyDays(30);assert.match(a.migrationWeaveNode.innerHTML,/Zoomed to 2025-03-03 through 2025-05-02/);
  a.setEcologyDays(90);assert.match(a.migrationWeaveNode.innerHTML,/Zoomed to 2025-03-01 through 2025-06-15/);
  const select=a.ecologyNode.querySelector('.wse-ecology-days');assert.equal(select.disabled,false);assert.equal(select.value,'90');
  a.selectedSampleId=null;a.renderEcology();assert.equal(select.disabled,true);assert.match(select.title,/Select a sample/);
  assert.equal(a.ecologyNode.querySelector('.wse-ecology-weather-panel').hidden,true);
  a.ecology.birdcast.seasons=[];a.selectedSampleId='s';a.renderEcology();
  assert.equal(a.ecologyNode.querySelector('.wse-ecology-weather-panel').hidden,false);
  assert.match(a.ecologyNode.querySelector('.wse-ecology-weather').innerHTML,/ERA5/);
});

// Synthetic daily values with the dates/source totals from the reported mismatch.
function linkedApp() {
  const a=app(),sample=a.samples[0],day=86400000;
  Object.assign(sample,{state:'Kentucky',collection_date:'2025-10-27',host:'Black Vulture',latitude:38,longitude:-85});
  Object.assign(a.ebirdContexts[0],{state:'KY',host:'Black Vulture',species:'Black Vulture',date_from:'2025-09-27',date_to:'2025-11-26',reporting_checklists:1017,complete_checklists:6576});
  a.ecologyDays=90;
  a.ecology.states.KY='Kentucky';
  a.ecology.birdcast.night_offset_days=-1;
  a.ecology.birdcast.bindings={s:{status:'AVAILABLE',state_code:'KY',night:'2025-10-26'}};
  a.ecology.birdcast.seasons=[{key:'fall',state_code:'KY',label:'Fall 2025',metric:'cumulative_birds_crossed',start_date:'2025-08-01',end_date:'2025-11-15',
    rows:Array.from({length:107},(_,i)=>({date:new Date(Date.UTC(2025,7,1)+i*day).toISOString().slice(0,10),cumulative_birds:(i+1)**2*100}))}];
  Object.assign(a.ecology.weather.w,{units:{temperature_2m_mean:'°C',precipitation_sum:'mm',wind_speed_10m_max:'km/h'},
    rows:Array.from({length:61},(_,i)=>({date:new Date(Date.UTC(2025,8,27)+i*day).toISOString().slice(0,10),temperature_2m_mean:12,temperature_2m_min:8,temperature_2m_max:16,precipitation_sum:1,wind_speed_10m_max:5,weather_code:3}))});
  a.migrationWeaveNode=new Element();
  a.renderEbird();a.renderEcology();
  return a;
}
const weave=(a,selector)=>a.migrationWeaveNode.querySelector(selector);
const ebirdCharts=a=>a.ecologyNode.querySelector('.wse-ecology-ebird-charts');
const ebirdSVG=a=>ebirdCharts(a).children.find(n=>n.name==='svg');
const intro=a=>a.ecologyNode.querySelector('.wse-ecology-intro').innerHTML;
const selectionBand=a=>ebirdSVG(a)?.children.find(n=>n.attributes['data-ecology']==='range-highlight');
function chooseDates(a,from,through) {
  const input=weave(a,'[data-wmw="from"]');input.value=from;
  weave(a,'[data-wmw="through"]').value=through;input.fire('change');
}

test('eBird and weather use linked display/selected dates while source totals retain their actual period',()=>{
  const a=linkedApp(),original=JSON.stringify(a.ebirdContexts);
  weave(a,'[data-wmw="weather"]').fire('click');
  chooseDates(a,'2025-10-01','2025-11-12');
  assert.match(intro(a),/Display: 2025-08-01 through 2025-11-15/);
  assert.match(intro(a),/Selected dates: 2025-10-01 through 2025-11-12/);
  assert.match(weave(a,'.wmw-weather').querySelector('.wmw-weather-summary').textContent,/2025-10-01.*2025-11-12/);
  const band=selectionBand(a);assert.ok(Number(band.attributes.width)>0);
  assert.match(band.children[0].textContent,/2025-10-01 through 2025-11-12/);
  assert.match(a.ebirdNode.innerHTML,/15.5%/);assert.match(a.ebirdNode.innerHTML,/1,017 of 6,576/);
  assert.match(a.ebirdNode.innerHTML,/Source period:/);
  assert.match(ebirdCharts(a).children[0].textContent,/2025-09-27 through 2025-11-26 is one aggregate window/);
  assert.match(ebirdCharts(a).children[1].textContent,/unavailable.*period totals, not daily checklist counts/);
  assert.equal(JSON.stringify(a.ebirdContexts),original);
});

test('weather pointer dragging refreshes eBird without replacing the captured weather or migration SVG',()=>{
  const a=linkedApp();weave(a,'[data-wmw="weather"]').fire('click');
  const main=weave(a,'.wmw-chart').children[0];
  const weather=weave(a,'.wmw-weather').querySelector('.wmw-weather-chart').children[0];
  const overlay=weather.children.find(n=>n.listeners?.pointerdown);
  const x=date=>70+(Date.parse(date+'T00:00:00Z')-Date.UTC(2025,7,1))/(106*86400000)*1000;
  const oldEbird=ebirdSVG(a);
  overlay.fire('pointerdown',{clientX:x('2025-10-01'),clientY:80});
  overlay.fire('pointermove',{clientX:x('2025-11-12'),clientY:80});
  assert.equal(overlay.capture,true);
  assert.match(intro(a),/Selected dates: 2025-10-01 through 2025-11-12/);
  assert.notEqual(ebirdSVG(a),oldEbird);
  assert.equal(weave(a,'.wmw-chart').children[0],main);
  assert.equal(weave(a,'.wmw-weather').querySelector('.wmw-weather-chart').children[0],weather);
  overlay.fire('pointerup',{clientX:x('2025-11-12'),clientY:80});
  assert.equal(overlay.capture,false);
  assert.equal(weave(a,'[data-wmw="from"]').value,'2025-10-01');
  assert.equal(weave(a,'[data-wmw="through"]').value,'2025-11-12');
});

test('axis, weather, reset and display controls preserve or reset the same linked dates in eBird',()=>{
  const a=linkedApp();chooseDates(a,'2025-10-01','2025-11-12');
  for(const control of ['progress','weather','calendar','weather']) {
    weave(a,`[data-wmw="${control}"]`).fire('click');
    assert.match(intro(a),/Selected dates: 2025-10-01 through 2025-11-12/);
    assert.ok(selectionBand(a));
  }
  weave(a,'[data-wmw="reset"]').fire('click');
  assert.match(intro(a),/Selected dates: 2025-08-01 through 2025-11-15 \(full displayed window\)/);
  assert.equal(selectionBand(a),undefined);
  a.setEcologyDays(7);
  assert.match(intro(a),/Display: 2025-10-20 through 2025-11-03/);
  assert.match(intro(a),/Selected dates: 2025-10-20 through 2025-11-03/);
  a.setEcologyDays(90);
  assert.match(intro(a),/Display: 2025-08-01 through 2025-11-15/);
  assert.doesNotMatch(intro(a),/2025-07-29|2026-01-25/);
  weave(a,'[data-wmw="whole"]').fire('click');
  assert.match(intro(a),/Display: 2025-08-01 through 2025-11-15/);
});

test('nonoverlap and single-day selection stay explicit without assigning the aggregate to a selected day',()=>{
  const a=linkedApp();chooseDates(a,'2025-08-01','2025-08-02');
  assert.match(ebirdCharts(a).children[1].textContent,/selected dates do not overlap.*source period/);
  chooseDates(a,'2025-11-15','2025-11-15');
  const band=selectionBand(a);
  assert.ok(Number(band.attributes.width)>0);
  assert.equal(Number(band.attributes.x)+Number(band.attributes.width),875);
  assert.match(ebirdCharts(a).children[1].textContent,/separate eBird frequency.*unavailable/);
  assert.match(a.ebirdNode.innerHTML,/15.5%/);
});

test('missing weave data or sample selection clears linked dates; off-axis collections have no stray marker',()=>{
  const a=linkedApp();chooseDates(a,'2025-10-01','2025-11-12');
  a.samples[0].collection_date='2025-12-01';a.renderEcology();
  assert.equal(ebirdSVG(a).children.some(n=>n.attributes.class==='wse-outbreak-sample-date'),false);
  a.selectedSampleId=null;a.renderEcology();
  assert.equal(ebirdCharts(a).children.length,0);
  a.selectedSampleId='s';a.samples[0].collection_date='2025-10-27';a.ecology.birdcast.seasons=[];a.renderEcology();
  assert.equal(a.migrationWeaveWindow,null);
  assert.match(intro(a),/Display: 2025-07-29 through 2026-01-25/);
  assert.doesNotMatch(intro(a),/Selected dates:/);
  assert.equal(selectionBand(a),undefined);
});
