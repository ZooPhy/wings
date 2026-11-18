/* Offline comparison: one replicate in memory, no pooled histories and no refitting. */
(() => {
  'use strict';
  const $=s=>document.querySelector(s),data=JSON.parse($('#comparison-data').textContent);
  const make=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const svg=(tag,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n;};
  const fmt=(v,d=2)=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(d):'—';
  const date=v=>v?new Date(v).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric',timeZone:'UTC'}):'Unavailable';
  let selected=null,player=null,loadingScript=null,loaded=null;
  const segment=$('#segment'),location=$('#location');
  [...new Set(data.analyses.map(r=>r.segment))].forEach(id=>segment.add(new Option(id,id)));
  function records(){return data.analyses.filter(r=>r.segment===segment.value);}
  function primary(r){return data.primary_analyses.includes(r.id);}
  function label(r){return `${r.strategy} · ${r.replicate}${primary(r)?' · Primary':''}`;}
  function status(r){return r.status==='complete'?'Complete':r.status+((r.reasons||[]).length?' · '+r.reasons.join(', '):'');}
  function chart(title,w=720,h=230){const box=make('div',undefined,'chart');box.append(make('h3',title));const s=svg('svg',{viewBox:`0 0 ${w} ${h}`,role:'img','aria-label':title});box.append(s);return [box,s];}
  function axis(s,x,y,x2,y2){s.append(svg('line',{x1:x,y1:y,x2,y2,stroke:'#b8c7cc'}));}
  function card(title,value,detail){const e=make('div',undefined,'card');e.append(make('span',title),make('strong',value));if(detail)e.append(make('small',detail));return e;}
  function refreshLocations(){const before=location.value;location.replaceChildren();const ids=[...new Set(records().flatMap(r=>Object.keys(r.introductions||{})))].sort();ids.forEach(id=>location.add(new Option(data.locations[id]||id,id)));location.value=ids.includes(before)?before:ids.includes('USA:KY')?'USA:KY':ids[0]||'';}
  function drawTable(){
    const tbody=$('#replicates tbody');tbody.replaceChildren();
    records().forEach(r=>{
      const tr=make('tr');tr.classList.toggle('selected',selected?.id===r.id);
      const b=make('button',label(r));b.type='button';b.setAttribute('aria-pressed',String(selected?.id===r.id));b.addEventListener('click',()=>choose(r));
      const c=make('td');c.append(b);tr.append(c);const e=r.introductions?.[location.value];
      [e?`${fmt(e.mean)} (${fmt(e.lower,1)}–${fmt(e.upper,1)})`:'Unavailable',e?`${fmt(100*e.zero_probability,1)}%`:'—',fmt(r.temporal_diagnostics?.observed?.r2,3),status(r)].forEach(v=>tr.append(make('td',v)));tbody.append(tr);
    });
    const rs=records(),[box,s]=chart(`Entries into ${data.locations[location.value]||location.value||'selected location'} · separate replicate intervals`,840,80+rs.length*43);
    const upper=Math.max(1,...rs.map(r=>r.introductions?.[location.value]?.upper||0)),x=v=>240+v/upper*540;
    rs.forEach((r,i)=>{const y=35+i*43,e=r.introductions?.[location.value];s.append(svg('text',{x:12,y:y+5,'font-size':15,fill:r.id===selected?.id?'#8c1d40':'#435961'},label(r)));if(!e){s.append(svg('text',{x:240,y:y+5},'Unavailable'));return;}
      s.append(svg('line',{x1:x(e.lower),x2:x(e.upper),y1:y,y2:y,stroke:r.id===selected?.id?'#8c1d40':'#007d86','stroke-width':5}));
      s.append(svg('circle',{cx:x(e.mean),cy:y,r:7,fill:r.id===selected?.id?'#8c1d40':'#007d86'}));
    });
    const y=rs.length*43+18;axis(s,240,y,780,y);for(let i=0;i<=4;i++)s.append(svg('text',{x:x(i*upper/4),y:y+23,'text-anchor':'middle'},fmt(i*upper/4,1)));
    $('#intervals').replaceChildren(box);
  }
  function histogram(title,counts,observed=null){
    const [box,s]=chart(title,420,240),entries=Object.entries(counts).map(([n,v])=>[Number(n),v]).sort((a,b)=>a[0]-b[0]);
    if(!entries.length){box.append(make('p','Unavailable'));return box;}
    const lo=Math.min(0,...entries.map(e=>e[0])),hi=Math.max(lo+1,...entries.map(e=>e[0]),observed??0),max=Math.max(1,...entries.map(e=>e[1]));
    const x=v=>45+(v-lo)/(hi-lo)*330,y=v=>185-v/max*150,w=Math.max(2,Math.min(35,310/entries.length));
    entries.forEach(([value,n])=>{const rect=svg('rect',{x:x(value)-w/2,y:y(n),width:w,height:185-y(n),fill:'#007d86'});rect.append(svg('title',{},`${value}: ${n}`));s.append(rect);});
    axis(s,35,185,395,185);for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4;s.append(svg('text',{x:x(v),y:210,'text-anchor':'middle','font-size':12},fmt(v,hi<=1?2:1)));}
    s.append(svg('text',{x:5,y:30,'font-size':12},String(max)),svg('text',{x:5,y:185,'font-size':12},'0'));
    if(observed!==null){s.append(svg('line',{x1:x(observed),x2:x(observed),y1:25,y2:185,stroke:'#8c1d40','stroke-width':3}));box.append(make('p',`Observed statistic ${fmt(observed,3)} · maroon line`));}
    return box;
  }
  function drawClock(r){
    const obs=r.temporal_diagnostics?.observed||{},ps=r.date_permutation_p||{};
    $('#clock-stats').replaceChildren(card('Raw ML fit',`R² ${fmt(obs.r2,3)}`,`Rate ${fmt(obs.rate,6)} substitutions/site/year`),card('TreeTime fit',`R² ${fmt(r.clock_r2,3)}`,`Rate ${fmt(r.clock_rate,6)} substitutions/site/year`),card('Date permutations',`${fmt(ps.tips,3)} / ${fmt(ps.same_date_clades,3)}`,'p: tips / same-date clades'));
    const plots=$('#clock-plots');plots.replaceChildren();const pts=r.clock_points||[];
    const [box,s]=chart('Raw ML root-to-tip distances',600,280);
    if(pts.length){
      const low=Math.min(...pts.map(p=>p.date)),high=Math.max(...pts.map(p=>p.date)),max=Math.max(1e-9,...pts.map(p=>p.root_distance));
      const x=v=>60+(v-low)/Math.max(1e-9,high-low)*490,y=v=>220-v/max*180;
      axis(s,60,30,60,220);axis(s,60,220,550,220);
      for(let i=0;i<=4;i++){const yr=low+(high-low)*i/4;s.append(svg('text',{x:x(yr),y:243,'text-anchor':'middle','font-size':12},fmt(yr,1)));s.append(svg('text',{x:52,y:y(max*i/4)+4,'text-anchor':'end','font-size':12},fmt(max*i/4,3)));}
      const avgX=pts.reduce((a,p)=>a+p.date,0)/pts.length,avgY=pts.reduce((a,p)=>a+p.root_distance,0)/pts.length;
      if(Number.isFinite(obs.rate)){const line=svg('line',{x1:x(low),x2:x(high),y1:y(avgY+obs.rate*(low-avgX)),y2:y(avgY+obs.rate*(high-avgX)),stroke:'#73878c','stroke-width':2});s.append(line);}
      pts.forEach(p=>{const dot=svg('circle',{cx:x(p.date),cy:y(p.root_distance),r:p.source==='study'?4.5:3,fill:p.source==='study'?'#8c1d40':'#007d86',opacity:.8});dot.append(svg('title',{},`${p.id} · ${fmt(p.date,3)} · ${fmt(p.root_distance,5)}`));s.append(dot);});
      box.append(make('p','Maroon: WINGS samples · teal: references. Distances in substitutions/site.'));
    }else box.append(make('p','Clock points unavailable. Rebuild this page beside the inference outputs to include the scatterplot.'));
    plots.append(box);
    for(const [key,title] of [['tips','Tip-date permutations'],['same_date_clades','Same-date clade permutations']]){
      const perm=r.temporal_diagnostics?.permutations?.[key],counts={};
      (perm?.draws||[]).forEach(d=>{const k=(Math.floor(d.statistic*40)/40).toFixed(3);counts[k]=(counts[k]||0)+1;});
      const h=histogram(title,counts,obs.rate>0?obs.r2:0);h.append(make('p',`${perm?.permutations??0} permutations · p ${fmt(perm?.p_value,3)}`));plots.append(h);
    }
  }
  function drawSelected(){
    if(!selected)return;const r=selected;$('#selection-title').textContent=`${r.segment} / ${label(r)}`;
    $('#dates').replaceChildren(card('WINGS common ancestor · TreeTime',date(r.study_mrca_date),'Default playback begins here'),card('Whole reference-tree root',date(r.root_date),'Context only · not a Kentucky introduction date'),card('Samples / references',`${r.study} / ${r.references}`,`${r.histories??'—'} reconstructed histories`));
    const bayesian=$('#bayesian');bayesian.replaceChildren();
    if(r.bayesian_dating){const d=r.bayesian_dating;const heading=make('h3','Bayesian WINGS common-ancestor date');bayesian.append(heading);
      if(d.status==='complete'&&!d.prior_only&&d.tmrca){bayesian.append(make('p',`Median ${date(d.tmrca.median)} · 95% HPD ${date(d.tmrca.hpd95[0])} – ${date(d.tmrca.hpd95[1])}`));}
      else bayesian.append(make('p',`Posterior HPD withheld · ${d.status}`));
      bayesian.append(make('p','Conditional on the fixed rooted topology and dating model. The movie still uses TreeTime dates.','scope'));
      if(r.bayesian_report){const a=make('a','Dating report and convergence diagnostics');a.href=r.bayesian_report;bayesian.append(a);}
    }
    drawClock(r);const plots=$('#clock-plots');plots.prepend(histogram('Study-ancestry entry counts · all histories',r.histograms?.[location.value]||{}));
    const links=$('#downloads');links.replaceChildren();
    for(const [name,file] of [['Raw ML tree','ml.treefile'],['Clock points','clock_points.tsv'],['Movie JSON','movie.json']]){const a=make('a',name);a.href=`inference/${r.id}/${file}`;a.download='';links.append(a,document.createTextNode('  '));}
  }
  function choose(r){
    selected=r;loaded=null;player?.destroy();player=null;$('#movie').replaceChildren();loadingScript?.remove();loadingScript=null;
    drawTable();drawSelected();
    if(!r.movie_script){$('#load-status').textContent=r.status==='complete'?'Movie file unavailable. Keep this page beside its comparison_assets folder and rebuild from the inference outputs.':`Reconstruction unavailable: ${status(r)}. No substitute replicate is loaded.`;return;}
    $('#load-status').textContent='Loading this replicate’s complete reconstruction…';
    const s=document.createElement('script');loadingScript=s;s.src=r.movie_script;
    s.onerror=()=>{if(selected===r)$('#load-status').textContent='Could not load this replicate. Keep comparison.html and comparison_assets together.';};document.body.append(s);
  }
  window.WINGS_COMPARISON_RECEIVE=(id,movie)=>{
    if(selected?.id!==id)return;
    try{
      const model=WINGS_PHYLOGEOGRAPHY_MOVIE.validate(movie);
      player?.destroy();$('#movie').replaceChildren();
      player=WINGS_PHYLOGEOGRAPHY_MOVIE.mount(null,$('#movie'),{data:movie,embedded:true});loaded=id;
      if(model.states.has(location.value))player.setTarget(location.value);
      $('#load-status').textContent=`${selected.histories} histories loaded · study ancestry shown. Select Play to animate.`;
    }catch(e){$('#load-status').textContent='Could not display reconstruction: '+e.message;}
    loadingScript?.remove();loadingScript=null;
  };
  segment.addEventListener('change',()=>{refreshLocations();choose(records().find(primary)||records()[0]);});
  location.addEventListener('change',()=>{drawTable();drawSelected();if(player&&loaded===selected?.id){if(player.data.locations.some(l=>l.id===location.value))player.setTarget(location.value);else{player.destroy();player=null;$('#load-status').textContent='This location is absent from the selected reconstruction; it is not a zero count.';}}else if(loaded===selected?.id)choose(selected);});
  refreshLocations();choose(records().find(primary)||records()[0]);
})();
