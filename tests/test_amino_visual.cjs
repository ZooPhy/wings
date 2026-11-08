const assert=require('node:assert/strict');
const m=require('../scripts/report/amino-acid-visual.js');
function sample(name,status='READY',query='MACDEFGHIK',changes=[]){return{sample:name,status,provenance:{panel:{references:[{id:'SYN.1:PB2',sequence:'MACDEFGHIK'}]}},proteins:[{gene:'PB2',reference_id:'SYN.1:PB2',reference_alignment:'MACDEFGHIK',query_alignment:query,status,changes}]};}
const change={position:6,query_position:6,kind:'substitution',reference_aa:'F',query_aa:'Y',change:'F6Y',evidence:[]};
const a=sample('a','READY','MACDEYGHIK',[change]),b=sample('b'),x=sample('unknown','PARTIAL_INTERPRETATION','MACDEXGHIK'),bad=sample('withheld','DISTANT_REFERENCE');
let g=m.groups({samples:[a,b,x,bad]})[0],e=m.events(g,new Set(['a','b','unknown','withheld']))[0];
assert.equal(e.n,1);assert.equal(e.denominator,2);assert.equal(e.frequency,.5);
assert.equal(m.events(g,new Set(['a']))[0].frequency,1);
assert.equal(m.events(g,new Set(['b'])).length,0);
assert.equal(m.events(g,new Set()).length,0);
assert(m.matches(e,'F6Y'));assert(m.matches(e,'a'));assert(!m.matches(e,'no such event'));
const c=sample('duplicate-CDS','READY','MACDEYGHIK',[change]);c.proteins.push({...c.proteins[0]});
g=m.groups({samples:[c]})[0];e=m.events(g,new Set(['duplicate-CDS']))[0];assert.equal(e.n,1);assert.equal(e.denominator,1);
const stop=sample('stop','PARTIAL_INTERPRETATION','MAC*EFGHIK');assert(!m.callablePosition(stop.proteins[0],7));assert(m.callablePosition(stop.proteins[0],4));
const alt=sample('other');alt.proteins[0].reference_id='OTHER.1:PB2';assert.equal(m.groups({samples:[a,alt]}).length,2);
const altered=sample('same-id-different-sequence');altered.provenance.panel.references[0].sequence='MACDEFGHIL';assert.equal(m.groups({samples:[a,altered]}).length,2);
assert.equal(m.groups({samples:[]}).length,0);
assert.equal(m.referenceLength(a,a.proteins[0]),10);
const insertion={position:0,kind:'insertion'};assert(m.callableEvent(a.proteins[0],insertion,10));
assert(!m.callableEvent(x.proteins[0],{position:5,kind:'insertion'},10));
console.log('PASS: position-specific denominators, sample filters, missing/withheld calls, stops, duplicate CDSs, insertion anchors and reference separation.');
// Exercise the browser event paths with a minimal DOM. Layout still needs a browser.
const fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.listeners={};this._text='';this._value='';this.style={};}
  append(...children){for(const c of children)this.children.push(c);}
  replaceChildren(...children){this.children=[];this._text='';this.append(...children);}
  setAttribute(k,v){this.attrs[k]=String(v);}
  addEventListener(k,fn){this.listeners[k]=fn;}
  focus(){this.focused=true;}
  showModal(){this.open=true;this.attrs.open='';}
  close(){this.open=false;delete this.attrs.open;}
  removeAttribute(k){delete this.attrs[k];}
  get textContent(){return this._text+this.children.map(c=>typeof c==='string'?c:c.textContent).join('');}
  set textContent(v){this._text=String(v);this.children=[];}
  get value(){return this._value||(this.tagName==='select'?this.children[0]?.value||'':'');}
  set value(v){this._value=String(v);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  querySelectorAll(selector){const out=[];function visit(e){for(const c of e.children){if(typeof c==='string')continue;if(c.tagName===selector||(selector.startsWith('.')&&c.attrs.class===selector.slice(1)))out.push(c);visit(c);}}visit(this);return out;}
}
function runDom(samples,options={}){
  const ids=['aa-data','aa-tsv','mutation-dialog','close-mutation-dialog','search','kind','frequency','from','to','samples','stats','sample-search','cohort-count','nav-sample','constellation-wheel','segment-summary','comparison-reference','detail','plot','tracks','plot-message','plot-title','reference-note','download-svg','download-tsv','download-json','all-samples','no-samples','zoom','reset','segment-browser','browser-record','browser-from','browser-to','browser-zoom','browser-fit','browser-bases','download-segment-svg','browser-message','browser-plot','browser-codon','browser-source','alignment-key','mutation-color-key'];
  const els=Object.fromEntries(ids.map(id=>[id,new Element(['protein','kind','frequency','browser-record','nav-sample'].includes(id)?'select':'div')]));
  els['aa-data'].textContent=JSON.stringify({samples});els['aa-tsv'].textContent=JSON.stringify('sample\tchange\n');els.kind.value='all';els.frequency.value='80';
  const document={getElementById:id=>{assert(els[id],'Missing '+id);return els[id];},createElement:tag=>new Element(tag),createElementNS:(ns,tag)=>new Element(tag)};
  vm.runInNewContext(fs.readFileSync(require.resolve('../scripts/report/amino-acid-visual.js'),'utf8'),{document,console,Set,Map,JSON,URL,Blob,setTimeout});
  if(!options.defaults&&samples.length){
    els.frequency.value='0';els.frequency.listeners.input();
    const preferred=samples.find(s=>s.proteins?.some(p=>p.codon_map?.codons?.length&&p.changes?.length))||samples.find(s=>s.proteins?.some(p=>p.changes?.length))||samples[0];
    els['nav-sample'].value=preferred.sample;els['nav-sample'].listeners.change();
  }
  return els;
}
const pmap={status:'READY',codon_map:{codons:[{aa_index:1,positions:[12,11,7],bases:'ATG',amino_acid:'M',crosses_junction:true},{aa_index:2,positions:[6,5,4],bases:'AAA',amino_acid:'K'}]}};
assert.deepEqual(m.codonSelection(pmap,{kind:'substitution',query_position:1}).positions,[12,11,7]);
assert.equal(m.codonSelection(pmap,{kind:'deletion',query_position:1}).mode,'flanks');
assert.equal(m.projectEvent({},change),null);
const bp={gene:'PB2',seqid:'x',segment:'PB2',reference_id:'SYN.1:PB2',reference_alignment:'MAC',query_alignment:'MAY',status:'READY',
 changes:[{kind:'substitution',position:3,query_position:3,reference_aa:'C',query_aa:'Y',change:'C3Y',evidence:[]}],
 cds_annotation:{intervals:[[1,4],[9,16]],strand:'+',partial:false,source:'synthetic.vadr.pass.tbl',source_sha256:'synthetic'},
 codon_map:{status:'MAPPED',codons:[{aa_index:1,positions:[1,2,3],bases:'ATG',amino_acid:'M'},
 {aa_index:2,positions:[4,9,10],bases:'GCT',amino_acid:'A',crosses_junction:true},
 {aa_index:3,positions:[11,12,13],bases:'TAT',amino_acid:'Y'},
 {aa_index:4,positions:[14,15,16],bases:'TAA',amino_acid:'*'}]}};
