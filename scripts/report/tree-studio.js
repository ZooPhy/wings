(() => {
  "use strict";

  const VERSION = "0.1.9";
  const SEGMENTS = ["PB2", "PB1", "PA", "HA", "NP", "NA", "MP", "NS"];
  const COLORS = ["#8c1d40", "#007c83", "#176b3a", "#6f2da8", "#c45500", "#006dae", "#7d6608", "#37474f", "#b3261e", "#00838f", "#5c1229", "#7a5b00"];
  const NEUTRAL = "#69777d";
  const LIGHT = "#dfe5e7";
  const GOLD = "#ffc627";
  const FILTER_MISSING = "__WINGS_FILTER_MISSING__";
  let sessionCounter = 0;
  const sessions = new Map();

  const POPUP_CSS = String.raw`
:root{--ink:#22363e;--muted:#64777e;--line:#d6dfe1;--panel:#fff;--wash:#f5f8f8;--maroon:#8c1d40;--teal:#007c83;--gold:#ffc627}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);background:#eef3f3}button,select,input{font:inherit}button,select,input[type=text]{border:1px solid #b9c6ca;border-radius:6px;background:#fff;color:var(--ink);min-height:36px;padding:7px 10px}.ts-shell{display:grid;grid-template-rows:auto auto minmax(0,1fr);min-height:100vh}.ts-head{display:flex;gap:20px;align-items:flex-start;justify-content:space-between;padding:16px 20px;background:#fff;border-top:7px solid #000;border-bottom:1px solid var(--line)}.ts-overline{font-size:10px;letter-spacing:.18em;color:var(--maroon);font-weight:800;text-transform:uppercase}.ts-title{font-size:24px;font-weight:800;margin-top:3px;letter-spacing:-.45px}.ts-sub{color:var(--muted);font-size:12px;margin-top:5px}.ts-badge{font-size:10px;border:1px solid #b8cfcc;background:#eaf4f2;color:#246d6b;border-radius:5px;padding:6px 9px;white-space:nowrap}.ts-controls{display:flex;flex-wrap:wrap;gap:10px 12px;align-items:end;padding:10px 16px;background:#f9fbfb;border-bottom:1px solid var(--line)}.ts-control{display:grid;gap:3px}.ts-control>span{font-size:9px;letter-spacing:.08em;font-weight:800;text-transform:uppercase;color:var(--muted)}.ts-search{min-width:210px}.ts-spacer{flex:1}.ts-btn{cursor:pointer;font-weight:700}.ts-btn:hover{border-color:var(--teal);background:#eef7f6}.ts-btn:disabled{cursor:not-allowed;opacity:.45;background:#f4f6f6;border-color:#d7dfe1}.ts-btn[aria-pressed=true]{background:#22363e;color:#fff;border-color:#22363e}.ts-btn[aria-pressed=true]:hover{background:#314a54;border-color:#314a54}.ts-main{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:12px;padding:12px;min-height:0}.ts-canvas-card,.ts-side{background:#fff;border:1px solid var(--line);border-radius:10px;min-width:0;overflow:hidden}.ts-canvas-head{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid var(--line);font-size:12px}.ts-status{color:var(--muted)}.ts-canvas-wrap{position:relative;height:calc(100vh - 185px);min-height:520px;background:#fff;overflow:hidden}.ts-canvas-wrap svg{width:100%;height:100%;display:block;touch-action:none;user-select:none}.ts-canvas-wrap.ts-lasso-active svg{cursor:crosshair}.ts-lasso-path{fill:rgba(0,124,131,.08);stroke:var(--teal);stroke-width:2;stroke-dasharray:7 5;vector-effect:non-scaling-stroke;pointer-events:none}.ts-branch{fill:none;stroke:#6c757b;stroke-width:1.4;vector-effect:non-scaling-stroke}.ts-branch.ts-dim{opacity:.2}.ts-tip{cursor:pointer;outline:none}.ts-tip text{font-size:11px;fill:#24383f}.ts-tip circle{stroke:#fff;stroke-width:1.2;vector-effect:non-scaling-stroke}.ts-tip.ts-selected circle{stroke:var(--gold);stroke-width:4}.ts-tip.ts-selected text{font-weight:800;fill:var(--maroon)}.ts-tip.ts-multi-selected circle{stroke:var(--gold);stroke-width:4}.ts-tip.ts-multi-selected text{font-weight:800;fill:var(--maroon)}.ts-tip.ts-search-hit text{text-decoration:underline;font-weight:800}.ts-tip.ts-dim{opacity:.14}.ts-tip.ts-selected.ts-dim,.ts-tip.ts-multi-selected.ts-dim{opacity:.5}.ts-tip.ts-filter-hit circle{stroke:#40545c;stroke-width:1.8}.ts-tip.ts-filter-hit.ts-selected circle,.ts-tip.ts-filter-hit.ts-multi-selected circle{stroke:var(--gold);stroke-width:4}.ts-support{font-size:8px;fill:#7d898e}.ts-root{fill:#fff;stroke:var(--maroon);stroke-width:2;vector-effect:non-scaling-stroke}.ts-scale{stroke:#202124;stroke-width:2;vector-effect:non-scaling-stroke}.ts-scale-label{font-size:9px;fill:#46545a}.ts-side{padding:14px;overflow:auto;max-height:calc(100vh - 185px)}.ts-side h3{font-size:16px;margin:0 0 10px}.ts-side h4{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:18px 0 7px}.ts-meta{display:grid;gap:6px;font-size:12px}.ts-meta-row{display:grid;grid-template-columns:95px minmax(0,1fr);gap:8px;border-bottom:1px solid #edf0f1;padding-bottom:5px}.ts-meta-row span:first-child{color:var(--muted)}.ts-note{font-size:11px;line-height:1.45;color:var(--muted);padding:8px 9px;background:#f5f8f8;border-left:3px solid var(--teal);margin:10px 0}.ts-warning{border-left-color:#b27617;background:#fbf3df;color:#6a5426}.ts-legend{display:grid;gap:5px}.ts-legend-row{display:flex;align-items:center;gap:7px;font-size:11px}.ts-swatch{width:11px;height:11px;border-radius:50%;flex:0 0 auto}.ts-empty{color:var(--muted);font-size:12px;padding:10px 0}.ts-pills{display:flex;gap:5px;flex-wrap:wrap}.ts-pill{background:#edf4f3;border:1px solid #d3e3e1;color:#216964;border-radius:5px;padding:3px 6px;font-size:10px}.ts-selection-list{display:flex;gap:5px;flex-wrap:wrap;max-height:120px;overflow:auto}.ts-selection-list .ts-pill{background:#fff7df;border-color:#ead18a;color:#654f12}.ts-filter-values{display:flex;flex-wrap:wrap;gap:6px;margin:7px 0 4px}.ts-filter-chip{cursor:pointer;border:1px solid #c8d3d5;background:#fff;color:var(--ink);border-radius:999px;padding:5px 8px;font-size:10px;min-height:0}.ts-filter-chip[aria-pressed=true]{background:#22363e;color:#fff;border-color:#22363e}.ts-filter-chip:hover{border-color:var(--teal)}.ts-filter-summary{font-size:11px;color:var(--muted);line-height:1.45}.ts-filter-clear{margin-top:7px;min-height:30px!important;padding:4px 8px!important;font-size:10px}.ts-help{font-size:10px;color:var(--muted);margin-top:7px}.ts-no-tree{display:grid;place-items:center;height:100%;color:var(--muted);font-weight:700}.ts-footer-note{font-size:10px;color:var(--muted);margin-top:12px;line-height:1.5}@media(max-width:900px){.ts-main{grid-template-columns:1fr}.ts-side{max-height:none}.ts-canvas-wrap{height:65vh;min-height:430px}.ts-head{display:block}.ts-badge{display:inline-block;margin-top:8px}}
`;

  const escHtml = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[ch]));
  const escAttr = value => escHtml(value);
  const clean = (value) => value == null ? "" : String(value).trim();
  const scalarText = value => {
    if (value == null) return "";
    if (["string","number","boolean"].includes(typeof value)) return String(value).trim();
    return "";
  };
  function genotypeText(value) {
    const scalar = scalarText(value);
    if (scalar) return scalar;
    if (!value || typeof value !== "object") return "";
    for (const key of ["call","genotype","label","name","value"]) {
      const nested = genotypeText(value[key]);
      if (nested) return nested;
    }
    return "";
  }

  const US_STATE_CODES = Object.freeze({
    "ALABAMA":"AL","ALASKA":"AK","ARIZONA":"AZ","ARKANSAS":"AR","CALIFORNIA":"CA",
    "COLORADO":"CO","CONNECTICUT":"CT","DELAWARE":"DE","DISTRICT OF COLUMBIA":"DC",
    "FLORIDA":"FL","GEORGIA":"GA","HAWAII":"HI","IDAHO":"ID","ILLINOIS":"IL",
    "INDIANA":"IN","IOWA":"IA","KANSAS":"KS","KENTUCKY":"KY","LOUISIANA":"LA",
    "MAINE":"ME","MARYLAND":"MD","MASSACHUSETTS":"MA","MICHIGAN":"MI","MINNESOTA":"MN",
    "MISSISSIPPI":"MS","MISSOURI":"MO","MONTANA":"MT","NEBRASKA":"NE","NEVADA":"NV",
    "NEW HAMPSHIRE":"NH","NEW JERSEY":"NJ","NEW MEXICO":"NM","NEW YORK":"NY",
    "NORTH CAROLINA":"NC","NORTH DAKOTA":"ND","OHIO":"OH","OKLAHOMA":"OK","OREGON":"OR",
    "PENNSYLVANIA":"PA","RHODE ISLAND":"RI","SOUTH CAROLINA":"SC","SOUTH DAKOTA":"SD",
    "TENNESSEE":"TN","TEXAS":"TX","UTAH":"UT","VERMONT":"VT","VIRGINIA":"VA",
    "WASHINGTON":"WA","WEST VIRGINIA":"WV","WISCONSIN":"WI","WYOMING":"WY",
    "PUERTO RICO":"PR","GUAM":"GU","AMERICAN SAMOA":"AS","NORTHERN MARIANA ISLANDS":"MP",
    "U.S. VIRGIN ISLANDS":"VI","US VIRGIN ISLANDS":"VI","VIRGIN ISLANDS":"VI",
    "WASHINGTON DC":"DC","WASHINGTON, DC":"DC","D.C.":"DC"
  });
  const US_STATE_CODE_SET = new Set(Object.values(US_STATE_CODES));
  function normalizeUSState(value) {
    const raw = clean(value);
    if (!raw) return "";
    let key = raw.toUpperCase().replace(/^US[-_ ]/, "").replace(/\s+/g, " ").trim();
    if (US_STATE_CODES[key]) return US_STATE_CODES[key];
    if (US_STATE_CODE_SET.has(key)) return key;
    return raw;
  }
  const parseDate = value => /^\d{4}-\d{2}-\d{2}$/.test(clean(value)) ? Date.parse(`${value}T00:00:00Z`) : NaN;
  const numericSupport = value => /^[0-9]+(?:\.[0-9]+)?(?:\/[0-9]+(?:\.[0-9]+)?)*$/.test(clean(value));

  function cloneSourceTree(root) {
    let uid = 0, leafOrder = 0;
    const walk = (node, path = "r") => {
      const out = {
        _uid: `n${uid++}`,
        _sourcePath: path,
        name: clean(node.name),
        label: clean(node.label),
        length: Number.isFinite(Number(node.length)) ? Number(node.length) : 0,
        sample_id: clean(node.sample_id),
        reference_id: clean(node.reference_id),
        accession_version: clean(node.accession_version),
      };
      if (Array.isArray(node.children) && node.children.length) {
        out.children = node.children.map((child, i) => walk(child, `${path}.${i}`));
      } else {
        out.children = [];
        out._leafOrder = leafOrder++;
      }
      return out;
    };
    return walk(root);
  }

  function annotateTree(root) {
    const visit = node => {
      if (!node.children?.length) {
        node._leafCount = 1;
        node._minLeafOrder = node._leafOrder ?? Number.MAX_SAFE_INTEGER;
        return node;
      }
      node.children.forEach(visit);
      node._leafCount = node.children.reduce((s, c) => s + c._leafCount, 0);
      node._minLeafOrder = Math.min(...node.children.map(c => c._minLeafOrder));
      return node;
    };
    return visit(root);
  }

  function graphFromTree(root) {
    const nodes = new Map(), adj = new Map();
    const ensure = node => {
      nodes.set(node._uid, node);
      if (!adj.has(node._uid)) adj.set(node._uid, []);
    };
    const walk = node => {
      ensure(node);
      for (const child of node.children || []) {
        ensure(child);
        const length = Math.max(0, Number(child.length) || 0);
        adj.get(node._uid).push({to: child._uid, length});
        adj.get(child._uid).push({to: node._uid, length});
        walk(child);
      }
    };
    walk(root);
    return {nodes, adj, sourceRootId: root._uid};
  }

  function cloneGraph(graph) {
    return {
      nodes: new Map([...graph.nodes].map(([id, n]) => [id, {...n, children: []}])),
      adj: new Map([...graph.adj].map(([id, edges]) => [id, edges.map(e => ({...e}))])),
      sourceRootId: graph.sourceRootId,
    };
  }

  function replaceEdge(adj, a, b, rootId, lenA, lenB) {
    adj.set(a, (adj.get(a) || []).filter(e => e.to !== b));
    adj.set(b, (adj.get(b) || []).filter(e => e.to !== a));
    adj.set(rootId, [{to:a,length:lenA},{to:b,length:lenB}]);
    adj.get(a).push({to:rootId,length:lenA});
    adj.get(b).push({to:rootId,length:lenB});
  }

  function rootedFromGraph(graph, rootId) {
    const build = (id, parent = null, parentLength = 0) => {
      const src = graph.nodes.get(id) || {_uid:id,name:"",label:"",sample_id:"",reference_id:"",accession_version:""};
      const out = {...src, length: parentLength, children: []};
      for (const edge of graph.adj.get(id) || []) {
        if (edge.to === parent) continue;
        out.children.push(build(edge.to, id, edge.length));
      }
      return out;
    };
    const root = build(rootId);
    root.length = 0;
    return annotateTree(root);
  }

  function farthestLeaf(graph, startId) {
    let best = {id:startId, distance:-1};
    const stack = [{id:startId,parent:null,distance:0}];
    while (stack.length) {
      const cur = stack.pop();
      const node = graph.nodes.get(cur.id);
      const degree = (graph.adj.get(cur.id) || []).length;
      const isLeaf = node && (!node.children?.length) && degree <= 1;
      if (isLeaf && cur.distance > best.distance) best = {id:cur.id,distance:cur.distance};
      for (const edge of graph.adj.get(cur.id) || []) if (edge.to !== cur.parent) {
        stack.push({id:edge.to,parent:cur.id,distance:cur.distance + edge.length});
      }
    }
    return best;
  }

  function pathBetween(graph, startId, targetId) {
    const stack = [{id:startId,parent:null}];
    const parent = new Map([[startId, null]]), edgeLen = new Map();
    while (stack.length) {
      const cur = stack.pop();
      if (cur.id === targetId) break;
      for (const edge of graph.adj.get(cur.id) || []) {
        if (parent.has(edge.to)) continue;
        parent.set(edge.to, cur.id);
        edgeLen.set(edge.to, edge.length);
        stack.push({id:edge.to,parent:cur.id});
      }
    }
    if (!parent.has(targetId)) return [];
    const ids = [];
    let id = targetId;
    while (id != null) { ids.push(id); id = parent.get(id); }
    ids.reverse();
    const path = [];
    for (let i=0;i<ids.length;i++) path.push({id:ids[i], lengthFromPrevious:i===0?0:edgeLen.get(ids[i])||0});
    return path;
  }

  function midpointRoot(sourceRoot) {
    const base = annotateTree(cloneSourceTree(sourceRoot));
    const graph = graphFromTree(base);
    const leaves = [...graph.nodes.values()].filter(n => !n.children?.length);
    if (leaves.length < 2) return base;
    const a = farthestLeaf(graph, leaves[0]._uid).id;
    const b = farthestLeaf(graph, a).id;
    const path = pathBetween(graph, a, b);
    const total = path.reduce((s,p)=>s+p.lengthFromPrevious,0);
    const half = total/2;
    let walked = 0;
    for (let i=1;i<path.length;i++) {
      const len = path[i].lengthFromPrevious;
      if (Math.abs(walked + len - half) < 1e-12) return rootedFromGraph(graph, path[i].id);
      if (walked + len > half) {
        const g = cloneGraph(graph);
        const rootId = "midpoint-root";
        g.nodes.set(rootId,{_uid:rootId,name:"",label:"",sample_id:"",reference_id:"",accession_version:"",children:[]});
        g.adj.set(rootId,[]);
        const distFromA = half - walked;
        replaceEdge(g.adj, path[i-1].id, path[i].id, rootId, distFromA, len - distFromA);
        return rootedFromGraph(g, rootId);
      }
      walked += len;
    }
    return rootedFromGraph(graph, graph.sourceRootId);
  }

  function outgroupRoot(sourceRoot, tipKey) {
    const base = annotateTree(cloneSourceTree(sourceRoot));
    const graph = graphFromTree(base);
    const tip = [...graph.nodes.values()].find(n => leafKey(n) === tipKey);
    if (!tip) return base;
    const edges = graph.adj.get(tip._uid) || [];
    if (edges.length !== 1) return base;
    const edge = edges[0];
    const g = cloneGraph(graph);
    const rootId = "outgroup-root";
    g.nodes.set(rootId,{_uid:rootId,name:"",label:"",sample_id:"",reference_id:"",accession_version:"",children:[]});
    g.adj.set(rootId,[]);
    replaceEdge(g.adj, tip._uid, edge.to, rootId, edge.length/2, edge.length/2);
    return rootedFromGraph(g, rootId);
  }

  function leafKey(node) {
    if (node.sample_id) return `s:${node.sample_id}`;
    if (node.reference_id) return `r:${node.reference_id}`;
    return `t:${node.name}`;
  }

  function allLeaves(root) {
    const leaves=[];
    (function walk(node){ if (!node.children?.length) leaves.push(node); else node.children.forEach(walk); })(root);
    return leaves;
  }

  function leafInfo(node, data) {
    if (node.sample_id) {
      const s = data.sampleById.get(node.sample_id) || {};
      return {
        key: leafKey(node), source:"WINGS", id:node.sample_id, tip:node.name,
        label:node.sample_id, host:clean(s.host), genotype:genotypeText(s.genotype),
        country:clean(s.country), state:normalizeUSState(s.state), state_raw:clean(s.state), date:clean(s.collection_date),
        isolate:clean(s.isolate), accession:"", sample_id:node.sample_id, reference_id:"",
      };
    }
    if (node.reference_id) {
      const r = data.referenceById.get(node.reference_id) || {};
      const segmentRec = r.segments?.[data.segment] || {};
      return {
        key:leafKey(node), source:"Public reference", id:node.reference_id, tip:node.name,
        label:clean(r.isolate || r.reference_id || node.reference_id), host:clean(r.host),
        genotype:genotypeText(r.genotype) || genotypeText(r.genotype_call), country:clean(r.country), state:normalizeUSState(r.state), state_raw:clean(r.state),
        date:clean(r.collection_date), isolate:clean(r.isolate),
        accession:clean(segmentRec.accession_version || node.accession_version || r.accession_version),
        sample_id:"", reference_id:node.reference_id,
      };
    }
    return {key:leafKey(node),source:"Unannotated",id:node.name,tip:node.name,label:node.name,host:"",genotype:"",country:"",state:"",state_raw:"",date:"",isolate:"",accession:"",sample_id:"",reference_id:""};
  }

  function traitValue(info, trait) {
    if (trait === "source") return info.source;
    if (trait === "collection_date") return info.date;
    return clean(info[trait]);
  }

  function filterTraitValue(info, trait) {
    const value = traitValue(info, trait);
    return value || FILTER_MISSING;
  }

  function matchesTraitFilter(info, trait, selectedValues) {
    if (!trait || trait === "none" || !Array.isArray(selectedValues) || selectedValues.length === 0) return true;
    return selectedValues.includes(filterTraitValue(info, trait));
  }

  function descendantHasFilterMatch(node, data, trait, selectedValues) {
    if (!trait || trait === "none" || !Array.isArray(selectedValues) || selectedValues.length === 0) return true;
    return allLeaves(node).some(leaf => matchesTraitFilter(leafInfo(leaf, data), trait, selectedValues));
  }

  function sortTree(root, mode, data) {
    const metric = node => {
      const leaves = allLeaves(node);
      if (mode === "ladder-asc" || mode === "ladder-desc") return leaves.length;
      if (mode === "date") {
        const dates = leaves.map(l=>parseDate(leafInfo(l,data).date)).filter(Number.isFinite);
        return dates.length ? Math.min(...dates) : Number.POSITIVE_INFINITY;
      }
      return Math.min(...leaves.map(l=>Number.isFinite(l._minLeafOrder)?l._minLeafOrder:(Number.isFinite(l._leafOrder)?l._leafOrder:Number.MAX_SAFE_INTEGER)));
    };
    const walk = node => {
      node.children?.forEach(walk);
      if (!node.children?.length) return;
      node.children.sort((a,b)=> {
        const av=metric(a), bv=metric(b);
        if (mode === "ladder-desc") return bv-av;
        return av-bv;
      });
    };
    walk(root);
    return root;
  }

  function categoricalColors(values) {
    const unique = [...new Set(values.filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    return new Map(unique.map((v,i)=>[v,COLORS[i%COLORS.length]]));
  }

  function dateColor(value, min, max) {
    const n=parseDate(value);
    if (!Number.isFinite(n) || !Number.isFinite(min) || !Number.isFinite(max)) return "#aeb7bb";
    const t=max===min?0.5:(n-min)/(max-min);
    const hue=215-(195*t);
    return `hsl(${hue} 62% 43%)`;
  }

  function colorContext(root, data, trait) {
    const leaves=allLeaves(root), infos=leaves.map(l=>leafInfo(l,data));
    const values=infos.map(i=>traitValue(i,trait));
    if (trait === "collection_date") {
      const dates=values.map(parseDate).filter(Number.isFinite), min=Math.min(...dates), max=Math.max(...dates);
      return {color:v=>dateColor(v,min,max), values:[...new Set(values.filter(Boolean))].sort(), continuous:true, min, max, missingCount:values.filter(v=>!v).length};
    }
    const map=categoricalColors(values);
    return {color:v=>map.get(v)||"#aeb7bb", values:[...map.keys()], continuous:false, missingCount:values.filter(v=>!v).length};
  }

  function descendantConsensus(node, data, trait) {
    const vals=[...new Set(allLeaves(node).map(l=>traitValue(leafInfo(l,data),trait)).filter(Boolean))];
    return vals.length===1?vals[0]:"";
  }

  function leafLabel(info, mode) {
    if (mode === "tip") return info.tip || info.id;
    if (mode === "accession") return info.accession || info.id;
    if (mode === "isolate") return info.isolate || info.id;
    if (mode === "host") return info.host || info.id;
    if (mode === "genotype") return info.genotype || info.id;
    return info.id || info.tip;
  }

  function layoutRectangular(root, width, height) {
    const leaves=allLeaves(root), top=30, bottom=35, left=35, right=190;
    const yStep=leaves.length>1?(height-top-bottom)/(leaves.length-1):0;
    leaves.forEach((leaf,i)=>leaf._ly=top+i*yStep);
    let maxDist=0,maxDepth=0;
    const setDist=(node,dist=0,depth=0)=>{node._dist=dist;node._depth=depth;maxDist=Math.max(maxDist,dist);maxDepth=Math.max(maxDepth,depth);node.children?.forEach(c=>setDist(c,dist+(Number(c.length)||0),depth+1));};
    setDist(root);
    const usable=Math.max(80,width-left-right);
    const xFor=node=>left+usable*((maxDist>0?node._dist/maxDist:(maxDepth?node._depth/maxDepth:0)));
    const position=node=>{node.children?.forEach(position);node._x=xFor(node);node._y=node.children?.length?node.children.reduce((s,c)=>s+c._y,0)/node.children.length:node._ly;};
    position(root);
    return {leaves,maxDist,left,right,top,bottom};
  }

  function circularMean(angles) {
    if (!angles.length) return 0;
    const x=angles.reduce((s,a)=>s+Math.cos(a),0), y=angles.reduce((s,a)=>s+Math.sin(a),0);
    return Math.atan2(y,x);
  }

  function layoutRadial(root, width, height) {
    const leaves=allLeaves(root), cx=width/2, cy=height/2, margin=120, radius=Math.max(50,Math.min(width,height)/2-margin);
    let maxDist=0,maxDepth=0;
    const setDist=(node,dist=0,depth=0)=>{node._dist=dist;node._depth=depth;maxDist=Math.max(maxDist,dist);maxDepth=Math.max(maxDepth,depth);node.children?.forEach(c=>setDist(c,dist+(Number(c.length)||0),depth+1));};
    setDist(root);
    leaves.forEach((leaf,i)=>leaf._angle=-Math.PI/2+(2*Math.PI*i/Math.max(1,leaves.length)));
    const position=node=>{
      node.children?.forEach(position);
      if (node.children?.length) node._angle=circularMean(node.children.map(c=>c._angle));
      const frac=maxDist>0?node._dist/maxDist:(maxDepth?node._depth/maxDepth:0);
      node._r=radius*frac;node._x=cx+node._r*Math.cos(node._angle);node._y=cy+node._r*Math.sin(node._angle);
    };
    position(root);
    return {leaves,maxDist,cx,cy,radius};
  }

  function treeToNewick(root) {
    const quote = name => {
      const text=clean(name);
      if (!text) return "";
      if (/^[A-Za-z0-9_.|:-]+$/.test(text)) return text;
      return `'${text.replace(/'/g,"''")}'`;
    };
    const walk = (node,isRoot=false) => {
      const body=node.children?.length?`(${node.children.map(c=>walk(c,false)).join(",")})${quote(node.label||node.name)}`:quote(node.name||node.sample_id||node.reference_id);
      return isRoot?body:`${body}:${Math.max(0,Number(node.length)||0).toPrecision(8)}`;
    };
    return walk(root,true)+";";
  }

  function zoomViewBoxToPoint(fullWidth, fullHeight, x, y, currentViewBox=null, minimumZoom=3.2) {
    const fw=Math.max(1,Number(fullWidth)||1), fh=Math.max(1,Number(fullHeight)||1);
    const px=Math.max(0,Math.min(fw,Number(x)||0)), py=Math.max(0,Math.min(fh,Number(y)||0));
    const current=currentViewBox&&Number(currentViewBox.w)>0&&Number(currentViewBox.h)>0?currentViewBox:{x:0,y:0,w:fw,h:fh};
    const currentZoom=Math.max(fw/current.w,fh/current.h);
    const zoom=Math.max(Number(minimumZoom)||3.2,currentZoom);
    const w=fw/zoom,h=fh/zoom;
    const maxX=Math.max(0,fw-w),maxY=Math.max(0,fh-h);
    return {x:Math.max(0,Math.min(maxX,px-w/2)),y:Math.max(0,Math.min(maxY,py-h/2)),w,h};
  }

  function pointInPolygon(point, polygon) {
    const x=Number(point?.x), y=Number(point?.y);
    if (!Number.isFinite(x)||!Number.isFinite(y)||!Array.isArray(polygon)||polygon.length<3) return false;
    let inside=false;
    for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
      const xi=Number(polygon[i]?.x), yi=Number(polygon[i]?.y), xj=Number(polygon[j]?.x), yj=Number(polygon[j]?.y);
      if(![xi,yi,xj,yj].every(Number.isFinite)) continue;
      const intersect=((yi>y)!==(yj>y)) && (x < (xj-xi)*(y-yi)/((yj-yi)||Number.EPSILON)+xi);
      if(intersect) inside=!inside;
    }
    return inside;
  }

  function lassoPath(points) {
    if(!Array.isArray(points)||points.length===0) return "";
    return points.map((p,i)=>`${i?"L":"M"} ${Number(p.x)||0} ${Number(p.y)||0}`).join(" " ) + (points.length>=3?" Z":"");
  }

  function zoomViewBoxToPoints(fullWidth, fullHeight, points, padding=0.22) {
    const fw=Math.max(1,Number(fullWidth)||1), fh=Math.max(1,Number(fullHeight)||1);
    const cleanPoints=(Array.isArray(points)?points:[]).map(p=>({x:Number(p?.x),y:Number(p?.y)})).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
    if(!cleanPoints.length) return {x:0,y:0,w:fw,h:fh};
    if(cleanPoints.length===1) return zoomViewBoxToPoint(fw,fh,cleanPoints[0].x,cleanPoints[0].y,null);
    let minX=Math.min(...cleanPoints.map(p=>p.x)),maxX=Math.max(...cleanPoints.map(p=>p.x)),minY=Math.min(...cleanPoints.map(p=>p.y)),maxY=Math.max(...cleanPoints.map(p=>p.y));
    const minSpanX=Math.max(20,fw*0.025),minSpanY=Math.max(20,fh*0.025);
    let spanX=Math.max(minSpanX,maxX-minX),spanY=Math.max(minSpanY,maxY-minY);
    spanX*=1+Math.max(0,Number(padding)||0)*2; spanY*=1+Math.max(0,Number(padding)||0)*2;
    const aspect=fw/fh;
    if(spanX/spanY>aspect) spanY=spanX/aspect; else spanX=spanY*aspect;
    const cx=(minX+maxX)/2,cy=(minY+maxY)/2;
    const w=Math.min(fw,spanX),h=Math.min(fh,spanY);
    return {x:Math.max(0,Math.min(fw-w,cx-w/2)),y:Math.max(0,Math.min(fh-h,cy-h/2)),w,h};
  }

  function studioBootstrap(payload) {
    "use strict";
    const API = payload.api;
    const data = payload.data;
    const sampleById = new Map(data.samples.map(s=>[s.sample_id,s]));
    const references = data.references || [];
    const referenceById = new Map(references.map(r=>[r.reference_id,r]));
    const state = {
      segment: data.segment_order.includes(payload.initialSegment)?payload.initialSegment:(data.segment_order.includes("HA")?"HA":data.segment_order[0]),
      layout:"rectangular", root:"source", outgroup:"", sort:"original", colorBy:"genotype", filterTrait:"none", filterValues:[], branchColor:"uniform", tipLabel:((data.trees[(data.segment_order.includes(payload.initialSegment)?payload.initialSegment:(data.segment_order.includes("HA")?"HA":data.segment_order[0]))]?.tip_count||0)>120?"focus":"id"), supports:((data.trees[(data.segment_order.includes(payload.initialSegment)?payload.initialSegment:(data.segment_order.includes("HA")?"HA":data.segment_order[0]))]?.tip_count||0)<=120), search:"", selectedSampleId:payload.selectedSampleId||null, selectedReferenceId:payload.selectedReferenceId||null,
      viewBox:null, drag:null, lasso:null, lassoMode:false,
      selectedKeys:new Set([payload.selectedSampleId?`s:${payload.selectedSampleId}`:payload.selectedReferenceId?`r:${payload.selectedReferenceId}`:null].filter(Boolean)),
    };
    const root=document.getElementById("studio");
    root.innerHTML=`<div class="ts-shell"><header class="ts-head"><div><div class="ts-overline">WINGS · phylogenetic exploration</div><div class="ts-title">Tree Studio</div><div class="ts-sub">Interactive display of existing WINGS segment trees. Rerooting and sorting are display transformations; source trees are not modified.</div></div><div class="ts-badge">v${API.VERSION} · offline-capable</div></header><div class="ts-controls"></div><main class="ts-main"><section class="ts-canvas-card"><div class="ts-canvas-head"><strong class="ts-tree-title"></strong><span class="ts-status"></span></div><div class="ts-canvas-wrap"></div></section><aside class="ts-side"></aside></main></div>`;
    const controls=root.querySelector(".ts-controls"), wrap=root.querySelector(".ts-canvas-wrap"), side=root.querySelector(".ts-side"), status=root.querySelector(".ts-status"), title=root.querySelector(".ts-tree-title");
    const options=(arr,val)=>arr.map(([v,l])=>`<option value="${API.escAttr(v)}"${v===val?" selected":""}>${API.escHtml(l)}</option>`).join("");
    controls.innerHTML=`
      <label class="ts-control"><span>Segment</span><select data-c="segment">${options(data.segment_order.map(x=>[x,x]),state.segment)}</select></label>
      <label class="ts-control"><span>Layout</span><select data-c="layout">${options([["rectangular","Rectangular"],["radial","Radial"],["unrooted","Unrooted display"]],state.layout)}</select></label>
      <label class="ts-control"><span>Rooting</span><select data-c="root">${options([["source","As supplied"],["midpoint","Midpoint display root"],["outgroup","Outgroup display root"]],state.root)}</select></label>
      <label class="ts-control"><span>Outgroup</span><select data-c="outgroup"></select></label>
      <label class="ts-control"><span>Sort</span><select data-c="sort">${options([["original","Source order"],["ladder-asc","Ladderize ↑"],["ladder-desc","Ladderize ↓"],["date","Collection date"]],state.sort)}</select></label>
      <label class="ts-control"><span>Tip color</span><select data-c="colorBy">${options([["genotype","Genotype"],["host","Host"],["country","Country"],["state","State"],["collection_date","Collection date"],["source","WINGS / public"]],state.colorBy)}</select></label>
      <label class="ts-control"><span>Filter trait</span><select data-c="filterTrait">${options([["none","None"],["genotype","Genotype"],["host","Host"],["country","Country"],["state","State"],["source","WINGS / public"]],state.filterTrait)}</select></label>
      <label class="ts-control"><span>Branches</span><select data-c="branchColor">${options([["uniform","Uniform"],["consensus","Descendant consensus"]],state.branchColor)}</select></label>
      <label class="ts-control"><span>Tip labels</span><select data-c="tipLabel">${options([["focus","Selected / search only"],["id","Sample / reference ID"],["tip","Tree tip"],["accession","Accession"],["isolate","Isolate"],["host","Host"],["genotype","Genotype"]],state.tipLabel)}</select></label>
      <label class="ts-control"><span>Support</span><select data-c="supports">${options([["yes","Show"],["no","Hide"]],state.supports?"yes":"no")}</select></label>
      <label class="ts-control ts-search"><span>Search tips</span><input type="text" data-c="search" placeholder="sample, accession, host, genotype…"></label>
      <span class="ts-spacer"></span><button class="ts-btn" data-a="lasso" aria-pressed="false" title="Drag a freehand loop around terminal taxa">Lasso select</button><button class="ts-btn" data-a="deselect" disabled>Deselect all</button><button class="ts-btn" data-a="zoom-selected" disabled>Zoom to selected</button><button class="ts-btn" data-a="fit">Fit</button><button class="ts-btn" data-a="svg">SVG</button><button class="ts-btn" data-a="png">PNG</button><button class="ts-btn" data-a="newick">Newick</button><button class="ts-btn" data-a="metadata">Metadata TSV</button>`;

    const c=name=>controls.querySelector(`[data-c="${name}"]`);
    function getTree(){ return data.trees[state.segment]?.root || null; }
    function updateOutgroups(tree){
      const select=c("outgroup"); const old=state.outgroup; select.innerHTML="";
      if (!tree) return;
      const localData={sampleById,referenceById,segment:state.segment};
      const base=API.annotateTree(API.cloneSourceTree(tree));
      const leaves=API.allLeaves(base);
      for(const leaf of leaves){const info=API.leafInfo(leaf,localData);const opt=new Option(info.label||info.id,info.key);select.append(opt);}
      if ([...select.options].some(o=>o.value===old)) select.value=old; else {select.value=select.options[0]?.value||"";state.outgroup=select.value;}
    }
    function displayedTree(){
      const source=getTree(); if(!source) return null;
      let tree;
      if(state.layout==="unrooted" || state.root==="source") tree=API.annotateTree(API.cloneSourceTree(source));
      else if(state.root==="midpoint") tree=API.midpointRoot(source);
      else tree=API.outgroupRoot(source,state.outgroup);
      return API.sortTree(tree,state.sort,{sampleById,referenceById,segment:state.segment});
    }
    function infoMatches(info){const q=state.search.trim().toLowerCase();if(!q)return true;return [info.id,info.tip,info.host,info.genotype,info.country,info.state,info.date,info.isolate,info.accession,info.source].some(v=>String(v||"").toLowerCase().includes(q));}
    function selectedKey(){return state.selectedSampleId?`s:${state.selectedSampleId}`:state.selectedReferenceId?`r:${state.selectedReferenceId}`:"";}
    function selectedKeys(){return state.selectedKeys instanceof Set?state.selectedKeys:new Set();}
    function postSingleSelection(){window.opener?.postMessage({type:"WINGS_TREE_STUDIO_SELECT",session:payload.session,sampleId:state.selectedSampleId,referenceId:state.selectedReferenceId},"*");}
    function clearSelection(sync=true){state.selectedKeys=new Set();state.selectedSampleId=null;state.selectedReferenceId=null;if(sync)window.opener?.postMessage({type:"WINGS_TREE_STUDIO_SELECT",session:payload.session,sampleId:null,referenceId:null,clear:true},"*");}
    function makeSingleSelection(key,sync=true){state.selectedKeys=new Set(key?[key]:[]);state.selectedSampleId=key?.startsWith("s:")?key.slice(2):null;state.selectedReferenceId=key?.startsWith("r:")?key.slice(2):null;if(sync)postSingleSelection();}
    function renderSide(tree,colorCtx){
      const localData={sampleById,referenceById,segment:state.segment};
      const leaves=API.allLeaves(tree);
      const selectedSet=selectedKeys();
      const selectedLeaves=leaves.filter(l=>selectedSet.has(API.leafKey(l)));
      const selected=selectedLeaves.length===1?selectedLeaves[0]:leaves.find(l=>API.leafKey(l)===selectedKey());
      const info=selected?API.leafInfo(selected,localData):null;
      const rootText=state.layout==="unrooted"?"Unrooted equal-angle display; root is not interpreted.":state.root==="source"?"Source tree orientation as supplied; no biological root is inferred.":state.root==="midpoint"?"Display rerooted at the branch-length midpoint.":"Display rerooted on the selected outgroup branch.";
      let html=`<h3>${info?API.escHtml(info.label||info.id):"Tree evidence"}</h3><div class="ts-note${state.root!=="source"||state.layout==="unrooted"?" ts-warning":""}">${API.escHtml(rootText)} Source tree bytes and WINGS analysis outputs are unchanged.</div>`;
      if(selectedLeaves.length>1){
        const infos=selectedLeaves.map(l=>API.leafInfo(l,localData));
        const countBy=field=>{const m=new Map();for(const x of infos){const v=clean(x[field])||"Not recorded";m.set(v,(m.get(v)||0)+1);}return [...m.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));};
        const top=(field,n=4)=>countBy(field).slice(0,n).map(([v,c])=>`${v} · ${c}`).join(", ");
        html+=`<h4>Selected taxa · ${selectedLeaves.length}</h4><div class="ts-meta"><div class="ts-meta-row"><span>Sources</span><span>${API.escHtml(top("source"))}</span></div><div class="ts-meta-row"><span>Hosts</span><span>${API.escHtml(top("host"))}</span></div><div class="ts-meta-row"><span>Genotypes</span><span>${API.escHtml(top("genotype"))}</span></div></div><div class="ts-selection-list">${infos.slice(0,60).map(x=>`<span class="ts-pill">${API.escHtml(x.id||x.tip)}</span>`).join("")}${infos.length>60?`<span class="ts-pill">+ ${infos.length-60} more</span>`:""}</div><div class="ts-help">Multiple selection is local to Tree Studio. Use Deselect all to clear it; Shift-click adds/removes individual tips.</div>`;
      } else if(info){
        const rows=[["Source",info.source],["ID",info.id],["Host",info.host],["Genotype",info.genotype],["Collection",info.date],["Country",info.country],["State",info.state],["State source",info.state_raw && info.state_raw !== info.state ? info.state_raw : ""],["Isolate",info.isolate],["Accession",info.accession]].filter(x=>x[1]);
        html+=`<h4>Selected tip</h4><div class="ts-meta">${rows.map(([k,v])=>`<div class="ts-meta-row"><span>${API.escHtml(k)}</span><span>${API.escHtml(v)}</span></div>`).join("")}</div>`;
      } else html+=`<div class="ts-empty">Click a tip to inspect it, Shift-click to build a multi-selection, or turn on Lasso select and draw a loop around terminal taxa.</div>`;

      if(state.filterTrait!=="none"){
        const counts=new Map();
        for(const leaf of leaves){
          const value=API.filterTraitValue(API.leafInfo(leaf,localData),state.filterTrait);
          counts.set(value,(counts.get(value)||0)+1);
        }
        const items=[...counts.entries()].sort((a,b)=>{
          if(a[0]===FILTER_MISSING)return 1;if(b[0]===FILTER_MISSING)return -1;
          return String(a[0]).localeCompare(String(b[0]));
        });
        const active=new Set(state.filterValues);
        const matching=leaves.filter(l=>API.matchesTraitFilter(API.leafInfo(l,localData),state.filterTrait,state.filterValues)).length;
        const traitLabel={genotype:"Genotype",host:"Host",country:"Country",state:"State",source:"WINGS / public"}[state.filterTrait]||state.filterTrait;
        html+=`<h4>Trait filter · ${API.escHtml(traitLabel)}</h4><div class="ts-filter-summary">${active.size?`${matching} of ${leaves.length} tips match. Nonmatching tips and branches without matching descendants are shaded, not removed.`:"Choose one or more values. Multiple values use OR logic; the full topology stays visible."}</div><div class="ts-filter-values">`;
        html+=items.map(([value,count])=>{const label=value===FILTER_MISSING?"Not recorded / not assigned":value;return `<button type="button" class="ts-filter-chip" data-filter-value="${API.escAttr(value)}" aria-pressed="${active.has(value)?"true":"false"}">${API.escHtml(label)} · ${count}</button>`;}).join("");
        html+=`</div>${active.size?'<button type="button" class="ts-btn ts-filter-clear" data-filter-clear="1">Clear trait filter</button>':""}`;
      }

      html+=`<h4>Color legend</h4><div class="ts-legend">`;
      if(colorCtx.continuous){
        html+=`<div class="ts-legend-row"><span class="ts-swatch" style="background:${colorCtx.color(new Date(colorCtx.min).toISOString().slice(0,10))}"></span><span>${Number.isFinite(colorCtx.min)?new Date(colorCtx.min).toISOString().slice(0,10):"No dated tips"}</span></div><div class="ts-legend-row"><span class="ts-swatch" style="background:${colorCtx.color(new Date(colorCtx.max).toISOString().slice(0,10))}"></span><span>${Number.isFinite(colorCtx.max)?new Date(colorCtx.max).toISOString().slice(0,10):""}</span></div>`;
      } else {
        html+=colorCtx.values.slice(0,18).map(v=>`<div class="ts-legend-row"><span class="ts-swatch" style="background:${colorCtx.color(v)}"></span><span>${API.escHtml(v)}</span></div>`).join("");
        if(colorCtx.values.length>18) html+=`<div class="ts-empty">+ ${colorCtx.values.length-18} additional categories</div>`;
      }
      if(colorCtx.missingCount) html+=`<div class="ts-legend-row"><span class="ts-swatch" style="background:#aeb7bb"></span><span>Not recorded / not assigned (${colorCtx.missingCount})</span></div>`;
      html+=`</div><h4>Display semantics</h4><div class="ts-footer-note">Trait filtering is a display operation: nonmatching observations are shaded rather than deleted, and a branch remains emphasized when at least one descendant tip matches the active filter. Multiple selected trait values use OR logic. Branch coloring by “descendant consensus” is a visual summary: a branch is colored only when all descendant annotated tips share the selected categorical trait. It is not ancestral-state reconstruction. Numeric internal labels are displayed as recorded; rerooting does not recompute support. Collection dates are metadata and are not used to time-calibrate the tree.</div>`;
      side.innerHTML=html;
      side.querySelectorAll("[data-filter-value]").forEach(button=>button.addEventListener("click",()=>{
        const value=button.dataset.filterValue;
        const set=new Set(state.filterValues);
        if(set.has(value))set.delete(value);else set.add(value);
        state.filterValues=[...set];
        render();
      }));
      side.querySelector("[data-filter-clear]")?.addEventListener("click",()=>{state.filterValues=[];render();});
    }
    function render(){
      const source=getTree();
      updateOutgroups(source);
      c("root").disabled=state.layout==="unrooted"; c("outgroup").disabled=state.layout==="unrooted"||state.root!=="outgroup";
      if(!source){wrap.innerHTML='<div class="ts-no-tree">No tree available for this segment.</div>';side.innerHTML="";title.textContent=`${state.segment} · unavailable`;status.textContent="";return;}
      const tree=displayedTree(), localData={sampleById,referenceById,segment:state.segment};
      const leaves=API.allLeaves(tree), colorCtx=API.colorContext(tree,localData,state.colorBy);
      const width=1500, height=Math.max(650,state.layout==="rectangular"?Math.min(1800,80+leaves.length*17):900);
      const layout=state.layout==="rectangular"?API.layoutRectangular(tree,width,height):API.layoutRadial(tree,width,height);
      const searchActive=Boolean(state.search.trim());
      const filterActive=state.filterTrait!=="none"&&state.filterValues.length>0;
      const passesFilter=info=>API.matchesTraitFilter(info,state.filterTrait,state.filterValues);
      const selectedSet=selectedKeys();
      const selected=selectedKey();
      const zoomFactor=state.viewBox?width/state.viewBox.w:1;
      const declutterLabels=leaves.length>120&&state.tipLabel!=="focus"&&zoomFactor<2.8;
      const parts=[];
      const branchColor=node=>{
        if(state.branchColor!=="consensus"||state.colorBy==="collection_date")return NEUTRAL;
        const v=API.descendantConsensus(node,localData,state.colorBy); return v?colorCtx.color(v):NEUTRAL;
      };
      const walkBranches=node=>{
        for(const child of node.children||[]){
          const descendantInfos=API.allLeaves(child).map(l=>API.leafInfo(l,localData));
          const branchHasMatch=descendantInfos.some(info=>(!searchActive||infoMatches(info))&&(!filterActive||passesFilter(info)));
          const dim=(searchActive||filterActive)&&!branchHasMatch;
          const stroke=branchColor(child);
          if(state.layout==="rectangular"){
            parts.push(`<path class="ts-branch${dim?" ts-dim":""}" stroke="${stroke}" d="M ${node._x} ${node._y} L ${node._x} ${child._y} L ${child._x} ${child._y}"/>`);
          } else parts.push(`<line class="ts-branch${dim?" ts-dim":""}" stroke="${stroke}" x1="${node._x}" y1="${node._y}" x2="${child._x}" y2="${child._y}"/>`);
          if(state.supports&&API.numericSupport(child.label)) parts.push(`<text class="ts-support" x="${(node._x+child._x)/2+3}" y="${(node._y+child._y)/2-3}">${API.escHtml(child.label)}</text>`);
          walkBranches(child);
        }
      };
      walkBranches(tree);
      if(state.layout!=="unrooted") parts.push(`<circle class="ts-root" cx="${tree._x}" cy="${tree._y}" r="4"><title>Displayed root</title></circle>`);
      for(const leaf of leaves){
        const info=API.leafInfo(leaf,localData), value=API.traitValue(info,state.colorBy), color=colorCtx.color(value), hit=infoMatches(info), filterMatch=passesFilter(info), isSel=selectedSet.has(info.key), isPrimary=info.key===selected;
        const dim=(searchActive&&!hit)||(filterActive&&!filterMatch);
        const klass=`ts-tip${isPrimary?" ts-selected":""}${isSel&&!isPrimary?" ts-multi-selected":""}${searchActive&&hit?" ts-search-hit":""}${filterActive&&filterMatch?" ts-filter-hit":""}${dim?" ts-dim":""}`;
        let tx=leaf._x+9,ty=leaf._y+4,anchor="start";
        if(state.layout!=="rectangular"){
          const left=Math.cos(leaf._angle)<0; tx=leaf._x+(left?-8:8);ty=leaf._y+3;anchor=left?"end":"start";
        }
        const requestedLabel=state.tipLabel==="focus"?info.id:API.leafLabel(info,state.tipLabel);
        const showLabel=state.tipLabel==="focus"?(isSel||(searchActive&&hit)):(declutterLabels?(isSel||(searchActive&&hit)):true);
        const shownLabel=showLabel?requestedLabel:"";parts.push(`<g class="${klass}" tabindex="0" role="button" data-key="${API.escAttr(info.key)}"><circle cx="${leaf._x}" cy="${leaf._y}" r="4.2" fill="${color}"/><text x="${tx}" y="${ty}" text-anchor="${anchor}">${API.escHtml(shownLabel)}</text><title>${API.escHtml([info.id,info.host,info.genotype,info.date,info.accession].filter(Boolean).join(" · "))}</title></g>`);
      }
      if(state.layout==="rectangular"&&layout.maxDist>0){const x0=40,x1=160,y=height-13;const val=layout.maxDist*((x1-x0)/(width-225));parts.push(`<line class="ts-scale" x1="${x0}" y1="${y}" x2="${x1}" y2="${y}"/><text class="ts-scale-label" x="${(x0+x1)/2}" y="${y-5}" text-anchor="middle">${val.toPrecision(2)} substitutions/site</text>`);}
      const view=state.viewBox||{x:0,y:0,w:width,h:height};
      wrap.classList.toggle("ts-lasso-active",state.lassoMode);
      wrap.innerHTML=`<svg id="tree-svg" data-full-width="${width}" data-full-height="${height}" viewBox="${view.x} ${view.y} ${view.w} ${view.h}" aria-label="Interactive ${API.escAttr(state.segment)} phylogenetic tree" xmlns="http://www.w3.org/2000/svg">${parts.join("")}<path class="ts-lasso-path" d="" hidden/></svg>`;
      const svg=wrap.querySelector("svg");
      const zoomSelectedButton=controls.querySelector('[data-a="zoom-selected"]'), deselectButton=controls.querySelector('[data-a="deselect"]'), lassoButton=controls.querySelector('[data-a="lasso"]');
      const visibleSelected=svg.querySelectorAll(".ts-tip.ts-selected,.ts-tip.ts-multi-selected").length;
      if(zoomSelectedButton) zoomSelectedButton.disabled=visibleSelected===0;
      if(deselectButton) deselectButton.disabled=selectedKeys().size===0;
      if(lassoButton) lassoButton.setAttribute("aria-pressed",String(state.lassoMode));
      svg.querySelectorAll(".ts-tip").forEach(g=>{const choose=(event=null)=>{const key=g.dataset.key;if(event?.shiftKey){const set=new Set(selectedKeys());if(set.has(key))set.delete(key);else set.add(key);state.selectedKeys=set;state.selectedSampleId=null;state.selectedReferenceId=null;render();return;}makeSingleSelection(key,true);render();};g.addEventListener("click",choose);g.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();choose(e);}});});
      svg.addEventListener("wheel",e=>{e.preventDefault();const vb=svg.viewBox.baseVal, rect=svg.getBoundingClientRect(), mx=vb.x+(e.clientX-rect.left)/rect.width*vb.width,my=vb.y+(e.clientY-rect.top)/rect.height*vb.height,f=API.wheelZoomFactor(e.deltaY,e.deltaMode),nw=vb.width*f,nh=vb.height*f;state.viewBox={x:mx-(mx-vb.x)*f,y:my-(my-vb.y)*f,w:nw,h:nh};render();},{passive:false});
      const svgPoint=e=>{const vb=svg.viewBox.baseVal,rect=svg.getBoundingClientRect();return {x:vb.x+(e.clientX-rect.left)/rect.width*vb.width,y:vb.y+(e.clientY-rect.top)/rect.height*vb.height};};
      svg.addEventListener("pointerdown",e=>{
        if(state.lassoMode){
          e.preventDefault();svg.setPointerCapture(e.pointerId);const p=svgPoint(e);state.lasso={pointerId:e.pointerId,points:[p],additive:Boolean(e.shiftKey)};const path=svg.querySelector(".ts-lasso-path");if(path){path.hidden=false;path.setAttribute("d",API.lassoPath(state.lasso.points));}return;
        }
        // Tip clicks are selection actions, not pan gestures. Capturing the
        // pointer on the SVG here would retarget pointerup/click away from the
        // tip group in some browsers, making visible tip nodes appear inert.
        if(e.target.closest?.(".ts-tip")) return;
        svg.setPointerCapture(e.pointerId);
        const vb=svg.viewBox.baseVal;
        state.drag={x:e.clientX,y:e.clientY,vx:vb.x,vy:vb.y,vw:vb.width,vh:vb.height};
      });
      svg.addEventListener("pointermove",e=>{
        if(state.lasso&&e.pointerId===state.lasso.pointerId){const p=svgPoint(e),prev=state.lasso.points[state.lasso.points.length-1];if(!prev||Math.hypot(p.x-prev.x,p.y-prev.y)>2){state.lasso.points.push(p);const path=svg.querySelector(".ts-lasso-path");if(path)path.setAttribute("d",API.lassoPath(state.lasso.points));}return;}
        if(!state.drag)return;const rect=svg.getBoundingClientRect(),dx=(e.clientX-state.drag.x)/rect.width*state.drag.vw,dy=(e.clientY-state.drag.y)/rect.height*state.drag.vh;state.viewBox={x:state.drag.vx-dx,y:state.drag.vy-dy,w:state.drag.vw,h:state.drag.vh};svg.setAttribute("viewBox",`${state.viewBox.x} ${state.viewBox.y} ${state.viewBox.w} ${state.viewBox.h}`);
      });
      const finishPointer=(e,cancelled=false)=>{
        if(state.lasso&&(!e||e.pointerId===state.lasso.pointerId)){const polygon=state.lasso.points,additive=state.lasso.additive;state.lasso=null;if(cancelled||polygon.length<3){render();return;}const keys=[];svg.querySelectorAll(".ts-tip").forEach(g=>{const circle=g.querySelector("circle"),p={x:Number(circle?.getAttribute("cx")),y:Number(circle?.getAttribute("cy"))};if(API.pointInPolygon(p,polygon))keys.push(g.dataset.key);});const set=additive?new Set(selectedKeys()):new Set();keys.forEach(k=>set.add(k));state.selectedKeys=set;state.selectedSampleId=null;state.selectedReferenceId=null;render();return;}state.drag=null;
      };
      svg.addEventListener("pointerup",e=>finishPointer(e,false));svg.addEventListener("pointercancel",e=>finishPointer(e,true));
      title.textContent=`${state.segment} · ${leaves.length} tips`;
      const filterCount=filterActive?leaves.filter(l=>passesFilter(API.leafInfo(l,localData))).length:null;
      status.textContent=`${state.layout}${state.layout!=="unrooted"?` · ${state.root==="source"?"as supplied":state.root+" display root"}`:" · root not interpreted"} · ${state.sort}${filterActive?` · filter ${filterCount}/${leaves.length}`:""}${selectedKeys().size?` · selected ${selectedKeys().size}`:""}${state.lassoMode?" · lasso mode":""}${declutterLabels?" · labels decluttered—zoom in to reveal":""}`;
      renderSide(tree,colorCtx);
    }
    controls.addEventListener("change",e=>{const el=e.target,name=el.dataset.c;if(!name)return;state[name]=name==="supports"?el.value==="yes":el.value;if(name==="filterTrait")state.filterValues=[];if(name==="segment"){state.viewBox=null;state.outgroup="";}if(name==="layout"||name==="root"||name==="sort")state.viewBox=null;render();});
    c("search").addEventListener("input",e=>{state.search=e.target.value;render();});
    controls.addEventListener("click",e=>{const a=e.target.dataset.a;if(!a)return;const tree=displayedTree();if(a==="lasso"){state.lassoMode=!state.lassoMode;state.drag=null;state.lasso=null;render();return;}if(a==="deselect"){clearSelection(true);render();return;}if(a==="fit"){state.viewBox=null;render();return;}if(a==="zoom-selected"){const svg=wrap.querySelector("svg"),tips=[...svg?.querySelectorAll(".ts-tip.ts-selected circle,.ts-tip.ts-multi-selected circle")||[]];if(!svg||!tips.length)return;const fw=Number(svg.dataset.fullWidth)||1500,fh=Number(svg.dataset.fullHeight)||900,points=tips.map(t=>({x:Number(t.getAttribute("cx")),y:Number(t.getAttribute("cy"))}));state.viewBox=points.length===1?API.zoomViewBoxToPoint(fw,fh,points[0].x,points[0].y,state.viewBox):API.zoomViewBoxToPoints(fw,fh,points);render();return;}if(!tree)return;const svg=wrap.querySelector("svg");if(a==="svg")API.downloadText(`${state.segment}_TreeStudio.svg`,new XMLSerializer().serializeToString(svg),"image/svg+xml");if(a==="newick")API.downloadText(`${state.segment}_TreeStudio.newick`,API.treeToNewick(tree),"text/plain");if(a==="metadata"){const localData={sampleById,referenceById,segment:state.segment};const rows=API.allLeaves(tree).map(l=>API.leafInfo(l,localData));const fields=["source","id","tip","host","genotype","collection_date","country","state","state_source","isolate","accession"];const tsv=[fields.join("\t"),...rows.map(r=>fields.map(f=>String(f==="collection_date"?r.date:f==="state_source"?r.state_raw:r[f]||"").replace(/[\t\r\n]/g," ")).join("\t"))].join("\n")+"\n";API.downloadText(`${state.segment}_TreeStudio_metadata.tsv`,tsv,"text/tab-separated-values");}if(a==="png"&&svg){const text=new XMLSerializer().serializeToString(svg), blob=new Blob([text],{type:"image/svg+xml"}),url=URL.createObjectURL(blob),img=new Image();img.onload=()=>{const canvas=document.createElement("canvas");canvas.width=2400;canvas.height=Math.max(1000,Math.round(2400*svg.viewBox.baseVal.height/svg.viewBox.baseVal.width));const ctx=canvas.getContext("2d");ctx.fillStyle="#fff";ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);URL.revokeObjectURL(url);canvas.toBlob(b=>{const u=URL.createObjectURL(b),x=document.createElement("a");x.href=u;x.download=`${state.segment}_TreeStudio.png`;x.click();setTimeout(()=>URL.revokeObjectURL(u),1000);});};img.src=url;}});
    window.addEventListener("message",e=>{const m=e.data||{};if(m.type!=="WINGS_TREE_STUDIO_SYNC"||m.session!==payload.session)return;state.selectedSampleId=m.sampleId||null;state.selectedReferenceId=m.referenceId||null;state.selectedKeys=new Set([state.selectedSampleId?`s:${state.selectedSampleId}`:state.selectedReferenceId?`r:${state.selectedReferenceId}`:null].filter(Boolean));render();});
    updateOutgroups(getTree()); render();
  }

  function safeJson(value) { return JSON.stringify(value).replace(/</g,"\\u003c").replace(/>/g,"\\u003e").replace(/&/g,"\\u0026"); }
  function wheelZoomFactor(deltaY, deltaMode=0) {
    // Trackpads can emit many tiny wheel events while traditional mouse wheels
    // emit much larger deltas. Normalize to an approximate pixel delta, cap a
    // single event, and use an exponential scale so tiny gestures stay gentle.
    const unit = deltaMode === 1 ? 16 : deltaMode === 2 ? 240 : 1;
    const pixels = Math.max(-60, Math.min(60, Number(deltaY || 0) * unit));
    return Math.exp(pixels * 0.002);
  }

  function downloadText(name,text,type="text/plain") { const blob=new Blob([text],{type}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000); }

  function apiForPopup() {
    return {VERSION, escHtml:String(escHtml), escAttr:String(escAttr)};
  }

  function bootstrapSource() {
    const names = [cloneSourceTree,annotateTree,graphFromTree,cloneGraph,replaceEdge,rootedFromGraph,farthestLeaf,pathBetween,midpointRoot,outgroupRoot,leafKey,allLeaves,leafInfo,traitValue,filterTraitValue,matchesTraitFilter,descendantHasFilterMatch,sortTree,categoricalColors,dateColor,colorContext,descendantConsensus,leafLabel,layoutRectangular,circularMean,layoutRadial,treeToNewick,numericSupport,parseDate,clean,scalarText,genotypeText,normalizeUSState,escHtml,escAttr,downloadText,wheelZoomFactor,zoomViewBoxToPoint,pointInPolygon,lassoPath,zoomViewBoxToPoints];
    return names.map(fn=>`const ${fn.name}=${fn.toString()};`).join("\n") + `\nconst SEGMENTS=${JSON.stringify(SEGMENTS)},COLORS=${JSON.stringify(COLORS)},NEUTRAL=${JSON.stringify(NEUTRAL)},LIGHT=${JSON.stringify(LIGHT)},GOLD=${JSON.stringify(GOLD)},FILTER_MISSING=${JSON.stringify(FILTER_MISSING)},US_STATE_CODES=${JSON.stringify(US_STATE_CODES)},US_STATE_CODE_SET=new Set(Object.values(US_STATE_CODES));\nconst API={VERSION:${JSON.stringify(VERSION)},cloneSourceTree,annotateTree,graphFromTree,cloneGraph,replaceEdge,rootedFromGraph,farthestLeaf,pathBetween,midpointRoot,outgroupRoot,leafKey,allLeaves,leafInfo,traitValue,filterTraitValue,matchesTraitFilter,descendantHasFilterMatch,sortTree,categoricalColors,dateColor,colorContext,descendantConsensus,leafLabel,layoutRectangular,circularMean,layoutRadial,treeToNewick,numericSupport,parseDate,clean,normalizeUSState,escHtml,escAttr,downloadText,wheelZoomFactor,zoomViewBoxToPoint,pointInPolygon,lassoPath,zoomViewBoxToPoints};`;
  }

  function openStudio(explorer, opts={}) {
    if (!explorer?.payload) throw new Error("WINGS Explorer instance is required.");
    const key=`tree-studio-${++sessionCounter}`;
    const references=Array.isArray(explorer.referenceContext?.references)?explorer.referenceContext.references:[];
    const payload={
      session:key,
      initialSegment:opts.segment||explorer.segment||"HA",
      selectedSampleId:explorer.selectedSampleId||null,
      selectedReferenceId:explorer.selectedReferenceId||null,
      data:{trees:explorer.payload.trees||{},samples:explorer.samples||[],references,segment_order:(explorer.payload.segment_order||SEGMENTS).filter(s=>explorer.payload.trees?.[s])},
    };
    const popup=window.open("","_blank","popup=yes,width=1500,height=950,resizable=yes,scrollbars=yes");
    if(!popup) throw new Error("Tree Studio pop-out was blocked by the browser.");
    sessions.set(key,{explorer,popup});
    const html=`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WINGS Tree Studio</title><style>${POPUP_CSS}</style></head><body><div id="studio"></div><script>${bootstrapSource()}\nconst payload=${safeJson(payload)};payload.api=API;(${studioBootstrap.toString()})(payload);<\/script></body></html>`;
    popup.document.open(); popup.document.write(html); popup.document.close();
    popup.addEventListener?.("beforeunload",()=>sessions.delete(key));
    return popup;
  }

  function mountExplorer(explorer) {
    if (!explorer?.root) throw new Error("Explorer instance is required.");
    if (explorer.treeStudio) return explorer.treeStudio;
    const genomeView=explorer.explorerTabs?.panels?.genome || explorer.root.querySelector("#wse-view-genome") || explorer.root.querySelector(".wse-genome-panel");
    if (!genomeView) throw new Error("Genome view not found. Install Explorer tabs or retain the genome panel.");
    const toolbar=document.createElement("div");toolbar.className="wse-tree-studio-launch";
    const copy=document.createElement("div");copy.innerHTML='<strong>Tree Studio</strong><span>Pop out any segment for dynamic phylogenetic exploration.</span>';
    const button=document.createElement("button");button.type="button";button.className="wse-tree-studio-open";button.textContent="Open Tree Studio ↗";
    toolbar.append(copy,button);genomeView.prepend(toolbar);
    button.addEventListener("click",()=>{try{openStudio(explorer,{segment:explorer.segment||"HA"});}catch(err){alert(err.message||String(err));}});
    const previous=explorer.updateSelection.bind(explorer);
    explorer.updateSelection=function(...args){const result=previous(...args);for(const [session,entry] of sessions){if(entry.explorer!==explorer||entry.popup.closed)continue;entry.popup.postMessage({type:"WINGS_TREE_STUDIO_SYNC",session,sampleId:explorer.selectedSampleId||null,referenceId:explorer.selectedReferenceId||null},"*");}return result;};
    const api={VERSION,open:(opts={})=>openStudio(explorer,opts),button};
    explorer.treeStudio=api;return api;
  }

  window.addEventListener?.("message", event => {
    const m=event.data||{};
    if(m.type!=="WINGS_TREE_STUDIO_SELECT"||!sessions.has(m.session))return;
    const entry=sessions.get(m.session), e=entry.explorer;
    if(m.clear){e.selectedSampleId=null;e.selectedReferenceId=null;}
    else if(m.sampleId&&e.sampleById?.has(m.sampleId)){e.selectedSampleId=m.sampleId;e.selectedReferenceId=null;}
    else if(m.referenceId&&e.referenceById?.has(m.referenceId)){e.selectedReferenceId=m.referenceId;e.selectedSampleId=null;}
    else return;
    e.hoverSampleId=null;e.updateSelection();
  });

  globalThis.WINGS_TREE_STUDIO={VERSION,open:openStudio,mountExplorer,_test:{cloneSourceTree,annotateTree,graphFromTree,midpointRoot,outgroupRoot,leafKey,allLeaves,sortTree,treeToNewick,layoutRectangular,layoutRadial,leafInfo,colorContext,descendantConsensus,genotypeText,normalizeUSState,filterTraitValue,matchesTraitFilter,descendantHasFilterMatch,wheelZoomFactor,zoomViewBoxToPoint,pointInPolygon,lassoPath,zoomViewBoxToPoints}};
})();
