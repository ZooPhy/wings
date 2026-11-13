/* Interactive WINGS model comparisons. Offline SVG; no network dependencies. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.WINGS_MODEL_EXPLORER=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const SEGMENTS=['HA','NA','PB2','PB1','PA','NP','MP','NS'];
  const finite=x=>typeof x==='number'&&Number.isFinite(x);
  const BASE=['temporal_days','geographic_km'];
  const FACTORS={host:'same_host',seasonal:'seasonal_profile_distance',weather:'environmental_distance',migration:'migration_context_distance'};
  const PATH_LABELS={seasonal:'Core model',weather:'Weather path',migration:'Migration path',host_vs_baseline:'Saved host comparison',ecology_vs_host:'Saved seasonal comparison',environment_vs_ecology:'Saved weather comparison',migration_vs_ecology:'Saved migration comparison'};
  const LABELS={baseline:'Time & location',host:'Add host',seasonal:'Add seasonal patterns',weather:'Add weather',migration:'Add migration'};
  const pairKey=(a,b)=>JSON.stringify(a<b?[a,b]:[b,a]);
  const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
  const percent=x=>finite(x)?`${(100*x).toFixed(1)}%`:'Unavailable';
  const pause=()=>new Promise(resolve=>setTimeout(resolve,0));
  function design(rows,predictors,minimum=8){
    const ids=[...new Set(rows.flatMap(r=>[r.sample_a,r.sample_b]))].sort();
    const base={n_samples:ids.length,n_pairs:rows.length,ids,predictors};
    if(ids.length<minimum)return {...base,status:'INSUFFICIENT_UNIQUE_SAMPLES'};
    if(rows.length<Math.max(10,predictors.length+3))return {...base,status:'INSUFFICIENT_COMPLETE_PAIRS'};
    const n=rows.length,Q=[Array(n).fill(1/Math.sqrt(n))];
    for(const name of predictors){
      const raw=rows.map(r=>r[name]);
      if(!raw.every(finite))return {...base,status:'MISSING_PREDICTOR'};
      const avg=raw.reduce((a,b)=>a+b,0)/n,centered=raw.map(v=>v-avg),norm=Math.sqrt(dot(centered,centered));
      if(norm===0)return {...base,status:'INSUFFICIENT_PREDICTOR_VARIATION'};
      let v=centered.map(x=>x/norm);
      // Reorthogonalization avoids normal-equation instability near collinearity.
      for(let pass=0;pass<2;pass++)for(const q of Q){const c=dot(q,v);v=v.map((x,i)=>x-c*q[i]);}
      const length=Math.sqrt(dot(v,v));
      if(length<1e-10)return {...base,status:'INSUFFICIENT_INDEPENDENT_VARIATION'};
      Q.push(v.map(x=>x/length));
    }
    return {...base,status:'READY',Q};
  }
  function project(plan,y){
    const avg=y.reduce((a,b)=>a+b,0)/y.length,center=y.map(v=>v-avg),sst=dot(center,center);
    if(sst<=0)return {status:'CONSTANT_GENETIC_DISTANCE'};
    const fitted=Array(y.length).fill(avg);
    for(const q of plan.Q.slice(1)){const c=dot(q,center);for(let i=0;i<y.length;i++)fitted[i]+=q[i]*c;}
    const residuals=y.map((v,i)=>v-fitted[i]);
    return {status:'READY',r2:Math.max(0,Math.min(1,1-dot(residuals,residuals)/sst)),fitted,residuals};
  }
  function fit(rows,predictors,minimum=8){const plan=design(rows,predictors,minimum);return plan.status==='READY'?{...plan,...project(plan,rows.map(r=>r.patristic_distance))}:plan;}
  function rng(seed){let n=seed>>>0||1;return ()=>{n^=n<<13;n^=n>>>17;n^=n<<5;return (n>>>0)/4294967296;};}
  function adjust(results){
    const groups=new Map();
    for(const r of results)if(finite(r.permutation_p)){const key=r.path+':'+r.code;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
    for(const rows of groups.values()){rows.sort((a,b)=>a.permutation_p-b.permutation_p);let q=1;for(let i=rows.length-1;i>=0;i--){q=Math.min(q,rows[i].permutation_p*rows.length/(i+1));rows[i].fdr_q=q;}}
  }
  async function permutation(rows,reduced,full,observed,count,random,alive,progress){
    const r=project(reduced,rows.map(x=>x.patristic_distance));
    const lookup=new Map(rows.map((row,i)=>[pairKey(row.sample_a,row.sample_b),r.residuals[i]]));
    const ids=reduced.ids;let valid=0,extreme=0;
    for(let k=0;k<count;k++){
      if(k%20===0){if(!alive())throw new Error('CANCELLED');progress?.(k,count);await pause();}
      const shuffled=ids.slice();for(let i=shuffled.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[shuffled[i],shuffled[j]]=[shuffled[j],shuffled[i]];}
      const map=new Map(ids.map((id,i)=>[id,shuffled[i]])),y=[];let complete=true;
      for(let i=0;i<rows.length;i++){const residual=lookup.get(pairKey(map.get(rows[i].sample_a),map.get(rows[i].sample_b)));if(residual===undefined){complete=false;break;}y.push(r.fitted[i]+residual);}
      if(!complete)continue;
      const a=project(reduced,y),b=project(full,y);if(a.status!=='READY'||b.status!=='READY')continue;
      valid++;if(b.r2-a.r2>=observed-1e-12)extreme++;
    }
    if(!alive())throw new Error('CANCELLED');
    return {permutation_p:valid?(extreme+1)/(valid+1):null,permutations_valid:valid};
  }
  function validateInputs(input,knownIds){
    if(!input||!Array.isArray(input.pairs)||!Array.isArray(input.sample_features))throw new Error('Pairwise inputs and sample features are required.');
    if(input.pairs.length>200000)throw new Error('This dataset exceeds the browser limit of 200,000 pair rows. Use the full analysis workflow.');
    const ids=new Set(),known=knownIds?new Set(knownIds):null,seen=new Set();
    for(const s of input.sample_features){if(typeof s.sample_id!=='string'||!s.sample_id||ids.has(s.sample_id)||known&&!known.has(s.sample_id))throw new Error('Sample identities are missing, duplicated, or do not match this run.');ids.add(s.sample_id);}
    for(const r of input.pairs){
      if(!SEGMENTS.includes(r.segment)||!ids.has(r.sample_a)||!ids.has(r.sample_b)||r.sample_a===r.sample_b)throw new Error('Invalid segment or sample identity in pairwise inputs.');
      const key=r.segment+pairKey(r.sample_a,r.sample_b);if(seen.has(key))throw new Error('Duplicate pairwise input.');seen.add(key);
      if(r.patristic_distance!==null&&(!finite(r.patristic_distance)||r.patristic_distance<0))throw new Error('Invalid genetic distance.');
      for(const p of [...BASE,...Object.values(FACTORS)])if(r[p]!==null&&r[p]!==undefined&&!finite(r[p]))throw new Error('Invalid predictor value: '+p);
    }
    return input;
  }
  async function analyze(input,options={},hooks={}){
    validateInputs(input);
    const minimum=options.minimum??8,count=options.permutations??999;
    if(!Number.isInteger(minimum)||minimum<3||!Number.isInteger(count)||count<0||count>9999)throw new Error('Invalid analysis settings.');
    const chosen=new Set(options.samples??input.sample_features.map(s=>s.sample_id));
    const selected=options.factors??['host','seasonal'];
    if(!Array.isArray(selected)||selected.some(f=>!Object.hasOwn(FACTORS,f)))throw new Error('Unknown factor.');
    const core=['host','seasonal'].filter(f=>selected.includes(f));
    const paths=['weather','migration'].filter(f=>selected.includes(f));if(!paths.length)paths.push('seasonal');
    const features=new Map(input.sample_features.map(s=>[s.sample_id,s]));
    const alive=hooks.alive??(()=>true),results=[],random=rng(options.seed??20261001);
    for(const segment of SEGMENTS)for(const path of paths){
      if(!alive())throw new Error('CANCELLED');
      const codes=['baseline',...core,...(path==='seasonal'?[]:[path])];
      const allPredictors=[...BASE,...codes.slice(1).map(c=>FACTORS[c])];
      const candidates=input.pairs.filter(r=>r.segment===segment&&chosen.has(r.sample_a)&&chosen.has(r.sample_b));
      const rows=candidates.filter(r=>finite(r.patristic_distance)&&allPredictors.every(p=>finite(r[p])));
      const ids=[...new Set(rows.flatMap(r=>[r.sample_a,r.sample_b]))],nodes=[];let predictors=[...BASE];
      let previous=null;
      for(const code of codes){
        if(code!=='baseline')predictors=[...predictors,FACTORS[code]];
        const plan=design(rows,predictors,minimum),fitted=plan.status==='READY'?project(plan,rows.map(r=>r.patristic_distance)):{status:plan.status};
        const node={segment,path,code,label:LABELS[code],status:fitted.status,r2:fitted.r2??null,delta_r2:null,permutation_p:null,fdr_q:null,permutations_valid:0,n_samples:ids.length,n_pairs:rows.length,n_selected:chosen.size,n_candidate_pairs:candidates.length,eligible_sample_ids:ids,predictors:[...predictors]};
        if(code==='migration'){
          const keys=ids.map(id=>features.get(id)?.migration_context_key),contexts=new Set(keys.filter(x=>typeof x==='string'&&x));node.n_migration_contexts=contexts.size;
          if(keys.some(x=>typeof x!=='string'||!x)||contexts.size<minimum){node.status='INSUFFICIENT_MIGRATION_CONTEXTS';node.r2=null;}
          else if(contexts.size!==ids.length)node.descriptive_reason='Samples share migration settings; statistical support is unavailable.';
        }
        if(previous&&node.status==='READY'&&previous.node.status==='READY'){
          node.delta_r2=node.r2-previous.node.r2;
          if(count>0&&!node.descriptive_reason){hooks.progress?.(`${segment} · ${path} path · ${LABELS[code]}`);Object.assign(node,await permutation(rows,previous.plan,plan,node.delta_r2,count,random,alive,(done,total)=>hooks.progress?.(`${segment} · ${LABELS[code]} · ${done}/${total} randomized comparisons`)));}
          if(!finite(node.permutation_p))node.descriptive_reason||='Fit only; statistical support has not been calculated.';
        }
        nodes.push(node);results.push(node);previous={node,plan};
      }
      await pause();
    }
    adjust(results);
    return {scope:'browser-refit',synthetic:input.synthetic===true,results,options:{...options,samples:[...chosen],factors:[...selected],minimum,permutations:count},notes:'Each path uses identical complete-data pairs at every step. Weather distances retain the original run standardization. FDR is adjusted across segments separately for each path and added factor.'};
  }

  const make=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
  const svg=(tag,attrs,text)=>{const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs||{}))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;return el;};
  function mount(explorer,container){
    const data=explorer.payload.genomic_ecological_concordance,samples=explorer.payload.samples||[],savedSettings=explorer.modelExplorerSettings;
    let input=data.interactive_inputs||null,result=null,serial=0,dirty=false,active=null,plotPoints=[],inputError='';
    if(input&&(explorer.payload.synthetic===true||explorer.payload.ecological_clock?.synthetic===true))input={...input,synthetic:true};
    const panel=make('section','wme'),head=make('div','wme-heading');head.append(make('span','wme-kicker','MODEL EXPLORER'),make('h4','','What helps explain genetic differences?'),make('p','','Follow each model from time and location to the factors you choose. Click a point for its results.'));
    const controls=make('div','wme-controls'),status=make('p','wme-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    const view=make('div','wme-view'),chart=make('div','wme-chart'),evidence=make('div','wme-evidence');evidence.setAttribute('role','complementary');evidence.setAttribute('aria-label','Model details');evidence.setAttribute('aria-live','polite');view.append(chart,evidence);
    const control=(label,el)=>{const wrap=make('label');wrap.append(make('span','',label),el);controls.append(wrap);return el;};
    const select=(values)=>{const el=make('select');for(const [value,label] of values){const o=make('option','',label);o.value=value;el.append(o);}return el;};
    const segment=control('Influenza segment',select(SEGMENTS.map(s=>[s,s])));
    const host=control('Host',select([['','All hosts'],...[...new Set(samples.map(s=>s.host||'Not recorded'))].sort().map(s=>[s,s])]));
    const region=control('Location',select([['','All locations'],...[...new Set(samples.map(s=>[s.country,s.state].filter(Boolean).join(' / ')||'Not recorded'))].sort().map(s=>[s,s])]));
    const start=control('Collected from',make('input'));start.type='date';const end=control('Collected through',make('input'));end.type='date';
    const support=control('Statistical checks',select([['999','999 randomized comparisons'],['199','199 — quicker exploration'],['0','Fit only']]));
    const factors=make('fieldset','wme-factors');factors.append(make('legend','','Factors included'));const checks={};
    for(const [key,label] of [['host','Host'],['seasonal','Seasonal bird patterns'],['weather','Weather'],['migration','Migration']]){const l=make('label'),c=make('input');c.type='checkbox';c.checked=key==='host'||key==='seasonal';checks[key]=c;l.append(c,make('span','',label));factors.append(l);}
    factors.append(make('small','','Time and location are always included. Weather and migration form separate paths.'));
    const chooser=make('details','wme-sample-picker'),sampleSummary=make('summary'),sampleSearch=make('input');sampleSearch.type='search';sampleSearch.placeholder='Find a sample';sampleSearch.setAttribute('aria-label','Find a comparison sample');
    const sampleList=make('div','wme-sample-list'),sampleChecks=new Map(),sampleLabels=[];
    for(const s of samples){const label=make('label'),c=make('input');c.type='checkbox';c.checked=true;sampleChecks.set(s.sample_id,c);label.append(c,make('span','',s.sample_id));sampleList.append(label);sampleLabels.push([s.sample_id,label]);}
    const pickActions=make('div','wme-actions');for(const [label,value] of [['Select all',true],['Clear all',false]]){const b=make('button','',label);b.type='button';b.addEventListener('click',()=>{for(const c of sampleChecks.values())c.checked=value;markDirty();});pickActions.append(b);}
    chooser.append(sampleSummary,sampleSearch,pickActions,sampleList);
    const actions=make('div','wme-actions'),update=make('button','wme-primary','Update comparison'),reset=make('button','','Reset filters'),download=make('button','','Download comparison');for(const b of [update,reset,download])b.type='button';download.disabled=true;actions.append(update,reset,download);
    const note=make('p','wme-note','Each colored path uses the same complete-data pairs at every step. Paths can include different samples. Changing filters recalculates the models; it does not change the saved run results.');
    const methods=make('details','wme-methods');methods.append(make('summary','','How these comparisons are calculated'),make('p','','Nested linear models use the same complete-data pairs within each path. Statistical checks shuffle sample labels in the reduced-model residual matrix, retaining reduced-model fitted values. Adjusted q values use Benjamini–Hochberg correction across segments separately for each path and added factor. Weather distances keep the original run standardization. Migration uses the fixed collection night; repeated contexts have no migration p or q value. All associations are exploratory and do not establish transmission or cause and effect.'));
    const legacy=make('div','wme-legacy'),file=make('input');file.type='file';file.accept='.json,application/json';const fileLabel=make('label','','Load analysis data (concordance.json)');fileLabel.append(file);legacy.append(make('p','','Older reports may contain saved summaries only. Load this run’s concordance.json to enable recalculation.'),fileLabel);
    panel.append(head,controls,factors,chooser,actions,status,view,note,methods,legacy);container.append(panel);
    function selectedIds(){return samples.filter(s=>sampleChecks.get(s.sample_id).checked&&(!host.value||(s.host||'Not recorded')===host.value)&&(!region.value||([s.country,s.state].filter(Boolean).join(' / ')||'Not recorded')===region.value)&&(!start.value||/^\d{4}-\d{2}-\d{2}$/.test(s.collection_date||'')&&s.collection_date>=start.value)&&(!end.value||/^\d{4}-\d{2}-\d{2}$/.test(s.collection_date||'')&&s.collection_date<=end.value)).map(s=>s.sample_id);}
    function sampleCount(){sampleSummary.textContent=`Samples included: ${selectedIds().length} of ${samples.length}`;}
    function remember(){explorer.modelExplorerSettings={host:host.value,region:region.value,start:start.value,end:end.value,support:support.value,samples:[...sampleChecks].filter(([,c])=>c.checked).map(([id])=>id),factors:Object.keys(checks).filter(k=>checks[k].checked)};}
    function markDirty(){serial++;dirty=true;remember();sampleCount();status.textContent='Selection changed. Select Update comparison to calculate these settings.';chart.replaceChildren();evidence.replaceChildren();download.disabled=true;update.disabled=!input;}
    function readable(code){return ({INSUFFICIENT_UNIQUE_SAMPLES:'Too few distinct samples',INSUFFICIENT_COMPLETE_PAIRS:'Too few complete sample pairs',INSUFFICIENT_PREDICTOR_VARIATION:'This factor does not vary enough',INSUFFICIENT_INDEPENDENT_VARIATION:'This factor cannot be separated from those already included',CONSTANT_GENETIC_DISTANCE:'No genetic-distance variation',INSUFFICIENT_MIGRATION_CONTEXTS:'Too few distinct migration settings'})[code]||'Unavailable';}
    function inspect(row){active=row;for(const [point,value] of plotPoints)point.setAttribute('aria-pressed',String(value===row));evidence.replaceChildren();evidence.append(make('h4','',row.label),make('p','',`${row.segment} · ${PATH_LABELS[row.path]||row.path}`),make('strong','wme-value',row.status==='READY'?percent(row.r2):readable(row.status)));
      if(row.status==='READY')evidence.append(make('p','','Genetic variation explained by this model.'));
      evidence.append(make('p','',`${row.n_samples} distinct samples · ${row.n_pairs} pairs`));
      if(Number.isInteger(row.n_candidate_pairs))evidence.append(make('p','',`${row.n_candidate_pairs-row.n_pairs} pairs excluded for missing inputs. ${row.n_selected-row.n_samples} selected samples are not represented in this path.`));
      if(finite(row.delta_r2))evidence.append(make('p','',`Added explanatory value: ${(100*row.delta_r2).toFixed(1)} percentage points`));
      if(finite(row.fdr_q)&&finite(row.permutation_p))evidence.append(make('p','',row.fdr_q<.05?'Statistical support after adjustment across segments.':'No statistical support at the 0.05 adjusted threshold.'),make('p','',`Adjusted q: ${row.fdr_q.toPrecision(3)} · p: ${row.permutation_p.toPrecision(3)}`));
      else if(row.code!=='baseline')evidence.append(make('p','',row.descriptive_reason||'Statistical support is unavailable.'));
      if(finite(row.permutation_p))evidence.append(make('p','',`Valid randomized comparisons: ${row.permutations_valid} of ${row.permutations_requested??result?.options?.permutations??'not recorded'}`));
      if(Number.isInteger(row.n_migration_contexts))evidence.append(make('p','',`${row.n_migration_contexts} distinct migration settings`));
    }
    function draw(){
      chart.replaceChildren();evidence.replaceChildren();plotPoints=[];const rows=(result?.results||[]).filter(r=>r.segment===segment.value);
      if(!rows.length){chart.append(make('p','','No model results are available for this segment.'));return;}
      const paths=[...new Set(rows.map(r=>r.path))],codes=['baseline','host','seasonal'];if(rows.some(r=>r.code==='weather'||r.code==='migration'))codes.push('context');
      const used=codes.filter(c=>c==='context'||rows.some(r=>r.code===c));const W=Math.max(300,chart.clientWidth||850),H=360,left=60,right=35,top=45,bottom=85;
      drawnWidth=chart.clientWidth||0;
      const x=code=>left+used.indexOf(['weather','migration'].includes(code)?'context':code)*(W-left-right)/Math.max(1,used.length-1),y=v=>H-bottom-v*(H-top-bottom);
      const picture=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'group','aria-label':'Model progression. Vertical axis: percent of genetic variation explained.'});
      picture.append(svg('text',{x:left,y:18},'Genetic variation explained'));
      for(let i=0;i<=4;i++){const v=i/4;picture.append(svg('line',{x1:left,x2:W-right,y1:y(v),y2:y(v),stroke:'#e0e6e8'}),svg('text',{x:left-12,y:y(v)+4,'text-anchor':'end'},`${100*v}%`));}
      for(const [i,code] of used.entries()){
        const words=({baseline:['Time &','location'],host:['Add host'],seasonal:['Add seasonal','patterns'],context:['Weather /','migration']})[code];
        const label=svg('text',{x:x(code),y:H-bottom+27,'text-anchor':i===0?'start':i===used.length-1?'end':'middle'});
        words.forEach((word,line)=>label.append(svg('tspan',{x:x(code),dy:line?17:0},word)));
        picture.append(label);
      }
      const legend=make('div','wme-path-legend');
      paths.forEach((path,index)=>{const color=['#8c1d40','#007f84','#80601d','#496ea0'][index%4],line=rows.filter(r=>r.path===path);let prev=null;
        const label=make('span','',`${PATH_LABELS[path]||path}${path==='migration'?' (dashed)':''} · ${line[0].n_samples} samples · ${line[0].n_pairs} pairs`);label.style.color=color;legend.append(label);
        for(const row of line){
          if(row.status!=='READY'||!finite(row.r2)){prev=null;continue;}
          if(prev)picture.append(svg('path',{d:`M${x(prev.code)},${y(prev.r2)} L${x(row.code)},${y(row.r2)}`,stroke:color,'stroke-width':3,'stroke-dasharray':path==='migration'?'7 5':'none',fill:'none'}));
          const point=svg('g',{role:'button',tabindex:0,'aria-pressed':'false','aria-label':`${row.label}: ${percent(row.r2)}; ${row.n_samples} samples`});
          plotPoints.push([point,row]);point.append(svg('circle',{cx:x(row.code),cy:y(row.r2),r:8,fill:color,stroke:'white','stroke-width':2}),svg('title',{},`${row.label}: ${percent(row.r2)}`));
          point.addEventListener('click',()=>inspect(row));point.addEventListener('focus',()=>inspect(row));point.addEventListener('pointerenter',()=>inspect(row));point.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspect(row);}});picture.append(point);prev=row;
        }
      });
      chart.append(picture,legend);
      const unavailable=rows.filter(r=>r.status!=='READY');if(unavailable.length){const list=make('ul','wme-unavailable');for(const r of unavailable){const li=make('li'),b=make('button','',`${r.label} (${PATH_LABELS[r.path]||r.path}): ${readable(r.status)}`);b.type='button';b.addEventListener('click',()=>inspect(r));li.append(b);list.append(li);}chart.append(list);}
      inspect(rows.includes(active)?active:rows.find(r=>finite(r.delta_r2))||rows[0]);
    }
    async function run(preview=false){
      if(!input)return;remember();const token=++serial;dirty=false;update.disabled=true;download.disabled=true;chart.replaceChildren();evidence.replaceChildren();
      if(start.value&&end.value&&start.value>end.value){status.textContent='The start date must be on or before the end date.';update.disabled=false;return;}
      try{
        status.textContent='Calculating model fits…';
        const next=await analyze(input,{samples:selectedIds(),factors:Object.keys(checks).filter(k=>checks[k].checked),minimum:data.readiness?.minimum_unique_samples??8,permutations:preview?0:Number(support.value)},{alive:()=>token===serial,progress:text=>{if(token===serial)status.textContent=text;}});
        if(token!==serial)return;result=next;draw();download.disabled=false;status.textContent=preview?'Fit preview ready. Select Update comparison to run the selected statistical checks.':`Comparison updated for ${selectedIds().length} selected samples. ${Number(support.value)===0?'Fit only; statistical support was not calculated.':'Statistical checks recalculated where estimable; select a point for support and exclusions.'}`;
      }catch(error){if(token===serial&&error.message!=='CANCELLED')status.textContent='Comparison unavailable: '+error.message;}
      finally{if(token===serial)update.disabled=false;}
    }
    function saved(){
      const results=[];for(const row of data.models||[]){
        const family=row.comparison;if(!['host_vs_baseline','ecology_vs_host','environment_vs_ecology','migration_vs_ecology'].includes(family))continue;
        const code=({host_vs_baseline:'host',ecology_vs_host:'seasonal',environment_vs_ecology:'weather',migration_vs_ecology:'migration'})[family];
        // Saved comparisons can have different cohorts: never join unrelated fits.
        const path=family,reducedCode=code==='host'?'baseline':code==='seasonal'?'host':'seasonal';
        results.push({...row,path,code:reducedCode,label:'Before adding '+LABELS[code].replace('Add ',''),r2:row.reduced_r2,status:finite(row.reduced_r2)?'READY':row.display_status||row.status,delta_r2:null,permutation_p:null,fdr_q:null});
        results.push({...row,path,code,label:LABELS[code],r2:row.delta_r2!==null?row.full_r2:null,status:row.delta_r2!==null&&finite(row.full_r2)?'READY':row.display_status||row.status,descriptive_reason:row.display_status==='DESCRIPTIVE'?row.diagnostic:null});
      }
      result={scope:'saved-results',synthetic:explorer.payload.synthetic===true,results};draw();download.disabled=false;status.textContent='Saved comparisons shown. Each line has its own sample set. Load analysis data to change included samples or factors.';
    }
    for(const el of [host,region,start,end,support,...Object.values(checks),...sampleChecks.values()])el.addEventListener('change',markDirty);
    segment.addEventListener('change',()=>{if(!dirty)draw();});
    sampleSearch.addEventListener('input',()=>{for(const [id,label] of sampleLabels)label.hidden=!id.toLowerCase().includes(sampleSearch.value.toLowerCase());});
    update.addEventListener('click',()=>run());reset.addEventListener('click',()=>{host.value='';region.value='';start.value='';end.value='';for(const c of sampleChecks.values())c.checked=true;for(const [k,c] of Object.entries(checks))c.checked=k==='host'||k==='seasonal';markDirty();});
    download.addEventListener('click',()=>{if(!result||dirty)return;const blob=new Blob([JSON.stringify({...result,notes:result.notes||'Saved run comparisons.'},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=make('a');a.href=url;a.download='wings-model-comparison.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
    file.addEventListener('change',async()=>{const selected=file.files?.[0];if(!selected)return;try{
      if(selected.size>100*1024*1024)throw new Error('Analysis file exceeds the 100 MB browser limit.');
      const raw=JSON.parse(await selected.text());
      if(!Array.isArray(raw.models)||data.models.some(old=>!raw.models.some(r=>r.segment===old.segment&&r.comparison===old.comparison&&r.n_samples===old.n_samples&&r.reduced_r2===old.reduced_r2&&r.full_r2===old.full_r2)))throw new Error('The analysis file does not match the saved comparisons in this report.');
      input=validateInputs({pairs:raw.pairs,sample_features:raw.sample_features},samples.map(s=>s.sample_id));enable();await run(true);
    }catch(error){status.textContent='Analysis data not loaded: '+error.message;}finally{file.value='';}});
    function enable(){for(const el of [host,region,start,end,support,...Object.values(checks),...sampleChecks.values(),reset,...pickActions.children])el.disabled=!input;update.disabled=!input;legacy.hidden=Boolean(input);}
    try{if(input)validateInputs(input,samples.map(s=>s.sample_id));}catch(error){input=null;inputError=error.message;}
    if(savedSettings){host.value=savedSettings.host;region.value=savedSettings.region;start.value=savedSettings.start;end.value=savedSettings.end;support.value=savedSettings.support;for(const [id,c] of sampleChecks)c.checked=savedSettings.samples.includes(id);for(const [k,c] of Object.entries(checks))c.checked=savedSettings.factors.includes(k);}
    let drawnWidth=0;
    const resizeObserver=typeof ResizeObserver==='function'?new ResizeObserver(()=>{
      if(chart.clientWidth>0&&Math.abs(chart.clientWidth-drawnWidth)>1&&result&&!dirty)draw();
    }):null;
    resizeObserver?.observe(chart);
    sampleCount();enable();if(input)run(true);else{saved();if(inputError)status.textContent+=' Embedded refit inputs unavailable: '+inputError;}
    return {
      refreshView:()=>{if(!dirty)draw();},cancel:()=>{serial++;resizeObserver?.disconnect();},getResult:()=>result,
      attach:(container,payload)=>{
        if(payload.genomic_ecological_concordance!==data||payload.samples!==samples)return false;
        container.append(panel);
        return true;
      }
    };
  }
  return {SEGMENTS,fit,analyze,validateInputs,adjust,mount};
});
