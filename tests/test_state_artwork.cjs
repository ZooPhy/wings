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
test('missing, unknown and non-US locations do not receive a guessed map', () => {
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
  for (const [state, country, expected] of [['Ontario', 'Canada', 'Ontario · Canada'],
    ['Not recorded', 'Not recorded', 'Not recorded'], ['Kentucky', 'Not recorded', 'Kentucky']]) {
    const card = element('div');
    api.populateLocationCard(card, state, country);
    assert.equal(card.children.length, 2);
    assert.equal(card.children[1].textContent, expected);
  }
});
