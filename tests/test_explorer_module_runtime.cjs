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
    this.classList = {
      add:(value)=>{if(!this.classList.contains(value))this.className += ' '+value;},
      remove:(value)=>{this.className=this.className.split(/\s+/).filter(v=>v!==value).join(' ');},
      contains:(value)=>this.className.split(/\s+/).includes(value),
      toggle:(value,force)=>{const include=force===undefined?!this.classList.contains(value):force;if(include)this.classList.add(value);else this.classList.remove(value);return include;},
    };
  }
  get parentElement(){return this.parentNode;}
  get tagName(){return this.tag.toUpperCase();}
  get childNodes(){return this.children;}
  contains(node){return node===this||this.children.some(child=>child.contains(node));}
  detach(node){if(node.parentNode){const a=node.parentNode.children;a.splice(a.indexOf(node),1);}node.parentNode=this;}
  append(...nodes){for(const node of nodes){this.detach(node);this.children.push(node);}}
  replaceChildren(...nodes){for(const node of this.children)node.parentNode=null;this.children=[];this.append(...nodes);}
  prepend(...nodes){for(const node of [...nodes].reverse()){this.detach(node);this.children.unshift(node);}}
  insertBefore(node, anchor){this.detach(node);const i=this.children.indexOf(anchor);assert.ok(i>=0);this.children.splice(i,0,node);}
  set innerHTML(value){this.children=[];this.textContent=value;}
  setAttribute(name,value){this.attrs[name]=String(value);if(name==='class')this.className=String(value);if(name==='id')this.id=String(value);}
  getAttribute(name){return this.attrs[name]??null;}
  removeAttribute(name){delete this.attrs[name];}
  addEventListener(name,fn){this.listeners[name]=fn;}
  focus(){this.focused=true;}
  scrollIntoView(){this.scrolled=true;}
  getBoundingClientRect(){return {top:this.top??0};}
  remove(){if(this.parentNode){const siblings=this.parentNode.children;siblings.splice(siblings.indexOf(this),1);this.parentNode=null;}}
  matches(selector){
    if(selector.startsWith('.'))return this.classList.contains(selector.slice(1));
    if(selector.startsWith('#'))return this.id===selector.slice(1);
    const compound=selector.match(/^([a-z][a-z0-9-]*)\.([a-z0-9-]+)$/i);
    if(compound)return this.tag===compound[1]&&this.classList.contains(compound[2]);
    if(selector==='a[href^="#"]')return this.tag==='a'&&this.attrs.href?.startsWith('#');
    const role=selector.match(/^\[role=["']?([^"'\]]+)["']?\]$/);
    return role?this.attrs.role===role[1]:this.tag===selector;
  }
  closest(selector){for(let node=this;node;node=node.parentNode)if(node.matches(selector))return node;return null;}
  querySelectorAll(selector){return this.children.flatMap(node=>[...(node.matches(selector)?[node]:[]),...node.querySelectorAll(selector)]);}
  querySelector(selector){
    return this.querySelectorAll(selector)[0] || null;
  }
}

