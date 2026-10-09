/* Load the public demo with gzip compression where supported. */
(() => {
  "use strict";

  function validate(bundle) {
    const summary = bundle?.run_summary;
    const html = typeof summary === "string" ? summary : summary?.html;
    if (bundle?.format !== "WINGS_REPORT_BUNDLE" || typeof html !== "string" ||
        !bundle.samples || typeof bundle.samples !== "object" || Array.isArray(bundle.samples)) {
      throw new Error("Invalid demo report bundle.");
    }
    return bundle;
  }

  async function load(options = {}) {
    const fetchImpl = options.fetchImpl || globalThis.fetch;
    const Decompress = Object.prototype.hasOwnProperty.call(options, "Decompress")
      ? options.Decompress : globalThis.DecompressionStream;
    if (typeof Decompress === "function") {
      try {
        const response = await fetchImpl("demo/wings_demo.wings.gz", {cache: "no-store"});
        if (!response.ok) throw new Error("Compressed demo unavailable.");
        const bytes = new Uint8Array(await response.arrayBuffer());
        let bundle;
        if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
          const stream = new Blob([bytes]).stream().pipeThrough(new Decompress("gzip"));
          bundle = await new Response(stream).json();
        } else {
          // Fetch may already have decoded an HTTP Content-Encoding response.
          bundle = JSON.parse(new TextDecoder().decode(bytes));
        }
        return validate(bundle);
      } catch (error) {
        // Keep older deployments, unsupported gzip implementations and corrupt
        // compressed assets usable through the original JSON demo.
      }
    }
    const response = await fetchImpl("demo/wings_demo.wings", {cache: "no-store"});
    if (!response.ok) throw new Error("Demo bundle is not available yet.");
    return validate(await response.json());
  }

  const api = {load};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else globalThis.WINGS_DEMO_LOADER = api;
})();
