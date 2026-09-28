// Synthetic UI checks: selection, exact links, distinct marks, safe display.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
class Element {
  constructor(name) { this.name = name; this.attributes = {}; this.children = []; this.events = {}; this.flags = new Set(); this.classList = {toggle: (key, on) => on ? this.flags.add(key) : this.flags.delete(key), contains: key => (this.attributes.class || '').split(' ').includes(key)}; }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k]; }
  appendChild(child) { this.children.push(child); }
  append(...children) { this.children.push(...children); }
  addEventListener(k, fn) { this.events[k] = fn; }
  set innerHTML(value) { this.html = value; this.children = []; }
  get innerHTML() { return this.html || ''; }
}
const context = vm.createContext({document: {readyState:'complete', querySelectorAll: () => [], createElementNS: (_, name) => new Element(name)}});
const source = fs.readFileSync(path.join(__dirname, '../scripts/report/surveillance-explorer.js'), 'utf8');
vm.runInContext(source.replace('  const initialize = () => {', '  globalThis.TestExplorer = Explorer;\n  const initialize = () => {'), context);
const Explorer = context.TestExplorer;
Explorer.prototype.render = () => {};
function app() {
  const ref = {reference_id:'ref1', isolate:'<script>fixture</script>', collection_date:'2024', collection_date_precision:'year', segments:{HA:{status:'PRESENT', accession_version:'ZZ999991.1', tips:[{name:'public_HA', parent_support:'95/99'}]}, NA:{status:'NO_TREE'}}};
  const instance = new Explorer({}, {samples:[{sample_id:'local', host:'A'}], segment_order:['HA','NA'], public_reference_context:{references:[ref], record_count:1, source_file:'manifest.tsv', retrieved_on:'2025-01-01'}, trees:{HA:{tip_count:3, root:{children:[{name:'local_HA', sample_id:'local', length:0.1},{name:'public_HA', reference_id:'ref1', accession_version:'ZZ999991.1', length:0.2},{name:'unknown', length:0.3}]}}}});
  instance.updateSelection = () => {};
  return instance;
}
test('reference selection keeps the WINGS sample and repeated selection clears only reference', () => {
  const e = app(); e.selectSample('local'); e.selectReference('ref1');
  assert.equal(e.selectedSampleId, 'local'); assert.equal(e.selectedReferenceId, 'ref1');
  e.selectReference('missing'); assert.equal(e.selectedReferenceId, 'ref1');
  e.selectReference('ref1'); assert.equal(e.selectedReferenceId, null); assert.equal(e.selectedSampleId, 'local');
  e.selectReference('ref1'); e.selectSample('local'); assert.equal(e.selectedReferenceId, null);
});
test('public square is keyboard-selectable and unannotated tip stays noninteractive', () => {
  const e = app(), target = new Element('div');
  e.renderTree('HA', target, new Element('p'));
  const tips = target.children[0].children.filter(x => x.attributes.class?.includes('wse-tree-tip'));
  const ref = tips.find(x => x.attributes['data-reference-id']);
  assert.equal(ref.children[0].name, 'rect'); assert.equal(ref.attributes.role, 'button');
  ref.events.keydown({key:'Enter', preventDefault(){}}); assert.equal(e.selectedReferenceId, 'ref1');
  ref.events.click(); assert.equal(e.selectedReferenceId, null);
  assert.equal(tips.find(x => x.attributes['aria-label'] === 'Unannotated tip unknown').attributes.tabindex, '-1');
});
test('details escape metadata, preserve date precision and support, and provide fixed GenBank links', () => {
  const e = app(); e.referenceNode = new Element('div'); e.selectReference('ref1'); e.renderReferenceDetails();
  const html = e.referenceNode.innerHTML;
  assert.match(html, /&lt;script&gt;fixture/); assert.doesNotMatch(html, /<script>/);
  assert.match(html, /Collection date: 2024 · Precision: year/);
  assert.match(html, /95\/99/); assert.match(html, /Tree unavailable/);
  assert.match(html, /https:\/\/www.ncbi.nlm.nih.gov\/nuccore\/ZZ999991.1/);
  assert.match(html, /raw-read QC and coverage are not available/);
  assert.equal(e.referenceLink('javascript:alert(1)'), 'Accession not recorded');
});
test('one reference highlights all matching segment tips without removing local highlights', () => {
  const e = app(), nodes = [new Element('g'), new Element('g'), new Element('g')];
  nodes.forEach(n => { n.setAttribute('class', 'wse-tree-tip'); n.setAttribute('data-sample-id',''); });
  nodes[0].setAttribute('data-sample-id','local');
  nodes[1].setAttribute('data-reference-id','ref1'); nodes[2].setAttribute('data-reference-id','ref1');
  e.root = {querySelectorAll: sel => nodes.filter(n => Object.hasOwn(n.attributes, sel.slice(1,-1)))};
  e.selectSample('local'); e.selectReference('ref1'); e.updateEmphasis();
  assert.ok(nodes.every(n => n.flags.has('is-selected')));
  e.selectReference('ref1'); e.updateEmphasis();
  assert.ok(nodes[0].flags.has('is-selected')); assert.ok(!nodes[1].flags.has('is-selected'));
});
test('clear resets both selections and restores all segments', () => {
  const e = app(), controls = new Map();
  for (const name of ['sample-select','reference-select','view-select','clear-selection']) controls.set('.wse-' + name, new Element('select'));
  e.genomeControlsNode = {querySelector: sel => controls.get(sel)};
  e.renderSegmentTabs = e.renderTrees = () => {};
  e.renderGenomeControls(); e.selectedSampleId = 'local'; e.selectedReferenceId = 'ref1'; e.treeMode = 'single';
  controls.get('.wse-clear-selection').events.click();
  assert.equal(e.selectedSampleId, null); assert.equal(e.selectedReferenceId, null); assert.equal(e.treeMode, 'all');
});
test('no manifest has an explicit empty explanation', () => {
  const e = app(); e.referenceContext = null; e.referenceNode = new Element('div'); e.renderReferenceDetails();
  assert.match(e.referenceNode.innerHTML, /metadata are not loaded/);
});
