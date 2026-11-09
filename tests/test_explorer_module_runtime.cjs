const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../scripts/report/explorer-tabs.js'), 'utf8');

// Small DOM fixture for component behavior. Browser rendering is outside this test.
class Element {
  constructor(tag='div', className='') {
    Object.assign(this, {tag, className, children:[], attrs:{}, listeners:{}, style:{}, dataset:{}, hidden:false, value:'', textContent:''});
    this.classList = {add:(value)=>{this.className += ' '+value;}, toggle:()=>{}};
  }
  get parentElement(){return this.parentNode;}
  detach(node){if(node.parentNode){const a=node.parentNode.children;a.splice(a.indexOf(node),1);}node.parentNode=this;}
  append(...nodes){for(const node of nodes){this.detach(node);this.children.push(node);}}
  prepend(...nodes){for(const node of [...nodes].reverse()){this.detach(node);this.children.unshift(node);}}
  insertBefore(node, anchor){this.detach(node);const i=this.children.indexOf(anchor);assert.ok(i>=0);this.children.splice(i,0,node);}
  set innerHTML(value){this.children=[];this.textContent=value;}
  setAttribute(name,value){this.attrs[name]=String(value);}
  addEventListener(name,fn){this.listeners[name]=fn;}
  focus(){this.focused=true;}
  closest(){return null;}
  querySelector(selector){
    const matches = node => selector.startsWith('.') ? node.className.split(/\s+/).includes(selector.slice(1)) : node.tag===selector;
    for(const child of this.children){if(matches(child))return child;const nested=child.querySelector?.(selector);if(nested)return nested;}
    return null;
  }
}

function mount(text=source) {
  const root=new Element('main'),shell=new Element('section','wse-shell');root.append(shell);
  const names=['wse-timeline-panel','wse-main-grid','wse-subtitle','wbc-embedded','wse-genome-panel','wse-footer-note','wse-ecology-panel','wse-outbreak-panel'];
  const nodes=Object.fromEntries(names.map(name=>[name,new Element('section',name)]));shell.append(...Object.values(nodes));
  const callbacks=[];
  const concordance={refresh(){}};
  const context=vm.createContext({
    document:{createElement:tag=>new Element(tag),getElementById:()=>null},
    Option:function(text,value){const node=new Element('option');node.textContent=text;node.value=value;return node;},
    requestAnimationFrame:fn=>callbacks.push(fn),setTimeout:fn=>callbacks.push(fn),
    WINGS_EVIDENCE_SYNTHESIS:{mount(_explorer,app){app.append(new Element('section','wse-evidence-synthesis'));}},
    WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE:{mount(){return concordance;}},
  });
  vm.runInContext(text,context);
  const samples=[{sample_id:'a',host:'Duck',collection_date:'2025-01-01'}];
  const explorer={root,payload:{},samples,hosts:['Duck'],sampleById:new Map(samples.map(s=>[s.sample_id,s])),referenceById:new Map(),hostFilter:'ALL',selectedSampleId:null,updateSelection(){}};
  const tabs=context.WINGS_EXPLORER_TABS.mount(explorer);
  return {root,explorer,tabs,nodes,concordance};
}

test('standalone tabs mount, switch all views, and retain the concordance controller',()=>{
  const h=mount();
  assert.equal(h.explorer.concordanceController,h.concordance);
  for(const name of ['overview','genome','amino','genotypes','ecology','coverage','concordance','outbreak']){
    assert.doesNotThrow(()=>h.tabs.activate(name));assert.equal(h.tabs.active,name);
    assert.equal(h.root.dataset.wseActiveTab,name);
  }
});

test('run brief remains on Overview and timeline/map remain in Sampling',()=>{
  const h=mount(),brief=h.root.querySelector('.wse-evidence-synthesis'),toolbar=h.root.querySelector('.wse-app-toolbar');
  assert.equal(brief.hidden,false);assert.equal(toolbar.hidden,true);assert.equal(toolbar.style.display,'none');
  assert.equal(h.nodes['wse-main-grid'].parentNode,h.tabs.panels.coverage);
  assert.equal(h.nodes['wse-timeline-panel'].parentNode,h.tabs.panels.coverage);
  h.tabs.activate('coverage');assert.equal(brief.hidden,true);assert.equal(toolbar.hidden,false);assert.equal(h.nodes['wse-subtitle'].hidden,false);
  h.tabs.activate('genome');assert.equal(h.nodes['wse-subtitle'].hidden,true);
  h.tabs.activate('overview');assert.equal(brief.hidden,false);
});

test('clear selection resets a selected tree tip and its context text',()=>{
  const h=mount(),clear=h.root.querySelector('.wse-app-clear'),context=h.root.querySelector('.wse-app-context');
  h.explorer.selectedTreeTip={name:'tip_a',segment:'HA'};h.explorer.updateSelection();
  assert.equal(clear.disabled,false);assert.match(context.textContent,/Tree tip: tip_a/);
  clear.listeners.click();assert.equal(h.explorer.selectedTreeTip,null);assert.equal(clear.disabled,true);assert.equal(context.textContent,'No sample selected');
});

test('negative control detects the original undeclared subtitle error',()=>{
  const broken=source.replace(/^[ \t]*const subtitle = shell\.querySelector\("\.wse-subtitle"\);\r?\n/m,'');
  assert.notEqual(broken,source,'subtitle declaration was not found');
  assert.throws(()=>mount(broken),/subtitle is not defined/);
});

test('embedded tabs body is exactly the standalone implementation',()=>{
  const bundle=fs.readFileSync(path.join(__dirname,'../scripts/report/surveillance-explorer.js'),'utf8');
  const embedded=bundle.split('/* WINGS_EXPLORER_TABS_JS_BEGIN */')[1].split('/* WINGS_EXPLORER_TABS_JS_END */')[0];
  assert.equal(embedded.trim(),source.trim());
});


// WINGS_AMINO_MINIMAL_DOM_CHECK_V1
test('Amino acids opens with explicit empty state in the minimal DOM',()=>{
  const h=mount();
  h.tabs.activate('amino');
  assert.equal(h.tabs.active,'amino');
  assert.equal(h.tabs.panels.amino.hidden,false);
  assert.equal(h.root.querySelector('.wse-app-toolbar').hidden,true);
  assert.match(h.tabs.panels.amino.querySelector('p').textContent,/not embedded/);
});
