const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../scripts/report/tree-studio.js'), 'utf8');
const windowObj = {addEventListener(){}, open(){return null;}};
const context = vm.createContext({window:windowObj, globalThis:windowObj, console, Blob:class{}, URL:{createObjectURL(){return 'blob:x'},revokeObjectURL(){}}, document:{}});
vm.runInContext(source, context);
const T = windowObj.WINGS_TREE_STUDIO._test;

test('empty phylogeny keeps segment choices and explains missing trees', () => {
  let popupHtml = '';
  windowObj.open = () => ({document:{open(){},write(html){popupHtml = html;},close(){}},addEventListener(){}});
  windowObj.WINGS_TREE_STUDIO.open({payload:{trees:{},segment_order:['HA','NA']},samples:[]}, {segment:'HA'});
  assert.match(popupHtml, /"segment_order":\["HA","NA"\]/);
  assert.match(popupHtml, /No \$\{segment\} tree was generated for this run/);
  assert.match(popupHtml, /ready_segments\.tsv/);
  assert.doesNotMatch(popupHtml, /No tree available for this segment/);
});

function tree() {
  return {children:[
    {length:1,children:[
      {name:'A',sample_id:'A',length:1},
      {name:'B',sample_id:'B',length:2}
    ]},
    {length:1,children:[
      {name:'C',sample_id:'C',length:3},
      {name:'D',sample_id:'D',length:4}
    ]}
  ]};
}

function data(segment='HA') {
  const samples=['A','B','C','D'].map((id,i)=>({sample_id:id,host:i<2?'Duck':'Goose',country:'USA',state:i<2?'KY':'OH',collection_date:`2026-01-0${i+1}`,genotype:{call:i<2?'D1.1':'A3'}}));
  return {sampleById:new Map(samples.map(s=>[s.sample_id,s])), referenceById:new Map(), segment};
}

test('source clone preserves four distinct leaves and branch lengths', () => {
  const root = T.annotateTree(T.cloneSourceTree(tree()));
  const leaves = T.allLeaves(root);
  assert.deepEqual(Array.from(leaves, x=>x.name).sort(), ['A','B','C','D']);
  assert.equal(leaves.find(x=>x.name==='D').length, 4);
});

test('midpoint reroot preserves all leaves and total pairwise path endpoints', () => {
  const root = T.midpointRoot(tree());
  assert.equal(T.allLeaves(root).length, 4);
  assert.equal(root.length, 0);
  const newick = T.treeToNewick(root);
  for (const name of ['A','B','C','D']) assert.match(newick, new RegExp(name));
});

test('outgroup reroot places chosen tip as a direct child of displayed root', () => {
  const root = T.outgroupRoot(tree(), 's:D');
  assert.ok(root.children.some(c => c.sample_id === 'D'));
  assert.equal(T.allLeaves(root).length, 4);
});

test('ladderization changes child ordering without changing leaf membership', () => {
  const root = T.annotateTree(T.cloneSourceTree(tree()));
  T.sortTree(root, 'ladder-desc', data());
  assert.equal(T.allLeaves(root).length, 4);
  assert.deepEqual(new Set(T.allLeaves(root).map(x=>x.name)), new Set(['A','B','C','D']));
});

test('trait coloring and descendant consensus use supplied metadata only', () => {
  const root = T.annotateTree(T.cloneSourceTree(tree()));
  const d = data();
  const ctx = T.colorContext(root,d,'genotype');
  assert.deepEqual(Array.from(ctx.values), ['A3','D1.1']);
  const firstClade = root.children[0];
  assert.equal(T.descendantConsensus(firstClade,d,'genotype'),'D1.1');
  assert.equal(T.descendantConsensus(root,d,'genotype'),'');
});

test('rectangular and radial layouts produce finite coordinates', () => {
  for (const mode of ['rect','radial']) {
    const root=T.annotateTree(T.cloneSourceTree(tree()));
    if (mode==='rect') T.layoutRectangular(root,1200,700); else T.layoutRadial(root,1200,800);
    for (const leaf of T.allLeaves(root)) {
      assert.ok(Number.isFinite(leaf._x));
      assert.ok(Number.isFinite(leaf._y));
    }
  }
});

test('Newick export remains syntactically terminated and keeps branch lengths', () => {
  const root=T.annotateTree(T.cloneSourceTree(tree()));
  const text=T.treeToNewick(root);
  assert.ok(text.endsWith(';'));
  assert.match(text,/A:1\.0000000/);
});

test('genotype metadata never stringifies objects into legend labels', () => {
  assert.equal(T.genotypeText({call:'D1.1'}), 'D1.1');
  assert.equal(T.genotypeText({call:{value:'Minor114'}}), 'Minor114');
  assert.equal(T.genotypeText({status:'NOT_ASSIGNED'}), '');
  assert.equal(T.genotypeText({}), '');
});

test('missing categorical traits are counted separately from legend categories', () => {
  const root = T.annotateTree(T.cloneSourceTree(tree()));
  const d = data();
  d.sampleById.get('A').genotype = {status:'NOT_ASSIGNED'};
  const ctx = T.colorContext(root,d,'genotype');
  assert.ok(!Array.from(ctx.values).some(v => String(v).includes('[object Object]')));
  assert.equal(ctx.missingCount, 1);
});

