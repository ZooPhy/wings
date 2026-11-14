const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this.listeners={};this.style={};this.value='';this.className='';this._text='';this.classList={add(){}};}
  setAttribute(key,value){this.attrs[key]=String(value);}
  append(...nodes){this.children.push(...nodes);if(this.tag==='select'&&!this.value&&this.children.length)this.value=this.children[0].value;}
  replaceChildren(...nodes){this.children=nodes;this._text="";}
  appendChild(node){this.children.push(node);return node;}
  set innerHTML(value){this.children=[];this._text='';}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
  addEventListener(name,fn){this.listeners[name]=fn;}
  fire(name,extra={}){assert.ok(this.listeners[name]);this.listeners[name]({target:this,preventDefault(){},...extra});}
}
const code=fs.readFileSync(path.join(__dirname,'../scripts/report/surveillance-explorer.js'),'utf8');
const start=code.indexOf('/* WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE_UI_BEGIN */'),end=code.indexOf('/* WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE_UI_END */');
const sandbox=vm.createContext({document:{createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)}});
vm.runInContext(code.slice(start,end),sandbox);
const walk=node=>[node,...node.children.flatMap(walk)];
const contextRows=panel=>walk(panel).filter(n=>n.tag==='button'&&n.className==='wm-context-row');
function app(){
  const panel=new Element(),migration=new Element();
  const data={models:[{segment:'HA',comparison:'migration_vs_ecology',status:'DESCRIPTIVE',display_status:'DESCRIPTIVE',delta_r2:.03,n_samples:2,n_pairs:1,n_migration_contexts:1,diagnostic:'Shared contexts; descriptive only.',eligible_sample_ids:['a','b']},{segment:'NP',comparison:'migration_vs_ecology',status:'INSUFFICIENT_MIGRATION_CONTEXTS',display_status:'INSUFFICIENT_MIGRATION_CONTEXTS',n_samples:0,n_pairs:0,n_migration_contexts:0,diagnostic:'No eligible contexts.',eligible_sample_ids:[]}],readiness:{total_samples:3,samples_with_migration_context:2,distinct_migration_contexts:1},migration_context:{method:'fixture',coverage:'fixture',inference:'fixture',window:'fixed matched night'},migration_samples:[
    {sample_id:'a',host:'Duck',collection_date:'2025-10-02',migration_night:'2025-10-01',migration_state:'KY',migration_context_key:'US-KY|2025-10-01',migration_season_label:'Fall 2025',migration_available:true,migration_intensity_percentile:.6,migration_progress:.4},
    {sample_id:'b',host:'Goose',collection_date:'2025-10-02',migration_night:'2025-10-01',migration_state:'KY',migration_context_key:'US-KY|2025-10-01',migration_season_label:'Fall 2025',migration_available:true,migration_intensity_percentile:.6,migration_progress:.4},
    {sample_id:'summer',host:'Duck',collection_date:'2025-07-01',migration_available:false,migration_reason:'Matched night is outside seasonal coverage.'}]};
  const a={payload:{genomic_ecological_concordance:data},selectedSampleId:'summer',hostFilter:'ALL',selectSample(id){this.calls=(this.calls||[]).concat(id);this.selectedSampleId=id;this.concordanceController.refresh();this.migrationContextController.refresh();}};
  a.concordanceController=sandbox.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE.mount(a,panel);
  a.migrationContextController=sandbox.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE.mountMigrationContext(a,migration);
  return {a,panel,data,migration};
}
test('context rows group shared state-nights and show unavailable collections explicitly',()=>{
  const {panel,migration}=app();assert.equal(contextRows(migration).length,1);
  assert.match(contextRows(migration)[0].textContent,/2 samples/);
  assert.match(migration.textContent,/summer · 2025-07-01: Matched night is outside seasonal coverage/);
  assert.match(panel.textContent,/Descriptive added fit.*p\/q values are withheld/);
  assert.doesNotMatch(JSON.stringify(walk(migration).map(n=>n.attrs)),/NaN|Infinity/);
});
test('native context buttons link actual samples and preserve a selected group member',()=>{
  const {a,migration:panel}=app();contextRows(panel)[0].fire('click');
  assert.equal(a.selectedSampleId,'a');assert.equal(contextRows(panel)[0].attrs['aria-pressed'],'true');
  a.selectSample('b');
  assert.equal(a.selectedSampleId,'b');contextRows(panel)[0].fire('click');
  assert.deepEqual(a.calls,['a','b']);assert.equal(contextRows(panel)[0].type,'button');assert.match(panel.textContent,/b · 2 samples share this context/);
});
test('nightly context lives separately from model comparisons and preserves evidence',()=>{
  const {a,panel,migration,data}=app(),original=JSON.stringify(data);
  assert.equal(contextRows(panel).length,0);
  assert.doesNotMatch(panel.textContent,/Nightly migration context by state|Compare nightly contexts/);
  assert.equal(contextRows(migration).length,1);
  assert.match(migration.textContent,/Nightly migration context by state/);
  assert.doesNotMatch(migration.textContent,/Compare activity and seasonal progress|distinct nightly migration contexts by state shown/);
  assert.ok(!walk(migration).some(n=>n.attrs['data-migration-context']||n.className==='wgec-migration-readout'));
  assert.doesNotMatch(migration.textContent,/Added fit by segment|Migration comparisons unavailable/);
  a.concordanceController.refresh();
  assert.equal(contextRows(migration).length,1);assert.equal(JSON.stringify(data),original);
});
test('host filtering only changes displayed contexts and legacy reports remain usable',()=>{
  const {a,panel,migration,data}=app();a.hostFilter='Duck';a.selectedSampleId=null;a.migrationContextController.refresh();
  assert.equal(contextRows(migration).length,1);assert.match(contextRows(migration)[0].textContent,/1 samples/);
  delete data.migration_context;delete data.migration_samples;a.migrationContextController.refresh();a.concordanceController.refresh();
  assert.equal(contextRows(migration).length,0);assert.equal(migration.hidden,true);assert.match(panel.textContent,/Genomic–Ecological Concordance/);
});
module.exports={Element,app,walk,contextRows};

