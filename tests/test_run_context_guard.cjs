// Exercise production context registration and launch gating without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../assets/wings-run.js'), 'utf8');
const begin = source.indexOf('  // WINGS_CONTEXT_STORAGE_V2:');
const start = source.indexOf('  async function startRun()', begin);
const end = source.indexOf('  function timelineIcon(', start);
assert.ok(begin >= 0 && start > begin && end > start);
const registration = source.slice(begin, start);
const launch = source.slice(start, end);

(async () => {
  for (const api of [undefined, {}, {setCreateSettings() {}}]) {
    const button = {}, messages = [];
    let writes = 0;
    const sandbox = {state:{step:0},window: {WINGS_CONTEXT_SETUP: api},
      preflightRows: () => [[true]],
      renderPreflight: () => {throw new Error('Valid preflight should not block');},
      $: id => {assert.equal(id, 'startRun'); return button;},
      alert: message => messages.push(message),
      fetch: () => {writes++; throw new Error('Unexpected request');}};
    vm.createContext(sandbox);
    vm.runInContext(registration + launch, sandbox);
    await sandbox.startRun();
    assert.equal(writes, 0);
    assert.equal(button.disabled, false);
    assert.match(messages[0], /Context setup did not load/);
  }
  let settings;
  const api = {setCreateSettings(fn) {settings = fn;}};
  const sandbox = {state:{step:0},window: {WINGS_CONTEXT_SETUP: api}, storageRevision: 'revision-one'};
  vm.runInNewContext(registration, sandbox);
  assert.equal(settings().storage_revision, 'revision-one');
  sandbox.storageRevision = 'revision-two';
  assert.equal(settings().storage_revision, 'revision-two');
  delete sandbox.storageRevision;
  assert.equal(Object.keys(settings()).length, 0);

  // A loaded module still checks preparation before creating a run or uploading.
  let checked = 0, writes = 0;
  const messages = [], button = {};
  api.readyForRun = async () => {checked++; throw new Error('Prepare context first');};
  api.attach = async () => {throw new Error('Unexpected attachment');};
  Object.assign(sandbox, {$: () => button, alert: msg => messages.push(msg),
    preflightRows: () => [[true]],
    renderPreflight: () => {throw new Error('Valid preflight should not block');},
    fetch: () => {writes++; throw new Error('Unexpected request');}});
  vm.runInNewContext(launch, sandbox);
  await sandbox.startRun();
  assert.equal(checked, 1); assert.equal(writes, 0);
  assert.match(messages[0], /Prepare context first/);
  api.readyForRun = async () => {checked++;};
  sandbox.state.docker={ready:false,message:'Start Docker Desktop'};
  sandbox.checkDocker=async()=>false;checked=0;writes=0;messages.length=0;
  await sandbox.startRun();assert.equal(checked,1);assert.equal(writes,0);assert.match(messages[0],/Start Docker Desktop/);
  sandbox.state.launchPending=true;checked=0;await sandbox.startRun();assert.equal(checked,0);sandbox.state.launchPending=false;
  // Preserve the pre-existing preflight gate in launchers that have it.
  if (/\bpreflightRows\s*\(/.test(launch)) {
    checked = 0; writes = 0; messages.length = 0;
    let rendered = 0;
    sandbox.preflightRows = () => [[false]];
    sandbox.renderPreflight = () => {rendered++;};
    await sandbox.startRun();
    assert.equal(rendered, 1);
    assert.equal(checked, 0);
    assert.equal(writes, 0);
    assert.equal(messages.length, 0);
  }
  console.log('PASS: context-free registration; live storage revision; missing/incomplete modules block new runs before requests; preflight and prepared-context validation retained.');
})().catch(error => {console.error(error); process.exitCode = 1;});