function mount(text=source) {
  const root=new Element('main'),shell=new Element('section','wse-shell');root.append(shell);
  const names=['wse-timeline-panel','wse-main-grid','wse-subtitle','wbc-embedded','wse-genome-panel','wse-footer-note','wse-ecology-panel','wse-outbreak-panel'];
  const nodes=Object.fromEntries(names.map(name=>[name,new Element('section',name)]));shell.append(...Object.values(nodes));
  nodes['wbc-embedded'].append(new Element('div','wbc-run-seasonal-summary'));
  const callbacks=[];
  const concordance={refresh(){}};
  const context=vm.createContext({
    document:{createElement:tag=>new Element(tag),createElementNS:(_ns,tag)=>new Element(tag),getElementById:()=>null},
    Option:function(text,value){const node=new Element('option');node.textContent=text;node.value=value;return node;},
    requestAnimationFrame:fn=>callbacks.push(fn),setTimeout:fn=>callbacks.push(fn),
    WINGS_EVIDENCE_SYNTHESIS:{mount(_explorer,app){app.append(new Element('section','wse-evidence-synthesis'));}},
    WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE:{mount(){return concordance;},mountMigrationContext(_explorer,panel){panel.append(new Element("div","nightly-context-fixture"));return {refresh(){}};}},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../scripts/report/vendor/d3-hierarchy.v3.min.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../scripts/report/explorer-view-navigator.js'),'utf8'),context);
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

test('grouped navigation retains sample and host selection across views',()=>{
  const h=mount(),sample=h.root.querySelector('.wse-app-sample'),host=h.root.querySelector('.wse-app-host');
  sample.value='a';sample.listeners.change();host.value='Duck';host.listeners.change();
  for(const name of ['genome','amino','ecology','coverage','outbreak','concordance','overview']){
    h.tabs.buttons[name].listeners.click();
    assert.equal(h.tabs.active,name);
    assert.equal(h.explorer.selectedSampleId,'a');
    assert.equal(h.explorer.hostFilter,'Duck');
    assert.equal(sample.value,'a');
  }
});

test('vertical keyboard navigation follows the visible group order',()=>{
  const h=mount(),press=(name,key)=>h.tabs.buttons[name].listeners.keydown({key,preventDefault(){}});
  press('overview','End');assert.equal(h.tabs.active,'concordance');
  press('concordance','ArrowUp');assert.equal(h.tabs.active,'outbreak');
  press('outbreak','Home');assert.equal(h.tabs.active,'overview');
  h.root.querySelector('.wse-nav-group').listeners.click();
  press('overview','ArrowDown');assert.equal(h.tabs.active,'ecology');
  h.tabs.activate('amino');assert.equal(h.tabs.buttons.amino.hidden,false);
});

function pipelineHarness(invalid=false) {
  const root=new Element('main'),top=new Element('ul','nav-tabs'),tabset=new Element('div','panel-tabset');
  top.append(new Element('a'),new Element('a'));root.append(top,tabset);
  const nativeNav=new Element('ul','nav-tabs'),content=new Element('div','tab-content');tabset.append(nativeNav,content);
  const labels={summary:'Run Summary',samples:'Sample Detail',distribution:'Subtype/Genotype Distribution',coverage:'Genome Coverage'};
  const panels={},buttons={};
  for(const [name,label] of Object.entries(labels)){
    const link=new Element('a','nav-link'),li=new Element('li'),panel=new Element('div','tab-pane');
    link.textContent=label;link.id='pipeline-'+name+'-tab';panel.id='pipeline-'+name;
    link.setAttribute('role','tab');link.setAttribute('aria-controls',panel.id);
    if(name==='summary'){link.classList.add('active');panel.classList.add('active');const overview=new Element('section');overview.id='overview';panel.append(overview);}
    li.append(link);nativeNav.append(li);content.append(panel);panels[name]=panel;buttons[name]=link;
  }
  const input=new Element('input');input.value='retained filter';panels.samples.append(input);
  if(invalid)buttons.samples.textContent='An unrelated tab';
  const ctx=vm.createContext({document:{readyState:'loading',addEventListener(){},createElement:tag=>new Element(tag),createElementNS:(_ns,tag)=>new Element(tag),getElementById:id=>root.querySelector('#'+id)}});
  for(const file of ['vendor/d3-hierarchy.v3.min.js','explorer-view-navigator.js','pipeline-view-navigator.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../scripts/report',file),'utf8'),ctx);
  const api=ctx.WINGS_PIPELINE_NAVIGATION.mount(tabset);
  return {api,root,top,tabset,nativeNav,content,input,panels,buttons,ctx};
}

test('Pipeline Results uses one navigator while retaining the two outer tabs',()=>{
  const h=pipelineHarness();
  assert.ok(h.api);assert.equal(h.root.querySelectorAll('.wse-view-navigator').length,1);
  assert.equal(h.top.parentNode,h.root);assert.equal(h.top.children.length,2);
  assert.equal(h.ctx.WINGS_PIPELINE_NAVIGATION.mount(h.tabset),h.api);
  assert.equal(h.api.navigation.element.tag,'nav');
  assert.equal(h.api.navigation.element.getAttribute('aria-label'),'Pipeline Results navigation');
});

test('all four Pipeline views retain their existing panels and filter state',()=>{
  const h=pipelineHarness();
  for(const name of ['samples','distribution','coverage','summary']){
    h.buttons[name].listeners.click({preventDefault(){}});
    assert.equal(h.api.active,name);assert.equal(h.api.panels[name],h.panels[name]);
    assert.equal(Object.values(h.panels).filter(p=>!p.hidden).length,1);
    assert.equal(h.panels[name].classList.contains('active'),true);
    assert.equal(h.buttons[name].getAttribute('aria-selected'),'true');
    assert.equal(h.input.value,'retained filter');assert.equal(h.input.parentNode,h.panels.samples);
  }
});

test('Pipeline keyboard order and Bootstrap tab notifications remain synchronized',()=>{
  const h=pipelineHarness(),press=(name,key)=>h.buttons[name].listeners.keydown({key,preventDefault(){}});
  press('summary','End');assert.equal(h.api.active,'coverage');
  press('coverage','ArrowUp');assert.equal(h.api.active,'distribution');
  h.buttons.samples.listeners['shown.bs.tab']();assert.equal(h.api.active,'samples');
  press('samples','Home');assert.equal(h.api.active,'summary');
});

test('unrecognized Pipeline tabsets are left unchanged',()=>{
  const h=pipelineHarness(true);assert.equal(h.api,null);
  assert.equal(h.nativeNav.parentNode,h.tabset);assert.equal(h.content.parentNode,h.tabset);
  assert.equal(h.root.querySelectorAll('.wse-view-navigator').length,0);
});

test('Pipeline startup finds the Run Summary tabset and is idempotent',()=>{
  const h=pipelineHarness();h.ctx.WINGS_PIPELINE_NAVIGATION.initialize();
  assert.equal(h.root.querySelectorAll('.wse-pipeline-workspace').length,1);
});

function sampleHarness(amd=false) {
  const body=new Element('body'),sidebar=new Element('aside','sidebar'),toc=new Element('nav'),main=new Element('main','content');
  toc.id='TOC';sidebar.append(toc);body.append(sidebar,main);
  const sections={};
  for(const id of ['sample-metadata','read-processing','segment-qc','influenza-subtype-evidence','blast-top-hits','irma-candidate-selection','genoflu-genotype','vadr-annotation-quality-control','consensus-and-variant-files','pipeline-provenance','interpretation','additional-evidence']){
    const section=new Element('section');section.id=id;sections[id]=section;main.append(section);
    const link=new Element('a');link.setAttribute('href','#'+id);link.textContent=id;toc.append(link);
  }
  const input=new Element('input');input.value='retained filter';sections['segment-qc'].append(input);
  const handlers={};
  let amdRegistrations=0;const define=()=>{amdRegistrations++;};define.amd={};
  const globals={document:{body,readyState:'loading',addEventListener(){},createElement:tag=>new Element(tag),createElementNS:(_ns,tag)=>new Element(tag),getElementById:id=>body.querySelector('#'+id)},addEventListener:(name,fn)=>{handlers[name]=fn;},requestAnimationFrame:fn=>fn()};
  if(amd)globals.define=define;
  const context=vm.createContext(globals);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../scripts/report/sample-navigation.js'),'utf8'),context);
  context.WINGS_SAMPLE_PRESENTATION?.initialize();
  const api=context.WINGS_SAMPLE_NAVIGATION.mount(main);
  return {api,main,body,sections,input,sidebar,context,handlers,define,get amdRegistrations(){return amdRegistrations;}};
}

test('sample reports receive grouped section navigation and a relative return button',()=>{
  const h=sampleHarness();assert.ok(h.api);
  assert.equal(h.api.back.href,'../../run_summary/run_summary.html');
  assert.equal(h.api.back.textContent,'← Back to run summary');
  assert.equal(h.api.navigation.element.tag,'nav');assert.equal(h.sidebar.hidden,true);
  assert.equal(h.body.classList.contains('wings-sample-navigated'),true);
  assert.ok(h.api.buttons['additional-evidence']);
});

test('sample section changes preserve original evidence nodes and table filters',()=>{
  const h=sampleHarness();
  for(const name of Object.keys(h.api.targets)){
    h.api.buttons[name].listeners.click({preventDefault(){}});
    assert.equal(h.api.active,name);assert.equal(h.api.buttons[name].getAttribute('aria-current'),'location');
    assert.equal(h.api.targets[name].scrolled,true);
    assert.equal(h.input.value,'retained filter');assert.equal(h.input.parentNode,h.sections['segment-qc']);
    assert.equal(Object.values(h.sections).some(section=>section.hidden),false);
  }
});

test('sample navigation has keyboard section jumps and mounts once',()=>{
  const h=sampleHarness();
  h.api.buttons.metadata.listeners.keydown({key:'End',preventDefault(){}});
  assert.equal(h.api.active,'additional-evidence');
  assert.equal(h.context.WINGS_SAMPLE_NAVIGATION.mount(h.main),h.api);
  assert.equal(h.main.querySelectorAll('.wse-sample-workspace').length,1);
});

test('sample navigation and return button initialize when Quarto loads RequireJS',()=>{
  const h=sampleHarness(true);
  assert.equal(h.context.define,h.define);assert.equal(h.amdRegistrations,0);
  assert.equal(h.api.back.href,'../../run_summary/run_summary.html');
  h.api.visit('segment-qc');assert.equal(h.api.active,'segment-qc');
  assert.equal(h.input.value,'retained filter');
});

function genofluHarness(status='Not assigned',values={PB1:'ea3',HA:'ea3',NP:'am13',NA:'am4N1',MP:'ea3',NS:'ea3'}){
  const section=new Element('section'),panel=new Element('div','report-panel'),badge=new Element('span','download-status');
  section.id='genoflu-genotype';badge.textContent=status;section.append(panel);panel.append(badge);
  const reason=new Element('p');reason.textContent='GenoFLU result: retained original result';panel.append(reason);
  const wrap=new Element('div','file-download-table-wrap'),table=new Element('table','genoflu-table'),tbody=new Element('tbody');
  const filter=new Element('input');filter.value='retained GenoFLU filter';wrap.append(filter,table);table.append(tbody);panel.append(wrap);
  for(const segment of ['PB2','PB1','PA','HA','NP','NA','MP','NS']){
    const row=new Element('tr'),a=new Element('td'),b=new Element('td');a.textContent=segment;b.textContent=values[segment]??'Not available';row.append(a,b);tbody.append(row);
  }
  const context=vm.createContext({document:{readyState:'loading',addEventListener(){},createElement:tag=>new Element(tag),createElementNS:(_ns,tag)=>new Element(tag),getElementById:()=>null}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../scripts/report/sample-report-presentation.js'),'utf8'),context);
  const api=context.WINGS_SAMPLE_PRESENTATION.mountGenoFLU(section);
  return {api,context,section,panel,wrap,table,filter,reason};
}

test('GenoFLU wheel keeps an unassigned genotype separate from six recorded calls',()=>{
  const h=genofluHarness();assert.ok(h.api);assert.equal(h.api.status,'Not assigned');assert.equal(h.api.count,6);
  assert.equal(h.api.root.querySelector('.wgc-center-status').textContent,'Not assigned');
  assert.equal(h.api.records.find(r=>r.segment==='PB2').call,null);
  assert.equal(h.api.records.find(r=>r.segment==='NA').call,'am4N1');
  assert.equal(h.api.groups.PB2.querySelector('path').getAttribute('fill'),'#FFFFFF');
  assert.equal(h.api.groups.NA.querySelector('path').getAttribute('fill'),'#8C1D40');
});

test('GenoFLU segment selection retains exact calls, source table and filter state',()=>{
  const h=genofluHarness();h.api.groups.NA.listeners.click();
  assert.equal(h.api.detail.querySelector('.wgc-call-value').textContent,'am4N1');
  assert.equal(h.api.detail.querySelector('.wgc-overall-status'),null);
  assert.equal(h.api.detail.querySelectorAll('dd').length,1);
  assert.equal(h.api.root.querySelector('.wgc-center-status').textContent,'Not assigned');
  assert.equal(h.api.groups.NA.getAttribute('aria-pressed'),'true');
  assert.equal(h.api.details.querySelector('table'),h.table);assert.equal(h.filter.value,'retained GenoFLU filter');
  assert.equal(h.reason.parentNode,h.api.details);
  assert.equal(h.context.WINGS_SAMPLE_PRESENTATION.mountGenoFLU(h.section),h.api);
});

test('GenoFLU keyboard selection and recorded assignment remain unchanged',()=>{
  const h=genofluHarness('D1.1');
  h.api.groups.PB2.listeners.keydown({key:'ArrowRight',preventDefault(){}});
  assert.equal(h.api.groups.PB1.getAttribute('aria-pressed'),'true');
  assert.equal(h.api.groups.PB1.focused,true);
  assert.equal(h.api.root.querySelector('.wgc-center-status').textContent,'D1.1');
  assert.equal(h.api.detail.querySelector('.wgc-overall-status'),null);
});

test('GenoFLU unavailable/skipped output does not become an assigned genotype',()=>{
  const h=genofluHarness('Not run',{});assert.equal(h.api.count,0);assert.equal(h.api.status,'Not run');
  assert.equal(h.api.records.every(record=>record.call===null),true);
  assert.equal(h.api.root.querySelector('.wgc-center-status').textContent,'Not run');
});

test('standalone IRMA candidate section is omitted from the sample navigator',()=>{
  const h=sampleHarness();assert.equal(h.main.querySelector('#irma-candidate-selection'),null);
  assert.equal(h.api.buttons['irma-candidate-selection'],undefined);
  assert.ok(h.api.buttons['segment-qc']);assert.ok(h.api.buttons['genoflu-genotype']);
});

test('standalone sample Interpretation is removed while evidence sections remain',()=>{
  const h=sampleHarness();assert.equal(h.main.querySelector('#interpretation'),null);
  assert.equal(h.api.buttons.interpretation,undefined);
  assert.ok(h.api.buttons['consensus-and-variant-files']);assert.ok(h.api.buttons['pipeline-provenance']);
});

test('consensus introduction is concise while original status definitions and files are retained',()=>{
  const h=genofluHarness(),section=new Element('section'),heading=new Element('h2'),original=new Element('p'),files=new Element('div','cell');
  original.textContent='Medaka processing is tracked explicitly. SUCCESS · MEDAKA; FAILED · IRMA FALLBACK; UNPOLISHED · IRMA FALLBACK; SKIPPED NO MODEL; SKIPPED QC. Variant failures are separate.';
  const table=new Element('table');files.append(table);section.append(heading,original,files);
  const guide=h.context.WINGS_SAMPLE_PRESENTATION.compactFileExplanation(section);
  assert.ok(guide);assert.equal(original.parentNode,guide);assert.equal(guide.open,undefined);
  assert.equal(section.querySelector('.wse-sample-file-intro').textContent,'Files and processing status are listed by segment. Unpolished IRMA fallbacks and variant failures are flagged.');
  assert.equal(table.parentNode,files);
  assert.equal(h.context.WINGS_SAMPLE_PRESENTATION.compactFileExplanation(section),guide);
});

function profileHarness(date='2025-10-20',additional=[]){
  const h=genofluHarness(),main=new Element('main');
  const kv=(heading,rows)=>{
    const panel=new Element('div','report-panel'),table=new Element('table'),head=new Element('thead'),headRow=new Element('tr'),body=new Element('tbody');
    for(const text of [heading,'Value']){const cell=new Element('th');cell.textContent=text;headRow.append(cell);}head.append(headRow);table.append(head,body);panel.append(table);main.append(panel);
    for(const [label,value] of rows){const row=new Element('tr');for(const text of [label,value]){const cell=new Element('td');cell.textContent=text;row.append(cell);}body.append(row);}
    return table;
  };
  const metadata=kv('Field',[['Sample Id','s1'],['Host','BLVU'],['Specimen Type','Dry (Oral+Cloacal)'],['Collection Date',date],['State','Kentucky'],['Country','USA'],['Metadata Status','COMPLETE'],['Medaka status','SUCCESS'],['Site code','Site A'],...additional]);
  const metrics=kv('Metric',[['Segments detected','8'],['Segments passing segment QC','6'],['Medaka provenance','retained in original report']]);
  const other=kv('Metric',[['Software','retained version']]);
  const api=h.context.WINGS_SAMPLE_PRESENTATION.mountSampleProfile(main);
  return {...h,main,metadata,metrics,other,profileApi:api};
}

test('sample profile retains collection metadata and omits the requested status rows',()=>{
  const h=profileHarness(),profile=h.profileApi.profile;
  assert.equal(profile.querySelector('.wsp-sample-id').textContent,'s1');
  assert.equal(profile.querySelector('.wsp-host-value').textContent,'BLVU');
  assert.equal(profile.querySelector('.wsp-specimen').textContent,'Dry (Oral+Cloacal)');
  assert.equal(profile.querySelector('.wsp-location').textContent,'Kentucky · USA');
  assert.equal(profile.querySelector('time').getAttribute('datetime'),'2025-10-20');
  assert.equal(profile.querySelector('.wsp-day').textContent,'20');
  assert.equal(profile.querySelector('.wsp-extra').querySelector('dd').textContent,'Site A');
  assert.ok(profile.querySelectorAll('dt').every(n=>!n.textContent.toLowerCase().includes('status')));
});

test('profile removes the redundant metrics table without affecting unrelated tables',()=>{
  const h=profileHarness();assert.equal(h.main.contains(h.metadata),false);assert.equal(h.main.contains(h.metrics),false);
  assert.equal(h.main.contains(h.other),true);
  assert.equal(h.context.WINGS_SAMPLE_PRESENTATION.mountSampleProfile(h.main),h.profileApi);
  assert.equal(h.main.querySelectorAll('.wings-sample-profile').length,1);
});

test('profile retains non-ISO dates as recorded instead of inventing a calendar date',()=>{
  const h=profileHarness('Unknown collection date');
  assert.equal(h.profileApi.profile.querySelector('time'),null);
  assert.equal(h.profileApi.profile.querySelector('.wsp-date-raw').textContent,'Unknown collection date');
});


test('compact profile groups exact coordinates in the location card without duplicate fields',()=>{
  const h=profileHarness('2025-12-11',[['Latitude','0'],['Longitude','-85.56343']]);
  const profile=h.profileApi.profile,location=profile.querySelector('.wsp-location-card');
  assert.equal(profile.querySelector('.wsp-layout').children.length,4);
  assert.equal(profile.querySelectorAll('.wsp-card').length,3);
  assert.deepEqual(location.querySelectorAll('dd').map(n=>n.textContent),['0','-85.56343']);
  assert.equal(profile.querySelector('.wsp-extra').querySelectorAll('dd').length,1);
  assert.equal(profile.querySelectorAll('img').length,0);
});

test('compact profile preserves a lone coordinate and explicitly marks an empty coordinate',()=>{
  const one=profileHarness('2025-10-20',[['Longitude','-85.56343']]).profileApi.profile;
  assert.equal(one.querySelector('.wsp-coordinates').querySelectorAll('dd').length,1);
  const empty=profileHarness('2025-10-20',[['Latitude','']]).profileApi.profile;
  assert.equal(empty.querySelector('.wsp-coordinates').querySelector('dd').textContent,'Not recorded');
});


test('nightly migration context mounts only inside the Ecology view',()=>{
  const h=mount();
  assert.ok(h.tabs.panels.ecology.querySelector('.nightly-context-fixture'));
  assert.equal(h.tabs.panels.concordance.querySelector('.nightly-context-fixture'),null);
  assert.ok(h.explorer.migrationContextController);
  h.tabs.activate('concordance');h.tabs.activate('ecology');
  assert.equal(h.root.querySelectorAll('.nightly-context-fixture').length,1);
});


test('Ecology moves the same host control to the timing table and restores it in other views',()=>{
  const h=mount(),toolbar=h.root.querySelector('.wse-app-toolbar'),host=h.root.querySelector('.wse-app-host');
  const label=host.parentElement,sample=h.root.querySelector('.wse-app-sample');
  assert.ok(toolbar.contains(host));
  h.tabs.activate('ecology');
  const dock=h.root.querySelector('.wse-timing-host-controls');
  const section=h.root.querySelector('.wse-timing-table-section');
  const summary=h.root.querySelector('.wbc-run-seasonal-summary');
  assert.equal(toolbar.parentElement,section);
  assert.ok(section.children.indexOf(toolbar)>section.children.indexOf(summary));
  assert.equal(host.parentElement,label);assert.ok(dock.contains(host));assert.ok(!toolbar.contains(host));
  assert.ok(dock.parentElement.contains(h.root.querySelector('.wbc-run-seasonal-summary')));
  assert.equal(sample.parentElement.children[0].textContent,'Sample for seasonal curve');
  host.value='Duck';host.listeners.change();assert.equal(h.explorer.hostFilter,'Duck');
  sample.value='a';sample.listeners.change();assert.equal(h.explorer.selectedSampleId,'a');assert.equal(h.explorer.hostFilter,'Duck');assert.ok(dock.contains(host));
  h.tabs.activate('genome');assert.equal(toolbar.parentElement,h.root.querySelector('.wse-app-shell'));assert.ok(toolbar.contains(host));assert.equal(host.value,'Duck');assert.equal(sample.parentElement.children[0].textContent,'Sample');
  h.tabs.activate('ecology');assert.equal(toolbar.parentElement,section);assert.ok(dock.contains(host));assert.equal(h.root.querySelectorAll('.wse-app-host').length,1);assert.equal(h.root.querySelectorAll('.wse-timing-host-controls').length,1);
});
