const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Element {
  constructor(name) { this.name = name; this.children = []; this.attributes = {}; this.events = {}; this.style = {}; this.textContent = ''; this.classList = {add() {}}; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getAttribute(key) { return this.attributes[key]; }
  appendChild(child) { this.children.push(child); }
  append(...children) { this.children.push(...children); }
  set innerHTML(value) { this.html = value; this.children = []; }
  addEventListener(type, fn) { this.events[type] = fn; }
  querySelectorAll(selector) {
    const items = []; const walk = node => { node.children.forEach(child => { if (selector === '[data-region-country="USA"]' && child.attributes['data-region-country'] === 'USA') items.push(child); walk(child); }); }; walk(this); return items;
  }
  querySelector(selector) { return selector === 'title' ? this.children.find(n => n.name === 'title') : null; }
}
const context = vm.createContext({document: {readyState:'complete', querySelectorAll:()=>[], createElement:n=>new Element(n), createElementNS:(_,n)=>new Element(n)}});
const root = path.join(__dirname, '..');
vm.runInContext(fs.readFileSync(path.join(root, 'scripts/report/map-boundaries.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(root, 'scripts/report/surveillance-explorer.js'), 'utf8').replace('  const initialize = () => {', '  globalThis.ExplorerForTest = Explorer;\n  const initialize = () => {'), context);
const Explorer = context.ExplorerForTest; Explorer.prototype.render = function() {};
const rec = (id, state, collection, detected) => ({source_row:id, state_code:state, state, county:'Example', collection_date:collection, detected_date:detected, collection_date_raw:collection || 'Unknown', detected_date_raw:detected, species:'Mallard', geographic_precision:'county', strain:'H5', classification:'Wild bird', sampling_method:'Live bird', submitting_agency:'Example'});
function app() {
  return new Explorer({}, {samples:[{sample_id:'s', country:'USA', state:'Kentucky', collection_date:'2025-01-15', has_coordinates:false, host:'Mallard'}],
    outbreak_context: {status:'READY', states:{KY:'Kentucky',TN:'Tennessee'}, records:[rec(1,'KY','2025-01-01','2025-02-01'),rec(2,'KY','2025-01-01','2025-02-01'),rec(3,'KY',null,'2025-01-15'),rec(4,'TN','2025-01-10','2025-02-01')], date_ranges:{collection_date:{min:'2025-01-01',max:'2025-01-10'},detected_date:{min:'2025-01-15',max:'2025-02-01'}}, source_url:'https://www.aphis.usda.gov/',source_file:'example.csv',sha256:'abc123',record_count:4,repeated_rows_retained:1,unmapped_states:[],snapshot_date_basis:'Test fixture'}});
}
test('state fallback works without sample coordinates and retains repeated rows',()=>{
  const a=app(); a.selectedSampleId='s'; a.syncOutbreakDates(); const v=a.outbreakView();
  assert.equal(v.code,'KY'); assert.match(v.scopeLabel,/coordinates unavailable/);
  assert.equal(v.rows.length,2); assert.equal(v.undated,1);
  assert.equal(a.outbreakStart,'2024-12-16'); assert.equal(a.outbreakEnd,'2025-02-14');
});
test('unknown or non-US sample geography never silently falls back to a national match',()=>{
  const a=app(); a.selectedSampleId='s'; a.samples[0].country='Canada'; a.syncOutbreakDates();
  assert.equal(a.outbreakView().rows.length,0); assert.equal(a.outbreakView().blocked,true);
  a.samples[0].country='US'; a.samples[0].state='Unknown'; assert.equal(a.outbreakView().blocked,true);
  a.outbreakScope='all'; assert.equal(a.outbreakView().rows.length,3);
});
test('date basis and inclusive boundaries filter independently without imputation',()=>{
  const a=app(); a.outbreakScope='KY'; a.outbreakFollow=false; a.outbreakStart=a.outbreakEnd='2025-01-15';
  assert.equal(a.outbreakView().rows.length,0);
  a.outbreakBasis='detected_date'; assert.equal(a.outbreakView().rows.length,1); assert.equal(a.outbreakView().rows[0].source_row,3);
  a.outbreakStart='2025-03-01'; a.outbreakEnd='2025-04-01'; assert.equal(a.outbreakView().outsideSnapshot,true);
  a.outbreakEnd='2025-02-01'; assert.equal(a.outbreakView().validWindow,false);
  assert.equal(a.outbreakEpoch('2025-02-30'),null);
});
test('manual windows persist through sample selection and host filters do not filter detections',()=>{
  const a=app(); a.outbreakFollow=false; a.outbreakStart='2025-01-01'; a.outbreakEnd='2025-01-31';
  a.selectedSampleId='s'; a.hostFilter='Another host'; a.syncOutbreakDates();
  assert.equal(a.outbreakStart,'2025-01-01'); assert.equal(a.outbreakView().rows.length,2);
  a.selectedSampleId=null; assert.equal(a.outbreakView().rows.length,3);
});
test('map state totals and timeline bars reconcile to the filtered records',()=>{
  const a=app(); a.syncOutbreakDates(); const v=a.outbreakView();
  const map=layer(a);
  const paths=map.querySelectorAll('[data-region-country="USA"]');
  const ky=paths.find(p=>p.getAttribute('data-region-code')==='KY');
  assert.match(ky.getAttribute('aria-label'),/2 matching source records/);
  assert.match(ky.querySelector('title').textContent,/State-level aggregate/);
  const timeline=new Element('div'); a.renderOutbreakTimeline(timeline,v);
  const bars=timeline.children[0].children.filter(p=>p.name==='rect');
  assert.equal(bars.length,2); assert.equal(bars.reduce((sum,p)=>sum+Number(p.getAttribute('aria-label').match(/: (\d+)/)[1]),0),3);
  a.outbreakNode={querySelector:()=>null}; a.renderOutbreak=()=>{};
  const beforeWindow=[a.outbreakStart,a.outbreakEnd];
  bars[0].events.click();
  assert.deepEqual([a.outbreakStart,a.outbreakEnd],beforeWindow);
  assert.equal(a.outbreakSelectedStart,'2025-01-01');
  assert.equal(a.outbreakSelectedEnd,'2025-01-01');
  assert.equal(a.outbreakView().rows.length,3);
  ky.events.click(); assert.equal(a.outbreakScope,'KY');
});
test('rendered records disclose source precision, missing dates, repeats and source link limitations',()=>{
  const a=app(); a.outbreakNode={hidden:true,innerHTML:'',querySelector:()=>null};
  a.renderOutbreakTimeline=()=>{};
  a.outbreakContext.records[0].species='<img src=x>';
  a.renderOutbreak(); const html=a.outbreakNode.innerHTML;
  assert.match(html,/&lt;img src=x&gt;/); assert.doesNotMatch(html,/<img src=x>/);
  assert.match(html,/do not imply epidemiological linkage/);
  assert.match(html,/no unique record IDs or record-specific URLs/);
  assert.match(html,/state-level aggregates/); assert.match(html,/1 records in this geographic scope lack/);
  assert.match(html,/identical repeat rows retained/);
});

function layer(a) {
  const svg = new Element('svg');
  const bounds = [-95, -75, 30, 43];
  const {px, py} = a.mapProjection(bounds);
  a.drawMapBoundaries(svg, bounds, px, py, 900, 460);
  a.applyOutbreakLayer(svg);
  return svg;
}
function state(svg, code) {
  return svg.querySelectorAll('[data-region-country="USA"]').find(p => p.getAttribute('data-region-code') === code);
}

test('selected state focuses records but neighboring states retain their map counts', () => {
  const a=app(); a.selectedSampleId='s'; a.syncOutbreakDates();
  const svg=layer(a);
  assert.equal(a.outbreakView().rows.length,2);
  assert.match(state(svg,'KY').getAttribute('aria-label'),/2 matching source records/);
  assert.match(state(svg,'TN').getAttribute('aria-label'),/1 matching source records/);
  assert.ok(state(svg,'TN').style.fill.startsWith('hsl'));
  assert.equal(state(svg,'KY').getAttribute('data-sample-state'),'true');
  a.outbreakScope='TN'; const browsed=layer(a);
  assert.equal(a.selectedSampleId,'s');
  assert.equal(state(browsed,'KY').getAttribute('data-sample-state'),'true');
  assert.equal(state(browsed,'TN').getAttribute('data-context-state'),'true');
  assert.equal(state(svg,'TN').style.fill,state(browsed,'TN').style.fill);
});

test('turning off APHIS shading preserves sample outline and context records', () => {
  const a=app(); a.selectedSampleId='s'; a.outbreakLayerEnabled=false;
  a.mapLayerLegendNode={innerHTML:'',hidden:true};
  const svg=layer(a);
  assert.equal(state(svg,'KY').style.fill,undefined);
  assert.equal(state(svg,'KY').getAttribute('data-sample-state'),'true');
  assert.equal(state(svg,'TN').events.click,undefined);
  assert.equal(a.outbreakView().rows.length,2);
  assert.match(a.mapLayerLegendNode.innerHTML,/shading hidden/);
});

test('one map renders sample points above state shading and supports state-only sample location', () => {
  const a=app(); a.selectedSampleId='s';
  a.mapNode=new Element('div'); a.mapCountNode=new Element('div'); a.mapStateButtonNode={disabled:true};
  a.renderMap();
  let svg=a.mapNode.children[0];
  assert.equal(svg.children.filter(p=>p.attributes['data-sample-ids']).length,0);
  assert.equal(state(svg,'KY').getAttribute('data-sample-state'),'true');
  assert.equal(a.mapStateButtonNode.disabled,false);
  a.samples[0].has_coordinates=true; a.samples[0].latitude=37.8; a.samples[0].longitude=-84.5;
  a.renderMap(); svg=a.mapNode.children[0];
  const point=svg.children.find(p=>p.attributes['data-sample-ids']==='s');
  assert.ok(point);
  assert.ok(svg.children.indexOf(point)>svg.children.indexOf(state(svg,'KY')));
  a.updateSelection=()=>{}; point.events.click(); assert.equal(a.selectedSampleId,null);
  point.events.click(); assert.equal(a.selectedSampleId,'s');
});

test('lock date window survives sample changes, and unlocking follows the new sample', () => {
  const a=app(); a.selectedSampleId='s'; a.syncOutbreakDates();
  a.outbreakNode=new Element('div'); a.bindOutbreakControls(); a.renderOutbreak=()=>a.syncOutbreakDates();
  const change=(key,checked)=>a.outbreakNode.events.change({target:{dataset:{outbreakControl:key},checked}});
  change('lock',true); const before=[a.outbreakStart,a.outbreakEnd];
  a.samples[0].collection_date='2025-05-01'; a.syncOutbreakDates();
  assert.deepEqual([a.outbreakStart,a.outbreakEnd],before);
  change('lock',false); assert.equal(a.outbreakStart,'2025-04-01'); assert.equal(a.outbreakEnd,'2025-05-31');
});

test('state focus and panning leave selected sample and locked date window intact', () => {
  const a=app(); a.selectedSampleId='s'; a.syncOutbreakDates(); a.outbreakFollow=false;
  const before=[a.outbreakStart,a.outbreakEnd]; a.refreshMapView=()=>{};
  a.showSelectedState(); assert.equal(a.mapView,'custom'); assert.equal(a.selectedSampleId,'s');
  const bounds=a.mapBounds(); assert.ok(bounds[0]<-84.5 && bounds[1]>-84.5);
  a.setMapViewport(a.shiftedMapBounds(bounds,90,0));
  assert.deepEqual([a.outbreakStart,a.outbreakEnd],before); assert.equal(a.selectedSampleId,'s');
});

test('a newly selected sample restores the record scope while retaining a locked date window', () => {
  const a=app(); a.outbreakNode={hidden:true,innerHTML:'',querySelector:()=>null}; a.renderOutbreakTimeline=()=>{};
  a.renderOutbreak(); a.outbreakScope='TN'; a.outbreakFollow=false;
  const dates=[a.outbreakStart,a.outbreakEnd]; a.selectedSampleId='s'; a.renderOutbreak();
  assert.equal(a.outbreakScope,'sample'); assert.deepEqual([a.outbreakStart,a.outbreakEnd],dates);
  assert.doesNotMatch(a.outbreakNode.innerHTML,/class="wse-outbreak-map"/);
  assert.match(a.outbreakNode.innerHTML,/Lock date window/);
});


test('partially visible states receive labels even when original anchors fall outside requested bounds', () => {
  const a=app(), svg=new Element('svg'), bounds=[-90,-78,33,41];
  const {px,py}=a.mapProjection(bounds);
  a.drawMapBoundaries(svg,bounds,px,py,900,460);
  const labels=svg.children.filter(n=>n.name==='text' && n.attributes['data-label-region']);
  for(const [code,name] of [['MO','Missouri'],['PA','Pennsylvania'],['VA','Virginia']]) {
    const label=labels.find(n=>n.attributes['data-label-region']===code);
    assert.ok(label, code+' label is present');
    assert.equal(label.getAttribute('aria-label'),name);
    assert.ok(Number(label.attributes.x)>8 && Number(label.attributes.x)<892);
  }
});

test('clicking a state shows its count immediately and enables zoom with no WINGS sample selected', () => {
  const a=app();
  a.mapStateCardNode={innerHTML:'',hidden:true};
  a.mapStateButtonNode={disabled:true};
  a.outbreakNode={querySelector:()=>null};
  a.renderOutbreak=()=>{layer(a)};
  const initial=layer(a);
  assert.equal(a.mapStateButtonNode.disabled,true);
  state(initial,'TN').events.click();
  assert.equal(a.selectedSampleId,null);
  assert.equal(a.mapStateButtonNode.disabled,false);
  assert.equal(a.mapStateButtonNode.textContent,'Zoom to Tennessee');
  assert.equal(a.mapStateCardNode.hidden,false);
  assert.match(a.mapStateCardNode.innerHTML,/Tennessee/);
  assert.match(a.mapStateCardNode.innerHTML,/1 APHIS source records/);
  assert.match(a.mapStateCardNode.innerHTML,/2025-01-01 through 2025-01-10/);
  a.refreshMapView=()=>{}; a.showSelectedState();
  const bounds=a.mapBounds();
  assert.equal(a.mapView,'custom');
  assert.ok(bounds[0]<-86.8 && bounds[1]>-86.8 && bounds[2]<36.2 && bounds[3]>36.2);
  assert.equal(a.selectedSampleId,null);
});

test('state summary distinguishes a zero count from an invalid window and can be reopened', () => {
  const a=app(); a.outbreakScope='TN'; a.outbreakFollow=false; a.outbreakStart=a.outbreakEnd='2025-01-01';
  a.mapStateCardNode={innerHTML:'',hidden:true}; a.renderMapStateCard(a.outbreakView());
  assert.match(a.mapStateCardNode.innerHTML,/0 APHIS source records/);
  a.outbreakEnd='2024-12-31'; a.renderMapStateCard(a.outbreakView());
  assert.match(a.mapStateCardNode.innerHTML,/Choose a valid date window/);
  assert.doesNotMatch(a.mapStateCardNode.innerHTML,/0 APHIS source records/);
  a.mapStateCardDismissed=true; a.renderMapStateCard(a.outbreakView()); assert.equal(a.mapStateCardNode.hidden,true);
  a.mapStateCardDismissed=false; a.renderMapStateCard(a.outbreakView()); assert.equal(a.mapStateCardNode.hidden,false);
});
