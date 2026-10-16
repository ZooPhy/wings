// Dependency-free checks for the actual stage renderer. Browser recovery is
// covered separately by test_run_recovery.cjs using Playwright and Chromium.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor() { this.children = []; this.dataset = {}; this.textContent = ""; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
  get text() { return this.textContent + this.children.map(child => child.text).join(" "); }
}
const timeline = new Element();
const source = fs.readFileSync(path.join(__dirname, "../assets/wings-run.js"), "utf8");
const renderer = source.slice(source.indexOf("  function timelineIcon("), source.indexOf("  function elapsedText("));
const context = vm.createContext({
  document: {createElement: () => new Element()},
  $: id => { assert.equal(id, "timeline"); return timeline; },
  stageDefinitions: [["assembly", "Assembly"], ["polishing", "Polishing"], ["surveillance", "Surveillance"]],
});
vm.runInContext(renderer, context);
const render = (stages, progress) => {
  context.stages = stages; context.progress = progress;
  vm.runInContext("renderTimeline(stages, progress)", context);
  return Object.fromEntries(timeline.children.map(item => [item.dataset.stage, item]));
};
let items = render({assembly: "running", polishing: "partial"}, {
  assembly: {completed: 3, expected: null, active: 1, totals_provisional: true, irma_completed: 3, irma_expected: 12},
  polishing: {completed: 2, expected: null, totals_provisional: true},
});
assert.match(items.assembly.text, /3 of 12 scheduled IRMA jobs completed/);
assert.match(items.assembly.text, /1 running/);
assert.match(items.polishing.text, /Partially complete/);
assert.doesNotMatch(items.assembly.text, /Complete/);
items = render({assembly: "partial"}, {assembly: {completed: 1, expected: null, irma_completed: 1, irma_expected: 3}});
assert.match(items.assembly.text, /1 of 3 scheduled IRMA jobs completed/);
items = render({surveillance: "failed"}, {surveillance: {completed: 1, expected: null, failed_rules: ["synthetic <img src=x>"]}});
assert.match(items.surveillance.text, /Failed task: synthetic <img src=x>/);
assert.equal(items.surveillance.children[1].children.at(-1).textContent, "Failed task: synthetic <img src=x>");
items = render({assembly: "interrupted", polishing: "skipped"}, {});
assert.match(items.assembly.text, /Interrupted/);
assert.match(items.polishing.text, /Not required/);
items = render({assembly: "complete"}, {assembly: {completed: 12, expected: 12}});
assert.match(items.assembly.text, /12 of 12 scheduled jobs completed/);
items = render(undefined, undefined);
assert.equal(timeline.children.length, 3);
assert.match(items.assembly.text, /Waiting/);
console.log("Stage display checks passed: overlapping stages, IRMA counts, attempt counts, failed task text, interrupted/skipped states, and legacy fallback.");
