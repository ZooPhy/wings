(() => {
  "use strict";
  const DAY = 86400000;
  const number = v => typeof v === "number" && Number.isFinite(v) && v >= 0;
  const epoch = s => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s || "")) return NaN;
    const t=Date.parse(s + "T00:00:00Z");
    return Number.isFinite(t) && new Date(t).toISOString().slice(0,10)===s ? t : NaN;
  };
  const iso = n => new Date(n).toISOString().slice(0,10);
  const shortDate = s => new Date(s + "T00:00:00Z").toLocaleDateString("en-US", {month:"short",day:"numeric",timeZone:"UTC"});
  const compact = n => number(n) ? new Intl.NumberFormat("en-US", {notation:"compact",maximumFractionDigits:1}).format(n) : "Unavailable";
  const exact = n => number(n) ? Math.round(n).toLocaleString("en-US") : "Unavailable";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const make = (name, attrs={}, text, svg=false) => {
    const n = svg ? document.createElementNS("http://www.w3.org/2000/svg", name) : document.createElement(name);
    Object.entries(attrs).forEach(([k,v]) => n.setAttribute(k, String(v)));
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const svgNode = (name, attrs={}, text) => make(name, attrs, text, true);

  function model(season) {
    const start=epoch(season.start_date), end=epoch(season.end_date);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end<start || end-start>200*DAY || season.metric!=="cumulative_birds_crossed") return null;
    const source=new Map(), ordered=season.rows || [];
    let previous=-Infinity, count=-Infinity;
    for (const r of ordered) {
      const t=epoch(r.date), c=r.cumulative_birds;
      if (!Number.isFinite(t) || t<start || t>end || t<=previous || (c!=null && (!number(c) || c<count))) return null;
      if (number(c)) count=c;
      previous=t; source.set(r.date,r);
    }
    const valid=ordered.filter(r=>number(r.cumulative_birds));
    if (!valid.length) return null;
    const last=valid[valid.length-1], total=last.cumulative_birds, through=epoch(last.date);
    let contiguous=true;
    const days=[];
    for (let t=start;t<=end;t+=DAY) {
      const date=iso(t), row=source.get(date), cumulative=row?.cumulative_birds;
      const prior=t===start ? 0 : source.get(iso(t-DAY))?.cumulative_birds;
      const value=number(cumulative) && number(prior) ? cumulative-prior : null;
      if (t<=through && !number(value)) contiguous=false;
      days.push({date,t,cumulative:number(cumulative)?cumulative:null,value,meanAloft:row?.mean_birds_aloft ?? null});
    }
    const progressAvailable=contiguous && total>0;
    days.forEach(d=> { d.phase=progressAvailable && number(d.cumulative) ? d.cumulative/total : null; });
    return {season,start,end,through,total,days,byDate:new Map(days.map(d=>[d.date,d])),
      complete:through===end && contiguous,progressAvailable,
      coverage:days.filter(d=>number(d.value)).length};
  }

  function eventsFor(explorer, m) {
    const bird=explorer.ecology?.birdcast, groups=new Map();
    for (const sample of explorer.samples || []) {
      if (explorer.hostFilter && explorer.hostFilter!=="ALL" && sample.host!==explorer.hostFilter) continue;
      const b=bird?.bindings?.[sample.sample_id];
      if (!b || !["AVAILABLE","UNAVAILABLE"].includes(b.status) || b.state_code!==m.season.state_code || !m.byDate.has(b.night)) continue;
      const k=b.night+"|"+sample.collection_date;
      if (!groups.has(k)) groups.set(k,{key:k,night:b.night,date:sample.collection_date,day:m.byDate.get(b.night),samples:[]});
      groups.get(k).samples.push(sample);
    }
    return [...groups.values()].sort((a,b)=>a.night.localeCompare(b.night));
  }

  function windowStats(m, events, from, through) {
    const selected=m.days.filter(d=>d.date>=from && d.date<=through);
    const available=selected.filter(d=>number(d.value));
    const sum=available.reduce((n,d)=>n+d.value,0), complete=available.length===selected.length;
    return {days:selected.length,available:available.length,sum,
      share:complete && m.total>0 ? sum/m.total : null,
      events:events.filter(e=>e.night>=from && e.night<=through).length};
  }

  function followWindow(explorer) {
    explorer.migrationWeaveState={...explorer.migrationWeaveState,view:"sample",range:null,page:0,lastSample:undefined};
  }

  function viewport(explorer,m,view) {
    const window=explorer.ecologyWindow?.();
    const binding=explorer.ecology?.birdcast?.bindings?.[explorer.selectedSampleId];
    const canFollow=Boolean(window && binding?.state_code===m.season.state_code && ["AVAILABLE","UNAVAILABLE"].includes(binding.status));
    if (view!=="sample") return {start:m.start,end:m.end,days:m.days,canFollow};
    if (!canFollow) return {days:[],canFollow,reason:"Select a dated sample with current BirdCast metadata for this state, or choose Full season."};
    const start=Math.max(m.start,window.start),end=Math.min(m.end,window.end);
    return {start,end,days:m.days.filter(d=>d.t>=start && d.t<=end),canFollow,
      reason:`The selected collection's ±${explorer.ecologyDays}-day window does not overlap this season. Choose Full season to restore the overview.`};
  }

  const finite = v => typeof v === "number" && Number.isFinite(v);
  const decimal = v => finite(v) ? v.toLocaleString("en-US",{maximumFractionDigits:1}) : "Unavailable";
  const CONDITIONS = {
    0:["Clear sky","sun"],1:["Mainly clear","partly"],2:["Partly cloudy","partly"],3:["Overcast","cloud"],
    45:["Fog","fog"],48:["Rime fog","fog"],51:["Light drizzle","rain"],53:["Moderate drizzle","rain"],55:["Dense drizzle","rain"],
    56:["Light freezing drizzle","rain"],57:["Dense freezing drizzle","rain"],61:["Slight rain","rain"],63:["Moderate rain","rain"],65:["Heavy rain","rain"],
    66:["Light freezing rain","rain"],67:["Heavy freezing rain","rain"],71:["Slight snowfall","snow"],73:["Moderate snowfall","snow"],75:["Heavy snowfall","snow"],77:["Snow grains","snow"],
    80:["Slight rain showers","rain"],81:["Moderate rain showers","rain"],82:["Violent rain showers","rain"],85:["Slight snow showers","snow"],86:["Heavy snow showers","snow"],
    95:["Thunderstorm","storm"],96:["Thunderstorm with slight hail","storm"],97:["Heavy thunderstorm","storm"],99:["Thunderstorm with heavy hail","storm"]
  };
  const condition = code => Number.isInteger(code) && CONDITIONS[code] ? CONDITIONS[code] : ["Condition unavailable",null];

  function weatherContext(explorer,m,sampleId=explorer.selectedSampleId) {
    const sample=(explorer.samples || []).find(s=>s.sample_id===sampleId);
    if (!sample) return {reason:"Select a collection sample to show weather at its location."};
    const coordinate=(value,limit)=>(typeof value==="number" || (typeof value==="string" && value.trim()!=="")) && Number.isFinite(Number(value)) && Math.abs(Number(value))<=limit;
    if (sample.has_coordinates===false || !coordinate(sample.latitude,90) || !coordinate(sample.longitude,180)) return {reason:`Sample ${sample.sample_id} has no valid coordinates. Choose a sample with cached weather using Weather sample above.`};
    const binding=explorer.ecology?.bindings?.[sample.sample_id];
    if (binding?.status!=="READY") return {reason:binding?.reason || "Weather is not cached for this sample."};
    const state=explorer.ecology?.birdcast?.bindings?.[sample.sample_id]?.state_code;
    if (state!==m.season.state_code) return {reason:"The selected sample belongs to a different region. Select a collection in the displayed state to show its weather."};
    const context=explorer.ecology?.weather?.[binding.weather_key];
    if (context?.dataset!=="ERA5" || context.units?.temperature_2m_mean!=="°C" || context.units?.precipitation_sum!=="mm" || context.units?.wind_speed_10m_max!=="km/h") return {reason:"A validated ERA5 weather snapshot is unavailable for this sample."};
    return {sample,context};
  }

  function weatherChoices(explorer,m) {
    const choices=new Map();
    for (const sample of explorer.samples || []) {
      if (explorer.hostFilter && explorer.hostFilter!=="ALL" && sample.host!==explorer.hostFilter) continue;
      const bird=explorer.ecology?.birdcast?.bindings?.[sample.sample_id];
      if (!["AVAILABLE","UNAVAILABLE"].includes(bird?.status) || !m.byDate.has(bird.night)) continue;
      const result=weatherContext(explorer,m,sample.sample_id);
      if (!result.context || !(result.context.rows || []).some(r=>m.byDate.has(r.date) && ["temperature_2m_mean","precipitation_sum","wind_speed_10m_max"].some(k=>finite(r[k])))) continue;
      const key=explorer.ecology.bindings[sample.sample_id].weather_key+"|"+sample.collection_date;
      if (!choices.has(key)) choices.set(key,{sample,count:0,ids:[]});
      const choice=choices.get(key);choice.count++;choice.ids.push(sample.sample_id);
      if (sample.sample_id===explorer.selectedSampleId) choice.sample=sample;
    }
    return [...choices.values()].sort((a,b)=>String(a.sample.collection_date).localeCompare(String(b.sample.collection_date)) || a.sample.sample_id.localeCompare(b.sample.sample_id));
  }

  function weatherDays(context,days) {
    const source=new Map((context.rows || []).map(r=>[r.date,r]));
    return days.map(d=>{
      const row=source.get(d.date) || {};
      const means=Array.from({length:7},(_,i)=>source.get(iso(d.t-i*DAY))?.temperature_2m_mean);
      return {...d,weather:row,average7:means.every(finite)?means.reduce((a,b)=>a+b,0)/7:null};
    });
  }

  function weatherSummary(days,from,through) {
    const rows=days.filter(d=>d.date>=from && d.date<=through).map(d=>d.weather);
    const values=key=>rows.map(r=>r[key]).filter(finite);
    const means=values("temperature_2m_mean"),precip=values("precipitation_sum"),wind=values("wind_speed_10m_max");
    return {days:rows.length,temperatureDays:means.length,precipitationDays:precip.length,windDays:wind.length,
      mean:means.length?means.reduce((a,b)=>a+b,0)/means.length:null,
      precipitation:precip.length?precip.reduce((a,b)=>a+b,0):null,wind:wind.length?Math.max(...wind):null};
  }

  function weatherIcon(kind,x,y,label) {
    const g=svgNode("g",{transform:`translate(${x-11},${y-11})`,role:"img","aria-label":label});
    g.appendChild(svgNode("title",{},label));
    const path=(d,color,width=1.4)=>g.appendChild(svgNode("path",{d,fill:"none",stroke:color,"stroke-width":width,"stroke-linecap":"round","stroke-linejoin":"round"}));
    if (kind==="sun" || kind==="partly") {
      const cx=kind==="partly"?7:11,cy=kind==="partly"?7:11;
      g.appendChild(svgNode("circle",{cx,cy,r:4,fill:"#f7d580",stroke:"#b77b18","stroke-width":1}));
      for (let i=0;i<8;i++) {const t=i*Math.PI/4;path(`M${cx+6*Math.cos(t)},${cy+6*Math.sin(t)} L${cx+8*Math.cos(t)},${cy+8*Math.sin(t)}`,"#b77b18",1);}
    }
    if (kind!=="sun") g.appendChild(svgNode("path",{d:"M5 15 C0 15 0 8 5 8 C6 2 15 2 17 8 C24 7 24 16 18 16 Z",fill:"#eef2f3",stroke:"#607985","stroke-width":1.3}));
    if (kind==="rain") for (const xx of [6,12,18]) path(`M${xx} 18 l-2 4`,"#2583ad");
    if (kind==="snow") for (const xx of [6,17]) path(`M${xx-2} 19 l4 4 M${xx+2} 19 l-4 4 M${xx} 18 v6`,"#448da3",1);
    if (kind==="fog") {path("M1 19 H21","#8a979a");path("M4 22 H19","#8a979a");}
    if (kind==="storm") path("M13 15 L9 20 H14 L10 25","#b5841c",1.8);
    return g;
  }

  function bindRangeGesture(overlay,svg,days,x,controls) {
    const drawable=days.filter(d=>Number.isFinite(x(d)));
    let active=null;
    const nearest=e=>{
      const transform=svg.getScreenCTM();
      if (!drawable.length || !transform) return null;
      const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;
      const xx=p.matrixTransform(transform.inverse()).x;
      if (!Number.isFinite(xx)) return null;
      return drawable.reduce((a,d)=>Math.abs(x(d)-xx)<Math.abs(x(a)-xx)?d:a);
    };
    const move=e=>{
      if (e.isPrimary===false || (active && e.pointerId!==active.id)) return;
      const day=nearest(e);if (!day) return;
      controls.showDate(day.date);
      if (active) controls.selectRange(active.anchor,day.date);
    };
    const finish=(e,commit)=>{
      if (!active || e.pointerId!==active.id) return;
      if (commit) move(e);
      active=null;
      if (overlay.hasPointerCapture(e.pointerId)) overlay.releasePointerCapture(e.pointerId);
    };
    overlay.addEventListener("pointerdown",e=>{
      if (e.button!==0 || e.isPrimary===false || active) return;
      const day=nearest(e);if (!day) return;
      active={id:e.pointerId,anchor:day.date};
      overlay.setPointerCapture(e.pointerId);move(e);e.preventDefault();
    });
    overlay.addEventListener("pointermove",move);
    overlay.addEventListener("pointerup",e=>finish(e,true));
    overlay.addEventListener("pointercancel",e=>finish(e,false));
    overlay.addEventListener("lostpointercapture",e=>{if(active?.id===e.pointerId)active=null;});
    overlay.addEventListener("pointerleave",()=>{if(!active)controls.clearHover();});
  }

  function renderWeather(root,explorer,m,view,state,x,controls,redraw) {
    const empty={showDate(){},clear(){},setRange(){}};
    if (!state.weather) {root.innerHTML="";return empty;}
    const result=weatherContext(explorer,m);
    if (!result.context) {root.innerHTML=`<div class="wmw-weather-card"><strong>Daily weather at the selected collection location</strong><p>${esc(result.reason)}</p></div>`;return empty;}
    const {context,sample}=result,days=weatherDays(context,view.days),byDate=new Map(days.map(d=>[d.date,d]));
    const exists=days.some(d=>["temperature_2m_mean","precipitation_sum","wind_speed_10m_max"].some(k=>finite(d.weather[k])));
    const hasRange=days.some(d=>finite(d.weather.temperature_2m_min) && finite(d.weather.temperature_2m_max));
    const hasCodes=days.some(d=>condition(d.weather.weather_code)[1]);
    root.innerHTML=`<div class="wmw-weather-card"><div class="wmw-header"><div><div class="wmw-kicker">Weather along the same dates</div><strong>Daily weather at the selected collection location</strong></div><label><input type="checkbox" data-wmw="average7" ${state.weatherAverage?"checked":""}> Seven-day temperature mean</label></div><p class="wmw-note">${esc(sample.sample_id)} · ERA5 ~25 km grid at ${esc(context.grid_latitude)}, ${esc(context.grid_longitude)}. Daily estimates align by calendar label with BirdCast’s evening dates; they describe the full day. ${!hasRange?"Daily min/max values are not present in this window.":""} ${!hasCodes?"Condition codes are unavailable; no weather icons are inferred.":""}</p><div class="wmw-weather-chart wmw-chart"></div><div class="wmw-weather-legend"><span>Temperature: daily mean <i style="background:#c16e32"></i>${state.weatherAverage?" · dashed seven-day mean":""}${hasRange?" · shaded daily min–max":""}</span><span>Precipitation: daily total <i style="background:#2985ad"></i></span><span>Wind: daily maximum <i style="background:#8271a3"></i></span></div><div class="wmw-weather-inspect"><label>Inspect day <select data-wmw="weather-day" aria-label="Inspect weather and migration date">${days.map(d=>`<option value="${d.date}">${d.date}</option>`).join("")}</select></label><div class="wmw-weather-readout" aria-live="polite"></div></div><p class="wmw-weather-summary" aria-live="polite"></p><details><summary>Weather values and source</summary><p>Icons summarize the source’s most severe condition during that day. Seven-day means use the selected date and six preceding calendar days; all seven temperature values must be cached. The daily values and min–max range remain visible. Missing values are gaps. Switching axes never changes the weather averaging interval. Weather is tied to this sample’s grid cell and is not a statewide estimate.</p><p>Retrieved: ${esc(context.retrieved_at)} · Source timezone: ${esc(context.timezone)}<br>Source SHA-256: <code>${esc(context.raw_sha256)}</code><br>Open-Meteo / Copernicus Climate Change Service · ERA5 · CC BY 4.0. <a href="https://open-meteo.com/en/docs/historical-weather-api" target="_blank" rel="noopener noreferrer">Source documentation</a></p><div class="wmw-table"><table><thead><tr><th>Date</th><th>Mean °C</th><th>Min °C</th><th>Max °C</th><th>Precip. mm</th><th>Max wind km/h</th><th>Daily condition</th></tr></thead><tbody>${days.map(d=>`<tr><td>${d.date}</td>${["temperature_2m_mean","temperature_2m_min","temperature_2m_max","precipitation_sum","wind_speed_10m_max"].map(k=>`<td>${decimal(d.weather[k])}</td>`).join("")}<td>${condition(d.weather.weather_code)[0]}</td></tr>`).join("")}</tbody></table></div></details></div>`;
    const q=s=>root.querySelector(s);
    q('[data-wmw="average7"]').addEventListener("change",e=>{state.weatherAverage=e.target.checked;redraw();});
    q('[data-wmw="weather-day"]').addEventListener("change",e=>controls.showDate(e.target.value));
    const svg=svgNode("svg",{viewBox:"0 0 1100 290",role:"img","aria-label":"Daily temperature, precipitation and maximum wind at the selected collection location"});
    q('.wmw-weather-chart').appendChild(svg);
    svg.appendChild(svgNode("title",{},"Weather aligned to the Migration Weave date axis"));
    const drawable=days.filter(d=>x(d)!==null),left=70,right=1070;
    const temps=drawable.flatMap(d=>[d.weather.temperature_2m_mean,d.weather.temperature_2m_min,d.weather.temperature_2m_max,state.weatherAverage?d.average7:null]).filter(finite);
    const lo=temps.length?Math.min(...temps):0,hi=temps.length?Math.max(...temps):1;
    const bottom=lo===hi?lo-1:lo,top=lo===hi?hi+1:hi;
    const ty=v=>104-(v-bottom)/(top-bottom)*66;
    const rainMax=Math.max(1,...drawable.map(d=>d.weather.precipitation_sum).filter(finite));
    const windMax=Math.max(1,...drawable.map(d=>d.weather.wind_speed_10m_max).filter(finite));
    const ry=v=>194-v/rainMax*38,wy=v=>258-v/windMax*36;
    const frame=(caption,yy,base,low,high)=>{
      svg.appendChild(svgNode("text",{x:left,y:yy-9},caption));
      for(const [y,label] of [[yy,high],[base,low]]) {svg.appendChild(svgNode("line",{x1:left,x2:right,y1:y,y2:y,stroke:"#e4dfd7","stroke-dasharray":"3 5"}));svg.appendChild(svgNode("text",{x:left-12,y:y+4,"text-anchor":"end"},label));}
    };
    frame("Temperature · °C",38,104,decimal(bottom),decimal(top));
    frame("Precipitation · mm (rain + snow)",156,194,"0",decimal(rainMax));
    frame("Maximum wind speed · km/h",222,258,"0",decimal(windMax));
    const highlight=svgNode("rect",{x:left,y:32,width:0,height:232,fill:"#147d83","fill-opacity":.14,stroke:"none","pointer-events":"none","data-weather":"range-highlight"});svg.appendChild(highlight);
    const segments=(predicate,draw)=>{let run=[];const flush=()=>{if(run.length)draw(run);run=[];};for(const d of days){if(x(d)!==null && predicate(d))run.push(d);else flush();}flush();};
    segments(d=>finite(d.weather.temperature_2m_min) && finite(d.weather.temperature_2m_max),run=>{
      const upper=run.map(d=>`${x(d)},${ty(d.weather.temperature_2m_max)}`),lower=run.slice().reverse().map(d=>`${x(d)},${ty(d.weather.temperature_2m_min)}`);
      if(run.length===1)svg.appendChild(svgNode("line",{x1:x(run[0]),x2:x(run[0]),y1:ty(run[0].weather.temperature_2m_min),y2:ty(run[0].weather.temperature_2m_max),stroke:"#d69254","stroke-width":3,opacity:.4}));
      else svg.appendChild(svgNode("path",{d:"M"+upper.join(" L")+" L"+lower.join(" L")+" Z",fill:"#e8c598",opacity:.5,"data-weather":"temperature-range"}));
    });
    const line=(get,y,color,extra={})=>segments(d=>finite(get(d)),run=>{
      svg.appendChild(svgNode("path",{d:"M"+run.map(d=>`${x(d)},${y(get(d))}`).join(" L"),fill:"none",stroke:color,"stroke-width":1.7,...extra}));
      if(run.length===1)svg.appendChild(svgNode("circle",{cx:x(run[0]),cy:y(get(run[0])),r:2,fill:color}));
    });
    line(d=>d.weather.temperature_2m_mean,ty,"#c16e32",{"data-weather":"temperature-mean"});
    if(state.weatherAverage)line(d=>d.average7,ty,"#783e22",{"stroke-width":2.5,"stroke-dasharray":"6 3","data-weather":"average7"});
    line(d=>d.weather.wind_speed_10m_max,wy,"#8271a3",{"data-weather":"wind"});
    drawable.forEach((d,i)=>{
      const xx=x(d),v=d.weather.precipitation_sum;
      const spacing=Math.min(i?Math.abs(xx-x(drawable[i-1])):right-left,i+1<drawable.length?Math.abs(x(drawable[i+1])-xx):right-left);
      const w=Math.max(1,Math.min(9,spacing*.6));
      if(finite(v))svg.appendChild(svgNode("rect",{x:Math.max(left,Math.min(right-w,xx-w/2)),y:ry(v)-(v===0?1:0),width:w,height:v===0?1:194-ry(v),fill:"#2985ad",opacity:.72,"data-weather":"precipitation"}));
    });
    let lastIcon=-Infinity;
    for(const d of drawable) {
      const [label,kind]=condition(d.weather.weather_code),xx=x(d);
      if(kind && xx-lastIcon>=28) {svg.appendChild(weatherIcon(kind,xx,125,`${d.date}: ${label}; most severe daily condition`));lastIcon=xx;}
    }
    if(!exists)svg.appendChild(svgNode("text",{x:570,y:125,"text-anchor":"middle"},"No cached weather values in these dates"));
    const brush=svgNode("path",{d:"",fill:"none",stroke:"#ac7418","stroke-width":1.2,"stroke-dasharray":"4 4","pointer-events":"none","data-weather":"range-boundaries"});svg.appendChild(brush);
    const cursor=svgNode("line",{x1:left,x2:left,y1:32,y2:264,stroke:"#147d83","stroke-dasharray":"3 3",opacity:0,"pointer-events":"none"});svg.appendChild(cursor);
    const overlay=svgNode("rect",{x:left,y:32,width:right-left,height:232,fill:"transparent",style:"cursor:crosshair;touch-action:none;user-select:none"});svg.appendChild(overlay);
    bindRangeGesture(overlay,svg,days,x,controls);
    const controller={
      active:true,
      showDate(date){
        const d=byDate.get(date);if(!d)return;
        state.weatherDay=date;const xx=x(d);cursor.setAttribute("opacity",xx===null?0:1);if(xx!==null){cursor.setAttribute("x1",xx);cursor.setAttribute("x2",xx);}
        q('[data-wmw="weather-day"]').value=date;
        const w=d.weather,unit=(v,u)=>finite(v)?decimal(v)+u:"Unavailable";
        q('.wmw-weather-readout').textContent=`${date} · ${condition(w.weather_code)[0]} · Mean ${unit(w.temperature_2m_mean," °C")} · Min ${unit(w.temperature_2m_min," °C")} / max ${unit(w.temperature_2m_max," °C")} · Precipitation ${unit(w.precipitation_sum," mm")} · Max wind ${unit(w.wind_speed_10m_max," km/h")}${state.weatherAverage?` · Seven-day mean ${unit(d.average7," °C")}`:""}`;
      },
      clear(){cursor.setAttribute("opacity",0);},
      setRange(from,through,selected){
        const s=weatherSummary(days,from,through);
        q('.wmw-weather-summary').textContent=`Selected dates ${from}–${through}: mean temperature ${decimal(s.mean)} °C (${s.temperatureDays}/${s.days} days); known precipitation ${decimal(s.precipitation)} mm (${s.precipitationDays}/${s.days}); highest daily max wind ${decimal(s.wind)} km/h (${s.windDays}/${s.days}).`;
        const visible=drawable.filter(d=>d.date>=from && d.date<=through);
        brush.setAttribute("d",selected && visible.length?`M${x(visible[0])},32 V264 M${x(visible.at(-1))},32 V264`:"");
        if(selected && visible.length){highlight.setAttribute("x",Math.min(right-2,x(visible[0])));highlight.setAttribute("width",Math.max(2,x(visible.at(-1))-x(visible[0])));}else highlight.setAttribute("width",0);
      }
    };
    const initial=byDate.has(state.weatherDay)?state.weatherDay:byDate.has(explorer.ecology?.birdcast?.bindings?.[sample.sample_id]?.night)?explorer.ecology.birdcast.bindings[sample.sample_id].night:days[0]?.date;
    if(initial)controller.showDate(initial);
    return controller;
  }

  const styles = `
  .wmw{--wmw-ink:#282733;--wmw-muted:#66616b;--wmw-red:#8a214b;--wmw-teal:#147d83;color:var(--wmw-ink);background:#faf8f4;border:1px solid #e6ddd9;border-radius:16px;padding:24px;margin:18px 0 28px;font:14px/1.5 system-ui,sans-serif;overflow:hidden}
  .wmw *{box-sizing:border-box}.wmw h4{font-size:28px;letter-spacing:-.8px;margin:0;color:var(--wmw-ink)}.wmw p{margin:6px 0}.wmw .wmw-kicker{font-size:10px;font-weight:800;letter-spacing:2px;color:var(--wmw-red);text-transform:uppercase}.wmw .wmw-subtitle{color:var(--wmw-muted);max-width:760px}.wmw .wmw-header,.wmw .wmw-controls,.wmw .wmw-window{display:flex;gap:14px;align-items:center;flex-wrap:wrap;justify-content:space-between}.wmw .wmw-controls{justify-content:flex-start;margin:22px 0 12px;gap:12px}.wmw label{display:flex;align-items:center;gap:7px;font-size:12px}.wmw select,.wmw input,.wmw button{font:inherit;color:inherit;border:1px solid #d8ceca;background:#fff;border-radius:7px;padding:7px 10px;max-width:100%}.wmw button{cursor:pointer}.wmw button:hover{border-color:var(--wmw-red)}.wmw button[aria-pressed=true]{background:var(--wmw-red);color:#fff;border-color:var(--wmw-red)}.wmw button:disabled{opacity:.4;cursor:default}.wmw :focus-visible{outline:3px solid #bd811f;outline-offset:3px}.wmw .wmw-toggle{display:flex;gap:4px}.wmw .wmw-badge{font-size:11px;background:#efe4db;color:#754714;padding:5px 10px;border-radius:30px}.wmw .wmw-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.wmw .wmw-metric{border-top:1px solid #ded6d1;padding:12px 0}.wmw .wmw-metric strong{font-size:23px;display:block;letter-spacing:-.5px}.wmw .wmw-metric span{font-size:11px;color:var(--wmw-muted)}.wmw .wmw-chart{overflow:auto}.wmw svg{width:100%;min-width:600px;height:auto;display:block;touch-action:pan-y}.wmw svg text{font:11px system-ui,sans-serif;fill:var(--wmw-muted)}.wmw .wmw-event{cursor:pointer}.wmw .wmw-event text{fill:var(--wmw-ink)}.wmw .wmw-event path{transition:opacity .18s ease}.wmw .wmw-event:hover path{opacity:.8}.wmw .wmw-tip{min-height:24px;font-size:12px;color:var(--wmw-teal)}.wmw .wmw-legend{display:flex;flex-wrap:wrap;gap:20px;font-size:11px;color:var(--wmw-muted);margin:0 0 12px}.wmw .wmw-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;background:var(--wmw-red)}.wmw .wmw-window{background:white;border:1px solid #e5dcd6;padding:13px;border-radius:9px;margin:12px 0}.wmw .wmw-window-title{font-weight:700;font-size:12px}.wmw .wmw-window-summary{font-size:12px;color:var(--wmw-muted)}.wmw .wmw-dates{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.wmw .wmw-detail{border-left:3px solid var(--wmw-teal);padding:8px 15px;margin:15px 0;background:#eef5f1}.wmw .wmw-detail strong{color:#185c62}.wmw .wmw-detail .wmw-samples{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px}.wmw .wmw-note,.wmw details{font-size:11px;color:var(--wmw-muted)}.wmw details{margin-top:12px}.wmw details code{word-break:break-all}.wmw summary{cursor:pointer}.wmw .wmw-table{overflow:auto;max-height:260px}.wmw table{border-collapse:collapse;width:100%;font-size:11px;margin:10px 0}.wmw th,.wmw td{padding:6px 10px;border-bottom:1px solid #e4ddd7;text-align:left;white-space:nowrap}.wmw .wmw-pagination{display:flex;align-items:center;justify-content:flex-end;gap:10px;font-size:11px}.wmw .wmw-error{color:#8a214b}.wmw a{color:#12676d}
  .wmw .wmw-weather-card{border:0;box-shadow:inset 0 0 0 1px #e0dacf;background:#fffdf8;border-radius:12px;padding:14px 0;margin:8px 0 18px}.wmw .wmw-weather-card > :not(.wmw-chart){margin-left:14px;margin-right:14px}.wmw .wmw-weather-card strong{font-size:14px}.wmw .wmw-weather-card .wmw-kicker{color:#916436;font-size:9px}.wmw .wmw-weather-legend{display:flex;flex-wrap:wrap;gap:15px;font-size:10px;color:var(--wmw-muted)}.wmw .wmw-weather-legend i{display:inline-block;width:15px;height:3px;vertical-align:middle}.wmw .wmw-weather-inspect{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:12px}.wmw .wmw-weather-readout{font-size:12px;flex:1;min-width:240px;color:#51585b}.wmw .wmw-weather-summary{font-size:11px;color:var(--wmw-muted)}
  .wmw .wmw-event,.wmw .wmw-event:focus,.wmw .wmw-event:focus-visible{outline:none;user-select:none;-webkit-user-select:none}.wmw .wmw-focus-ring{opacity:0;pointer-events:none}.wmw .wmw-event:focus-visible .wmw-focus-ring{opacity:1}
  .wmw .wmw-weather-controls{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 0 18px}.wmw .wmw-weather-controls select{max-width:480px}.wmw .wmw-weather-card{box-shadow:none;background:transparent;border-top:1px solid #e0dacf;border-radius:0}.wmw .wmw-weather-card > :not(.wmw-chart){margin-left:0;margin-right:0}
  @media(max-width:650px){.wmw{padding:15px}.wmw .wmw-metrics{gap:8px}.wmw .wmw-metric strong{font-size:19px}.wmw h4{font-size:24px}.wmw .wmw-window{align-items:flex-start}.wmw .wmw-controls label{width:100%}}

  .wmw{--wmw-red:#8C1D40;--wmw-ink:#263b43;--wmw-muted:#566b75;background:#fff;border-color:#dce4e7;border-top:5px solid #8C1D40}
  .wmw .wmw-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px;margin:18px 0 8px}.wmw .wmw-toolbar label{flex-wrap:wrap}.wmw .wmw-toggle{flex-wrap:wrap}
  .wmw .wmw-view-options{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 24px;justify-content:space-between;margin-bottom:12px}.wmw .wmw-view-options details{margin:0}.wmw .wmw-option-content{padding:12px;border:1px solid #dce4e7;border-radius:8px;max-width:460px;margin-top:8px;background:#f6f8f8}.wmw .wmw-option-content p{margin:8px 0 0}
  .wmw summary{color:var(--wmw-red);font-weight:700}.wmw .wmw-metrics{display:flex;flex-wrap:wrap;gap:12px 28px;background:#f6f8f8;border:1px solid #dce4e7;border-radius:9px;padding:12px 16px;margin:12px 0}.wmw .wmw-metric{border:0;padding:0;display:flex;flex-wrap:wrap;align-items:baseline;gap:6px}.wmw .wmw-metric strong{font-size:16px;letter-spacing:0}.wmw .wmw-metric span{font-size:12px}
  .wmw .wmw-window{border-color:#dce4e7;margin-top:10px}.wmw .wmw-window details{margin:0}.wmw .wmw-dates{padding-top:10px}.wmw .wmw-detail:empty,.wmw .wmw-pagination:empty{display:none}.wmw .wmw-weather-controls{margin:8px 0;font-size:12px}
  .wmw .wmw-samples label{flex-wrap:wrap;max-width:100%;min-width:0}.wmw .wmw-samples select{min-width:0;max-width:100%}
  @media(prefers-reduced-motion:reduce){.wmw *{transition:none!important}}`;

  function render(explorer) {
    const root=explorer.migrationWeaveNode;
    explorer.migrationWeaveWindow=null;
    if (!root) return false;
    const bird=explorer.ecology?.birdcast;
    const models=(bird?.seasons || []).map(model).filter(Boolean);
    const state=explorer.migrationWeaveState=Object.assign({mode:"calendar",scale:"linear",season:null,range:null,page:0,view:"season",weather:false,weatherAverage:false},explorer.migrationWeaveState);
    const binding=bird?.bindings?.[explorer.selectedSampleId];
    const selectedSeason=binding && ["AVAILABLE","UNAVAILABLE"].includes(binding.status) ? models.find(m=>m.season.state_code===binding.state_code && m.byDate.has(binding.night)) : null;
    if (state.lastSample!==explorer.selectedSampleId) {
      state.lastSample=explorer.selectedSampleId;
      if (state.view==="sample") {state.range=null;state.page=0;}
      if (selectedSeason && selectedSeason.season.key!==state.season) {state.season=selectedSeason.season.key;state.range=null;state.page=0;}
    }
    const m=models.find(s=>s.season.key===state.season) || models[0];
    root.className="wse-migration-weave wmw";
    const heading=`<style>${styles}</style><div class="wmw-header"><div><div class="wmw-kicker">BirdCast × WINGS</div><h4>Migration Weave</h4></div></div>`;
    if (!m) {
      root.innerHTML=heading+`<p class="wmw-subtitle">Place collection events along the season’s migration pulse.</p><p>A validated seasonal series is not included in this snapshot. Matched nightly values remain available below.</p><details><summary>Seasonal availability</summary><p>Rebuild the ecological snapshot with BirdCast fetching enabled to upgrade older caches. Saved reports use only their included data.</p><p>${esc([...new Set((bird?.records || []).map(r=>r.seasonal_reason).filter(Boolean))].join(" "))}</p></details>`;
      explorer.renderEbirdContext?.();
      return false;
    }
    if (state.season!==m.season.key) {state.season=m.season.key;state.range=null;state.page=0;}
    const view=viewport(explorer,m,state.view),plotDays=view.days;
    if (!plotDays.length) {
      root.innerHTML=heading+`<p>${esc(m.season.label)} · ${esc(view.reason)}</p><button type="button" data-wmw="whole">Full season</button>`;
      root.querySelector('[data-wmw="whole"]').addEventListener("click",()=>{state.view="season";state.range=null;render(explorer);});
      explorer.renderEbirdContext?.();
      return true;
    }
    const viewStart=iso(view.start),viewEnd=iso(view.end);
    if (state.range && (state.range[0]<viewStart || state.range[1]>viewEnd)) state.range=null;
    const phases=plotDays.map(d=>d.phase).filter(number);
    const phaseStart=state.view==="season"?0:Math.min(...phases),phaseEnd=state.view==="season"?1:Math.max(...phases);
    const progressAvailable=m.progressAvailable && phases.length>0 && phaseEnd>phaseStart;
    if (state.mode==="progress" && !progressAvailable) state.mode="calendar";
    const events=eventsFor(explorer,m).filter(e=>e.day.t>=view.start && e.day.t<=view.end), focus=events.find(e=>e.samples.some(s=>s.sample_id===explorer.selectedSampleId));
    const plottable=state.mode==="progress"?events.filter(e=>e.day.phase!==null):events;
    if (state.focusSample!==explorer.selectedSampleId) {
      state.focusSample=explorer.selectedSampleId;
      if (focus && plottable.includes(focus)) state.page=Math.floor(plottable.indexOf(focus)/8);
    }
    const region=explorer.ecology?.states?.[m.season.state_code] || m.season.state_code;
    const basis=m.complete ? "full-season passage" : `observed passage through ${shortDate(iso(m.through))}`;
    const choices=state.weather?weatherChoices(explorer,m):[];
    const chosenWeather=choices.find(c=>c.ids.includes(explorer.selectedSampleId));
    root.innerHTML=heading+`
      <p class="wmw-subtitle">Sample collections alongside estimated nightly migration.</p>
      <div class="wmw-toolbar">
        <label>Season <select data-wmw="season" aria-label="Migration season">${models.map(n=>`<option value="${esc(n.season.key)}" ${n===m?"selected":""}>${esc(explorer.ecology?.states?.[n.season.state_code] || n.season.state_code)} · ${esc(n.season.label)}</option>`).join("")}</select></label>
        <div class="wmw-toggle" role="group" aria-label="Migration horizontal axis"><button type="button" data-wmw="calendar" aria-pressed="${state.mode==="calendar"}">Calendar</button><button type="button" data-wmw="progress" aria-pressed="${state.mode==="progress"}" ${!progressAvailable?"disabled":""}>Migration progress</button></div>
        <div class="wmw-toggle" role="group" aria-label="Migration displayed dates"><button type="button" data-wmw="whole" aria-pressed="${state.view==="season"}">Full season</button><button type="button" data-wmw="sample-window" aria-pressed="${state.view==="sample"}" ${!view.canFollow?"disabled":""}>Sample ±${explorer.ecologyDays || 30} days</button></div>
        <button type="button" data-wmw="weather" aria-pressed="${Boolean(state.weather)}" title="Toggle daily weather at the selected collection location">Weather</button>
      </div>
      <div class="wmw-view-options"><span class="wmw-note" data-wmw="view-label">${shortDate(viewStart)} – ${shortDate(viewEnd)} · ${state.view==="sample"?"Follows selected sample":"Full season"}</span><details data-wmw="options" ${state.optionsOpen?"open":""}><summary>Chart options</summary><div class="wmw-option-content"><label>Pulse height <select data-wmw="scale"><option value="linear" ${state.scale==="linear"?"selected":""}>Linear</option><option value="sqrt" ${state.scale==="sqrt"?"selected":""}>Square root</option></select></label><p>Calendar shows migration-night dates. Migration progress shows the cumulative share of ${esc(basis)}.</p><p>Connecting lines have a fixed width; they do not show movement routes or sample counts.</p></div></details></div>
      ${state.weather?`<div class="wmw-weather-controls">${choices.length?`<label>Weather sample <select data-wmw="weather-sample" aria-label="Select a sample with cached weather"><option value="" ${!chosenWeather?"selected":""}>Choose a collection with weather…</option>${choices.map(c=>`<option value="${esc(c.sample.sample_id)}" ${c===chosenWeather?"selected":""}>${esc(c.sample.collection_date)} · ${esc(c.sample.sample_id)}${c.count>1?` · ${c.count} samples share weather`:""}</option>`).join("")}</select></label><span class="wmw-note">Weather at the selected collection location.</span>`:`<span class="wmw-note">No samples with cached weather in this season and host filter.</span>`}</div>`:""}
      <div class="wmw-metrics" aria-label="Migration summary">
        <div class="wmw-metric"><strong>${compact(m.total)}</strong><span>${m.complete?"estimated season crossings":"estimated crossings through "+esc(shortDate(iso(m.through)))}</span></div>
        <div class="wmw-metric"><strong>${events.reduce((n,e)=>n+e.samples.length,0)} samples</strong><span>${events.length} collection ${events.length===1?"event":"events"} in view</span></div>
        <div class="wmw-metric"><strong>${plotDays.filter(d=>number(d.value)).length} / ${plotDays.length}</strong><span>nights with estimates</span></div>
      </div>
      ${!m.complete?'<p class="wmw-note">Incomplete season: percentages use observed passage only.</p>':""}
      ${!progressAvailable?'<p class="wmw-note">Migration progress unavailable for these dates.</p>':""}
      <div class="wmw-chart"></div><div class="wmw-legend"><span><i class="wmw-dot"></i>Estimated nightly crossings · ${state.scale==="sqrt"?"square-root":"linear"} height</span><span><i class="wmw-dot" style="background:#147d83"></i>Sample collection → matched migration night</span><span>Gaps = missing estimates</span></div><div class="wmw-weather"></div>
      <div class="wmw-tip" aria-live="polite">Hover for nightly estimates; select a collection to inspect its samples.</div>
      <div class="wmw-window"><div><div class="wmw-window-title">Selected nights</div><div class="wmw-window-summary" aria-live="polite"></div></div><details data-wmw="dates" ${state.datesOpen?"open":""}><summary>Select dates</summary><div class="wmw-dates"><label>From <input type="date" data-wmw="from" aria-label="Window start migration night" min="${viewStart}" max="${viewEnd}"></label><label>Through <input type="date" data-wmw="through" aria-label="Window end migration night" min="${viewStart}" max="${viewEnd}"></label><button type="button" data-wmw="reset">Reset selection</button></div></details></div>
      <div class="wmw-pagination"></div>
      <div class="wmw-detail"></div>
      <p class="wmw-note">Drag across a chart to select nights. Collections link to their ${bird.night_offset_days===-1?"preceding migration night":"collection-date evening"}. BirdCast combines species; these links show timing, not host movement.</p>
`;
    const q=s=>root.querySelector(s), redraw=()=>render(explorer);
    for(const [name,key] of [["options","optionsOpen"],["dates","datesOpen"]]) {
      q(`[data-wmw="${name}"]`).addEventListener("toggle",e=>{state[key]=e.target.open;});
    }
    q('[data-wmw="weather"]').addEventListener("click",()=>{state.weather=!state.weather;redraw();});
    q('[data-wmw="weather-sample"]')?.addEventListener("change",e=>{
      const choice=choices.find(c=>c.sample.sample_id===e.target.value);
      if (choice && choice.sample.sample_id!==explorer.selectedSampleId) explorer.selectSample(choice.sample.sample_id);
    });
    q('[data-wmw="season"]').addEventListener("change",e=>{state.season=e.target.value;state.view="season";state.range=null;state.page=0;redraw();});
    q('[data-wmw="whole"]').addEventListener("click",()=>{state.view="season";state.range=null;state.page=0;redraw();});
    q('[data-wmw="sample-window"]').addEventListener("click",()=>{followWindow(explorer);redraw();});
    for (const mode of ["calendar","progress"]) q(`[data-wmw="${mode}"]`).addEventListener("click",()=>{state.mode=mode;redraw();});
    q('[data-wmw="scale"]').addEventListener("change",e=>{state.scale=e.target.value;redraw();});
    const width=1100, left=70, right=1070, top=42, base=236, eventY=355, height=418;
    const x=d=>state.mode==="progress" ? (d.phase===null?null:left+(d.phase-phaseStart)/(phaseEnd-phaseStart)*(right-left)) : left+(d.t-view.start)/Math.max(DAY,view.end-view.start)*(right-left);
    const max=Math.max(1,...plotDays.filter(d=>number(d.value)).map(d=>d.value));
    const y=v=>base-(state.scale==="sqrt"?Math.sqrt(v/max):v/max)*(base-top);
    const svg=svgNode("svg",{viewBox:`0 0 ${width} ${height}`,role:"group","aria-label":`Migration pulse and collection ribbons for ${region}, ${m.season.label}`});
    svg.appendChild(svgNode("desc",{},"Nightly crossing estimates with linked collection events. Open Select dates below the chart to choose nights without dragging. Select a collection marker to inspect linked samples."));
    q('.wmw-chart').appendChild(svg);
    for (let i=0;i<=3;i++) {
      const ratio=i/3, value=max*(state.scale==="sqrt"?ratio*ratio:ratio), yy=base-ratio*(base-top);
      svg.appendChild(svgNode("line",{x1:left,x2:right,y1:yy,y2:yy,stroke:"#e6dfd8","stroke-dasharray":i?"3 5":"none"}));
      svg.appendChild(svgNode("text",{x:left-12,y:yy+4,"text-anchor":"end"},compact(value)));
    }
    svg.appendChild(svgNode("text",{x:left,y:20},"Estimated birds crossing the state / night"));
    if (state.mode==="calendar" && m.through<view.end) {
      const tail=Math.max(left,Math.min(right,x({t:m.through+DAY})));
      svg.appendChild(svgNode("rect",{x:tail,y:top,width:Math.max(0,right-tail),height:base-top,fill:"#ebe6df",opacity:.7}));
      if (right-tail>120) svg.appendChild(svgNode("text",{x:(tail+right)/2,y:top+22,"text-anchor":"middle"},"Beyond observed series"));
    }
    const highlight=svgNode("rect",{x:left,y:top,width:0,height:base-top,fill:"#147d83","fill-opacity":.14,stroke:"none","pointer-events":"none","data-wmw":"range-highlight"});svg.appendChild(highlight);
    // Straight segments retain daily estimates; missing dates break the area.
    let run=[];
    const flush=()=>{
      if (!run.length) return;
      const coords=run.map(d=>[x(d),y(d.value)]);
      const path=`M${coords[0][0]},${base} L${coords.map(p=>p.join(",")).join(" L")} L${coords[coords.length-1][0]},${base} Z`;
      svg.appendChild(svgNode("path",{d:path,fill:"#bd6b7e","fill-opacity":.2,stroke:"none"}));
      svg.appendChild(svgNode("path",{d:"M"+coords.map(p=>p.join(",")).join(" L"),fill:"none",stroke:"#8a214b","stroke-width":1.8}));
      if (run.length===1) svg.appendChild(svgNode("circle",{cx:coords[0][0],cy:coords[0][1],r:2,fill:"#8a214b"}));
      run=[];
    };
    for (const d of plotDays) {if (number(d.value) && x(d)!==null) run.push(d);else flush();} flush();
    for (let i=0;i<=4;i++) {
      const xx=left+i*(right-left)/4;
      const text=state.mode==="progress"?`${Number((100*(phaseStart+i*(phaseEnd-phaseStart)/4)).toFixed(1))}%`:shortDate(iso(view.start+Math.round(i*(view.end-view.start)/DAY/4)*DAY));
      svg.appendChild(svgNode("text",{x:xx,y:base+22,"text-anchor":i===0?"start":i===4?"end":"middle"},text));
    }
    const brush=svgNode("path",{d:"",fill:"none",stroke:"#ac7418","stroke-width":1.2,"stroke-dasharray":"4 4","pointer-events":"none","data-wmw":"range-boundaries"});svg.appendChild(brush);
    const fromInput=q('[data-wmw="from"]'), toInput=q('[data-wmw="through"]');
    let weatherLayer=null;
    const updateWindow=()=>{
      const [from,through]=state.range || [viewStart,viewEnd];
      fromInput.value=from;toInput.value=through;
      const stats=windowStats(m,events,from,through);
      weatherLayer?.setRange(from,through,Boolean(state.range));
      q('.wmw-window-summary').textContent=`${stats.events} collection event${stats.events===1?"":"s"} · ${stats.available}/${stats.days} nights with estimates · ${compact(stats.sum)} known crossings${stats.share===null?" · share unavailable":` · ${(100*stats.share).toFixed(1)}% of ${basis}`}`;
      const dates=plotDays.filter(d=>d.date>=from && d.date<=through && x(d)!==null);
      brush.setAttribute("d",state.range && dates.length?`M${x(dates[0])},${top} V${base} M${x(dates.at(-1))},${top} V${base}`:"");
      if(state.range && dates.length){highlight.setAttribute("x",Math.min(right-2,x(dates[0])));highlight.setAttribute("width",Math.max(2,x(dates.at(-1))-x(dates[0])));}else highlight.setAttribute("width",0);
      explorer.migrationWeaveWindow={sampleId:explorer.selectedSampleId,start:view.start,end:view.end,
        selection:state.range?[epoch(from),epoch(through)]:null};
      // Refresh only the linked eBird view; rebuilding the weave would interrupt pointer capture.
      explorer.renderEbirdContext?.();
    };
    const rangeInput=()=>{
      const a=fromInput.value,b=toInput.value;
      if (!m.byDate.has(a) || !m.byDate.has(b) || a>b || a<viewStart || b>viewEnd) {q('.wmw-window-summary').textContent="Choose an ordered pair of dates within the displayed range.";return;}
      state.range=[a,b];updateWindow();
    };
    fromInput.addEventListener("change",rangeInput);toInput.addEventListener("change",rangeInput);
    q('[data-wmw="reset"]').addEventListener("click",()=>{state.range=null;updateWindow();});updateWindow();
    const cursor=svgNode("line",{x1:left,x2:left,y1:top,y2:base,stroke:"#147d83","stroke-dasharray":"3 3",opacity:0,"pointer-events":"none"});svg.appendChild(cursor);
    const overlay=svgNode("rect",{x:left,y:top,width:right-left,height:base-top,fill:"transparent",style:"cursor:crosshair;touch-action:none;user-select:none"});svg.appendChild(overlay);
    const showDay=date=>{
      const d=m.byDate.get(date);if(!d)return;
      const xx=x(d);cursor.setAttribute("opacity",xx===null?0:1);
      if(xx!==null){cursor.setAttribute("x1",xx);cursor.setAttribute("x2",xx);}
      q('.wmw-tip').textContent=`${d.date} · ${exact(d.value)} derived nightly crossings · ${exact(d.cumulative)} cumulative${d.phase===null?"":` · ${(100*d.phase).toFixed(1)}% of ${basis}`}`;
      weatherLayer?.showDate(date);
    };
    const controls={
      showDate:showDay,
      selectRange(from,through){state.range=[from,through].sort();updateWindow();},
      clearHover(){cursor.setAttribute("opacity",0);weatherLayer?.clear();}
    };
    bindRangeGesture(overlay,svg,plotDays,x,controls);
    weatherLayer=renderWeather(q('.wmw-weather'),explorer,m,view,state,x,controls,redraw);
    updateWindow();
    if(weatherLayer.active && state.weatherDay)showDay(state.weatherDay);
    const choose=e=>{
      const sample=e.samples.find(s=>s.sample_id===explorer.selectedSampleId) || e.samples[0];
      if (sample.sample_id!==explorer.selectedSampleId) explorer.selectSample(sample.sample_id);
    };
    const pageCount=Math.max(1,Math.ceil(plottable.length/8));state.page=Math.min(state.page,pageCount-1);
    const displayed=plottable.slice(state.page*8,state.page*8+8);
    displayed.forEach((e,i)=>{
      const sx=x(e.day),tx=left+(i+.5)*(right-left)/Math.max(displayed.length,1),selected=e===focus;
      // An event outside the observed prefix cannot be placed on a progress axis.
      if (sx===null) return;
      const sy=number(e.day.value)?y(e.day.value):base, color=selected?"#8a214b":"#147d83";
      const g=svgNode("g",{class:"wmw-event",role:"button",tabindex:0,"aria-label":`Collected ${e.date}, ${e.samples.length} samples; matched migration night ${e.night}. Select event.`,"aria-pressed":selected,"data-sample-ids":e.samples.map(s=>s.sample_id).join("|")});
      const ribbon=`M${sx-3},${sy+4} C${sx-3},${base+60} ${tx-3},${base+60} ${tx-3},${eventY-12} L${tx+3},${eventY-12} C${tx+3},${base+60} ${sx+3},${base+60} ${sx+3},${sy+4} Z`;
      g.appendChild(svgNode("path",{d:ribbon,fill:color,opacity:selected?.7:.24}));
      g.appendChild(svgNode("circle",{cx:sx,cy:sy,r:selected?6:4,fill:number(e.day.value)?color:"#faf8f4",stroke:color,"stroke-width":2}));
      g.appendChild(svgNode("circle",{class:"wmw-focus-ring",cx:tx,cy:eventY,r:18,fill:"none",stroke:"#bd811f","stroke-width":2,"aria-hidden":"true"}));
      g.appendChild(svgNode("circle",{cx:tx,cy:eventY,r:13,fill:selected?color:"#fff",stroke:color,"stroke-width":1.5}));
      const countText=svgNode("text",{x:tx,y:eventY+4,"text-anchor":"middle",style:`fill:${selected?"white":color};font-weight:700`},String(e.samples.length));g.appendChild(countText);
      g.appendChild(svgNode("text",{x:tx,y:eventY+33,"text-anchor":"middle",style:"font-weight:600"},shortDate(e.date)));
      g.appendChild(svgNode("text",{x:tx,y:eventY+49,"text-anchor":"middle"},"collection"));
      g.appendChild(svgNode("title",{},`Collected ${e.date} · migration night ${e.night} · ${exact(e.day.value)} derived crossings · ${e.samples.length} samples`));
      g.addEventListener("click",()=>choose(e));g.addEventListener("keydown",event=>{if(["Enter"," "].includes(event.key)){event.preventDefault();choose(e);}});
      svg.appendChild(g);
    });
    const paging=q('.wmw-pagination');
    if (events.length>plottable.length) paging.appendChild(make("span",{},`${events.length-plottable.length} events have no observed progress position. Use Calendar to see their dates.`));
    if (pageCount>1) {
      const prev=make("button",{type:"button"},"Previous events"),next=make("button",{type:"button"},"Next events");prev.disabled=state.page===0;next.disabled=state.page===pageCount-1;
      prev.addEventListener("click",()=>{state.page--;redraw();});next.addEventListener("click",()=>{state.page++;redraw();});
      paging.append(prev,make("span",{},`Events ${state.page*8+1}–${Math.min(plottable.length,state.page*8+8)} of ${plottable.length}`),next);
    }
    const detail=q('.wmw-detail');
    if (focus) {
      const record=bird.records?.find(r=>r.state_code===m.season.state_code && r.date===focus.night);
      detail.innerHTML=`<strong>Collected ${esc(focus.date)} · ${focus.samples.length} samples</strong><p>Matched night: ${focus.night} · ${focus.day.phase===null?"Migration progress unavailable":(100*focus.day.phase).toFixed(1)+"% of "+esc(basis)}.</p><p>${record?.status==="AVAILABLE"?`${exact(record.birds_crossed)} estimated crossings in the matched-night record.`:esc(record?.reason || "No matched-night estimate is available.")}</p><div class="wmw-samples"><label>Linked sample <select aria-label="Sample within selected collection event">${focus.samples.map(s=>`<option value="${esc(s.sample_id)}" ${s.sample_id===explorer.selectedSampleId?"selected":""}>${esc(s.sample_id)}${s.host?" · "+esc(s.host):""}</option>`).join("")}</select></label></div>`;
      detail.querySelector('select').addEventListener("change",e=>{if(e.target.value!==explorer.selectedSampleId)explorer.selectSample(e.target.value);});
    } else {
      detail.textContent=explorer.selectedSampleId ? `Selected sample ${explorer.selectedSampleId} has no collection event in the displayed dates and host filter. Choose another season or select a collection ribbon.` : events.length?"Select a collection ribbon to inspect its samples and matched migration night.":"No metadata-matched collection events fall within the displayed dates and host filter.";
    }
    return true;
  }
  globalThis.WINGS_MIGRATION_WEAVE={render,followWindow,_test:{model,eventsFor,windowStats,viewport,condition,weatherContext,weatherChoices,weatherDays,weatherSummary}};
})();
