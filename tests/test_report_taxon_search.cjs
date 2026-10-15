const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const source=fs.readFileSync(__dirname+'/../scripts/report/surveillance-explorer.js','utf8');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const classSource=source.slice(source.indexOf('  class Explorer {'),source.indexOf('  const initialize =',source.indexOf('  class Explorer {')));
const Explorer=vm.runInNewContext(classSource+'\nExplorer;', {esc});

class Element {
  constructor(){this.value='';this.hidden=false;this.innerHTML='';this.textContent='';this.listeners={};this.dataset={};this.focused=false;}
  addEventListener(name,fn){this.listeners[name]=fn;}
  fire(name,event={}){event.preventDefault??=()=>{event.prevented=true;};this.listeners[name]?.(event);return event;}
  focus(){this.focused=true;}
  contains(button){return button.owner===this;}
  querySelector(selector){
    if(selector==='button[data-taxon-key]'){
      const key=this.innerHTML.match(/data-taxon-key="([^"]+)"/)?.[1];if(!key)return null;
      this.firstButton??=new Element();this.firstButton.dataset.taxonKey=key;this.firstButton.owner=this;
      return this.firstButton;
    }
    return this.nodes?.[selector]??null;
  }
}
function fixture(){
  const samples=[{sample_id:'WINGS-ONE',host:'BLVU',collection_date:'2025-10-21'}, {sample_id:'WINGS-TWO',host:'MALL',collection_date:'2025-10-22'}];
  const references=[
    {reference_id:'REF1',isolate:'A/Canada Goose/Manitoba/2022',host:'Branta canadensis',segments:{HA:{accession_version:'PV306208.1',tips:[{name:'public_HA'}]}}},
    {reference_id:'REF2',isolate:'A/Canada Goose/Ontario/2023',host:'Branta canadensis',segments:{}}
  ];
  const payload={samples,public_reference_context:{references},trees:{
    HA:{root:{children:[{name:'WINGS-ONE__HA',sample_id:'WINGS-ONE',length:.1},{name:'public_HA',reference_id:'REF1',accession_version:'PV306208.1',length:.2},{name:'UNLINKED[tip]',length:.3}]}},
    NA:{root:{children:[{name:'WINGS-ONE__NA',sample_id:'WINGS-ONE',length:.1},{name:'public_NA',reference_id:'REF1',accession_version:'PV306210.1',length:.2},{name:'UNLINKED[tip]',length:.3}]}}
  }};
  const controls=new Element();
  controls.nodes=Object.fromEntries(['.wse-taxon-search','.wse-taxon-search-results','.wse-taxon-search-status','.wse-view-select','.wse-clear-selection'].map(selector=>[selector,new Element()]));
  const app=Object.assign(Object.create(Explorer.prototype),{
    samples,references,payload,sampleById:new Map(samples.map(s=>[s.sample_id,s])),referenceById:new Map(references.map(r=>[r.reference_id,r])),
    genomeControlsNode:controls,hostFilter:'ALL',treeMode:'all',segment:'HA',selectedSampleId:null,selectedReferenceId:null,hoverSampleId:null,
    updates:0,treeRenders:0,tabRenders:0,renderTrees(){this.treeRenders++;},renderSegmentTabs(){this.tabRenders++;},
    updateSelection(){this.updates++;this.syncTaxonSearchSelection();},setHostFilter(value){this.hostFilter=value;}
  });
  app.renderGenomeControls();return {app,controls,payload};
}
test('one index finds WINGS samples, public isolates, accession aliases, and unannotated tips without changing source data',()=>{
  const {app,payload}=fixture(),before=JSON.stringify(payload);
  const local=app.findTaxa('wings-one__na');assert.equal(local.length,1);assert.equal(local[0].kind,'sample');assert.deepEqual(Array.from(local[0].segments),['HA','NA']);
  assert.equal(app.findTaxa('canada goose').length,2);
  assert.equal(app.findTaxa('pv306210').length,1);assert.equal(app.findTaxa('pv306210')[0].id,'REF1');
  const tips=app.findTaxa('unlinked[tip]');assert.equal(tips.length,2);assert.equal(tips[0].kind,'tip');assert.notEqual(tips[0].key,tips[1].key);
  assert.equal(JSON.stringify(payload),before);
});
test('typing filters the table without changing selection; unique Enter selects and synchronizes a WINGS sample',()=>{
  const {app}=fixture();app.selectedSampleId='WINGS-TWO';app.syncTaxonSearchSelection();
  app.taxonSearchInput.value='wings-one';app.taxonSearchInput.fire('input');
  assert.equal(app.selectedSampleId,'WINGS-TWO');assert.equal(app.taxonSearchResults.hidden,false);
  assert.match(app.taxonSearchResults.innerHTML,/WINGS-ONE/);assert.doesNotMatch(app.taxonSearchResults.innerHTML,/WINGS-TWO/);
  app.taxonSearchInput.fire('keydown',{key:'Enter'});
  assert.equal(app.selectedSampleId,'WINGS-ONE');assert.equal(app.selectedReferenceId,null);
  assert.equal(app.taxonSearchResults.hidden,true);assert.match(app.taxonSearchStatus.textContent,/WINGS sample selected: WINGS-ONE/);
});
test('ambiguous Enter does not silently select the first match; arrow and escape keys preserve the current selection',()=>{
  const {app}=fixture();app.selectedSampleId='WINGS-ONE';
  app.taxonSearchInput.value='Canada Goose';app.taxonSearchInput.fire('input');
  app.taxonSearchInput.fire('keydown',{key:'Enter'});assert.equal(app.selectedReferenceId,null);assert.equal(app.selectedSampleId,'WINGS-ONE');
  assert.equal(app.taxonSearchResults.firstButton.focused,true);
  app.taxonSearchResults.firstButton.focused=false;
  app.taxonSearchInput.fire('keydown',{key:'ArrowDown'});assert.equal(app.taxonSearchResults.firstButton.focused,true);
  app.taxonSearchInput.fire('keydown',{key:'Escape'});assert.equal(app.taxonSearchResults.hidden,true);assert.equal(app.selectedSampleId,'WINGS-ONE');
});
test('clicking a public taxon preserves the WINGS comparison sample and switches a single-tree view to an available segment',()=>{
  const {app}=fixture();app.selectedSampleId='WINGS-ONE';app.treeMode='single';app.segment='PB2';
  const button=new Element();button.owner=app.taxonSearchResults;button.dataset.taxonKey='r:REF1';button.closest=()=>button;
  app.taxonSearchResults.fire('click',{target:button});
  assert.equal(app.selectedReferenceId,'REF1');assert.equal(app.selectedSampleId,'WINGS-ONE');assert.equal(app.segment,'HA');
  assert.ok(app.treeRenders>0);assert.match(app.taxonSearchStatus.textContent,/Public reference selected/);
});
test('unannotated same-name tips in different segments remain separate and select only their own segment',()=>{
  const {app}=fixture();app.selectedSampleId='WINGS-ONE';app.selectedReferenceId='REF1';
  app.selectTaxonSearchResult('t:NA|UNLINKED[tip]');
  assert.equal(app.selectedSampleId,null);assert.equal(app.selectedReferenceId,null);
  assert.equal(app.selectedTreeTip.segment,'NA');assert.equal(app.selectedTreeTip.name,'UNLINKED[tip]');
  assert.match(app.taxonSearchStatus.textContent,/Other tree tip selected/);
});
test('searching for a WINGS sample outside the host filter reveals it; clear resets search and all selection types',()=>{
  const {app,controls}=fixture();app.hostFilter='MALL';app.selectTaxonSearchResult('s:WINGS-ONE');assert.equal(app.hostFilter,'ALL');
  app.selectTaxonSearchResult('t:NA|UNLINKED[tip]');
  controls.nodes['.wse-clear-selection'].fire('click');
  assert.equal(app.selectedSampleId,null);assert.equal(app.selectedReferenceId,null);assert.equal(app.selectedTreeTip,null);assert.equal(app.taxonSearchInput.value,'');assert.equal(app.treeMode,'all');
});
test('search results escape imported names and report empty and limited result sets clearly',()=>{
  const {app}=fixture();app.samples.push({sample_id:'<img src=x onerror=alert(1)>',host:'UNKNOWN'});app.taxonSearchIndex=null;
  app.taxonSearchInput.value='<img';app.taxonSearchInput.fire('input');
  assert.match(app.taxonSearchResults.innerHTML,/&lt;img/);assert.doesNotMatch(app.taxonSearchResults.innerHTML,/<img/);
  app.taxonSearchInput.value='no-such-taxon';app.taxonSearchInput.fire('input');assert.match(app.taxonSearchStatus.textContent,/No matching taxa/);assert.equal(app.taxonSearchResults.hidden,true);
  for(let i=0;i<60;i++)app.samples.push({sample_id:'MANY-'+i,host:'HOST'});
  app.taxonSearchIndex=null;app.taxonSearchInput.value='MANY-';app.taxonSearchInput.fire('input');
  assert.match(app.taxonSearchStatus.textContent,/Showing 50 of 60 matches/);
  assert.equal((app.taxonSearchResults.innerHTML.match(/data-taxon-key=/g)||[]).length,50);
});
test('unknown result keys do not change selection',()=>{
  const {app}=fixture();app.selectedSampleId='WINGS-ONE';const count=app.updates;
  app.selectTaxonSearchResult('r:NO_SUCH_REFERENCE');assert.equal(app.selectedSampleId,'WINGS-ONE');assert.equal(app.updates,count);
});
test('raw-tip highlighting and scrolling use segment plus label, rather than merging equal tip names',()=>{
  const {app}=fixture();app.selectedTreeTip={segment:'NA',name:'UNLINKED[tip]'};
  const groups=['HA','NA'].map(segment=>({dataset:{taxonSegment:segment,taxonTip:'UNLINKED[tip]'},selected:false,classList:{toggle(name,value){this.owner.selected=value;}},getBoundingClientRect(){return {top:400,bottom:420,left:20,right:60};}}));
  for(const g of groups)g.classList.owner=g;
  const container={hidden:false,clientHeight:200,clientWidth:300,scrollTop:0,scrollLeft:0,getBoundingClientRect(){return {top:0,bottom:200,left:0,right:300};},querySelectorAll(){return groups;}};
  app.root={querySelectorAll(selector){if(selector==='.wse-tree')return [container];if(selector==='.wse-tree-tip[data-taxon-tip]')return groups;return [];}};
  Explorer.prototype.updateEmphasis.call(app);assert.equal(groups[0].selected,false);assert.equal(groups[1].selected,true);
  Explorer.prototype.revealSelectedTips.call(app);assert.equal(container.scrollTop,300);
});

