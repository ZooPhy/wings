#!/usr/bin/env python3
"""WINGS consensus protein comparisons, schema 1. Standard-library only."""
import argparse
from array import array
import csv
from datetime import datetime, timezone
import hashlib
from functools import lru_cache
import html
import io
import json
from pathlib import Path
import re
import urllib.request

VERSION = '1.3.0'
SEGMENTS = {'NC_007357.1':'PB2','NC_007358.1':'PB1','NC_007359.1':'PA',
            'NC_007360.1':'NP','NC_007361.1':'NA','NC_007362.1':'HA',
            'NC_007363.1':'MP','NC_007364.1':'NS'}
PRODUCTS = {'polymerase pb2':'PB2','pb2 protein':'PB2','polymerase pb1':'PB1',
 'pb1 protein':'PB1','pb1-f2 protein':'PB1-F2','polymerase pa':'PA','pa protein':'PA',
 'polymerase basic protein 2':'PB2','polymerase basic protein 1':'PB1',
 'polymerase acidic protein':'PA','non-structural protein 1':'NS1','non-structural protein 2':'NEP',
 'pa-x protein':'PA-X','hemagglutinin':'HA','nucleoprotein':'NP','neuraminidase':'NA',
 'matrix protein 1':'M1','matrix protein 2':'M2','m1 protein':'M1','m2 protein':'M2',
 'nonstructural protein 1':'NS1','nonstructural protein 2':'NEP',
 'nuclear export protein':'NEP','ns1 protein':'NS1','ns2 protein':'NEP'}
GENES = {'PB2','PB1','PB1-F2','PA','PA-X','HA','NP','NA','M1','M2','NS1','NEP'}
AA = set('ACDEFGHIKLMNPQRSTVWY')
CODE = dict(zip((a+b+c for a in 'TCAG' for b in 'TCAG' for c in 'TCAG'),
 'FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG'))
COMPLEMENT = str.maketrans('ACGTRYSWKMBDHVN','TGCAYRSWMKVHDBN')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n');temp.replace(path)

def fasta(text):
    records={};name=None
    for line in text.splitlines():
        if line.startswith('>'):
            name=line[1:].strip()
            if not name or name in records:raise ValueError('Empty/duplicate FASTA header')
            records[name]=''
        elif line.strip():
            if name is None:raise ValueError('FASTA sequence before header')
            records[name]+=line.strip().upper()
    return records

def gene_name(q):
    product=q.get('product',[''])[0].lower().strip()
    # Product disambiguates M1/M2 and NS1/NEP, whose gene qualifier may be shared.
    if product in PRODUCTS:return PRODUCTS[product]
    if product.upper() in GENES:return product.upper()
    g=q.get('gene',[''])[0].upper().replace('NS2','NEP')
    if g in GENES:return g
    return None

def features(text):
    """NCBI five-column table; coordinates retained in biological order."""
    seqid=None;current=None;result=[]
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'):continue
        if line.startswith('>Feature '):
            seqid=line.split()[1];current=None;continue
        if line.startswith('['):raise ValueError('Feature-table offsets are not supported')
        fields=line.split('\t');fields+=['']*(5-len(fields))
        a,b,key,qual,value=fields[:5]
        if a and b:
            if not seqid:raise ValueError('Missing >Feature header')
            if key:
                current={'seqid':seqid,'key':key,'intervals':[],'qualifiers':{},'partial':False}
                result.append(current)
            if current is None:raise ValueError('Orphan feature interval')
            if not re.fullmatch(r'[<>]?\d+',a) or not re.fullmatch(r'[<>]?\d+',b):
                raise ValueError('Unsupported feature coordinate')
            current['partial'] |= a.startswith(('<','>')) or b.startswith(('<','>'))
            current['intervals'].append((int(a.lstrip('<>')),int(b.lstrip('<>'))))
        elif qual:
            if current is None:raise ValueError('Orphan qualifier')
            current['qualifiers'].setdefault(qual,[]).append(value)
    return [x for x in result if x['key']=='CDS']

