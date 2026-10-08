// Run with: node tests/test_run_recovery.cjs
// Requires Playwright and Chromium. No real pipeline or sequence data are used.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const {chromium} = require("playwright");

const root = path.resolve(__dirname, "..");
const files = new Map([
  ["/run.html", ["text/html", "run.html"]],
  ["/assets/wings-run.js", ["text/javascript", "assets/wings-run.js"]],
  ["/assets/wings-portal.css", ["text/css", "assets/wings-portal.css"]],
]);
const run = {
  run_id: "20261008-135811-be5742", name: "Test Run", status: "running",
  created_at: "2026-10-08T20:58:11Z", started_at: "2026-10-08T20:58:11Z",
  finished_at: null, sample_count: 2, log_tail: "rule irma:",
  stages: {inputs: "complete", read_qc: "complete", assembly: "running"},
};
const older = {...run, run_id: "older-run", name: "Older <b>run</b>",
  status: "failed", created_at: "2026-10-07T20:58:11Z",
  finished_at: "2026-10-08T21:08:11Z"};
let offline = false;
let writes = 0;
const errors = [];
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (req.method !== "GET") writes += 1;
  const json = (value, status = 200) => {
    res.writeHead(status, {"Content-Type": "application/json", "Cache-Control": "no-store"});
    res.end(JSON.stringify(value));
  };
  if (url.pathname.startsWith("/api/") && offline) return json({error: "offline"}, 503);
  if (url.pathname === "/api/health") return json({snakemake_available: true, config_yaml_present: true});
  if (url.pathname === "/api/runs") return json([older, run]);
  if (url.pathname === `/api/runs/${run.run_id}`) return json(run);
  if (url.pathname === "/api/runs/older-run") return json(older);
  const file = files.get(url.pathname);
  if (file) {
    res.writeHead(200, {"Content-Type": file[0]});
    res.end(fs.readFileSync(path.join(root, file[1])));
    return;
  }
  json({error: "Unknown run"}, 404);
});

(async () => {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  const newPage = async () => {
    const page = await browser.newPage();
    page.on("pageerror", error => errors.push(error.message));
    return page;
  };
  const status = (page, label) => page.waitForFunction(
    label => document.getElementById("metricStatus").textContent === label, label);
  try {
    browser = await chromium.launch({headless: true});
    let page = await newPage();
    // A plain URL discovers an existing active run, including runs launched before this fix.
    await page.goto(`${base}/run.html`);
    await status(page, "flying");
    const savedUrl = page.url();
    assert.equal(new URL(savedUrl).searchParams.get("run"), run.run_id);
    assert.equal(await page.locator("#setupView").isVisible(), false);
    assert.equal(await page.locator("#runStatus").isVisible(), true);
    await page.reload();
    await status(page, "flying");
    assert.equal(await page.locator("#metricRunId").innerText(), run.run_id);
    // Lost connections retain the run and retry without creating/starting anything.
    offline = true;
    await page.waitForFunction(() => document.getElementById("statusSubtitle").textContent.includes("Reconnecting"));
    assert.equal(await page.locator("#stopRun").isDisabled(), true);
    offline = false;
    run.log_tail = "rule medaka_inference:";
    run.stages.polishing = "running";
    await page.waitForFunction(() => document.getElementById("runLog").textContent.includes("medaka_inference"));
    assert.equal(await page.locator("#stopRun").isDisabled(), false);
    // Close the entire browser; the synthetic backend finishes while it is closed.
    await browser.close();
    run.status = "complete";
    run.finished_at = "2026-10-08T23:03:11Z";
    browser = await chromium.launch({headless: true});
    page = await newPage();
    await page.goto(savedUrl);
    await status(page, "landed");
    assert.equal(await page.locator("#metricElapsed").innerText(), "2h 5m");
    assert.equal(await page.locator("#resultsLink").getAttribute("href"), `results.html?run=${run.run_id}`);
    assert.equal(await page.locator("#resultsLink").isVisible(), true);
    // With no browser storage, a plain URL still recovers the newest launched run.
    await page.goto(`${base}/run.html`);
    await status(page, "landed");
    await page.locator("#savedRunSelect").selectOption("older-run");
    await status(page, "failed");
    assert.equal(await page.locator("#statusTitle").innerText(), "Older <b>run</b>");
    assert.equal(await page.locator("#resultsLink").isVisible(), false);
    // Explicit selection wins over the latest run; missing IDs never launch a replacement.
    await page.reload();
    await status(page, "failed");
    await page.goto(`${base}/run.html?run=missing`);
    await status(page, "unavailable");
    assert.match(await page.locator("#statusSubtitle").innerText(), /could not be found/);
    await page.goto(`${base}/run.html?new=1`);
    await page.waitForFunction(() => document.getElementById("savedRunSelect").options.length === 3);
    assert.equal(await page.locator("#setupView").isVisible(), true);
    assert.equal(await page.locator("#runStatus").isVisible(), false);
    assert.equal(writes, 0, "Viewing/recovering runs must never create, start, or stop a run");
    assert.deepEqual(errors, []);
    console.log("Run recovery passed: refresh, browser restart, disk discovery, reconnect, completion, selection, missing run, and new-run setup.");
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
