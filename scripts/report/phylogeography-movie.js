/* WINGS phylogeography movie: consumes histories; never infers them from ML labels. */
(() => {
  'use strict';
  const SCHEMA = 'wings.phylogeography-movie.v1';
  const DAY = 86400000;
  const COLORS = ['#8C1D40','#007D86','#5B57A6','#B65E17','#37775C','#2D6792','#96517A','#666D32'];
  const own = (o,k) => Object.prototype.hasOwnProperty.call(o,k);
  const fail = m => { throw new Error(m); };
  function stamp(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z)?$/.test(value)) fail('Dates must be YYYY-MM-DD or UTC ISO timestamps.');
    const t = Date.parse(value.length === 10 ? value+'T00:00:00Z' : value);
    if (!Number.isFinite(t) || new Date(t).toISOString().slice(0,10) !== value.slice(0,10)) fail('Invalid calendar date: '+value);
    return t;
  }
  const iso = t => new Date(t).toISOString().slice(0,10);
  const labelDate = t => new Date(t).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'});
  function string(v,where) {
    if(typeof v !== 'string' || !v.trim() || v.length>300) fail(where+' must be a nonempty string (up to 300 characters).');
    return v;
  }
  function validate(raw) {
    if (!raw || raw.schema !== SCHEMA) fail('Expected '+SCHEMA+' reconstruction JSON.');
    if (typeof raw.synthetic !== 'boolean') fail('Declare synthetic: true or false.');
    if (!raw.provenance || raw.provenance.uncertainty !== 'conditional-on-fixed-tree') fail('This version requires histories conditional on fixed dated segment trees.');
    if (!['bayesian','empirical-bayes','synthetic'].includes(raw.provenance.inference)) fail('Declare inference as bayesian, empirical-bayes, or synthetic.');
    if(raw.synthetic !== (raw.provenance.inference === 'synthetic')) fail('Synthetic data and inference labels must agree.');
    string(raw.provenance.method,'Inference method');
    string(raw.title,'Title');
    if (!Array.isArray(raw.locations) || raw.locations.length < 2 || raw.locations.length > 100) fail('Provide 2–100 named geographic states.');
    const states = new Map();
    raw.locations.forEach((s,i)=>{
      string(s.id,'State ID'); string(s.label,'State label');
      if(states.has(s.id)) fail('Duplicate state ID: '+s.id);
      if(typeof s.lat !== 'number' || typeof s.lon !== 'number' || !Number.isFinite(s.lat) || !Number.isFinite(s.lon) || Math.abs(s.lat)>90 || Math.abs(s.lon)>180) fail('Each geographic state needs valid numeric lat/lon coordinates.');
      states.set(s.id,{...s,color:COLORS[i%COLORS.length]});
    });
    if(!Array.isArray(raw.segments) || !raw.segments.length || raw.segments.length>8) fail('Provide 1–8 segment reconstructions.');
    const ids = new Set(); let eventTotal=0;
    const segments=raw.segments.map(segment=>{
      string(segment.id,'Segment ID'); if(ids.has(segment.id)) fail('Duplicate segment: '+segment.id); ids.add(segment.id);
      if(!Array.isArray(segment.nodes) || segment.nodes.length<2 || segment.nodes.length>5000) fail('Each segment needs 2–5,000 tree nodes.');
      const nodes=new Map();
      segment.nodes.forEach(n=>{
        string(n.id,'Node ID'); if(nodes.has(n.id)) fail('Duplicate node ID: '+n.id);
        if(n.label!==undefined) string(n.label,'Node label');
        if(n.sample_id!==undefined) string(n.sample_id,'Sample ID');
        if(n.observed_state!==undefined && !states.has(n.observed_state)) fail('Unknown observed state: '+n.observed_state);
        nodes.set(n.id,{...n,t:stamp(n.date),children:[]});
      });
      const roots=[...nodes.values()].filter(n=>n.parent===null);
      if(roots.length!==1) fail('Each segment must have exactly one root with parent: null.');
      nodes.forEach(n=>{ if(n.parent!==null) {
        const p=nodes.get(n.parent); if(!p || p===n) fail('Missing or invalid parent for '+n.id);
        if(p.t>n.t) fail('Child predates its parent: '+n.id); p.children.push(n);
      }});
      const order=[], visited=new Set(), stack=[roots[0]];
      while(stack.length) { const n=stack.pop(); if(visited.has(n.id)) fail('Tree contains a cycle.'); visited.add(n.id); order.push(n); stack.push(...n.children.slice().reverse()); }
      if(order.length!==nodes.size) fail('Tree is disconnected or cyclic.');
      const tips=order.filter(n=>!n.children.length), end=Math.max(...tips.map(n=>n.t)), start=roots[0].t;
      if(end<=start) fail('A positive dated-tree duration is required.');
      tips.forEach(n=>{if(!states.has(n.observed_state)) fail('Every tip must have a known observed_state: '+n.id);});
      if(!Array.isArray(segment.histories) || !segment.histories.length || segment.histories.length>10000) fail('Provide 1–10,000 equally weighted, post-burn-in histories per segment.');
      if(segment.histories.length*nodes.size>1000000) fail('Limit each segment to 1,000,000 node × history combinations for browser playback.');
      let focal=null;
      const marked=tips.filter(n=>n.sample_id).map(n=>n.sample_id);
      const declared=segment.focal_sample_ids??(marked.length>=2?marked:undefined);
      if(declared!==undefined) {
        const samples=declared;
        if(!Array.isArray(samples)||samples.length<2||new Set(samples).size!==samples.length) fail('Provide at least two unique focal sample IDs.');
        const chosen=samples.map(id=>{const matches=tips.filter(n=>n.sample_id===id);if(matches.length!==1)fail('Focal sample must match exactly one tip: '+id);return matches[0];});
        const paths=chosen.map(t=>{const a=[];for(let n=t;n;n=nodes.get(n.parent))a.push(n.id);return a;});
        const mrca=paths[0].find(id=>paths.every(p=>p.includes(id))),branches=new Set();
        paths.forEach(p=>p.slice(0,p.indexOf(mrca)).forEach(id=>branches.add(id)));
        focal={mrca,branches,sampleIds:samples};
      }
      const hids=new Set();
      const histories=segment.histories.map(h=>{
        string(h.id,'History ID'); if(hids.has(h.id)) fail('Duplicate history ID: '+h.id); hids.add(h.id);
        if(own(h,'weight')) fail('Weighted histories are not supported; supply equally weighted posterior draws.');
        if(!states.has(h.root_state) || !Array.isArray(h.jumps)) fail('Each history needs root_state and a jumps array, including zero-jump histories.');
        eventTotal+=h.jumps.length; if(eventTotal>500000) fail('File exceeds the 500,000-event limit.');
        const byBranch=new Map(), jumps=h.jumps.map(j=>{
          const n=nodes.get(j.branch), t=stamp(j.date);
          if(!n || n.parent===null) fail('Jump must reference a non-root child node.');
          if(t<=nodes.get(n.parent).t || t>n.t) fail('Jump is outside its branch interval: '+j.branch);
          if(!states.has(j.from) || !states.has(j.to) || j.from===j.to) fail('Jump states must be known and different.');
          return {...j,t};
        }).sort((a,b)=>a.t-b.t);
        jumps.forEach(j=>{if(!byBranch.has(j.branch))byBranch.set(j.branch,[]);byBranch.get(j.branch).push(j);});
        const nodeStates=new Map([[roots[0].id,h.root_state]]);
        for(const n of order) {
          let current=n.parent===null?h.root_state:nodeStates.get(n.parent), last=-Infinity;
          for(const j of byBranch.get(n.id)||[]) {
            if(j.t===last) fail('Two jumps share a time on branch '+n.id);
            if(j.from!==current) fail('Discontinuous state history on branch '+n.id);
            current=j.to;last=j.t;
          }
          if(n.observed_state!==undefined && current!==n.observed_state) fail('History does not match observed state at '+n.id);
          nodeStates.set(n.id,current);
        }
        const incoming=new Map([...states.keys()].map(k=>[k,[]]));
        jumps.forEach(j=>{if(!focal||focal.branches.has(j.branch))incoming.get(j.to).push(j.t);});
        return {...h,jumps,byBranch,nodeStates,incoming};
      });
      return {id:segment.id,nodes,order,root:roots[0],tips,start,end,histories,focal};
    });
    return {raw,states,segments};
  }
  function upperBound(a,t) { let l=0,r=a.length;while(l<r){const m=(l+r)>>>1;if(a[m]<=t)l=m+1;else r=m;}return l; }
  function quantile(a,p) {return a[Math.max(0,Math.ceil(p*a.length)-1)];}
  function studyView(segment) {
    if(!segment.focal)return segment;
    const keep=new Set([...segment.focal.branches,segment.focal.mrca]);
    const nodes=new Map(segment.order.filter(n=>keep.has(n.id)).map(n=>[n.id,{...n,children:[],parent:n.id===segment.focal.mrca?null:n.parent}]));
    nodes.forEach(n=>{if(n.parent!==null)nodes.get(n.parent).children.push(n);});
    const root=nodes.get(segment.focal.mrca),order=segment.order.filter(n=>keep.has(n.id)).map(n=>nodes.get(n.id));
    return {...segment,nodes,root,order,tips:order.filter(n=>!n.children.length),start:root.t,end:Math.max(...order.filter(n=>!n.children.length).map(n=>n.t)),
      histories:segment.histories.map(h=>({...h,root_state:h.nodeStates.get(root.id)})),pieceCache:new Map()};
  }
  function linearQuantile(a,p){const x=(a.length-1)*p,i=Math.floor(x);return a[i]+(a[Math.min(i+1,a.length-1)]-a[i])*(x-i);}
  function summarize(segment,time,target,historyIndex=null) {
    const draws=historyIndex===null?segment.histories:[segment.histories[historyIndex]];
    const counts=draws.map(h=>upperBound(h.incoming.get(target)||[],time));
    const sorted=counts.slice().sort((a,b)=>a-b), histogram=new Map();
    counts.forEach(n=>histogram.set(n,(histogram.get(n)||0)+1));
    return {mean:counts.reduce((a,b)=>a+b,0)/counts.length,low:(segment.focal?linearQuantile:quantile)(sorted,.025),high:(segment.focal?linearQuantile:quantile)(sorted,.975),counts,histogram};
  }
  function stateAt(segment,h,node,time) {
    if(node.parent===null)return h.root_state;
    const jumps=h.byBranch.get(node.id)||[];
    let state=h.nodeStates.get(node.parent);
    for(const j of jumps) {if(j.t>time)break;state=j.to;} return state;
  }
  function probabilities(segment,node,time,historyIndex=null) {
    const hs=historyIndex===null?segment.histories:[segment.histories[historyIndex]], counts=new Map();
    for(const h of hs) {const k=stateAt(segment,h,node,time);counts.set(k,(counts.get(k)||0)+1);}
    return [...counts].map(([id,n])=>({id,p:n/hs.length})).sort((a,b)=>b.p-a.p);
  }
  function branchPieces(segment,node,historyIndex=null) {
    if(node.parent===null)return [];
    if(historyIndex!==null){const h=segment.histories[historyIndex];return [{t:segment.nodes.get(node.parent).t,state:h.nodeStates.get(node.parent),p:1},...(h.byBranch.get(node.id)||[]).map(j=>({t:j.t,state:j.to,p:1}))];}
    segment.pieceCache ||= new Map();if(segment.pieceCache.has(node.id))return segment.pieceCache.get(node.id);
    const counts=new Map(),events=[];
    for(const h of segment.histories){const state=h.nodeStates.get(node.parent);counts.set(state,(counts.get(state)||0)+1);events.push(...(h.byBranch.get(node.id)||[]));}
    events.sort((a,b)=>a.t-b.t);
    const best=t=>{const [state,n]=[...counts].sort((a,b)=>b[1]-a[1])[0];return {t,state,p:n/segment.histories.length};};
    const result=[best(segment.nodes.get(node.parent).t)];
    for(let i=0;i<events.length;){const t=events[i].t;while(i<events.length&&events[i].t===t){const j=events[i++];counts.set(j.from,counts.get(j.from)-1);counts.set(j.to,(counts.get(j.to)||0)+1);}result.push(best(t));}
    segment.pieceCache.set(node.id,result);return result;
  }
  function routes(segment,time,historyIndex=null) {
    const hs=historyIndex===null?segment.histories:[segment.histories[historyIndex]], result=new Map();
    for(const h of hs) for(const j of h.jumps) {
      if(j.t>time)break;
      if(segment.focal&&!segment.focal.branches.has(j.branch))continue;
      const key=JSON.stringify([j.from,j.to]);
      if(!result.has(key))result.set(key,{from:j.from,to:j.to,n:0,branches:new Set()});
      const r=result.get(key); r.n+=1/hs.length;r.branches.add(j.branch);
    }
    return [...result.values()].sort((a,b)=>b.n-a.n);
  }
  function exampleData() {
    const date=n=>iso(Date.UTC(2025,0,1)+n*DAY);
    const nodes=[{id:'root',parent:null,date:date(0)},
      {id:'north',parent:'root',date:date(45)}, {id:'midwest',parent:'root',date:date(40)},
      {id:'ky',parent:'midwest',date:date(90)}, {id:'tn',parent:'midwest',date:date(100)},
      {id:'a',parent:'north',date:date(110),label:'Example ON-01',observed_state:'ON'},
      {id:'b',parent:'north',date:date(145),label:'Example OH-01',observed_state:'OH'},
      {id:'c',parent:'ky',date:date(165),label:'Example KY-01',observed_state:'KY'},
      {id:'d',parent:'ky',date:date(190),label:'Example KY-02',observed_state:'KY'},
      {id:'e',parent:'tn',date:date(170),label:'Example TN-01',observed_state:'TN'},
      {id:'f',parent:'tn',date:date(220),label:'Example KY-03',observed_state:'KY'}];
    const segment=id=>({id,nodes:JSON.parse(JSON.stringify(nodes)),histories:Array.from({length:40},(_,i)=>{
      const j=(branch,n,from,to)=>({branch,date:date(n),from,to});
      const jump=[j('midwest',15+i%20,'ON','OH'),j('b',65+i%45,'ON','OH'),j('tn',65+i%25,'OH','TN'),j('f',180+i%30,'TN','KY')];
      if(id==='HA' || i%3)jump.push(j('ky',55+i%30,'OH','KY'));
      else jump.push(j('c',120+i%30,'OH','KY'),j('d',145+i%35,'OH','KY'));
      if(i%4===0)jump.push(j('d',170,'KY','OH'),j('d',180,'OH','KY'));
      return {id:'draw-'+(i+1),root_state:'ON',jumps:jump};
    })});
    return {schema:SCHEMA,title:'Illustrative phylogeographic histories',synthetic:true,
      provenance:{method:'Constructed demonstration histories; no WINGS analysis',inference:'synthetic',uncertainty:'conditional-on-fixed-tree'},
      locations:[{id:'ON',label:'Ontario',lat:44.8,lon:-80.5},{id:'OH',label:'Ohio',lat:40.4,lon:-82.8},{id:'KY',label:'Kentucky',lat:37.7,lon:-85.3},{id:'TN',label:'Tennessee',lat:35.8,lon:-86.3}],segments:[segment('HA'),segment('NA')]};
  }
  const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  function mount(explorer,container,options={}) {
    const wrap=make('section','wpm'); container.append(wrap);
    const header=make('div','wpm-head'),heading=make('div');
    heading.append(make('div','wpm-kicker','Ancestral locations · Markov jumps'),make('h3','','Phylogeography movie'));
    const importLabel=make('label','wpm-import','Load reconstruction');
    const file=make('input');file.type='file';file.accept='.json,application/json';file.setAttribute('aria-label','Load phylogeographic reconstruction JSON');importLabel.append(file);
    header.append(heading,importLabel);wrap.append(header);
    if(explorer?.payload?.phylodynamics){
      const link=make('a','wpm-import','Compare reference replicates');
      link.href='phylodynamics/comparison.html';link.target='_blank';link.rel='noopener';header.append(link);
    }
    if(options.embedded)importLabel.hidden=true;
    const status=make('p','wpm-status');status.setAttribute('role','status');
    const empty=make('div','wpm-empty');empty.append(make('h4','','No reconstruction loaded'),make('p','','Load dated trees and posterior migration histories to play their inferred geographic history.'));
    const example=make('button','wpm-primary','Try illustrative example');example.type='button';empty.append(example);
    const body=make('div','wpm-body');body.hidden=true;
    const controls=make('div','wpm-controls');
    const select=(label,cls)=>{const l=make('label','wpm-control'),s=make('select',cls);s.setAttribute('aria-label',label);l.append(make('span','',label),s);controls.append(l);return s;};
    const segmentControl=select('Segment','wpm-segment'),targetControl=select('Introductions into','wpm-target'),modeControl=select('View','wpm-mode'),drawControl=select('History','wpm-draw');
    const windowControl=select('Tree / time window','wpm-window');
    const addOption=(s,label,value)=>s.append(new Option(label,String(value)));
    addOption(windowControl,'Study ancestry','study');addOption(windowControl,'Full reference tree','full');
    addOption(modeControl,'Posterior summary','summary');addOption(modeControl,'Sampled history','history');
    const restore=make('button','wpm-secondary','Close example');restore.type='button';controls.append(restore);
    const stage=make('div','wpm-stage'),canvas=make('canvas','wpm-canvas');canvas.width=1440;canvas.height=900;canvas.setAttribute('role','img');canvas.setAttribute('aria-label','Animated geographic transitions, dated tree and introduction count distribution');stage.append(canvas);
    const player=make('div','wpm-player'),play=make('button','wpm-primary','Play'),reset=make('button','wpm-secondary','Restart');play.type=reset.type='button';
    const slider=make('input','wpm-slider');slider.type='range';slider.min='0';slider.max='1000';slider.step='1';slider.value='0';slider.setAttribute('aria-label','Movie date');
    const dateText=make('output','wpm-date'),speed=make('select','wpm-speed');speed.setAttribute('aria-label','Playback speed');[['0.5×',.5],['1×',1],['2×',2],['4×',4]].forEach(([l,v])=>addOption(speed,l,v));speed.value='1';
    const record=make('button','wpm-secondary','Export video');record.type='button';
    player.append(play,reset,slider,dateText,speed,record);
    const details=make('details','wpm-details'),summary=make('summary','','Inspect nodes and transitions'),inspect=make('div','wpm-inspect');details.append(summary,inspect);
    const nodeLabel=make('label','wpm-control'),nodeControl=make('select');nodeControl.setAttribute('aria-label','Inspect tree node');nodeLabel.append(make('span','','Tree node'),nodeControl);
    const nodeInfo=make('p','wpm-node-info');const routeTable=make('table','wpm-route-table');inspect.append(nodeLabel,nodeInfo,routeTable);
    const note=make('p','wpm-note','Arrows connect geographic states; they do not trace bird flight paths. Counts describe transitions in sampled ancestry.');
    body.append(controls,stage,player,details,note);wrap.append(status,empty,body);
    let model=null,raw=null,seg=null,time=0,mode='summary',drawIndex=0,target='',nodeId='',frame=0,last=0,playing=false,active=true,recording=false,destroyed=false,hitNodes=[],treePage=0,selectedRoute=null;
    const ctx=canvas.getContext('2d');let N=20;
    const hi=()=>mode==='history'?drawIndex:null;
    const current=()=>summarize(seg,time,target,hi());
    function stop(){playing=false;cancelAnimationFrame(frame);frame=0;last=0;play.textContent='Play';play.setAttribute('aria-pressed','false');}
    function load(data){
      // Older embedded summaries already contain the declared focal IDs.
      if(explorer?.payload?.phylodynamics&&!data.synthetic){
        const meta=explorer.payload.phylodynamics;
        data={...data,segments:data.segments.map(s=>{const r=meta.analyses?.find(r=>r.segment===s.id&&meta.primary_analyses?.includes(r.id));return r?.focal_sample_ids?{...s,focal_sample_ids:r.focal_sample_ids}:s;})};
      }
      const next=validate(data); stop();raw=data;model=next;segmentControl.replaceChildren();targetControl.replaceChildren();
      next.segments.forEach(s=>addOption(segmentControl,s.id,s.id));next.states.forEach(s=>addOption(targetControl,s.label,s.id));
      target=next.states.has('USA:KY')?'USA:KY':next.states.has('KY')?'KY':next.states.keys().next().value;targetControl.value=target;mode='summary';modeControl.value=mode;
      modeControl.options[0].textContent=data.synthetic?'Illustrative summary':data.provenance.inference==='bayesian'?'Posterior summary':'Conditional mapping summary';
      body.hidden=false;empty.hidden=true;restore.hidden=!data.synthetic;
      status.textContent=data.synthetic?'ILLUSTRATIVE EXAMPLE · Synthetic histories, not WINGS findings.':`${data.title} · ${data.provenance.method}`;
      status.classList.toggle('wpm-synthetic',data.synthetic);windowControl.value='study';changeSegment();
    }
    function changeSegment(){stop();seg=model.segments.find(s=>s.id===segmentControl.value)||model.segments[0];windowControl.disabled=!seg.focal;if(seg.focal&&windowControl.value==='study')seg=studyView(seg);N=seg.focal&&windowControl.value==='study'?Math.max(20,Math.min(40,seg.tips.length)):20;time=seg.start;treePage=0;nodeId=seg.root.id;selectedRoute=null;drawIndex=0;drawControl.replaceChildren();seg.histories.forEach((h,i)=>addOption(drawControl,h.id,i));nodeControl.replaceChildren();seg.order.forEach(n=>addOption(nodeControl,n.label||n.sample_id||n.id,n.id));nodeControl.value=nodeId;render();}
    function setTime(t){time=Math.max(seg.start,Math.min(seg.end,t));render();}
    function tick(now){if(!playing||!active||destroyed)return;if(last)time=Math.min(seg.end,time+(now-last)*(seg.end-seg.start)/20000*Number(speed.value));last=now;render();if(time>=seg.end)stop();else frame=requestAnimationFrame(tick);}
    function start(){if(!model)return;if(time>=seg.end)time=seg.start;playing=true;last=0;play.textContent='Pause';play.setAttribute('aria-pressed','true');frame=requestAnimationFrame(tick);}
    function text(str,x,y,size=18,color='#263C46',bold=false){ctx.font=`${bold?'600':'400'} ${size}px Arial, sans-serif`;ctx.fillStyle=color;ctx.fillText(str,x,y);}
    function line(x1,y1,x2,y2,color='#DCE4E7',width=1){ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();}
    function circle(x,y,r,fill,stroke=null){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=fill;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=2;ctx.stroke();}}
    function clipped(str,n){return str.length>n?str.slice(0,n-1)+'…':str;}
    function renderMap(){
      const box={x:32,y:166,w:810,h:430};
      const threshold=mode==='summary'?.1:0;
      seg.mapStates ||= new Map();const mapKey=String(hi());
      if(!seg.mapStates.has(mapKey)){
        const visible=new Set(seg.tips.filter(n=>!seg.focal||n.sample_id).map(n=>n.observed_state));
        routes(seg,seg.end,hi()).filter(r=>r.n>=threshold).forEach(r=>{visible.add(r.from);visible.add(r.to);});
        const root=probabilities(seg,seg.root,seg.start,hi())[0];if(root)visible.add(root.id);
        seg.mapStates.set(mapKey,visible);
      }
      const visible=seg.mapStates.get(mapKey),states=[...model.states.values()].filter(s=>visible.has(s.id)||s.id===target);
      ctx.fillStyle='#F4F7F7';ctx.fillRect(box.x,box.y,box.w,box.h);
      let xmin=Math.min(...states.map(s=>s.lon)),xmax=Math.max(...states.map(s=>s.lon)),ymin=Math.min(...states.map(s=>s.lat)),ymax=Math.max(...states.map(s=>s.lat));
      const dx=Math.max(4,xmax-xmin),dy=Math.max(4,ymax-ymin);xmin-=dx*.3;xmax+=dx*.3;ymin=Math.max(-90,ymin-dy*.3);ymax=Math.min(90,ymax+dy*.3);
      const cos=Math.max(.15,Math.cos((ymin+ymax)/2*Math.PI/180)),scale=Math.min(box.w/((xmax-xmin)*cos),box.h/(ymax-ymin));
      const mx=(xmin+xmax)/2,my=(ymin+ymax)/2;
      const project=(lon,lat)=>[box.x+box.w/2+(lon-mx)*cos*scale,box.y+box.h/2-(lat-my)*scale];
      ctx.save();ctx.beginPath();ctx.rect(box.x,box.y,box.w,box.h);ctx.clip();
      const bounds=options.boundaries||globalThis.WINGS_MAP_BOUNDARIES;
      for(const region of bounds?.regions||[]) {
        ctx.beginPath();for(const polygon of region.polygons||[])for(const ring of polygon){ring.forEach(([lon,lat],i)=>{const p=project(lon,lat);if(i===0)ctx.moveTo(...p);else ctx.lineTo(...p);});ctx.closePath();}
        ctx.fillStyle='#E7EEED';ctx.fill('evenodd');ctx.strokeStyle='#BCCECE';ctx.lineWidth=.7;ctx.stroke();
      }
      if(!bounds) {for(let f=0;f<5;f++){line(box.x+f*box.w/4,box.y,box.x+f*box.w/4,box.y+box.h);line(box.x,box.y+f*box.h/4,box.x+box.w,box.y+f*box.h/4);}}
      const rs=routes(seg,time,hi()).filter(r=>r.n>=threshold);
      for(const r of rs){
        const a=model.states.get(r.from),b=model.states.get(r.to),p=project(a.lon,a.lat),q=project(b.lon,b.lat),vx=q[0]-p[0],vy=q[1]-p[1],len=Math.hypot(vx,vy);
        if(len<1)continue;
        const bend=Math.min(60,len*.24),cx=(p[0]+q[0])/2-vy/len*bend,cy=(p[1]+q[1])/2+vx/len*bend;
        ctx.beginPath();ctx.moveTo(...p);ctx.quadraticCurveTo(cx,cy,...q);ctx.strokeStyle=selectedRoute&&selectedRoute.from===r.from&&selectedRoute.to===r.to?'#000000':a.color;ctx.globalAlpha=.72;ctx.lineWidth=Math.min(11,1.5+Math.sqrt(r.n)*3);ctx.stroke();ctx.globalAlpha=1;
        const u=.78,ax=(1-u)**2*p[0]+2*(1-u)*u*cx+u*u*q[0],ay=(1-u)**2*p[1]+2*(1-u)*u*cy+u*u*q[1],angle=Math.atan2((1-u)*(cy-p[1])+u*(q[1]-cy),(1-u)*(cx-p[0])+u*(q[0]-cx));
        ctx.save();ctx.translate(ax,ay);ctx.rotate(angle);ctx.beginPath();ctx.moveTo(9,0);ctx.lineTo(-7,-6);ctx.lineTo(-7,6);ctx.closePath();ctx.fillStyle=a.color;ctx.fill();ctx.restore();
      }
      for(const s of states){const p=project(s.lon,s.lat),collected=seg.tips.filter(n=>n.t<=time&&n.observed_state===s.id).length;
        if(target===s.id)circle(...p,17,'#FFC627');circle(...p,8,s.color,'#FFFFFF');
        text(s.label,p[0]+15,p[1]-10,16,'#263C46',true);if(collected)text(`${collected} collected`,p[0]+15,p[1]+11,13,'#526A72');
      }
      ctx.restore();text('Geographic states · arrow width = cumulative '+(mode==='summary'?'expected ':'')+'jumps',32,622,14,'#526A72');
      text(mode==='summary'?'Routes with ≥0.1 expected jumps shown; all counts retained. Basemap: Natural Earth':bounds?'Basemap: Natural Earth':'Geographic coordinate view · no basemap loaded',32,643,12,'#637A80');
    }
    function renderTree(){
      const x=894,y=170,w=270,h=400;
      const tips=seg.tips.slice(treePage*N,(treePage+1)*N),keep=new Set();tips.forEach(n=>{while(n){keep.add(n.id);n=seg.nodes.get(n.parent);}});
      const ypos=new Map(tips.map((n,i)=>[n.id,y+24+i*h/Math.max(1,tips.length-1)]));
      for(const n of seg.order.slice().reverse())if(keep.has(n.id)&&!ypos.has(n.id)){const a=n.children.filter(c=>keep.has(c.id)).map(c=>ypos.get(c.id));ypos.set(n.id,a.reduce((s,v)=>s+v,0)/a.length);}
      const tx=t=>x+(t-seg.start)/(seg.end-seg.start)*w;
      hitNodes=[];
      for(const n of seg.order){if(!keep.has(n.id))continue;const ny=ypos.get(n.id),nx=tx(n.t),p=seg.nodes.get(n.parent),probs=probabilities(seg,n,Math.min(n.t,time),hi()),best=probs[0],color=model.states.get(best.id).color;
        if(p){const py=ypos.get(p.id),px=tx(p.t);line(px,py,px,ny,'#DCE4E7',1.5);line(px,ny,nx,ny,'#DCE4E7',1.5);
          if(time>=p.t){const highlighted=selectedRoute?.branches.has(n.id),pieces=branchPieces(seg,n,hi());
            const parent=pieces[0];ctx.globalAlpha=.25+.75*parent.p;line(px,py,px,ny,model.states.get(parent.state).color,2);
            pieces.forEach((part,i)=>{const end=Math.min(pieces[i+1]?.t??n.t,time);if(end<=part.t)return;ctx.globalAlpha=.25+.75*part.p;line(tx(part.t),ny,tx(end),ny,highlighted?'#000':model.states.get(part.state).color,highlighted?5:3);});ctx.globalAlpha=1;
          }
        }
        if(n.t<=time){circle(nx,ny,n.id===nodeId?7:4.5,color,n.id===nodeId?'#FFC627':null);hitNodes.push({id:n.id,x:nx,y:ny});}
        if(!n.children.length)text(n.sample_id||clipped(n.label||n.id,25),nx+10,ny+4,n.sample_id?11:12,n.t<=time?'#263C46':'#8B9A9E',Boolean(n.sample_id));
      }
      line(tx(time),y-5,tx(time),y+h+35,'#8C1D40',1);
      text(iso(seg.start),x,622,13,'#526A72');text(iso(seg.end),x+w-65,622,13,'#526A72');
      text(`${seg.id} · ${seg.tips.length} tips · ${seg.root.id===seg.focal?.mrca?'WINGS ancestry':'full reference tree'}`,x,643,12,'#526A72');
      if(seg.focal&&seg.root.id===seg.focal.mrca)text('WINGS common ancestor · '+labelDate(seg.start),x,664,12,'#8C1D40',true);
      if(seg.tips.length>N)text(`Showing tips ${treePage*N+1}–${Math.min((treePage+1)*N,seg.tips.length)}; choose a node to navigate`,x,664,11,'#526A72');
    }
    function renderBottom(stats){
      line(32,690,1408,690);text(seg.focal?'STUDY-ANCESTRY ENTRIES THROUGH TIME':'ALL-TREE ENTRIES THROUGH TIME',32,720,14,'#8C1D40',true);
      const bx=32,by=750,bw=810,bh=90,steps=60;
      seg.curveCache ||= new Map();const key=target+':'+hi();if(!seg.curveCache.has(key))seg.curveCache.set(key,Array.from({length:steps+1},(_,i)=>summarize(seg,seg.start+(seg.end-seg.start)*i/steps,target,hi())));const values=seg.curveCache.get(key);
      const max=Math.max(1,...values.map(s=>s.high));
      ctx.beginPath();values.forEach((s,i)=>{const x=bx+i*bw/steps,y=by+bh-s.high/max*bh;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});values.slice().reverse().forEach((s,i)=>ctx.lineTo(bx+(steps-i)*bw/steps,by+bh-s.low/max*bh));ctx.closePath();ctx.fillStyle='#F0DDE3';ctx.fill();
      ctx.beginPath();values.forEach((s,i)=>{const x=bx+i*bw/steps,y=by+bh-s.mean/max*bh;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.strokeStyle='#8C1D40';ctx.lineWidth=3;ctx.stroke();
      const px=bx+(time-seg.start)/(seg.end-seg.start)*bw;line(px,by-4,px,by+bh,'#263C46',1);circle(px,by+bh-stats.mean/max*bh,5,'#FFC627','#8C1D40');
      text('0',bx,by+bh+17,12,'#637A80');text(String(max),bx,by-8,12,'#637A80');text('Calendar time',bx+bw-95,by+bh+17,12,'#637A80');
      text(mode==='summary'?'COUNT DISTRIBUTION · CURRENT DATE':'COUNT · SELECTED HISTORY',894,720,14,'#8C1D40',true);
      const bins=[...stats.histogram].sort((a,b)=>a[0]-b[0]),wid=Math.min(80,450/bins.length),den=stats.counts.length;
      bins.forEach(([count,n],i)=>{const height=n/den*75,x=914+i*wid;ctx.fillStyle='#8C1D40';ctx.fillRect(x,840-height,wid*.65,height);text(String(count),x,858,13);if(bins.length<12)text(Math.round(n/den*100)+'%',x,832-height,12,'#637A80');});
    }
    function render(){
      if(!model||destroyed)return;
      drawControl.parentElement.hidden=mode!=='history';
      slider.value=String(Math.round(1000*(time-seg.start)/(seg.end-seg.start)));slider.setAttribute('aria-valuetext',labelDate(time));dateText.textContent=labelDate(time);
      const stats=current();ctx.clearRect(0,0,1440,900);ctx.fillStyle='#FFFFFF';ctx.fillRect(0,0,1440,900);ctx.fillStyle='#8C1D40';ctx.fillRect(0,0,1440,8);
      text('WINGS / PHYLOGEOGRAPHY',32,43,14,'#8C1D40',true);
      text(`${seg.id} · Introductions into ${model.states.get(target).label}`,32,84,29,'#263C46',true);
      const label=raw.synthetic?'SYNTHETIC EXAMPLE · NOT WINGS FINDINGS':raw.provenance.inference==='empirical-bayes'?'CONDITIONAL ON TREE AND FITTED RATES':'POSTERIOR CONDITIONAL ON FIXED TREE';
      text(label,32,113,13,raw.synthetic?'#8C1D40':'#526A72',true);
      text(labelDate(time),1050,47,24,'#263C46',true);
      text((mode==='summary'?stats.mean.toFixed(1):String(stats.mean))+(mode==='summary'?' expected entries':' introductions'),1050,84,24,'#8C1D40',true);
      const interval=raw.synthetic?'illustrative interval':raw.provenance.inference==='bayesian'?'credible interval':'mapping interval';
      text(mode==='summary'?`95% ${interval}: ${stats.low}–${stats.high}`:`${seg.histories[drawIndex].id} · one sampled history`,1050,111,14,'#526A72');
      text('GEOGRAPHIC HISTORY',32,150,14,'#526A72',true);text(seg.root.id===seg.focal?.mrca?'DATED WINGS SAMPLE TREE':'DATED REFERENCE TREE',894,150,14,'#526A72',true);
      renderMap();renderTree();renderBottom(stats);
      text(seg.focal?'Entries on study ancestry only; ancestral stem excluded. Full-tree context does not change the count.':'All-tree geographic transitions; not observed flight paths. Each segment is shown separately.',32,884,12,'#637A80');
      if(details.open)renderDetails();
      canvas.setAttribute('aria-label',`${raw.synthetic?'Synthetic example. ':''}${seg.id}, ${labelDate(time)}. ${stats.mean.toFixed(1)} ${mode==='summary'?'expected ':''}introductions into ${model.states.get(target).label}; ${mode==='summary'?`95% ${interval} ${stats.low} to ${stats.high}.`:seg.histories[drawIndex].id}`);
    }
    function selectNode(id){nodeId=id;nodeControl.value=id;const node=seg.nodes.get(id);const index=seg.tips.findIndex(n=>n.id===id);if(index>=0)treePage=Math.floor(index/N);time=Math.max(time,node.t);selectedRoute=null;render();if(node.sample_id&&explorer?.sampleById?.has(node.sample_id))explorer.selectSample?.(node.sample_id);}
    function renderDetails(){
      const node=seg.nodes.get(nodeId),p=probabilities(seg,node,node.t,hi());
      nodeInfo.textContent=`${node.label||node.sample_id||node.id} · ${labelDate(node.t)} · `+p.map(s=>`${model.states.get(s.id).label} ${(100*s.p).toFixed(1)}%`).join(' · ');
      routeTable.replaceChildren();const head=make('thead'),hr=make('tr');['From','To',mode==='summary'?'Expected jumps':'Jumps','Branches'].forEach(s=>hr.append(make('th','',s)));head.append(hr);routeTable.append(head);const tbody=make('tbody');
      for(const r of routes(seg,time,hi())){const row=make('tr');row.append(make('td','',model.states.get(r.from).label),make('td','',model.states.get(r.to).label),make('td','',r.n.toFixed(mode==='summary'?2:0)));const cell=make('td'),b=make('button','wpm-link','Highlight');b.type='button';b.addEventListener('click',()=>{selectedRoute=r;render();});cell.append(b);row.append(cell);tbody.append(row);}routeTable.append(tbody);
    }
    windowControl.addEventListener('change',changeSegment);
    segmentControl.addEventListener('change',changeSegment);targetControl.addEventListener('change',()=>{target=targetControl.value;render();});
    modeControl.addEventListener('change',()=>{mode=modeControl.value;selectedRoute=null;render();});drawControl.addEventListener('change',()=>{drawIndex=Number(drawControl.value);render();});
    nodeControl.addEventListener('change',()=>selectNode(nodeControl.value));details.addEventListener('toggle',()=>{if(details.open&&model)renderDetails();});
    canvas.addEventListener('click',e=>{if(!model||recording)return;const b=canvas.getBoundingClientRect(),x=(e.clientX-b.left)*canvas.width/b.width,y=(e.clientY-b.top)*canvas.height/b.height;const near=hitNodes.find(n=>Math.hypot(n.x-x,n.y-y)<13);if(near){details.open=true;selectNode(near.id);}});
    play.addEventListener('click',()=>playing?stop():start());reset.addEventListener('click',()=>{stop();setTime(seg.start);});slider.addEventListener('input',()=>{stop();setTime(seg.start+Number(slider.value)/1000*(seg.end-seg.start));});
    example.addEventListener('click',()=>load(exampleData()));
    restore.addEventListener('click',()=>{stop();if(explorer?.payload?.phylogeography)load(explorer.payload.phylogeography);else {model=null;raw=null;body.hidden=true;empty.hidden=false;status.textContent='';status.classList.remove('wpm-synthetic');}});
    file.addEventListener('change',async()=>{const f=file.files?.[0];if(!f)return;try{if(f.size>128*1024*1024)fail('Reconstruction exceeds 128 MB.');load(JSON.parse(await f.text()));}catch(e){status.textContent='Could not load reconstruction: '+e.message;}finally{file.value='';}});
    const supported=()=>typeof MediaRecorder!=='undefined'&&typeof canvas.captureStream==='function';
    if(!supported()){record.disabled=true;record.title='Use scripts/render_phylogeography_movie.cjs to export MP4.';}
    let recorder=null,stream=null;
    function unlock(){recording=false;controls.querySelectorAll('select,button').forEach(n=>n.disabled=false);[play,reset,slider,speed,file].forEach(n=>n.disabled=false);record.textContent='Export video';record.disabled=!supported();}
    record.addEventListener('click',()=>{
      if(recording){recorder?.stop();return;}if(!model||!supported())return;
      const mime=['video/mp4;codecs=avc1.42001E','video/mp4','video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'].find(m=>MediaRecorder.isTypeSupported(m));
      if(!mime){status.textContent='Video recording is unavailable in this browser. Use the MP4 export script.';return;}
      const oldTime=time,oldSpeed=speed.value;stop();recording=true;controls.querySelectorAll('select,button').forEach(n=>n.disabled=true);[play,reset,slider,speed,file].forEach(n=>n.disabled=true);record.textContent='Stop export';
      try{stream=canvas.captureStream(30);recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:5000000});const chunks=[];
        recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
        recorder.onerror=()=>{status.textContent='Video export failed. Use the MP4 export script.';};
        recorder.onstop=()=>{stop();stream.getTracks().forEach(t=>t.stop());const blob=new Blob(chunks,{type:mime});if(blob.size){const url=URL.createObjectURL(blob),a=make('a');a.href=url;a.download='wings-'+seg.id.replace(/[^a-z0-9_-]/gi,'_')+(raw.synthetic?'-illustrative':'')+(mime.startsWith('video/mp4')?'.mp4':'.webm');a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}unlock();speed.value=oldSpeed;setTime(oldTime);};
        recorder.start();speed.value='1';time=seg.start;start();
        const endCheck=()=>{if(!recording)return;if(!playing){if(recorder.state!=='inactive')recorder.stop();}else setTimeout(endCheck,150);};setTimeout(endCheck,150);
      }catch(e){stop();stream?.getTracks().forEach(t=>t.stop());unlock();speed.value=oldSpeed;setTime(oldTime);status.textContent='Video export failed: '+e.message;}
    });
    function visibility(){if(document.hidden){stop();if(recording&&recorder?.state!=='inactive')recorder.stop();}}
    document.addEventListener('visibilitychange',visibility);
    const api={load,setTime,setSegment:id=>{segmentControl.value=id;changeSegment();},setTarget:id=>{if(!model?.states.has(id))fail('Unknown focal state.');target=id;targetControl.value=id;render();},setMode:(value,index=0)=>{if(!['summary','history'].includes(value)||!Number.isInteger(index)||index<0||index>=seg.histories.length)fail('Invalid view or history index.');mode=value;drawIndex=index;modeControl.value=value;drawControl.value=String(index);render();},
      setWindow:value=>{if(!['study','full'].includes(value))fail('Unknown tree window.');windowControl.value=value;changeSegment();},
      setActive:value=>{active=value;if(!value){stop();if(recording&&recorder?.state!=='inactive')recorder.stop();}},
      destroy:()=>{stop();destroyed=true;document.removeEventListener('visibilitychange',visibility);stream?.getTracks().forEach(t=>t.stop());wrap.remove();},
      canvas,get range(){return seg?{start:seg.start,end:seg.end}:null;},get state(){return {segment:seg?.id,time,mode,target,playing,synthetic:raw?.synthetic};},get data(){return raw;}};
    const initial=options.data||explorer?.payload?.phylogeography;
    if(initial)try{load(initial);}catch(e){status.textContent='Could not load reconstruction: '+e.message;}
    return api;
  }
  const api={SCHEMA,validate,studyView,summarize,probabilities,branchPieces,routes,exampleData,mount};
  globalThis.WINGS_PHYLOGEOGRAPHY_MOVIE=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})();