const bs={sample:'mapped',status:'READY',coordinate_schema_version:1,proteins:[bp],segment_sequences:[{seqid:'x',segment:'PB2',sequence:'ATGGAAA ACTTATTAA'.replaceAll(' ',''),length:16}]};

assert.equal(m.segmentRecords({samples:[bs]}).length,1);
let browser=runDom([bs]);
assert(browser['browser-plot'].querySelector('svg'));assert.equal(browser['browser-plot'].querySelectorAll('.lollipop').length,1);
assert.equal(browser['browser-plot'].querySelectorAll('.codon-token').length,3);
browser['browser-plot'].querySelectorAll('.lollipop')[0].listeners.click();assert.match(browser['browser-codon'].textContent,/C3Y/);assert.match(browser['browser-codon'].textContent,/11, 12, 13/);assert.match(browser.detail.textContent,/C3Y/);
browser['browser-plot'].querySelectorAll('.codon-token')[1].listeners.click();assert.match(browser['browser-codon'].textContent,/splice junction/);assert.match(browser['browser-codon'].textContent,/4, 9, 10/);
browser.search.value='absent-change';browser.search.listeners.input();assert.equal(browser['browser-plot'].querySelectorAll('.lollipop').length,0);
browser.search.value='';browser.search.listeners.input();browser['no-samples'].onclick();assert.equal(browser['browser-plot'].querySelectorAll('.lollipop').length,0);
browser['all-samples'].onclick();assert.equal(browser['browser-plot'].querySelectorAll('.lollipop').length,1);
browser['browser-from'].value=1;browser['browser-to'].value=2;browser['browser-zoom'].onclick();assert.equal(browser['browser-plot'].querySelectorAll('.lollipop').length,0);
browser['browser-fit'].onclick();assert.equal(browser['browser-plot'].querySelectorAll('.lollipop').length,1);
assert.deepEqual(m.referenceToQuery({reference_alignment:'MACD',query_alignment:'MA-D'},3),{query_position:2,deleted:true});
assert.equal(m.referenceToQuery({reference_alignment:'MACD',query_alignment:'MA*D'},4),null);
let projected=m.projectEvent(bp,bp.changes[0]);assert.equal(projected.anchor,11);assert(projected.displayCarries);assert(!projected.boundary);
const wt={...bp,query_alignment:'MAC',changes:[],codon_map:{codons:[{aa_index:3,positions:[11,12,13],bases:'TGT',amino_acid:'C'}]}};
projected=m.projectEvent(wt,bp.changes[0]);assert.equal(projected.anchor,11);assert(!projected.displayCarries);assert.match(projected.label,/does not carry/);
const minus={...bp,cds_annotation:{strand:'-'},changes:[{...bp.changes[0],query_position:1}],codon_map:{codons:[{aa_index:1,positions:[20,19,18],bases:'ATG',amino_acid:'M'}]}};
assert.equal(m.projectEvent(minus,minus.changes[0]).anchor,20);
const junction={...bp,changes:[{...bp.changes[0],query_position:1}],codon_map:{codons:[{aa_index:1,positions:[4,100,101],bases:'TAT',amino_acid:'Y'}]}};
assert.equal(m.projectEvent(junction,junction.changes[0]).anchor,4);
const del={...bp,changes:[{kind:'deletion',position:2,query_position:1,reference_aa:'A',query_aa:'-',change:'deletion@2:A'}],codon_map:{codons:[{aa_index:1,positions:[1,2,3],bases:'ATG',amino_acid:'M'},{aa_index:2,positions:[4,5,6],bases:'TGT',amino_acid:'C'}]}};
projected=m.projectEvent(del,del.changes[0]);assert(projected.boundary);assert.equal(projected.anchor,3.5);assert.equal(projected.mode,'flanks');
assert.equal(m.projectEvent({...bp,status:'DISTANT_REFERENCE'},bp.changes[0]),null);
assert.equal(m.projectEvent({...bp,status:'PARTIAL_INTERPRETATION',query_alignment:'MAX'},bp.changes[0]),null);
console.log('PASS: single-canvas lollipops/CDS/codon links; sample filters; zoom; absent-change projection; reverse/joined codons; indel boundaries; withheld and legacy data.');
module.exports={runDom,Element};