def translate_feature(sequence, feature):
    q=feature['qualifiers'];issues=[]
    if feature['partial']:issues.append('PARTIAL_CDS')
    if any(k in q for k in ('exception','transl_except','ribosomal_slippage','pseudo','pseudogene')):
        issues.append('UNSUPPORTED_TRANSLATION_EXCEPTION')
    if q.get('transl_table',['1'])[0]!='1':issues.append('UNSUPPORTED_GENETIC_CODE')
    start=int(q.get('codon_start',['1'])[0])
    if start not in (1,2,3):raise ValueError('Invalid codon_start')
    if start!=1:issues.append('PARTIAL_READING_FRAME')
    intervals=feature['intervals'];used=set();strands=set();pieces=[]
    for a,b in intervals:
        if min(a,b)<1 or max(a,b)>len(sequence):raise ValueError('CDS outside sequence')
        strands.add(a<=b)
        positions=set(range(min(a,b),max(a,b)+1))
        if positions & used:issues.append('OVERLAPPING_CDS_INTERVALS')
        used |= positions
        s=sequence[min(a,b)-1:max(a,b)]
        pieces.append(s if a<=b else s.translate(COMPLEMENT)[::-1])
    if len(strands)!=1:raise ValueError('Mixed-strand CDS')
    dna=''.join(pieces)[start-1:]
    if len(dna)%3:issues.append('INCOMPLETE_CODON_OR_FRAMESHIFT')
    protein=''.join(CODE.get(dna[i:i+3],'X') for i in range(0,len(dna)-2,3))
    if not protein.startswith('M'):issues.append('START_CODON_REVIEW')
    if not protein.endswith('*'):issues.append('TERMINAL_STOP_MISSING')
    protein=protein[:-1] if protein.endswith('*') else protein
    if 'X' in protein:issues.append('AMBIGUOUS_RESIDUES')
    if '*' in protein:issues.append('PREMATURE_STOP')
    return protein,sorted(set(issues))

