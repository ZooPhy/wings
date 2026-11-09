const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../scripts/report/explorer-tabs.js'),'utf8');
function env(available=true,legacyMode=false){
 const handlers={};let cloneCount=0,removed=0;
 const frame={style:{},contentWindow:{postMessage(){}},setAttribute(){},addEventListener(){}};
 const original={parentElement:{},cloneNode(){cloneCount++;return frame;},remove(){removed++;}};
 const legacy={querySelector(){return available?original:null;},remove(){removed++;}};
 const template={content:{querySelector(){return available?original:null;}}};
 const context=vm.createContext({document:{getElementById(id){return id==='wings-amino-acid-dashboard-0'&&!legacyMode?template:id==='amino-acid-cohort-demo'&&legacyMode?legacy:null;},querySelector(){return null;},createElement(){return {}; }},addEventListener(type,fn){handlers[type]=fn;}});
 vm.runInContext(source,context);const panel={children:[],append(node){this.children.push(node);}};
 const api=context.WINGS_EXPLORER_TABS;const mount=()=>api._test.mountAminoDashboard({root:{dataset:{}}},panel);
 return {api,panel,frame,handlers,mount,get clones(){return cloneCount;},get removed(){return removed;}};
}
test('Amino acids follows Genome and precedes genotype frequencies',()=>{const e=env();assert.deepEqual(Array.from(e.api.TAB_ORDER).slice(0,4),['overview','genome','amino','genotypes']);});
test('report loads on first activation and is retained across switches',()=>{const e=env();const mounted=e.mount();assert.equal(e.clones,0);mounted.refresh();mounted.refresh();assert.equal(e.clones,1);assert.equal(e.panel.children.length,1);});
test('height messages require the embedded window and valid bounds',()=>{const e=env();e.mount().refresh();const send=(source,height)=>e.handlers.message({source,data:{type:'wings-amino-height',height}});send({},900);assert.equal(e.frame.style.height,'1000px');send(e.frame.contentWindow,1400);assert.equal(e.frame.style.height,'1416px');for(const h of [NaN,Infinity,0,30001,'900'])send(e.frame.contentWindow,h);assert.equal(e.frame.style.height,'1416px');});
test('missing amino results show an explicit empty state',()=>{const e=env(false);assert.equal(e.mount(),null);assert.match(e.panel.children[0].textContent,/not embedded/);});
test('legacy appended report is moved without leaving a duplicate',()=>{const e=env(true,true);const m=e.mount();assert.equal(e.removed,2);m.refresh();assert.equal(e.clones,1);});
test('height bridge ignores viewport-only changes and remeasures content',()=>{
 const cp=require('node:child_process');
 const py="import ast,sys; t=ast.parse(open(sys.argv[1]).read()); print(next(ast.literal_eval(n.value) for n in ast.walk(t) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='bridge' for x in n.targets)))";
 const bridge=cp.execFileSync('python3',['-c',py,path.join(__dirname,'../scripts/wings_amino_acids.py')],{encoding:'utf8'});
 const js=bridge.match(/<script>([\s\S]*?)<\/script>/)[1];
 const handlers={},sent=[];let height=900,resize;
 const content={getBoundingClientRect(){return {height};}};
 const parent={postMessage(m){sent.push(m);}};
 const ctx=vm.createContext({document:{querySelector(){return content;},documentElement:{scrollHeight:4000}},parent,addEventListener(k,f){handlers[k]=f;},requestAnimationFrame(f){f();},ResizeObserver:class{constructor(f){resize=f;}observe(){}}});
 vm.runInContext(js,ctx);handlers.load();assert.equal(sent.length,1);assert.equal(sent[0].height,900);
 handlers.resize();resize();assert.equal(sent.length,1);
 height=1400;resize();assert.equal(sent.length,2);assert.equal(sent[1].height,1400);
});
