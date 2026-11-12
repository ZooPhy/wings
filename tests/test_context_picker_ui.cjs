'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const crypto=require('node:crypto').webcrypto;
const path=require('node:path');
class Element {
  constructor(tag='div') {Object.assign(this,{tagName:tag,value:'',checked:false,files:[],children:[],disabled:false,dataset:{},className:'',open:false,listeners:{},attrs:{},_text:''});}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set textContent(value){this._text=String(value);this.children=[];}
  append(...children){for(const child of children){child.parent=this;this.children.push(child);}}
  replaceChildren(...children){this.children=[];this._text='';this.append(...children);}
  addEventListener(type,fn){this.listeners[type]=fn;}
  setAttribute(key,value){this.attrs[key]=value;}
  querySelectorAll(selector){const all=[];const visit=el=>{for(const child of el.children){if(selector==='input,button,select'?['input','button','select'].includes(child.tagName):selector==='details[open]'?child.tagName==='details'&&child.open:selector.startsWith('.')?child.className.split(' ').includes(selector.slice(1)):child.tagName===selector)all.push(child);visit(child);}};visit(this);return all;}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  remove(){this.parent.children=this.parent.children.filter(c=>c!==this);}
  focus(){this.focused=true;}
  scrollIntoView(){this.scrolled=true;}
}
Element.prototype.showModal=function(){this.open=true;};
Element.prototype.close=function(){this.open=false;};
Element.prototype.dispatchEvent=function(event){if(this.listeners[event.type])this.listeners[event.type](event);if(event.bubbles&&this.parent)this.parent.dispatchEvent(event);return true;};
(async()=>{
  const ids=['contextSetup','contextSource','contextPackage','contextCoverage','contextCoverageRow','contextPickerNotice','contextFolderDialog','contextFolderRoot','contextFolderTitle','contextFolderPath','contextFolderMessage','contextFolderEntries','contextFolderUp','contextFolderPrevious','contextFolderNext','contextFolderUse','contextFolderCancel'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));
  elements.contextSetup.append(...Object.entries(elements).filter(([id])=>id!=='contextSetup').map(([,el])=>el));
  let invalidations=0;elements.contextSetup.addEventListener('input',()=>invalidations++);
  const buttons=['ebird_download','ebird_package'].map((kind,i)=>{const el=new Element('button');el.dataset={contextPick:kind,contextTarget:['contextSource','contextPackage'][i]};return el;});
  const clear=new Element('button');clear.dataset.contextClear='contextSource';
  const calls=[];let nativeStatus='BROWSE',nativePath='/home/user/Downloaded birds',failure=false,deferBrowse=null;
  const roots=[{id:'home',label:'Home',path:'/home/user'}];
  const fetch=async(url,opts)=>{
    assert.equal(opts.method,'POST');assert.equal(opts.headers['Content-Type'],'application/json');
    const body=JSON.parse(opts.body),action=url.split('/').at(-1);calls.push({action,body});
    if(failure)return {ok:false,json:async()=>({error:'secret diagnostic'})};
    let data;
    if(action==='native')data={status:nativeStatus,path:nativePath,roots};
    else if(action==='browse'){
      if(deferBrowse)await new Promise(resolve=>{deferBrowse.resolve=resolve;});
      data={status:'BROWSE',root_id:body.root_id,path:'/home/user/'+(body.relative||''),relative:body.relative||'',parent:body.relative?'':null,offset:body.offset||0,next_offset:body.offset?null:100,entries:body.relative?[]:[{name:'Bird folder <img>',relative:'Bird folder <img>',directory:true},...(body.kind==='aphis_csv'?[{name:'snapshot.csv',relative:'snapshot.csv',directory:false}]:[])]};
    }else if(action==='select')data={status:'SELECTED',path:'/home/user/'+body.relative};
    else throw new Error('Unexpected '+action);
    return {ok:true,json:async()=>data};
  };
  const sandbox={window:{},location:{hostname:'localhost',origin:'http://localhost:8765'},document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag),querySelectorAll:selector=>selector==='[data-context-pick]'?buttons:[clear]},fetch,Event:class{constructor(type,opts){this.type=type;this.bubbles=opts.bubbles;}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../assets/wings-context-picker.js'),'utf8'),sandbox);
  const picker=sandbox.window.WINGS_CONTEXT_PICKER;
  elements.contextPackage.value='/old/package';elements.contextCoverage.checked=true;
  await buttons[0].listeners.click();assert.equal(elements.contextFolderDialog.open,true);assert.equal(picker.isBusy(),true);
  assert.equal(elements.contextFolderRoot.value,'home');assert.equal(elements.contextFolderUp.disabled,true);
  const folder=elements.contextFolderEntries.children[0];assert.match(folder.textContent,/<img>/);assert.equal(folder.querySelector('img'),null);
  await folder.listeners.click();assert.equal(elements.contextFolderPath.textContent,'/home/user/Bird folder <img>');assert.equal(elements.contextFolderUp.disabled,false);
  await elements.contextFolderUse.listeners.click();assert.equal(elements.contextSource.value,'/home/user/Bird folder <img>');assert.equal(elements.contextPackage.value,'');assert.equal(elements.contextCoverage.checked,false);assert.equal(invalidations,1);assert.equal(elements.contextCoverageRow.hidden,true);assert.equal(picker.isBusy(),false);assert.equal(elements.contextFolderDialog.open,false);
  const original=elements.contextSource.value;nativeStatus='CANCELLED';await buttons[0].listeners.click();assert.equal(elements.contextSource.value,original);assert.equal(invalidations,1);
  nativeStatus='SELECTED';nativePath='/mounted/disk/Prepared birds';await buttons[1].listeners.click();assert.equal(elements.contextPackage.value,nativePath);assert.equal(elements.contextSource.value,'');assert.equal(invalidations,2);assert.equal(elements.contextCoverageRow.hidden,true);
  nativeStatus='BROWSE';
  await buttons[0].listeners.click();await elements.contextFolderNext.listeners.click();assert.equal(calls.at(-1).body.offset,100);assert.equal(elements.contextFolderPrevious.disabled,false);
  await elements.contextFolderPrevious.listeners.click();assert.equal(calls.at(-1).body.offset,0);
  elements.contextFolderCancel.listeners.click();assert.equal(picker.isBusy(),false);
  failure=true;await buttons[0].listeners.click();assert.match(elements.contextPickerNotice.textContent,/Restart the updated runner/);assert.doesNotMatch(elements.contextSetup.textContent,/secret diagnostic/);assert.equal(buttons[0].disabled,false);failure=false;
  // Closing during a request must not reopen the dialog or change a selection.
  deferBrowse={};const pending=buttons[0].listeners.click();
  for(let n=0;n<8&&!deferBrowse.resolve;n++)await Promise.resolve();
  assert.ok(deferBrowse.resolve);elements.contextFolderCancel.listeners.click();deferBrowse.resolve();await pending;deferBrowse=null;
  assert.equal(elements.contextFolderDialog.open,false);assert.equal(picker.isBusy(),false);
  elements.contextSource.value='/manual/download';elements.contextCoverage.checked=true;elements.contextSource.dispatchEvent(new sandbox.Event('input',{bubbles:true}));assert.equal(elements.contextPackage.value,'');assert.equal(elements.contextCoverage.checked,false);
  clear.listeners.click();assert.equal(elements.contextSource.value,'');
  assert.equal(calls.some(c=>c.action==='start'||c.action==='prepare'),false);
  const html=fs.readFileSync(path.join(__dirname,'../run.html'),'utf8');
  for(const id of ids)assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  assert.equal((html.match(/data-context-pick=/g)||[]).length,1);
  assert.ok(html.includes('eBird observations folder'));
  assert.ok(html.includes('id="contextCheckFolder"'));
  assert.ok(!html.includes('Use previously prepared eBird data</summary>'));
  assert.ok(html.indexOf('assets/wings-context-picker.js')<html.indexOf('assets/wings-context-setup.js'));
  console.log('PASS: native selection/cancellation; runner-folder navigation and pagination; safe names; import exclusivity; coverage reset; stale-response protection; cache wording and script order.');
})().catch(e=>{console.error(e);process.exitCode=1;});