@lru_cache(maxsize=32)
def alignment_resolution(reference, query):
    """Global affine-gap alignment. Track nonunique optimal paths conservatively."""
    n,m=len(reference),len(query)
    if not n or not m or max(n,m)>2500:raise ValueError('Protein length outside 1..2500')
    width=m+1;size=(n+1)*width;neg=-10**8
    scores=[array('i',[neg])*size for _ in range(3)]
    traces=[bytearray(size) for _ in range(3)];ways=[bytearray(size) for _ in range(3)]
    scores[0][0]=0;ways[0][0]=1
    for i in range(n+1):
        for j in range(m+1):
            if i==j==0:continue
            k=i*width+j
            for state in range(3):
                if state==0:
                    if not i or not j:continue
                    prev=k-width-1;cost=2 if reference[i-1]==query[j-1] else -3
                    candidates=[s[prev]+cost for s in scores]
                elif state==1:
                    if not i:continue
                    prev=k-width;candidates=[scores[0][prev]-8,scores[1][prev]-1,neg]
                else:
                    if not j:continue
                    prev=k-1;candidates=[scores[0][prev]-8,neg,scores[2][prev]-1]
                best=max(candidates);scores[state][k]=best
                choices=[x for x in range(3) if candidates[x]==best and ways[x][prev]]
                if choices:
                    traces[state][k]=sum(1 << choice for choice in choices)
                    ways[state][k]=min(2,sum(ways[x][prev] for x in choices))
    k=size-1;best=max(s[k] for s in scores);states=[x for x in range(3) if scores[x][k]==best]
    ambiguous=sum(ways[x][k] for x in states)>1
    state=states[0];i=n;j=m;a=[];b=[]
    while i or j:
        k=i*width+j;mask=traces[state][k];previous=(mask & -mask).bit_length()-1
        if state==0:a.append(reference[i-1]);b.append(query[j-1]);i-=1;j-=1
        elif state==1:a.append(reference[i-1]);b.append('-');i-=1
        else:a.append('-');b.append(query[j-1]);j-=1
        state=previous
    # Traverse the entire optimal traceback DAG, without enumerating paths.
    # A residue is safe only if every optimal path maps it to the same query index.
    ref_map=array('i',[-1])*(n+1);query_map=array('i',[-1])*(m+1)
    seen=bytearray(size);stack=[];insertions=[]
    def push(state,k):
        bit=1 << state
        if not seen[k] & bit:seen[k]|=bit;stack.append((state,k))
    def record(mapping,index,value):
        if mapping[index]==-1:mapping[index]=value
        elif mapping[index]!=value:mapping[index]=-2
    for state in states:push(state,size-1)
    while stack:
        state,k=stack.pop();i,j=divmod(k,width)
        if k==0:continue
        if state==0:
            record(ref_map,i,2*j);record(query_map,j,2*i);prev=k-width-1
        elif state==1:
            record(ref_map,i,2*j+1);prev=k-width
        else:
            record(query_map,j,2*i+1);insertions.append((i,j));prev=k-1
        mask=traces[state][k]
        for previous in range(3):
            if mask & (1 << previous):push(previous,prev)
    uncertain=[i for i in range(1,n+1) if ref_map[i]==-2]
    uncertain_anchors=sorted({i for i,j in insertions if query_map[j]!=2*i+1})
    first_stop=query.find('*')+1 or m+1
    callable_positions=[]
    for i in range(1,n+1):
        value=ref_map[i]
        if value<0:continue
        j,deleted=divmod(value,2)
        if deleted:
            if j<first_stop:callable_positions.append(i)
        elif j<=first_stop and query[j-1]!='X' and reference[i-1]!='X':callable_positions.append(i)
    callable_set=set(callable_positions);uncertain_anchor_set=set(uncertain_anchors)
    callable_anchors=[i for i in range(n+1) if i not in uncertain_anchor_set and
                      (i==0 or i in callable_set) and (i==n or i+1 in callable_set)]
    resolution={'method':'all_optimal_paths','ambiguous':ambiguous,
                'uncertain_reference_positions':uncertain,'uncertain_insertion_anchors':uncertain_anchors,
                'callable_reference_positions':callable_positions,'callable_insertion_anchors':callable_anchors}
    return ''.join(reversed(a)),''.join(reversed(b)),best,ambiguous,resolution


def align(reference,query):
    return alignment_resolution(reference,query)[:4]

def compare(reference,query):
    a,b,score,ambiguous,resolution=alignment_resolution(reference,query)
    paired=sum(x!='-' and y!='-' for x,y in zip(a,b))
    valid=sum(x in AA and y in AA for x,y in zip(a,b))
    identity=sum(x==y and x in AA for x,y in zip(a,b))/max(1,valid)
    coverage=paired/len(reference)
    changes=[];r=q=0;stop=False
    for x,y in zip(a,b):
        r+=x!='-';q+=y!='-'
        if not stop and x!=y and x!='X' and y!='X':
            kind='insertion' if x=='-' else 'deletion' if y=='-' else 'stop_gain' if y=='*' else 'substitution'
            changes.append({'position':r,'query_position':q,'reference_aa':x,'query_aa':y,
                            'kind':kind,'change':f'{x}{r}{y}' if kind in ('substitution','stop_gain') else f'{kind}@{r}:{y if x=="-" else x}'})
        if y=='*':stop=True
    callable_set=set(resolution['callable_reference_positions']);callable_anchors=set(resolution['callable_insertion_anchors'])
    # Stable query indices are required as well as stable reference numbering.
    changes=[c for c in changes if c['position'] in (callable_anchors if c['kind']=='insertion' else callable_set)]
    return {'reference_alignment':a,'query_alignment':b,'score':score,'ambiguous_alignment':ambiguous,
            'identity':identity,'coverage':coverage,'changes':changes,'alignment_resolution':resolution}