let moduleSource=source.split('/* WINGS_BRAID_CLOCK_JS_BEGIN */')[1].split('/* WINGS_BRAID_CLOCK_JS_END */')[0];
moduleSource=moduleSource.replace('clockRecord,lagText,seasonalTimingSummary,mount','clockRecord,lagText,seasonalTimingSummary,genotypeEvidenceMarkup,collectionContextMarkup,neighborExplanation,mount');
const moduleSandbox={module:{exports:{}}};vm.runInNewContext(moduleSource,moduleSandbox);const api=moduleSandbox.module.exports;
const evidenceContext=vm.createContext({...api,esc,pct:value=>value===null?'Not estimable':`${Math.round(value*100)}%`,genotype:raw=>raw.genotype?.call||'Not recorded'});
const renderEvidence=vm.compileFunction(source.match(/^    renderEvidence\(\) \{([\s\S]*?)^    \}\n(?=    renderClock\()/m)[1],[],{parsingContext:evidenceContext});
test('genotype and assignment details appear beside the braid; the neighbor percentage is inside a closed technical disclosure',()=>{
  const samples=[{sample_id:'FOCUS',host:'HOST',country:'USA',state:'STATE',collection_date:'2025-10-21',genotype:{call:'D1.1',reason:'Synthetic assignment details'}},...['A','B','C','D','E'].map(sample_id=>({sample_id,host:'HOST'}))];
  const tree=order=>({root:{children:order.map((sample_id,i)=>({sample_id,name:sample_id,length:.01*(i+1)}))}});
  const m=api.model({samples,trees:{HA:tree(['FOCUS','A','B','C','D','E']),NA:tree(['FOCUS','A','D','E','B','C'])}});
  const node={innerHTML:''};const app={selected:'s:FOCUS',selectedReference:null,m,phenology:null,root:{querySelector:()=>node},profile:key=>api.neighborhoodProfile(m,key)};
  renderEvidence.call(app);const html=node.innerHTML;
  const [primary,technical]=html.split('<details class="wbc-technical-comparisons">');
  assert.match(primary,/Recorded genotype/);assert.match(primary,/D1\.1/);assert.match(primary,/Genotype assignment details/);assert.match(primary,/Synthetic assignment details/);
  assert.doesNotMatch(primary,/20%|wbc-score|Average neighbor overlap/);
  assert.match(technical,/<summary>Technical tree comparisons<\/summary>/);assert.match(technical,/20%/);assert.match(technical,/1 usable tree-pair comparison\./);
  assert.doesNotMatch(html,/<details[^>]*\sopen(?:\s|>|=)/);
  assert.doesNotMatch(source,/<div class="wse-genome-evidence"><\/div>/);
});
test('public references do not inherit a WINGS sample genotype',()=>{
  assert.equal(api.genotypeEvidenceMarkup({kind:'reference',raw:{genotype:{call:'D1.1'}}}),'');
});
test('the individual-tree controls contain a search input and matching table rather than taxon dropdowns',()=>{
  const {controls}=fixture();assert.match(controls.innerHTML,/type="search"/);assert.doesNotMatch(controls.innerHTML,/class="wse-reference-select"|class="wse-sample-select"/);
  assert.match(controls.innerHTML,/class="wse-view-select"/);
});