test('migration summary separates available data from configured fit requirements',()=>{
  const {a,panel,data}=app();
  data.models.forEach(row=>{row.status=row.display_status='INSUFFICIENT_MIGRATION_CONTEXTS';});
  Object.assign(data.readiness,{samples_with_migration_context:28,distinct_migration_contexts:5,minimum_unique_samples:8});
  const summary=()=>walk(panel).find(n=>n.className==='wgec-summary-row' && n.children[0]?.textContent==='Migration context').textContent;
  a.concordanceController.refresh();
  assert.match(summary(),/Migration data available for 28 samples across 5 distinct settings/);
  assert.match(summary(),/configured minimum is 8/);
  assert.doesNotMatch(summary(),/Not estimable|No samples have both/);
  data.readiness.minimum_unique_samples=3;
  a.concordanceController.refresh();
  assert.match(summary(),/no segment comparison meets all analysis requirements/);
  assert.doesNotMatch(summary(),/configured minimum is/);
});

test('migration summary explains missing normalized context without calling it an estimated effect',()=>{
  const {a,panel,data}=app();
  data.models.forEach(row=>{row.status=row.display_status='INSUFFICIENT_MIGRATION_CONTEXTS';});
  Object.assign(data.readiness,{samples_with_migration_context:0,distinct_migration_contexts:0,minimum_unique_samples:8});
  a.concordanceController.refresh();
  const summary=walk(panel).find(n=>n.className==='wgec-plain-summary').textContent;
  assert.match(summary,/No samples have both a matched BirdCast night and a complete spring\/fall season/);
  assert.doesNotMatch(summary,/Migration data available for|configured minimum is/);
});