def panel_check(panel):
    if panel.get('schema_version')!=1 or not panel.get('references'):raise ValueError('Invalid/empty reference panel')
    ids=set()
    for r in panel['references']:
        for key in ('id','accession','protein_id','segment','gene','sequence','source_url'):
            if not r.get(key):raise ValueError('Reference missing '+key)
        if r['id'] in ids:raise ValueError('Duplicate reference ID')
        ids.add(r['id'])
        if r['gene'] not in GENES or r['segment'] not in set(SEGMENTS.values()):raise ValueError('Unknown reference gene/segment')
        if not set(r['sequence'])<=AA:raise ValueError('Reference contains ambiguous amino acids')
        if not re.search(r'\.\d+$',r['accession']):raise ValueError('Reference accession must be versioned')
    return panel

def prepare(args):
    target=Path(args.output)
    if target.exists() and not args.replace:
        panel_check(json.loads(target.read_text()));print('Existing validated panel retained:',target);return
    if args.fasta:
        text=Path(args.fasta).read_text();source='local NCBI CDS FASTA'
    else:
        url=('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id='+
             ','.join(SEGMENTS)+'&rettype=fasta_cds_aa&retmode=text&tool=WINGS')
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'WINGS-amino-acids/1.0'}),timeout=60) as response:
            text=response.read(2000000).decode()
        source=url
    refs=[];seen=set()
    for header,protein in fasta(text).items():
        matches=[x for x in SEGMENTS if re.search(re.escape(x)+r'(?![0-9])',header)]
        if len(matches)!=1:raise ValueError('Unexpected/unversioned accession in downloaded FASTA')
        accession=matches[0];seen.add(accession)
        quals={k:[v] for k,v in re.findall(r'\[([^=\]]+)=([^\]]*)\]',header)}
        if 'protein' in quals and 'product' not in quals:quals['product']=quals['protein']
        gene=gene_name(quals)
        if not gene:continue
        pid=quals.get('protein_id',[''])[0]
        refs.append({'id':accession+':'+gene,'accession':accession,'protein_id':pid,
            'segment':SEGMENTS[accession],'gene':gene,'sequence':protein.rstrip('*'),
            'strain':'A/goose/Guangdong/1/1996 (H5N1)',
            'source_url':'https://www.ncbi.nlm.nih.gov/nuccore/'+accession,
            'numbering':'full-length reference protein, 1-based; includes signal peptide where present'})
    if seen!=set(SEGMENTS):raise ValueError('Incomplete download: all eight pinned segments required')
    if {r['segment'] for r in refs}!=set(SEGMENTS.values()):raise ValueError('No recognized reference protein for one or more segments')
    panel={'schema_version':1,'panel_name':'GsGd-H5N1-1996-v1','references':refs,'retrieved_at':datetime.now(timezone.utc).isoformat(),
           'source':source,'source_sha256':hashlib.sha256(text.encode()).hexdigest()}
    panel_check(panel);write_json(target,panel);print('Prepared',len(refs),'reference proteins:',target)

def evidence_check(data,panel):
    if data.get('schema_version')!=1:raise ValueError('Invalid evidence schema')
    refs={r['id']:r for r in panel['references']}
    for row in data['entries']:
        if not row.get('citation_url','').startswith('https://') or not row.get('study_context') or not row.get('statement'):
            raise ValueError('Evidence needs citation, study context, and statement')
        ref=refs.get(row['reference_id']);pos=row['position']
        if ref and (not isinstance(pos,int) or pos<1 or pos>len(ref['sequence']) or ref['sequence'][pos-1]!=row['reference_aa']):
            raise ValueError('Evidence reference-residue mismatch: '+row['reference_id'])
    return data['entries']

