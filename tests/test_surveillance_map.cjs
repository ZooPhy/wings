// Offline map checks; no browser, network, or map service required.
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(name) { this.name = name; this.attributes = {}; this.children = []; this.textContent = ""; this.events = {}; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  appendChild(child) { this.children.push(child); }
  append(...children) { this.children.push(...children); }
  addEventListener(type, fn) { this.events[type] = fn; }
  set innerHTML(value) { this.html = value; this.children = []; }
}
const context = vm.createContext({document: {
  readyState: "complete", querySelectorAll: () => [],
  createElement: name => new Element(name),
  createElementNS: (_, name) => new Element(name),
}});
const root = path.join(__dirname, "..");
vm.runInContext(fs.readFileSync(path.join(root, "scripts/report/map-boundaries.js"), "utf8"), context);
const source = fs.readFileSync(path.join(root, "scripts/report/surveillance-explorer.js"), "utf8");
vm.runInContext(source.replace("  const initialize = () => {",
  "  globalThis.ExplorerForTest = Explorer;\n  const initialize = () => {"), context);
const Explorer = context.ExplorerForTest;
Explorer.prototype.render = function () {};
const sample = (id, longitude, latitude, host = "Host A") =>
  ({sample_id: id, longitude, latitude, host, has_coordinates: true, collection_date: "2025-01-01"});
function explorer(samples) {
  const app = new Explorer({}, {samples, trees: {}, segment_order: []});
  app.mapNode = new Element("div");
  app.mapCountNode = new Element("div");
  return app;
}

test("offline dataset contains all US states/DC and Canadian provinces/territories", () => {
  const data = context.WINGS_MAP_BOUNDARIES;
  assert.equal(data.regions.filter(f => f.country === "USA").length, 51);
  assert.equal(data.regions.filter(f => f.country === "CAN").length, 13);
  for (const name of ["Kentucky", "Tennessee", "Alaska", "Hawaii", "Ontario", "Quebec", "Nunavut"]) {
    assert.ok(data.regions.some(f => f.name === name), name);
  }
  assert.ok(data.countries.some(f => f.country === "JPN"));
});

test("sample-area projection includes US, Canadian, overseas, and dateline coordinates", () => {
  for (const points of [
    [sample("Kentucky", -84.5, 37.8), sample("Tennessee", -85, 36)],
    [sample("Alaska", -149.9, 61.2), sample("Hawaii", -157.8, 21.3), sample("Canada", -79.4, 43.7)],
    [sample("Japan", 139.7, 35.7), sample("UK", -.1, 51.5)],
    [sample("east", 179.5, 52), sample("west", -179.5, 52)],
  ]) {
    const app = explorer(points);
    const {px, py} = app.mapProjection(app.mapBounds());
    for (const point of points) {
      assert.ok(px(point.longitude) >= 31 && px(point.longitude) <= 869);
      assert.ok(py(point.latitude) >= 31 && py(point.latitude) <= 429);
    }
  }
});

test("host filtering retains map extent", () => {
  const app = explorer([sample("a", -84, 38), sample("b", -123, 49, "Host B")]);
  const before = JSON.stringify(app.mapBounds());
  app.hostFilter = "Host B";
  assert.equal(JSON.stringify(app.mapBounds()), before);
});

test("invalid coordinates are counted separately and never plotted", () => {
  const app = explorer([sample("bad", 500, 35), sample("empty", null, 40),
    {...sample("missing", null, null), has_coordinates: false}, sample("zero", 0, 0)]);
  app.renderMap();
  assert.match(app.mapCountNode.textContent, /1 geolocated · 1 without coordinates · 2 invalid coordinates/);
  const svg = app.mapNode.children.find(node => node.name === "svg");
  assert.equal(svg.children.filter(node => node.attributes.class === "wse-map-cluster").length, 1);
});