const annotated=JSON.parse(JSON.stringify(bs));
annotated.provenance={panel:{references:[{id:bp.reference_id,accession:'NC_007357.1',protein_id:'YP_308664.1',strain:'A/goose/Guangdong/1/1996 (H5N1)',source_url:'https://www.ncbi.nlm.nih.gov/nuccore/NC_007357.1',sequence:'MAC'}]}};
const rrecord=m.segmentRecords({samples:[annotated]})[0];
let refs=m.referenceDetails({samples:[annotated]},rrecord);
assert.equal(refs[0].strain,'A/goose/Guangdong/1/1996 (H5N1)');assert.equal(refs[0].accession,'NC_007357.1');assert.equal(refs[0].proteinId,'YP_308664.1');
let refdom=runDom([annotated]);
assert.match(refdom['comparison-reference'].textContent,/A\/goose\/Guangdong/);assert.match(refdom['comparison-reference'].textContent,/NC_007357.1/);assert.match(refdom['comparison-reference'].textContent,/YP_308664.1/);
assert.equal(refdom['comparison-reference'].querySelectorAll('a').length,2);
const fallback=m.referenceDetails({samples:[bs]},m.segmentRecords({samples:[bs]})[0]);assert.equal(fallback[0].strain,'');assert.equal(fallback[0].accession,'');
assert(m.referenceDetails({demonstration:true,samples:[bs]},m.segmentRecords({samples:[bs]})[0])[0].synthetic);
const other=JSON.parse(JSON.stringify(annotated));other.sample='another';other.provenance.panel.references[0].strain='Another recorded strain';
refdom=runDom([annotated,other]);refdom['browser-record'].value=m.segmentRecords({samples:[other]})[0].key;refdom['browser-record'].listeners.change();assert.match(refdom['comparison-reference'].textContent,/Another recorded strain/);
console.log('PASS: visible reference strain, versioned segment/protein accessions, source links, sample switching, missing metadata and synthetic references.');
// A54T in only one of two samples: preserve the displayed sequence and offer a carrier switch.
const referenceAA='M'+'A'.repeat(59);
function a54Sample(name,alternate){
 const protein=referenceAA.slice(0,53)+(alternate?'T':'A')+referenceAA.slice(54);
 const codons=[...protein].map((amino_acid,i)=>({aa_index:i+1,amino_acid,bases:amino_acid==='M'?'ATG':amino_acid==='T'?'ACT':'GCT',positions:[3*i+1,3*i+2,3*i+3]}));
 const dna=codons.map(c=>c.bases).join('')+'TAA';
 return {sample:name,status:'READY',segment_sequences:[{seqid:'PB2',segment:'PB2',sequence:dna}],provenance:{panel:{references:[{id:'A54.1:PB2',sequence:referenceAA}]}},proteins:[{gene:'PB2',segment:'PB2',seqid:'PB2',status:'READY',reference_id:'A54.1:PB2',reference_alignment:referenceAA,query_alignment:protein,cds_annotation:{intervals:[[1,183]],strand:'+'},codon_map:{status:'MAPPED',codons},changes:alternate?[{position:54,query_position:54,kind:'substitution',reference_aa:'A',query_aa:'T',change:'A54T',evidence:[]}]:[]}]};
}
const aaWT=a54Sample('sample A',false),aaT=a54Sample('sample B',true),originalJSON=JSON.stringify([aaWT,aaT]);
const display=runDom([aaWT,aaT]);
display['browser-record'].value=m.segmentRecords({samples:[aaWT]})[0].key;display['browser-record'].listeners.change();
assert.equal(display['browser-plot'].querySelectorAll('.lollipop').length,0);
display['nav-sample'].value='sample B';display['nav-sample'].listeners.change();
let marker=display['browser-plot'].querySelectorAll('.lollipop')[0];assert(marker);assert.notEqual(marker.querySelector('circle').attrs.fill,'white');
marker.listeners.click();assert.match(display.detail.textContent,/Present in displayed sample/);assert.match(display.detail.textContent,/Displayed amino acid: T/);assert.match(display['browser-codon'].textContent,/ACT → T/);
assert.match(marker.attrs['aria-label'],/1\/2 samples callable at this position/);
display['nav-sample'].value='sample A';display['nav-sample'].listeners.change();assert.equal(display['browser-plot'].querySelectorAll('.lollipop').length,0);
assert.equal(JSON.stringify([aaWT,aaT]),originalJSON);
console.log('PASS: only displayed-sample mutations plotted, sample switching, original cohort denominators and unchanged input data.');
// Compact cohort picker and familiar eight-segment navigator.
const wheelData=runDom([aaWT,aaT]);
assert.equal(wheelData['constellation-wheel'].querySelectorAll('.constellation-wedge').length,8);
assert.match(wheelData['cohort-count'].textContent,/2 \/ 2/);
wheelData['sample-search'].value='sample B';wheelData['sample-search'].listeners.input();assert.equal(wheelData.samples.children.length,1);assert.match(wheelData.samples.textContent,/sample B/);
wheelData.samples.children[0].children[0].checked=false;wheelData.samples.children[0].children[0].listeners.change();assert.match(wheelData['cohort-count'].textContent,/1 \/ 2/);
wheelData['all-samples'].onclick();assert.match(wheelData['cohort-count'].textContent,/2 \/ 2/);
let wedges=wheelData['constellation-wheel'].querySelectorAll('.constellation-wedge');wedges[7].listeners.click();
assert.equal(wheelData['browser-plot'].querySelector('svg'),null);assert.match(wheelData['segment-summary'].textContent,/NS/);assert.match(wheelData['browser-message'].textContent,/No recorded protein entries/);
wheelData['constellation-wheel'].querySelectorAll('.constellation-wedge')[0].listeners.click();assert(wheelData['browser-plot'].querySelector('svg'));
wheelData['nav-sample'].value='sample A';wheelData['nav-sample'].listeners.change();assert.match(wheelData['reference-note'].textContent,/sample A/);assert.match(wheelData['browser-message'].textContent,/sample A/);
const states=m.constellationState({samples:[aaWT]},aaWT.sample);assert.equal(states.length,8);assert.equal(states[0].state,'assessed');assert.equal(states[1].state,'no-data');
const partial=JSON.parse(JSON.stringify(aaWT));partial.proteins[0].status='PARTIAL_INTERPRETATION';assert.equal(m.constellationState({samples:[partial]},partial.sample)[0].state,'review');
assert.match(m.wheelArc(160,160,88,148,0,.7),/^M /);
assert.equal(JSON.stringify([aaWT,aaT]),originalJSON);
console.log('PASS: eight wedges, assessment-only states, navigation, missing-segment handling, sample search, selection count and preserved calls.');