def cds_coordinate_map(sequence, feature, issues):
    """Map translated CDS indices to actual consensus positions, in codon order.

    A joined codon may span non-adjacent segment positions. Minus-strand bases
    are complemented but coordinates always refer to the stored consensus.
    """
    blocked={'UNSUPPORTED_TRANSLATION_EXCEPTION','UNSUPPORTED_GENETIC_CODE','OVERLAPPING_CDS_INTERVALS'}
    if blocked.intersection(issues):
        return {'status':'UNSUPPORTED_TRANSLATION','codons':[]}
    start=int(feature['qualifiers'].get('codon_start',['1'])[0])
    if start not in (1,2,3):raise ValueError('Invalid codon_start')
    coordinates=[];bases=[];strands=set()
    for a,b in feature['intervals']:
        if min(a,b)<1 or max(a,b)>len(sequence):raise ValueError('CDS outside sequence')
        minus=a>b;strands.add(minus)
        for pos in range(a,b+(-1 if minus else 1),-1 if minus else 1):
            coordinates.append(pos)
            base=sequence[pos-1]
            bases.append(base.translate(COMPLEMENT) if minus else base)
    if len(strands)!=1:raise ValueError('Mixed-strand CDS')
    coordinates=coordinates[start-1:];bases=bases[start-1:]
    codons=[];stopped=False
    for i in range(0,len(coordinates)-2,3):
        triplet=''.join(bases[i:i+3]);positions=coordinates[i:i+3]
        codons.append({'aa_index':i//3+1,'positions':positions,'bases':triplet,
                       'amino_acid':CODE.get(triplet,'X'),
                       'crosses_junction':any(abs(positions[j+1]-positions[j])!=1 for j in (0,1)),
                       'after_stop':stopped})
        if CODE.get(triplet,'X')=='*':stopped=True
    return {'status':'PARTIAL_CDS' if feature['partial'] or start!=1 or len(coordinates)%3 else 'MAPPED',
            'codons':codons,'untranslated_terminal_positions':coordinates[len(codons)*3:]}


def assess_protein(item,panel,evidence,min_identity,min_coverage):
    protein=item['query_sequence'];gene=item['gene'];segment=item['segment']
    item['changes']=[]
    item.pop('alignment_resolution',None)
    item.pop('reference_equivalents',None)
    for key in ['reference_id','reference_accession','reference_protein_id','reference_alignment','query_alignment','identity','coverage','numbering']:
        item.pop(key,None)
    item['status']='READY'
    refs=[r for r in panel['references'] if r['gene']==gene and r['segment']==segment]
    if not refs:item['status']='NO_REFERENCE_FOR_PROTEIN';return
    options=[(compare(r['sequence'],protein),r) for r in refs]
    options.sort(key=lambda v:(-v[0]['score'],v[1]['id']))
    c,ref=options[0]
    item.update({'reference_id':ref['id'],'reference_accession':ref['accession'],'reference_protein_id':ref['protein_id'],
                 'numbering':ref.get('numbering','reference protein, 1-based'),
                 'identity':c['identity'],'coverage':c['coverage'],
                 'reference_alignment':c['reference_alignment'],'query_alignment':c['query_alignment']})
    tied=[r for comparison,r in options if comparison['score']==c['score']]
    if len({r['sequence'] for r in tied})>1:item['status']='AMBIGUOUS_REFERENCE';return
    if len(tied)>1:item['reference_equivalents']=[{'id':r['id'],'accession':r['accession'],'strain':r.get('strain','')} for r in tied]
    if c['identity']<min_identity or c['coverage']<min_coverage:item['status']='DISTANT_REFERENCE';return
    item['alignment_resolution']=c['alignment_resolution']
    if c['ambiguous_alignment'] and not c['alignment_resolution']['callable_reference_positions']:
        item['status']='AMBIGUOUS_ALIGNMENT';return
    for change in c['changes']:
        change['evidence']=[e for e in evidence if e['reference_id']==ref['id'] and e['position']==change['position']
            and e['reference_aa']==change['reference_aa'] and e['alternate_aa']==change['query_aa'] and change['kind']=='substitution']
        item['changes'].append(change)
    if item.get('issues') or c['ambiguous_alignment']:item['status']='PARTIAL_INTERPRETATION'


