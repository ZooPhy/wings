/* Offline adapter for the shared Phylodynamics viewer. */
(function(global){
'use strict';
function decode(s){return new TextDecoder().decode(Uint8Array.from(atob(s),c=>c.charCodeAt(0)));}
function documentFor(model,assets){
 const close='</'+'script>';
 const script=s=>'<script>'+s+close;
 const json=JSON.stringify(model).replace(/</g,'\\u003c');
 const setup=`const data=JSON.parse(document.getElementById('results-data').textContent);const link=document.querySelector('a[download]');if(link){link.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));link.download='phylodynamics-results.json';}window.addEventListener('message',e=>{if(e.source===parent&&e.data==='wings:pause'){const b=document.getElementById('play');if(b&&b.textContent.trim()==='Pause')b.click();}});`;
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WINGS Phylodynamics</title><style>'+decode(assets.style)+'</style></head><body><main id="app"></main><script type="application/json" id="results-data">'+json+close+script(decode(assets.boundaries))+script(decode(assets.script))+script(setup)+'</body></html>';
}
function mount(explorer,panel){
 const model=explorer.payload.phylodynamics_results;
 panel.replaceChildren();
 const note=document.createElement('p');note.style.cssText='margin:1rem 1.5rem;color:#435a66';
 if(!model){
  note.textContent='No Phylodynamics results are included in this report. For a new run, enable Phylodynamics (Fast) in job submission. Existing runs can add checked results using the report-only workflow described in the README.';
  panel.append(note);return {setActive(){}};
 }
 if(model.demo){note.textContent='Illustrative demo — simulated phylodynamics data, not inferred from the demo samples. Synthetic sample IDs are shown in this tab.';note.style.cssText+=';padding:1rem;border-left:4px solid #ffc72c;background:#fff6d9';panel.append(note);}
 const frame=document.createElement('iframe');frame.title='WINGS Phylodynamics results';frame.setAttribute('sandbox','allow-scripts allow-downloads');frame.style.cssText='display:block;width:100%;height:85vh;min-height:650px;border:0;background:white';panel.append(frame);
 let loaded=false;
 return {setActive(active){if(active&&!loaded){frame.srcdoc=documentFor(model,global.WINGS_PHYLODYNAMICS_ASSETS);loaded=true;}else if(!active&&loaded){frame.contentWindow?.postMessage('wings:pause','*');}}};
}
const api={mount,documentFor};global.WINGS_PHYLODYNAMICS_TAB=api;if(typeof module==='object'&&module.exports)module.exports=api;
})(globalThis);
