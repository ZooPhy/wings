const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../scripts/report/explorer-tabs.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source, context);
const api = context.WINGS_EXPLORER_TABS;

test('Coverage is a stable application view', () => {
  assert.equal(api.VERSION, '0.2.0');
  assert.deepEqual(Array.from(api.TAB_ORDER), ['overview','genome','ecology','coverage','outbreak']);
});

test('coverage aggregation preserves missing denominators and real zeros', () => {
  const rows = [
    {period_start:'2025-01-01',period_end:'2025-01-31',host:'A',tested:10,positive:0,sequenced:2},
    {period_start:'2025-01-01',period_end:'2025-01-31',host:'B',tested:5,positive:1,sequenced:null},
  ];
  const out = api._test.aggregateCoverageRecords(rows, 'ALL');
  assert.equal(out.totals.tested, 15);
  assert.equal(out.totals.positive, 1);
  assert.equal(out.totals.sequenced, 2);
  assert.equal(out.periods.length, 1);
});


test('all-missing denominator totals remain unavailable rather than zero', () => {
  const rows = [
    {
      period_start:'2025-01-01',
      period_end:'2025-01-31',
      host:'A',
      sampled:null,
      tested:null,
      positive:null,
      sequenced:null,
    },
    {
      period_start:'2025-02-01',
      period_end:'2025-02-28',
      host:'A',
      sampled:'',
      tested:'',
      positive:'',
      sequenced:'',
    },
  ];

  const out = api._test.aggregateCoverageRecords(rows, 'ALL');

  assert.equal(out.totals.sampled, null);
  assert.equal(out.totals.tested, null);
  assert.equal(out.totals.positive, null);
  assert.equal(out.totals.sequenced, null);
});

test('host filter uses exact source host values only', () => {
  const rows = [
    {period_start:'2025-01-01',period_end:'2025-01-31',host:'BLVU',tested:10,positive:2},
    {period_start:'2025-01-01',period_end:'2025-01-31',host:'Black Vulture',tested:20,positive:4},
  ];
  const out = api._test.aggregateCoverageRecords(rows, 'BLVU');
  assert.equal(out.totals.tested, 10);
  assert.equal(out.visibleRows, 1);
});