const popup=runDom([aaWT,aaT]);assert(!popup['mutation-dialog'].open);assert(!Object.hasOwn(popup,'protein'));
popup['browser-plot'].querySelectorAll('.lollipop')[0].listeners.click();assert(popup['mutation-dialog'].open);assert.match(popup.detail.textContent,/A54T/);
popup['close-mutation-dialog'].listeners.click();assert(!popup['mutation-dialog'].open);assert(popup['segment-browser'].focused);
assert.match(popup['segment-summary'].textContent,/recorded protein entries/);
assert.match(popup['constellation-wheel'].querySelectorAll('.constellation-wedge')[0].attrs['aria-label'],/Show PB2 proteins/);
const oldProteinOnly=JSON.parse(JSON.stringify(aaWT));delete oldProteinOnly.segment_sequences;
assert.equal(m.constellationState({samples:[oldProteinOnly]},oldProteinOnly.sample)[0].state,'assessed');
console.log('PASS: no redundant dropdown, details initially closed, click-to-open/close focus behavior and clear comparison-completeness labels.');

// Independent amino acid axes; a shared DNA coordinate must not place markers.
const axis=runDom([aaWT,aaT]);
let aMarker=axis['browser-plot'].querySelectorAll('.lollipop')[0];
assert.equal(aMarker.attrs['data-aa-position'],'54');
assert.match(aMarker.attrs['aria-label'],/reference amino acid 54/);
assert.equal(axis['browser-to'].value,'60'); // 183-nt DNA is never the plot extent.
assert.equal(axis['browser-plot'].querySelectorAll('.protein-track')[0].attrs['data-to-aa'],'60');
axis['browser-bases'].onclick();assert(axis['browser-plot'].querySelectorAll('.codon-token').length>0);
assert(!axis['browser-plot'].textContent.includes('nucleotide axis'));
const plain=JSON.parse(JSON.stringify(aaT));delete plain.segment_sequences;delete plain.proteins[0].codon_map;delete plain.proteins[0].cds_annotation;
const plainDOM=runDom([plain]);assert.equal(plainDOM['browser-plot'].querySelectorAll('.lollipop').length,1);
plainDOM['browser-plot'].querySelectorAll('.lollipop')[0].listeners.click();assert.match(plainDOM['browser-codon'].textContent,/No reliable codon map/);
// Overlapping/spliced proteins each span their own reference, not the nucleotide segment.
const multi=JSON.parse(JSON.stringify(aaT));multi.segment_sequences[0].segment='NS';
multi.proteins[0].gene='NS1';multi.proteins[0].segment='NS';
const short=JSON.parse(JSON.stringify(multi.proteins[0]));short.gene='NEP';short.reference_id='NEP.1';short.reference_alignment='M'+'A'.repeat(19);short.query_alignment='M'+'A'.repeat(19);short.changes=[];short.codon_map.codons=short.codon_map.codons.slice(0,20);
multi.proteins.push(short);const md=runDom([multi]);
assert.equal(md['browser-plot'].querySelectorAll('.protein-track').length,2);
assert.deepEqual(md['browser-plot'].querySelectorAll('.protein-track').map(e=>e.attrs['data-to-aa']),['60','20']);
const partial2=JSON.parse(JSON.stringify(multi));partial2.proteins[1].status='CDS_REVIEW_REQUIRED';partial2.proteins[1].issues=['PARTIAL_CDS','TERMINAL_STOP_MISSING'];
const rd=runDom([partial2]);assert.match(rd['browser-source'].textContent,/NEP/);assert.match(rd['browser-source'].textContent,/coding sequence is incomplete/);assert.match(rd['browser-source'].textContent,/terminal stop codon is missing/);
assert(!rd['segment-summary'].textContent.includes('Partial comparison'));
assert.equal(m.proteinReasons({status:'DISTANT_REFERENCE'})[0],'The alignment did not meet the configured identity or coverage threshold for a reliable comparison.');
console.log('PASS: reference AA54 placement, independent protein lengths, protein-only legacy results, per-protein reasons and nucleotide details on demand.');

