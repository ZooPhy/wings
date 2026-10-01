const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../scripts/report/genomic-ecological-concordance.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source, context);

test('exports concordance report module', () => {
  assert.equal(context.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE.VERSION, '0.3.1');
  assert.equal(typeof context.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE.mount, 'function');
});

test('report leads with plain-language interpretation', () => {
  assert.match(source, /What this run suggests/);
  assert.match(source, /What this run suggests/);
  assert.match(source, /Added explanatory value in/);
  assert.match(source, /Exploratory associations only/);
  assert.match(source, /finding\(\s*"Seasonal ecology"/);
  assert.match(source, /Not independently estimable in this run/);
  assert.match(source, /not evidence of transmission/);
});

test('data cards use novice-friendly labels and explain ERA5', () => {
  assert.match(source, /Seasonal ecology data/);
  assert.match(source, /Samples with weather data/);
  assert.match(source, /Distinct weather settings/);
  assert.match(source, /temperature, precipitation, and wind from ERA5/);
});

test('report exposes model hierarchy and unique sample counts', () => {
  assert.match(source, /M0/);
  assert.match(source, /Seasonal ecology/);
  assert.match(source, /samples ·/);
  assert.match(source, /Models compared:/);
  assert.match(source, /M0/);
  assert.match(source, /M3/);
});

test('report maps rank deficiency to plain language and keeps technical detail collapsible', () => {
  assert.match(source, /INSUFFICIENT_INDEPENDENT_VARIATION/);
  assert.match(source, /Not independently estimable/);
  assert.match(source, /Environmental distance does not provide independent variation/);
  assert.match(source, /Technical detail/);
});