test("North America view reports overseas points outside its extent", () => {
  const app = explorer([sample("Japan", 139.7, 35.7)]);
  app.mapView = "north-america";
  app.renderMap();
  assert.match(app.mapCountNode.textContent, /1 outside this view/);
  app.mapView = "world";
  app.renderMap();
  assert.doesNotMatch(app.mapCountNode.textContent, /outside this view/);
});

test("real boundary paths and location clusters retain sample selection", () => {
  const app = explorer([sample("a", -84.5, 37.8), sample("b", -84.5, 37.8)]);
  const selected = [];
  app.selectSample = id => { selected.push(id); app.selectedSampleId = id; };
  app.renderMap();
  const svg = app.mapNode.children.find(node => node.name === "svg");
  const regions = svg.children.filter(node => node.attributes.class === "wse-region-boundary");
  assert.ok(regions.length > 1);
  assert.ok(regions.some(node => node.children.some(child => child.textContent === "Kentucky (USA)")));
  const cluster = svg.children.find(node => node.attributes.class === "wse-map-cluster");
  cluster.events.click();
  cluster.events.keydown({key: "Enter", preventDefault() {}});
  assert.deepEqual(selected, ["a", "b"]);
});

test("empty data uses a finite North America context", () => {
  const app = explorer([]);
  app.renderMap();
  assert.equal(JSON.stringify(app.mapBounds()), "[-180,-45,5,85]");
  const svg = app.mapNode.children.find(node => node.name === "svg");
  assert.ok(svg.children.some(node => node.textContent === "No valid coordinates available for the current filter"));
});

test("clear selection still resets the genome explorer to all segments", () => {
  const app = explorer([]);
  const controls = new Map();
  app.genomeControlsNode = {querySelector(selector) {
    if (!controls.has(selector)) controls.set(selector, new Element("control"));
    return controls.get(selector);
  }};
  app.renderGenomeControls();
  app.treeMode = "single";
  app.selectedSampleId = "a";
  app.renderSegmentTabs = app.renderTrees = app.updateSelection = () => {};
  controls.get(".wse-clear-selection").events.click();
  assert.equal(app.treeMode, "all");
  assert.equal(app.selectedSampleId, null);
  assert.equal(controls.get(".wse-view-select").value, "all");
});

// Optional SVG previews use the actual renderer and the bundled boundary asset.
if (process.env.WINGS_MAP_PREVIEW_DIR) {
  const esc = value => String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const serialize = node => "<" + node.name + Object.entries(node.attributes).map(([key, value]) =>
    " " + key + '="' + esc(value) + '"').join("") + ">" + esc(node.textContent) +
    node.children.map(serialize).join("") + "</" + node.name + ">";
  fs.mkdirSync(process.env.WINGS_MAP_PREVIEW_DIR, {recursive: true});
  for (const [name, points, view] of [
    ["sample-area", [sample("a", -84.5, 37.8), sample("b", -84.2, 36.2)], "samples"],
    ["canada", [sample("a", -123.1, 49.3), sample("b", -79.4, 43.7)], "samples"],
    ["world", [sample("a", -84.5, 37.8), sample("b", 139.7, 35.7)], "world"],
  ]) {
    const app = explorer(points); app.mapView = view; app.renderMap();
    const svg = app.mapNode.children.find(node => node.name === "svg");
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    svg.setAttribute("width", 900); svg.setAttribute("height", 460);
    const css = fs.readFileSync(path.join(root, "scripts/report/surveillance-explorer.css"), "utf8");
    const style = new Element("style"); style.textContent = css;
    svg.children.unshift(style);
    fs.writeFileSync(path.join(process.env.WINGS_MAP_PREVIEW_DIR, name + ".svg"), serialize(svg));
  }
}

