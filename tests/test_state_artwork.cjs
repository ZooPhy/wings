const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function element(tag) {
  return {tagName: tag, children: [], events: {}, textContent: '', append(...nodes) {this.children.push(...nodes);},
    addEventListener(name, callback) {this.events[name] = callback;}, remove() {this.removed = true;}};
}
const states = [
  {name: 'Kentucky', code: 'KY', src: 'data:image/svg+xml;base64,fixtureKY'},
  {name: 'New York', code: 'NY', src: 'data:image/svg+xml;base64,fixtureNY'},
  {name: 'Georgia', code: 'GA', src: 'data:image/svg+xml;base64,fixtureGA'},
];
const canada = [
  ['Alberta','AB'], ['British Columbia','BC'], ['Manitoba','MB'], ['New Brunswick','NB'],
  ['Newfoundland and Labrador','NL'], ['Northwest Territories','NT'], ['Nova Scotia','NS'],
  ['Nunavut','NU'], ['Ontario','ON'], ['Prince Edward Island','PE'], ['Quebec','QC'],
  ['Saskatchewan','SK'], ['Yukon','YT'],
];
states.push(...canada.map(([name, code]) => ({name, code, country:'CA', src:'data:image/svg+xml;base64,fixture'+code})));
const context = vm.createContext({WINGS_STATE_ARTWORK: states,
  document: {readyState: 'loading', addEventListener() {}, createElement: element}});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../scripts/report/sample-report-presentation.js'), 'utf8'), context);
const api = context.WINGS_SAMPLE_PRESENTATION;

test('full state names and postal abbreviations match US drawings', () => {
  for (const country of ['US', 'USA', 'U.S.A.', 'United States', 'United States of America']) {
    for (const state of ['Kentucky', 'KY', 'ky', ' kentucky ']) assert.equal(api.resolveState(state, country).code, 'KY');
  }
  assert.equal(api.resolveState('New_York', 'USA').code, 'NY');
});
test('missing, unknown and mismatched countries do not receive a guessed map', () => {
  for (const [state, country] of [['Georgia', 'Georgia'], ['Georgia', 'Not recorded'], ['KY', 'Canada'],
    ['Unknown', 'USA'], ['Not recorded', 'USA'], ['', 'US'], [null, null], ['Kentucky / Georgia', 'USA']]) {
    assert.equal(api.resolveState(state, country), null);
  }
});
test('location card includes offline artwork and retains exact location text', () => {
  const card = element('div');
  api.populateLocationCard(card, 'KY', 'U.S.A.');
  assert.deepEqual(card.children.map(node => node.className), ['wsp-label', 'wsp-state-artwork', 'wsp-location']);
  assert.equal(card.children[1].src, states[0].src);
  assert.equal(card.children[1].alt, '');
  assert.equal(card.children[1].height, 100);
  assert.equal(card.children[2].textContent, 'KY · U.S.A.');
});
test('image errors preserve the location value', () => {
  const card = element('div');
  api.populateLocationCard(card, 'Kentucky', 'USA');
  card.children[1].events.error();
  assert.equal(card.children[1].removed, true);
  assert.equal(card.children[2].textContent, 'Kentucky · USA');
});
test('unsupported locations remain visible as text', () => {
  for (const [state, country, expected] of [['Ontario', 'USA', 'Ontario · USA'],
    ['Not recorded', 'Not recorded', 'Not recorded'], ['Kentucky', 'Not recorded', 'Kentucky']]) {
    const card = element('div');
    api.populateLocationCard(card, state, country);
    assert.equal(card.children.length, 2);
    assert.equal(card.children[1].textContent, expected);
  }
});
test('all 13 Canadian provinces and territories match names and abbreviations', () => {
  for (const [name, code] of canada) {
    for (const country of ['Canada','CAN','CA','canada']) {
      for (const region of [name, code, name.toLowerCase(), name.replaceAll(' ', '_')]) {
        assert.equal(api.resolveState(region, country).code, code);
        assert.equal(api.resolveState(region, country).country, 'CA');
      }
    }
    assert.equal(api.resolveState(name, 'USA'), null);
  }
  assert.equal(api.resolveState('Québec', 'Canada').code, 'QC');
});
test('Canadian location cards preserve recorded text and use province artwork', () => {
  const card = element('div');
  api.populateLocationCard(card, 'Québec', 'CAN');
  assert.equal(card.children[1].src, api.resolveState('QC', 'Canada').src);
  assert.equal(card.children[2].textContent, 'Québec · CAN');
});
