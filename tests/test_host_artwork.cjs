const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
function element(tag) {
  return {tagName: tag, children: [], events: {}, textContent: '', append(...nodes) {this.children.push(...nodes);},
    addEventListener(name, callback) {this.events[name] = callback;}, remove() {this.removed = true;}};
}
const context = vm.createContext({document: {readyState: 'loading', addEventListener() {}, createElement: element}});
vm.runInContext(fs.readFileSync(path.join(root, 'assets/birds/host-artwork.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(root, 'scripts/report/sample-report-presentation.js'), 'utf8'), context);
const {resolveHost} = context.WINGS_SAMPLE_PRESENTATION;

for (const [code, name, ebird] of [
  ['BLVU', 'Black Vulture', 'blkvul'], ['SNGO', 'Snow Goose', 'snogoo'],
  ['TUVU', 'Turkey Vulture', 'turvul'], ['CANG', 'Canada Goose', 'cangoo'],
  ['RTHA', 'Red-tailed Hawk', 'rethaw'],
]) test('offline illustration resolves for ' + name, () => {
  for (const value of [code, name, ebird, name + ' (' + code + ')', code.toLowerCase()]) {
    const bird = resolveHost(value);
    assert.equal(bird.name, name);
    assert.equal(bird.code, code);
    const original = fs.readFileSync(path.join(root, 'assets/birds', name.replaceAll(' ', '_') + '_' + code + '.svg'));
    assert.deepEqual(Buffer.from(bird.src.split(',')[1], 'base64'), original);
  }
});
test('unknown and conflicting hosts retain text without a guessed image', () => {
  for (const host of ['Unknown', 'Duck', '', null, 'Snow Goose (TUVU)', 'Snow Goose / Black Vulture']) assert.equal(resolveHost(host), null);
});
test('all drawings are available offline and repeated SVG stems have unique names/codes', () => {
  const birds = context.WINGS_HOST_ARTWORK;
  assert.equal(birds.length, 173);
  assert.equal(new Set(birds.map(bird => bird.name)).size, birds.length);
  const codes = birds.filter(bird => bird.code).map(bird => bird.code);
  assert.equal(new Set(codes).size, codes.length);
  for (const bird of birds) assert.match(bird.src, /^data:image\/svg\+xml;base64,/);
  assert.equal(resolveHost('Swan Goose').name, 'Swan Goose');
});
test('host cards show embedded artwork, species name and the exact recorded code', () => {
  const card = element('div');
  context.WINGS_SAMPLE_PRESENTATION.populateHostCard(card, 'SNGO');
  const image = card.children.find(node => node.tagName === 'img');
  assert.match(image.src, /^data:image\/svg\+xml;base64,/);
  assert.equal(image.alt, '');
  assert.equal(card.children.find(node => node.className === 'wsp-host-name').textContent, 'Snow Goose');
  assert.equal(card.children.find(node => node.className === 'wsp-host-code').textContent, 'SNGO');
  image.events.error();
  assert.equal(image.removed, true);
  assert.equal(card.children.find(node => node.className === 'wsp-host-code').textContent, 'SNGO');
});
test('unrecognized hosts keep the recorded text and omit an image', () => {
  const card = element('div');
  context.WINGS_SAMPLE_PRESENTATION.populateHostCard(card, 'Unspecified waterfowl');
  assert.equal(card.children.some(node => node.tagName === 'img'), false);
  assert.equal(card.children.find(node => node.className === 'wsp-host-value').textContent, 'Unspecified waterfowl');
});
test('recorded CAGO uses the Canada Goose drawing and keeps its recorded code', () => {
  assert.equal(resolveHost('CAGO').name, 'Canada Goose');
  assert.equal(resolveHost('cago').code, 'CANG');
  const card = element('div');
  context.WINGS_SAMPLE_PRESENTATION.populateHostCard(card, 'CAGO');
  assert.equal(card.children.find(node => node.tagName === 'img').src, resolveHost('CANG').src);
  assert.equal(card.children.find(node => node.className === 'wsp-host-name').textContent, 'Canada Goose');
  assert.equal(card.children.find(node => node.className === 'wsp-host-code').textContent, 'CAGO');
});
