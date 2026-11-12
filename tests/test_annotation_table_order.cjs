const {test,describe}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ROOT=path.resolve(__dirname,'..');
const ORDER=['PB2','PB1','PA','HA','NP','NA','MP','NS'];

class Node {
  constructor(tag,text='',className=''){Object.assign(this,{tag,text,className,children:[],attrs:{},events:{},parentElement:null,hidden:false});this.classList={contains:name=>this.className.split(/\s+/).includes(name)};}
  get tagName(){return this.tag.toUpperCase();}
  get textContent(){return this.text+this.children.map(node=>node.textContent).join('');}
  set textContent(value){this.text=String(value);this.children=[];}
  append(...nodes){for(const node of nodes){node.remove();node.parentElement=this;this.children.push(node);}}
  remove(){if(this.parentElement){const siblings=this.parentElement.children;siblings.splice(siblings.indexOf(this),1);this.parentElement=null;}}
  setAttribute(name,value){this.attrs[name]=String(value);}
  getAttribute(name){return this.attrs[name]??null;}
  matches(selector){if(selector.startsWith('#'))return this.id===selector.slice(1);if(selector.startsWith('.'))return this.classList.contains(selector.slice(1));if(selector==='a[href^="#"]')return this.tag==='a'&&this.getAttribute('href')?.startsWith('#');return this.tag===selector;}
  closest(selector){for(let node=this;node;node=node.parentElement)if(node.matches(selector))return node;return null;}
  querySelectorAll(selector){return this.children.flatMap(node=>[...(node.matches(selector)?[node]:[]),...node.querySelectorAll(selector)]);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  addEventListener(name,handler,capture=false){(this.events[name]||=[]).push({handler,capture});}
  dispatch(name,key){const event={key,stopped:false,preventDefault(){},stopImmediatePropagation(){this.stopped=true;}};for(const capture of [true,false])for(const listener of this.events[name]||[])if(listener.capture===capture&&!event.stopped)listener.handler(event);}
}
function table(headers,segments){
  const table=new Node('table'),head=new Node('thead'),header=new Node('tr'),body=new Node('tbody');
  for(const label of headers)header.append(new Node('th',label));head.append(header);table.append(head,body);
  const rows={};for(const segment of segments){const row=new Node('tr');for(const [i,label] of headers.entries())row.append(new Node('td',i===0?segment:label==='VADR status'?'PASS':label==='QC status'?'FAIL':label==='Consensus length'?'2,280 nt':'recorded'));rows[segment]=row;body.append(row);}
  return {table,body,header:header.children[0],rows,order:()=>body.children.map(row=>row.children[0].textContent)};
}
function environment(source){
  const main=new Node('main','','content'),toc=new Node('nav');toc.id='TOC';
  const document={readyState:'loading',addEventListener(){},createElement:tag=>new Node(tag),getElementById:id=>id==='TOC'?toc:main.querySelector('#'+id),querySelector:selector=>['main','main.content'].includes(selector)?main:null};
  const context=vm.createContext({document});vm.runInContext(fs.readFileSync(path.join(ROOT,source),'utf8'),context);
  return {api:context.WINGS_SAMPLE_PRESENTATION,main,toc};
}
for(const source of ['scripts/report/sample-report-presentation.js','scripts/report/sample-navigation.js'])describe(source,()=>{
  for(const [id,headers] of [
    ['vadr-annotation-quality-control',['Segment','Model','Subtype/group','VADR status']],
    ['consensus-and-variant-files',['Segment','Consensus length','QC status','Medaka inference','Consensus provenance','Consensus','Variant status','Variant calls','VCF']],
  ]){
    test(id+' initializes in numeric segment order and keeps the same rows and links',()=>{
      const h=environment(source),section=new Node('section');section.id=id;h.main.append(section);
      const t=table(headers,['NS','PB1','NP','HA','MP','PB2','NA','PA']);section.append(t.table);
      const link=new Node('a','recorded file');link.setAttribute('href','data:text/plain;base64,ZmFrZQ==');t.rows.HA.children[1].append(link);t.rows.PB2.hidden=true;
      const evidence=t.body.children.map(row=>[row,...row.children.map(cell=>cell.textContent)]);
      h.api.initialize();assert.deepEqual(t.order(),ORDER);assert.equal(t.body.children[0],t.rows.PB2);assert.equal(t.rows.PB2.hidden,true);
      assert.equal(link.getAttribute('href'),'data:text/plain;base64,ZmFrZQ==');assert.equal(link.parentElement,t.rows.HA.children[1]);
      for(const [row,...values] of evidence)assert.deepEqual(row.children.map(cell=>cell.textContent),values);
      assert.equal(t.table.querySelectorAll('th').length,headers.length);
    });
    test(id+' overrides legacy alphabetical sorting for click and keyboard',()=>{
      const h=environment(source),t=table(headers,['NS','PB1','NP','HA','MP','PB2','NA','PA']);let oldSort=0;
      t.header.addEventListener('click',()=>oldSort++);h.api.mountSegmentOrder(t.table);t.header.dispatch('click');
      assert.equal(oldSort,0);assert.deepEqual(t.order(),[...ORDER].reverse());t.header.dispatch('keydown','Enter');assert.deepEqual(t.order(),ORDER);
      const api=h.api.mountSegmentOrder(t.table);assert.equal(h.api.mountSegmentOrder(t.table),api);assert.equal(t.header.events.click.length,2);
    });
  }
  test('partial VADR results retain only the recorded segments in segment order',()=>{
    const h=environment(source),t=table(['Segment','Model','VADR status'],['NS','NP','NA','MP','HA']);
    h.api.mountSegmentOrder(t.table);assert.deepEqual(t.order(),['HA','NP','NA','MP','NS']);
  });
  test('expected-length table, heading, controls and empty section are removed',()=>{
    const h=environment(source),section=new Node('section');section.id='expected-segment-length-ranges';h.main.append(section);
    const heading=new Node('h3','Expected segment-length ranges'),wrapper=new Node('div','','escape-table-wrapper'),controls=new Node('div','Search table');
    const t=table(['Segment','Expected complete length'],ORDER);wrapper.append(controls,t.table);section.append(heading,wrapper);
    const link=new Node('a','Expected segment-length ranges');link.setAttribute('href','#expected-segment-length-ranges');h.toc.append(link);
    h.api.initialize();assert.equal(section.parentElement,null);assert.equal(h.main.querySelectorAll('table').length,0);assert.equal(h.toc.children.length,0);
  });
  test('removal preserves a shared QC panel, consensus lengths and embedded evidence',()=>{
    const h=environment(source),panel=new Node('div','','report-panel'),chart=new Node('div','Genome QC visualization'),script=new Node('script','{"unchanged":true}');
    const heading=new Node('div','Expected segment-length ranges','file-download-title'),wrapper=new Node('div','','escape-table-wrapper'),fileWrap=new Node('div','','file-download-table-wrap'),expected=table(['Segment','Expected complete length'],ORDER);
    const provenanceTitle=new Node('div','Reproducibility record','file-download-title'),note=new Node('div','Recorded workflow revision','file-download-note');
    const measured=table(['Segment','Consensus length','QC status'],['HA']);wrapper.append(expected.table);fileWrap.append(wrapper);panel.append(provenanceTitle,chart,heading,fileWrap,measured.table,script,note);h.main.append(panel);
    const result=h.api.removeExpectedLengthTables(h.main);assert.equal(result.removed,1);assert.equal(fileWrap.parentElement,null);assert.equal(heading.parentElement,null);
    assert.equal(panel.parentElement,h.main);assert.equal(chart.parentElement,panel);assert.equal(measured.table.parentElement,panel);assert.equal(script.textContent,'{"unchanged":true}');
    assert.equal(provenanceTitle.parentElement,panel);assert.equal(note.parentElement,panel);
    assert.equal(h.api.removeExpectedLengthTables(h.main).removed,0);
  });
});
