const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync(__dirname + '/../results.html', 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];

function fixture(version = 1) {
  const nodes = new Map();
  const element = () => ({hidden: false, style: {}, textContent: '', events: {},
    classList: {add() {}, remove() {}}, addEventListener(name, callback) {this.events[name] = callback;}});
  const document = {getElementById(id) {if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id);}};
  const context = vm.createContext({document, window: {location: {search: ''}, scrollTo() {}, alert() {}}, URLSearchParams});
  vm.runInContext(script, context);
  const run = '<h1>Stored run summary</h1>', sample = '<h1>Stored sample</h1>';
  const bundle = {format: 'WINGS_REPORT_BUNDLE', version, run_summary: {html: run},
    samples: {one: version === 1 ? {html: sample} : {html_mid: 'Stored sample'}}};
  if (version === 2) bundle.shared = {report_prefix: '<h1>', report_suffix: '</h1>'};
  context.bundleForTest = bundle;
  vm.runInContext('openBundle(bundleForTest, "Fixture run")', context);
  const frame = nodes.get('report-frame');
  function click(href) {
    let listener;
    frame.contentDocument = {addEventListener(name, callback, capture) {
      assert.equal(name, 'click'); assert.equal(capture, true); listener = callback;
    }};
    frame.events.load();
    const link = {getAttribute: () => href};
    const event = {target: {closest: () => link}, prevented: false, stopped: false,
      preventDefault() {this.prevented = true;}, stopPropagation() {}, stopImmediatePropagation() {this.stopped = true;}};
    listener(event);
    return event;
  }
  return {nodes, frame, click, run, sample};
}

for (const version of [1, 2]) {
  test('sample return restores the stored summary for bundle v' + version, () => {
    const h = fixture(version);
    h.click('../one/summary/one.sample_summary.html');
    assert.equal(h.frame.srcdoc, h.sample);
    assert.equal(h.nodes.get('back-to-run').hidden, false);
    const event = h.click('../../run_summary/run_summary.html');
    assert.equal(event.prevented, true); assert.equal(event.stopped, true);
    assert.equal(h.frame.srcdoc, h.run);
    assert.equal(h.nodes.get('report-status').textContent, 'Fixture run');
    assert.equal(h.nodes.get('back-to-run').hidden, true);
    // Return to the sample and back again without reloading the bundle.
    h.click('../one/summary/one.sample_summary.html');
    h.click('../../run_summary/run_summary.html');
    assert.equal(h.frame.srcdoc, h.run);
  });
}

for (const href of ['run_summary.html', './run_summary.html', '../run_summary/run_summary.html', '../../run_summary/run_summary.html?source=sample#overview']) {
  test('local summary link is handled inside the viewer: ' + href, () => {
    const h = fixture();
    assert.equal(h.click(href).prevented, true);
    assert.equal(h.frame.srcdoc, h.run);
  });
}

for (const href of ['https://example.org/run_summary.html', '//example.org/run_summary.html', 'consensus.fasta', '../../other/run_summary.html', 'mailto:person@example.org']) {
  test('unrelated links retain their existing behavior: ' + href, () => {
    const h = fixture();
    assert.equal(h.click(href).prevented, false);
  });
}
