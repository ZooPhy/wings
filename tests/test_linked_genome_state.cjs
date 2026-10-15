// Dependency-free state/rendering checks. Browser layout is tested separately.
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor() { this.attributes = {}; this.children = []; this.textContent = ""; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  appendChild(child) { this.children.push(child); }
  append(...children) { this.children.push(...children); }
  addEventListener() {}
  set innerHTML(value) { this.html = value; this.children = []; }
  get innerHTML() { return this.html || ""; }
}
const document = {readyState: "complete", querySelectorAll: () => [],
  createElementNS: () => new Element()};
const context = vm.createContext({document});
const source = fs.readFileSync(path.join(__dirname, "../scripts/report/surveillance-explorer.js"), "utf8");
vm.runInContext(source.replace('return {VERSION,SEGMENTS',
  'return {DashboardForTest:Dashboard,VERSION,SEGMENTS').replace("  const initialize = () => {",
  "  globalThis.ExplorerForTest = Explorer;\n  const initialize = () => {"), context);
const Explorer = context.ExplorerForTest;
// Keep constructor state initialization, but leave DOM mounting to browser tests.
Explorer.prototype.render = function () {};

function explorer() {
  return new Explorer({}, {segment_order: ["HA", "NA"], trees: {},
    samples: [
      {sample_id: "a", host: "Host A", collection_date: "2025-01-01"},
      {sample_id: "b", host: "Host B", collection_date: "2025-07-01"},
    ]});
}

test("starts with no sample selected; repeated clicks clear selection", () => {
  const app = explorer();
  app.updateSelection = () => {};
  assert.equal(app.selectedSampleId, null);
  app.selectSample("a");
  assert.equal(app.selectedSampleId, "a");
  app.selectSample("a");
  assert.equal(app.selectedSampleId, null);
  app.selectSample("missing");
  assert.equal(app.selectedSampleId, null);
});

test("hover never changes the selected sample", () => {
  const app = explorer();
  app.updateSelection = app.updateEmphasis = () => {};
  app.selectSample("a");
  app.setHover("b");
  assert.equal(app.selectedSampleId, "a");
  app.clearHover();
  assert.equal(app.selectedSampleId, "a");
});

test("host filtering clears incompatible selection and preserves the full-run timeline axis", () => {
  const app = explorer();
  app.timelineNode = new Element();
  app.renderTimeline();

  const axis = () => JSON.stringify(app.timelineNode.children[0].children
    .filter(node => node.attributes.class?.startsWith("wse-axis"))
    .map(node => [node.attributes, node.textContent]));

  const full = axis();

  app.selectedSampleId = "a";
  app.renderEbird = app.renderMap = app.renderTrees = app.renderLegend = app.updateSelection = () => {};

  app.setHostFilter("Host B");

  assert.equal(app.selectedSampleId, null);
  assert.equal(axis(), full);

  const marks = app.timelineNode.children[0].children.filter(
    node => node.attributes["data-sample-id"]
  );

  assert.equal(marks.length, 1);
  assert.equal(marks[0].attributes["data-sample-id"], "b");

  app.selectedSampleId = "b";
  app.setHostFilter("Host B");
  assert.equal(app.selectedSampleId, "b");
});

test("missing segment evidence remains distinct from tree presence", () => {
  const app = explorer();
  app.payload.trees.HA = {root: {children: [{name: "a__HA", sample_id: "a"}]}};
  const record = app.segmentEvidence(app.samples[0], "HA");
  assert.equal(record.record_status, "NOT_RECORDED");
  assert.equal(record.tree_status, "PRESENT");
  assert.equal(app.segmentEvidence(app.samples[1], "HA").tree_status, "ABSENT_FROM_TREE");
  assert.equal(app.segmentEvidence(app.samples[0], "NA").tree_status, "NO_TREE");
});

test("clearing a sample removes tree-presence text and stale braid genotype", () => {
  const app = explorer();
  app.payload.trees.HA = {root: {children: [{name: 'a__HA', sample_id: 'a', length: 0.1}]}};
  app.samples[0].genotype = {call: 'FIXTURE'};
  const presence = {textContent: ''};
  const card = {dataset: {segment: 'HA'}, querySelector: selector => {
    assert.equal(selector, '.wse-tree-presence');
    return presence;
  }};
  app.treeGridNode = {querySelectorAll: selector => {
    assert.equal(selector, '.wse-segment-tree');
    return [card];
  }};
  app.updateSelection = () => app.renderGenomeEvidence();
  app.selectSample('a');
  assert.match(presence.textContent, /Sample present/);
  assert.match(braidEvidence(app), /FIXTURE/);
  app.selectSample('a');
  assert.equal(presence.textContent, "");
  const cleared = braidEvidence(app);
  assert.match(cleared, /Follow one record/);
  assert.doesNotMatch(cleared, /FIXTURE|wbc-recorded-genotype/);
});

function braidEvidence(app) {
  const api = context.WINGS_BRAID_CLOCK;
  const dashboard = Object.create(api.DashboardForTest.prototype);
  const target = new Element();
  dashboard.root = {querySelector: selector => {
    assert.equal(selector, '.wbc-evidence');
    return target;
  }};
  dashboard.m = api.model(app.payload);
  dashboard.selected = app.selectedSampleId ? `s:${app.selectedSampleId}` : null;
  dashboard.selectedReference = null;
  dashboard.phenology = null;
  dashboard.profile = id => api.neighborhoodProfile(dashboard.m, id);
  dashboard.renderEvidence();
  return target.innerHTML;
}

test("braid genotype details escape recorded values without restoring the old tree panel", () => {
  const app = explorer();
  app.selectedSampleId = "a";
  app.samples[0].genotype = {call: "<img src=x>", reason: "<script>fixture</script>"};
  app.samples[0].segments = {HA: {record_status: "AVAILABLE", overall_status: "FAIL",
    median_depth: 0, breadth_covered: 0, tree_status: "ABSENT_FROM_TREE", tips: []}};
  const html = braidEvidence(app);
  const primary = html.split('<details class="wbc-technical-comparisons">')[0];
  assert.match(primary, /wbc-recorded-genotype/);
  assert.match(primary, /Genotype assignment details/);
  assert.doesNotMatch(primary, /<table|Segment evidence for|Median depth|Coverage breadth/);
  assert.match(primary, /&lt;img src=x&gt;/);
  assert.match(primary, /&lt;script&gt;fixture&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<img|<script>/);
  assert.doesNotMatch(source, /<div class="wse-genome-evidence"><\/div>/);
});

test("eBird citation and terms remain visible even for an unmatched host filter", () => {
  const app = explorer();
  app.ebirdPanelNode = new Element();
  app.ebirdNode = new Element();
  app.ebirdContexts = [{host: "Host A", sample_ids: ["a"], complete_checklists: 10,
    reporting_checklists: 2, reporting_frequency: .2, state: "Arizona", country: "US",
    date_from: "2024-12-01", date_to: "2025-02-01", release: "fixture"}];
  app.ebirdAttribution = {citation: "Fixture citation", terms: "Fixture <terms>"};
  app.renderEbird();
  assert.match(app.ebirdNode.innerHTML, /Fixture citation/);
  assert.match(app.ebirdNode.innerHTML, /Fixture &lt;terms&gt;/);
  app.hostFilter = "Host B";
  app.renderEbird();
  assert.match(app.ebirdNode.innerHTML, /No eBird context/);
  assert.match(app.ebirdNode.innerHTML, /Fixture citation/);
  assert.match(app.ebirdNode.innerHTML, /Fixture &lt;terms&gt;/);
});
