const {test, describe} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const root = path.join(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const bundle = read('scripts/report/surveillance-explorer.js');
const moduleSource = read('scripts/report/explorer-view-navigator.js');
const embedded = bundle.split('/* WINGS_VIEW_NAVIGATOR_BEGIN */')[1].split('/* WINGS_VIEW_NAVIGATOR_END */')[0].trim();
assert.equal(embedded, moduleSource.trim());

function environment(source) {
  let document;
  class Node {
    constructor(tag) { this.tagName=tag; this.children=[]; this.attrs={}; this.style={}; this.handlers={}; this.hidden=false; this.text=''; this.parentElement=null; this.className='';
      this.classList={add:(...names)=>{this.className=[...new Set([...this.className.split(' ').filter(Boolean),...names])].join(' ');},remove:name=>{this.className=this.className.split(' ').filter(n=>n!==name).join(' ');},contains:name=>this.className.split(' ').includes(name),toggle:name=>{const has=this.classList.contains(name);if(has)this.classList.remove(name);else this.classList.add(name);return !has;}};
    }
    append(...nodes) { for(const n of nodes){if(n.parentElement)n.parentElement.children=n.parentElement.children.filter(x=>x!==n);this.children.push(n);n.parentElement=this;} }
    replaceChildren(...nodes) { for(const node of this.children)node.parentElement=null;this.children=[];this.append(...nodes); }
    setAttribute(k,v) {this.attrs[k]=String(v);}
    getAttribute(k) {return this.attrs[k]??null;}
    addEventListener(k,fn) {this.handlers[k]=fn;}
    get textContent() {return this.text+this.children.map(x=>x.textContent).join('');}
    set textContent(v) {this.text=String(v);this.children=[];}
    focus() {document.activeElement=this;}
    click() {this.handlers.click?.({target:this});}
  }
  document={createElement:tag=>new Node(tag),createElementNS:(_,tag)=>new Node(tag),activeElement:null};
  const ctx=vm.createContext({document,matchMedia:()=>({matches:true})});
  vm.runInContext(read('scripts/report/vendor/d3-hierarchy.v3.min.js'),ctx);
  vm.runInContext(source,ctx);
  const labels={overview:'Overview',genome:'Genome',amino:'Amino acids',genotypes:'Genotype frequencies',ecology:'Ecology',coverage:'Sampling & Detections',outbreak:'Outbreak context',concordance:'Concordance'};
  const buttons=Object.fromEntries(Object.entries(labels).map(([key,label])=>{const n=new Node('button');n.id='wse-tab-'+key;n.textContent=label;n.setAttribute('aria-selected',String(key==='overview'));return [key,n];}));
  const nav=new Node('div');
  const api=ctx.WINGS_VIEW_NAVIGATOR.mount(nav,buttons);
  const walk=(n,cls)=>[...(n.classList.contains(cls)?[n]:[]),...n.children.flatMap(c=>walk(c,cls))];
  const group=name=>walk(api.element,'wse-nav-group').find(n=>n.textContent===name);
  return {api,nav,buttons,document,group,walk};
}

for(const [name,source] of [['canonical navigator',moduleSource],['generated navigator',embedded]])describe(name,()=>{
  test('navigation omits the removed helper sentence and footer',()=>{
    const e=environment(source);
    assert.doesNotMatch(e.api.element.textContent,/Choose a view\. Keep your context\.|8 views · one connected workspace/);
    assert.equal(e.walk(e.api.element,'wse-nav-footer').length,0);
  });
  test('navigation avoids Quarto aside margin-column placement',()=>{
    const e=environment(source);
    // The embedded report's Quarto CSS has a !important named-grid-column
    // rule for aside:not(.footnotes):not(.sidebar). Navigation must not match.
    assert.equal(e.api.element.tagName,'nav');
    assert.equal(e.api.element.getAttribute('aria-label'),'Explorer navigation');
  });
  test('all eight views are visible initially, including Outbreak context',()=>{
    const e=environment(source);
    assert.equal(e.api.visibleViews().length,8);
    assert.ok(e.api.visibleViews().includes('outbreak'));
    assert.equal(Object.values(e.buttons).filter(b=>!b.hidden).length,8);
    assert.equal(e.nav.getAttribute('aria-orientation'),'vertical');
    assert.ok(parseFloat(e.buttons.outbreak.style.top)<parseFloat(e.nav.style.height));
  });
  test('collapsing groups hides destinations and selection reopens their group',()=>{
    const e=environment(source);e.group('Ecological context').click();
    assert.equal(e.group('Ecological context').getAttribute('aria-expanded'),'false');
    assert.equal(e.buttons.outbreak.hidden,true);
    assert.ok(!e.api.visibleViews().includes('outbreak'));
    e.api.select('outbreak');
    assert.equal(e.buttons.outbreak.hidden,false);
    assert.equal(e.group('Ecological context').getAttribute('aria-expanded'),'true');
  });
  test('switching views retains the original button nodes and event handlers',()=>{
    const e=environment(source);let clicks=0;e.buttons.amino.addEventListener('click',()=>clicks++);
    for(const view of ['genome','amino','outbreak','overview'])e.api.select(view);
    e.buttons.amino.click();assert.equal(clicks,1);
    assert.equal(e.buttons.amino.parentElement,e.nav);
  });
  test('mobile control names the current view and Escape closes it',()=>{
    const e=environment(source),toggle=e.walk(e.api.element,'wse-nav-toggle')[0];
    toggle.click();assert.equal(toggle.getAttribute('aria-expanded'),'true');
    e.api.element.handlers.keydown({key:'Escape'});
    assert.equal(toggle.getAttribute('aria-expanded'),'false');
    assert.equal(e.document.activeElement,toggle);
    e.api.select('outbreak');
    assert.match(toggle.textContent,/Outbreak context/);
    assert.equal(toggle.getAttribute('aria-controls'),'wse-tab-overview-navigation');
  });
  test('keyboard selection retains the open menu; pointer selection closes it',()=>{
    const e=environment(source),toggle=e.walk(e.api.element,'wse-nav-toggle')[0];
    toggle.click();e.api.select('amino',true);
    assert.equal(toggle.getAttribute('aria-expanded'),'true');
    e.buttons.amino.focus();e.api.select('amino',false);
    assert.equal(toggle.getAttribute('aria-expanded'),'false');
    assert.equal(e.document.activeElement,toggle);
  });
});