def analyze(args):
    result={'schema_version':1,'coordinate_schema_version':1,'module_version':VERSION,'sample':args.sample,'proteins':[],'segment_sequences':[],
            'status':'READY','limitations':['Consensus comparisons; no within-sample allele frequencies.',
            'Evidence is a small pilot catalog; unannotated changes have not been assessed for biological effect.'],
            'provenance':{'script_sha256':sha(__file__),'min_identity':args.min_identity,'min_coverage':args.min_coverage}}
    if not 0<=args.min_identity<=1 or not 0<=args.min_coverage<=1:raise ValueError('Invalid alignment threshold')
    if not args.enabled:result['status']='DISABLED'
    elif not args.vadr_dir:result['status']='VADR_DISABLED'
    elif not args.panel or not Path(args.panel).is_file():result['status']='NEEDS_REFERENCE'
    else:
        panel=panel_check(json.loads(Path(args.panel).read_text()))
        evidence=evidence_check(json.loads(Path(args.evidence).read_text()),panel)
        result['provenance'].update({'panel_sha256':sha(args.panel),'evidence_sha256':sha(args.evidence),'panel':panel})
        tables=sorted(Path(args.vadr_dir).rglob('*.vadr.pass.tbl'))
        result['provenance']['tables']={str(p):sha(p) for p in tables}
        sequences={};segments={}
        for segment,path in args.consensus:
            result['provenance'].setdefault('consensus',{})[str(path)]=sha(path)
            for name,seq in fasta(Path(path).read_text()).items():
                name=name.split()[0]
                if name in sequences:raise ValueError('Duplicate consensus sequence ID '+name)
                sequences[name]=seq;segments[name]=segment
                result['segment_sequences'].append({'seqid':name,'segment':segment,'sequence':seq,'length':len(seq),'sha256':hashlib.sha256(seq.encode()).hexdigest(),'coordinate_system':'stored_consensus_1_based'})
        if not tables:result['status']='NO_VADR_PASS_ANNOTATIONS'
        observed=set();annotated_sequences=set()
        for table in tables:
            for feature in features(table.read_text()):
                name=feature['seqid'];annotated_sequences.add(name);gene=gene_name(feature['qualifiers'])
                item={'seqid':name,'gene':gene or 'UNKNOWN','segment':segments.get(name,''),'status':'READY','changes':[]}
                result['proteins'].append(item)
                key=(name,gene,tuple(feature['intervals']))
                if key in observed:raise ValueError('Duplicate CDS annotation')
                observed.add(key)
                if name not in sequences:item['status']='SEQUENCE_ID_MISMATCH';continue
                item['cds_annotation']={'intervals':feature['intervals'],'partial':feature['partial'],
                    'qualifiers':feature['qualifiers'],'source':str(table),'source_sha256':sha(table),
                    'strand':'-' if feature['intervals'][0][0]>feature['intervals'][0][1] else '+',
                    'coordinate_system':'stored_consensus_1_based'}
                protein,issues=translate_feature(sequences[name],feature)
                item.update({'query_sequence':protein,'issues':issues,'cds_intervals':feature['intervals']})
                item['codon_map']=cds_coordinate_map(sequences[name],feature,issues)
                if not gene:item['status']='UNSUPPORTED_PRODUCT';continue
                blockers=set(issues)-{'AMBIGUOUS_RESIDUES','PREMATURE_STOP'}
                if blockers:item['status']='CDS_REVIEW_REQUIRED';continue
                assess_protein(item,panel,evidence,args.min_identity,args.min_coverage)
        result['unannotated_sequences']=sorted(set(sequences)-annotated_sequences)
        if tables and not result['proteins']:result['status']='NO_CDS_ANNOTATIONS'
        elif result['unannotated_sequences'] or any(p['status']!='READY' for p in result['proteins']):result['status']='REVIEW'
    write_json(args.output,result)

FIELDS=['sample','segment','protein','status','reference_accession','reference_protein_id','numbering','change','kind',
        'position','query_position','reference_aa','query_aa','identity','coverage','evidence','citations',
        'alignment_method','uncertain_reference_positions','uncertain_insertion_anchors']

