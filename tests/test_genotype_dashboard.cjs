const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const source=fs.readFileSync(path.join(root,'assets/wings-genotypes.js'),'utf8');
const snapshot={schema_version:'wings.genotype-frequencies.v1',unit:'SRA run',has_metadata:true,
  audit:{included_runs:10,assigned_runs:10},groups:[
    {month:'2025-01',host:'Bird',location:'USA/Kentucky//',genotype:'D1.1',status:'assigned',n:3},
    {month:'2025-01',host:'Bird',location:'USA/Kentucky//',genotype:'B3.13',status:'assigned',n:7}]};

class Node {
  constructor(tag){this.tag=tag;this.children=[];this.attrs={};this.value='';this.checked=false;this.style={};this.listeners={};this.classList={toggle(){}};}
  append(...nodes){for(const node of nodes){node.parentNode?.removeChild(node);node.parentNode=this;this.children.push(node);}}
  removeChild(node){const i=this.children.indexOf(node);if(i<0)throw Error('Not a child');this.children.splice(i,1);node.parentNode=null;}
  replaceChildren(...nodes){for(const node of [...this.children])this.removeChild(node);this.append(...nodes);}
  after(...nodes){if(!this.parentNode)return;const parent=this.parentNode;for(const node of nodes)node.parentNode?.removeChild(node);const i=parent.children.indexOf(this);for(const node of nodes)node.parentNode=parent;parent.children.splice(i+1,0,...nodes);}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(name,fn){this.listeners[name]=fn;}
  querySelector(selector){const value=selector.match(/^\[value="([^"]*)"\]$/)?.[1];return this.children.find(n=>n.value===value)||null;}
}
function harness(embedded, local=null) {
  const nodes={};
  const markup=fs.readFileSync(path.join(root,'genotypes.html'),'utf8');
  for(const match of markup.matchAll(/id="(gf-[^"]+)"/g))nodes[match[1]]=new Node('div');
  for(const match of markup.matchAll(/<select id="(gf-[^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){
    const node=nodes[match[1]];
    for(const option of match[2].matchAll(/<option([^>]*)>([^<]*)<\/option>/g)){
      const child=new Node('option');child.value=option[1].match(/value="([^"]*)"/)[1];child.textContent=option[2];child.disabled=/\bdisabled\b/.test(option[1]);node.append(child);
      if(node.children.length===1 || /\bselected\b/.test(option[1]))node.value=child.value;
    }
  }
  nodes['gf-denominator'].value='assigned';
  if(embedded!==null)nodes['wings-genotype-frequency-data']={textContent:embedded};
  if(local!==null)nodes['wings-genotype-local-data']={textContent:JSON.stringify(local)};
  const body=new Node('body');body.append(...Object.values(nodes));
  const findId=(node,id)=>node.id===id?node:(node.children||[]).map(child=>findId(child,id)).find(Boolean);
  let ready,requests=0;
  const document={getElementById:id=>nodes[id]||findId(body,id)||null,createElement:tag=>new Node(tag),createElementNS:(_,tag)=>new Node(tag),createTextNode:text=>({textContent:text}),addEventListener:(_,fn)=>{ready=fn;}};
  const context=vm.createContext({document,Option:function(text,value){const n=new Node('option');n.textContent=text;n.value=value;return n;},
    fetch:async()=>{requests++;return {ok:true,json:async()=>snapshot};},setTimeout});
  vm.runInContext(source,context);ready();
  return {nodes,context,document,requests:()=>requests};
}
test('embedded dashboard renders and filters without a network request',async()=>{
  const h=harness(JSON.stringify(snapshot));await new Promise(setImmediate);
  assert.equal(h.requests(),0);
  assert.equal(h.nodes['gf-controls'].hidden,false);
  assert.equal(h.nodes['gf-export-svg'].disabled,false,h.nodes['gf-status'].textContent);
  assert.equal(h.nodes['gf-genotype'].children.length,3);
  assert.equal(h.nodes['gf-source'].value,'all');
  assert.equal(h.nodes['gf-view'].value,'monthly');
  assert.equal(h.nodes['gf-source'].querySelector('[value="wings"]').disabled,true);
  h.nodes['gf-genotype'].value='D1.1';h.nodes['gf-genotype'].listeners.change();
  assert.match(h.nodes['gf-denominator-note'].textContent,/denominator includes the other genotypes/);
  const table=h.nodes['gf-table'].children[0];
  assert.deepEqual(table.children[1].children[0].children.map(n=>n.textContent),['Public Data','SRA run','2025-01','D1.1','3','10','30.0%']);
});
test('month pickers contain labeled calendar months and filter inclusively',async()=>{
  const d=JSON.parse(JSON.stringify(snapshot));
  d.groups[1].month='2025-03';
  const h=harness(JSON.stringify(d));await new Promise(setImmediate);
  assert.deepEqual(h.nodes['gf-from'].children.map(n=>n.textContent),['First available month','January 2025','February 2025','March 2025']);
  h.nodes['gf-from'].value='2025-03';h.nodes['gf-through'].value='2025-03';h.nodes['gf-through'].listeners.change();
  assert.equal(h.nodes['gf-stats'].children[1].children[1].textContent,'7');
  const markup=fs.readFileSync(path.join(root,'genotypes.html'),'utf8');
  assert.match(markup,/<select id="gf-from">/);assert.match(markup,/<select id="gf-through">/);
  assert.doesNotMatch(markup,/type="month"/);
});
test('WINGS/public switching separates cohorts, units and filters without fetching',async()=>{
  const local={schema_version:snapshot.schema_version,unit:'WINGS sample',has_metadata:true,
    audit:{included_samples:3,assigned_samples:2},groups:[
      {month:'2026-04',host:'Black Vulture',location:'USA / Kentucky',genotype:'Minor114',status:'assigned',n:2},
      {month:null,host:'Snow Goose',location:'USA / Kentucky',genotype:null,status:'not_eligible',n:1}]};
  const h=harness(JSON.stringify(snapshot),local);await new Promise(setImmediate);
  assert.equal(h.requests(),0);assert.equal(h.nodes['gf-source'].value,'all');
  assert.deepEqual(h.nodes['gf-source'].children.map(n=>n.textContent),['All','WINGS','Public Data']);
  assert.equal(h.nodes['gf-view'].value,'monthly');
  assert.deepEqual(h.nodes['gf-stats'].children[0].children.map(n=>n.textContent),['WINGS samples','2']);
  h.nodes['gf-source'].value='wings';h.nodes['gf-source'].listeners.change();
  assert.equal(h.nodes['gf-view'].value,'monthly');
  assert.deepEqual(h.nodes['gf-stats'].children[0].children.map(n=>n.textContent),['Included samples','2']);
  assert.equal(h.nodes['gf-from'].children[1].textContent,'April 2026');
  h.nodes['gf-genotype'].value='Minor114';h.nodes['gf-genotype'].listeners.change();
  h.nodes['gf-source'].value='public';h.nodes['gf-source'].listeners.change();
  assert.equal(h.nodes['gf-genotype'].value,'');
  assert.deepEqual(h.nodes['gf-stats'].children[0].children.map(n=>n.textContent),['Included runs','10']);
  assert.equal(h.nodes['gf-from'].children[1].textContent,'January 2025');
  h.nodes['gf-source'].value='wings';h.nodes['gf-source'].listeners.change();
  assert.equal(h.nodes['gf-genotype'].value,'Minor114');
  const row=h.nodes['gf-table'].children[0].children[1].children[0];
  assert.deepEqual(row.children.map(n=>n.textContent),['2026-04','Minor114','2','2','100.0%']);
  // An overall view still honors date filters; clear them to include undated samples.
  h.nodes['gf-from'].value='';h.nodes['gf-through'].value='';
  h.nodes['gf-view'].value='overall';h.nodes['gf-view'].listeners.change();
  h.nodes['gf-denominator'].value='all';h.nodes['gf-denominator'].listeners.change();
  const all=h.nodes['gf-table'].children[0].children[1].children[0];
  assert.deepEqual(all.children.map(n=>n.textContent),['Overall','Minor114','2','3','66.7%']);
  assert.match(h.nodes['gf-unit-note'].textContent,/WINGS sample/);
});
test('a malformed public snapshot leaves embedded WINGS samples usable',async()=>{
  const local={schema_version:snapshot.schema_version,unit:'WINGS sample',has_metadata:true,
    audit:{included_samples:0,assigned_samples:0},groups:[]};
  const h=harness('{',local);await new Promise(setImmediate);
  assert.equal(h.requests(),0);assert.equal(h.nodes['gf-source'].value,'all');
  assert.equal(h.nodes['gf-from'].disabled,true);
  assert.match(h.nodes['gf-status'].textContent,/Could not load the public snapshot/);
});
test('public attribution remains a clickable repository link in All and Public Data',async()=>{
  const local={schema_version:snapshot.schema_version,unit:'WINGS sample',has_metadata:true,audit:{included_samples:0,assigned_samples:0},groups:[]};
  const h=harness(JSON.stringify(snapshot),local);await new Promise(setImmediate);
  for(const key of ['all','public','wings','all']){
    h.nodes['gf-source'].value=key;h.nodes['gf-source'].listeners.change();
    const links=h.nodes['gf-source-description'].children.filter(n=>n.tag==='a');
    assert.equal(links.length,key==='wings'?0:1);
    if(links.length){
      assert.equal(links[0].attrs.href,'https://github.com/andersen-lab/avian-influenza');
      assert.equal(links[0].attrs.target,'_blank');assert.equal(links[0].attrs.rel,'noopener noreferrer');
    }
  }
});
test('All renders aligned monthly panels with shared colors and separate bar counts',async()=>{
  const local={schema_version:snapshot.schema_version,unit:'WINGS sample',has_metadata:true,audit:{included_samples:5,assigned_samples:5},groups:[
    {month:'2025-01',host:'Bird',location:'USA/Kentucky//',genotype:'D1.1',status:'assigned',n:4},
    {month:'2025-01',host:'Bird',location:'USA/Kentucky//',genotype:'B3.13',status:'assigned',n:1}]};
  const h=harness(JSON.stringify(snapshot),local);await new Promise(setImmediate);
  const svg=h.nodes['gf-chart'].children[0];
  const bars=svg.children.filter(n=>n.tag==='rect' && n.attrs['aria-label']);
  const wings=bars.find(n=>n.attrs['aria-label'].startsWith('WINGS ·') && n.attrs['aria-label'].includes('D1.1'));
  const pub=bars.find(n=>n.attrs['aria-label'].startsWith('Public Data ·') && n.attrs['aria-label'].includes('D1.1'));
  assert.equal(wings.attrs.x,pub.attrs.x);assert.equal(wings.attrs.fill,pub.attrs.fill);
  assert.match(wings.attrs['aria-label'],/4 of 5 samples, 80.0%/);
  assert.match(pub.attrs['aria-label'],/3 of 10 runs, 30.0%/);
  assert.ok(wings.attrs.y<pub.attrs.y);
});
test('standalone portal still fetches its snapshot; a corrupt embedded snapshot never falls back to network',async()=>{
  const portal=harness(null);await new Promise(setImmediate);
  assert.equal(portal.requests(),1);assert.equal(portal.nodes['gf-controls'].hidden,false);
  const corrupt=harness('{');await new Promise(setImmediate);
  assert.equal(corrupt.requests(),0);assert.match(corrupt.nodes['gf-status'].textContent,/Could not load/);
});
test('dashboard tab clones the embedded frame and accepts sizing only from that frame',()=>{
  let listener,posted=0;
  const frame={style:{},contentWindow:{postMessage(){posted++;}},addEventListener(){}};
  const context=vm.createContext({document:{getElementById:()=>({content:{querySelector:()=>({cloneNode:()=>frame})}})},addEventListener:(name,fn)=>{if(name==='message')listener=fn;}});
  vm.runInContext(fs.readFileSync(path.join(root,'scripts/report/explorer-tabs.js'),'utf8'),context);
  const panel={children:[],append(x){this.children.push(x);}};
  const api=context.WINGS_EXPLORER_TABS;
  const controller=api._test.mountGenotypeDashboard({root:{dataset:{wseGenotypeTemplateId:'embedded'}}},panel);
  assert.equal(panel.children[0],frame);assert.ok(posted>0);
  listener({source:{},data:{type:'wings-genotype-height',height:500}});assert.equal(frame.style.height,undefined);
  listener({source:frame.contentWindow,data:{type:'wings-genotype-height',height:650}});assert.equal(frame.style.height,'650px');
  listener({source:frame.contentWindow,data:{type:'wings-genotype-height',height:Infinity}});assert.equal(frame.style.height,'650px');
  controller.refresh();assert.ok(posted>1);
});

const localFixture=()=>({schema_version:snapshot.schema_version,unit:'WINGS sample',has_metadata:true,
  audit:{included_samples:2,assigned_samples:2},groups:[
    {month:'2025-01',host:'Bird',location:'USA / Kentucky',genotype:'D1.1',status:'assigned',n:1},
    {month:'2025-03',host:'Bird',location:'USA / Kentucky',genotype:'D1.1',status:'assigned',n:1}]});
const publicFixture=()=>({schema_version:snapshot.schema_version,unit:'SRA run',has_metadata:true,
  audit:{included_runs:5,assigned_runs:5},groups:['2024-12','2025-01','2025-02','2025-03','2025-04'].map(month=>
    ({month,host:'Bird',location:'United States/Kentucky//',genotype:'D1.1',status:'assigned',n:1}))});
const change=(h,id,value)=>{h.nodes['gf-'+id].value=value;h.nodes['gf-'+id].listeners.change();};
const monthLabels=h=>h.nodes['gf-chart'].children[0].children.filter(n=>n.tag==='text' && /^\d{4}-\d{2}$/.test(n.textContent)).map(n=>n.textContent);

test('WINGS span defaults preserve wider public choices and user overrides',async()=>{
  const h=harness(JSON.stringify(publicFixture()),localFixture());await new Promise(setImmediate);
  assert.equal(h.nodes['gf-from'].value,'2025-01');assert.equal(h.nodes['gf-through'].value,'2025-03');
  assert.ok(h.nodes['gf-from'].children.some(n=>n.value==='2024-12'));
  change(h,'from','2024-12');change(h,'through','2025-04');
  change(h,'source','public');assert.equal(h.nodes['gf-from'].value,'');assert.equal(h.nodes['gf-through'].value,'');
  assert.equal(h.nodes['gf-stats'].children[0].children[1].textContent,'5');
  change(h,'source','wings');assert.equal(h.nodes['gf-from'].value,'2025-01');assert.equal(h.nodes['gf-through'].value,'2025-03');
  change(h,'source','all');assert.equal(h.nodes['gf-from'].value,'2024-12');assert.equal(h.nodes['gf-through'].value,'2025-04');
  change(h,'from','');change(h,'through','');change(h,'source','public');change(h,'source','all');
  assert.equal(h.nodes['gf-from'].value,'');assert.equal(h.nodes['gf-through'].value,'');
});

test('calendar toggle explains shared months, preserves its listener, and changes WINGS spacing',async()=>{
  const h=harness(JSON.stringify(publicFixture()),localFixture());await new Promise(setImmediate);
  const toggle=h.nodes['gf-show-empty'],listener=toggle.listeners.change;
  const help=h.document.getElementById('gf-calendar-help');assert.ok(help);
  assert.match(help.textContent,/at least one source/);
  assert.match(h.nodes['gf-calendar-control'].children[1].textContent,/empty in both sources/);
  assert.equal(toggle.attrs['aria-describedby'],'gf-calendar-help');
  const before=monthLabels(h);assert.equal(before.length,6);
  toggle.checked=true;listener();assert.deepEqual(monthLabels(h),before);
  assert.equal(h.document.getElementById('gf-calendar-help'),help);
  assert.equal(toggle.listeners.change,listener);
  change(h,'source','wings');assert.deepEqual(monthLabels(h),['2025-01','2025-03']);
  assert.match(help.textContent,/omit 1 months/);
  toggle.checked=true;listener();assert.deepEqual(monthLabels(h),['2025-01','2025-02','2025-03']);
  toggle.checked=false;listener();assert.deepEqual(monthLabels(h),['2025-01','2025-03']);
  change(h,'view','overall');assert.equal(help.hidden,true);assert.equal(h.nodes['gf-calendar-control'].hidden,true);
});

test('country aliases and hierarchical location choices retain both cohorts',async()=>{
  const h=harness(JSON.stringify(publicFixture()),localFixture());await new Promise(setImmediate);
  assert.deepEqual(h.nodes['gf-location'].children.map(n=>n.value),['','United States','United States / Kentucky']);
  for(const location of ['United States','United States / Kentucky']){
    change(h,'location',location);
    assert.equal(h.nodes['gf-stats'].children[0].children[1].textContent,'2');
    assert.equal(h.nodes['gf-stats'].children[1].children[1].textContent,'3');
  }
  assert.equal(h.requests(),0);
});
