/* Paths are selected on the runner computer, never uploaded as directory contents. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const origin=['localhost','127.0.0.1'].includes(location.hostname)?location.origin:'http://127.0.0.1:8765';
  const dialog=$('contextFolderDialog');
  let active=null,listing=null,generation=0,busy=false;
  async function request(action,payload={}) {
    const response=await fetch(origin+'/api/context/files/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await response.json();
    if(!response.ok)throw new Error('The folder could not be opened. Check access on the runner computer.');
    return data;
  }
  function notice(text) {$('contextPickerNotice').textContent=text;$('contextPickerNotice').hidden=!text;}
  function changed(field) {
    if(field==='contextSource' && $(field).value){$('contextPackage').value='';$('contextCoverage').checked=false;}
    if(field==='contextPackage' && $(field).value){$('contextSource').value='';$('contextCoverage').checked=false;}
    $('contextCoverageRow').hidden=true;
    $(field).dispatchEvent(new Event('input',{bubbles:true}));
  }
  function finish() {generation++;active=null;listing=null;busy=false;if(dialog.open)dialog.close();}
  function apply(path) {
    if(!active)return;
    const target=active.target;
    $(target).value=path;changed(target);
    finish();notice('Selection saved. Check the folder, then prepare context.');$(target).focus();
    if(target==='contextSource')window.WINGS_CONTEXT_SETUP?.checkEbirdFolder?.();
  }
  function error() {$('contextFolderMessage').textContent='Could not open this location. Choose another folder.';}
  function navigationDisabled(value) {
    for(const id of ['contextFolderRoot','contextFolderUp','contextFolderPrevious','contextFolderNext','contextFolderUse'])$(id).disabled=value;
  }
  async function browse(relative='',offset=0) {
    if(!active)return;
    const token=++generation;
    navigationDisabled(true);listing=null;
    $('contextFolderEntries').replaceChildren();$('contextFolderMessage').textContent='Loading folders…';
    try {
      const data=await request('browse',{kind:active.kind,root_id:$('contextFolderRoot').value,relative,offset});
      if(!active||token!==generation)return;
      listing=data;$('contextFolderPath').textContent=data.path;
      $('contextFolderMessage').textContent=data.entries.length?'':(active.kind==='aphis_csv'?'No folders or CSV files here.':'No subfolders. You can select this folder.');
      for(const row of data.entries) {
        const button=document.createElement('button');button.type='button';button.className='context-folder-entry';
        button.textContent=(row.directory?'Open folder: ':'Choose CSV: ')+row.name;
        button.addEventListener('click',()=>row.directory?browse(row.relative):select(row.relative));
        $('contextFolderEntries').append(button);
      }
      navigationDisabled(false);
      $('contextFolderUp').disabled=data.parent===null;
      $('contextFolderPrevious').disabled=data.offset===0;
      $('contextFolderNext').disabled=data.next_offset===null;
      $('contextFolderUse').hidden=active.kind==='aphis_csv';
    } catch(e) {if(active&&token===generation){error();$('contextFolderRoot').disabled=false;}}
  }
  async function select(relative) {
    if(!active||!listing)return;
    const token=++generation;navigationDisabled(true);
    try {
      const result=await request('select',{kind:active.kind,root_id:listing.root_id,relative});
      if(active&&token===generation&&result.status==='SELECTED')apply(result.path);
    } catch(e) {if(active&&token===generation){error();navigationDisabled(false);}}
  }
  async function openBrowser(roots) {
    const root=$('contextFolderRoot');root.replaceChildren();
    for(const entry of roots){const option=document.createElement('option');option.value=entry.id;option.textContent=entry.label;root.append(option);}
    root.value=roots[0]?.id||'';
    $('contextFolderTitle').textContent=active.kind==='aphis_csv'?'Choose an APHIS CSV':'Choose a folder';
    $('contextFolderUse').hidden=active.kind==='aphis_csv';
    if(!dialog.open)dialog.showModal();
    if(!roots.length){navigationDisabled(true);$('contextFolderMessage').textContent='No accessible locations. Set WINGS_BROWSE_ROOTS or enter a path in the form.';return;}
    await browse();root.focus();
  }
  async function choose(kind,target,button) {
    if(busy)return;
    busy=true;active={kind,target};button.disabled=true;notice('Opening chooser on the runner computer…');
    try {
      const result=await request('native',{kind});
      if(result.status==='CANCELLED'){finish();notice('');}
      else if(result.status==='SELECTED')apply(result.path);
      else if(result.status==='BROWSE'){notice('');await openBrowser(result.roots);}
      else throw new Error('Invalid picker response');
    } catch(e) {finish();notice('Chooser unavailable. Restart the updated runner, or enter the path manually.');}
    finally {button.disabled=false;}
  }
  for(const button of document.querySelectorAll('[data-context-pick]'))button.addEventListener('click',()=>choose(button.dataset.contextPick,button.dataset.contextTarget,button));
  for(const button of document.querySelectorAll('[data-context-clear]'))button.addEventListener('click',()=>{const target=button.dataset.contextClear;$(target).value='';if(target==='contextSource')$('contextCoverage').checked=false;changed(target);});
  // Manual path entry stays available for advanced and unusual mount setups.
  for(const id of ['contextSource','contextPackage'])$(id).addEventListener('input',()=>{
    $('contextCoverageRow').hidden=true;
    if(!$(id).value)return;
    $(id==='contextSource'?'contextPackage':'contextSource').value='';$('contextCoverage').checked=false;
    $('contextCoverageRow').hidden=true;
  });
  $('contextFolderRoot').addEventListener('change',()=>browse());
  $('contextFolderUp').addEventListener('click',()=>listing&&listing.parent!==null&&browse(listing.parent));
  $('contextFolderPrevious').addEventListener('click',()=>listing&&browse(listing.relative,Math.max(0,listing.offset-100)));
  $('contextFolderNext').addEventListener('click',()=>listing&&listing.next_offset!==null&&browse(listing.relative,listing.next_offset));
  $('contextFolderUse').addEventListener('click',()=>listing&&select(listing.relative));
  $('contextFolderCancel').addEventListener('click',()=>{finish();notice('');});
  dialog.addEventListener('cancel',()=>{finish();notice('');});
  $('contextCoverageRow').hidden=true;
  window.WINGS_CONTEXT_PICKER={isBusy:()=>busy};
})();
