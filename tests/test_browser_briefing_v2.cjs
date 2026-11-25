// Exercise the actual portal script with a small DOM fixture; no browser install required.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'run.html'), 'utf8');
const nodes = new Map();
function element() {
  return {value: '', checked: false, disabled: false, hidden: false, dataset: {},
    textContent: '', innerHTML: '', handlers: {}, children: [],
    addEventListener(name, fn) { this.handlers[name] = fn; },
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    setAttribute() {}, removeAttribute() {}, before() {}};
}
for (const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
  const node = element();
  node.value = match[0].match(/\bvalue="([^"]*)"/)?.[1] || '';
  node.checked = /\bchecked\b/.test(match[0]);
  node.hidden = /\bhidden\b/.test(match[0]);
  nodes.set(match[1], node);
}
nodes.get('briefingAudience').value = 'wildlife';
nodes.get('phylodynamicsMethod').value = 'fast';
let installed = true;
let created = null;
let storageRequest = null;
let storageOk = true;
const context = vm.createContext({
  window: {WINGS_CONTEXT_SETUP:{setCreateSettings(){},isReady(){return true;},async readyForRun(){},async attach(){}}},
  document: {addEventListener(){}, getElementById: id => nodes.get(id) || null, querySelectorAll: () => [], createElement: element},
  location: {hostname: '', search: '', origin: 'null'},
  URLSearchParams, URL, AbortController, setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
  alert() {}, console,
  fetch: async (url, options) => {
    if (url.endsWith('/api/docker/check')) return {ok:true,json:async()=>({ready:true,message:'Docker ready'})};
    if (url.endsWith('/api/storage')) {
      storageRequest = JSON.parse(options.body);
      return {ok: storageOk, json: async () => storageOk ? {
        runs_root: storageRequest.runs_dir, conda_pkgs_dir: storageRequest.conda_pkgs_dir,
        conda_pkgs_default: 'Conda configuration default', storage_revision: 'applied', free_bytes: 100000
      } : {error: 'Directory is not writable'}};
    }
    if (url.endsWith('/api/briefing/check')) return {ok: true, json: async () => ({ready: installed, detail: 'Checked'})};
    created = JSON.parse(options.body);
    return {ok: false, text: async () => 'Test stops before run creation'};
  }
});
let source = fs.readFileSync(path.join(root, 'assets/wings-run.js'), 'utf8');
source = source.replace(/\}\)\(\);\s*$/, 'globalThis.fixture = {state, briefingOptions, syncBriefing, checkBriefingModel, preflightRows, startRun, syncStorage, applyStorage, renderPreflight, applyOllamaDefaults};\n})();');
vm.runInContext(source, context);
const t = context.fixture;
const $ = id => nodes.get(id);
(async () => {
  assert.equal(t.briefingOptions().briefing, false);
  t.applyOllamaDefaults({model:'saved:7b',url:'http://host.docker.internal:12345/api/chat',display_url:'http://localhost:12345'});
  assert.equal($('briefingModel').value,'saved:7b');
  assert.match($('briefingServerStatus').textContent,/localhost:12345/);
  $('optExplorer').checked = false;
  $('optBriefing').checked = true;
  $('optBriefing').handlers.change();
  assert.equal($('briefingSettings').hidden, false);
  assert.equal($('optExplorer').checked, true);
  assert.equal($('optExplorer').disabled, true);
  const row = () => t.preflightRows().find(r => r[1] === 'Local agency briefing');
  assert.equal(row()[0], false);
  await t.checkBriefingModel();
  assert.equal(row()[0], true);
  t.applyOllamaDefaults({model:'saved:7b',url:'http://host.docker.internal:23456/api/chat',display_url:'http://localhost:23456'});
  assert.equal(row()[0],false,'Changing endpoint invalidates the old connection check');
  $('briefingModel').value = 'custom:latest';
  $('briefingModel').handlers.input();
  t.applyOllamaDefaults({model:'changed:8b',url:'http://host.docker.internal:23456/api/chat',display_url:'http://localhost:23456'});
  assert.equal($('briefingModel').value,'custom:latest','User-selected model survives health refresh');
  assert.equal(row()[0], false);
  installed = false;
  await t.checkBriefingModel();
  assert.equal(row()[0], false);
  installed = true;
  await t.checkBriefingModel();
  assert.equal(row()[0], true);
  $('briefingAudience').value = 'public_health';
  t.state.runner = {snakemake_available: true, config_yaml_present: true,
    runs_root: '/original/runs', storage_revision: 'initial', free_bytes: 100000,
    conda_pkgs_default: 'Conda configuration default'};
  t.state.docker={ready:true,selection_vadr:true};
  t.state.reads = [{name: 'sample.fastq.gz', size: 100}];
  t.state.metadata = {name: 'metadata.tsv', size: 10};
  t.state.metadataIds = ['sample'];
  $('runName').value = 'Test';
  t.syncStorage();
  const storageRow = () => t.preflightRows().find(r => r[1] === 'Storage locations');
  assert.equal(storageRow()[0], true);
  assert.equal($('runsDirectory').value, '/original/runs');
  $('runsDirectory').value = '/project/<runs>';
  $('runsDirectory').handlers.input();
  $('condaCacheDirectory').value = '/project/cache';
  assert.equal(storageRow()[0], false);
  await t.startRun();
  assert.equal(created, null, 'Unsaved storage must prevent run creation');
  storageOk = false;
  await t.applyStorage();
  assert.equal(storageRow()[0], false);
  assert.match($('storageMessage').textContent, /not writable/);
  storageOk = true;
  await t.applyStorage();
  assert.equal(storageRequest.storage_revision, 'initial');
  assert.equal(storageRow()[0], true);
  assert.equal(t.state.runner.runs_root, '/project/<runs>');
  t.renderPreflight();
  assert.match($('preflightList').innerHTML, /&lt;runs&gt;/);
  assert.equal($('preflightList').innerHTML.includes('<runs>'), false);
  await t.startRun();
  assert.equal(created, null, 'Missing metadata validation must still prevent run creation');
  // This fixture isolates briefing/storage behavior after setup validation.
  t.state.metadataValidation = {ok:true,errors:[],warnings:[]};
  await t.startRun();
  assert.equal(created.storage_revision, 'applied');
  assert.deepEqual(created.options, {context_setup:true, genoflu: true, vadr: true, phylogeny: false, phylodynamics:false, phylodynamics_method:'fast',
    explorer: true, briefing: true, briefing_model: 'custom:latest', briefing_audience: 'public_health'});
  $('optBriefing').checked = false;
  t.syncBriefing();
  assert.equal($('briefingSettings').hidden, true);
  assert.equal($('optExplorer').disabled, false);
  assert.equal(row(), undefined);
  console.log('Portal DOM fixture passed: option, dependency, model check, invalidation, preflight and request payload.');
})().catch(error => { console.error(error); process.exitCode = 1; });
