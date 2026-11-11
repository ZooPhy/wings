const {test,describe}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=name=>fs.readFileSync(path.join(__dirname,'../scripts/report',name),'utf8');
const bundle=read('surveillance-explorer.js');
const explorerD3=bundle.split('/* WINGS_D3_HIERARCHY_BEGIN */')[1].split('/* WINGS_D3_HIERARCHY_END */')[0];

for(const [name,source] of [['sample navigation',read('sample-navigation.js')],['Explorer bundled D3',explorerD3]])describe(name,()=>{
  for(const loader of ['plain browser','RequireJS','CommonJS-like globals'])test('D3 initializes with '+loader,()=>{
    const calls=[];
    const define=(...args)=>calls.push(args);define.amd={quarto:true};
    const originalExports={preserved:true},originalModule={exports:{preserved:true}};
    const globals={document:{readyState:'loading',addEventListener(){}},d3:{existingPlugin:'retained'}};
    if(loader==='RequireJS')globals.define=define;
    if(loader==='CommonJS-like globals'){globals.exports=originalExports;globals.module=originalModule;}
    const context=vm.createContext(globals);
    vm.runInContext(source,context);
    assert.equal(typeof context.d3.hierarchy,'function');
    assert.equal(context.d3.hierarchy({children:[{id:'a'}]}).descendants().length,2);
    assert.equal(context.d3.existingPlugin,'retained');
    if(loader==='RequireJS'){assert.equal(context.define,define);assert.equal(context.define.amd.quarto,true);assert.equal(calls.length,0);}
    if(loader==='CommonJS-like globals'){assert.equal(context.exports,originalExports);assert.equal(context.module,originalModule);assert.deepEqual(originalModule.exports,{preserved:true});assert.deepEqual(originalExports,{preserved:true});}
  });
});


for (const [name, source] of [['canonical Pipeline navigator', read('pipeline-view-navigator.js')], ['generated Explorer bundle', bundle]]) {
  for (const readyState of ['complete', 'loading']) test(name + ' initializes safely without a Pipeline document (' + readyState + ')', () => {
    const listeners = [];
    const document = {readyState, querySelectorAll: () => [], addEventListener: (event, callback) => listeners.push(callback)};
    const context = vm.createContext({document});
    assert.doesNotThrow(() => vm.runInContext(source, context));
    for (const callback of listeners) assert.doesNotThrow(() => callback());
    assert.equal(typeof context.WINGS_PIPELINE_NAVIGATION.mount, 'function');
    assert.doesNotThrow(() => context.WINGS_PIPELINE_NAVIGATION.initialize());
  });
}
