const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../assets/wings-run.js'), 'utf8');
const start = source.indexOf('  function phylodynamicsLabel()');
const end = source.indexOf('  function preflightRows()', start);
assert.ok(start >= 0 && end > start);

function setup(runner = {phylodynamics_methods: ['fast', 'beast'], phylodynamics_ready: true}) {
  const ids = ['optPhylodynamics', 'optExplorer', 'phylodynamicsSettings',
    'phylodynamicsMethod', 'phylodynamicsMethodHint'];
  const elements = Object.fromEntries(ids.map(id => [id, {
    checked: false, value: id === 'phylodynamicsMethod' ? 'fast' : '',
    addEventListener() {}, hidden: false, disabled: false, textContent: ''
  }]));
  const ctx = vm.createContext({$: id => elements[id], state: {runner}});
  vm.runInContext(source.slice(start, end), ctx);
  return {elements, ctx, run: text => vm.runInContext(text, ctx)};
}

test('method hidden until selected, Fast default, Explorer included independently of Phylogenetics', () => {
  const {elements:e, run} = setup();
  assert.equal(e.phylodynamicsSettings.hidden, true);
  assert.equal(e.phylodynamicsMethod.value, 'fast');
  e.optPhylodynamics.checked = true;
  run('updatePhylodynamics()');
  assert.equal(e.phylodynamicsSettings.hidden, false);
  assert.equal(e.optExplorer.checked, true);
  assert.equal(e.optExplorer.disabled, true);
  e.phylodynamicsMethod.value = 'beast';
  run('updatePhylodynamics()');
  assert.match(e.phylodynamicsMethodHint.textContent, /two MCMC chains/);
  assert.equal(run('phylodynamicsPreflight()[0]'), true);
  assert.match(run('phylodynamicsPreflight()[2]'), /BEAST/);
  e.optPhylodynamics.checked = false;
  run('updatePhylodynamics()');
  assert.equal(e.phylodynamicsSettings.hidden, true);
  assert.equal(e.optExplorer.disabled, false);
});

test('stale runner, unsupported BEAST and absent NCBI contact block launch', () => {
  for (const runner of [{phylodynamics_ready: true},
    {phylodynamics_methods: ['fast'], phylodynamics_ready: true},
    {phylodynamics_methods: ['fast', 'beast'], phylodynamics_ready: false}]) {
    const {elements:e, run} = setup(runner);
    e.optPhylodynamics.checked = true;
    e.phylodynamicsMethod.value = 'beast';
    assert.equal(run('phylodynamicsPreflight()[0]'), false);
  }
});