// Unavailable proteins do not reserve SVG row height or duplicate their notices.
const compact=JSON.parse(JSON.stringify(multi));compact.proteins.forEach(p=>{p.status='DISTANT_REFERENCE';p.identity=.66;p.coverage=1;});
const compactDOM=runDom([compact]);assert.equal(compactDOM['browser-plot'].querySelector('svg'),null);assert(compactDOM['download-svg'].disabled);assert(!Object.hasOwn(compactDOM,'plot-footnote'));
assert.equal(compactDOM['browser-source'].children.length,2);assert.match(compactDOM['browser-source'].textContent,/66% identity/);
assert.match(compactDOM['browser-source'].textContent,/aa reference/);
const mixedDOM=runDom([partial2]);assert.equal(mixedDOM['browser-plot'].querySelectorAll('.protein-track').length,1);
assert.equal(mixedDOM['browser-plot'].querySelectorAll('.protein-row').length,1);assert(Number(mixedDOM['browser-plot'].querySelector('svg').attrs.viewBox.split(' ')[3])<520);
assert.equal(mixedDOM['browser-plot'].textContent.includes('Mutation calls unavailable'),false);
const navPaths=compactDOM['constellation-wheel'].querySelectorAll('.constellation-wedge').map(w=>w.querySelector('path'));
assert(navPaths.some(p=>p.attrs.fill==='#747474'));assert(navPaths.every(p=>['#747474','#8c193e'].includes(p.attrs.fill)));
compactDOM['nav-sample'].value=compact.sample;compactDOM['nav-sample'].listeners.change();assert.equal(compactDOM['browser-plot'].querySelector('svg'),null);
console.log('PASS: no empty SVG for unavailable proteins, mixed-track height, compact reference notices and exact #747474 wheel gray.');

// Ambiguous repeat positions never inflate denominators or claim codon coordinates.
const resolved=JSON.parse(JSON.stringify(aaT));
resolved.proteins[0].status='PARTIAL_INTERPRETATION';resolved.proteins[0].alignment_resolution={method:'all_optimal_paths',ambiguous:true,uncertain_reference_positions:[2,3,4],uncertain_insertion_anchors:[2,3],callable_reference_positions:Array.from({length:60},(_,i)=>i+1).filter(i=>i<2||i>4),callable_insertion_anchors:[0,1,5,6,53,54,55,60]};
assert.equal(m.callablePosition(resolved.proteins[0],3),false);assert.equal(m.referenceToQuery(resolved.proteins[0],3),null);
assert.equal(m.callablePosition(resolved.proteins[0],54),true);assert.equal(m.callableEvent(resolved.proteins[0],{kind:'insertion',position:3},60),false);
assert.equal(m.positionRanges([7,3,2,1,6,7]),'1–3, 6–7');
const ud=runDom([resolved]);assert.equal(ud['browser-plot'].querySelectorAll('.lollipop').length,1);assert.equal(ud['browser-plot'].querySelectorAll('.uncertain-position').length,3);
assert.match(ud['browser-source'].textContent,/Some positions are uncertain/);assert.match(ud['browser-source'].textContent,/2–4/);assert.equal(ud['alignment-key'].hidden,false);
const maskedWT=JSON.parse(JSON.stringify(aaWT));maskedWT.proteins[0].alignment_resolution={callable_reference_positions:[1,2],callable_insertion_anchors:[0,1]};
const eg=m.events(m.groups({samples:[aaT,maskedWT]})[0],new Set(['sample A','sample B']))[0];assert.equal(eg.denominator,1);
assert.match(m.proteinReasons({status:'AMBIGUOUS_ALIGNMENT'})[0],/older result/);
console.log('PASS: recovered calls, uncertainty shading/messages, masked denominators and suppressed uncertain codon mapping.');

