/* Select a directory on the WINGS runner, including mounted project storage. */
(() => {
  "use strict";
  const origin = ["localhost", "127.0.0.1"].includes(location.hostname) ? location.origin : "http://127.0.0.1:8765";
  const triggers = [...document.querySelectorAll("[data-storage-browse]")];
  if (!triggers.length) return;
  const make = (tag, text, cls) => {const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;};
  const button = (text, action) => {const node=make("button",text,"btn btn-secondary");node.type="button";node.addEventListener("click",action);return node;};
  const dialog=make("dialog",undefined,"wings-folder-picker");dialog.id="storageFolderPicker";dialog.setAttribute("aria-labelledby","folderPickerTitle");
  const title=make("h2");title.id="folderPickerTitle";
  const status=make("p",undefined,"help");status.id="folderPickerStatus";status.setAttribute("role","status");status.setAttribute("aria-live","polite");
  const current=make("p",undefined,"folder-current");current.id="folderPickerPath";
  const shortcuts=make("nav",undefined,"folder-actions");shortcuts.setAttribute("aria-label","Folder shortcuts");
  const toolbar=make("div",undefined,"folder-actions");
  const up=button("Up one folder",()=>load(parent)),search=make("input");search.type="search";search.placeholder="Filter folder names";search.setAttribute("aria-label","Filter folder names");
  const searchButton=button("Search",()=>load(path,0,true));
  search.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();load(path,0,true);}});
  const hiddenLabel=make("label"),hidden=make("input");hidden.type="checkbox";hidden.addEventListener("change",()=>load(path,0,true));hiddenLabel.append(hidden,document.createTextNode(" Show hidden folders"));
  toolbar.append(up,search,searchButton,hiddenLabel);
  const list=make("ul",undefined,"folder-list");list.id="folderPickerList";list.setAttribute("aria-label","Folders");
  const pager=make("div",undefined,"folder-actions"),count=make("span");
  const previous=button("Previous folders",()=>load(path,Math.max(0,offset-limit),true)),next=button("Next folders",()=>load(path,offset+limit,true));pager.append(previous,count,next);
  const footer=make("footer",undefined,"folder-actions"),cancel=button("Cancel",()=>dialog.close()),choose=button("Use this folder",select);choose.className="btn btn-primary";choose.id="folderPickerChoose";footer.append(cancel,choose);
  dialog.append(title,make("p","Browse folders on the computer running WINGS. Choose a folder, then validate and apply the storage locations.","help"),shortcuts,current,toolbar,status,list,pager,footer);document.body.append(dialog);
  let target,path="",parent="",offset=0,limit=200,request=0,selectedPath=null;
  dialog.addEventListener("close",()=>{request++;selectedPath=null;target?.focus();});
  async function load(value="",start=0,keepSearch=false) {
    const revision=++request;selectedPath=null;choose.disabled=true;up.disabled=true;previous.disabled=true;next.disabled=true;
    status.textContent="Loading folders…";list.replaceChildren();count.textContent="";
    if(!keepSearch)search.value="";
    try {
      const response=await fetch(`${origin}/api/storage/directories`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:value,query:search.value,show_hidden:hidden.checked,offset:start})});
      if(response.status===404)throw new Error("Restart WINGS with the updated runner to enable folder browsing.");
      if(response.status===403)throw new Error("Open the local WINGS portal on the runner computer to browse folders.");
      const result=await response.json();if(!response.ok)throw new Error(result.error || "This folder could not be opened.");
      if(revision!==request || !dialog.open)return;
      path=result.path;parent=result.parent;offset=result.offset;limit=result.limit;selectedPath=path;current.textContent=path;
      shortcuts.replaceChildren();
      for(const item of result.shortcuts)shortcuts.append(button(item.name,()=>load(item.path)));
      for(const item of result.directories){const row=make("li");row.append(button(item.name+" /",()=>load(item.path)));list.append(row);}
      status.textContent=result.notice || (result.total?"Open a folder below, or use the current folder.":search.value?"No folders match this search.":"No subfolders. You can use this folder.");
      count.textContent=result.total?`${offset+1}–${Math.min(offset+limit,result.total)} of ${result.total} folders`:"0 folders";
      choose.disabled=false;up.disabled=path===parent;previous.disabled=offset===0;next.disabled=offset+limit>=result.total;
    } catch(error) {
      if(revision!==request || !dialog.open)return;
      status.textContent=error instanceof TypeError?"Connect to the updated local WINGS runner to browse folders. You can still enter a path manually.":error.message;
      up.disabled=!parent; // Keep navigation available after an inaccessible folder.
    }
  }
  function select() {
    if(!selectedPath || !target || target.disabled)return;
    target.value=selectedPath;target.dispatchEvent(new Event("input",{bubbles:true}));dialog.close();
    document.getElementById("storageMessage").textContent="Folder selected. Validate and apply locations to use it.";
  }
  for(const trigger of triggers)trigger.addEventListener("click",()=>{
    target=document.getElementById(trigger.dataset.storageBrowse);if(!target || target.disabled)return;
    title.textContent=target.id==="runsDirectory"?"Choose run storage folder":"Choose Conda cache folder";
    hidden.checked=false;path="";parent="";current.textContent="";shortcuts.replaceChildren();
    dialog.showModal();load(target.value.trim());
  });
})();
