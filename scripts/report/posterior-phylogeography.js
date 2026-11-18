/* Offline posterior viewer. Every displayed history uses its own sampled dates. */
(function (global) {
  'use strict';
  const stamp = x => { const v=Date.parse(x); if(!Number.isFinite(v)) throw Error('Invalid date'); return v; };
  const quantile = (xs,p) => {const a=xs.slice().sort((x,y)=>x-y);return a[Math.max(0,Math.ceil(p*a.length)-1)];};
  function validate(data) {
    if(!data||data.schema!=='wings.posterior-movie.v1'||data.status!=='passed'||!Array.isArray(data.draws)||!data.draws.length) throw Error('A passing posterior publication is required');
    const loc=new Set(data.locations.map(x=>x.id));
    if(loc.size!==data.locations.length) throw Error('Duplicate locations');
    const counts=new Map(),seen=new Set();
    data.draws.forEach(d=>{
      const key=d.chain+':'+d.state;if(seen.has(key))throw Error('Repeated tree draw');seen.add(key);counts.set(d.chain,(counts.get(d.chain)||0)+1);
      const by=new Map(d.nodes.map(n=>[n.id,n]));if(by.size!==d.nodes.length)throw Error('Duplicate nodes');
      const roots=d.nodes.filter(n=>n.parent===null);if(roots.length!==1||roots[0].id!==d.focal_mrca)throw Error('Missing WINGS ancestor');
      if(!loc.has(d.history.root_state))throw Error('Unknown state');
      d.nodes.forEach(n=>{stamp(n.date);if(n.parent!==null&&(!by.has(n.parent)||stamp(by.get(n.parent).date)>stamp(n.date)))throw Error('Invalid dated branch');});
      const visited=new Set(),active=new Set();
      function walk(id){if(active.has(id))throw Error('Cycle');if(visited.has(id))return;active.add(id);d.nodes.filter(n=>n.parent===id).forEach(n=>walk(n.id));active.delete(id);visited.add(id);}
      walk(roots[0].id);if(visited.size!==by.size)throw Error('Disconnected ancestry');
      const observed=d.nodes.filter(n=>n.sample_id).map(n=>n.sample_id).sort();
      if(JSON.stringify(observed)!==JSON.stringify(data.focal_sample_ids.slice().sort()))throw Error('Missing WINGS samples');
      d.history.jumps.forEach(j=>{const n=by.get(j.branch);if(!n||n.parent===null||!loc.has(j.from)||!loc.has(j.to)||j.from===j.to||stamp(j.date)<=stamp(by.get(n.parent).date)||stamp(j.date)>stamp(n.date))throw Error('Invalid mapped event');});
    });
    if(counts.size<2||new Set(counts.values()).size!==1)throw Error('Unequal posterior chain weights');
    return data;
  }
  function cumulative(data,target,times){
    const rows=times.map(()=>[]);
    data.draws.forEach(d=>{
      const events=d.history.jumps.filter(j=>j.to===target).map(j=>stamp(j.date)).sort((a,b)=>a-b);let n=0;
      times.forEach((t,i)=>{while(n<events.length&&events[n]<=t)n++;rows[i].push(n);});
    });
    return rows.map((a,i)=>({time:times[i],mean:a.reduce((s,x)=>s+x,0)/a.length,low:quantile(a,.025),high:quantile(a,.975)}));
  }
  function statesAt(d,t){
    const children=new Map(d.nodes.map(n=>[n.id,[]])),by=new Map(d.nodes.map(n=>[n.id,n]));
    d.nodes.forEach(n=>{if(n.parent!==null)children.get(n.parent).push(n.id);});
    const ends={},active=[];const root=d.nodes.find(n=>n.parent===null);
    function visit(id,start){
      const n=by.get(id),p=n.parent===null?null:by.get(n.parent);let end=start,at=start;
      const events=d.history.jumps.filter(j=>j.branch===id).sort((a,b)=>stamp(a.date)-stamp(b.date));
      events.forEach(j=>{if(j.from!==end)throw Error('Broken history');end=j.to;if(stamp(j.date)<=t)at=j.to;});ends[id]=end;
      if(p&&stamp(p.date)<=t&&t<stamp(n.date))active.push({id,state:at});
      if(!children.get(id).length&&stamp(n.date)<=t&&t-stamp(n.date)<86400000*30)active.push({id,state:end,sample:true});
      children.get(id).forEach(k=>visit(k,end));
    }
    visit(root.id,d.history.root_state);
    if(t===stamp(root.date))active.push({id:root.id,state:d.history.root_state});
    return {ends,active,by,children};
  }
  const api={validate,cumulative,statesAt};
  if(typeof module==='object'&&module.exports)module.exports=api;
  global.WingsPosteriorMovie=api;
  if(typeof document==='undefined')return;
  const app=document.getElementById('app');if(!app)return;
  try{start(validate(JSON.parse(document.getElementById('posterior-data').textContent)));}catch(e){app.textContent='Movie withheld: '+e.message;}
  function start(data){
    const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const date=t=>new Date(t).toLocaleDateString('en-US',{timeZone:'UTC',year:'numeric',month:'short',day:'numeric'});
    const colors=['#8c1d40','#007d85','#4f689c','#8b783b','#805f98','#c36325','#487d69','#b46985'];
    const location=new Map(data.locations.map((l,i)=>[l.id,{...l,color:colors[i%colors.length]}]));
    let target=(data.locations.find(l=>/Kentucky/i.test(l.label))||data.locations[0]).id,drawIndex=0,playing=false,timer=null;
    const starts=data.draws.map(d=>stamp(d.nodes.find(n=>n.id===d.focal_mrca).date));
    const min=Math.min(...starts),max=Math.max(...data.draws[0].nodes.map(n=>stamp(n.date)));
    let time=max;const times=Array.from({length:161},(_,i)=>min+(max-min)*i/160);let curve=cumulative(data,target,times);
    app.innerHTML=`<header><div><p class="eyebrow">WINGS / POSTERIOR PHYLOGEOGRAPHY</p><h1>The ancestry of your samples</h1><p>${esc(data.analysis)} · ${data.focal_sample_ids.length} WINGS samples · ${data.draws.length.toLocaleString()} dated-tree histories</p></div><span class="passed">Diagnostics passed</span></header>
      <section class="metrics"><article><span>WINGS common ancestor</span><strong>${date(stamp(data.tmrca.median))}</strong><small>95% HPD ${date(stamp(data.tmrca.hpd95[0]))} – ${date(stamp(data.tmrca.hpd95[1]))}</small></article><article><span id="entry-label"></span><strong id="entry-value"></strong><small id="entry-interval"></small></article><article><span>Posterior uncertainty</span><strong>Dates + geography</strong><small>Fixed rooted topology · one reference set</small></article></section>
      <section class="toolbar"><label>Entries into <select id="target">${data.locations.map(l=>`<option value="${esc(l.id)}" ${l.id===target?'selected':''}>${esc(l.label)}</option>`).join('')}</select></label><div class="draw-control"><label for="draw">Sampled history</label><button id="prev" aria-label="Previous history">←</button><input id="draw" aria-label="Sampled history number" type="number" min="1" max="${data.draws.length}" value="1"><button id="next" aria-label="Next history">→</button><span id="chain"></span></div></section>
      <section class="player"><button id="play">Play</button><label class="sr-only" for="time">Calendar time</label><input id="time" type="range" min="0" max="1000" value="1000"><output id="current-date"></output><label>Speed <select id="speed"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></label></section>
      <div class="views"><section class="panel"><h2>Geographic history <span>One posterior draw</span></h2><svg id="map" viewBox="0 0 760 430" role="img" aria-label="Sampled geographic history"></svg><p id="map-caption"></p><div id="legend"></div></section><section class="panel"><h2>WINGS dated ancestry <span>Same posterior draw</span></h2><div class="tree-scroll"><svg id="tree" role="img" aria-label="Dated ancestry showing every WINGS sample"></svg></div><p>Gold tips mark WINGS samples. Reference-only branches and the ancestral stem are excluded.</p></section></div>
      <section class="panel counts"><h2 id="curve-title"></h2><svg id="counts" viewBox="0 0 1200 240" role="img" aria-label="Cumulative entries across the posterior"></svg><p>Line: mean · band: pointwise 95% equal-tailed interval across all dated-tree histories, including zero-event histories.</p></section>
      <details><summary>Model and diagnostics</summary><ul><li>${esc(data.scope)}</li><li>Symmetric equal-rate geographic model; Gamma(${data.prior.rate_prior_shape}, rate ${data.prior.rate_prior_rate}) prior; uniform ancestral-location prior.</li><li>Counts begin at each draw’s WINGS common ancestor. Re-entries count separately; the ancestral stem is excluded.</li><li>A sampled history is one possible reconstruction. Passing diagnostics measures Monte Carlo reliability, not biological model validity.</li></ul><a href="diagnostics.json">Geographic diagnostics</a> · <a href="../gate/diagnostics.json">Dating and internal-node diagnostics</a> · <a href="movie.json" download>Download posterior movie data</a></details>`;
    const el=id=>document.getElementById(id),svgEl=(tag,attrs,text)=>{let n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs||{}).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;};
    function add(svg,tag,attrs,text){const n=svgEl(tag,attrs,text);svg.appendChild(n);return n;}
    const col=s=>location.get(s)?.color||'#71828a';
    function stop(){playing=false;clearInterval(timer);el('play').textContent='Play';}
    function updateMetrics(){const e=data.entries[target];el('entry-label').textContent='Entries into '+location.get(target).label;el('entry-value').textContent=e.mean.toFixed(2);el('entry-interval').textContent=e.constant_sample?'No count variation sampled; inspect boundary bounds in diagnostics':`95% interval ${e.interval95[0]}–${e.interval95[1]} · MCSE ${e.mean_mcse.toFixed(2)}`;}
    function map(d,state){
      const s=el('map');s.replaceChildren();
      const lons=data.locations.map(l=>l.lon),lats=data.locations.map(l=>l.lat);
      // Regional bounding box with a global fallback; no invented travel geometry.
      let x0=Math.max(-180,Math.min(...lons)-12),x1=Math.min(180,Math.max(...lons)+12),y0=Math.max(-85,Math.min(...lats)-9),y1=Math.min(85,Math.max(...lats)+9);
      const project=(lon,lat)=>[35+(lon-x0)/(x1-x0)*690,395-(lat-y0)/(y1-y0)*350];
      add(s,'rect',{x:0,y:0,width:760,height:430,rx:16,fill:'#f5f8f8'});
      for(let lon=Math.ceil(x0/20)*20;lon<=x1;lon+=20){const x=project(lon,y0)[0];add(s,'line',{x1:x,x2:x,y1:35,y2:395,stroke:'#e3eaec'});}
      for(let lat=Math.ceil(y0/10)*10;lat<=y1;lat+=10){const y=project(x0,lat)[1];add(s,'line',{x1:35,x2:725,y1:y,y2:y,stroke:'#e3eaec'});}
      const boundaries=global.WINGS_MAP_BOUNDARIES;
      if(boundaries){const defs=add(s,'defs');const clip=add(defs,'clipPath',{id:'mapClip'});add(clip,'rect',{x:20,y:20,width:720,height:390});const g=add(s,'g',{'clip-path':'url(#mapClip)'});[...(boundaries.countries||[]),...(boundaries.regions||[])].forEach(r=>{(r.polygons||[]).forEach(poly=>{const path=poly.map(ring=>'M'+ring.map(p=>project(p[0],p[1]).join(',')).join('L')+'Z').join('');add(g,'path',{d:path,fill:'#eef2f1',stroke:'#cedbdc','stroke-width':.6});});});}
      const events=d.history.jumps.filter(j=>stamp(j.date)<=time&&time-stamp(j.date)<86400000*60);
      events.forEach(j=>{const a=location.get(j.from),b=location.get(j.to),p=project(a.lon,a.lat),q=project(b.lon,b.lat);add(s,'path',{d:`M${p} Q${(p[0]+q[0])/2},${Math.min(p[1],q[1])-30} ${q}`,fill:'none',stroke:col(j.to),'stroke-width':2,opacity:.65});add(s,'circle',{cx:q[0],cy:q[1],r:5,fill:col(j.to)});});
      const active={};state.active.forEach(a=>active[a.state]=(active[a.state]||0)+1);
      data.locations.forEach(l=>{const p=project(l.lon,l.lat),n=active[l.id]||0;add(s,'circle',{cx:p[0],cy:p[1],r:n?9+Math.min(9,Math.sqrt(n)*2):4,fill:l.id===target?'#ffc627':col(l.id),stroke:'#fff','stroke-width':2,opacity:n?1:.45});if(n)add(s,'text',{x:p[0],y:p[1]+4,'text-anchor':'middle',fill:'#18313b','font-size':12,'font-weight':700},n);const title=svgEl('title',{},l.label+': '+n+' active/recently sampled lineages');s.lastChild.appendChild(title);});
      el('map-caption').textContent=time<stamp(d.nodes.find(n=>n.id===d.focal_mrca).date)?'This draw’s WINGS ancestor has not yet appeared.':`${events.length} mapped changes in the preceding 60 days. Circles show active lineages and samples collected in the preceding 30 days; arcs are state changes, not flight routes.`;
      el('legend').replaceChildren();data.locations.forEach(l=>{let item=document.createElement('span');item.className='legend-item';let dot=document.createElement('i');dot.style.background=col(l.id);item.append(dot,document.createTextNode(l.label));el('legend').appendChild(item);});
    }
    function tree(d,state){
      const s=el('tree');s.replaceChildren();let cursor=34,ys={};const root=d.nodes.find(n=>n.parent===null);
      function layout(id){const children=state.children.get(id);ys[id]=children.length?children.map(layout).reduce((a,b)=>a+b,0)/children.length:(cursor+=27);return ys[id];}layout(root.id);
      s.setAttribute('viewBox',`0 0 820 ${cursor+45}`);s.style.minWidth='700px';s.style.width='100%';s.style.height=(cursor+45)+'px';
      const x=t=>28+(t-min)/(max-min)*465;
      const hpd=data.tmrca.hpd95.map(stamp);add(s,'rect',{x:x(hpd[0]),y:20,width:Math.max(1,x(hpd[1])-x(hpd[0])),height:cursor,fill:'#fff2c6',opacity:.6});
      d.nodes.forEach(n=>{const end=stamp(n.date);if(n.parent!==null){const p=state.by.get(n.parent);let from=stamp(p.date),st=state.ends[p.id];add(s,'line',{x1:x(from),x2:x(from),y1:ys[p.id],y2:ys[n.id],stroke:col(st),'stroke-width':1.6,opacity:from<=time?1:.2});const events=d.history.jumps.filter(j=>j.branch===n.id).sort((a,b)=>stamp(a.date)-stamp(b.date));[...events,{date:n.date,to:null}].forEach(j=>{let to=stamp(j.date);add(s,'line',{x1:x(from),x2:x(to),y1:ys[n.id],y2:ys[n.id],stroke:col(st),'stroke-width':2.5,opacity:from<=time?1:.18});from=to;st=j.to;});}
        add(s,n.sample_id?'rect':'circle',n.sample_id?{x:x(end)-4,y:ys[n.id]-4,width:8,height:8,fill:'#ffc627',stroke:'#8c1d40',opacity:end<=time?1:.35}:{cx:x(end),cy:ys[n.id],r:n.parent===null?6:2.5,fill:col(state.ends[n.id]),opacity:end<=time?1:.2});
        if(n.sample_id)add(s,'text',{x:510,y:ys[n.id]+4,'font-size':12,fill:'#243c46','font-weight':650},n.label||n.sample_id);
      });
      add(s,'line',{x1:x(time),x2:x(time),y1:18,y2:cursor+12,stroke:'#8c1d40','stroke-dasharray':'4 4',opacity:.7});
      add(s,'text',{x:28,y:18,fill:'#536b77','font-size':11},date(min));add(s,'text',{x:490,y:18,fill:'#536b77','font-size':11,'text-anchor':'end'},date(max));
    }
    function counts(){const s=el('counts');s.replaceChildren();el('curve-title').textContent='Entries into '+location.get(target).label+' through time';const high=Math.max(1,...curve.map(p=>p.high)),x=t=>50+(t-min)/(max-min)*1120,y=v=>195-v/high*165;
      [0,high/2,high].forEach(v=>{add(s,'line',{x1:50,x2:1170,y1:y(v),y2:y(v),stroke:'#e2e8ea'});add(s,'text',{x:40,y:y(v)+4,'text-anchor':'end','font-size':12,fill:'#536b77'},v.toFixed(v%1?1:0));});
      const line=pts=>pts.map(p=>`${x(p.time)},${y(p.v)}`).join('L');add(s,'path',{d:'M'+line(curve.map(p=>({...p,v:p.high})))+'L'+line(curve.slice().reverse().map(p=>({...p,v:p.low})))+'Z',fill:'#8c1d40',opacity:.12});add(s,'path',{d:'M'+line(curve.map(p=>({...p,v:p.mean}))),fill:'none',stroke:'#8c1d40','stroke-width':3});add(s,'line',{x1:x(time),x2:x(time),y1:25,y2:195,stroke:'#5d6870'});
      const p=curve.reduce((a,b)=>Math.abs(b.time-time)<Math.abs(a.time-time)?b:a);add(s,'circle',{cx:x(p.time),cy:y(p.mean),r:5,fill:'#ffc627',stroke:'#8c1d40','stroke-width':2});add(s,'text',{x:50,y:225,'font-size':12,fill:'#536b77'},date(min));add(s,'text',{x:1170,y:225,'text-anchor':'end','font-size':12,fill:'#536b77'},date(max));}
    function render(){const d=data.draws[drawIndex],state=statesAt(d,time);el('current-date').textContent=date(time);el('time').value=Math.round((time-min)/(max-min)*1000);el('draw').value=drawIndex+1;el('chain').textContent=`Chain ${d.chain} · state ${d.state.toLocaleString()}`;el('prev').disabled=drawIndex===0;el('next').disabled=drawIndex===data.draws.length-1;map(d,state);tree(d,state);counts();}
    el('target').addEventListener('change',e=>{target=e.target.value;curve=cumulative(data,target,times);updateMetrics();render();});
    function choose(n){drawIndex=Math.max(0,Math.min(data.draws.length-1,Number.isFinite(n)?n:0));render();}
    el('prev').onclick=()=>choose(drawIndex-1);el('next').onclick=()=>choose(drawIndex+1);el('draw').onchange=e=>choose(Math.round(Number(e.target.value))-1);
    el('time').oninput=e=>{stop();time=min+(max-min)*Number(e.target.value)/1000;render();};
    el('play').onclick=()=>{if(playing){stop();return;}if(time>=max)time=min;playing=true;el('play').textContent='Pause';timer=setInterval(()=>{time=Math.min(max,time+(max-min)/180*Number(el('speed').value));render();if(time>=max)stop();},100);};
    updateMetrics();render();
  }
})(typeof globalThis!=='undefined'?globalThis:this);
