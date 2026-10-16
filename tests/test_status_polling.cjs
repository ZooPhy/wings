const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../assets/wings-run.js'), 'utf8');
const start = source.indexOf('  async function pollStatus()');
const end = source.indexOf('  function renderFailures(', start);
assert.ok(start >= 0 && end > start);
const state = {runId: 'example', statusRequest: 0, pollPending: false};
const elements = new Map();
const requests = [];
const context = vm.createContext({state, localOrigin: 'http://localhost:8765',
  AbortController, setTimeout, clearTimeout, clearInterval: () => {},
  fetch: () => new Promise(resolve => requests.push(resolve)),
  $: id => {
    if (!elements.has(id)) elements.set(id, {textContent: '', removeAttribute() {}});
    return elements.get(id);
  },
  setActivity() {}, elapsedText() {return '0s';}, renderTimeline() {},
  renderIrmaProgress() {}, renderFailures() {}, renderAttempts() {},
});
vm.runInContext(source.slice(start, end), context);
const response = status => ({ok: true, status: 200, json: async () => ({status, run_id: 'example'})});
(async () => {
  const first = context.pollStatus();
  await context.pollStatus();
  assert.equal(requests.length, 1, 'polls must not overlap within one view');
  requests[0](response('running'));
  await first;
  assert.equal(state.pollPending, false);
  assert.equal(elements.get('metricStatus').textContent, 'flying');

  const old = context.pollStatus();
  // Opening a new attempt of the SAME run invalidates the old request.
  state.statusRequest += 1;
  state.pollPending = false;
  const current = context.pollStatus();
  requests[2](response('running'));
  await current;
  requests[1](response('failed'));
  await old;
  assert.equal(elements.get('metricStatus').textContent, 'flying');
  assert.equal(elements.get('resultsLink').hidden, true);
  console.log('Status polling checks passed: single request and stale-attempt rejection.');
})().catch(error => {console.error(error); process.exitCode = 1;});
