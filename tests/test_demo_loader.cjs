const {test} = require('node:test');
const assert = require('node:assert/strict');
const {gzipSync} = require('node:zlib');
const {load} = require('../assets/wings-demo-loader.js');
const bundle = {format: 'WINGS_REPORT_BUNDLE', run_summary: {html: '<h1>Demo</h1>'}, samples: {example: {html: '<p>Sample</p>'}}, provenance: {data: {fixture: true}}};
const json = JSON.stringify(bundle);

for (const [name, compressed] of [
  ['gzip', () => new Response(gzipSync(json))],
  ['HTTP-decoded JSON', () => new Response(json)],
]) {
  test(name + ' preserves the complete bundle without fallback', async () => {
    const requests = [];
    assert.deepEqual(await load({fetchImpl: async url => {requests.push(url); return compressed();}}), bundle);
    assert.deepEqual(requests, ['demo/wings_demo.wings.gz']);
  });
}
for (const [name, compressed] of [
  ['missing asset', () => new Response('', {status: 404})],
  ['corrupt gzip', () => new Response(new Uint8Array([31, 139, 0]))],
  ['invalid bundle', () => new Response('{}')],
  ['network failure', () => {throw new Error('offline');}],
]) {
  test(name + ' falls back to original demo', async () => {
    const requests = [];
    const result = await load({fetchImpl: async url => {
      requests.push(url);
      return url.endsWith('.gz') ? compressed() : new Response(json);
    }});
    assert.deepEqual(result, bundle);
    assert.deepEqual(requests, ['demo/wings_demo.wings.gz', 'demo/wings_demo.wings']);
  });
}
test('unsupported browsers request only the original', async () => {
  const requests = [];
  assert.deepEqual(await load({Decompress: null, fetchImpl: async url => {requests.push(url); return new Response(json);}}), bundle);
  assert.deepEqual(requests, ['demo/wings_demo.wings']);
});
test('failure of both downloads surfaces an error', async () => {
  await assert.rejects(load({fetchImpl: async () => new Response('', {status: 404})}), /not available/);
});
test('invalid original bundle surfaces an error', async () => {
  await assert.rejects(load({Decompress: null, fetchImpl: async () => new Response('{}')}), /Invalid demo/);
});
