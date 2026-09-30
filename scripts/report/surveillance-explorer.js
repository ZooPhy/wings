/* WINGS_BRAID_CLOCK_JS_BEGIN */
/* WINGS Genome Braid + Ecological Clock v0.1.0. Offline, dependency-free. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.WINGS_BRAID_CLOCK = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const VERSION = '0.1.0';
  const SEGMENTS = ['PB2', 'PB1', 'PA', 'HA', 'NP', 'NA', 'MP', 'NS'];
  const DAY = 86400000;
  const COLORS = ['#8c1d40', '#007f84', '#80601d', '#496ea0', '#7b5a8f', '#417b62', '#b05730'];
  const text = x => x === null || x === undefined ? '' : String(x).trim();
  const keyText = x => text(x).toLowerCase().replace(/\s+/g, ' ');
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
  const pct = x => x === null ? 'Not estimable' : `${Math.round(x * 100)}%`;
  const signed = n => n > 0 ? `+${n}` : String(n);
  function strictDate(s) {
    s = text(s);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
    const [y, m, d] = s.split('-').map(Number);
    if (y < 1000 || y > 9999) return null;
    const n = Date.UTC(y, m - 1, d);
    return new Date(n).toISOString().slice(0, 10) === s ? n / DAY : null;
  }
  function dateInterval(s) {
    s = text(s);
    if (/^\d{4}$/.test(s)) {
      const start = strictDate(`${s}-01-01`), end = strictDate(`${s}-12-31`);
      return start === null ? null : {start, end, precision:'year', raw:s};
    }
    if (/^\d{4}-\d{2}$/.test(s)) {
      const start = strictDate(`${s}-01`);
      if (start === null) return null;
      const [y, m] = s.split('-').map(Number);
      return {start, end:Date.UTC(y, m, 0) / DAY, precision:'month', raw:s};
    }
    const n = strictDate(s);
    return n === null ? null : {start:n, end:n, precision:'day', raw:s};
  }
  const isoDay = d => new Date(Math.round(d) * DAY).toISOString().slice(0, 10);
  const mid = v => (v.start + v.end) / 2;
  function normalizeCountry(s) {
    const v = keyText(s);
    return ['us','usa','u.s.','u.s.a.','united states','united states of america'].includes(v) ? 'usa' : v;
  }
  function genotype(sample) {
    const v = sample.genotype;
    return text(v && typeof v === 'object' ? v.call : v) || 'Not recorded';
  }
  function model(payload) {
    if (!payload || !Array.isArray(payload.samples) || !payload.trees || typeof payload.trees !== 'object' || Array.isArray(payload.trees)) {
      throw new Error('Load a WINGS surveillance_explorer.json with samples[] and trees{}.');
    }
    const entities = new Map(), samples = [], references = [];
    for (const raw of payload.samples) {
      const id = text(raw.sample_id);
      if (!id || entities.has(`s:${id}`)) throw new Error('Sample IDs must be nonempty and unique.');
      const e = {key:`s:${id}`, id, kind:'sample', label:id, host:text(raw.host) || 'Not recorded', raw};
      entities.set(e.key, e); samples.push(e);
    }
    for (const raw of payload.public_reference_context?.references || []) {
      const id = text(raw.reference_id);
      if (!id || entities.has(`r:${id}`)) throw new Error('Public reference IDs must be nonempty and unique.');
      const e = {key:`r:${id}`, id, kind:'reference', label:text(raw.isolate) || id, host:text(raw.host) || 'Not recorded', raw};
      entities.set(e.key, e); references.push(e);
    }
    const bySegment = {}, warnings = [];
    for (const segment of SEGMENTS) {
      const source = payload.trees[segment];
      if (!source?.root) continue;
      const leaves = [], index = new Map();
      let counter = 0;
      const visited = new Set();
      // Independent copy of layout evidence. Never rotate or mutate source trees.
      const walk = (node, path, total, valid) => {
        if (!node || typeof node !== 'object' || visited.has(node)) throw new Error(`Invalid/cyclic tree: ${segment}`);
        visited.add(node);
        const nodeId = counter++;
        if (counter > 100000) throw new Error('Tree exceeds the preview node limit (100,000).');
        const isRoot = !path.length;
        const length = isRoot ? 0 : node.length;
        const edgeValid = isRoot || (finite(length) && length >= 0);
        const cumulative = total + (edgeValid ? length : 0);
        const next = path.concat({id:nodeId, distance:cumulative});
        if (Array.isArray(node.children) && node.children.length) {
          for (const child of node.children) walk(child, next, cumulative, valid && edgeValid);
        } else {
          let id = text(node.sample_id) ? `s:${text(node.sample_id)}` : text(node.reference_id) ? `r:${text(node.reference_id)}` : '';
          if (!entities.has(id)) id = '';
          const leaf = {id, name:text(node.name), order:leaves.length, path:next, distance:cumulative, valid:valid && edgeValid};
          leaves.push(leaf);
          if (id) {
            if (!index.has(id)) index.set(id, []);
            index.get(id).push(leaf);
          }
        }
      };
      walk(source.root, [], 0, true);
      for (const [id, matches] of index) if (matches.length > 1) warnings.push(`${segment}: multiple tips map to ${id}; excluded from one-to-one braid and neighborhood comparisons.`);
      bySegment[segment] = {source, leaves, index};
    }
    return {payload, entities, samples, references, bySegment, warnings};
  }
  function presence(m, id, segment) {
    const tree = m.bySegment[segment];
    if (!tree) return {status:'NO_TREE', count:0};
    const found = tree.index.get(id) || [];
    return {status:found.length === 1 ? 'PRESENT' : found.length > 1 ? 'MULTIPLE_TIPS' : 'ABSENT_FROM_TREE', count:found.length};
  }
  function distance(a, b) {
    if (!a?.valid || !b?.valid) return null;
    let shared = 0;
    for (let i = 0; i < Math.min(a.path.length, b.path.length); i++) {
      if (a.path[i].id !== b.path[i].id) break;
      shared = a.path[i].distance;
    }
    return Math.max(0, a.distance + b.distance - 2 * shared);
  }
  function nearest(tree, focal, common, k) {
    const f = tree.index.get(focal)?.[0];
    const entries = common.map(id => ({id, distance:distance(f, tree.index.get(id)?.[0])}));
    if (entries.some(v => v.distance === null)) return {status:'INVALID_LENGTHS'};
    entries.sort((a,b) => a.distance - b.distance || a.id.localeCompare(b.id));
    if (entries.length <= k) return {status:'TOO_FEW_SHARED'};
    // Reject tied cutoffs rather than resolve ties by identifier or leaf order.
    const a = entries[k-1].distance, b = entries[k].distance;
    if (Math.abs(a-b) <= 1e-10 * Math.max(1, Math.abs(a), Math.abs(b))) return {status:'TIED_CUTOFF'};
    return {status:'AVAILABLE', ids:new Set(entries.slice(0,k).map(v => v.id))};
  }
  function neighborhoodProfile(m, focal, k = 3) {
    if (!Number.isInteger(k) || k < 1) throw new Error('Neighbor count must be a positive integer.');
    if (!focal?.startsWith('s:')) return {status:'SAMPLES_ONLY', mean:null, available:0, pairs:[], k};
    const pairs = [];
    for (let a = 0; a < SEGMENTS.length; a++) for (let b = a+1; b < SEGMENTS.length; b++) {
      const x = SEGMENTS[a], y = SEGMENTS[b], tx=m.bySegment[x], ty=m.bySegment[y];
      const result = {segments:[x,y], status:'FOCAL_UNAVAILABLE', overlap:null, shared:0};
      if (presence(m,focal,x).status === 'PRESENT' && presence(m,focal,y).status === 'PRESENT') {
        const common = m.samples.map(s => s.key).filter(id => id !== focal && presence(m,id,x).status === 'PRESENT' && presence(m,id,y).status === 'PRESENT');
        result.shared = common.length;
        const nx = nearest(tx, focal, common, k), ny = nearest(ty, focal, common, k);
        result.status = nx.status !== 'AVAILABLE' ? nx.status : ny.status;
        if (result.status === 'AVAILABLE') {
          const intersection = [...nx.ids].filter(id => ny.ids.has(id)).length;
          result.overlap = intersection / (2 * k - intersection);
        }
      }
      pairs.push(result);
    }
    const values=pairs.filter(v => v.overlap !== null).map(v => v.overlap);
    return {status:values.length ? 'DESCRIPTIVE' : 'NOT_ESTIMABLE', mean:mean(values), available:values.length, pairs, k};
  }
  function validatePhenology(raw) {
    if (!raw || raw.schema_version !== 'wings.phenology.v1' || !Array.isArray(raw.profiles)) throw new Error('Phenology input requires schema_version "wings.phenology.v1" and profiles[].');
    if (typeof raw.synthetic !== 'boolean') throw new Error('Phenology input must explicitly declare synthetic: true or false.');
    const seen = new Set();
    const profiles = raw.profiles.map(p => {
      if (!text(p.profile_id) || seen.has(p.profile_id)) throw new Error('Phenology profile IDs must be unique.');
      seen.add(p.profile_id);
      for (const f of ['host','country','state']) if (!text(p.scope?.[f])) throw new Error(`${p.profile_id}: exact scope.${f} is required; no inferred location.`);
      for (const f of ['source','citation','retrieved_on','method']) if (!text(p.provenance?.[f])) throw new Error(`${p.profile_id}: provenance.${f} is required.`);
      if (strictDate(p.provenance.retrieved_on) === null) throw new Error('retrieved_on must be a valid ISO day.');
      if (!['reference_season','year_specific'].includes(p.baseline_kind)) throw new Error('baseline_kind must be reference_season or year_specific.');
      if (!text(p.measure) || !text(p.unit)) throw new Error('A phenology measure and unit are required.');
      const start = strictDate(p.season_start), end = strictDate(p.season_end);
      if (start === null || end === null || end < start) throw new Error('Invalid phenology season interval.');
      if (!Array.isArray(p.bins)) throw new Error('Phenology bins must be an array.');
      let previous = start-1;
      const bins = p.bins.map(bin => {
        const s = strictDate(bin.start), e = strictDate(bin.end);
        if (s === null || e === null || s > e || s <= previous || s < start || e > end) throw new Error(`${p.profile_id}: bins must be ordered, nonoverlapping ISO-day intervals inside the season.`);
        if (bin.value !== null && (!finite(bin.value) || bin.value < 0)) throw new Error('Bin value must be a nonnegative number or null.');
        previous = e;
        return {...bin, s, e};
      });
      let anchor;
      if (p.anchor) {
        const early = strictDate(p.anchor.earliest), late = strictDate(p.anchor.latest);
        if (early === null || late === null || early > late || early < start || late > end || !text(p.anchor.label) || !text(p.anchor.basis)) throw new Error('A supplied anchor requires a valid interval, label, and documented basis.');
        anchor={status:'AVAILABLE', start:early, end:late, label:p.anchor.label, basis:p.anchor.basis, method:'supplied'};
      } else anchor=deriveAnchor(bins);
      return {...p, start, end, bins, anchor};
    });
    return {...raw, profiles};
  }
  function deriveAnchor(bins) {
    const valid=bins.filter(b => b.value !== null);
    if (valid.length < 3) return {status:'INSUFFICIENT_BINS'};
    const max=Math.max(...valid.map(b=>b.value));
    if (max <= 0) return {status:'NO_POSITIVE_VALUES'};
    const peaks=valid.filter(b=>Math.abs(b.value-max) < 1e-12);
    if (peaks.length === valid.length) return {status:'FLAT_PROFILE'};
    if (peaks.some((b,i)=>i>0 && b.s !== peaks[i-1].e+1)) return {status:'AMBIGUOUS_PEAK'};
    return {status:'AVAILABLE', start:peaks[0].s, end:peaks.at(-1).e, label:'Peak supplied bin', basis:'Maximum of supplied nonmissing bins; interval is temporal resolution, not a confidence interval.', method:'maximum_bin'};
  }
  function clockRecord(sample, phenology) {
    const date=dateInterval(sample.collection_date);
    if (!date) return {status:'NO_COLLECTION_DATE'};
    if (!phenology) return {status:'NO_PHENOLOGY'};
    const exact=phenology.profiles.filter(p => keyText(p.scope.host) === keyText(sample.host) && normalizeCountry(p.scope.country) === normalizeCountry(sample.country) && keyText(p.scope.state) === keyText(sample.state) && date.start >= p.start && date.end <= p.end);
    if (!exact.length) return {status:'NO_MATCHING_PROFILE', date};
    if (exact.length !== 1) return {status:'AMBIGUOUS_PROFILE', date};
    const profile=exact[0], anchor=profile.anchor;
    if (anchor.status !== 'AVAILABLE') return {status:anchor.status, date, profile};
    const lower=date.start-anchor.end, upper=date.end-anchor.start;
    return {status:'AVAILABLE', date, profile, anchor, lower, upper, midpoint:(lower+upper)/2};
  }
  function lagText(record) {
    if (record.status !== 'AVAILABLE') return record.status.toLowerCase().replace(/_/g,' ');
    return record.lower === record.upper ? `${signed(record.lower)} days` : `${signed(record.lower)} to ${signed(record.upper)} days`;
  }
  function svg(name, attrs, contents) {
    const n=document.createElementNS('http://www.w3.org/2000/svg',name);
    for (const [k,v] of Object.entries(attrs || {})) n.setAttribute(k,String(v));
    if (contents !== undefined) n.textContent=String(contents);
    return n;
  }
  function buttonNode(n, label, action) {
    n.setAttribute('role','button'); n.setAttribute('tabindex','0'); n.setAttribute('aria-label',label);
    n.addEventListener('click', action);
    n.addEventListener('keydown', e => {if (e.key==='Enter'||e.key===' ') {e.preventDefault();action();}});
    n.appendChild(svg('title',{},label));
    return n;
  }
  class Dashboard {
    constructor(root, payload, options={}) {
      this.root=root; this.options=options; this.payload=payload; this.m=model(payload);
      this.selected=null; this.selectedReference=null; this.host='ALL'; this.includeReferences=false; this.mode='calendar'; this.k=3;
      this.phenology=payload.ecological_clock ? validatePhenology(payload.ecological_clock) : null;
      this.cache=new Map(); this.notice='';
      this.build(); this.refresh();
    }
    color(e) { return e.kind === 'reference' ? '#00828a' : COLORS[this.m.samples.map(s=>s.host).filter((h,i,a)=>a.indexOf(h)===i).indexOf(e.host)%COLORS.length]; }
    build() {
      this.root.classList.add('wbc');
      this.root.innerHTML=`
        <header class="wbc-masthead"><div><span class="wbc-overline">WINGS / OBSERVATORY</span><h2>Eight segments. One ecological story.</h2><p>Follow the same record through the genome. Read its collection date against the bird's seasonal clock.</p></div><span class="wbc-release">RESEARCH PREVIEW <b>v${VERSION}</b></span></header>
        <div class="wbc-banner" role="status"></div>
        <div class="wbc-tools"><label>Focus sample<select class="wbc-sample" aria-label="Braid focus sample"></select></label><label>Host<select class="wbc-host" aria-label="Braid host filter"></select></label><button type="button" class="wbc-clear">Clear focus</button><div class="wbc-file-tools"><label class="wbc-file-button" tabindex="0">Load phenology<input class="wbc-import-phenology" type="file" accept=".json,application/json"></label><button type="button" class="wbc-export">Export evidence</button></div></div>
        <div class="wbc-stats"></div>
        <div class="wbc-workbench"><div class="wbc-card wbc-braid-card"><div class="wbc-card-title"><div><span class="wbc-kicker">01 / GENOME BRAID</span><h3>One identity, eight views</h3></div><label class="wbc-checkbox"><input type="checkbox" class="wbc-references"> Show public links</label></div><div class="wbc-braid-scroll"><div class="wbc-braid"></div></div><div class="wbc-braid-caption"></div><details class="wbc-method"><summary>What the braid does and does not mean</summary><p>Vertical position follows tip order in each supplied tree, restricted to displayed identities. Rotating a tree can change crossings without changing its relationships. Crossings are not a reassortment statistic or a route of transmission. Lines only join adjacent lanes with one unambiguous tip; gaps remain gaps.</p><p>Public records are joined only by supplied reference_id. A metadata-derived linkage remains a candidate, not verified common-specimen identity. Public groups do not enter the sample-neighborhood metric.</p></details></div>
        <div class="wbc-card wbc-focus"><span class="wbc-kicker">EVIDENCE / SELECT A RECORD</span><div class="wbc-evidence" aria-live="polite"></div></div></div>
        <section class="wbc-card wbc-clock-card"><div class="wbc-card-title"><div><span class="wbc-kicker">02 / ECOLOGICAL CLOCK</span><h3>Same observation. A different time axis.</h3></div><div class="wbc-switch" role="group" aria-label="Clock time axis"><button type="button" data-wbc-mode="calendar" aria-pressed="true">Calendar</button><button type="button" data-wbc-mode="ecological" aria-pressed="false">Ecological time</button></div></div><p class="wbc-clock-subtitle"></p><div class="wbc-clock-scroll"><div class="wbc-clock"></div></div><div class="wbc-clock-caption"></div><details class="wbc-method"><summary>Phenology matching, precision, and provenance</summary><p>The clock uses an exact supplied host, country, state, and season match. No species is inferred from a host code. Missing or ambiguous profiles remain unavailable. Collection date is not infection date. Expected seasonal profiles are labeled separately from year-specific estimates.</p><p>Offset interval = [collection start - anchor latest, collection end - anchor earliest]. An interval from a weekly peak bin describes temporal resolution, not a statistical confidence interval. Empty bins are not zero; curves are never extended through missing observations.</p><div class="wbc-provenance"></div></details></section>
        <details class="wbc-card wbc-audit"><summary>Inspect the evidence table</summary><div class="wbc-evidence-table"></div></details>
        <footer class="wbc-footer">Exploratory description, not a risk score. No transmission, reassortment, infection timing, or causal climate effect is inferred. Files stay in this browser; no data are uploaded.</footer>`;
      const q=s=>this.root.querySelector(s);
      q('.wbc-sample').innerHTML='<option value="">Select a sample</option>'+this.m.samples.map(e=>`<option value="${esc(e.id)}">${esc(e.id)}</option>`).join('');
      q('.wbc-host').innerHTML='<option value="ALL">All hosts</option>'+[...new Set(this.m.samples.map(e=>e.host))].map(h=>`<option>${esc(h)}</option>`).join('');
      q('.wbc-sample').addEventListener('change',e=>this.choose(e.target.value ? `s:${e.target.value}` : null, false));
      q('.wbc-host').addEventListener('change',e=>{this.host=e.target.value;this.options.onHost?.(this.host);this.refresh();});
      q('.wbc-clear').addEventListener('click',()=>this.choose(null,false));
      q('.wbc-references').addEventListener('change',e=>{this.includeReferences=e.target.checked;this.refresh();});
      this.root.querySelectorAll('[data-wbc-mode]').forEach(b=>b.addEventListener('click',()=>{this.mode=b.dataset.wbcMode;this.renderClock();}));
      q('.wbc-import-phenology').addEventListener('change',async e=>{
        const f=e.target.files[0]; if (!f) return;
        try {if(f.size>20000000) throw new Error('Phenology file exceeds the 20 MB preview limit.');this.phenology=validatePhenology(JSON.parse(await f.text()));this.notice=`Loaded ${f.name} locally. This import is session-only in an embedded Explorer.`;this.refresh();}
        catch(error){this.notice=`Phenology not loaded: ${error.message}`;this.renderBanner();}
        e.target.value='';
      });
      q('.wbc-file-button').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();q('.wbc-import-phenology').click();}});
      q('.wbc-export').addEventListener('click',()=>this.exportEvidence());
    }
    choose(id, toggle=true) {
      if (id && !this.m.entities.has(id)) return;
      if (this.options.onSelect) {this.options.onSelect(id, toggle);return;}
      if (id?.startsWith('r:')) this.selectedReference=toggle && this.selectedReference===id ? null : id;
      else {this.selected=toggle&&this.selected===id?null:id;this.selectedReference=null;}
      this.refresh();
    }
    sync(state) {
      this.selected=state.sample ? `s:${state.sample}` : null;
      this.selectedReference=state.reference ? `r:${state.reference}` : null;
      this.host=state.host || 'ALL'; this.refresh();
    }
    profile(id) {if (!this.cache.has(`${id}|${this.k}`)) this.cache.set(`${id}|${this.k}`,neighborhoodProfile(this.m,id,this.k));return this.cache.get(`${id}|${this.k}`);}
    visible() {return this.m.samples.filter(e=>this.host==='ALL'||e.host===this.host);}
    renderBanner() {
      const synthetic=this.payload.synthetic===true || this.phenology?.synthetic===true;
      const node=this.root.querySelector('.wbc-banner');
      node.classList.toggle('wbc-is-synthetic',synthetic);
      node.textContent=[synthetic ? 'SYNTHETIC DEMONSTRATION - illustrative tree geometry and/or seasonal profiles; not surveillance findings.' : 'Local Explorer data - existing trees are displayed without rerooting or reinference.',this.notice].filter(Boolean).join(' ');
    }
    refresh() {
      this.renderBanner();
      this.root.querySelector('.wbc-sample').value=this.selected?.slice(2)||'';
      this.root.querySelector('.wbc-host').value=this.host;
      const mapped=this.m.samples.filter(e=>clockRecord(e.raw,this.phenology).status==='AVAILABLE').length;
      const pairInfo=this.selected ? this.profile(this.selected):null;
      this.root.querySelector('.wbc-stats').innerHTML=[['LOCAL SAMPLES',this.m.samples.length,'Identities, not deduplicated specimens'],['SEGMENT TREES',`${Object.keys(this.m.bySegment).length} / 8`,'Supplied tree geometry'],['PHENOLOGY MATCHES',`${mapped} / ${this.m.samples.length}`,'Exact host / place / season'],['SHARED-NEIGHBOR OVERLAP',pairInfo?.mean!==null&&pairInfo ? pct(pairInfo.mean):'Select a sample',pairInfo ? `${pairInfo.available} / 28 available comparisons`:'Descriptive; local sample cohort only']].map(([a,b,c])=>`<div><span>${esc(a)}</span><strong>${esc(b)}</strong><small>${esc(c)}</small></div>`).join('');
      this.renderBraid();this.renderEvidence();this.renderClock();this.renderTable();
    }
    renderBraid() {
      const target=this.root.querySelector('.wbc-braid');target.replaceChildren();
      let ids=this.visible().map(e=>e.key);
      if (this.selected&&!ids.includes(this.selected)) ids.push(this.selected);
      // Bound rendering without sampling the analytical cohort. Always retain focus.
      const totalLocal=ids.length;
      ids=ids.slice(0,60);
      if (this.selected&&!ids.includes(this.selected)) ids.push(this.selected);
      if (this.includeReferences) ids.push(...this.m.references.slice(0,36).map(e=>e.key));
      if (this.selectedReference&&!ids.includes(this.selectedReference)) ids.push(this.selectedReference);
      const W=980,H=Math.max(320,Math.min(620,ids.length*12+105)),left=45,right=45,top=58,bottom=34;
      const el=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'group','aria-label':'Genome Braid. Lines connect the same supplied identity across segment trees.'});
      const positions={};
      SEGMENTS.forEach((segment,i)=>{
        const x=left+i*(W-left-right)/7,tree=this.m.bySegment[segment];
        const lane=svg('g',{});
        lane.append(svg('line',{x1:x,y1:top-8,x2:x,y2:H-bottom,stroke:'#d7dce1','stroke-dasharray':tree?'none':'4 4'}));
        lane.append(svg('text',{x,y:24,'text-anchor':'middle',class:'wbc-lane-label'},segment));
        const inLane=ids.filter(id=>presence(this.m,id,segment).status==='PRESENT').sort((a,b)=>tree.index.get(a)[0].order-tree.index.get(b)[0].order);
        positions[segment]=new Map(inLane.map((id,j)=>[id,{x,y:top+(j+0.5)*(H-top-bottom)/Math.max(inLane.length,1)}]));
        lane.append(svg('text',{x,y:42,'text-anchor':'middle',class:'wbc-small'},tree?`${inLane.length} shown`:'No tree'));
        el.append(lane);
      });
      const focused=this.selectedReference||this.selected;
      const ordered=ids.slice().sort((a,b)=>Number(a===focused)-Number(b===focused));
      for(const id of ordered){
        const e=this.m.entities.get(id);if(!e)continue;
        const active=id===this.selected||id===this.selectedReference;
        const group=svg('g',{'data-wbc-entity':id,class:`wbc-strand${active?' wbc-active':''}`,'aria-pressed':String(active)});
        for(let i=0;i<7;i++){
          const a=positions[SEGMENTS[i]].get(id),b=positions[SEGMENTS[i+1]].get(id);if(!a||!b)continue;
          const dx=(b.x-a.x)*0.43;
          group.append(svg('path',{d:`M ${a.x} ${a.y} C ${a.x+dx} ${a.y}, ${b.x-dx} ${b.y}, ${b.x} ${b.y}`,fill:'none',stroke:this.color(e),'stroke-width':active?3.5:e.kind==='reference'?1.1:1.6,opacity:focused&&!active?0.15:e.kind==='reference'?0.38:0.62}));
        }
        for(const segment of SEGMENTS){const p=positions[segment].get(id);if(!p)continue;
          const attrs={fill:this.color(e),stroke:active?'#fff':'none','stroke-width':1.6};
          group.append(e.kind==='reference'?svg('rect',{x:p.x-4,y:p.y-4,width:8,height:8,...attrs}):svg('circle',{cx:p.x,cy:p.y,r:active?5:3,...attrs}));
        }
        buttonNode(group,`${e.kind==='sample'?'Sample':'Public reference'} ${e.label}. ${SEGMENTS.filter(s=>presence(this.m,id,s).status==='PRESENT').length} of 8 segment trees.`,()=>this.choose(id));
        el.append(group);
      }
      target.append(el);
      const outside=this.selected&&this.host!=='ALL'&&this.m.entities.get(this.selected)?.host!==this.host;
      this.root.querySelector('.wbc-braid-caption').innerHTML=`<span class="wbc-dot"></span> Circles: WINGS samples &nbsp; <span class="wbc-square"></span> Squares: public groups as supplied. Gaps: no unambiguous tip.<br><small>${esc(outside?'Selected sample is outside the host filter and remains visible. ': '')}${totalLocal>60?`Showing up to 60 of ${totalLocal} local samples plus focus. `:''}${this.includeReferences?`Showing up to 36 public groups in source order, plus focus. `:''}Tip order is a layout choice, not evolutionary distance.</small>`;
    }
    renderEvidence() {
      const id=this.selectedReference||this.selected,e=this.m.entities.get(id),target=this.root.querySelector('.wbc-evidence');
      if(!e){target.innerHTML='<div class="wbc-empty-focus"><span class="wbc-focus-icon">8</span><h3>Follow one record</h3><p>Select a strand or use the sample menu. The braid and clock share one focus.</p><p>Nothing is scored simply because two strands cross.</p></div>';return;}
      const c=e.kind==='sample'?clockRecord(e.raw,this.phenology):{status:'PUBLIC_CLOCK_NOT_COMPUTED'}, p=e.kind==='sample'?this.profile(id):null;
      const count=SEGMENTS.filter(s=>presence(this.m,id,s).status==='PRESENT').length;
      const matrix=SEGMENTS.map(a=>`<tr><th>${a}</th>${SEGMENTS.map(b=>{if(a===b)return '<td class="wbc-diagonal">-</td>';const pair=p?.pairs.find(v=>v.segments.includes(a)&&v.segments.includes(b));return `<td title="${esc(pair?`${pair.status}; ${pair.shared} shared comparison samples`:'Not computed')}">${pair?.overlap!==null&&pair?.overlap!==undefined?Math.round(pair.overlap*100):'&middot;'}</td>`;}).join('')}</tr>`).join('');
      target.innerHTML=`<h3 class="wbc-focus-name">${esc(e.label)}</h3><p>${esc(e.host)}<br>${esc(e.raw.collection_date||'Date not recorded')} &middot; ${esc(e.raw.state||e.raw.country||'Place not recorded')}</p><div class="wbc-chips"><span>${esc(e.kind==='sample'?genotype(e.raw):'Public group')}</span><span>${count} / 8 trees</span></div><div class="wbc-presence">${SEGMENTS.map(s=>`<span class="${presence(this.m,id,s).status==='PRESENT'?'wbc-present':''}" title="${esc(presence(this.m,id,s).status)}">${s}</span>`).join('')}</div><h4>Ecological timing</h4><div class="wbc-lag">${esc(c.status==='AVAILABLE'?lagText(c):'Unavailable')}</div><p class="wbc-muted">${esc(c.status==='AVAILABLE'?`Relative to ${c.anchor.label.toLowerCase()}. ${c.profile.baseline_kind==='reference_season'?'Expected seasonal reference; not realized migration timing.':'Year-specific supplied profile.'}`:lagText(c))}</p>${p?`<h4>Shared-neighbor overlap</h4><strong class="wbc-score">${pct(p.mean)}</strong><p class="wbc-muted">${p.available} of 28 segment-pair comparisons available. Three nearest other WINGS samples, evaluated on the shared identities for each pair.</p><details><summary>Comparison matrix (%)</summary><div class="wbc-matrix-scroll"><table class="wbc-matrix"><thead><tr><th></th>${SEGMENTS.map(s=>`<th>${s}</th>`).join('')}</tr></thead><tbody>${matrix}</tbody></table></div><p class="wbc-muted">Mean Jaccard overlap; unavailable and tied-cutoff pairs are omitted, not scored zero. This is descriptive, not a support probability, validated concordance score, or reassortment test. No tree-support threshold is applied.</p></details>`:`<p class="wbc-muted">Linkage basis: ${esc(e.raw.linkage_basis||'Not recorded')}. Public groups are not included in the sample-neighborhood score.</p>`}`;
    }
    renderClock() {
      this.root.querySelectorAll('[data-wbc-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.wbcMode===this.mode)));
      const target=this.root.querySelector('.wbc-clock');target.replaceChildren();
      const visible=this.visible(),records=visible.map(e=>({entity:e,c:clockRecord(e.raw,this.phenology)}));
      if(this.selected&&!visible.some(e=>e.key===this.selected)){const e=this.m.entities.get(this.selected);if(e)records.push({entity:e,c:clockRecord(e.raw,this.phenology)});}
      const available=records.filter(r=>r.c.status==='AVAILABLE');
      const profiles=[...new Map(available.map(r=>[r.c.profile.profile_id,r.c.profile])).values()];
      const subtitle=this.root.querySelector('.wbc-clock-subtitle'),caption=this.root.querySelector('.wbc-clock-caption');
      if(!profiles.length){
        subtitle.textContent=this.mode==='calendar'?'Collection dates remain visible without a seasonal anchor.':'Ecological time is unavailable until a matching phenology profile is supplied.';
        if(this.mode==='calendar')this.renderCalendarOnly(target,records);
        else target.innerHTML='<div class="wbc-no-data"><h4>No defensible seasonal anchor yet</h4><p>Load a documented host-and-region phenology JSON. Existing eBird window aggregates, weather values, and aggregate radar counts are not silently converted into species arrival dates.</p></div>';
        caption.textContent=`${records.length} sample records; 0 assigned an ecological offset. Missing information is not zero.`;
        this.renderProvenance([]);return;
      }
      subtitle.textContent=this.mode==='calendar'?'Collection dates and supplied seasonal profiles on the calendar.':'Each profile is centered on its own seasonal anchor. Sample intervals retain collection-date and anchor precision.';
      let shown=profiles.slice(0,8);
      const focus=records.find(r=>r.entity.key===this.selected)?.c.profile;
      if(focus&&!shown.includes(focus)){shown=shown.slice(0,7).concat(focus);}
      const W=1240,left=225,right=40,rowH=106,top=36,H=top+shown.length*rowH+48;
      const ranges=shown.flatMap(p=>this.mode==='calendar'?[p.start,p.end]:[p.start-mid(p.anchor),p.end-mid(p.anchor)]);
      let low=Math.min(...ranges),high=Math.max(...ranges);if(high===low)high++;
      const x=n=>left+(n-low)/(high-low)*(W-left-right);
      const el=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'group','aria-label':`Ecological Clock, ${this.mode} axis`});
      for(let i=0;i<=5;i++){const v=low+(high-low)*i/5;const label=this.mode==='calendar'?isoDay(v):`${signed(Math.round(v))} d`;el.append(svg('line',{x1:x(v),x2:x(v),y1:top-10,y2:H-35,stroke:'#e4e8eb'}),svg('text',{x:x(v),y:H-12,'text-anchor':'middle',class:'wbc-tick'},label));}
      shown.forEach((p,i)=>{
        const y=top+i*rowH,base=y+66;
        const anchorMid=mid(p.anchor),off=this.mode==='calendar'?0:anchorMid;
        const peakX=x(p.anchor.start-off),peakEnd=x(p.anchor.end-off);
        el.append(svg('rect',{x:peakX,y:y-7,width:Math.max(2,peakEnd-peakX),height:80,fill:'#efddb1',opacity:.55}));
        el.append(svg('text',{x:14,y:y+14,class:'wbc-row-title'},p.scope.host),svg('text',{x:14,y:y+33,class:'wbc-small'},`${p.scope.state} / ${p.baseline_kind==='reference_season'?'expected season':'year-specific'}`));
        el.append(svg('text',{x:14,y:y+51,class:'wbc-small'},`${p.season_start.slice(0,4)} / ${p.measure}`));
        const max=Math.max(1e-10,...p.bins.filter(b=>b.value!==null).map(b=>b.value));
        for(const b of p.bins){if(b.value===null)continue;const height=b.value/max*45;const rect=svg('rect',{x:x(b.s-off),y:base-height,width:Math.max(1,x(b.e+1-off)-x(b.s-off)-1),height,fill:'#70b0b2',opacity:.48});rect.append(svg('title',{},`${b.start} to ${b.end}: ${b.value} ${p.unit}`));el.append(rect);}
        el.append(svg('line',{x1:left,x2:W-right,y1:base,y2:base,stroke:'#a9b4bd'}));
        const cohort=available.filter(r=>r.c.profile.profile_id===p.profile_id);
        cohort.forEach((r,j)=>{
          const c=r.c,s=this.mode==='calendar'?c.date.start:c.lower,e=this.mode==='calendar'?c.date.end:c.upper;
          const yy=base+13+(j%2)*9,active=r.entity.key===this.selected;
          const mark=svg('g',{'data-wbc-clock-sample':r.entity.id,class:active?'wbc-clock-active':''});
          mark.append(svg('line',{x1:x(s),x2:x(e),y1:yy,y2:yy,stroke:this.color(r.entity),'stroke-width':3}));
          mark.append(svg('circle',{cx:x((s+e)/2),cy:yy,r:active?7:4.5,fill:this.color(r.entity),stroke:active?'#f4c652':'#fff','stroke-width':active?3:1}));
          buttonNode(mark,`${r.entity.id}: ${r.entity.raw.collection_date}; ${lagText(c)} relative to ${c.anchor.label}`,()=>this.choose(r.entity.key));el.append(mark);
        });
      });
      if(this.mode==='ecological'&&low<=0&&high>=0)el.append(svg('line',{x1:x(0),x2:x(0),y1:15,y2:H-35,stroke:'#8f691e','stroke-dasharray':'4 5'}),svg('text',{x:x(0),y:12,'text-anchor':'middle',class:'wbc-anchor-label'},'Seasonal anchor'));
      target.append(el);
      caption.textContent=`${available.length} / ${records.length} visible sample records have an exact profile match. ${records.length-available.length} remain unavailable in ecological time. ${profiles.length>8?'Showing at most 8 profile rows plus selected focus. ':''}Bars are scaled within each profile; heights are not comparable abundance between hosts. Gold bands show anchor intervals, not infection windows.`;
      this.renderProvenance(shown);
    }
    renderCalendarOnly(target,records) {
      const dated=records.filter(r=>r.c.date||dateInterval(r.entity.raw.collection_date));
      if(!dated.length){target.innerHTML='<div class="wbc-no-data">No valid collection dates are available.</div>';return;}
      const data=dated.map(r=>({...r,date:r.c.date||dateInterval(r.entity.raw.collection_date)})),W=1100,H=120,left=32,right=32;
      const low=Math.min(...data.map(r=>r.date.start))-7,high=Math.max(...data.map(r=>r.date.end))+7,x=n=>left+(n-low)/(high-low)*(W-left-right);
      const el=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'group','aria-label':'Collection dates without phenology anchors'});
      el.append(svg('line',{x1:left,x2:W-right,y1:65,y2:65,stroke:'#bec8ce'}));
      data.forEach((r,i)=>{const y=40+(i%3)*13,g=svg('g',{});g.append(svg('line',{x1:x(r.date.start),x2:x(r.date.end),y1:y,y2:y,stroke:this.color(r.entity),'stroke-width':3}),svg('circle',{cx:x(mid(r.date)),cy:y,r:5,fill:this.color(r.entity)}));buttonNode(g,`${r.entity.id}; ${r.date.raw}`,()=>this.choose(r.entity.key));el.append(g);});
      for(let i=0;i<=4;i++){const d=low+(high-low)*i/4;el.append(svg('text',{x:x(d),y:97,'text-anchor':'middle',class:'wbc-small'},isoDay(d)));}
      target.append(el);
    }
    renderProvenance(profiles) {
      this.root.querySelector('.wbc-provenance').innerHTML=profiles.length?profiles.map(p=>`<p><b>${esc(p.profile_id)}</b> &middot; ${esc(p.provenance.source)}<br>${esc(p.provenance.citation)}<br>Retrieved ${esc(p.provenance.retrieved_on)}. ${esc(p.provenance.method)}<br>Anchor: ${esc(p.anchor.label)} (${isoDay(p.anchor.start)} to ${isoDay(p.anchor.end)}). ${esc(p.anchor.basis)}</p>`).join(''):'<p>No matching phenology source has been loaded. No seasonal timing has been inferred.</p>';
    }
    evidenceRows() {
      return this.m.samples.map(e=>{const c=clockRecord(e.raw,this.phenology);return {sample_id:e.id,host:e.host,collection_date:text(e.raw.collection_date),genotype:genotype(e.raw),tree_presence:Object.fromEntries(SEGMENTS.map(s=>[s,presence(this.m,e.key,s).status])),clock_status:c.status,profile_id:c.profile?.profile_id||null,baseline_kind:c.profile?.baseline_kind||null,offset_min_days:c.lower??null,offset_max_days:c.upper??null};});
    }
    renderTable() {
      this.root.querySelector('.wbc-evidence-table').innerHTML='<table><thead><tr><th>Sample</th><th>Host</th><th>Collection date</th><th>Clock status</th><th>Offset interval (days)</th></tr></thead><tbody>'+this.evidenceRows().map(r=>`<tr><td>${esc(r.sample_id)}</td><td>${esc(r.host)}</td><td>${esc(r.collection_date)}</td><td>${esc(r.clock_status)}</td><td>${r.offset_min_days===null?'Not available':`${signed(r.offset_min_days)} to ${signed(r.offset_max_days)}`}</td></tr>`).join('')+'</tbody></table>';
    }
    exportEvidence() {
      const report={schema_version:'wings.braid-clock-evidence.v1',version:VERSION,input_provenance:this.payload.braid_clock_build||null,synthetic:this.payload.synthetic===true||this.phenology?.synthetic===true,samples:this.evidenceRows(),focused_neighborhood:this.selected?this.profile(this.selected):null,tree_sources:Object.fromEntries(Object.entries(this.m.bySegment).map(([s,t])=>[s,{file:t.source.source_file||null,sha256:t.source.source_sha256||null}])),phenology:this.phenology?{synthetic:this.phenology.synthetic,profiles:this.phenology.profiles.map(p=>({profile_id:p.profile_id,provenance:p.provenance,anchor:p.anchor}))}:null,warnings:this.m.warnings,limitations:['Descriptive overlap is not a reassortment test, support probability, or risk score.','Phenology offsets concern collection timing, not infection timing.','Source identities are not automatically deduplicated biological specimens.']};
      const blob=new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='wings-braid-clock-evidence.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
  }
  function mount(root,payload,options) {return new Dashboard(root,payload,options);}
  function mountExplorer(explorer) {
    if(explorer.braidClock)return explorer.braidClock;
    const parent=explorer.root.querySelector('.wse-shell')||explorer.root;
    const host=document.createElement('section');host.className='wbc-embedded';
    parent.insertBefore(host,parent.querySelector('.wse-genome-panel'));
    const update=explorer.updateSelection.bind(explorer);
    const app=mount(host,explorer.payload,{
      onSelect:(id,toggle)=>{
        if(!id){explorer.selectedSampleId=null;explorer.selectedReferenceId=null;}
        else if(id.startsWith('s:')){const sid=id.slice(2);explorer.selectedSampleId=toggle&&explorer.selectedSampleId===sid?null:sid;explorer.selectedReferenceId=null;}
        else {const rid=id.slice(2);explorer.selectedReferenceId=toggle&&explorer.selectedReferenceId===rid?null:rid;}
        explorer.hoverSampleId=null;explorer.updateSelection();
      },
      onHost:host=>{explorer.hostFilter=host;explorer.renderTimeline();explorer.renderMap();explorer.renderLegend();explorer.renderTrees();explorer.updateSelection();}
    });
    explorer.updateSelection=function(...args){const result=update(...args);app.sync({sample:this.selectedSampleId,reference:this.selectedReferenceId,host:this.hostFilter});return result;};
    explorer.braidClock=app;
    app.sync({sample:explorer.selectedSampleId,reference:explorer.selectedReferenceId,host:explorer.hostFilter});
    return app;
  }
  return {VERSION,SEGMENTS,strictDate,dateInterval,model,presence,distance,nearest,neighborhoodProfile,deriveAnchor,validatePhenology,clockRecord,lagText,mount,mountExplorer};
});
/* WINGS_BRAID_CLOCK_JS_END */
(() => {
  "use strict";

  const HOST_COLORS = ["#8C1D40", "#006DAE", "#176B3A", "#6F2DA8", "#C45500", "#00838F", "#5C1229", "#7D6608", "#37474F"];
  const GOLD = "#FFC627";
  const RED = "#B3261E";
  const GREEN = "#176B3A";
  const GRAY = "#AEB4BC";
  const INK = "#202124";

  const svgEl = (name, attrs = {}) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
    return el;
  };

  const esc = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  const formatNumber = (value, digits = 0) => {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString(undefined, {maximumFractionDigits: digits}) : "NA";
  };

  const parseDate = (value) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return null;
    const [y, m, d] = value.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d));
  };

  const dateLabel = (value) => {
    const d = parseDate(value);
    return d ? d.toLocaleDateString(undefined, {year:"numeric", month:"short", day:"numeric", timeZone:"UTC"}) : String(value || "Unknown");
  };

  const monthLabel = (d) => d.toLocaleDateString(undefined, {year:"2-digit", month:"short", timeZone:"UTC"});

  const statusClass = (status) => {
    const s = String(status || "").toUpperCase();
    if (s === "DETECTED") return "is-detected";
    if (s === "NOT_DETECTED") return "is-clear";
    return "is-indeterminate";
  };

  class Explorer {
    constructor(root, payload) {
      this.root = root;
      this.payload = payload;
      this.samples = Array.isArray(payload.samples) ? payload.samples : [];
      this.sampleById = new Map(this.samples.map((sample) => [sample.sample_id, sample]));
      this.referenceContext = payload.public_reference_context || null;
      this.references = Array.isArray(this.referenceContext?.references) ? this.referenceContext.references : [];
      this.referenceById = new Map(this.references.map(ref => [ref.reference_id, ref]));
      this.selectedReferenceId = null;
      this.ebirdContexts = Array.isArray(payload.ebird_contexts) ? payload.ebird_contexts : [];
      this.ebirdAttribution = payload.ebird_attribution || null;
      this.ecology = payload.ecological_context || null;
      this.ecologyDays = 30;
      this.hosts = [...new Set([
        ...(Array.isArray(payload.hosts) ? payload.hosts : []),
        ...this.samples.map((sample) => sample.host).filter(Boolean),
      ])];
      this.hostColor = new Map(this.hosts.map((host, i) => [host, HOST_COLORS[i % HOST_COLORS.length]]));
      this.segments = (payload.segment_order || []).filter((segment) => payload.trees && payload.trees[segment]);
      this.segment = this.segments.includes("HA") ? "HA" : (this.segments[0] || null);
      this.treeMode = "all";
      this.hostFilter = "ALL";
      this.selectedSampleId = null;
      this.hoverSampleId = null;
      this.clusterCursor = new Map();
      this.mapView = "samples";
      this.mapViewport = null;
      this.mapBoundaries = globalThis.WINGS_MAP_BOUNDARIES || null;
      this.outbreakContext = payload.outbreak_context || null;
      this.outbreakLayerEnabled = true;
      this.outbreakScope = "sample";
      this.outbreakBasis = "collection_date";
      this.outbreakFollow = true;
      this.outbreakDays = 30;
      this.outbreakStart = "";
      this.outbreakEnd = "";
      this.outbreakPage = 0;
      this.render();
    }

    visibleSamples() {
      return this.samples.filter((sample) => this.hostFilter === "ALL" || sample.host === this.hostFilter);
    }

    hostColorFor(sample) {
      return this.hostColor.get(sample.host) || "#5F6368";
    }

    selectSample(sampleId) {
      if (!this.sampleById.has(sampleId)) return;
      this.selectedReferenceId = null;
      this.selectedSampleId = this.selectedSampleId === sampleId ? null : sampleId;
      this.hoverSampleId = null;
      this.updateSelection();
    }

    selectReference(referenceId) {
      if (!this.referenceById.has(referenceId)) return;
      this.selectedReferenceId = this.selectedReferenceId === referenceId ? null : referenceId;
      this.hoverSampleId = null;
      this.updateSelection();
    }

    setHover(sampleId) {
      this.hoverSampleId = sampleId;
      this.updateEmphasis();
    }

    clearHover() {
      this.hoverSampleId = null;
      this.updateEmphasis();
    }

    render() {
      this.root.innerHTML = `
        <div class="wse-shell">
          <div class="wse-heading">
            <div>
              <div class="wse-eyebrow">Run-level genomic surveillance</div>
              <div class="wse-title">WINGS Surveillance Explorer</div>
              <div class="wse-subtitle">Linked collection timeline, geospatial context, and segment-specific phylogeny. Click any sample on the timeline, map, or phylogeny to select it and highlight it across all views.</div>
            </div>
            <div class="wse-heading-accent" aria-hidden="true"></div>
          </div>
          <div class="wse-metrics"></div>
          <div class="wse-selected" aria-live="polite" hidden></div>
          <section class="wse-panel wse-timeline-panel">
            <div class="wse-panel-heading"><div><span class="wse-panel-kicker">When</span><h3>Collection timeline</h3></div><div class="wse-panel-note">Circle color = host</div></div>
            <div class="wse-timeline"></div>
          </section>
          <div class="wse-main-grid">
            <section class="wse-panel wse-map-panel">
              <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Where</span><h3>Samples and outbreak context</h3></div><div class="wse-panel-note wse-map-count"></div></div>
              <div class="wse-map-toolbar"><label>Map extent <select class="wse-map-view"><option value="samples">Sample area</option><option value="north-america">North America</option><option value="world">World</option><option value="custom" disabled>Custom view</option></select></label><div class="wse-map-navigation" role="group" aria-label="Map navigation"><button type="button" class="wse-map-zoom-in" aria-label="Zoom in">+</button><button type="button" class="wse-map-zoom-out" aria-label="Zoom out">−</button><button type="button" class="wse-map-reset">Reset view</button><button type="button" class="wse-map-show-state" disabled>Select a state to zoom</button></div><span class="wse-map-help">Drag to pan. Focus the map for arrow keys, +/−, or 0 to reset.</span></div>
              <div class="wse-map-layers" hidden><label><input type="checkbox" class="wse-aphis-layer-toggle" checked> APHIS state shading</label><span>Points = WINGS samples · Shading = APHIS source records</span></div>
              <div class="wse-map-frame">
                <div class="wse-map" tabindex="0" role="group" aria-label="Interactive sampling map. Drag to pan; arrow keys move the view; plus and minus zoom; zero resets."></div>
                <div class="wse-map-state-card" aria-live="polite" hidden></div>
              </div>
              <div class="wse-map-layer-legend" aria-live="polite" hidden></div>
              <div class="wse-map-selection" aria-live="polite" aria-atomic="true"></div>
              <div class="wse-map-attribution">Country outlines worldwide; U.S. states and Canadian provinces/territories. Generalized boundaries from <a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener noreferrer">Natural Earth</a>. Sample-area extent stays fixed when filtering hosts.</div>
              <div class="wse-host-legend"></div>
              <div class="wse-outbreak-panel" hidden></div>
            </section>
          </div>
          <section class="wse-panel wse-genome-panel">
            <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Linked evidence</span><h3>Eight-segment genome explorer</h3></div><div class="wse-panel-note">One sample selection across all available trees</div></div>
            <div class="wse-genome-controls"></div>
            <div class="wse-genome-evidence"></div>
            <div class="wse-reference-details" aria-live="polite"></div>
            <div class="wse-segment-tabs" role="group" aria-label="Phylogeny segment"></div>
            <div class="wse-tree-note wse-panel-note"></div>
            <div class="wse-tree"></div>
            <div class="wse-tree-grid"></div>
          </section>
          <div class="wse-footer-note">When the optional phylogeny stage is enabled, WINGS infers segment trees from QC-passing consensus sequences. Otherwise, the Explorer displays available external trees. Trees are displayed without rerooting or time calibration. Collection dates come from metadata, not tip labels.</div>
          <section class="wse-panel wse-ecology-panel">
            <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Ecological context</span><h3>Host reporting, migration, and weather</h3></div><label>Display window ± <select class="wse-ecology-days"><option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option></select></label></div>
            <div class="wse-ecology-intro" aria-live="polite"></div>
            <section class="wse-ecology-source wse-ebird-panel">
              <h4>eBird · Host reporting frequency</h4>
              <div class="wse-ebird"></div>
              <div class="wse-ecology-ebird-charts"></div>
            </section>
            <section class="wse-ecology-source"><h4>BirdCast · Nocturnal migration pilot</h4><div class="wse-ecology-birdcast"></div></section>
            <section class="wse-ecology-source"><h4>Weather · Historical reanalysis</h4><div class="wse-ecology-weather"></div></section>
            <div class="wse-ecology-provenance"></div>
          </section>
        </div>`;

      this.ecologyNode = this.root.querySelector(".wse-ecology-panel");
      this.ecologyNode.querySelector(".wse-ecology-days").addEventListener("change", event => {
        this.ecologyDays = Number(event.target.value);
        this.renderEcology();
      });
      this.outbreakNode = this.root.querySelector(".wse-outbreak-panel");
      this.bindOutbreakControls();
      this.metricsNode = this.root.querySelector(".wse-metrics");
      this.selectedNode = this.root.querySelector(".wse-selected");
      this.timelineNode = this.root.querySelector(".wse-timeline");
      this.ebirdPanelNode = this.root.querySelector(".wse-ebird-panel");
      this.ebirdNode = this.root.querySelector(".wse-ebird");
      this.mapNode = this.root.querySelector(".wse-map");
      this.mapSelectionNode = this.root.querySelector(".wse-map-selection");
      this.mapLayerLegendNode = this.root.querySelector(".wse-map-layer-legend");
      this.mapStateCardNode = this.root.querySelector(".wse-map-state-card");
      this.mapStateCardNode.addEventListener("click", event => {
        const action = event.target.closest("[data-state-action]")?.dataset.stateAction;
        if (action === "zoom") this.showSelectedState();
        if (action === "close") { this.mapStateCardDismissed = true; this.mapStateCardNode.hidden = true; }
        if (action === "records") {
          const records = this.outbreakNode.querySelector(".wse-outbreak-records");
          if (records) { records.open = true; records.scrollIntoView({behavior:"smooth", block:"start"}); records.querySelector("summary")?.focus({preventScroll:true}); }
        }
      });
      this.mapStateButtonNode = this.root.querySelector(".wse-map-show-state");
      this.mapStateButtonNode.addEventListener("click", () => this.showSelectedState());
      this.root.querySelector(".wse-map-layers").hidden = this.outbreakContext?.status !== "READY";
      this.root.querySelector(".wse-aphis-layer-toggle").addEventListener("change", event => {
        this.outbreakLayerEnabled = event.target.checked;
        this.renderMap();
        this.updateEmphasis();
      });
      this.root.querySelector(".wse-map-view").addEventListener("change", event => {
        this.mapView = event.target.value;
        this.mapViewport = null;
        this.refreshMapView();
      });
      this.mapCountNode = this.root.querySelector(".wse-map-count");
      this.root.querySelector(".wse-map-zoom-in").addEventListener("click", () => this.zoomMap(1 / 1.5));
      this.root.querySelector(".wse-map-zoom-out").addEventListener("click", () => this.zoomMap(1.5));
      this.root.querySelector(".wse-map-reset").addEventListener("click", () => this.resetMapView());
      this.bindMapNavigation();
      this.legendNode = this.root.querySelector(".wse-host-legend");
      this.segmentTabsNode = this.root.querySelector(".wse-segment-tabs");
      this.treeNode = this.root.querySelector(".wse-tree");
      this.treeNoteNode = this.root.querySelector(".wse-tree-note");
      this.treeGridNode = this.root.querySelector(".wse-tree-grid");
      this.referenceNode = this.root.querySelector(".wse-reference-details");
      this.evidenceNode = this.root.querySelector(".wse-genome-evidence");
      this.genomeControlsNode = this.root.querySelector(".wse-genome-controls");

      this.renderMetrics();
      this.renderGenomeControls();
      this.renderSegmentTabs();
      this.renderTimeline();
      this.renderEbird();
      this.renderEcology();
      this.renderMap();
      this.renderTrees();
      this.renderLegend();
      this.updateSelection();
    }

    renderMetrics() {
      const s = this.payload.summary || {};
      const treeCount = Object.keys(this.payload.trees || {}).length;
      this.metricsNode.innerHTML = [
        ["Samples", formatNumber(s.sample_count ?? this.samples.length)],
        ["Geolocated", `${formatNumber(s.geolocated_count ?? 0)} / ${formatNumber(s.sample_count ?? this.samples.length)}`],
        ["Collection dates", formatNumber(s.date_count ?? 0)],
        ["Host groups", formatNumber(s.host_count ?? this.hosts.length)],
        ["Segment trees", `${formatNumber(treeCount)} / 8`],
      ].map(([label, value]) => `<div class="wse-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
    }

    renderSegmentTabs() {
      if (!this.segmentTabsNode) return;

      const order = this.payload.segment_order || [];
      this.segmentTabsNode.innerHTML = order.map((segment) => {
        const available = Boolean(this.payload.trees?.[segment]);
        const active = this.treeMode === "single" && segment === this.segment;
        return `<button
          type="button"
          class="wse-segment-tab${active ? " is-active" : ""}"
          data-segment="${esc(segment)}"
          aria-pressed="${active ? "true" : "false"}"
          ${available ? "" : "disabled"}
        >${esc(segment)}</button>`;
      }).join("");

      this.segmentTabsNode.querySelectorAll(".wse-segment-tab").forEach((button) => {
        button.addEventListener("click", () => {
          if (button.disabled) return;

          this.segment = button.dataset.segment;
          this.treeMode = "single";
          this.genomeControlsNode.querySelector(".wse-view-select").value = "single";
          this.renderSegmentTabs();
          this.renderTrees();
          this.updateSelection();
        });
      });
    }

    renderGenomeControls() {
      this.genomeControlsNode.innerHTML = `
        <label>Sample<select class="wse-sample-select" aria-label="Selected sample"><option value="">Select a sample…</option>${this.samples.map(sample => `<option value="${esc(sample.sample_id)}">${esc(sample.sample_id)}</option>`).join("")}</select></label>
        <label>Public reference<select class="wse-reference-select" aria-label="Selected public reference" ${this.references.length ? "" : "disabled"}><option value="">${this.references.length ? "Select a public reference…" : "No reference manifest loaded"}</option>${this.references.map(ref => `<option value="${esc(ref.reference_id)}">${esc(ref.isolate || ref.reference_id)}</option>`).join("")}</select></label>
        <label>Tree view<select class="wse-view-select"><option value="all">All eight segments</option><option value="single">Single segment</option></select></label>
        <button type="button" class="wse-clear-selection">Clear selection</button>`;
      this.genomeControlsNode.querySelector(".wse-sample-select").addEventListener("change", event => {
        this.selectedReferenceId = null;
        this.selectedSampleId = this.sampleById.has(event.target.value) ? event.target.value : null;
        this.hoverSampleId = null;
        this.updateSelection();
      });
      this.genomeControlsNode.querySelector(".wse-reference-select")?.addEventListener("change", event => {
        this.selectedReferenceId = this.referenceById.has(event.target.value) ? event.target.value : null;
        this.hoverSampleId = null;
        this.updateSelection();
      });
      this.genomeControlsNode.querySelector(".wse-view-select").addEventListener("change", event => {
        this.treeMode = event.target.value;
        this.renderSegmentTabs();
        this.renderTrees();
        this.updateSelection();
      });
      this.genomeControlsNode.querySelector(".wse-clear-selection").addEventListener("click", () => {
        this.selectedReferenceId = null;
        this.selectedSampleId = null;
        this.hoverSampleId = null;
        this.treeMode = "all";
        this.genomeControlsNode.querySelector(".wse-view-select").value = "all";
        this.renderSegmentTabs();
        this.renderTrees();
        this.updateSelection();
      });
    }

    setHostFilter(host) {
      this.hostFilter = host;
      this.renderTimeline();
      this.renderEbird();
      this.renderEcology();
      this.renderMap();
      this.renderTrees();
      this.renderLegend();
      this.updateSelection();
    }

    renderSelected() {
      const sample = this.sampleById.get(this.selectedSampleId);
      if (!sample) {
        this.selectedNode.hidden = true;
        this.selectedNode.innerHTML = "";
        return;
      }
      this.selectedNode.hidden = false;
      const location = sample.has_coordinates
        ? `${sample.state}, ${sample.country} · ${Number(sample.latitude).toFixed(3)}, ${Number(sample.longitude).toFixed(3)}`
        : `${sample.state}, ${sample.country} · coordinates unavailable`;
      const tags = [];
      if (sample.potential_subtype && sample.potential_subtype !== "Undetermined") {
        tags.push(`<span>${esc(sample.potential_subtype)}</span>`);
      }
      if (sample.h5_status && sample.h5_status !== "NOT_RECORDED") {
        tags.push(`<span class="${statusClass(sample.h5_status)}">H5 ${esc(String(sample.h5_status).replaceAll("_", " "))}</span>`);
      }
      if (sample.segments_pass != null) {
        tags.push(`<span>${esc(`${sample.segments_pass}/8`)} segments pass</span>`);
      }
      this.selectedNode.innerHTML = `
        <div class="wse-selected-color" style="--host-color:${this.hostColorFor(sample)}"></div>
        <div class="wse-selected-main">
          <span class="wse-selected-kicker">Selected sample</span>
          <strong>${esc(sample.sample_id)}</strong>
          <small>${esc(sample.host)} · ${esc(dateLabel(sample.collection_date))} · ${esc(location)}</small>
        </div>
        <div class="wse-selected-tags">${tags.join("")}</div>
        <a class="wse-report-link" href="${esc(sample.report_href)}">Open sample report →</a>`;
    }

    renderEbird() {
      if (!this.ebirdPanelNode) return;
      this.ebirdPanelNode.hidden = false;
      if (!this.ebirdContexts.length) {
        this.ebirdNode.innerHTML = '<p class="wse-ebird-note">No validated eBird reporting frequency is available in this report. Missing or unmatched data are not zero frequency.</p>';
        return;
      }
      const contexts = this.ebirdContexts.filter((item) =>
        (this.hostFilter === "ALL" || item.host === this.hostFilter) &&
        (!this.selectedSampleId || (item.sample_ids || []).includes(this.selectedSampleId)));
      const attribution = this.ebirdAttribution;
      const sourceUrl = "https://ebird.org/data/download";
      const legalNotice = attribution ? `
        <div class="wse-ebird-legal">
          <strong>Data source and citation</strong>
          <p>${esc(attribution.citation)}</p>
          <p>Derived eBird data in this report are subject to the eBird Data Access Terms of Use. Cornell Lab of Ornithology does not endorse this WINGS report. <a href="${sourceUrl}" target="_blank" rel="noopener noreferrer">Get the original data from eBird</a>.</p>
          <details><summary>eBird Data Access Terms of Use (full text)</summary><pre>${esc(attribution.terms)}</pre></details>
        </div>` : "";
      if (!contexts.length) {
        this.ebirdNode.innerHTML = '<p class="wse-ebird-note">No eBird context is available for this selection.</p>' + legalNotice;
        return;
      }
      this.ebirdNode.innerHTML = `
        <p class="wse-ebird-note">These are complete eBird checklist reporting frequencies, not bird abundance, infection prevalence, or measurements at the sampled birds. Records sharing the same location and date window are displayed once; sample counts must not be added together.</p>
        <div class="wse-ebird-grid">${contexts.map((item) => {
          const ids = Array.isArray(item.sample_ids) ? item.sample_ids : [];
          const count = Number(item.complete_checklists);
          const positives = Number(item.reporting_checklists);
          const percent = count > 0 ? 100 * positives / count : NaN;
          const scope = item.radius_km == null ? `${item.state}, ${item.country} · state-wide` :
            `${item.state}, ${item.country} · ${formatNumber(item.radius_km, 1)} km radius`;
          const isSelected = ids.includes(this.selectedSampleId);
          return `<article class="wse-ebird-card${isSelected ? " is-selected" : ""}">
            <div class="wse-ebird-card-heading"><strong>${esc(item.species)}</strong><span>${Number.isFinite(percent) ? percent.toFixed(1) + "%" : "NA"}</span></div>
            <div class="wse-ebird-track"><span style="width:${Number.isFinite(percent) ? Math.min(100, Math.max(0, percent)) : 0}%"></span></div>
            <div>${esc(`${formatNumber(positives)} of ${formatNumber(count)} complete checklists reported this species`)}</div>
            <small>${esc(scope)} · ${esc(dateLabel(item.date_from))}–${esc(dateLabel(item.date_to))}</small>
            <small>Source: eBird Basic Dataset${item.release ? ` · ${esc(item.release)}` : ""}</small>
          </article>`;
        }).join("")}</div>${legalNotice}`;
    }

    ecologyWindow() {
      const sample = this.sampleById.get(this.selectedSampleId);
      const center = this.outbreakEpoch(sample?.collection_date);
      return center === null ? null : {sample, start: center - this.ecologyDays * 86400000, end: center + this.ecologyDays * 86400000, center};
    }

    ecologyState(sample) {
      if (!sample || !["US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"].includes(String(sample.country || "").trim().toUpperCase())) return null;
      const value = String(sample.state || "").trim().toUpperCase().replace(/^US-/, "");
      const states = this.ecology?.states || this.outbreakContext?.states || {};
      const code = Object.keys(states).find(code => code === value || states[code].toUpperCase() === value);
      const region = this.mapBoundaries?.regions.find(item => item.country === "USA" && (item.code === value || String(item.name || "").toUpperCase() === value));
      return code || region?.code || null;
    }

    ecologyLink(url, label) {
      // Only ordinary HTTPS source links can be emitted from imported metadata.
      return /^https:\/\/[^\s/]+(?:\/|$)/i.test(String(url || "")) ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : esc(label);
    }

    renderEcology() {
      if (!this.ecologyNode) return;
      const node = selector => this.ecologyNode.querySelector(selector);
      const window = this.ecologyWindow();
      const sample = this.sampleById.get(this.selectedSampleId);
      const bird = this.ecology?.birdcast;
      const provenance = this.ecology ? `<details><summary>Ecological snapshot provenance</summary><p>Snapshot built: ${esc(this.ecology.created_at)} · Cached window: ±${esc(this.ecology.window_days)} days. Changing the display window does not download more data.</p><p>File: ${esc(this.ecology.source_file)}<br>SHA-256: <code>${esc(this.ecology.snapshot_sha256)}</code></p><p>Sources retain their own scales and dates. This offline snapshot stays fixed in saved bundles.</p></details>` : '<p>No BirdCast or weather snapshot is loaded. The existing eBird results remain available.</p>';
      node(".wse-ecology-provenance").innerHTML = provenance;
      const birdNode = node(".wse-ecology-birdcast"), weatherNode = node(".wse-ecology-weather");
      const ebirdCharts = node(".wse-ecology-ebird-charts");
      ebirdCharts.innerHTML = "";
      if (!window) {
        node(".wse-ecology-intro").textContent = sample ? `Selected WINGS sample: ${sample.sample_id}. A valid collection date is required for aligned ecological views.` : "Select a WINGS sample on the map, timeline, or tree to align these views around its collection date.";
        birdNode.innerHTML = `<p>${bird?.status === "READY" ? "A BirdCast pilot snapshot is loaded. Select a dated sample to view regional migration." : "BirdCast pilot data are not loaded."} ${this.ecologyLink("https://dashboard.birdcast.org/", "Open BirdCast dashboard")}</p>`;
        weatherNode.textContent = "Select a dated sample with valid coordinates to view cached weather. No state-centroid weather is substituted.";
        return;
      }
      const from = new Date(window.start).toISOString().slice(0, 10), through = new Date(window.end).toISOString().slice(0, 10);
      node(".wse-ecology-intro").innerHTML = `<p><strong>Selected WINGS sample: ${esc(sample.sample_id)}</strong> · Collected: ${esc(sample.collection_date)} · Display: ${from} through ${through}</p><p>All charts share this calendar-date axis; dashed burgundy lines mark the sample collection date. eBird retains its original aggregation window, BirdCast uses the local evening date, and weather uses local calendar days. Different units and geographic scales are shown separately; these signals do not establish infection risk or epidemiological linkage.</p>`;
      const contexts = this.ebirdContexts.filter(item => (item.sample_ids || []).includes(sample.sample_id) && (this.hostFilter === "ALL" || item.host === this.hostFilter));
      contexts.forEach(item => {
        const caption = document.createElement("p");
        caption.textContent = `${item.species}: ${item.date_from} through ${item.date_to} is one aggregate window. Its original checklist denominator is unchanged; the displayed portion is clipped to the shared axis, not recomputed.`;
        ebirdCharts.appendChild(caption);
        const start = this.outbreakEpoch(item.date_from), end = this.outbreakEpoch(item.date_to);
        if (start !== null && end !== null && end >= window.start && start <= window.end) this.renderEcologyChart(ebirdCharts, window, [{date:item.date_from, end:item.date_to, value:100 * item.reporting_checklists / item.complete_checklists}], "Complete-checklist reporting frequency (%)", "#176B3A", true);
        else { const missing = document.createElement("p"); missing.textContent = "The eBird aggregation window does not overlap this display window."; ebirdCharts.appendChild(missing); }
      });
      const state = this.ecologyState(sample);
      const stateName = this.ecology?.states?.[state] || this.outbreakContext?.states?.[state] || sample.state;
      const dashboard = state && !["AK", "HI"].includes(state) ? `https://dashboard.birdcast.org/region/US-${state}` : "https://dashboard.birdcast.org/";
      const birdLink = this.ecologyLink(dashboard, "Open BirdCast dashboard (online)");
      if (!state || ["AK", "HI"].includes(state)) {
        birdNode.innerHTML = `<p>This state-level pilot requires a recognized state in the contiguous United States. Sample geography: ${esc(sample.state)}, ${esc(sample.country)}. ${birdLink}</p>`;
      } else if (bird?.status !== "READY") {
        birdNode.innerHTML = `<p>${esc(stateName)} · State-level migration. No BirdCast pilot snapshot is loaded; this is unavailable data, not zero migration. ${birdLink}</p>`;
      } else {
        const records = bird.records.filter(row => row.state_code === state && this.outbreakEpoch(row.date) >= window.start && this.outbreakEpoch(row.date) <= window.end);
        const available = records.filter(row => row.status === "AVAILABLE" && typeof row.birds_crossed === "number" && Number.isFinite(row.birds_crossed));
        const nights = Math.round((window.end - window.start) / 86400000) + 1;
        const zones = [...new Set(records.map(row => row.timezone))];
        birdNode.innerHTML = `<p><strong>${esc(stateName)} · State-level radar-derived estimate</strong><br>Estimated birds crossing the state per night (birds/night). Aggregate nocturnal migration across species; this does not measure movement of the sample's host species. Counts depend on regional extent.</p><p>Night = local evening date, sunset to following sunrise. Timezone(s): ${esc(zones.join(", ") || "No nights loaded for this window")}. ${available.length} of ${nights} nights have estimates. Missing nights are gaps, not zero; seasonal and radar coverage can limit availability.</p><p>${birdLink} · Imported: ${esc(bird.retrieved_on)}</p><div class="wse-ecology-chart"></div><details><summary>Nightly values and missing-data reasons</summary><div class="wse-ecology-table"><table><thead><tr><th>Night</th><th>Timezone</th><th>Estimated birds</th><th>Status / reason</th></tr></thead><tbody>${records.map(row => `<tr><td>${esc(row.date)}</td><td>${esc(row.timezone)}</td><td>${row.status === "AVAILABLE" && row.birds_crossed != null ? formatNumber(row.birds_crossed, 2) : "Unavailable"}</td><td>${esc(row.status)} ${esc(row.reason)}</td></tr>`).join("") || '<tr><td colspan="4">No imported records match this state and window.</td></tr>'}</tbody></table></div><p>Nights absent from the imported file have no estimate or recorded reason.</p></details><details><summary>BirdCast source and provenance</summary><p>${esc(bird.citation)}</p><p>Source: ${this.ecologyLink(bird.source_url, "Imported source")} · Retrieved: ${esc(bird.retrieved_on)}<br>Reuse basis: ${esc(bird.reuse_basis)}<br>CSV SHA-256: <code>${esc(bird.sha256)}</code></p></details>`;
        this.renderEcologyChart(birdNode.querySelector(".wse-ecology-chart"), window, available.map(row => ({date:row.date, value:row.birds_crossed})), "Estimated birds crossing state / night", "#006DAE");
      }
      const binding = this.ecology?.bindings?.[sample.sample_id];
      const weather = binding?.status === "READY" ? this.ecology.weather?.[binding.weather_key] : null;
      if (!weather) {
        const reason = !this.validMapCoordinates(sample) ? "Valid sample coordinates are required; no state-centroid weather is substituted." : binding?.reason || "No weather snapshot is loaded for this sample.";
        weatherNode.innerHTML = `<p>${esc(reason)}</p><p>Weather uses ERA5 gridded reanalysis: daily mean temperature at 2 m (°C), daily precipitation total (mm), and daily maximum wind speed at 10 m (km/h).</p>`;
        return;
      }
      const weatherRows = weather.rows.filter(row => this.outbreakEpoch(row.date) >= window.start && this.outbreakEpoch(row.date) <= window.end);
      const columns = [ ["temperature_2m_mean", "Daily mean temperature at 2 m (°C)", "#B45309"], ["precipitation_sum", "Daily precipitation total (mm)", "#006DAE"], ["wind_speed_10m_max", "Daily maximum wind speed at 10 m (km/h)", "#6F2DA8"] ];
      const countDays = Math.round((window.end - window.start) / 86400000) + 1;
      weatherNode.innerHTML = `<p><strong>ERA5 · ${esc(weather.resolution)} · Gridded reanalysis estimate</strong><br>Requested location: ${esc(sample.latitude)}, ${esc(sample.longitude)}. Returned grid location: ${esc(weather.grid_latitude)}, ${esc(weather.grid_longitude)}. Local daily timezone: ${esc(weather.timezone)}.</p><p>Cached dates: ${esc(weather.rows[0]?.date || "Unavailable")} through ${esc(weather.rows.at(-1)?.date || "Unavailable")}. ${weatherRows.length} of ${countDays} displayed days have source rows; null values remain gaps. These are model-assisted estimates, not measurements at the collection site. ${this.ecologyLink(weather.source_url, "Source documentation")}</p>${columns.map(([key, label]) => `<div data-weather-chart="${key}"></div>`).join("")}<details><summary>Daily weather values</summary><div class="wse-ecology-table"><table><thead><tr><th>Local date</th><th>Mean temperature (°C)</th><th>Precipitation (mm)</th><th>Maximum wind (km/h)</th></tr></thead><tbody>${weatherRows.map(row => `<tr><td>${esc(row.date)}</td>${columns.map(([key]) => `<td>${row[key] == null ? "Unavailable" : formatNumber(row[key], 2)}</td>`).join("")}</tr>`).join("") || '<tr><td colspan="4">No cached weather rows in this window.</td></tr>'}</tbody></table></div></details><details><summary>Weather source and provenance</summary><p>${esc(weather.provider)} · ${esc(weather.license)}<br>Retrieved: ${esc(weather.retrieved_at)}<br>Raw response SHA-256: <code>${esc(weather.raw_sha256)}</code></p><p>${this.ecologyLink(weather.request_url, "Original weather request (online)")}</p></details>`;
      columns.forEach(([key, label, color]) => {
        const rows = weatherRows.map(row => ({date:row.date, value:row[key]}));
        const target = weatherNode.querySelector(`[data-weather-chart="${key}"]`);
        const heading = document.createElement("p");
        heading.textContent = `${label} · ${rows.filter(row => typeof row.value === "number" && Number.isFinite(row.value)).length}/${countDays} days with values`;
        target.appendChild(heading);
        this.renderEcologyChart(target, window, rows, label, color);
      });
    }

    renderEcologyChart(target, window, rows, title, color, aggregate = false) {
      if (!target) return;
      const width = 900, height = 180, left = 76, right = 875, top = 20, bottom = 115;
      const values = rows.filter(row => typeof row.value === "number" && Number.isFinite(row.value));
      const min = Math.min(0, ...values.map(row => row.value));
      const max = aggregate ? 100 : Math.max(1, ...values.map(row => row.value));
      const x = time => left + (time - window.start) / (window.end - window.start + 86400000) * (right - left);
      const y = value => bottom - (value - min) / (max - min) * (bottom - top);
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":title, class:"wse-ecology-plot"});
      const label = (text, px, py, anchor="middle") => { const el=svgEl("text", {x:px,y:py,"text-anchor":anchor,class:"wse-outbreak-axis"}); el.textContent=text; svg.appendChild(el); };
      [...new Set([min, max, 0])].forEach(value => {
        svg.appendChild(svgEl("line", {x1:left,x2:right,y1:y(value),y2:y(value),class:"wse-outbreak-gridline"}));
        const tick = Math.abs(value) >= 10000 ? value.toLocaleString(undefined, {notation:"compact", maximumFractionDigits:1}) : formatNumber(value, 1);
        if (value !== 0 || value === min || value === max || (Math.abs(y(0) - y(min)) >= 16 && Math.abs(y(0) - y(max)) >= 16)) label(tick,left-8,y(value)+4,"end");
      });
      values.forEach(row => {
        const start = this.outbreakEpoch(row.date), end = this.outbreakEpoch(row.end || row.date);
        if (start === null || end === null || end < window.start || start > window.end) return;
        const from = Math.max(start, window.start), through = Math.min(end + 86400000, window.end + 86400000);
        const valueY = y(row.value), zeroY = y(0);
        const mark = row.value === 0 ? svgEl("line", {x1:x(from),x2:x(through)-1,y1:zeroY,y2:zeroY,stroke:color,"stroke-width":3}) : svgEl("rect", {x:x(from),y:Math.min(valueY,zeroY),width:Math.max(1,x(through)-x(from)-1),height:Math.max(1,Math.abs(zeroY-valueY)),fill:color,opacity:aggregate?0.4:0.85});
        const tip = svgEl("title"); tip.textContent = `${row.date}${row.end ? " through " + row.end + " (one aggregate)" : ""}: ${formatNumber(row.value, 2)} · ${title}`; mark.appendChild(tip); svg.appendChild(mark);
      });
      svg.appendChild(svgEl("line", {x1:x(window.center+43200000),x2:x(window.center+43200000),y1:top-4,y2:bottom,class:"wse-outbreak-sample-date"}));
      label(new Date(window.start).toISOString().slice(0,10),left,bottom+24,"start");
      label(window.sample.collection_date,x(window.center+43200000),bottom+24);
      label(new Date(window.end).toISOString().slice(0,10),right,bottom+24,"end");
      label(title,(left+right)/2,height-9);
      if (!values.length) label("No values available in this window",(left+right)/2,65);
      target.appendChild(svg);
    }


    renderLegend() {
      const counts = new Map(this.hosts.map((host) => [host, 0]));
      this.samples.forEach((sample) => counts.set(sample.host, (counts.get(sample.host) || 0) + 1));
      const ranked = [...counts.keys()].filter((host) => counts.get(host) > 0)
        .sort((a, b) => counts.get(b) - counts.get(a) || a.localeCompare(b));
      const maxCount = Math.max(1, ...ranked.map((host) => counts.get(host)));

      this.legendNode.innerHTML = `
        <div class="wse-host-distribution-title">Host distribution</div>
        ${ranked.length ? ranked.map((host) => {
          const count = counts.get(host);
          const color = this.hostColor.get(host) || "#5F6368";
          const active = this.hostFilter === host;
          return `<button type="button" class="wse-host-row${active ? " is-active" : ""}"
            data-host="${esc(host)}" aria-pressed="${active ? "true" : "false"}"
            aria-label="Filter by ${esc(host)}: ${count} samples">
            <span class="wse-host-label"><i style="background:${color}"></i>${esc(host)}</span>
            <span class="wse-host-track"><span class="wse-host-fill" style="width:${100 * count / maxCount}%;background:${color}"></span></span>
            <strong>${formatNumber(count)}</strong>
          </button>`;
        }).join("") : '<div class="wse-empty">No host data available.</div>'}`;

      this.legendNode.querySelectorAll(".wse-host-row").forEach((button) => {
        button.addEventListener("click", () => {
          this.setHostFilter(this.hostFilter === button.dataset.host ? "ALL" : button.dataset.host);
        });
      });
    }

    renderTimeline() {
      const samples = this.visibleSamples().filter((sample) => parseDate(sample.collection_date));
      this.timelineNode.innerHTML = "";
      if (!samples.length) {
        this.timelineNode.innerHTML = `<div class="wse-empty">No dated samples are available for the current filter.</div>`;
        return;
      }
      const width = 1100, height = 210, left = 52, right = 24, top = 22, bottom = 45;
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":"Collection timeline"});
      // Keep the same axis when a host filter changes the visible samples.
      const dates = this.samples.map((s) => parseDate(s.collection_date))
        .filter((date) => date).map((date) => date.getTime());
      let min = Math.min(...dates), max = Math.max(...dates);
      const pad = Math.max((max - min) * 0.035, 86400000 * 10);
      min -= pad; max += pad;
      const x = (ms) => left + (ms - min) / Math.max(1, max - min) * (width - left - right);
      const baselineY = height - bottom;

      const axis = svgEl("line", {x1:left, y1:baselineY, x2:width-right, y2:baselineY, class:"wse-axis-line"});
      svg.appendChild(axis);

      const minDate = new Date(min), maxDate = new Date(max);
      const tick = new Date(Date.UTC(minDate.getUTCFullYear(), minDate.getUTCMonth(), 1));
      while (tick <= maxDate) {
        const tx = x(tick.getTime());
        svg.appendChild(svgEl("line", {x1:tx, y1:baselineY, x2:tx, y2:baselineY+6, class:"wse-axis-tick"}));
        const label = svgEl("text", {x:tx, y:baselineY+25, "text-anchor":"middle", class:"wse-axis-label"});
        label.textContent = monthLabel(tick);
        svg.appendChild(label);
        tick.setUTCMonth(tick.getUTCMonth() + 2);
      }

      const grouped = new Map();
      samples.forEach((sample) => {
        const key = sample.collection_date;
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(sample);
      });

      grouped.forEach((group, date) => {
        const tx = x(parseDate(date).getTime());
        group.forEach((sample, index) => {
          const col = index % 2;
          const row = Math.floor(index / 2);
          const cx = tx + (col ? 7 : -7);
          const cy = baselineY - 16 - row * 16;
          const circle = svgEl("circle", {
            cx, cy, r:6.2,
            fill:this.hostColorFor(sample),
            class:"wse-sample-mark wse-timeline-mark",
            "data-sample-id":sample.sample_id,
            tabindex:0,
          });
          circle.addEventListener("click", () => this.selectSample(sample.sample_id));
          circle.addEventListener("mouseenter", () => this.setHover(sample.sample_id));
          circle.addEventListener("mouseleave", () => this.clearHover());
          circle.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") this.selectSample(sample.sample_id); });
          const title = svgEl("title");
          title.textContent = `${sample.sample_id}\n${sample.host} · ${dateLabel(sample.collection_date)}`;
          circle.appendChild(title);
          svg.appendChild(circle);
        });
      });
      this.timelineNode.appendChild(svg);
    }

    validMapCoordinates(sample) {
      const valid = value => value !== null && value !== undefined && String(value).trim() !== "" && Number.isFinite(Number(value));
      return Boolean(sample.has_coordinates && valid(sample.longitude) && valid(sample.latitude) &&
        Math.abs(Number(sample.longitude)) <= 180 && Math.abs(Number(sample.latitude)) <= 90);
    }

    mapBounds() {
      if (this.mapViewport) return [...this.mapViewport];
      if (this.mapView === "world") return [-180, 180, -90, 90];
      const northAmerica = [-180, -45, 5, 85];
      if (this.mapView === "north-america") return northAmerica;
      // Use the entire run so host filtering never shifts the geographic frame.
      const points = this.samples.filter(sample => this.validMapCoordinates(sample));
      if (!points.length) return northAmerica;
      const lons = points.map(sample => Number(sample.longitude));
      const lats = points.map(sample => Number(sample.latitude));
      const lonMin = Math.min(...lons), lonMax = Math.max(...lons);
      const latMin = Math.min(...lats), latMax = Math.max(...lats);
      const lonPad = Math.max(5, (lonMax - lonMin) * .15);
      const latPad = Math.max(3, (latMax - latMin) * .15);
      return [Math.max(-180, lonMin - lonPad), Math.min(180, lonMax + lonPad),
        Math.max(-90, latMin - latPad), Math.min(90, latMax + latPad)];
    }

    constrainMapBounds(bounds) {
      const width = Math.max(.05, Math.min(360, bounds[1] - bounds[0]));
      const height = Math.max(.025, Math.min(180, bounds[3] - bounds[2]));
      const x = Math.max(-180 + width / 2, Math.min(180 - width / 2, (bounds[0] + bounds[1]) / 2));
      const y = Math.max(-90 + height / 2, Math.min(90 - height / 2, (bounds[2] + bounds[3]) / 2));
      return [x - width / 2, x + width / 2, y - height / 2, y + height / 2];
    }

    refreshMapView() {
      const select = this.root.querySelector(".wse-map-view");
      if (select) select.value = this.mapView;
      this.renderMap();
      this.renderMapSelection();
      this.updateEmphasis();
    }

    setMapViewport(bounds) {
      this.mapViewport = this.constrainMapBounds(bounds);
      this.mapView = "custom";
      this.refreshMapView();
    }

    zoomMap(factor) {
      const [left, right, bottom, top] = this.mapBounds();
      const x = (left + right) / 2, y = (bottom + top) / 2;
      const dx = (right - left) * factor / 2, dy = (top - bottom) * factor / 2;
      this.setMapViewport([x - dx, x + dx, y - dy, y + dy]);
    }

    resetMapView() {
      this.mapViewport = null;
      this.mapView = "samples";
      this.refreshMapView();
    }

    shiftedMapBounds(bounds, dx, dy) {
      const {px, py} = this.mapProjection(bounds);
      const lon = dx / (px(1) - px(0));
      const lat = dy / (py(1) - py(0));
      return this.constrainMapBounds([bounds[0] - lon, bounds[1] - lon, bounds[2] - lat, bounds[3] - lat]);
    }

    bindMapNavigation() {
      const node = this.mapNode;
      let drag = null, suppressClick = false;
      const restore = () => {
        if (!drag) return;
        const current = drag;
        drag = null;
        current.svg.style.transform = "";
        node.classList.remove("is-panning");
        if (node.hasPointerCapture(current.id)) node.releasePointerCapture(current.id);
      };
      node.addEventListener("pointerdown", event => {
        if (drag || event.button !== 0 || event.isPrimary === false) return;
        suppressClick = false;
        const svg = node.querySelector("svg");
        const matrix = svg?.getScreenCTM();
        if (!matrix || !matrix.a || !matrix.d) return;
        drag = {id: event.pointerId, x: event.clientX, y: event.clientY,
          sx: matrix.a, sy: matrix.d, svg, bounds: this.mapBounds(), moved: false};
      });
      node.addEventListener("pointermove", event => {
        if (!drag || event.pointerId !== drag.id) return;
        const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
        if (!drag.moved && Math.hypot(dx, dy) < 5) return;
        drag.moved = true;
        suppressClick = true;
        node.setPointerCapture(drag.id);
        node.classList.add("is-panning");
        drag.svg.style.transform = `translate(${dx}px, ${dy}px)`;
        event.preventDefault();
      });
      node.addEventListener("pointerup", event => {
        if (!drag || event.pointerId !== drag.id) return;
        const bounds = drag.moved ? this.shiftedMapBounds(drag.bounds,
          (event.clientX - drag.x) / drag.sx, (event.clientY - drag.y) / drag.sy) : null;
        restore();
        if (bounds) { event.preventDefault(); this.setMapViewport(bounds); }
      });
      node.addEventListener("pointercancel", event => { if (drag?.id === event.pointerId) restore(); });
      node.addEventListener("lostpointercapture", () => restore());
      node.addEventListener("pointerleave", () => { if (drag && !drag.moved) restore(); });
      // A drag that starts on a sample must never select/cycle that sample.
      node.addEventListener("click", event => {
        if (suppressClick) { suppressClick = false; event.preventDefault(); event.stopImmediatePropagation(); }
      }, true);
      node.addEventListener("keydown", event => {
        if (event.target !== node || event.ctrlKey || event.metaKey || event.altKey) return;
        suppressClick = false;
        const moves = {ArrowLeft: [90, 0], ArrowRight: [-90, 0], ArrowUp: [0, 60], ArrowDown: [0, -60]};
        if (moves[event.key]) this.setMapViewport(this.shiftedMapBounds(this.mapBounds(), ...moves[event.key]));
        else if (event.key === "+" || event.key === "=") this.zoomMap(1 / 1.5);
        else if (event.key === "-") this.zoomMap(1.5);
        else if (event.key === "0") this.resetMapView();
        else return;
        event.preventDefault();
      });
    }

    mapProjection(bounds, width = 900, height = 460) {
      const [lonMin, lonMax, latMin, latMax] = bounds;
      const centerLon = (lonMin + lonMax) / 2, centerLat = (latMin + latMax) / 2;
      const cosLat = Math.max(.15, Math.cos(centerLat * Math.PI / 180));
      const scale = Math.min((width - 64) / ((lonMax - lonMin) * cosLat), (height - 64) / (latMax - latMin));
      return {px: lon => width / 2 + (lon - centerLon) * cosLat * scale,
        py: lat => height / 2 - (lat - centerLat) * scale};
    }

    visibleMapLabel(feature, projected, anchor, width, height) {
      // Clip each outer ring to the viewport before choosing its label position.
      const clip = (ring, axis, edge, keepGreater) => {
        const inside = point => keepGreater ? point[axis] >= edge : point[axis] <= edge;
        const output = [];
        if (!ring.length) return output;
        let previous = ring[ring.length - 1];
        for (const current of ring) {
          if (inside(current) !== inside(previous)) {
            const ratio = (edge - previous[axis]) / (current[axis] - previous[axis]);
            output.push([previous[0] + ratio * (current[0] - previous[0]), previous[1] + ratio * (current[1] - previous[1])]);
          }
          if (inside(current)) output.push(current);
          previous = current;
        }
        return output;
      };
      const contains = (point, ring) => {
        let inside = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          const [x, y] = ring[i], [xx, yy] = ring[j];
          if ((y > point[1]) !== (yy > point[1]) && point[0] < (xx - x) * (point[1] - y) / (yy - y) + x) inside = !inside;
        }
        return inside;
      };
      const pieces = projected.map(polygon => {
        let ring = polygon[0];
        for (const [axis, edge, greater] of [[0, 8, true], [0, width - 8, false], [1, 8, true], [1, height - 8, false]]) ring = clip(ring, axis, edge, greater);
        let twiceArea = 0, cx = 0, cy = 0;
        for (let i = 0; i < ring.length; i++) {
          const a = ring[i], b = ring[(i + 1) % ring.length], cross = a[0] * b[1] - b[0] * a[1];
          twiceArea += cross; cx += (a[0] + b[0]) * cross; cy += (a[1] + b[1]) * cross;
        }
        return {ring, polygon, area: Math.abs(twiceArea / 2), center: [cx / (3 * twiceArea), cy / (3 * twiceArea)]};
      }).filter(piece => piece.area >= 35).sort((a, b) => b.area - a.area);
      if (!pieces.length) return null;
      const piece = pieces[0], xs = piece.ring.map(p => p[0]), ys = piece.ring.map(p => p[1]);
      const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
      const within = point => point.every(Number.isFinite) && contains(point, piece.ring) && !piece.polygon.slice(1).some(hole => contains(point, hole));
      const grid = [];
      for (let y = 1; y < 8; y++) for (let x = 1; x < 8; x++) grid.push([minX + (maxX - minX) * x / 8, minY + (maxY - minY) * y / 8]);
      grid.sort((a,b) => Math.hypot(a[0]-piece.center[0],a[1]-piece.center[1]) - Math.hypot(b[0]-piece.center[0],b[1]-piece.center[1]));
      return {area: piece.area, span: maxX - minX, within, points: [anchor, piece.center, ...grid].filter(within)};
    }

    drawMapBoundaries(svg, bounds, px, py, width, height) {
      if (!this.mapBoundaries) return false;
      const labels = [];
      const draw = (feature, regional) => {
        const projected = feature.polygons.map(polygon => polygon.map(ring => ring.map(([lon, lat]) => [px(lon), py(lat)])));
        const coordinates = projected.flat(2), xs = coordinates.map(p => p[0]), ys = coordinates.map(p => p[1]);
        if (Math.max(...xs) < 0 || Math.min(...xs) > width || Math.max(...ys) < 0 || Math.min(...ys) > height) return;
        const d = projected.map(polygon => polygon.map(ring => ring.map(([x,y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ") + " Z").join(" ")).join(" ");
        const path = svgEl("path", {d, class: regional ? "wse-region-boundary" : "wse-country-boundary", "fill-rule": "evenodd"});
        if (regional) { path.setAttribute("data-region-code", feature.code); path.setAttribute("data-region-country", feature.country); }
        const fullName = regional && feature.country === "USA" && feature.code === "DC" ? "District of Columbia" : feature.name;
        const title = svgEl("title"); title.textContent = `${fullName} (${feature.country})`; path.appendChild(title); svg.appendChild(path);
        const placement = this.visibleMapLabel(feature, projected, [px(feature.label[0]), py(feature.label[1])], width, height);
        if (placement) labels.push({feature, regional, fullName, ...placement});
      };
      (this.mapBoundaries.countries || []).forEach(feature => draw(feature, false));
      (this.mapBoundaries.regions || []).forEach(feature => draw(feature, true));
      const occupied = this.visibleSamples().filter(sample => this.validMapCoordinates(sample)).map(sample => {
        const x = px(Number(sample.longitude)), y = py(Number(sample.latitude));
        return {left:x-22, right:x+22, top:y-22, bottom:y+22};
      });
      labels.sort((a,b) => Number(b.regional) - Number(a.regional) || b.area - a.area).forEach(item => {
        const {feature, regional, fullName, span, points} = item;
        const texts = regional ? (feature.code === "DC" ? [feature.code] : [fullName, feature.code]) : [fullName];
        for (const text of texts) {
          if (!text || text.length * 6.5 > span * 1.2) continue;
          const halfWidth = text.length * 3.6 + 4;
          for (const [x,y] of points) {
            const box = {left:x-halfWidth, right:x+halfWidth, top:y-12, bottom:y+5};
            if (![[x-halfWidth+2,y-5],[x+halfWidth-2,y-5],[x,y-11],[x,y+3]].every(item.within)) continue;
            if (box.left < 8 || box.right > width - 8 || box.top < 8 || box.bottom > height - 8) continue;
            if (occupied.some(other => box.left < other.right && box.right > other.left && box.top < other.bottom && box.bottom > other.top)) continue;
            occupied.push(box);
            const label = svgEl("text", {x, y, "text-anchor":"middle", class:"wse-map-region-label", "data-label-region":regional ? feature.code : "", "aria-label":fullName});
            label.textContent = text; svg.appendChild(label); return;
          }
        }
      });
      return true;
    }

    renderMap() {
      const allVisible = this.visibleSamples();
      const geolocated = allVisible.filter(sample => this.validMapCoordinates(sample));
      const invalid = allVisible.filter(sample => sample.has_coordinates && !this.validMapCoordinates(sample)).length;
      const missing = allVisible.length - geolocated.length - invalid;
      const bounds = this.mapBounds();
      const [lonMin, lonMax, latMin, latMax] = bounds;
      const samples = geolocated.filter(sample => Number(sample.longitude) >= lonMin && Number(sample.longitude) <= lonMax &&
        Number(sample.latitude) >= latMin && Number(sample.latitude) <= latMax);
      const outside = geolocated.length - samples.length;
      this.mapCountNode.textContent = `${geolocated.length} geolocated · ${missing} without coordinates` +
        (invalid ? ` · ${invalid} invalid coordinates` : "") + (outside ? ` · ${outside} outside this view` : "");
      this.mapNode.innerHTML = "";

      const width = 900, height = 460;
      const extentLabel = this.mapView === "custom" ? "Custom view" : this.mapView === "world" ? "World" : this.mapView === "north-america" ? "North America" : "Sample area";
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"group", "aria-label":`Sampling locations: ${extentLabel}`});
      const {px, py} = this.mapProjection(bounds, width, height);
      if (!this.drawMapBoundaries(svg, bounds, px, py, width, height)) {
        const note = document.createElement("p");
        note.className = "wse-map-attribution";
        note.textContent = "Boundary data unavailable. Rebuild the report with map-boundaries.js.";
        this.mapNode.appendChild(note);
      }

      this.applyOutbreakLayer(svg);

      if (!samples.length && this.outbreakContext?.status !== "READY") {
        const label = svgEl("text", {x:width/2,y:height/2,"text-anchor":"middle",class:"wse-map-empty"});
        label.textContent = outside ? "No sample locations in this map extent; select Sample area or World" : "No valid coordinates available for the current filter";
        svg.appendChild(label);
        this.mapNode.appendChild(svg);
        return;
      }

      const groups = new Map();
      samples.forEach((sample) => {
        const key = `${Number(sample.latitude).toFixed(5)},${Number(sample.longitude).toFixed(5)}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(sample);
      });

      groups.forEach((members, key) => {
        const first = members[0];
        const cx = px(Number(first.longitude));
        const cy = py(Number(first.latitude));
        const radius = Math.min(18, 6 + Math.sqrt(members.length) * 2.5);
        const cluster = svgEl("g", {
          class:"wse-map-cluster",
          "data-sample-ids":members.map(s=>s.sample_id).join("|"),
          tabindex:0,
          role:"button",
          "aria-pressed":"false",
          "aria-label":`Select a sample at ${Number(first.latitude).toFixed(3)}, ${Number(first.longitude).toFixed(3)}; ${members.length} sample(s)`,
        });
        const halo = svgEl("circle", {cx,cy,r:radius+5,class:"wse-map-halo"});
        const bubble = svgEl("circle", {cx,cy,r:radius,fill:this.hostColorFor(first),class:"wse-map-bubble"});
        cluster.append(halo,bubble);
        if (members.length > 1) {
          const count = svgEl("text", {x:cx,y:cy+5,"text-anchor":"middle",class:"wse-map-cluster-count"});
          count.textContent = String(members.length);
          cluster.appendChild(count);
        }
        const title = svgEl("title");
        title.textContent = `${members.length} sample${members.length===1?"":"s"} at ${Number(first.latitude).toFixed(3)}, ${Number(first.longitude).toFixed(3)}\n` + members.map(s=>`${s.sample_id} · ${s.host}`).join("\n");
        cluster.appendChild(title);
        const choose = () => {
          const current = members.findIndex(sample => sample.sample_id === this.selectedSampleId);
          const next = current < 0 ? 0 : (current + 1) % members.length;
          this.selectSample(members[next].sample_id);
        };
        cluster.addEventListener("click", choose);
        cluster.addEventListener("keydown", (event) => { if(event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } });
        cluster.addEventListener("mouseenter", () => this.setHover(members[0].sample_id));
        cluster.addEventListener("mouseleave", () => this.clearHover());
        svg.appendChild(cluster);
      });

      this.mapNode.appendChild(svg);
    }

    renderMapSelection() {
      if (!this.mapSelectionNode) return;
      const sample = this.sampleById.get(this.selectedSampleId);
      if (!sample) {
        this.mapSelectionNode.innerHTML = '<p>Click a point to select a sample. A number shows how many samples share that location.</p>';
        return;
      }
      const key = item => `${Number(item.latitude).toFixed(5)},${Number(item.longitude).toFixed(5)}`;
      const colocated = this.validMapCoordinates(sample) ? this.visibleSamples().filter(item =>
        this.validMapCoordinates(item) && key(item) === key(sample)) : [];
      const bounds = this.mapBounds();
      const outside = this.validMapCoordinates(sample) && (Number(sample.longitude) < bounds[0] || Number(sample.longitude) > bounds[1] || Number(sample.latitude) < bounds[2] || Number(sample.latitude) > bounds[3]);
      const notice = this.hostFilter !== "ALL" && sample.host !== this.hostFilter
        ? "Selected sample is outside the current host filter."
        : !this.validMapCoordinates(sample) ? (this.selectedOutbreakState() ? `Sample location available at state level: ${this.outbreakContext.states[this.selectedOutbreakState()]}. No sample point is plotted; use the Zoom to state button to locate the outline.` : "Selected sample has no valid map coordinates.")
        : outside ? "Selected sample is outside this map view. Reset view to return to the sample area."
        : colocated.length > 1 ? `${colocated.length} samples share this point. Choose a sample below, or click the point again to cycle through them.`
        : "Selected on the linked timeline and available segment trees. Click this point again to clear selection.";
      this.mapSelectionNode.innerHTML = `
        <div class="wse-map-selection-heading">Selected sample: <strong>${esc(sample.sample_id)}</strong></div>
        <p>${esc(sample.host)} · ${esc(dateLabel(sample.collection_date))}</p>
        <p>${esc(notice)}</p>
        ${colocated.length > 1 ? `<div class="wse-map-sample-choices" role="group" aria-label="Samples at this location">${colocated.map(item =>
          `<button type="button" class="wse-map-sample-choice" data-sample-id="${esc(item.sample_id)}" aria-pressed="${item.sample_id === sample.sample_id}">${esc(item.sample_id)}</button>`
        ).join("")}</div>` : ""}
        ${sample.report_href ? `<a class="wse-map-report-link" href="${esc(sample.report_href)}">Open sample report →</a>` : ""}`;
      this.mapSelectionNode.querySelectorAll(".wse-map-sample-choice").forEach(button => {
        button.addEventListener("click", () => {
          this.selectedReferenceId = null;
          this.selectedSampleId = button.getAttribute("data-sample-id");
          this.hoverSampleId = null;
          this.updateSelection();
          const active = [...this.mapSelectionNode.querySelectorAll(".wse-map-sample-choice")]
            .find(item => item.getAttribute("data-sample-id") === this.selectedSampleId);
          if (active) active.focus({preventScroll: true});
        });
      });
    }

    outbreakEpoch(value) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
      const time = Date.parse(`${value}T00:00:00Z`);
      return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? time : null;
    }

    outbreakStateCode(value) {
      const text = String(value || "").trim().toLowerCase().replace(/^us-/, "");
      return Object.entries(this.outbreakContext?.states || {}).find(([code, name]) =>
        code.toLowerCase() === text || name.toLowerCase() === text)?.[0] || null;
    }

    syncOutbreakDates() {
      if (!this.outbreakFollow) return;
      const sample = this.sampleById.get(this.selectedSampleId);
      const time = this.outbreakEpoch(sample?.collection_date);
      const range = this.outbreakContext?.date_ranges?.[this.outbreakBasis] || {};
      this.outbreakStart = time === null ? range.min || "" : new Date(time - this.outbreakDays * 86400000).toISOString().slice(0, 10);
      this.outbreakEnd = time === null ? range.max || "" : new Date(time + this.outbreakDays * 86400000).toISOString().slice(0, 10);
    }

    outbreakView(scope = this.outbreakScope) {
      const context = this.outbreakContext;
      const sample = this.sampleById.get(this.selectedSampleId);
      let code = null, blocked = false, scopeLabel = "All U.S. states";
      if (scope === "sample" && sample) {
        const country = String(sample.country || "").trim().toUpperCase();
        if (!["US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"].includes(country)) {
          blocked = true;
          scopeLabel = "No automatic geographic match: sample country is outside the U.S. or not recorded. Choose a state or All U.S. states to browse.";
        } else {
          code = this.outbreakStateCode(sample.state);
          blocked = !code;
          scopeLabel = code ? `${context.states[code]} — state-level match to ${sample.sample_id}${this.validMapCoordinates(sample) ? "" : "; sample coordinates unavailable"}.` : "No automatic geographic match: sample state is missing or unrecognized. Choose a state to browse.";
        }
      } else if (scope !== "all" && scope !== "sample") {
        code = scope;
        scopeLabel = `${context.states[code] || code} — manually selected state`;
      } else if (scope === "sample") {
        scopeLabel = "All U.S. states — select a WINGS sample for state-level context.";
      }
      const scoped = blocked ? [] : context.records.filter(row => !code || row.state_code === code);
      const start = this.outbreakEpoch(this.outbreakStart), end = this.outbreakEpoch(this.outbreakEnd);
      const validWindow = start !== null && end !== null && start <= end;
      const undated = scoped.filter(row => !row[this.outbreakBasis]).length;
      const rows = validWindow ? scoped.filter(row => row[this.outbreakBasis] && row[this.outbreakBasis] >= this.outbreakStart && row[this.outbreakBasis] <= this.outbreakEnd) : [];
      rows.sort((a, b) => b[this.outbreakBasis].localeCompare(a[this.outbreakBasis]) || a.source_row - b.source_row);
      const counts = new Map();
      rows.forEach(row => { if (row.state_code) counts.set(row.state_code, (counts.get(row.state_code) || 0) + 1); });
      const range = context.date_ranges[this.outbreakBasis] || {};
      const outsideSnapshot = validWindow && range.min && range.max && (this.outbreakEnd < range.min || this.outbreakStart > range.max);
      return {rows, code, blocked, scopeLabel, start, end, validWindow, undated, counts, outsideSnapshot};
    }

    bindOutbreakControls() {
      if (!this.outbreakNode) return;
      this.outbreakNode.addEventListener("change", event => {
        const key = event.target.dataset.outbreakControl;
        if (!key) return;
        if (key === "scope") { this.outbreakScope = event.target.value; this.mapStateCardDismissed = false; }
        if (key === "basis") this.outbreakBasis = event.target.value;
        if (key === "days") this.outbreakDays = Number(event.target.value);
        if (key === "lock") this.outbreakFollow = !event.target.checked;
        if (key === "start" || key === "end") {
          this.outbreakFollow = false;
          if (key === "start") this.outbreakStart = event.target.value;
          else this.outbreakEnd = event.target.value;
        }
        this.outbreakPage = 0;
        this.renderOutbreak();
      });
      this.outbreakNode.addEventListener("click", event => {
        const button = event.target.closest("[data-outbreak-page]");
        if (!button) return;
        this.outbreakPage += Number(button.dataset.outbreakPage);
        this.renderOutbreak(true);
        this.outbreakNode.querySelector(".wse-outbreak-records summary")?.focus({preventScroll: true});
      });
    }

    renderOutbreak(forceRecordsOpen = false) {
      if (!this.outbreakNode) return;
      const context = this.outbreakContext;
      this.outbreakNode.hidden = context?.status !== "READY";
      if (this.outbreakNode.hidden) return;
      if (this.outbreakLastSampleId !== this.selectedSampleId) { this.mapStateCardDismissed = false; this.outbreakPage = 0; if (this.outbreakLastSampleId !== undefined) this.outbreakScope = "sample"; this.outbreakLastSampleId = this.selectedSampleId; }
      this.syncOutbreakDates();
      const view = this.outbreakView();
      const focusedControl = document.activeElement?.dataset?.outbreakControl;
      const recordsOpen = forceRecordsOpen || Boolean(this.outbreakNode.querySelector(".wse-outbreak-records")?.open);
      const pages = Math.max(1, Math.ceil(view.rows.length / 25));
      this.outbreakPage = Math.max(0, Math.min(this.outbreakPage, pages - 1));
      const rows = view.rows.slice(this.outbreakPage * 25, (this.outbreakPage + 1) * 25);
      const option = (value, label, active) => `<option value="${esc(value)}"${value === active ? " selected" : ""}>${esc(label)}</option>`;
      const basisLabel = this.outbreakBasis === "collection_date" ? "collection date" : "detection date";
      const sample = this.sampleById.get(this.selectedSampleId);
      const sampleDate = this.outbreakEpoch(sample?.collection_date);
      const markerVisible = view.validWindow && sampleDate !== null && sampleDate >= view.start && sampleDate <= view.end;
      const sampleState = this.selectedOutbreakState();
      let sampleDateLabel = "No WINGS sample selected; no collection-date marker shown.";
      if (sample) {
        sampleDateLabel = `Selected WINGS sample: ${sample.sample_id} · Collected: ${sampleDate === null ? "unavailable" : sample.collection_date}`;
        if (sampleState) sampleDateLabel += ` · Sample state: ${context.states[sampleState]}`;
        sampleDateLabel += markerVisible ? ". Dashed line = this sample's collection date." : sampleDate === null ? ". No collection-date marker shown." : view.validWindow ? ". Collection date is outside the displayed window; no marker shown." : ". Enter a valid date window to show the marker.";
        if (view.code && view.code !== sampleState) {
          sampleDateLabel += sampleState
            ? ` Records shown are for ${context.states[view.code] || view.code}, a different state from the selected sample.`
            : ` Records shown are for ${context.states[view.code] || view.code}; the selected sample has no confirmed U.S. state match.`;
        }
      }
      const missingSampleDate = this.outbreakFollow && sample && sampleDate === null;
      const range = context.date_ranges[this.outbreakBasis] || {};
      this.outbreakNode.innerHTML = `
        <div class="wse-panel-heading"><div><span class="wse-panel-kicker">Outbreak context</span><h3>APHIS wild-bird detections</h3></div><a href="${esc(context.source_url)}" target="_blank" rel="noopener noreferrer">Open APHIS source table ↗</a></div>
        <div class="wse-outbreak-body">
          <p class="wse-outbreak-caution">Date and place overlap provide context only; they do not imply epidemiological linkage. Counts are source records, not unique outbreaks, incidence, or prevalence.</p>
          <div class="wse-outbreak-controls">
            <label>Timeline / records <select data-outbreak-control="scope">${option("sample", "Follow selected sample (state)", this.outbreakScope)}${option("all", "All U.S. states", this.outbreakScope)}${Object.entries(context.states).sort((a,b) => a[1].localeCompare(b[1])).map(([code, name]) => option(code, name, this.outbreakScope)).join("")}</select></label>
            <label>Date basis <select data-outbreak-control="basis">${option("collection_date", "Collection date", this.outbreakBasis)}${option("detected_date", "Date detected", this.outbreakBasis)}</select></label>
            <label><input type="checkbox" data-outbreak-control="lock"${this.outbreakFollow ? "" : " checked"}> Lock date window</label>
            <label>Window ± <select data-outbreak-control="days"${this.outbreakFollow ? "" : " disabled"}>${[7,30,90,365].map(days => option(String(days), `${days} days`, String(this.outbreakDays))).join("")}</select></label>
            <label>From <input type="date" data-outbreak-control="start" value="${esc(this.outbreakStart)}"></label>
            <label>Through <input type="date" data-outbreak-control="end" value="${esc(this.outbreakEnd)}"></label>
          </div>
          <p class="wse-outbreak-scope">${esc(view.scopeLabel)} ${missingSampleDate ? "Sample collection date unavailable; displaying the snapshot's full date range." : this.outbreakFollow && !sample ? "No selected sample; displaying the snapshot's full date range." : ""}</p>
          <p class="wse-outbreak-summary" aria-live="polite">${view.validWindow ? `<strong>${formatNumber(view.rows.length)} matching source records</strong> · ${esc(this.outbreakStart)} through ${esc(this.outbreakEnd)} by ${basisLabel}.` : "Enter a valid date range with From on or before Through."} ${formatNumber(view.undated)} records in this geographic scope lack a usable ${basisLabel} and are excluded.</p>
          ${view.outsideSnapshot ? '<p class="wse-outbreak-caution">This window is outside the date range represented in this snapshot. Zero matches do not establish absence of detections.</p>' : ""}
          <p class="wse-outbreak-precision">Source precision: county/state. Map: state-level aggregates; shaded areas are not exact detection locations. State matching also applies when sample coordinates are absent. No distance-based linkage is calculated.</p>
          <p class="wse-outbreak-map-key">The shared map shades all U.S. states for the chosen dates, including neighboring states. This timeline and the source records follow the geographic choice above. Click a shaded state to browse its records without changing the selected WINGS sample. Host filters affect sample points only.</p>
          <p class="wse-outbreak-sample-label" aria-live="polite">${markerVisible ? '<span class="wse-outbreak-sample-swatch" aria-hidden="true"></span>' : ""}<span>${esc(sampleDateLabel)}</span></p>
          <div class="wse-outbreak-timeline"></div>
          <p class="wse-outbreak-timeline-note">${this.outbreakBasis === "collection_date" ? "Collection date is the sample collection date reported by APHIS." : "Date detected is the date of APHIS confirmatory testing; it can be later than collection."} Click a bar to narrow the date window. A dashed line marks the selected WINGS sample's collection date when it falls in this window.</p>
          <details class="wse-outbreak-records"${recordsOpen ? " open" : ""}><summary>Source records (${formatNumber(view.rows.length)})</summary>
            <p>CSV data-record numbers refer to this snapshot. APHIS supplies no unique record IDs or record-specific URLs; each source link opens the APHIS table. Repeated rows are retained.</p>
            <div class="wse-outbreak-table-wrap"><table><thead><tr><th>CSV record</th><th>State / county</th><th>Bird species</th><th>Collection date</th><th>Date detected</th><th>Source details</th></tr></thead><tbody>${rows.map(row => `
              <tr><td>${row.source_row}</td><td>${esc(row.state)} / ${esc(row.county || "Not recorded")}<small>Source precision: ${esc(row.geographic_precision)}</small></td><td>${esc(row.species)}</td><td>${esc(row.collection_date_raw)}</td><td>${esc(row.detected_date_raw)}</td><td><details><summary>Details</summary><p>Strain: ${esc(row.strain)}<br>Classification: ${esc(row.classification)}<br>Sampling method: ${esc(row.sampling_method)}<br>Submitting agency: ${esc(row.submitting_agency)}</p><p>Snapshot reference: ${esc(context.sha256.slice(0,12))}:${row.source_row}</p></details><a href="${esc(context.source_url)}" target="_blank" rel="noopener noreferrer" aria-label="Open APHIS source table for CSV record ${row.source_row}">APHIS table ↗</a></td></tr>`).join("") || '<tr><td colspan="6">No dated records match these filters in this snapshot.</td></tr>'}</tbody></table></div>
            <div class="wse-outbreak-pagination"><button type="button" data-outbreak-page="-1"${this.outbreakPage === 0 ? " disabled" : ""}>Previous</button><span>Page ${this.outbreakPage + 1} of ${pages}</span><button type="button" data-outbreak-page="1"${this.outbreakPage >= pages - 1 ? " disabled" : ""}>Next</button></div>
          </details>
          <details class="wse-outbreak-provenance"><summary>Snapshot and source provenance</summary><p>${formatNumber(context.record_count)} source rows; ${formatNumber(context.repeated_rows_retained)} identical repeat rows retained. Snapshot supplied: ${esc(context.snapshot_supplied_date || "Not recorded")} (${esc(context.snapshot_date_basis)}). This is an offline snapshot, not a live feed.</p><p>${esc(basisLabel)} range: ${esc(range.min || "Unavailable")} to ${esc(range.max || "Unavailable")}. Latest detection date in file: ${esc(context.date_ranges.detected_date.max || "Unavailable")}.</p><p>File: ${esc(context.source_file)}<br>SHA-256: <code>${esc(context.sha256)}</code></p>${context.unmapped_states.length ? `<p>States that cannot be mapped: ${esc(context.unmapped_states.join(", "))}. Their records remain available in All U.S. states.</p>` : ""}<p>Reporting can lag collection. No matching records does not mean no infections or no surveillance activity. The positive-record CSV does not provide a testing denominator.</p></details>
        </div>`;
      this.renderOutbreakTimeline(this.outbreakNode.querySelector(".wse-outbreak-timeline"), view);
      if (this.mapNode) {
        const focused = this.mapNode.contains?.(document.activeElement) ? document.activeElement : null;
        const sampleIds = focused?.getAttribute("data-sample-ids");
        const stateCode = focused?.getAttribute("data-region-code");
        this.renderMap();
        this.updateEmphasis();
        if (focused) {
          const match = [...this.mapNode.querySelectorAll("[data-sample-ids], [data-region-code]")].find(node =>
            sampleIds ? node.getAttribute("data-sample-ids") === sampleIds : stateCode && node.getAttribute("data-region-code") === stateCode);
          (match || this.mapNode).focus({preventScroll: true});
        }
      }
      if (focusedControl) this.outbreakNode.querySelector(`[data-outbreak-control="${focusedControl}"]`)?.focus({preventScroll: true});
    }

    selectedOutbreakState() {
      const sample = this.sampleById.get(this.selectedSampleId);
      if (!sample || !["US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"].includes(String(sample.country || "").trim().toUpperCase())) return null;
      return this.outbreakStateCode(sample.state);
    }

    mapFocusState() {
      return this.outbreakContext?.states?.[this.outbreakScope] ? this.outbreakScope : this.selectedOutbreakState();
    }

    showSelectedState() {
      const code = this.mapFocusState();
      const region = this.mapBoundaries?.regions.find(item => item.country === "USA" && item.code === code);
      if (!region) return;
      const points = region.polygons.flat(2), xs = points.map(point => point[0]), ys = points.map(point => point[1]);
      this.setMapViewport([Math.min(...xs) - 2, Math.max(...xs) + 2, Math.min(...ys) - 2, Math.max(...ys) + 2]);
    }

    renderMapStateCard(view) {
      if (!this.mapStateCardNode) return;
      const code = view.code;
      this.mapStateCardNode.hidden = !code || Boolean(this.mapStateCardDismissed);
      if (this.mapStateCardNode.hidden) return;
      const basis = this.outbreakBasis === "collection_date" ? "Collection date" : "Date detected";
      this.mapStateCardNode.innerHTML = `
        <button type="button" class="wse-state-card-close" data-state-action="close" aria-label="Close state summary">×</button>
        <strong>${esc(this.outbreakContext.states[code] || code)}</strong>
        <div class="wse-state-card-value">${view.validWindow ? `${formatNumber(view.rows.length)} APHIS source records` : "Choose a valid date window"}</div>
        <p>${esc(basis)}<br>${esc(this.outbreakStart)} through ${esc(this.outbreakEnd)}</p>
        <p>State-level aggregate. ${formatNumber(view.undated)} records excluded for missing ${basis.toLowerCase()}.</p>
        ${view.outsideSnapshot ? '<p>Window outside snapshot coverage; zero matches do not establish absence.</p>' : ""}
        <p>Context only; no implied epidemiological linkage.</p>
        <div class="wse-state-card-actions"><button type="button" data-state-action="zoom">Zoom to state</button><button type="button" data-state-action="records">View records</button></div>`;
    }

    applyOutbreakLayer(svg) {
      if (this.outbreakContext?.status !== "READY") return;
      this.syncOutbreakDates();
      // State browsing filters the timeline/records, never the neighboring map states.
      const view = this.outbreakView("all"), details = this.outbreakView();
      const selectedCode = this.selectedOutbreakState();
      const focusCode = this.mapFocusState();
      if (this.mapStateButtonNode) {
        this.mapStateButtonNode.disabled = !focusCode;
        this.mapStateButtonNode.textContent = focusCode ? `Zoom to ${this.outbreakContext.states[focusCode]}` : "Select a state to zoom";
        this.mapStateButtonNode.title = focusCode ? "Fit this state in the map without changing the selected WINGS sample" : "Click a state or select a WINGS sample with a recorded U.S. state";
      }
      this.renderMapStateCard(details);
      const max = Math.max(1, ...view.counts.values());
      const active = this.outbreakLayerEnabled && view.validWindow;
      svg.querySelectorAll('[data-region-country="USA"]').forEach(path => {
        const code = path.getAttribute("data-region-code"), count = view.counts.get(code) || 0;
        path.setAttribute("data-sample-state", String(code === selectedCode));
        path.setAttribute("data-context-state", String(code === details.code));
        if (!active) return;
        path.style.fill = count ? `hsl(178 48% ${88 - 53 * Math.log1p(count) / Math.log1p(max)}%)` : "#f1f3f4";
        path.classList.add("wse-outbreak-state");
        path.setAttribute("tabindex", "0"); path.setAttribute("role", "button");
        path.setAttribute("aria-label", `${this.outbreakContext.states[code] || code}: ${count} matching source records; state aggregate${code === selectedCode ? "; selected WINGS sample state" : ""}`);
        path.setAttribute("aria-pressed", String(code === details.code));
        const title = path.querySelector("title");
        if (title) title.textContent = `${this.outbreakContext.states[code] || code}: ${count} matching source records\nState-level aggregate; no exact detection locations${code === selectedCode ? "\nSelected WINGS sample state" : ""}`;
        const choose = () => {
          this.outbreakScope = code;
          this.mapStateCardDismissed = false;
          this.outbreakPage = 0;
          this.renderOutbreak();
          this.outbreakNode.querySelector('[data-outbreak-control="scope"]')?.focus({preventScroll: true});
        };
        path.addEventListener("click", choose);
        path.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } });
      });
      // Redraw outlines above neighboring polygons so shared borders remain visible.
      const regionPaths = [...svg.querySelectorAll('[data-region-country="USA"]')];
      for (const [code, kind] of [[details.code !== selectedCode ? details.code : null, "context"], [selectedCode, "sample"]]) {
        const path = code && regionPaths.find(item => item.getAttribute("data-region-code") === code);
        if (path) svg.appendChild(svgEl("path", {d: path.getAttribute("d"), class: `wse-${kind}-state-outline`, "pointer-events": "none", "aria-hidden": "true"}));
      }
      if (this.mapLayerLegendNode) {
        this.mapLayerLegendNode.hidden = false;
        const basis = this.outbreakBasis === "collection_date" ? "Collection date" : "Date detected";
        this.mapLayerLegendNode.innerHTML = `
          <div><strong>WINGS samples:</strong> host-colored points; numbers show samples sharing coordinates. ${selectedCode ? `Solid burgundy outline = selected sample state (${esc(this.outbreakContext.states[selectedCode])}).` : ""}</div>
          <div><strong>APHIS:</strong> ${!this.outbreakLayerEnabled ? "State shading hidden; timeline and records remain available." : !view.validWindow ? "Enter a valid date window below to display state shading." : `<span class="wse-aphis-gradient" aria-hidden="true"></span> 0 (gray) to ${formatNumber(Math.max(0, ...view.counts.values()))} records (darkest teal). National relative scale; all U.S. states retain their counts.`}</div>
          <div>${esc(basis)} · ${esc(this.outbreakStart)} through ${esc(this.outbreakEnd)} · ${this.outbreakFollow ? "Following sample date" : "Date window locked"}. State-level context; no implied epidemiological linkage.</div>
          <div>Timeline / records: ${esc(details.scopeLabel)} Dashed outline = state being browsed. Non-U.S. areas are outside this APHIS layer's coverage; gray U.S. states have no matching dated records in this snapshot, not evidence of absence.</div>
          ${view.validWindow && view.outsideSnapshot ? '<div class="wse-outbreak-caution">Date window is outside the snapshot range; zero matches do not establish absence of detections.</div>' : ""}`;
      }
    }

    renderOutbreakTimeline(target, view) {
      if (!view.validWindow) { target.textContent = "Timeline unavailable until a valid date window is entered."; return; }
      const width = 900, height = 200, left = 65, right = 870, top = 25, bottom = 140;
      const svg = svgEl("svg", {viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": `APHIS records by ${this.outbreakBasis === "collection_date" ? "collection date" : "detection date"}`});
      const daily = (view.end - view.start) / 86400000 <= 90;
      const bins = new Map();
      view.rows.forEach(row => { const key = row[this.outbreakBasis].slice(0, daily ? 10 : 7); bins.set(key, (bins.get(key) || 0) + 1); });
      const max = Math.max(1, ...bins.values());
      const x = time => left + (time - view.start) / (view.end - view.start + 86400000) * (right - left);
      const label = (text, px, py, anchor = "middle") => { const node = svgEl("text", {x: px, y: py, "text-anchor": anchor, class: "wse-outbreak-axis"}); node.textContent = text; svg.appendChild(node); };
      [0, max].forEach(count => {
        const y = bottom - count / max * (bottom - top);
        svg.appendChild(svgEl("line", {x1:left, x2:right, y1:y, y2:y, class:"wse-outbreak-gridline"}));
        label(String(count), left - 8, y + 4, "end");
      });
      [...bins.entries()].sort().forEach(([key, count]) => {
        const start = this.outbreakEpoch(daily ? key : `${key}-01`);
        const date = new Date(start);
        const end = daily ? start + 86400000 : Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1);
        const from = Math.max(start, view.start), through = Math.min(end, view.end + 86400000);
        const bar = svgEl("rect", {x:x(from), y:bottom - count / max * (bottom - top), width:Math.max(1, x(through) - x(from) - 1), height:count / max * (bottom - top), class:"wse-outbreak-bar", tabindex:0, role:"button", "aria-label":`${key}: ${count} source records; filter to this period`});
        const title = svgEl("title"); title.textContent = `${key}: ${count} source records`; bar.appendChild(title);
        const choose = () => { this.outbreakStart = new Date(from).toISOString().slice(0, 10); this.outbreakEnd = new Date(through - 86400000).toISOString().slice(0, 10); this.outbreakFollow = false; this.outbreakPage = 0; this.renderOutbreak(true); this.outbreakNode.querySelector('[data-outbreak-control="start"]')?.focus({preventScroll: true}); };
        bar.addEventListener("click", choose);
        bar.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } });
        svg.appendChild(bar);
      });
      const sampleDate = this.outbreakEpoch(this.sampleById.get(this.selectedSampleId)?.collection_date);
      if (sampleDate !== null && sampleDate >= view.start && sampleDate <= view.end) {
        const line = svgEl("line", {x1:x(sampleDate + 43200000), x2:x(sampleDate + 43200000), y1:top - 6, y2:bottom, class:"wse-outbreak-sample-date"});
        const title = svgEl("title"); title.textContent = `Selected WINGS sample: ${this.selectedSampleId} · Collected: ${this.sampleById.get(this.selectedSampleId).collection_date}`; line.appendChild(title); svg.appendChild(line);
      }
      label(this.outbreakStart, left, bottom + 25, "start");
      label(this.outbreakEnd, right, bottom + 25, "end");
      label(`Source records per ${daily ? "day" : "month"} · ${this.outbreakBasis === "collection_date" ? "collection date" : "detection date"}`, (left + right) / 2, height - 8);
      if (!view.rows.length) label("No dated records match this window in the loaded snapshot", (left + right) / 2, 80);
      target.appendChild(svg);
    }

    treeLayout(root, width, height) {
      const leaves = [];
      let maxDistance = 0;
      const walk = (node, distance, depth) => {
        node._distance = distance;
        node._depth = depth;
        maxDistance = Math.max(maxDistance, distance);
        const children = node.children || [];
        if (!children.length) leaves.push(node);
        children.forEach((child) => walk(child, distance + Number(child.length || 0), depth + 1));
      };
      walk(root, 0, 0);
      const maxDepth = Math.max(1, ...leaves.map((leaf) => leaf._depth));
      const left = 22, right = 220, top = 20, bottom = 22;
      leaves.forEach((leaf, i) => { leaf._y = top + (i + 0.5) / leaves.length * (height - top - bottom); });
      const placeInternal = (node) => {
        const children = node.children || [];
        if (children.length) {
          children.forEach(placeInternal);
          node._y = children.reduce((sum,c)=>sum+c._y,0)/children.length;
        }
        const usable = width - left - right;
        node._x = left + (maxDistance > 0 ? node._distance / maxDistance : node._depth / maxDepth) * usable;
      };
      placeInternal(root);
      return {leaves, maxDistance, left, right, top, bottom};
    }

    segmentEvidence(sample, segment) {
      if (sample?.segments?.[segment]) return sample.segments[segment];
      const tree = this.payload.trees?.[segment];
      const tips = [];
      const visit = (node, parent) => {
        if (node.children?.length) node.children.forEach(child => visit(child, node));
        else if (node.sample_id === sample?.sample_id) {
          tips.push({name: node.name, parent_support: parent?.support == null ? null : String(parent.support)});
        }
      };
      if (tree?.root) visit(tree.root, null);
      return {record_status: "NOT_RECORDED", overall_status: "NOT_RECORDED", tips,
        tree_status: !tree ? "NO_TREE" : tips.length ? "PRESENT" : "ABSENT_FROM_TREE"};
    }

    treePresence(record) {
      if (record.tree_status === "NO_TREE") return "Tree unavailable";
      if (record.tree_status === "ABSENT_FROM_TREE") return "Sample absent from tree";
      const count = record.tips?.length || 0;
      return count > 1 ? `${count} matching tips — all highlighted` : "Sample present";
    }

    renderGenomeEvidence() {
      const sample = this.sampleById.get(this.selectedSampleId);
      if (!sample) {
        this.evidenceNode.innerHTML = this.samples.length
          ? '<p class="wse-empty">Select a sample to view its recorded genotype and highlight it across the segment trees.</p>'
          : '<p class="wse-empty">No samples are available.</p>';
        this.treeGridNode.querySelectorAll(".wse-tree-presence").forEach(node => { node.textContent = ""; });
        return;
      }
      const status = value => String(value || "NOT_RECORDED").replaceAll("_", " ");
      const genotype = sample.genotype || {status: "NOT_RECORDED", reason: "Rebuild the explorer data to include the recorded genotype."};
      const filtered = this.hostFilter !== "ALL" && sample.host !== this.hostFilter;
      this.evidenceNode.innerHTML = `
        <div class="wse-genotype"><strong>Recorded genotype: ${esc(genotype.call || status(genotype.status))}</strong><span>${esc(genotype.reason || "")}</span></div>
        ${filtered ? '<p class="wse-filter-notice">The selected sample is outside the host filter. Its genotype and tree highlights remain visible.</p>' : ""}
        `;
      this.treeGridNode.querySelectorAll(".wse-segment-tree").forEach(card => {
        card.querySelector(".wse-tree-presence").textContent = this.treePresence(this.segmentEvidence(sample, card.dataset.segment));
      });
    }

    referenceStatus(status) {
      return ({PRESENT: "Present in tree", NO_TREE: "Tree unavailable", NOT_IN_MANIFEST: "No metadata record for this segment", ABSENT_FROM_TREE: "Record supplied; tip absent from tree"})[status] || "Not recorded";
    }

    referenceLink(accession) {
      return /^[A-Z]{1,6}_?\d{5,12}\.\d+$/.test(accession || "")
        ? `<a href="https://www.ncbi.nlm.nih.gov/nuccore/${esc(accession)}" target="_blank" rel="noopener noreferrer">${esc(accession)} ↗</a>`
        : "Accession not recorded";
    }

    renderReferenceDetails() {
      if (!this.referenceNode) return;
      const context = this.referenceContext;
      if (!context) {
        this.referenceNode.innerHTML = '<p class="wse-reference-empty">Public reference metadata are not loaded. Existing tree tips are unchanged.</p>';
        return;
      }
      const ref = this.referenceById.get(this.selectedReferenceId);
      const known = value => esc(value || "Not recorded");
      const provenance = `<details class="wse-reference-provenance"><summary>Public reference provenance · ${this.references.length} reference groups · ${esc(context.record_count)} records</summary><p>Retrieved: ${known(context.retrieved_on)} · Manifest: ${known(context.source_file)}</p><p>Selection: ${known(context.selection_notes)}</p><p>Citation: ${known(context.citation)}</p><p>${esc(context.records_without_displayed_tips || 0)} manifest records have no displayed tip.</p><p>Manifest SHA-256: <code>${known(context.manifest_sha256)}</code></p>${Object.entries(this.payload.trees || {}).map(([segment, tree]) => `<p>${esc(segment)} tree: ${known(tree.source_file)} · SHA-256: <code>${known(tree.source_sha256)}</code></p>`).join("")}<p>Checksums identify the supplied files; they do not verify the submitter's metadata.</p></details>`;
      const legend = '<p class="wse-reference-legend">● WINGS sample (host color) · ■ Public reference (teal) · Gray circle: unannotated tip. Selecting a reference retains the selected WINGS sample for comparison. Tree proximity alone does not establish transmission.</p>';
      if (!ref) {
        this.referenceNode.innerHTML = legend + '<p>Select a teal square or choose a public reference to see its record and linked segments.</p>' + provenance;
        return;
      }
      const order = this.payload.segment_order || ["HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS"];
      this.referenceNode.innerHTML = legend + `<article class="wse-reference-card"><h4>Public reference · ${known(ref.isolate || ref.reference_id)}</h4><p>Reference ID: ${known(ref.reference_id)} · Host: ${known(ref.host)} · Location: ${known([ref.state, ref.country].filter(Boolean).join(", "))}</p><p>Collection date: ${known(ref.collection_date)} · Precision: ${known(ref.collection_date_precision)} · Segment linkage: ${known(ref.linkage_basis || "Single record; cross-segment identity not established")}</p><p>Public record metadata; WINGS raw-read QC and coverage are not available for this reference.</p><div class="wse-reference-segments">${order.map(segment => {
        const record = ref.segments?.[segment] || {};
        return `<div><strong>${esc(segment)}</strong><span>${esc(this.referenceStatus(record.status))}</span>${record.accession_version ? this.referenceLink(record.accession_version) : ""}${(record.tips || []).map(tip => `<small>Tip: ${esc(tip.name)}<br>Parent-node support (as recorded): ${known(tip.parent_support)}</small>`).join("")}</div>`;
      }).join("")}</div></article>` + provenance;
    }

    revealSelectedTips() {
      // Scroll inside each tree only; do not move the report viewport.
      this.root.querySelectorAll(".wse-tree").forEach(container => {
        if (container.hidden) return;
        const tip = [...container.querySelectorAll(".wse-tree-tip")].find(el => this.selectedReferenceId ? el.dataset.referenceId === this.selectedReferenceId : this.selectedSampleId && el.dataset.sampleId === this.selectedSampleId);
        if (!tip) return;
        const box = tip.getBoundingClientRect(), viewport = container.getBoundingClientRect();
        if (box.top < viewport.top || box.bottom > viewport.bottom) {
          container.scrollTop += box.top - viewport.top - container.clientHeight / 2;
        }
        if (box.left < viewport.left || box.right > viewport.right) {
          container.scrollLeft += box.left - viewport.left - container.clientWidth / 3;
        }
      });
    }

    renderTrees() {
      const all = this.treeMode === "all";
      this.treeNode.hidden = all;
      this.treeNoteNode.hidden = all;
      this.treeGridNode.hidden = !all;
      this.treeGridNode.innerHTML = "";
      if (!all) {
        this.renderTree(this.segment, this.treeNode, this.treeNoteNode);
        return;
      }
      this.treeNode.innerHTML = "";
      (this.payload.segment_order || ["HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS"]).forEach(segment => {
        const card = document.createElement("article");
        card.className = "wse-segment-tree";
        card.dataset.segment = segment;
        card.innerHTML = `<div class="wse-panel-heading"><h4>${esc(segment)}</h4><span class="wse-panel-note"></span></div><p class="wse-tree-presence"></p><div class="wse-tree" tabindex="0" role="region" aria-label="${esc(segment)} tree, scroll to explore"></div>`;
        this.treeGridNode.appendChild(card);
        this.renderTree(segment, card.querySelector(".wse-tree"), card.querySelector(".wse-panel-note"));
      });
    }

    renderTree(segment, target, note) {
      target.innerHTML = "";
      if (!segment || !this.payload.trees?.[segment]) {
        note.textContent = "Tree unavailable";
        target.innerHTML = `<div class="wse-empty">No segment phylogeny was supplied.</div>`;
        return;
      }
      const record = this.payload.trees[segment];
      const visibleIds = new Set(this.visibleSamples().map(s=>s.sample_id));
      note.textContent = `${segment} · ${record.tip_count} tips · ${record.source_file || "Source not recorded"}`;
      const tipCount = Math.max(1, record.tip_count || 1);
      const width = this.treeMode === "all" ? 640 : 900;
      const height = Math.max(this.treeMode === "all" ? 220 : 450, tipCount * 25 + 40);
      const root = JSON.parse(JSON.stringify(record.root));
      const layout = this.treeLayout(root, width, height);
      const svg = svgEl("svg", {viewBox:`0 0 ${width} ${height}`, role:"group", "aria-label":`${segment} phylogeny`});

      const drawBranches = (node) => {
        const children = node.children || [];
        if (children.length) {
          const ys = children.map(c=>c._y);
          svg.appendChild(svgEl("line", {x1:node._x,y1:Math.min(...ys),x2:node._x,y2:Math.max(...ys),class:"wse-tree-branch"}));
          children.forEach((child) => {
            const branch = svgEl("line", {x1:node._x,y1:child._y,x2:child._x,y2:child._y,class:"wse-tree-branch"});
            if (child.sample_id) branch.setAttribute("data-sample-id", child.sample_id);
            if (child.reference_id) branch.setAttribute("data-reference-id", child.reference_id);
            svg.appendChild(branch);
            if (child.label && /^[0-9]+(?:\.[0-9]+)?(?:\/[0-9]+(?:\.[0-9]+)?)*$/.test(child.label) && child.children?.length) {
              const support = svgEl("text", {x:(node._x+child._x)/2,y:child._y-4,"text-anchor":"middle",class:"wse-support-label"});
              support.textContent = child.label;
              svg.appendChild(support);
            }
            drawBranches(child);
          });
        }
      };
      drawBranches(root);

      layout.leaves.forEach((leaf) => {
        const sample = this.sampleById.get(leaf.sample_id);
        const reference = this.referenceById.get(leaf.reference_id);
        const visible = !sample || visibleIds.has(leaf.sample_id);
        const group = svgEl("g", {
          class:`wse-tree-tip${reference ? " wse-public-tip" : ""}${visible ? "" : " is-filtered"}`,
          "data-sample-id":leaf.sample_id || "",
          "data-reference-id":reference ? leaf.reference_id : "",
          tabindex: sample || reference ? 0 : -1,
          role: sample || reference ? "button" : "img",
          "aria-label": sample ? `Select ${sample.sample_id}; tip ${leaf.name}` : reference ? `Select public reference ${reference.reference_id}; accession ${leaf.accession_version}` : `Unannotated tip ${leaf.name}`,
        });
        const dot = reference ? svgEl("rect", {x:leaf._x+2,y:leaf._y-5,width:10,height:10,fill:"#007C83",class:"wse-tree-tip-dot"}) : svgEl("circle", {cx:leaf._x+7,cy:leaf._y,r:4.8,fill:sample?this.hostColorFor(sample):GRAY,class:"wse-tree-tip-dot"});
        const label = svgEl("text", {x:leaf._x+18,y:leaf._y+4,class:"wse-tree-tip-label"});
        label.textContent = sample ? sample.sample_id : reference ? leaf.accession_version : leaf.name;
        group.append(dot,label);
        if (leaf.sample_id) {
          group.addEventListener("click", () => this.selectSample(leaf.sample_id));
          group.addEventListener("mouseenter", () => this.setHover(leaf.sample_id));
          group.addEventListener("mouseleave", () => this.clearHover());
          group.addEventListener("keydown", (event) => { if(event.key === "Enter" || event.key === " ") { event.preventDefault(); this.selectSample(leaf.sample_id); } });
        }
        if (reference) {
          group.addEventListener("click", () => this.selectReference(leaf.reference_id));
          group.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); this.selectReference(leaf.reference_id); } });
        }
        const title = svgEl("title");
        title.textContent = sample ? `${sample.sample_id}\n${sample.host} · ${dateLabel(sample.collection_date)}\nTip: ${leaf.name}` : reference ? `Public reference: ${reference.reference_id}\n${leaf.accession_version}\n${reference.host || "Host not recorded"} · ${reference.collection_date || "Date not recorded"}\nTip: ${leaf.name}` : `Unannotated tip: ${leaf.name}`;
        group.appendChild(title);
        svg.appendChild(group);
      });

      if (layout.maxDistance > 0) {
        const scaleY = height - 10;
        const x0 = layout.left, x1 = layout.left + Math.min(120, width - layout.left - layout.right);
        svg.appendChild(svgEl("line", {x1:x0,y1:scaleY,x2:x1,y2:scaleY,class:"wse-tree-scale"}));
        const scaleValue = layout.maxDistance * ((x1-x0)/(width-layout.left-layout.right));
        const text = svgEl("text", {x:(x0+x1)/2,y:scaleY-5,"text-anchor":"middle",class:"wse-tree-scale-label"});
        text.textContent = `${scaleValue.toPrecision(2)} substitutions/site`;
        svg.appendChild(text);
      }
      target.appendChild(svg);
    }

    updateSelection() {
      const select = this.genomeControlsNode.querySelector(".wse-sample-select");
      if (select) select.value = this.selectedSampleId || "";
      this.renderSelected();
      this.renderMapSelection();
      this.renderOutbreak();
      this.renderGenomeEvidence();
      this.renderReferenceDetails();
      const refSelect = this.genomeControlsNode.querySelector(".wse-reference-select");
      if (refSelect) refSelect.value = this.selectedReferenceId || "";
      this.renderEbird();
      this.renderEcology();
      this.updateEmphasis();
      this.revealSelectedTips();
    }

    updateEmphasis() {
      const focus = this.selectedSampleId;
      this.root.querySelectorAll("[data-sample-id]").forEach((el) => {
        const id = el.getAttribute("data-sample-id");
        el.classList.toggle("is-selected", Boolean(focus && id === focus));
        el.classList.toggle("is-hovered", Boolean(this.hoverSampleId && id === this.hoverSampleId));
        if (el.classList.contains("wse-tree-tip") && id) el.setAttribute("aria-pressed", String(id === focus));
      });
      this.root.querySelectorAll("[data-reference-id]").forEach(el => {
        const id = el.getAttribute("data-reference-id");
        if (!id) return;
        const selected = Boolean(this.selectedReferenceId && id === this.selectedReferenceId);
        el.classList.toggle("is-selected", selected);
        if (el.classList.contains("wse-tree-tip")) el.setAttribute("aria-pressed", String(selected));
      });
      this.root.querySelectorAll("[data-sample-ids]").forEach((el) => {
        const ids = (el.getAttribute("data-sample-ids") || "").split("|");
        el.classList.toggle("is-selected", Boolean(focus && ids.includes(focus)));
        el.setAttribute("aria-pressed", String(Boolean(focus && ids.includes(focus))));
      });
    }
  }

  const initialize = () => {
    document.querySelectorAll(".wings-surveillance-explorer").forEach((root, index) => {
      if (root.dataset.wseRendered === "true") return;
      const dataId = root.dataset.wseDataId || `wings-surveillance-data-${index}`;
      const script = document.getElementById(dataId);
      if (!script) return;
      let payload;
      try { payload = JSON.parse(script.textContent || "{}"); } catch (error) {
        root.innerHTML = `<div class="wse-error">Surveillance Explorer data could not be parsed.</div>`;
        return;
      }
      root.dataset.wseRendered = "true";
      const explorer = new Explorer(root, payload);
      // WINGS_BRAID_CLOCK_HOOK_BEGIN
      try {
        globalThis.WINGS_BRAID_CLOCK.mountExplorer(explorer);
      } catch (error) {
        const notice = document.createElement("p");
        notice.className = "wbc-preview-error";
        notice.setAttribute("role", "status");
        notice.textContent = "Genome Braid / Ecological Clock unavailable: " + error.message;
        root.appendChild(notice);
        console.error("WINGS optional observatory preview:", error);
      }
      // WINGS_BRAID_CLOCK_HOOK_END
    });
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, {once:true});
  else initialize();
})();
