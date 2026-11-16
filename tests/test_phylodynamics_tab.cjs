const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..');
const tab=require('../scripts/report/phylodynamics-tab.js');
const api=require('../scripts/report/phylogeography-results.js');
const assets={style:Buffer.from('body{background:white}').toString('base64'),script:Buffer.from('window.viewerLoaded=true').toString('base64'),boundaries:Buffer.from('window.mapLoaded=true').toString('base64')};
test('offline document includes Unicode and escapes hostile JSON',()=>{
 const html=tab.documentFor({title:'Résumé </script><script>alert(1)</script>'},assets);
 assert.ok(html.includes('Résumé \\u003c/script>'));
 assert.ok(!html.includes('<script>alert(1)'));
 assert.ok(html.includes('window.viewerLoaded=true'));
 assert.ok(html.includes('URL.createObjectURL'));
});
test('illustrative data remain explicitly simulated and internally valid',()=>{
 const model=api.validateModel(JSON.parse(fs.readFileSync(path.join(root,'resources/demo/phylodynamics.json'))));
 assert.equal(model.demo,true);
 assert.equal(model.analyses.length,1);
 assert.equal(model.analyses[0].methods.beast,undefined);
 const pre=api.prepare(model.analyses[0].methods.fast);
 assert.equal(pre.data.focal_sample_ids.length,30);
 assert.ok(pre.data.focal_sample_ids.every(s=>s.startsWith('WINGS_DEMO')));
});