// Reference-specific HA regions, clipped by zoom and absent for unrelated references.
const ha=JSON.parse(JSON.stringify(aaT)),haReference='M'+'A'.repeat(567);
ha.sample='HA sample';ha.segment_sequences[0].segment='HA';ha.proteins[0].gene='HA';ha.proteins[0].segment='HA';
ha.proteins[0].reference_id='NC_007362.1:HA';ha.proteins[0].reference_accession='NC_007362.1';ha.proteins[0].reference_protein_id='YP_308669.1';
ha.proteins[0].reference_alignment=haReference;ha.proteins[0].query_alignment=haReference;
ha.provenance.panel.references=[{id:'NC_007362.1:HA',accession:'NC_007362.1',protein_id:'YP_308669.1',sequence:haReference}];
let hd=runDom([ha]);let regions=hd['browser-plot'].querySelectorAll('.ha-region');assert.equal(regions.length,3);
assert.deepEqual(regions.map(r=>[r.attrs['data-region'],r.attrs['data-start'],r.attrs['data-end']]),[['Signal peptide','1','16'],['HA1','17','346'],['HA2','347','568']]);
hd['browser-from'].value=340;hd['browser-to'].value=355;hd['browser-zoom'].onclick();regions=hd['browser-plot'].querySelectorAll('.ha-region');assert.equal(regions.length,2);assert(regions.every(r=>r.querySelector('rect').attrs.width>0));
hd['browser-from'].value=1;hd['browser-to'].value=16;hd['browser-zoom'].onclick();assert.equal(hd['browser-plot'].querySelectorAll('.ha-region').length,1);assert.match(hd['browser-plot'].querySelectorAll('.ha-region')[0].textContent,/Signal peptide/);
assert(!Object.hasOwn(hd,'annotation-source'));assert(!Object.hasOwn(hd,'provenance'));
const unrecognized=JSON.parse(JSON.stringify(ha));unrecognized.provenance.panel.references[0].protein_id='OTHER.1';assert.equal(runDom([unrecognized])['browser-plot'].querySelectorAll('.ha-region').length,0);
const mismatched=JSON.parse(JSON.stringify(ha));mismatched.proteins[0].reference_alignment='M'+'G'.repeat(567);assert.equal(runDom([mismatched])['browser-plot'].querySelectorAll('.ha-region').length,0);
assert.equal(m.proteinRegions({samples:[aaT]},m.segmentRecords({samples:[aaT]})[0],aaT.proteins[0]).length,0);
assert.equal(ha.proteins[0].changes[0].position,54);
console.log('PASS: pinned HA precursor regions, version and sequence guards, source links, zoom clipping and preserved mutation numbering.');

// All HA changes follow reference-region colors, including boundary residues.
const colored=JSON.parse(JSON.stringify(ha));
colored.proteins[0].changes=[1,16,17,346,347,568].map(position=>({position,query_position:position,kind:'substitution',reference_aa:'A',query_aa:'T',change:'A'+position+'T',evidence:[]}));
const cd=runDom([colored]),marks=cd['browser-plot'].querySelectorAll('.lollipop');
assert.equal(marks.length,6);assert.deepEqual(marks.map(g=>g.querySelector('circle').attrs.fill),['#4AB7C4','#4AB7C4','#8C1D40','#8C1D40','#FFC627','#FFC627']);
assert.deepEqual(marks.map(g=>g.querySelector('path').attrs.stroke),['#4AB7C4','#4AB7C4','#8C1D40','#8C1D40','#FFC627','#FFC627']);
assert.deepEqual(cd['browser-plot'].querySelectorAll('.ha-region').map(g=>g.querySelector('rect').attrs.fill),['#4AB7C4','#8C1D40','#FFC627']);
assert.match(cd['mutation-color-key'].textContent,/Signal peptide/);assert.match(cd['mutation-color-key'].textContent,/HA2/);assert(!cd['mutation-color-key'].textContent.includes('substitution'));
assert(runDom([aaT])['mutation-color-key'].textContent.includes('substitution'));
console.log('PASS: exact region colors for stems/heads/bars, boundary assignment, adaptive legend and non-HA type-color preservation.');

