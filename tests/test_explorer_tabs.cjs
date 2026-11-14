const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../scripts/report/explorer-tabs.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source, context);
const api = context.WINGS_EXPLORER_TABS;

test('exports application views including the embedded genotype dashboard', () => {
  assert.equal(api.VERSION, '0.4.0');
  assert.deepEqual(Array.from(api.TAB_ORDER), ['overview', 'genome', 'amino', 'genotypes', 'ecology', 'coverage', 'concordance', 'outbreak']);
});

test('mount rejects a missing Explorer instance', () => {
  assert.throws(() => api.mount(null), /Explorer instance is required/);
});

test('module contains accessible tab semantics and shared-state controls', () => {
  assert.match(source, /role", "tablist/);
  assert.match(source, /aria-selected/);
  assert.match(source, /Selected WINGS sample/);
  assert.match(source, /Browse samples by host/);
  assert.match(source, /previousUpdateSelection/);
});

test('genome trees are demoted into a closed details disclosure', () => {
  assert.match(source, /Individual segment trees and QC evidence/);
  assert.match(source, /make\("details", "wse-genome-details"\)/);
});

test('APHIS records action switches to outbreak view', () => {
  assert.match(source, /data-state-action=\"records\"/);
  assert.match(source, /activate\("outbreak"\)/);
});


test('Genome Braid and Ecological Clock use separate application lenses without duplicating the component', () => {
  assert.match(source, /make\("div", "wse-app-shared"\)/);
  assert.match(source, /shared\.append\(braid\)/);
  assert.match(source, /braid\.dataset\.wseLens = showShared \? name : ""/);
  assert.match(source, /name === "genome" \|\| name === "ecology"/);
});

test('Ecology lens exposes evidence export without an abundance import action', () => {
  assert.doesNotMatch(source, /(?:Load|Replace) bird abundance data/);
  assert.doesNotMatch(source, /loadPhenology/);
  assert.match(source, /Export evidence/);
  assert.match(source, /\.wbc-export/);
});