function wireSelectionPanel(app) {
  app.root = {querySelectorAll: () => []};
  app.genomeControlsNode = {querySelector: () => null};
  app.renderSelected = app.renderGenomeEvidence = app.renderEbird = app.revealSelectedTips = () => {};
  app.mapSelectionNode = {
    innerHTML: "",
    querySelectorAll() {
      return [...this.innerHTML.matchAll(/class="wse-map-sample-choice" data-sample-id="([^"]+)"/g)].map(match => ({
        events: {}, getAttribute: () => match[1], focus() {},
        addEventListener(name, handler) { this.events[name] = handler; },
      }));
    },
  };
  // Retain the rendered button objects so their actual click handlers can run.
  const query = app.mapSelectionNode.querySelectorAll;
  app.mapSelectionNode.querySelectorAll = function () {
    if (this.lastHTML !== this.innerHTML) { this.buttons = query.call(this); this.lastHTML = this.innerHTML; }
    return this.buttons;
  };
}

test("map clicks immediately identify the selected sample and offer colocated choices", () => {
  const app = explorer([sample("a", -84.5, 37.8), sample("b", -84.5, 37.8)]);
  wireSelectionPanel(app);
  app.updateSelection();
  assert.match(app.mapSelectionNode.innerHTML, /Click a point/);
  app.renderMap();
  const cluster = app.mapNode.children[0].children.find(node => node.attributes.class === "wse-map-cluster");
  cluster.events.click();
  assert.equal(app.selectedSampleId, "a");
  assert.match(app.mapSelectionNode.innerHTML, /Selected sample: <strong>a<\/strong>/);
  assert.match(app.mapSelectionNode.innerHTML, /2 samples share this point/);
  const choices = app.mapSelectionNode.querySelectorAll();
  assert.equal(choices.length, 2);
  choices[1].events.click();
  assert.equal(app.selectedSampleId, "b");
  assert.match(app.mapSelectionNode.innerHTML, /Selected sample: <strong>b<\/strong>/);
  cluster.events.click();
  assert.equal(app.selectedSampleId, "a", "Point cycling follows direct choice without accidentally clearing");
  cluster.events.keydown({key: "Enter", preventDefault() {}});
  assert.equal(app.selectedSampleId, "b");
  app.selectedSampleId = null;
  app.updateSelection();
  assert.match(app.mapSelectionNode.innerHTML, /Click a point/);
  assert.doesNotMatch(app.mapSelectionNode.innerHTML, /Selected sample:/);
});

test("single map points toggle selection and panel values are escaped", () => {
  const app = explorer([sample("<sample>", -84.5, 37.8, "<host>")]);
  wireSelectionPanel(app);
  app.renderMap();
  const cluster = app.mapNode.children[0].children.find(node => node.attributes.class === "wse-map-cluster");
  cluster.events.click();
  assert.match(app.mapSelectionNode.innerHTML, /&lt;sample&gt;/);
  assert.match(app.mapSelectionNode.innerHTML, /&lt;host&gt;/);
  assert.doesNotMatch(app.mapSelectionNode.innerHTML, /<sample>|<host>/);
  app.hostFilter = "Other host";
  app.updateSelection();
  assert.match(app.mapSelectionNode.innerHTML, /outside the current host filter/);
  cluster.events.click();
  assert.equal(app.selectedSampleId, null);
  assert.match(app.mapSelectionNode.innerHTML, /Click a point/);
});

function navigationApp() {
  const app = explorer([sample("a", -84.5, 37.8), sample("b", -83, 38)]);
  app.selectedSampleId = "a";
  app.refreshMapView = () => {};
  const svg = {style: {}, getScreenCTM: () => ({a: .5, d: .5})};
  const captured = new Set();
  app.mapNode.querySelector = () => svg;
  app.mapNode.classList = {add() {}, remove() {}};
  app.mapNode.setPointerCapture = id => captured.add(id);
  app.mapNode.hasPointerCapture = id => captured.has(id);
  app.mapNode.releasePointerCapture = id => captured.delete(id);
  app.bindMapNavigation();
  return {app, svg, captured};
}
function pointer(x, y, extra = {}) {
  return {clientX: x, clientY: y, pointerId: 1, button: 0, isPrimary: true,
    preventDefault() { this.prevented = true; },
    stopImmediatePropagation() { this.stopped = true; }, ...extra};
}

