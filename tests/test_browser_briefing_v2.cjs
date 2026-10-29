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
let installed = true;
let created = null;
const context = vm.createContext({
  document: {getElementById: id => nodes.get(id) || null, querySelectorAll: () => [], createElement: element},
  location: {hostname: '', search: '', origin: 'null'},
  URLSearchParams, URL, AbortController, setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
  alert() {}, console,
  fetch: async (url, options) => {
    if (url.endsWith('/api/briefing/check')) return {ok: true, json: async () => ({ready: installed, detail: 'Checked'})};
    created = JSON.parse(options.body);
    return {ok: false, text: async () => 'Test stops before run creation'};
  }
});
let source = fs.readFileSync(path.join(root, 'assets/wings-run.js'), 'utf8');
source = source.replace(/\}\)\(\);\s*$/, 'globalThis.fixture = {state, briefingOptions, syncBriefing, checkBriefingModel, preflightRows, startRun};\n})();');
vm.runInContext(source, context);
const t = context.fixture;
const $ = id => nodes.get(id);
(async () => {
  assert.equal(t.briefingOptions().briefing, false);
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
  $('briefingModel').value = 'custom:latest';
  $('briefingModel').handlers.input();
  assert.equal(row()[0], false);
  installed = false;
  await t.checkBriefingModel();
  assert.equal(row()[0], false);
  installed = true;
  await t.checkBriefingModel();
  assert.equal(row()[0], true);
  $('briefingAudience').value = 'public_health';
  await t.startRun();
  assert.deepEqual(created.options, {genoflu: true, vadr: true, phylogeny: false,
    explorer: true, briefing: true, briefing_model: 'custom:latest', briefing_audience: 'public_health'});
  $('optBriefing').checked = false;
  t.syncBriefing();
  assert.equal($('briefingSettings').hidden, true);
  assert.equal($('optExplorer').disabled, false);
  assert.equal(row(), undefined);
  console.log('Portal DOM fixture passed: option, dependency, model check, invalidation, preflight and request payload.');
})().catch(error => { console.error(error); process.exitCode = 1; });