// Tight bounds follow visible rows; empty mutation views do not reserve stem/label height.
const fitted=runDom([colored]);const fullHeight=Number(fitted['browser-plot'].querySelector('svg').attrs.viewBox.split(' ')[3]);
fitted.search.value='no-such-change';fitted.search.listeners.input();const emptyHeight=Number(fitted['browser-plot'].querySelector('svg').attrs.viewBox.split(' ')[3]);
assert(emptyHeight<fullHeight);assert(emptyHeight<220);assert.equal(fitted['browser-plot'].querySelectorAll('.ha-region').length,3);
assert(fitted['browser-plot'].querySelectorAll('.protein-row')[0].attrs.transform);
fitted.search.value='';fitted.search.listeners.input();assert.equal(Number(fitted['browser-plot'].querySelector('svg').attrs.viewBox.split(' ')[3]),fullHeight);
console.log('PASS: compact visible bounds, shorter zero-marker view, restored filtered view and retained HA region labels.');

const annotatedHA=JSON.parse(JSON.stringify(ha)),newRef=annotatedHA.provenance.panel.references[0];
newRef.id='NC_999999.1:HA';newRef.accession='NC_999999.1';newRef.protein_id='TEST_HA.1';
newRef.reference_regions=[{name:'Signal peptide',short:'SP',start:1,end:20,color:'#4AB7C4'},{name:'HA1',short:'HA1',start:21,end:350,color:'#8C1D40'},{name:'HA2',short:'HA2',start:351,end:568,color:'#FFC627'}];
newRef.region_sources=[{label:'Synthetic selected-reference annotation',url:'https://example.org/synthetic'}];annotatedHA.proteins[0].reference_id=newRef.id;
const nr=runDom([annotatedHA]);assert.deepEqual(nr['browser-plot'].querySelectorAll('.ha-region').map(g=>g.attrs['data-start']),['1','21','351']);
assert.match(nr['browser-plot'].textContent,/HA1 21–350/);assert.equal(newRef.region_sources[0].label,'Synthetic selected-reference annotation');
assert(!nr['browser-plot'].textContent.includes('YP_308669.1 precursor'));
console.log('PASS: selected-reference HA annotations and sources replace pinned coordinates when explicitly recorded.');

// Matrix products retain independent AA axes and share only the sample nucleotide overview.
const matrix={sample:'matrix synthetic',segment_sequences:[{seqid:'mp',segment:'MP',sequence:'ATGCCCGAGTAA'}],proteins:[
 {seqid:'mp',gene:'M1',segment:'MP',status:'READY',reference_id:'SYN.1:M1',reference_alignment:'MPD',query_alignment:'MPE',changes:[{kind:'substitution',position:3,query_position:3,reference_aa:'D',query_aa:'E',change:'D3E',evidence:[]}],cds_annotation:{intervals:[[1,12]],strand:'+'}},
 {seqid:'mp',gene:'M2',segment:'MP',status:'READY',reference_id:'SYN.1:M2',reference_alignment:'MD',query_alignment:'ME',changes:[{kind:'substitution',position:2,query_position:2,reference_aa:'D',query_aa:'E',change:'D2E',evidence:[]}],cds_annotation:{intervals:[[1,3],[7,12]],strand:'+'}}]};
const mx=runDom([matrix]);assert.equal(mx['browser-plot'].querySelectorAll('.matrix-cds-overview').length,1);
assert.equal(mx['browser-plot'].querySelectorAll('.matrix-cds-block').length,3);assert.equal(mx['browser-plot'].querySelectorAll('.matrix-splice').length,1);
assert.deepEqual(mx['browser-plot'].querySelectorAll('.protein-track').map(t=>t.attrs['data-to-aa']),['3','2']);
assert.deepEqual(mx['browser-plot'].querySelectorAll('.lollipop').map(g=>g.querySelector('circle').attrs.fill),['#8C1D40','#FFC627']);
assert.match(mx['mutation-color-key'].textContent,/M1M2/);assert.match(mx['browser-plot'].textContent,/Sample nucleotide positions/);
const mr=m.segmentRecords({samples:[matrix]})[0];assert.equal(m.matrixCdsRecords(mr).length,2);
const invalidMatrix=JSON.parse(JSON.stringify(mr));invalidMatrix.proteins[1].cds_annotation.intervals=[[1,99]];assert.equal(m.matrixCdsRecords(invalidMatrix).length,1);
const noMatrixCds=JSON.parse(JSON.stringify(matrix));noMatrixCds.proteins.forEach(p=>delete p.cds_annotation);const nm=runDom([noMatrixCds]);assert.equal(nm['browser-plot'].querySelectorAll('.matrix-cds-overview').length,0);assert.equal(nm['browser-plot'].querySelectorAll('.protein-track').length,2);
const reversedMatrix=JSON.parse(JSON.stringify(mr));reversedMatrix.proteins[1].cds_annotation.intervals=[[12,10],[6,1]];assert.equal(m.matrixCdsRecords(reversedMatrix)[1].strand,'-');
console.log('PASS: M1/M2 CDS blocks, splice connector, independent AA scales, matched protein colors, reverse strand and missing/invalid-coordinate guards.');

