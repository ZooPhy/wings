const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
class Element {
  constructor(name='div') { this.name=name; this.children=[]; this.attributes={}; this.nodes=new Map(); this.textContent=''; this.html=''; }
  setAttribute(k,v) { this.attributes[k]=String(v); }
  appendChild(n) { this.children.push(n); }
  set innerHTML(s) { this.html=s; this.children=[]; this.nodes.clear(); this.textContent=''; }
  get innerHTML() { return this.html; }
  querySelector(s) { if (!this.nodes.has(s)) this.nodes.set(s,new Element()); return this.nodes.get(s); }
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
  assert.match(bird.innerHTML,/1 of 15 nights/);
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