test("zoom and reset retain sample selection and stay within geographic limits", () => {
  const {app} = navigationApp();
  const original = app.mapBounds();
  app.zoomMap(1 / 1.5);
  const zoomed = app.mapBounds();
  assert.ok(zoomed[1] - zoomed[0] < original[1] - original[0]);
  assert.equal(app.mapView, "custom");
  assert.equal(app.selectedSampleId, "a");
  app.hostFilter = "Other host";
  assert.deepEqual(app.mapBounds(), zoomed);
  for (let i = 0; i < 100; i++) app.zoomMap(1 / 1.5);
  assert.ok(app.mapBounds()[1] - app.mapBounds()[0] >= .049999);
  for (let i = 0; i < 100; i++) app.zoomMap(1.5);
  assert.equal(JSON.stringify(app.mapBounds()), "[-180,180,-90,90]");
  app.resetMapView();
  assert.equal(app.mapView, "samples");
  assert.deepEqual(app.mapBounds(), original);
  assert.equal(app.selectedSampleId, "a");
});

test("drag pans in screen coordinates, preserves selection, and consumes the following click", () => {
  const {app, svg, captured} = navigationApp();
  const original = app.mapBounds();
  const events = app.mapNode.events;
  events.pointerdown(pointer(100, 100));
  events.pointermove(pointer(130, 120));
  assert.equal(svg.style.transform, "translate(30px, 20px)");
  assert.ok(captured.has(1));
  events.pointerup(pointer(130, 120));
  assert.equal(svg.style.transform, "");
  assert.equal(captured.size, 0);
  assert.deepEqual(app.mapBounds(), app.shiftedMapBounds(original, 60, 40));
  assert.ok(app.mapBounds()[0] < original[0], "dragging right moves the view west");
  assert.ok(app.mapBounds()[2] > original[2], "dragging down moves the view north");
  assert.equal(app.selectedSampleId, "a");
  const dragClick = pointer(130, 120);
  events.click(dragClick);
  assert.equal(dragClick.stopped, true);
  events.pointerdown(pointer(130, 120));
  events.pointerup(pointer(130, 120));
  const normalClick = pointer(130, 120);
  events.click(normalClick);
  assert.equal(normalClick.stopped, undefined, "a subsequent ordinary click can select a sample");
});

test("small movement, cancellation, and a second touch do not accidentally pan", () => {
  const {app, svg} = navigationApp();
  const original = app.mapBounds();
  const events = app.mapNode.events;
  events.pointerdown(pointer(100, 100));
  events.pointermove(pointer(102, 101));
  events.pointerup(pointer(102, 101));
  assert.deepEqual(app.mapBounds(), original);
  const click = pointer(102, 101);
  events.click(click);
  assert.equal(click.stopped, undefined);
  events.pointerdown(pointer(100, 100));
  events.pointermove(pointer(140, 120, {pointerId: 2, isPrimary: false}));
  assert.equal(svg.style.transform, "");
  events.pointermove(pointer(150, 130));
  events.pointercancel(pointer(150, 130));
  assert.equal(svg.style.transform, "");
  assert.deepEqual(app.mapBounds(), original);
});

test("map keyboard controls work without taking keys from sample markers", () => {
  const {app} = navigationApp();
  const original = app.mapBounds();
  const key = value => ({key: value, target: app.mapNode, preventDefault() { this.prevented = true; }});
  const right = key("ArrowRight");
  app.mapNode.events.keydown(right);
  assert.equal(right.prevented, true);
  assert.ok(app.mapBounds()[0] > original[0]);
  app.mapNode.events.keydown(key("+"));
  assert.ok(app.mapBounds()[1] - app.mapBounds()[0] < original[1] - original[0]);
  const before = app.mapBounds();
  app.mapNode.events.keydown({...key("ArrowLeft"), target: {}});
  assert.deepEqual(app.mapBounds(), before);
  app.mapNode.events.keydown(key("0"));
  assert.deepEqual(app.mapBounds(), original);
  assert.equal(app.selectedSampleId, "a");
});