// The same coordinate-safe layout supports NS1/NEP and recorded accessory products.
const ns=JSON.parse(JSON.stringify(matrix));ns.sample='NS synthetic';ns.segment_sequences[0].segment='NS';ns.proteins[0].gene='NS1';ns.proteins[1].gene='NEP';ns.proteins.forEach(p=>p.segment='NS');
let nsd=runDom([ns]);assert.equal(nsd['browser-plot'].querySelectorAll('.segment-cds-overview').length,1);assert.match(nsd['browser-plot'].textContent,/NS segment · CDS/);
assert.equal(nsd['browser-plot'].querySelectorAll('.segment-cds-block').length,3);assert.equal(nsd['browser-plot'].querySelectorAll('.segment-splice').length,1);assert.match(nsd['browser-plot'].textContent,/NEP \(NS2\) CDS/);
assert.deepEqual(nsd['browser-plot'].querySelectorAll('.protein-track').map(p=>p.attrs['data-to-aa']),['3','2']);assert.deepEqual(nsd['browser-plot'].querySelectorAll('.lollipop').map(g=>g.querySelector('circle').attrs.fill),['#8C1D40','#FFC627']);
assert.match(nsd['mutation-color-key'].textContent,/NS1NEP \(NS2\)/);
const alias=JSON.parse(JSON.stringify(ns));alias.proteins[1].gene='NS2';assert.equal(m.cdsTrackRecords(m.segmentRecords({samples:[alias]})[0])[1].gene,'NEP');
for(const [segment,primary,accessory]of [['PB1','PB1','PB1-F2'],['PA','PA','PA-X']]){
 const record=JSON.parse(JSON.stringify(ns));record.segment_sequences[0].segment=segment;record.proteins[0].gene=primary;record.proteins[1].gene=accessory;record.proteins.forEach(p=>p.segment=segment);
 const d=runDom([record]);assert.equal(d['browser-plot'].querySelectorAll('.segment-cds-block').length,3);assert(d['browser-plot'].textContent.includes(accessory+' CDS'));
 const missing=JSON.parse(JSON.stringify(record));missing.proteins.pop();assert.equal(runDom([missing])['browser-plot'].querySelectorAll('.segment-cds-block').length,1);
}
assert.equal(JSON.stringify(ns.proteins[1].cds_annotation.intervals),JSON.stringify([[1,3],[7,12]]));
console.log('PASS: NS1/NEP spliced tracks, NS2 alias, accessory product annotations only when recorded, independent AA scales and preserved coordinates.');

// New report defaults: All samples, >=80% of the entire selected cohort.
const cohortTen=Array.from({length:10},(_,i)=>a54Sample('cohort '+i,i<8)),cohortOriginal=JSON.stringify(cohortTen);
let cv=runDom(cohortTen,{defaults:true});assert.equal(cv.frequency.value,'80');assert.equal(cv['nav-sample'].value,m.ALL_SAMPLES);assert.equal(cv['nav-sample'].children[0].textContent,'All samples');
assert.equal(cv['browser-plot'].querySelectorAll('.lollipop').length,1);assert.match(cv['browser-plot'].textContent,/8\/10/);assert(!cv['reference-note'].textContent.includes('consensus'));
cv['browser-plot'].querySelectorAll('.lollipop')[0].listeners.click();assert.match(cv.detail.textContent,/8 \/ 10 selected samples/);assert.match(cv['browser-codon'].textContent,/Select an individual sample/);
cv.frequency.value='90';cv.frequency.listeners.input();assert.equal(cv['browser-plot'].querySelectorAll('.lollipop').length,0);assert.match(cv['browser-message'].textContent,/1 before frequency filter/);
cv.frequency.value='0';cv.frequency.listeners.input();assert.equal(cv['browser-plot'].querySelectorAll('.lollipop').length,1);
cv['nav-sample'].value='cohort 9';cv['nav-sample'].listeners.change();assert.equal(cv['browser-plot'].querySelectorAll('.lollipop').length,0);
cv['nav-sample'].value=m.ALL_SAMPLES;cv['nav-sample'].listeners.change();assert.equal(cv['browser-plot'].querySelectorAll('.lollipop').length,1);
assert.equal(JSON.stringify(cohortTen),cohortOriginal);
assert(m.passesFrequency({n:24},new Set(Array.from({length:30},(_,i)=>i)),80));assert(!m.passesFrequency({n:23},new Set(Array.from({length:30},(_,i)=>i)),80));
const rare=runDom([aaWT,aaT],{defaults:true});assert.equal(rare['browser-plot'].querySelectorAll('.lollipop').length,0);rare.frequency.value='0';rare.frequency.listeners.input();assert.equal(rare['browser-plot'].querySelectorAll('.lollipop').length,1);
rare['no-samples'].onclick();assert.equal(rare['browser-plot'].querySelector('svg'),null);assert.match(rare['browser-message'].textContent,/Select comparison samples/);
console.log('PASS: All samples default, 80% cutoff, exact 24/30 boundary, lower-frequency inspection, mode switching, empty selections and preserved cohort data.');
