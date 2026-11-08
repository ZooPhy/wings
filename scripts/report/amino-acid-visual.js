/* WINGS protein landscape: no external libraries or network requests. */
(function(){
'use strict';
const COLORS={substitution:'#8c193e',insertion:'#167c80',deletion:'#4271ad',stop_gain:'#ad6200'};
const ASSESSED=new Set(['READY','PARTIAL_INTERPRETATION']);
function referenceLength(sample,p){
  const refs=sample.provenance?.panel?.references||[];
  return refs.find(r=>r.id===p.reference_id)?.sequence?.length || (p.reference_alignment||'').replace(/-/g,'').length;
}
function groups(data){
  const map=new Map();
  for(const s of data.samples||[])for(const p of s.proteins||[]){
    if(!p.reference_id)continue;
    const refs=s.provenance?.panel?.references||[];
    const referenceSequence=refs.find(r=>r.id===p.reference_id)?.sequence || (p.reference_alignment||'').replace(/-/g,'');
    const key=JSON.stringify([p.gene,p.reference_id,referenceSequence]);
    if(!map.has(key))map.set(key,{key,gene:p.gene,reference:p.reference_id,accession:p.reference_accession||'',length:0,records:[]});
    const g=map.get(key);g.length=Math.max(g.length,referenceLength(s,p));g.records.push({sample:s.sample,protein:p});
  }
  return [...map.values()].sort((a,b)=>a.gene.localeCompare(b.gene)||a.reference.localeCompare(b.reference));
}
function callablePosition(p,position){
  if(!ASSESSED.has(p.status))return false;
  if(p.alignment_resolution?.callable_reference_positions&&!p.alignment_resolution.callable_reference_positions.includes(position))return false;
  const a=p.reference_alignment||'',b=p.query_alignment||'';let pos=0;
  for(let i=0;i<a.length;i++){
    if(a[i]!=='-')pos++;
    if(a[i]!=='-'&&pos===position)return !!b[i]&&b[i]!=='X';
    if(b[i]==='*')return false;
  }
  return false;
}
function callableEvent(p,e,length){
  if(e.kind!=='insertion')return callablePosition(p,e.position);
  if(p.alignment_resolution?.callable_insertion_anchors)return ASSESSED.has(p.status)&&p.alignment_resolution.callable_insertion_anchors.includes(e.position);
  const left=Math.max(1,e.position),right=Math.min(length,e.position+1);
  return callablePosition(p,left)&&callablePosition(p,right);
}
function events(group,selected){
  const map=new Map();
  for(const r of group.records){
    if(!selected.has(r.sample)||!ASSESSED.has(r.protein.status))continue;
    for(const c of r.protein.changes||[]){
      const key=JSON.stringify([c.kind,c.position,c.reference_aa,c.query_aa]);
      if(!map.has(key))map.set(key,{...c,key,carriers:new Set(),evidence:[],eligible:new Set()});
      const e=map.get(key);e.carriers.add(r.sample);
      for(const x of c.evidence||[])if(!e.evidence.some(y=>JSON.stringify(x)===JSON.stringify(y)))e.evidence.push(x);
    }
  }
  for(const e of map.values()){
    for(const r of group.records)if(selected.has(r.sample)&&callableEvent(r.protein,e,group.length))e.eligible.add(r.sample);
    // A validated event is itself evidence that its carrier was assessed there.
    for(const carrier of e.carriers)e.eligible.add(carrier);
    e.n=e.carriers.size;e.denominator=e.eligible.size;e.frequency=e.n/e.denominator;
  }
  return [...map.values()].sort((a,b)=>a.position-b.position||a.change.localeCompare(b.change));
}
function matches(e,text){return [e.change,e.position,...e.carriers,...e.evidence.map(x=>x.statement+' '+x.study_context)].join(' ').toLowerCase().includes(text.toLowerCase());}
function segmentRecords(data){
  const out=[];
  for(const s of data.samples||[]){
    const keys=new Set();
    for(const seq of s.segment_sequences||[]){
      const proteins=(s.proteins||[]).filter(p=>p.seqid===seq.seqid);
      out.push({key:JSON.stringify([s.sample,seq.seqid]),sample:s.sample,seqid:seq.seqid,segment:seq.segment,sequence:seq.sequence||'',sha256:seq.sha256,proteins});keys.add(seq.seqid);
    }
    for(const p of s.proteins||[]){
      if(keys.has(p.seqid))continue;
      keys.add(p.seqid);
      out.push({key:JSON.stringify([s.sample,p.seqid||p.segment]),sample:s.sample,seqid:p.seqid,segment:p.segment||p.gene,sequence:'',proteins:(s.proteins||[]).filter(q=>q.seqid===p.seqid)});
    }
  }
  return out;
}
const REASONS={
  PARTIAL_CDS:'The coding sequence is incomplete.',PARTIAL_READING_FRAME:'The coding sequence starts in a partial reading frame.',
  INCOMPLETE_CODON_OR_FRAMESHIFT:'The coding sequence ends in an incomplete codon or has a possible frameshift.',
  START_CODON_REVIEW:'The translated sequence does not start with methionine.',TERMINAL_STOP_MISSING:'The terminal stop codon is missing.',
  AMBIGUOUS_RESIDUES:'Some amino acids are unknown (X); calls at those positions are unavailable.',
  PREMATURE_STOP:'An early stop codon is present; positions after it are not interpreted.',
  UNSUPPORTED_TRANSLATION_EXCEPTION:'A translation exception could not be interpreted.',UNSUPPORTED_GENETIC_CODE:'The genetic code is not supported.',
  OVERLAPPING_CDS_INTERVALS:'The CDS annotation contains overlapping intervals.',
  DISTANT_REFERENCE:'The alignment did not meet the configured identity or coverage threshold for a reliable comparison.',
  COHORT_UNAVAILABLE:'No callable comparisons are available for this protein in the selected samples. Select an individual sample to inspect its recorded reason.',
  AMBIGUOUS_ALIGNMENT:'No uniquely mapped positions were available, so mutation calls could not be made.',
  AMBIGUOUS_REFERENCE:'Multiple reference proteins scored equally; mutation calls were withheld.',
  NO_REFERENCE_FOR_PROTEIN:'No matching protein reference was available.',UNSUPPORTED_PRODUCT:'The protein annotation was not recognized.',
  SEQUENCE_ID_MISMATCH:'The CDS sequence ID did not match a saved consensus.',
  NO_VADR_PASS_ANNOTATIONS:'No passing VADR annotation was available.',NO_CDS_ANNOTATIONS:'No coding sequence annotation was available.',
  VADR_DISABLED:'VADR annotations were not supplied.',NEEDS_REFERENCE:'The reference panel was not prepared.',DISABLED:'Amino acid analysis was disabled.'
};
function positionRanges(positions){
  const sorted=[...new Set(positions||[])].sort((a,b)=>a-b),out=[];let start=null,last=null;
  for(const n of sorted){if(start===null){start=last=n;}else if(n===last+1){last=n;}else{out.push(start===last?String(start):start+'–'+last);start=last=n;}}
  if(start!==null)out.push(start===last?String(start):start+'–'+last);return out.join(', ');
}
function proteinReasons(p){
  const issues=(p.issues||[]).map(code=>REASONS[code]||'Recorded sequence issue: '+code.replaceAll('_',' ').toLowerCase()+'.');
  const resolution=p.alignment_resolution;
  if(resolution?.ambiguous){
    if(resolution.callable_reference_positions?.length){
      issues.unshift('Changes are shown only where all equally scoring alignments agree on the amino acid and its mapped position. Uncertain sites are excluded from calls and frequency calculations.');
    }
    if(resolution.uncertain_reference_positions?.length)issues.push('Uncertain reference amino acid positions: '+positionRanges(resolution.uncertain_reference_positions)+'.');
    if(resolution.uncertain_insertion_anchors?.length)issues.push('Uncertain insertion locations after reference amino acids: '+positionRanges(resolution.uncertain_insertion_anchors)+'.');
  }else if(p.status==='AMBIGUOUS_ALIGNMENT'){
    issues.unshift('This older result withheld the entire protein because multiple alignments tied. Recompare saved proteins to recover reliably mapped changes.');
  }
  if(p.status!=='READY'&&p.status!=='PARTIAL_INTERPRETATION'&&p.status!=='CDS_REVIEW_REQUIRED'&&!(p.status==='AMBIGUOUS_ALIGNMENT'&&!resolution))issues.unshift(REASONS[p.status]||'Comparison could not be completed ('+p.status+').');
  if(p.status==='DISTANT_REFERENCE'&&Number.isFinite(p.identity)&&Number.isFinite(p.coverage))issues.push('Recorded alignment: '+Math.round(100*p.identity)+'% identity; '+Math.round(100*p.coverage)+'% reference coverage.');
  if(!issues.length&&p.status!=='READY')issues.push('The saved result does not record the reason; inspect its annotation sources.');
  return [...new Set(issues)];
}
function proteinSpan(p){return (p.reference_alignment||'').replace(/-/g,'').length||p.query_sequence?.length||Math.max(1,...(p.changes||[]).map(c=>c.position||0));}
function aminoAt(p,position){
  const mapped=referenceToQuery(p,position);if(!mapped)return null;
  if(mapped.deleted)return {amino_acid:'−',query_position:mapped.query_position,deleted:true};
  const codon=p.codon_map?.codons?.find(c=>c.aa_index===mapped.query_position&&!c.after_stop);
  const sequence=(p.query_alignment||'').replace(/-/g,'');
  return {amino_acid:codon?.amino_acid||sequence[mapped.query_position-1]||'?',query_position:mapped.query_position,codon};
}
function codonSelection(p,change){
  const codons=p.codon_map?.codons||[];
  if(!codons.length)return null;
  if(change.kind==='deletion'){
    const indices=new Set([change.query_position,change.query_position+1]);
    const nearby=codons.filter(c=>indices.has(c.aa_index));
    return {mode:'flanks',codons:nearby,positions:nearby.flatMap(c=>c.positions),label:'Deleted amino acid: no codon exists in this consensus. Highlighted bases are flanking codons.'};
  }
  const c=codons.find(c=>c.aa_index===change.query_position);
  return c?{mode:'codon',codons:[c],positions:c.positions,label:'Translated CDS index '+c.aa_index+' · '+c.bases+' → '+c.amino_acid+(c.crosses_junction?' · codon spans a splice junction':'')}:null;
}
function referenceToQuery(p,position){
  if(p.alignment_resolution?.callable_reference_positions&&!p.alignment_resolution.callable_reference_positions.includes(position))return null;
  let r=0,q=0;const a=p.reference_alignment||'',b=p.query_alignment||'';
  for(let i=0;i<a.length;i++){
    if(a[i]!=='-')r++;if(b[i]!=='-')q++;
    if(a[i]!=='-'&&r===position)return {query_position:q,deleted:b[i]==='-'};
    if(b[i]==='*')return null;
  }
  return null;
}

function projectEvent(p,e){
  if(!ASSESSED.has(p.status)||!p.codon_map?.codons?.length)return null;
  const referenceSize=(p.reference_alignment||'').replace(/-/g,'').length;
  if(!callableEvent(p,e,referenceSize))return null;
  const same=(p.changes||[]).filter(c=>c.kind===e.kind&&c.position===e.position&&c.reference_aa===e.reference_aa&&c.query_aa===e.query_aa);
  const direction=p.cds_annotation?.strand==='-'?-1:1;
  if(same.length){
    const parts=same.map(c=>codonSelection(p,c)).filter(Boolean);
    const codons=parts.flatMap(s=>s.codons).filter(c=>!c.after_stop);
    if(!codons.length)return null;
    const boundary=e.kind==='deletion';
    const left=p.codon_map.codons.find(c=>c.aa_index===same[0].query_position&&!c.after_stop);
    const anchor=boundary?(left?left.positions[2]+.5*direction:codons[0].positions[0]-.5*direction):codons[0].positions[0];
    return {anchor,boundary,displayCarries:true,codons,positions:[...new Set(codons.flatMap(c=>c.positions))],mode:boundary?'flanks':'codon',
      label:boundary?'Deletion boundary; highlighted bases are flanking codons.':codons.map(c=>c.bases+' → '+c.amino_acid).join(' · ')};
  }
  // Project a change present in other selected samples onto this sample's aligned site.
  const map=e.position===0?{query_position:0,deleted:false}:referenceToQuery(p,e.position);
  if(!map)return null;
  const codons=p.codon_map.codons;
  if(e.kind==='insertion'||e.kind==='deletion'||map.deleted){
    const left=codons.find(c=>c.aa_index===map.query_position&&!c.after_stop),right=codons.find(c=>c.aa_index===map.query_position+1&&!c.after_stop);
    if(!left&&!right)return null;
    const near=[left,right].filter(Boolean);
    return {anchor:left?left.positions[2]+.5*direction:right.positions[0]-.5*direction,boundary:true,displayCarries:false,
      codons:near,positions:near.flatMap(c=>c.positions),mode:'flanks',label:'Projected indel boundary in the coordinate sample; highlighted bases are flanks, not an altered codon.'};
  }
  const c=codons.find(c=>c.aa_index===map.query_position&&!c.after_stop);
  if(!c)return null;
  return {anchor:c.positions[0],boundary:false,displayCarries:false,codons:[c],positions:c.positions,mode:'codon',label:'Aligned site in coordinate sample: '+c.bases+' → '+c.amino_acid+'. This sample does not carry the plotted change.'};
}

function referenceDetails(data,record){
  if(!record)return [];
  const rows=[],seen=new Set();
  for(const p of record.proteins){
    const sample=(data.samples||[]).find(s=>s.sample===(p._sourceSample||record.sample));
    const ref=sample?.provenance?.panel?.references?.find(r=>r.id===p.reference_id);
    const row={gene:p.gene,id:p.reference_id||'',accession:ref?.accession||p.reference_accession||'',
      proteinId:ref?.protein_id||p.reference_protein_id||'',strain:ref?.strain||'',
      sourceUrl:ref?.source_url||'',numbering:ref?.numbering||p.numbering||'full-length reference protein',
      synthetic:!!data.demonstration};
    const key=JSON.stringify(row);if(!seen.has(key)){rows.push(row);seen.add(key);}
  }
  return rows;
}

const SEGMENT_ORDER=['PB2','PB1','PA','HA','NP','NA','MP','NS'];
function constellationState(data,sampleName){
  const s=(data.samples||[]).find(s=>s.sample===sampleName);
  return SEGMENT_ORDER.map(segment=>{
    const records=(s?.proteins||[]).filter(p=>p.segment===segment),sequence=(s?.segment_sequences||[]).some(r=>r.segment===segment&&r.sequence);
    const changes=new Set(records.filter(p=>ASSESSED.has(p.status)).flatMap(p=>(p.changes||[]).map(c=>JSON.stringify([p.gene,p.reference_id,c.kind,c.position,c.reference_aa,c.query_aa]))));
    const assessed=records.filter(p=>ASSESSED.has(p.status)).length;
    const state=!records.length?'no-data':records.every(p=>p.status==='READY')?'assessed':'review';
    return {segment,state,sequence,assessed,cdsCount:records.length,changes:changes.size};
  });
}
// Same clockwise annular geometry as scripts/report/genome-constellation.js.
function wheelPolar(cx,cy,r,a){return[cx+r*Math.cos(a-Math.PI/2),cy+r*Math.sin(a-Math.PI/2)];}
function wheelArc(cx,cy,inner,outer,start,end){
  const [x1,y1]=wheelPolar(cx,cy,outer,start),[x2,y2]=wheelPolar(cx,cy,outer,end),[x3,y3]=wheelPolar(cx,cy,inner,end),[x4,y4]=wheelPolar(cx,cy,inner,start),large=end-start>Math.PI?1:0;
  return `M ${x1} ${y1} A ${outer} ${outer} 0 ${large} 1 ${x2} ${y2} L ${x3} ${y3} A ${inner} ${inner} 0 ${large} 0 ${x4} ${y4} Z`;
}

// Reference-specific precursor regions. Coordinates are inclusive and never subtype-wide guesses.
const HA_REFERENCE_REGIONS={
  protein:'YP_308669.1',accession:'NC_007362.1',length:568,uniprot:'Q9Q0U6',
  sources:[
    {label:'Signal peptide: Wibawa et al. (2011)',url:'https://doi.org/10.1186/1743-422X-8-425'},
    {label:'HA1 and HA2 boundary: PDB 4MHI depositor annotation',url:'https://pdbj.org/emnavi/quick.php?id=pdb-4mhi'},
    {label:'Full-length precursor: NCBI YP_308669.1',url:'https://www.ncbi.nlm.nih.gov/protein/YP_308669.1'}
  ],
  regions:[{name:'Signal peptide',short:'SP',start:1,end:16,color:'#4AB7C4'},
           {name:'HA1',short:'HA1',start:17,end:346,color:'#8C1D40'},
           {name:'HA2',short:'HA2',start:347,end:568,color:'#FFC627'}]
};
function proteinRegions(data,record,p){
  if(p.gene!=='HA'||!record)return [];
  const sample=(data.samples||[]).find(s=>s.sample===(p._sourceSample||record.sample)),ref=sample?.provenance?.panel?.references?.find(r=>r.id===p.reference_id);
  if(ref?.reference_regions?.length){
    const sequence=ref.sequence||'',regions=ref.reference_regions;
    const valid=regions.every(r=>['Signal peptide','HA1','HA2'].includes(r.name)&&Number.isInteger(r.start)&&Number.isInteger(r.end)&&r.start>=1&&r.end>=r.start&&r.end<=sequence.length&&/^#[0-9a-f]{6}$/i.test(r.color));
    if(valid&&ref.region_sources?.length&&(!p.reference_alignment||sequence===p.reference_alignment.replace(/-/g,'')))return regions;
    return [];
  }
  const protein=ref?.protein_id||p.reference_protein_id,accession=ref?.accession||p.reference_accession;
  const sequence=ref?.sequence||(p.reference_alignment||'').replace(/-/g,'');
  if(protein!==HA_REFERENCE_REGIONS.protein||accession!==HA_REFERENCE_REGIONS.accession||sequence.length!==HA_REFERENCE_REGIONS.length)return [];
  if(ref?.sequence&&p.reference_alignment&&ref.sequence!==(p.reference_alignment||'').replace(/-/g,''))return [];
  return HA_REFERENCE_REGIONS.regions;
}

const MATRIX_COLORS={M1:'#8C1D40',M2:'#FFC627'};
const SEGMENT_PRODUCT_COLORS={MP:MATRIX_COLORS,NS:{NS1:'#8C1D40',NEP:'#FFC627'},PB1:{PB1:'#8C1D40','PB1-F2':'#FFC627'},PA:{PA:'#8C1D40','PA-X':'#FFC627'}};
function canonicalProduct(gene){return gene==='NS2'?'NEP':gene;}
function productLabel(gene){return canonicalProduct(gene)==='NEP'?'NEP (NS2)':gene;}
function proteinTrackColor(record,gene){return SEGMENT_PRODUCT_COLORS[record?.segment]?.[canonicalProduct(gene)]||null;}
function cdsTrackRecords(record){
  if(!SEGMENT_PRODUCT_COLORS[record?.segment]||!record.sequence?.length)return [];
  const rows=[],seen=new Set(),length=record.sequence.length;
  for(const p of record.proteins||[]){
    const gene=canonicalProduct(p.gene),color=proteinTrackColor(record,gene);if(!color)continue;
    const f=p.cds_annotation,intervals=f?.intervals;
    if(!intervals?.length||!intervals.every(pair=>pair.length===2&&pair.every(n=>Number.isInteger(n)&&n>=1&&n<=length)))continue;
    const strands=new Set(intervals.map(([a,b])=>a<=b?'+':'-'));if(strands.size!==1)continue;
    const key=JSON.stringify([gene,intervals]);if(seen.has(key))continue;seen.add(key);
    rows.push({gene,intervals,strand:[...strands][0],partial:!!f.partial,color});
  }
  const order=Object.keys(SEGMENT_PRODUCT_COLORS[record.segment]);
  return rows.sort((a,b)=>order.indexOf(a.gene)-order.indexOf(b.gene));
}
function matrixCdsRecords(record){return record?.segment==='MP'?cdsTrackRecords(record):[];}

const ALL_SAMPLES='__all_samples__';
function cohortPercent(event,selected){return selected.size?100*event.n/selected.size:0;}
function passesFrequency(event,selected,percent){return selected.size>0&&event.n*100+1e-9>=percent*selected.size;}
function cohortRecord(data,segment,selected){
  const proteins=[];
  for(const group of groups(data)){
    const members=group.records.filter(r=>selected.has(r.sample)&&r.protein.segment===segment);
    const row=members.find(r=>ASSESSED.has(r.protein.status))||members[0];
    if(!row)continue;
    const sample=data.samples.find(s=>s.sample===row.sample),ref=sample.provenance?.panel?.references?.find(r=>r.id===row.protein.reference_id);
    const sequence=ref?.sequence||(row.protein.reference_alignment||'').replace(/-/g,'');
    if(!sequence)continue;
    const p={...row.protein,_groupKey:group.key,_sourceSample:row.sample,status:members.some(r=>ASSESSED.has(r.protein.status))?'READY':'COHORT_UNAVAILABLE',issues:[],reference_alignment:sequence,query_alignment:sequence,query_sequence:sequence};
    delete p.codon_map;delete p.cds_annotation;delete p.alignment_resolution;proteins.push(p);
  }
  return proteins.length?{key:ALL_SAMPLES+':'+segment,sample:ALL_SAMPLES,seqid:'',segment,sequence:'',proteins,aggregate:true}:null;
}

const api={ALL_SAMPLES,cohortPercent,passesFrequency,cohortRecord,SEGMENT_PRODUCT_COLORS,canonicalProduct,productLabel,proteinTrackColor,cdsTrackRecords,MATRIX_COLORS,matrixCdsRecords,HA_REFERENCE_REGIONS,proteinRegions,positionRanges,proteinReasons,proteinSpan,aminoAt,constellationState,wheelArc,referenceDetails,projectEvent,segmentRecords,codonSelection,referenceToQuery,groups,events,callablePosition,callableEvent,matches,referenceLength};
if(typeof module!=='undefined')module.exports=api;
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id),NS='http://www.w3.org/2000/svg';
const data=JSON.parse($('aa-data').textContent),allGroups=groups(data),selected=new Set(data.samples.map(s=>s.sample));
let allMode=true;
let current=allGroups[0],activeKey=null,domain=[0,current?.length||1],visibleEvents=[];
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function svg(tag,attrs,text){const e=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs||{}))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;}
function add(parent,tag,attrs,text){const e=svg(tag,attrs,text);parent.append(e);return e;}
function save(text,name,type){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([text],{type}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function fmt(f){return Math.round(f*100)+'%';}
function changeLabel(kind){return kind==='stop_gain'?'Nonsense mutation':kind.replaceAll('_',' ');}
function openMutationDialog(){
  const dialog=$('mutation-dialog');
  if(!dialog.open){if(typeof dialog.showModal==='function')dialog.showModal();else{dialog.setAttribute('open','');dialog.open=true;}}
  $('close-mutation-dialog').focus?.();
}
function closeMutationDialog(){
  const dialog=$('mutation-dialog');
  if(typeof dialog.close==='function')dialog.close();else{dialog.removeAttribute('open');dialog.open=false;}
  $('segment-browser').focus?.({preventScroll:true});
}
$('close-mutation-dialog').addEventListener('click',closeMutationDialog);
$('mutation-dialog').addEventListener('close',()=>$('segment-browser').focus?.({preventScroll:true}));

function setDomain(){domain=[0,current?.length||1];}
function sampleChoices(){
  $('samples').replaceChildren();const query=$('sample-search').value.trim().toLowerCase();
  for(const s of data.samples){if(!s.sample.toLowerCase().includes(query))continue;const label=el('label',undefined,'sample-option'),input=el('input');input.type='checkbox';input.checked=selected.has(s.sample);input.addEventListener('change',()=>{input.checked?selected.add(s.sample):selected.delete(s.sample);activeKey=null;draw();});label.append(input,el('span',s.sample));$('samples').append(label);}
}
function stats(){
  const totalChanges=new Set();for(const g of allGroups)for(const e of events(g,selected))totalChanges.add(g.key+e.key);
  $('stats').replaceChildren();$('cohort-count').textContent=selected.size+' / '+data.samples.length+' comparison samples';
  for(const [n,label]of[[selected.size,'selected samples'],[allGroups.length,'protein tracks'],[totalChanges.size,'distinct changes'],[current?.length||'—','aa in selected reference']]){
    const box=el('div',undefined,'stat');box.append(el('strong',String(n)),el('span',label));$('stats').append(box);
  }
}
function detail(e){
  const box=$('detail');box.replaceChildren();
  if(!e)return;
  box.append(el('h2',e.change,'mutation-name'),el('span',changeLabel(e.kind),'badge'),el('p',e.n+' / '+selected.size+' selected samples carry this change','metric'),el('p',e.denominator+' samples have a callable comparison at this position','muted'),el('p',Math.round(cohortPercent(e,selected))+'% of all '+selected.size+' selected samples','muted'),el('p',`Reference: ${current.reference} · position ${e.position}${e.kind==='insertion'?' (after anchor residue)':''}`,'muted'));
  const displayed=current.records.find(r=>r.sample===bCurrent?.sample&&r.protein.seqid===bCurrent?.seqid);
  const projection=displayed&&projectEvent(displayed.protein,e);
  const regionProtein=displayed?.protein||bCurrent?.proteins.find(p=>p._groupKey===current.key);
  const region=regionProtein&&proteinRegions(data,bCurrent,regionProtein).find(r=>e.position>=r.start&&e.position<=r.end);
  if(region)box.append(el('p','Reference region: '+region.name+' · precursor positions '+region.start+'–'+region.end,'muted'));
  if(projection){
    const status=el('div',undefined,'sample-state '+(projection.displayCarries?'present':'absent'));
    status.append(el('strong',projection.displayCarries?'Present in displayed sample':'Not present in displayed sample'),el('p',bCurrent.sample));
    if(!projection.boundary)status.append(el('p','Displayed amino acid: '+projection.codons.map(c=>c.amino_acid).join(' · ')));
    box.append(status);
    if(!projection.displayCarries){
      const carrier=current.records.find(r=>e.carriers.has(r.sample)&&bRecords.some(b=>b.sample===r.sample&&b.seqid===r.protein.seqid));
      if(carrier){const button=el('button','Show carrier: '+carrier.sample);button.onclick=()=>choose(e,carrier);box.append(button);}
    }
  }
  if(displayed&&!projection){
    const residue=aminoAt(displayed.protein,e.position),present=e.carriers.has(bCurrent.sample);
    box.append(el('strong',present?'Present in displayed sample':'Not present in displayed sample'));
    if(residue)box.append(el('p','Displayed amino acid: '+residue.amino_acid));
  }
  const list=el('ul',undefined,'detail-list');for(const s of e.carriers)list.append(el('li',s));box.append(el('h3','Samples carrying the change'),list);
  if(!e.evidence.length)box.append(el('p','No exact-match annotation in the pilot evidence catalog.','muted'));
  for(const ev of e.evidence){const d=el('div',undefined,'evidence');d.append(el('strong','Published association'),el('p',ev.statement),el('p',ev.study_context));if(/^https:\/\//.test(ev.citation_url)){const a=el('a','Read study');a.href=ev.citation_url;a.target='_blank';a.rel='noopener noreferrer';d.append(a);}box.append(d);}
  const container=el('details'),summary=el('summary','Sequence context');container.append(summary,el('p','A representative best-scoring alignment is shown. Calls exclude positions that differ across equally scoring alignments.','muted'));
  for(const r of current.records.filter(r=>e.carriers.has(r.sample))){
    const a=r.protein.reference_alignment||'',b=r.protein.query_alignment||'';let pos=0,index=0;
    for(let i=0;i<a.length;i++){if(a[i]!=='-')pos++;if(pos>=e.position){index=i;break;}}
    const lo=Math.max(0,index-15),hi=Math.min(a.length,index+16);
    container.append(el('p',r.sample,'muted'),el('pre','Ref    '+a.slice(lo,hi)+'\nSample '+b.slice(lo,hi)));
  }
  box.append(container);
  const view=el('button','Zoom to amino acid');view.onclick=()=>{browserRange(Math.max(1,e.position-12),e.position+12);drawBrowser();closeMutationDialog();$('segment-browser').scrollIntoView?.({behavior:'smooth',block:'start'});};box.append(view);
}
function choose(e,preferred){activeKey=e.key;if(!allMode||preferred){if(preferred)allMode=false;linkMutation(e,preferred);}draw();openMutationDialog();}
function draw(){
  if(allMode&&typeof bRecords!=='undefined'){bCurrent=cohortRecord(data,navSegment||bCurrent?.segment||'PB2',selected);}
  const query=$('search').value.trim(),kind=$('kind').value;
  visibleEvents=current?events(current,selected).filter(e=>e.position>=domain[0]&&e.position<=domain[1]&&(kind==='all'||e.kind===kind)&&matches(e,query)&&passesFrequency(e,selected,Number($('frequency').value))):[];
  if(activeKey&&!visibleEvents.some(e=>e.key===activeKey))activeKey=null;
  $('plot-title').textContent=bCurrent?bCurrent.segment+' mutation & coding landscape':'Mutation & coding landscape';
  $('reference-note').textContent=bCurrent?(allMode?'All selected samples · '+bCurrent.segment+' · reference protein coordinates':'Displayed sequence: '+bCurrent.sample+' · '+bCurrent.segment+' consensus'):'';
  stats();detail(visibleEvents.find(e=>e.key===activeKey));drawBrowser();
}
for(const id of ['search','kind','frequency'])$(id).addEventListener('input',draw);
$('all-samples').onclick=()=>{data.samples.forEach(s=>selected.add(s.sample));sampleChoices();draw();};
$('no-samples').onclick=()=>{selected.clear();sampleChoices();draw();};
$('download-tsv').onclick=()=>save(JSON.parse($('aa-tsv').textContent),'amino_acid_changes.tsv','text/tab-separated-values');
$('download-json').onclick=()=>save($('aa-data').textContent,'amino_acid_changes.json','application/json');
$('download-svg').onclick=()=>{const root=$('browser-plot').querySelector('svg');if(root)save(new XMLSerializer().serializeToString(root),((bCurrent?.segment||'segment')+'-mutation-coding-landscape.svg'),'image/svg+xml');};
const bRecords=segmentRecords(data);
let navSample='',navSegment='';
const informative=r=>r.proteins.reduce((n,p)=>n+(ASSESSED.has(p.status)&&p.codon_map?.codons?.length?(p.changes||[]).length:0),0);
let bCurrent=bRecords.reduce((best,r)=>!best||informative(r)>informative(best)?r:best,null),bDomain=[1,bCurrent?.sequence.length||120],bSelection=null,bNote='';
function chooseSegment(sampleName,segment){
  allMode=sampleName===ALL_SAMPLES;
  navSample=sampleName;navSegment=segment;activeKey=null;bSelection=null;bNote='';
  const options=bRecords.filter(r=>r.sample===sampleName&&r.segment===segment);
  bCurrent=allMode?cohortRecord(data,segment,selected):options.reduce((best,r)=>!best||informative(r)>informative(best)?r:best,null);
  $('nav-sample').value=sampleName;$('browser-record').value=bCurrent?.key||'';
  if(bCurrent){
    const relevant=allGroups.filter(g=>bCurrent.aggregate?bCurrent.proteins.some(p=>p._groupKey===g.key):g.records.some(r=>r.sample===sampleName&&r.protein.seqid===bCurrent.seqid));
    current=relevant.find(g=>g.records.some(r=>r.sample===sampleName&&r.protein.changes?.length))||relevant[0]||null;
    
    setDomain();browserRange(1,Infinity);
  }else{current=null;bNote='No recorded protein entries for '+sampleName+' / '+segment+'.';}
  draw();
}
function drawNavigation(){
  if(bCurrent){navSample=allMode?ALL_SAMPLES:bCurrent.sample;navSegment=bCurrent.segment;}
  if(!navSample)navSample=allMode?ALL_SAMPLES:data.samples[0]?.sample||'';
  if(!navSegment)navSegment='PB2';
  $('nav-sample').replaceChildren();const allOption=el('option','All samples');allOption.value=ALL_SAMPLES;$('nav-sample').append(allOption);for(const s of data.samples){const option=el('option',s.sample);option.value=s.sample;$('nav-sample').append(option);}
  $('nav-sample').value=navSample;$('nav-sample').disabled=!data.samples.length;
  const rows=allMode?SEGMENT_ORDER.map(segment=>{const gs=allGroups.filter(g=>g.records.some(r=>selected.has(r.sample)&&r.protein.segment===segment));return{segment,cdsCount:gs.length,changes:gs.reduce((n,g)=>n+events(g,selected).length,0)};}):constellationState(data,navSample),focus=rows.find(r=>r.segment===navSegment),mount=$('constellation-wheel');mount.replaceChildren();
  const root=svg('svg',{xmlns:NS,viewBox:'0 0 320 320',role:'img','aria-label':'Eight-segment amino acid analysis navigator for '+navSample});
  add(root,'title',{},'Genome constellation · select a segment to view its proteins');
  rows.forEach((r,i)=>{
    const start=i*Math.PI/4+.025,end=(i+1)*Math.PI/4-.025,on=r.segment===navSegment;
    const g=add(root,'g',{class:'constellation-wedge',role:'button',tabindex:0,'aria-pressed':on,'aria-label':'Show '+r.segment+' proteins'});
    add(g,'path',{d:wheelArc(160,160,88,148,start,end),fill:on?'#8c193e':'#747474',stroke:on?'#ffbd18':'white','stroke-width':on?6:3});
    const [x,y]=wheelPolar(160,160,118,(start+end)/2);
    add(g,'text',{x,y:y+6,'text-anchor':'middle','font-size':21,'font-weight':750,fill:'white'},r.segment);
    const activate=()=>chooseSegment(navSample,r.segment);g.addEventListener('click',activate);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});
  });
  add(root,'circle',{cx:160,cy:160,r:73,fill:'#080808',stroke:'#ffc627','stroke-width':6});
  add(root,'text',{x:160,y:153,'text-anchor':'middle','font-size':34,'font-weight':750,fill:'white'},navSegment);
  add(root,'text',{x:160,y:178,'text-anchor':'middle','font-size':14,'font-weight':700,fill:'#ffc627'},focus?.cdsCount?focus.changes+' AA changes':'No AA data');
  add(root,'text',{x:160,y:197,'text-anchor':'middle','font-size':10,fill:'#d6dce0'},allMode?'ALL SAMPLES':'DISPLAYED SAMPLE');
  mount.append(root);
  $('segment-summary').replaceChildren(el('strong',navSegment+' · '));
  $('segment-summary').append(el('span',focus?.cdsCount?focus.cdsCount+(allMode?' protein reference tracks · ':' recorded protein entries · ')+focus.changes+' reported AA changes':'No recorded protein entries'));
}
$('nav-sample').addEventListener('change',()=>chooseSegment($('nav-sample').value,navSegment||'PB2'));
$('sample-search').addEventListener('input',sampleChoices);

function browserChoices(){
  $('browser-record').replaceChildren();
  for(const r of bRecords){const option=el('option',r.sample+' · '+r.segment+' · '+r.seqid);option.value=r.key;$('browser-record').append(option);}
  $('browser-record').disabled=!bRecords.length;
  if(bCurrent)$('browser-record').value=bCurrent.key;
}
function browserRange(lo,hi){
  const length=Math.max(1,...(bCurrent?.proteins||[]).map(proteinSpan));
  bDomain=[Math.min(length,Math.max(1,Math.floor(lo))),Math.min(length,Math.max(1,Math.ceil(hi)))];
  $('browser-from').value=bDomain[0];$('browser-to').value=bDomain[1];
  $('browser-from').max=length;$('browser-to').max=length;
}
function selectionFor(record,p,c){
  const selection=codonSelection(p,c);
  bSelection=selection?{...selection,protein:p,gene:p.gene,change:c.change||'Aligned position'}:null;
  bNote=selection?'':p.codon_map?'No reliable codon mapping is available for this CDS.':'This is an older result. Regenerate its sample changes.json to add codon maps.';
  if(selection?.positions.length){const lo=Math.min(...selection.positions),hi=Math.max(...selection.positions);browserRange(c.position-12,c.position+12);}
}
function linkMutation(e,preferred){
  if(!current)return;
  const r=preferred||current.records.find(r=>r.sample===bCurrent?.sample&&e.carriers.has(r.sample))||current.records.find(r=>e.carriers.has(r.sample));
  if(!r)return;
  const record=bRecords.find(b=>b.sample===r.sample&&b.seqid===r.protein.seqid);
  if(!record){bCurrent=null;$('browser-record').value='';bSelection=null;bNote='Nucleotide sequence is absent from this older result. Regenerate the sample changes.json to enable codon links.';return;}
  bCurrent=record;$('browser-record').value=record.key;
  const changes=(r.protein.changes||[]).filter(c=>c.kind===e.kind&&c.position===e.position&&c.reference_aa===e.reference_aa&&c.query_aa===e.query_aa);
  if(changes.length){
    selectionFor(record,r.protein,changes[0]);
    if(e.kind==='insertion'&&changes.length>1&&bSelection){
      const parts=changes.map(c=>codonSelection(r.protein,c)).filter(Boolean);
      bSelection.codons=parts.flatMap(s=>s.codons);bSelection.positions=[...new Set(parts.flatMap(s=>s.positions))];
      bSelection.label='Inserted residue codons · '+parts.map(p=>p.codons.map(c=>c.bases).join(' ')).join(' ');
      browserRange(e.position-12,e.position+12);
    }
  }
}
function codonClick(p,c){
  if(!bCurrent)return;
  const group=allGroups.find(g=>g.records.some(r=>r.sample===bCurrent.sample&&r.protein===p));
  const change=(p.changes||[]).find(x=>x.kind!=='deletion'&&x.query_position===c.aa_index);
  if(group&&change){
    current=group;setDomain();
    selected.add(bCurrent.sample);sampleChoices();$('search').value='';$('kind').value='all';
    const e=events(group,selected).find(e=>e.kind===change.kind&&e.position===change.position&&e.reference_aa===change.reference_aa&&e.query_aa===change.query_aa);
    if(e){activeKey=e.key;linkMutation(e,{sample:bCurrent.sample,protein:p});draw();openMutationDialog();return;}
  }
  bSelection={mode:'codon',protein:p,gene:p.gene,change:'CDS index '+c.aa_index,codons:[c],positions:c.positions,
    label:'Translated CDS index '+c.aa_index+' · '+c.bases+' → '+c.amino_acid+(c.crosses_junction?' · codon spans a splice junction':'')};
  activeKey=null;bNote='';draw();openMutationDialog();
}
function drawReference(){
  const box=$('comparison-reference');box.replaceChildren();
  box.append(el('p','COMPARISON REFERENCE · AMINO ACID CHANGES','eyebrow'));
  const refs=referenceDetails(data,bCurrent);
  if(!bCurrent){box.append(el('p','No comparison reference is available for this sample/segment.'));return;}
  const strains=[...new Set(refs.map(r=>r.synthetic?'Synthetic demonstration reference — not a biological strain':r.strain||'Strain name not recorded in these results'))];
  for(const strain of strains)box.append(el('strong',strain,'reference-strain'));
  if(!refs.length)box.append(el('p','No protein comparison reference was assigned for this segment.'));
  for(const r of refs){
    const row=el('div',undefined,'reference-accessions');row.append(el('b',r.gene));
    const nucleotide=el('span','Segment accession: ');
    if(r.accession){
      const node=el(!r.synthetic&&/^https:\/\//.test(r.sourceUrl)?'a':'span',r.accession);
      if(node.tagName==='A'||node.tagName==='a'){node.href=r.sourceUrl;node.target='_blank';node.rel='noopener noreferrer';}
      nucleotide.append(node);
    }else nucleotide.append(el('span',r.id?'not recorded':'not assigned'));
    row.append(nucleotide);
    const protein=el('span','Protein accession: ');
    if(r.proteinId){
      const linkable=!r.synthetic&&/^[A-Z]{1,4}_?[0-9]+\.[0-9]+$/.test(r.proteinId);
      const node=el(linkable?'a':'span',r.proteinId);
      if(linkable){node.href='https://www.ncbi.nlm.nih.gov/protein/'+encodeURIComponent(r.proteinId);node.target='_blank';node.rel='noopener noreferrer';}
      protein.append(node);
    }else protein.append(el('span','not recorded'));
    row.append(protein);box.append(row);
  }
  box.append(el('p','Each protein has its own reference-amino-acid axis. Residue letters show the displayed sample aligned to that reference. Codon and nucleotide details are available when you inspect a marker.','reference-explanation'));
}
function drawColorLegend(){
  const box=$('mutation-color-key');box.replaceChildren();
  const ha=bCurrent?.proteins.some(p=>proteinRegions(data,bCurrent,p).length);
  const products=Object.entries(SEGMENT_PRODUCT_COLORS[bCurrent?.segment]||{}).filter(([gene])=>bCurrent.proteins.some(p=>canonicalProduct(p.gene)===gene)).map(([gene,color])=>[productLabel(gene),color]);
  const entries=products.length?products:ha?HA_REFERENCE_REGIONS.regions.map(r=>[r.name,r.color]):Object.entries(COLORS).map(([kind,color])=>[changeLabel(kind),color]);
  for(const [name,color]of entries){const entry=el('span'),dot=el('i');dot.style.backgroundColor=color;entry.append(dot,el('span',name));box.append(entry);}
}
function drawBrowser(){
  if(allMode)bCurrent=cohortRecord(data,navSegment||bCurrent?.segment||'PB2',selected);
  drawNavigation();drawReference();drawColorLegend();
  $('alignment-key').hidden=true;
  const mount=$('browser-plot');mount.replaceChildren();$('browser-codon').replaceChildren();$('browser-source').replaceChildren();
  $('download-svg').disabled=!bCurrent;
  if(!bCurrent){
    const sample=data.samples.find(s=>s.sample===navSample);
    $('browser-message').textContent=allMode&&!selected.size?'Select comparison samples to display cohort mutations.':bNote||'No recorded protein entries for this segment. '+(REASONS[sample?.status]||'No saved protein annotation is available.');return;
  }
  const record=bCurrent,W=1100,L=185,R=1070,palette=['#8c193e','#247f85','#5666a2','#95601a','#64823f'];
  const plottedCount=record.proteins.filter(p=>ASSESSED.has(p.status)&&p.reference_alignment).length;
  const rowStep=240+(record.proteins.some(p=>proteinRegions(data,record,p).length)?58:0);
  const height=120+plottedCount*rowStep;
  const root=svg('svg',{xmlns:NS,viewBox:`0 0 ${W} ${height}`,role:'img','aria-label':record.sample+' '+record.segment+' independent reference amino acid tracks'});
  add(root,'title',{},record.sample+' · '+record.segment+' · reference amino acid positions');
  const background=add(root,'rect',{width:W,height,fill:'white'}),plotRows=[];
  const cdsRows=cdsTrackRecords(record);
  if(plottedCount&&cdsRows.length){
    const overview=add(root,'g',{class:record.segment==='MP'?'matrix-cds-overview':'segment-cds-overview','data-segment':record.segment,'data-nt-length':record.sequence.length,'aria-label':'Displayed sample '+record.segment+'-segment CDS annotations in nucleotide coordinates'});
    const length=record.sequence.length,edge=n=>L+(n-1)/length*(R-L),bottom=70+cdsRows.length*32;
    add(overview,'text',{x:8,y:16,'font-size':15,'font-weight':700,fill:'#20313b'},record.segment+' segment · CDS');
    add(overview,'text',{x:8,y:34,'font-size':10,fill:'#596a75'},'Displayed sample');
    add(overview,'line',{x1:L,x2:R,y1:28,y2:28,stroke:'#aeb7bd'});
    const step=Math.max(1,Math.ceil(length/5/50)*50),ticks=new Set([1,length]);
    for(let n=step;n<length;n+=step)if(n>length/30&&length-n>length/30)ticks.add(n);
    for(const n of [...ticks].sort((a,b)=>a-b)){const at=edge(n);add(overview,'line',{x1:at,x2:at,y1:24,y2:31,stroke:'#aeb7bd'});add(overview,'text',{x:at,y:18,'font-size':10,'text-anchor':'middle',fill:'#596a75'},n);}
    cdsRows.forEach((row,index)=>{
      const y=60+index*32;
      add(overview,'text',{x:8,y:y+5,'font-size':13,'font-weight':650,fill:row.color==='#FFC627'?'#775b00':row.color},productLabel(row.gene)+' CDS'+(row.partial?' · partial':''));
      for(let j=0;j<row.intervals.length-1;j++){
        const a=row.intervals[j][1],b=row.intervals[j+1][0];
        add(overview,'line',{class:record.segment==='MP'?'matrix-splice':'segment-splice',x1:edge(a),x2:edge(b),y1:y,y2:y,stroke:row.color==='#FFC627'?'#8c6b00':row.color,'stroke-dasharray':'4 3','stroke-width':1.5});
      }
      row.intervals.forEach(([a,b],index)=>{
        const start=edge(Math.min(a,b)),end=edge(Math.max(a,b)+1),last=index===row.intervals.length-1,arrow=Math.min(7,(end-start)/2);
        const points=last?(row.strand==='-'?`${start},${y} ${start+arrow},${y-7} ${end},${y-7} ${end},${y+7} ${start+arrow},${y+7}`:`${start},${y-7} ${end-arrow},${y-7} ${end},${y} ${end-arrow},${y+7} ${start},${y+7}`):`${start},${y-7} ${end},${y-7} ${end},${y+7} ${start},${y+7}`;
        const block=add(overview,'polygon',{class:record.segment==='MP'?'matrix-cds-block':'segment-cds-block','data-gene':row.gene,'data-from-nt':a,'data-to-nt':b,points,fill:row.color,stroke:row.color==='#FFC627'?'#8c6b00':row.color,'stroke-width':.7});
        add(block,'title',{},productLabel(row.gene)+' CDS · sample nt '+a+'–'+b+' · '+row.strand+' strand'+(row.partial?' · partial':''));
      });
    });
    add(overview,'text',{x:L,y:bottom-7,'font-size':10,fill:'#596a75'},'Sample nucleotide positions · dashed connectors join CDS blocks · protein plots below use amino acid positions');
    plotRows.push({node:overview,min:0,max:bottom,right:R});
  }
  let markerCount=0,plotIndex=0,totalBeforeCutoff=0;
  record.proteins.forEach((p,index)=>{
    const y=215+plotIndex*rowStep,color=proteinTrackColor(record,p.gene)||palette[index%palette.length],group=p._groupKey?allGroups.find(g=>g.key===p._groupKey):allGroups.find(g=>g.records.some(r=>r.sample===record.sample&&r.protein===p));
    const length=group?.length||proteinSpan(p),lo=Math.max(1,bDomain[0]),hi=Math.min(length,bDomain[1]);
    const reasons=proteinReasons(p),usable=ASSESSED.has(p.status)&&!!p.reference_alignment;
    const regions=proteinRegions(data,record,p),residueOffset=regions.length?58:0;
    const regionRef=data.samples.find(s=>s.sample===(p._sourceSample||record.sample))?.provenance?.panel?.references?.find(r=>r.id===p.reference_id);
    const regionCaption=regions.map(r=>r.name+' '+r.start+'–'+r.end).join(' · ');
    const issue=el('div',undefined,'protein-notice');
    if(reasons.length){
      issue.append(el('strong',p.gene+(usable?(p.alignment_resolution?.ambiguous?' · Some positions are uncertain':' · Available calls are shown'):' · Mutation calls unavailable')));
      for(const reason of reasons)issue.append(el('p',reason));
      $('browser-source').append(issue);
    }

    if(!usable){
      if(!reasons.length)issue.append(el('strong',p.gene+' · Mutation calls unavailable'),el('p','No usable protein alignment is recorded.'));
      const ref=referenceDetails(data,record).find(r=>r.gene===p.gene&&r.id===p.reference_id);
      issue.append(el('small',(group?.length?group.length+' aa reference · ':'')+(ref?.proteinId||p.reference_id||'Reference not assigned'),'unavailable-reference'));
      if(!reasons.length)$('browser-source').append(issue);
      return;
    }
    const row=add(root,'g',{class:'protein-row','data-protein':p.gene}),rowBounds={node:row,min:y-45,max:y+57,right:R};plotRows.push(rowBounds);
    add(row,'text',{x:8,y:y-25,'font-size':20,'font-weight':750,fill:color==='#FFC627'?'#775b00':color},p.gene);
    add(row,'text',{x:8,y:y-4,'font-size':11,fill:'#596a75'},group?.length?group.length+' aa reference':'No aligned reference');
    const ref=referenceDetails(data,record).find(r=>r.gene===p.gene&&r.id===p.reference_id);
    add(row,'text',{x:8,y:y+15,'font-size':10,fill:'#596a75'},ref?.proteinId||p.reference_id||'Reference not assigned');
    plotIndex++;
    if(lo>hi){
      add(row,'text',{x:L,y:y,'font-size':14,fill:'#596a75'},'This protein ends at amino acid '+length+'; the selected range is outside it.');
    }else{
      const range=hi-lo+1,x=pos=>L+(pos-lo+.5)/(range)*(R-L),tick=Math.max(1,Math.ceil(range/8/5)*5);
      const ticks=new Set([lo,hi]);for(let pos=Math.ceil(lo/tick)*tick;pos<=hi;pos+=tick)if(pos-lo>range/35&&hi-pos>range/35)ticks.add(pos);
      const query=$('search').value.trim(),kind=$('kind').value;
      const unfiltered=group?events(group,selected).filter(e=>(record.aggregate||(e.carriers.has(record.sample)&&(p.changes||[]).some(c=>c.kind===e.kind&&c.position===e.position&&c.reference_aa===e.reference_aa&&c.query_aa===e.query_aa)))&&e.position>=lo-(lo===1?1:0)&&e.position<=hi&&(kind==='all'||e.kind===kind)&&matches(e,query)):[];
      totalBeforeCutoff+=unfiltered.length;
      const rowEvents=unfiltered.filter(e=>passesFrequency(e,selected,Number($('frequency').value)));
      const track=add(row,'g',{class:'protein-track','data-protein':p.gene,'data-from-aa':lo,'data-to-aa':hi});
      for(const pos of p.alignment_resolution?.uncertain_reference_positions||[]){
        if(pos<lo||pos>hi)continue;
        const shade=add(track,'rect',{class:'uncertain-position',x:x(pos)-(R-L)/range*.5,y:y-(rowEvents.length?110:12),width:Math.max(1,(R-L)/range),height:rowEvents.length?125:28,fill:'#e1e5e8',opacity:.7});
        add(shade,'title',{},'Reference amino acid '+pos+': alignment position uncertain; no mutation call or frequency contribution');$('alignment-key').hidden=false;
      }
      add(track,'line',{x1:L,x2:R,y1:y,y2:y,stroke:color,'stroke-width':9,'stroke-linecap':'round'});
      for(const pos of [...ticks].sort((a,b)=>a-b)){
        add(track,'line',{x1:x(pos),x2:x(pos),y1:y+8,y2:y+14,stroke:'#9aaab4'});
        add(track,'text',{x:x(pos),y:y+30,'text-anchor':'middle','font-size':12,fill:'#596a75'},pos);
      }
      add(track,'text',{x:R,y:y+53,'text-anchor':'end','font-size':11,fill:'#596a75'},p.gene+' reference amino acid position');
      if(rowEvents.length){
        rowBounds.min=Math.min(rowBounds.min,y-123);
        const label=add(track,'text',{class:'frequency-axis-label',x:L-12,y:y-109,'text-anchor':'end','font-size':11,'font-weight':650,fill:'#596a75'},'Samples with change (%)');
        add(label,'title',{},'Observed carriers divided by all selected samples. Callable counts are shown in mutation details; missing and uncertain samples cannot satisfy the frequency cutoff.');
      }
      if(rowEvents.length)for(const f of [0,.5,1]){
        const gy=y-16-75*f;add(track,'line',{x1:L,x2:R,y1:gy,y2:gy,stroke:'#e2e8ed','stroke-dasharray':'3 5'});
        add(track,'text',{x:L-12,y:gy+4,'text-anchor':'end','font-size':11,fill:'#6b7c88'},fmt(f));
      }
      const heads=rowEvents.map(e=>x(e.position+(e.kind==='insertion'?.45:0)));
      if(heads.length*24<R-L){
        for(let i=1;i<heads.length;i++)heads[i]=Math.max(heads[i],heads[i-1]+24);
        if(heads.at(-1)>R){heads[heads.length-1]=R;for(let i=heads.length-2;i>=0;i--)heads[i]=Math.min(heads[i],heads[i+1]-24);}
      }
      rowEvents.forEach((e,markerIndex)=>{
        const region=regions.find(r=>Math.max(1,e.position)>=r.start&&Math.max(1,e.position)<=r.end);
        const projection=projectEvent(p,e),present=record.aggregate||e.carriers.has(record.sample),residue=aminoAt(p,e.position),at=x(e.position+(e.kind==='insertion'?.45:0)),ny=y-16-75*cohortPercent(e,selected)/100,c=proteinTrackColor(record,p.gene)||region?.color||COLORS[e.kind]||'#596a75',on=current?.key===group.key&&activeKey===e.key;
        const label=p.gene+' '+e.change+' · reference amino acid '+e.position+(e.kind==='insertion'?' (insertion after this residue)':'')+' · '+e.n+'/'+e.denominator+' samples callable at this position · '+Math.round(cohortPercent(e,selected))+'% of all selected samples'+(record.aggregate?' · cohort view':present?' · present in displayed sample':' · absent from displayed sample')+(region?' · region: '+region.name:'');
        const g=add(track,'g',{class:'lollipop',role:'button',tabindex:0,'aria-label':label,'aria-pressed':on,'data-aa-position':e.position,'data-protein':p.gene,'data-region':region?.name||''});add(g,'title',{},label);
        add(g,'path',{d:`M ${at} ${y-5} L ${at} ${y-12} L ${heads[markerIndex]} ${ny}`,fill:'none',stroke:c,'stroke-width':on?3:1.7,'stroke-dasharray':present?'none':'4 3'});
        const head=heads[markerIndex];
        if(e.evidence.length)add(g,'circle',{cx:head,cy:ny,r:11,fill:'white',stroke:c,'stroke-width':1.5});
        if(e.kind==='insertion'||e.kind==='deletion')add(g,'path',{d:`M ${head} ${ny-7} L ${head+7} ${ny} L ${head} ${ny+7} L ${head-7} ${ny} Z`,fill:present?c:'white',stroke:c,'stroke-width':2});
        else add(g,'circle',{cx:head,cy:ny,r:on?8:6.5,fill:present?c:'white',stroke:on?'#17252d':c==='#FFC627'?'#8c6b00':c,'stroke-width':on?2.5:1.5});
        if(rowEvents.length<=18||on){
          const labelText=e.change+' ('+e.n+'/'+selected.size+')'+(!present&&residue?' ['+residue.amino_acid+' here]':'');
          rowBounds.min=Math.min(rowBounds.min,ny-20-labelText.length*5.2);
          rowBounds.right=Math.max(rowBounds.right,head+10+labelText.length*5.2);
          add(g,'text',{x:head+4,y:ny-12,transform:`rotate(-45 ${head+4} ${ny-12})`,'font-size':12,fill:c==='#FFC627'?'#775b00':c==='#4AB7C4'?'#20616a':c},e.change+' ('+e.n+'/'+selected.size+')'+(!present&&residue?' ['+residue.amino_acid+' here]':''));
        }
        const activate=()=>{
          current=group;setDomain();activeKey=e.key;
          bSelection=projection?{...projection,protein:p,gene:p.gene,change:e.change}:null;
          bNote='';draw();openMutationDialog();
        };
        g.addEventListener('click',activate);g.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();activate();}});markerCount++;
      });
      if(regions.length){
        rowBounds.max=Math.max(rowBounds.max,y+112);
        const band=add(track,'g',{class:'ha-regions','aria-label':'Reference precursor regions: signal peptide, HA1 and HA2'});
        for(const region of regions){
          const a=Math.max(lo,region.start),b=Math.min(hi,region.end);if(a>b)continue;
          const left=x(a)-(R-L)/range*.5,width=(b-a+1)*(R-L)/range;
          const block=add(band,'g',{class:'ha-region',role:'img','aria-label':region.name+' · reference positions '+region.start+'–'+region.end,'data-region':region.name,'data-start':region.start,'data-end':region.end});
          add(block,'title',{},region.name+' · '+(regionRef?.protein_id||p.reference_protein_id||p.reference_id)+' precursor aa '+region.start+'–'+region.end+' · reference annotation, not sample-specific processing');
          add(block,'rect',{x:left,y:y+65,width:Math.max(.5,width),height:22,fill:region.color,stroke:'white','stroke-width':1});
          if(width>=18)add(block,'text',{x:left+width/2,y:y+81,'text-anchor':'middle','font-size':11,'font-weight':650,fill:region.name==='HA1'?'white':'#20313b'},region.name==='Signal peptide'&&width<100?'SP':region.name);
        }
        add(band,'text',{x:L,y:y+106,'font-size':10,fill:'#596a75'},regionCaption+' · reference precursor positions');
      }
      // Residues use reference positions, while letters come from the displayed sample.
      if(range<=55)rowBounds.max=Math.max(rowBounds.max,y+90+residueOffset);
      if(range<=55)for(let position=lo;position<=hi;position++){
        const residue=aminoAt(p,position);if(!residue)continue;
        const at=x(position),token=add(track,'g',{class:'codon-token',role:'button',tabindex:0,'aria-label':p.gene+' reference amino acid '+position+(record.aggregate?' · reference ':' · displayed ')+residue.amino_acid});
        add(token,'rect',{x:at-(R-L)/range*.43,y:y+65+residueOffset,width:(R-L)/range*.86,height:23,rx:3,fill:'#f1f5f7'});
        add(token,'text',{x:at,y:y+82+residueOffset,'text-anchor':'middle','font-size':14,'font-weight':650,fill:color==='#FFC627'?'#775b00':color},residue.amino_acid);
        const activate=()=>{
          current=group;activeKey=null;
          bSelection=residue.codon?{protein:p,gene:p.gene,change:'Reference amino acid '+position,codons:[residue.codon],positions:residue.codon.positions,label:residue.codon.bases+' → '+residue.codon.amino_acid+(residue.codon.crosses_junction?' · codon spans a splice junction':'')}:null;
          draw();$('detail').append(el('h2',p.gene+' · reference position '+position),el('p',(record.aggregate?'Reference amino acid: ':'Displayed amino acid: ')+residue.amino_acid));
          if(!bSelection)$('detail').append(el('p',record.aggregate?'Select an individual sample to inspect this position in its consensus.':residue.deleted?'This reference residue is deleted; no sample codon exists.':'No codon map is recorded for this result.'));openMutationDialog();
        };
        token.addEventListener('click',activate);token.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();activate();}});
      }
    }

  });
  if(plottedCount){
    mount.append(root);
    let top=12,right=W;
    for(const row of plotRows){
      let box={y:row.min,height:row.max-row.min,x:0,width:row.right};
      if(typeof row.node.getBBox==='function'){
        try{const measured=row.node.getBBox();if(measured.height>0)box=measured;}catch(_){/* Conservative geometry fallback for non-rendering DOMs. */}
      }
      row.node.setAttribute('transform',`translate(0 ${top-box.y})`);
      top+=box.height+18;right=Math.max(right,box.x+box.width+12);
    }
    const fittedHeight=Math.max(24,top-18+12);
    root.setAttribute('viewBox',`0 0 ${Math.ceil(right)} ${Math.ceil(fittedHeight)}`);
    background.setAttribute('width',Math.ceil(right));background.setAttribute('height',Math.ceil(fittedHeight));
  }
  $('download-svg').disabled=!plottedCount;
  $('browser-message').textContent=(record.aggregate?'All samples':record.sample)+' · '+record.proteins.length+' protein tracks · '+markerCount+' mutations meet ≥'+$('frequency').value+'% ('+totalBeforeCutoff+' before frequency filter)'+(!selected.size?' · Select samples to show mutations':!markerCount&&totalBeforeCutoff?' · Choose All frequencies to inspect rarer changes':'');
  if(bSelection){
    const card=el('div',undefined,'codon-card');card.append(el('strong',bSelection.gene+' · '+bSelection.change),el('p',bSelection.label),el('p','Consensus nucleotide positions (coding order): '+bSelection.positions.join(', ')),el('p','Codon bases use coding orientation. Plot positions use the full-length reference protein, including any signal peptide.'));$('browser-codon').append(card);
  }else if(activeKey){$('browser-codon').append(el('p',record.aggregate?'Select an individual sample to inspect its codon and nucleotide coordinates.':'No reliable codon map is recorded for this marker. The protein comparison remains available.','muted'));}
}
$('browser-record').addEventListener('change',()=>{
  allMode=false;
  const previous=current?.key,oldEvent=visibleEvents.find(e=>e.key===activeKey);
  bCurrent=bRecords.find(r=>r.key===$('browser-record').value);bSelection=null;bNote='';browserRange(1,Infinity);
  const eligible=allGroups.filter(g=>g.records.some(r=>r.sample===bCurrent?.sample&&r.protein.seqid===bCurrent?.seqid));
  const next=eligible.find(g=>g.key===previous)||eligible.find(g=>g.gene===current?.gene)||eligible[0];
  if(next){current=next;setDomain();}
  if(!next||next.key!==previous)activeKey=null;
  if(oldEvent&&next?.key===previous){const r=next.records.find(r=>r.sample===bCurrent.sample&&r.protein.seqid===bCurrent.seqid),projection=r&&projectEvent(r.protein,oldEvent);if(projection)bSelection={...projection,protein:r.protein,gene:r.protein.gene,change:oldEvent.change};}
  draw();
});
$('browser-zoom').onclick=()=>{
  if(!bCurrent)return;const a=Number($('browser-from').value),b=Number($('browser-to').value);
  if(!Number.isInteger(a)||!Number.isInteger(b)||a<1||b>Math.max(...bCurrent.proteins.map(proteinSpan))||a>b){$('browser-message').textContent='Enter an amino acid range within 1..'+Math.max(...bCurrent.proteins.map(proteinSpan));return;}
  browserRange(a,b);drawBrowser();
};
$('browser-fit').onclick=()=>{if(bCurrent){browserRange(1,Infinity);drawBrowser();}};
$('browser-bases').onclick=()=>{if(bCurrent){const center=current?events(current,selected).find(e=>e.key===activeKey)?.position||bDomain[0]:bDomain[0];browserRange(Math.max(1,center-12),center+27);drawBrowser();}};

browserChoices();browserRange(1,Infinity);
const initial=bCurrent&&allGroups.find(g=>g.records.some(r=>r.sample===bCurrent.sample&&r.protein.seqid===bCurrent.seqid&&r.protein.changes?.length));
if(initial)current=initial;

navSegment=bCurrent?.segment||'PB2';navSample=ALL_SAMPLES;
sampleChoices();setDomain();draw();
})();