def render(args):
    samples=[json.loads(Path(p).read_text()) for p in args.inputs]
    rows=[];summaries=[];alignments=[]
    for sample in samples:
        summaries.append((sample['sample'],sample['status'],len(sample['proteins'])))
        for p in sample['proteins']:
            for c in p['changes'] or [{}]:
                row={k:c.get(k,'') for k in FIELDS}
                row.update(sample=sample['sample'],segment=p['segment'],protein=p['gene'],status=p['status'],
                    reference_accession=p.get('reference_accession',''),reference_protein_id=p.get('reference_protein_id',''),
                    numbering=p.get('numbering',''),identity=p.get('identity',''),coverage=p.get('coverage',''),
                    alignment_method=p.get('alignment_resolution',{}).get('method',''),
                    uncertain_reference_positions=','.join(map(str,p.get('alignment_resolution',{}).get('uncertain_reference_positions',[]))),
                    uncertain_insertion_anchors=','.join(map(str,p.get('alignment_resolution',{}).get('uncertain_insertion_anchors',[]))),
                    change=c.get('change','No differences' if p['status']=='READY' else 'No unambiguous differences called; see protein issues'),
                    evidence=' | '.join(e['statement']+' Study context: '+e['study_context'] for e in c.get('evidence',[])),
                    citations=' | '.join(e['citation_url'] for e in c.get('evidence',[])))
                rows.append(row)
            if 'reference_alignment' in p:
                alignments.append('<details><summary>'+html.escape(sample['sample']+' / '+p['gene']+' / '+p['reference_id'])+
                    '</summary><pre>Reference '+html.escape(p['reference_alignment'])+'\nSample    '+html.escape(p['query_alignment'])+'</pre></details>')
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=FIELDS,delimiter='\t',lineterminator='\n');writer.writeheader()
    writer.writerows(rows)
    Path(args.tsv).parent.mkdir(parents=True,exist_ok=True);Path(args.tsv).write_text(stream.getvalue())
    data={'schema_version':1,'samples':samples,'rows':rows};write_json(args.json,data)
    import importlib.util
    module_path=Path(__file__).with_name('amino_acid_visual_report.py')
    spec=importlib.util.spec_from_file_location('wings_amino_visual',module_path)
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    renderer.render_visual(data,stream.getvalue(),args.html)


def recompare(args):
    """Recompare saved translated proteins; do not read raw reads or run upstream tools."""
    inputs=[Path(p).resolve() for p in args.inputs]
    output_root=Path(args.output_dir).expanduser().resolve();pending=[];names=set()
    eligible={'READY','PARTIAL_INTERPRETATION','AMBIGUOUS_ALIGNMENT','DISTANT_REFERENCE','AMBIGUOUS_REFERENCE'}
    evidence_path=Path(args.evidence)
    for path in inputs:
        data=json.loads(path.read_text());name=data['sample']
        if not name or name in {'.','..'} or Path(name).name!=name or name in names:
            raise ValueError('Unsafe or duplicate sample ID: '+name)
        names.add(name);output=output_root/name/'changes.json'
        if output.resolve() in inputs:raise ValueError('Choose a new output directory; source JSONs must be preserved.')
        records=[p for p in data.get('proteins',[]) if p.get('status') in eligible]
        if records:
            provenance=data.get('provenance',{});panel=panel_check(provenance.get('panel',{}))
            expected=provenance.get('evidence_sha256')
            if not expected or not evidence_path.is_file() or sha(evidence_path)!=expected:
                raise ValueError(name+': evidence file does not match the recorded version. Supply the original file with --evidence.')
            evidence=evidence_check(json.loads(evidence_path.read_text()),panel)
            identity=provenance.get('min_identity');coverage=provenance.get('min_coverage')
            if not isinstance(identity,(int,float)) or not isinstance(coverage,(int,float)) or not 0<=identity<=1 or not 0<=coverage<=1:
                raise ValueError(name+': recorded comparison thresholds are missing or invalid.')
            for protein in records:
                if not protein.get('query_sequence'):raise ValueError(name+': saved translated sequence is missing; rerun only amino acid analyze from saved consensus/VADR files.')
                assess_protein(protein,panel,evidence,identity,coverage)
            data['status']='REVIEW' if data.get('unannotated_sequences') or any(p['status']!='READY' for p in data['proteins']) else 'READY'
            provenance['recomparison']={'source_json_sha256':sha(path),'source_module_version':data.get('module_version'),'previous_script_sha256':provenance.get('script_sha256'),'method':'all_optimal_paths'}
            provenance['script_sha256']=sha(__file__);data['module_version']=VERSION
        pending.append((output,data))
    # Validate and compute every sample before writing any output files.
    for output,data in pending:write_json(output,data)
    print('Recompared '+str(len(pending))+' saved samples. Outputs: '+str(output_root))
    print('Source JSONs retained. No raw-read processing, Snakemake jobs, or downloads were run.')


