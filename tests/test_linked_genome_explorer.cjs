// Run with: node tests/test_linked_genome_explorer.cjs
// Requires Playwright and its Chromium browser. All fixtures are synthetic.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {spawnSync} = require("node:child_process");
const {chromium} = require("playwright");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "scripts/report/surveillance-explorer.js"), "utf8");
const css = fs.readFileSync(path.join(root, "scripts/report/surveillance-explorer.css"), "utf8");
const fixture = spawnSync(process.env.PYTHON || "python", ["-c", [
  "import sys, json, tempfile",
  "from pathlib import Path",
  "sys.path.insert(0, 'tests')",
  "from test_linked_genome_explorer import payload_from_fixture",
  "with tempfile.TemporaryDirectory() as temp:",
  "    print(json.dumps(payload_from_fixture(Path(temp))))",
].join("\n")], {cwd: root, encoding: "utf8"});
assert.equal(fixture.status, 0, fixture.stderr);
const payload = JSON.parse(fixture.stdout);

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1400, height: 1000}});
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    async function load(data) {
      const json = JSON.stringify(data).replaceAll("</", "<\\/");
      await page.setContent(`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body {font-family: system-ui; margin: 20px;} ${css}</style></head><body><script type="application/json" id="data">${json}</script><div class="wings-surveillance-explorer" data-wse-data-id="data"></div></body></html>`);
      await page.addScriptTag({content: source});
      await page.waitForSelector(".wse-genome-panel", {state: "attached"});
      await page.locator('.wse-app-tab[data-tab="genome"]').click();
      await page.locator(".wse-genome-details-summary").click();
      await page.waitForSelector(".wse-genome-panel", {state: "visible"});
    }
    const selected = () => page.locator(".wse-tree-grid .wse-tree-tip.is-selected").count();
    const presence = segment => page.locator(`.wse-segment-tree[data-segment="${segment}"] .wse-tree-presence`).innerText();
    await load(payload);
    assert.equal(await page.locator(".wse-segment-tree").count(), 8);
    assert.equal(await selected(), 0);
    assert.equal(await page.locator(".wse-selected").isVisible(), false);
    await page.selectOption(".wse-app-sample", "complete");
    assert.equal(await selected(), 8);
    assert.match(await page.locator(".wse-genotype").innerText(), /DEMO/);
    assert.equal(await page.locator(".wse-genome-panel table").count(), 0);

    await page.selectOption(".wse-app-sample", "partial");
    assert.equal(await selected(), 5);
    assert.match(await presence("NA"), /Sample absent from tree/);
    assert.match(await page.locator(".wse-selected").innerText(), /coordinates unavailable/);
    assert.match(await page.locator(".wse-report-link").getAttribute("href"), /partial\/summary\/partial.sample_summary.html$/);

    const completeTip = page.locator('.wse-tree-grid [data-segment="HA"] .wse-tree-tip[data-sample-id="complete"]');
    await completeTip.dispatchEvent("mouseenter");
    assert.equal(await selected(), 5, "Hover must preserve the selected sample");
    await completeTip.focus();
    await page.keyboard.press("Enter");
    assert.equal(await selected(), 8);
    assert.equal(await page.locator(".wse-app-sample").inputValue(), "complete");
    const axisBefore = await page.locator(".wse-axis-label").allTextContents();
    await page.selectOption(".wse-app-host", "Host B");
    assert.equal(await selected(), 8);
    assert.deepEqual(await page.locator(".wse-axis-label").allTextContents(), axisBefore);
    assert.match(await page.locator(".wse-filter-notice").innerText(), /outside the host filter/);
    await page.click(".wse-app-clear");
    assert.equal(await selected(), 0);
    assert.equal(await page.locator(".wse-selected").isVisible(), false);
    await page.selectOption(".wse-app-host", "ALL");
    await page.selectOption(".wse-app-sample", "complete");
    await page.locator('.wse-app-tab[data-tab="overview"]').click();
    await page.locator('.wse-timeline-mark[data-sample-id="partial"]').click();
    await page.locator('.wse-app-tab[data-tab="genome"]').click();
    assert.equal(await selected(), 5);

    await page.selectOption(".wse-view-select", "single");
    assert.equal(await page.locator(".wse-tree-grid").isVisible(), false);
    assert.equal(await page.locator(".wse-genome-panel > .wse-tree .wse-tree-tip.is-selected").count(), 1);
    await page.locator('.wse-segment-tab[data-segment="NA"]').click();
    assert.equal(await page.locator(".wse-genome-panel > .wse-tree .wse-tree-tip.is-selected").count(), 0);
    await page.selectOption(".wse-view-select", "all");
    assert.equal(await selected(), 5);
    await page.selectOption(".wse-app-sample", "no_evidence");
    assert.equal(await selected(), 0);
    assert.match(await presence("HA"), /Sample absent from tree/);

    const missing = structuredClone(payload);
    delete missing.trees.NS;
    missing.samples.forEach(sample => { sample.segments.NS.tree_status = "NO_TREE"; sample.segments.NS.tips = []; });
    await load(missing);
    await page.selectOption(".wse-app-sample", "complete");
    assert.equal(await page.locator(".wse-segment-tree").count(), 8);
    assert.match(await presence("NS"), /Tree unavailable/);
    assert.equal(await page.locator('.wse-segment-tab[data-segment="NS"]').isDisabled(), true);

    const legacy = structuredClone(payload);
    legacy.version = 1;
    legacy.samples.forEach(sample => { delete sample.segments; delete sample.genotype; });
    await load(legacy);
    await page.selectOption(".wse-app-sample", "complete");
    assert.equal(await selected(), 8);
    assert.match(await page.locator(".wse-genotype").innerText(), /NOT RECORDED/);

    const escaped = structuredClone(payload);
    escaped.samples[0].genotype.call = '<img src=x onerror="window.injected=true">';
    escaped.samples[0].segments.HA.qc_reason = "</script><script>window.injected=true</script>";
    await load(escaped);
    await page.selectOption(".wse-app-sample", "complete");
    assert.equal(await page.locator(".wse-genotype img").count(), 0);
    assert.equal(await page.evaluate(() => window.injected), undefined);

    await load(payload);
    await page.selectOption(".wse-app-sample", "complete");
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, "Mobile overflow should remain within the tree regions");
    if (process.env.WINGS_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.WINGS_SCREENSHOT_DIR, {recursive: true});
      await page.screenshot({path: path.join(process.env.WINGS_SCREENSHOT_DIR, "explorer-mobile.png"), fullPage: true});
      await page.setViewportSize({width: 1400, height: 1000});
      await page.screenshot({path: path.join(process.env.WINGS_SCREENSHOT_DIR, "explorer-desktop.png"), fullPage: true});
    }
    assert.deepEqual(errors, []);
    console.log("Linked explorer browser checks passed: selection, keyboard, hover, filters, missing evidence, legacy data, escaping, and mobile layout.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
