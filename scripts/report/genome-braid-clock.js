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
