# Public demo compression

The results viewer prefers `demo/wings_demo.wings.gz`. It decompresses the
download in the browser using the native DecompressionStream API. Browsers
without that API, or failed compressed downloads, use `demo/wings_demo.wings`.
Keep both files published. No biological analysis or report data is changed.

After updating the demo bundle, regenerate and commit its compressed copy:

```sh
python scripts/compress_demo_bundle.py
python scripts/compress_demo_bundle.py --check
node --test tests/test_demo_loader.cjs
node tests/test_results_auto_open.cjs
```

The generator uses gzip level 6 with a fixed timestamp and no embedded filename.
CI checks that decompressing the committed gzip file reproduces the source
exactly. It also tests the loader and browser fallback using synthetic fixtures.
Browser tests require Playwright and its Chromium installation.

Compression reduces network transfer. It does not reduce the size of the
decompressed report in browser memory, change IRMA, or remove existing Git history.
