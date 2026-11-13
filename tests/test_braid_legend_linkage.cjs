'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const api=require('../scripts/report/genome-braid-clock.js');
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/braid_clock/synthetic_explorer.json'),'utf8'));

// Minimal DOM adapter: exercise the real dashboard and its generated SVG/HTML.
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.attrs={};this.nodes=new Map();this.classList={add(){},toggle(){}};this.innerHTML='';this.textContent='';this.dataset={};}
  setAttribute(k,v){this.attrs[k]=String(v);}
  addEventListener(){}
  append(...nodes){this.children.push(...nodes);}
  appendChild(node){this.append(node);return node;}
  replaceChildren(...nodes){this.children=[...nodes];}
  querySelector(s){if(!this.nodes.has(s))this.nodes.set(s,new Element());return this.nodes.get(s);}
  querySelectorAll(){return [];}
}
function dashboard(run){
  const prior=global.document;
  global.document={createElementNS:(_ns,tag)=>new Element(tag)};
  try{const data=structuredClone(fixture),root=new Element(),app=api.mount(root,data);run({app,root,data});}
  finally{if(prior===undefined)delete global.document;else global.document=prior;}
}
test('host legend matches actual strand colors and survives filtering and focus',()=>dashboard(({app,root})=>{
  const caption=()=>root.querySelector('.wbc-braid-caption').innerHTML;
  const hosts=[...new Set(app.m.samples.map(e=>e.host))];assert.ok(hosts.length>=2);
  assert.match(caption(),/WINGS samples, colored by host/);
  for(const host of hosts){
    const e=app.m.samples.find(e=>e.host===host);
    assert.ok(caption().includes(`background:${app.color(e)}`));assert.ok(caption().includes(host));
    const group=root.querySelector('.wbc-braid').children[0].children.find(n=>n.attrs['data-wbc-entity']===e.key);
    assert.ok(group.children.some(n=>n.attrs.stroke===app.color(e)||n.attrs.fill===app.color(e)));
  }
  const outside=app.m.samples.find(e=>e.host!==hosts[0]);
  app.host=hosts[0];app.selected=outside.key;app.refresh();
  assert.ok(caption().includes(outside.host));assert.match(caption(),/outside the host filter/);
  assert.match(caption(),/Thicker line: selected record/);
  app.selected=null;app.refresh();assert.ok(!caption().includes(`</span>${outside.host}</span>`));
}));
test('public grouping uses readable text and keeps raw provenance in escaped details',()=>dashboard(({app,root})=>{
  const e=app.m.references[0];assert.ok(e);
  const basis='algorithmic_exact_metadata_group:isolate+collection_date+country+state+host';
  e.raw.linkage_basis=basis;app.selectedReference=e.key;app.renderEvidence();
  let markup=root.querySelector('.wbc-evidence').innerHTML;
  assert.match(markup,/Matching isolate name, date, country, state and host/);
  assert.match(markup,/specimen identity is unverified/);
  assert.match(markup,/<details[^>]*><summary>Grouping details<\/summary><code>algorithmic_exact/);
  assert.equal(e.raw.linkage_basis,basis);
  e.raw.linkage_basis='<img src=x onerror=alert(1)>';app.renderEvidence();
  markup=root.querySelector('.wbc-evidence').innerHTML;
  assert.ok(!markup.includes('<img'));assert.ok(markup.includes('&lt;img'));
  e.raw.linkage_basis='';app.renderEvidence();
  assert.match(root.querySelector('.wbc-evidence').innerHTML,/Linkage basis:<\/strong> Not recorded/);
}));
test('host names are escaped in the color legend',()=>dashboard(({app})=>{
  const e=app.m.samples[0];e.host='<script>unexpected()</script>';
  const legend=app.hostLegend([e.key]);
  assert.ok(legend.includes('&lt;script&gt;'));assert.ok(!legend.includes('<script>'));
}));
