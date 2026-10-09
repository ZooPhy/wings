// Run with: node tests/test_results_auto_open.cjs
// Requires Playwright and Chromium. All fixtures are synthetic.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const {gzipSync} = require("node:zlib");
const {chromium} = require("playwright");

const root = path.resolve(__dirname, "..");
const resultsHtml = fs.readFileSync(path.join(root, "results.html"));

const bundle = {
  format: "WINGS_REPORT_BUNDLE",
  version: 1,
  run_summary: {
    filename: "run_summary.html",
    html: `<!doctype html>
<html>
<body>
<h1 id="auto-run-marker">AUTO_OPEN_RUN_SUMMARY</h1>
</body>
</html>`
  },
  provenance: {
    filename: "run_provenance.json",
    data: {}
  },
  samples: {
    sample_one: {
      filename: "sample_one.sample_summary.html",
      html: `<!doctype html><html><body><h1>Sample one</h1></body></html>`
    }
  }
};

let bundleRequests = 0;
let compressedRequests = 0;
let fallbackRequests = 0;

const server = http.createServer((request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");

  if (url.pathname === "/assets/wings-demo-loader.js") {
    response.writeHead(200, {"Content-Type": "text/javascript"});
    response.end(fs.readFileSync(path.join(root, "assets/wings-demo-loader.js")));
    return;
  }
  if (url.pathname === "/demo/wings_demo.wings.gz") {
    compressedRequests += 1;
    response.writeHead(200, {"Content-Type": "application/gzip"});
    response.end(gzipSync(JSON.stringify(bundle)));
    return;
  }
  if (url.pathname === "/demo/wings_demo.wings") {
    fallbackRequests += 1;
    response.writeHead(200, {"Content-Type": "application/json"});
    response.end(JSON.stringify(bundle));
    return;
  }

  if (url.pathname === "/results.html") {
    response.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store"
    });
    response.end(resultsHtml);
    return;
  }

  if (url.pathname === "/api/runs/auto-run/bundle") {
    bundleRequests += 1;
    response.writeHead(200, {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    });
    response.end(JSON.stringify(bundle));
    return;
  }

  response.writeHead(404);
  response.end("Not found");
});

(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  const address = server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;

  const browser = await chromium.launch({headless: true});

  try {
    const page = await browser.newPage();

    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));

    await page.goto(`${baseUrl}/results.html?run=auto-run`);

    await page.waitForSelector("#report-viewer.is-open");

    assert.equal(bundleRequests, 1);

    const reportStatus = await page.locator("#report-status").innerText();
    assert.match(reportStatus, /WINGS run auto-run/);
    assert.match(reportStatus, /1 sample reports/);

    assert.equal(
      await page.locator("#bundle-launcher").evaluate(
        (element) => getComputedStyle(element).display
      ),
      "none"
    );

    const frame = page.frameLocator("#report-frame");
    await frame.locator("#auto-run-marker").waitFor();

    assert.equal(
      await frame.locator("#auto-run-marker").innerText(),
      "AUTO_OPEN_RUN_SUMMARY"
    );

    await page.goto(`${baseUrl}/results.html?demo=1`);
    await page.frameLocator("#report-frame").locator("#auto-run-marker").waitFor();
    assert.equal(compressedRequests, 1);
    assert.equal(fallbackRequests, 0);
    await page.addInitScript(() => { window.DecompressionStream = undefined; });
    await page.goto(`${baseUrl}/results.html?demo=1`);
    await page.frameLocator("#report-frame").locator("#auto-run-marker").waitFor();
    assert.equal(compressedRequests, 1);
    assert.equal(fallbackRequests, 1);
    assert.deepEqual(errors, []);

    console.log(
      "Results auto-open browser check passed: run query, gzip demo, and compatibility fallback rendered."
    );
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
})().catch((error) => {
  console.error(error);
  server.close();
  process.exitCode = 1;
});