def embed(args):
    # WINGS_AMINO_TAB_EMBED_V1
    p=Path(args.report);text=p.read_text();start='<!-- WINGS_AMINO_ACIDS_BEGIN -->';end='<!-- WINGS_AMINO_ACIDS_END -->'
    text=re.sub(re.escape(start)+'.*?'+re.escape(end)+r'\n?','',text,flags=re.S)
    report=Path(args.amino).read_text()
    bridge='<!-- WINGS_AMINO_HEIGHT_BRIDGE_V1 -->\n<script>\n(() => {\n  let lastHeight = 0;\n  const content = document.querySelector("main") || document.body;\n  const measure = () => {\n    const height = Math.ceil(content.getBoundingClientRect().height);\n    if(height >= 200 && height !== lastHeight) {\n      lastHeight = height;\n      parent.postMessage({type:"wings-amino-height",height}, "*");\n    }\n  };\n  addEventListener("message", event => { if(event.source === parent && event.data?.type === "wings-amino-measure") requestAnimationFrame(measure); });\n  addEventListener("load", measure);\n  addEventListener("resize", measure);\n  if(typeof ResizeObserver === "function") new ResizeObserver(measure).observe(content);\n})();\n</script>\n'
    if 'WINGS_AMINO_HEIGHT_BRIDGE_V1' not in report:
        if '</body>' not in report:raise ValueError('Amino acid report has no closing body')
        report=report.replace('</body>',bridge+'\n</body>',1)
    fragment=(start+'<template id="wings-amino-acid-dashboard-0"><iframe title="WINGS amino acid landscape" '
              'sandbox="allow-scripts allow-downloads" style="width:100%;height:1000px;border:0" srcdoc="'+
              html.escape(report,quote=True)+'"></iframe></template>'+end)
    if '</body>' not in text:raise ValueError('Run report has no closing body')
    text=text.replace('</body>',fragment+'\n</body>',1);p.write_text(text)


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--output',default='resources/amino_acids/reference_panel.json');p.add_argument('--fasta');p.add_argument('--replace',action='store_true');p.set_defaults(func=prepare)
    p=sub.add_parser('analyze');p.add_argument('--sample',required=True);p.add_argument('--panel');p.add_argument('--evidence',required=True)
    p.add_argument('--vadr-dir');p.add_argument('--enabled',type=int,default=1);p.add_argument('--consensus',nargs=2,action='append',default=[],metavar=('SEGMENT','FASTA'))
    p.add_argument('--min-identity',type=float,default=.90);p.add_argument('--min-coverage',type=float,default=.90);p.add_argument('--output',required=True);p.set_defaults(func=analyze)
    p=sub.add_parser('report');p.add_argument('--inputs',nargs='+',required=True);p.add_argument('--html',required=True);p.add_argument('--tsv',required=True);p.add_argument('--json',required=True);p.set_defaults(func=render)
    p=sub.add_parser('recompare');p.add_argument('--inputs',nargs='+',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--evidence',default='resources/amino_acids/evidence.json');p.set_defaults(func=recompare)
    p=sub.add_parser('embed');p.add_argument('--report',required=True);p.add_argument('--amino',required=True);p.set_defaults(func=embed)
    args=ap.parse_args();args.func(args)

if __name__=='__main__':
    main()
