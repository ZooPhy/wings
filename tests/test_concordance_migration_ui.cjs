const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this.listeners={};this.className='';this._text='';this.classList={add(){}};}
  setAttribute(key,value){this.attrs[key]=String(value);}
  append(...nodes){this.children.push(...nodes);}
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
const points=panel=>walk(panel).filter(n=>n.attrs['data-migration-context']);
function app(){
  const panel=new Element();
  const data={models:[{segment:'HA',comparison:'migration_vs_ecology',status:'DESCRIPTIVE',display_status:'DESCRIPTIVE',delta_r2:.03,n_samples:2,n_pairs:1,n_migration_contexts:1,diagnostic:'Shared contexts; descriptive only.',eligible_sample_ids:['a','b']},{segment:'NP',comparison:'migration_vs_ecology',status:'INSUFFICIENT_MIGRATION_CONTEXTS',display_status:'INSUFFICIENT_MIGRATION_CONTEXTS',n_samples:0,n_pairs:0,n_migration_contexts:0,diagnostic:'No eligible contexts.',eligible_sample_ids:[]}],readiness:{total_samples:3,samples_with_migration_context:2,distinct_migration_contexts:1},migration_context:{method:'fixture',coverage:'fixture',inference:'fixture',window:'fixed matched night'},migration_samples:[
    {sample_id:'a',host:'Duck',collection_date:'2025-10-02',migration_night:'2025-10-01',migration_state:'KY',migration_context_key:'US-KY|2025-10-01',migration_season_label:'Fall 2025',migration_available:true,migration_intensity_percentile:.6,migration_progress:.4},
    {sample_id:'b',host:'Goose',collection_date:'2025-10-02',migration_night:'2025-10-01',migration_state:'KY',migration_context_key:'US-KY|2025-10-01',migration_season_label:'Fall 2025',migration_available:true,migration_intensity_percentile:.6,migration_progress:.4},
    {sample_id:'summer',host:'Duck',collection_date:'2025-07-01',migration_available:false,migration_reason:'Matched night is outside seasonal coverage.'}]};
  const a={payload:{genomic_ecological_concordance:data},selectedSampleId:'summer',hostFilter:'ALL',selectSample(id){this.calls=(this.calls||[]).concat(id);this.selectedSampleId=id;this.concordanceController.refresh();}};
  a.concordanceController=sandbox.WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE.mount(a,panel);
  return {a,panel,data};
}
test('map groups shared state-nights and shows missing summer context explicitly',()=>{
  const {panel}=app();assert.equal(points(panel).length,1);
  assert.match(points(panel)[0].textContent,/2 samples/);
  assert.match(panel.textContent,/summer: Matched night is outside seasonal coverage/);
  assert.match(panel.textContent,/Descriptive.*p\/q withheld/);
  assert.doesNotMatch(JSON.stringify(walk(panel).map(n=>n.attrs)),/NaN|Infinity/);
});
test('click and keyboard activation link actual samples and refresh selection',()=>{
  const {a,panel}=app();points(panel)[0].fire('click');
  assert.equal(a.selectedSampleId,'a');assert.equal(points(panel)[0].attrs['aria-pressed'],'true');
  const select=walk(panel).find(n=>n.tag==='select');select.value='b';select.fire('change');
  assert.equal(a.selectedSampleId,'b');points(panel)[0].fire('keydown',{key:'Enter'});
  assert.deepEqual(a.calls,['a','b']);assert.match(panel.textContent,/b · matched night 2025-10-01/);
});
test('segment contribution selection filters eligible collections without changing analysis results',()=>{
  const {a,panel,data}=app(),original=JSON.stringify(data.models);
  const fit=()=>walk(panel).find(n=>n.tag==='svg' && n.attrs['aria-label']==='Migration added fit by segment');
  fit().children.find(n=>n.attrs['aria-label']?.startsWith('NP:')).fire('click');
  assert.equal(a.migrationConcordanceSegment,'NP');assert.equal(points(panel).length,0);
  assert.match(panel.textContent,/NP: 0 eligible samples/);
  fit().children.find(n=>n.attrs['aria-label']?.startsWith('NP:')).fire('keydown',{key:' '});
  assert.equal(points(panel).length,1);assert.equal(JSON.stringify(data.models),original);
});
test('host filtering only changes displayed contexts and legacy reports remain usable',()=>{
  const {a,panel,data}=app();a.hostFilter='Duck';a.selectedSampleId=null;a.concordanceController.refresh();
  assert.equal(points(panel).length,1);assert.match(points(panel)[0].textContent,/1 samples/);
  delete data.migration_context;delete data.migration_samples;a.concordanceController.refresh();
  assert.equal(points(panel).length,0);assert.match(panel.textContent,/Genomic–Ecological Concordance/);
});
module.exports={Element,app,walk,points};