test('trait filter matches selected categorical values with OR semantics', () => {
  const root = T.annotateTree(T.cloneSourceTree(tree()));
  const d = data();
  const infos = T.allLeaves(root).map(x => T.leafInfo(x, d));
  const ducks = infos.filter(info => T.matchesTraitFilter(info, 'host', ['Duck']));
  assert.equal(ducks.length, 2);
  const both = infos.filter(info => T.matchesTraitFilter(info, 'host', ['Duck','Goose']));
  assert.equal(both.length, 4);
  const noneActive = infos.filter(info => T.matchesTraitFilter(info, 'host', []));
  assert.equal(noneActive.length, 4);
});

test('trait filter keeps missing values separate and detects matching descendants', () => {
  const root = T.annotateTree(T.cloneSourceTree(tree()));
  const d = data();
  d.sampleById.get('A').genotype = {status:'NOT_ASSIGNED'};
  const infoA = T.leafInfo(T.allLeaves(root).find(x => x.sample_id === 'A'), d);
  assert.equal(T.filterTraitValue(infoA, 'genotype'), '__WINGS_FILTER_MISSING__');
  assert.equal(T.matchesTraitFilter(infoA, 'genotype', ['__WINGS_FILTER_MISSING__']), true);
  assert.equal(T.descendantHasFilterMatch(root.children[0], d, 'host', ['Duck']), true);
  assert.equal(T.descendantHasFilterMatch(root.children[1], d, 'host', ['Duck']), false);
});


test('US state names and postal codes normalize to one canonical trait value', () => {
  assert.equal(T.normalizeUSState('Kentucky'), 'KY');
  assert.equal(T.normalizeUSState('KY'), 'KY');
  assert.equal(T.normalizeUSState('us-ky'), 'KY');
  assert.equal(T.normalizeUSState('New York'), 'NY');
  assert.equal(T.normalizeUSState('Ontario'), 'Ontario');

  const root = T.annotateTree(T.cloneSourceTree(tree()));
  const d = data();
  d.sampleById.get('A').state = 'Kentucky';
  d.sampleById.get('B').state = 'KY';
  const states = T.allLeaves(root).map(x => T.leafInfo(x, d));
  assert.equal(states.filter(info => T.filterTraitValue(info, 'state') === 'KY').length, 2);
  assert.equal(states.find(info => info.id === 'A').state_raw, 'Kentucky');
});

test('wheel zoom is gentle for small trackpad deltas and capped for large wheel deltas', () => {
  const tinyIn = T.wheelZoomFactor(-1, 0);
  const tinyOut = T.wheelZoomFactor(1, 0);
  assert.ok(tinyIn > 0.99 && tinyIn < 1);
  assert.ok(tinyOut > 1 && tinyOut < 1.01);
  const largeIn = T.wheelZoomFactor(-1000, 0);
  const largeOut = T.wheelZoomFactor(1000, 0);
  assert.ok(largeIn > 0.88 && largeIn < 0.9);
  assert.ok(largeOut > 1.12 && largeOut < 1.14);
  assert.equal(T.wheelZoomFactor(-1000, 0), T.wheelZoomFactor(-60, 0));
  assert.equal(T.wheelZoomFactor(1000, 0), T.wheelZoomFactor(60, 0));
});


test('zoom to selected recenters around the chosen tip and never zooms out', () => {
  const fit = T.zoomViewBoxToPoint(1500, 900, 1200, 700, null);
  assert.ok(Math.abs(fit.w - 468.75) < 1e-9);
  assert.ok(Math.abs(fit.h - 281.25) < 1e-9);
  assert.ok(fit.x >= 0 && fit.x + fit.w <= 1500);
  assert.ok(fit.y >= 0 && fit.y + fit.h <= 900);
  assert.ok(1200 >= fit.x && 1200 <= fit.x + fit.w);
  assert.ok(700 >= fit.y && 700 <= fit.y + fit.h);

  const deep = {x:100, y:100, w:300, h:180};
  const recentered = T.zoomViewBoxToPoint(1500, 900, 800, 450, deep);
  assert.ok(recentered.w <= deep.w + 1e-9);
  assert.ok(recentered.h <= deep.h + 1e-9);
  assert.ok(800 >= recentered.x && 800 <= recentered.x + recentered.w);
  assert.ok(450 >= recentered.y && 450 <= recentered.y + recentered.h);
});

test('lasso geometry selects points inside a freehand polygon only', () => {
  const polygon = [{x:0,y:0},{x:10,y:0},{x:10,y:10},{x:0,y:10}];
  assert.equal(T.pointInPolygon({x:5,y:5}, polygon), true);
  assert.equal(T.pointInPolygon({x:15,y:5}, polygon), false);
  assert.equal(T.pointInPolygon({x:5,y:15}, polygon), false);
  assert.equal(T.pointInPolygon({x:5,y:5}, polygon.slice(0,2)), false);
  assert.match(T.lassoPath(polygon), /^M 0 0 L 10 0 L 10 10 L 0 10 Z$/);
});

test('zoom to multiple selected taxa fits every selected point in one view', () => {
  const pts = [{x:250,y:250},{x:900,y:500},{x:1100,y:650}];
  const vb = T.zoomViewBoxToPoints(1500, 900, pts);
  assert.ok(vb.w < 1500 && vb.h < 900);
  for (const p of pts) {
    assert.ok(p.x >= vb.x && p.x <= vb.x + vb.w);
    assert.ok(p.y >= vb.y && p.y <= vb.y + vb.h);
  }
});
