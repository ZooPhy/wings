#!/usr/bin/env python3
"""Select annotated reference proteins using the existing local influenza nucleotide DB."""
import argparse
import copy
import csv
import importlib.util
import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

spec=importlib.util.spec_from_file_location('wings_aa_local',Path(__file__).with_name('wings_amino_acids.py'))
aa=importlib.util.module_from_spec(spec);spec.loader.exec_module(aa)
ACCESSION=re.compile(r'^[A-Z][A-Z0-9_]*\.[0-9]+$')


def location(text):
    text=re.sub(r'\s+','',text)
    if text.startswith('complement(') and text.endswith(')'):
        return [(b,a) for a,b in reversed(location(text[11:-1]))]
    if text.startswith('join(') and text.endswith(')'):
        parts=[];depth=0;start=0;inner=text[5:-1]
        for i,char in enumerate(inner):
            depth+=(char=='(')-(char==')')
            if char==',' and depth==0:parts.append(inner[start:i]);start=i+1
        parts.append(inner[start:]);return [pair for part in parts for pair in location(part)]
    m=re.fullmatch(r'(\d+)\.\.(\d+)',text)
    if not m:raise ValueError('Unsupported or partial reference location: '+text)
    return [(int(m[1]),int(m[2]))]


def references_from_xml(raw,accession,segment,local_sequence):
    records=ET.fromstring(raw).findall('.//GBSeq')
    matches=[r for r in records if r.findtext('GBSeq_accession-version')==accession]
    if len(matches)!=1:raise ValueError(accession+': exact accession version missing from NCBI record')
    record=matches[0];sequence=(record.findtext('GBSeq_sequence') or '').upper()
    normalized=local_sequence.upper().replace('U','T')
    if sequence not in (normalized,normalized.translate(aa.COMPLEMENT)[::-1]):
        raise ValueError(accession+': annotated NCBI sequence differs from the local database sequence')
    features=[];strain=''
    for node in record.findall('./GBSeq_feature-table/GBFeature'):
        qualifiers={}
        for q in node.findall('./GBFeature_quals/GBQualifier'):
            qualifiers.setdefault(q.findtext('GBQualifier_name'),[]).append(q.findtext('GBQualifier_value') or '')
        kind=node.findtext('GBFeature_key');loc=node.findtext('GBFeature_location') or ''
        if kind=='source':strain=qualifiers.get('strain',[strain])[0]
        features.append((kind,loc,qualifiers))
    refs=[]
    for kind,loc,q in features:
        if kind!='CDS' or any(key in q for key in ['pseudo','pseudogene','transl_except','ribosomal_slippage']):continue
        gene=aa.gene_name(q)
        gene_segment={'M1':'MP','M2':'MP','NS1':'NS','NEP':'NS','PB1-F2':'PB1','PA-X':'PA'}.get(gene,gene)
        if not gene or gene_segment!=segment:continue
        try:intervals=location(loc)
        except ValueError:continue
        feature={'intervals':intervals,'partial':False,'qualifiers':q}
        protein,issues=aa.translate_feature(sequence,feature)
        annotated=''.join(q.get('translation',[''])[0].split()).rstrip('*')
        pid=q.get('protein_id',[''])[0]
        if issues or not annotated or protein!=annotated or not ACCESSION.fullmatch(pid) or not set(protein)<=aa.AA:continue
        refs.append({'id':accession+':'+gene,'accession':accession,'protein_id':pid,'gene':gene,'segment':segment,'sequence':protein,
                     'strain':strain or record.findtext('GBSeq_organism') or 'Strain not recorded',
                     'source_url':'https://www.ncbi.nlm.nih.gov/nuccore/'+accession,
                     'numbering':'full-length selected reference protein, 1-based; includes signal peptide where present',
                     'annotation_sha256':__import__('hashlib').sha256(raw).hexdigest()})
        if gene=='HA':
            regions=annotated_regions(sequence,feature,features,len(protein))
            if regions:
                refs[-1]['reference_regions']=regions
                refs[-1]['region_sources']=[{'label':'Selected reference GenBank feature annotations: '+accession,'url':refs[-1]['source_url']}]
    if len({r['id'] for r in refs})!=len(refs):raise ValueError(accession+': duplicate annotated gene products')
    return refs


def annotated_regions(sequence,cds,features,length):
    codons=aa.cds_coordinate_map(sequence,cds,[])['codons'];regions=[]
    for kind,loc,q in features:
        product=' '.join(q.get('product',[]))
        if kind in {'sig_peptide','signal_peptide'}:name='Signal peptide'
        elif kind=='mat_peptide' and re.search(r'\bHA1\b',product,re.I):name='HA1'
        elif kind=='mat_peptide' and re.search(r'\bHA2\b',product,re.I):name='HA2'
        else:continue
        try:intervals=location(loc)
        except ValueError:continue
        positions={pos for a,b in intervals for pos in range(min(a,b),max(a,b)+1)}
        indices=[c['aa_index'] for c in codons if c['aa_index']<=length and all(n in positions for n in c['positions'])]
        if not indices or indices!=list(range(min(indices),max(indices)+1)):continue
        regions.append({'name':name,'short':'SP' if name=='Signal peptide' else name,'start':min(indices),'end':max(indices),
                        'color':{'Signal peptide':'#4AB7C4','HA1':'#8C1D40','HA2':'#FFC627'}[name]})
    regions.sort(key=lambda r:r['start'])
    if len({r['name'] for r in regions})!=len(regions) or any(a['end']>=b['start'] for a,b in zip(regions,regions[1:])):return []
    return regions


def cached_record(accession,cache,offline):
    path=cache/(accession+'.xml')
    if path.is_file():return path.read_bytes()
    if offline:raise ValueError('Missing cached NCBI annotation: '+accession+' (run once without --offline)')
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?'+urllib.parse.urlencode({'db':'nuccore','id':accession,'retmode':'xml','rettype':'gb','tool':'WINGS'})
    time.sleep(.4)
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'WINGS-reference-assignment/1.0'}),timeout=60) as response:raw=response.read(10000000)
    if not any(r.findtext('GBSeq_accession-version')==accession for r in ET.fromstring(raw).findall('.//GBSeq')):
        raise ValueError(accession+': NCBI did not return the requested accession version')
    cache.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.xml.tmp');temp.write_bytes(raw);temp.replace(path)
    return raw


def read_database(fasta,manifest):
    with manifest.open() as stream:rows=list(csv.DictReader(stream,delimiter='\t'))
    if len(rows)!=1 or not rows[0].get('fasta_sha256'):raise ValueError('Expected one database manifest row with fasta_sha256')
    if aa.sha(fasta)!=rows[0]['fasta_sha256']:raise ValueError('Database FASTA checksum does not match its manifest')
    references={}
    for header,sequence in aa.fasta(fasta.read_text()).items():
        accession=header.split()[0].strip('|')
        if not ACCESSION.fullmatch(accession):raise ValueError('Reference header lacks a versioned accession: '+header)
        if accession in references and references[accession]!=sequence:raise ValueError('Conflicting database sequences for '+accession)
        references[accession]=sequence
    return references,rows[0]


def shortlist(query,db,work,args):
    fasta=work/'query.fasta';fasta.write_text('>query\n'+query+'\n')
    if getattr(args,'docker',None):
        prefix=[args.docker,'run','--rm','--network','none','-v',str(db.parent)+':/database:ro','-v',str(work)+':/query:ro',args.blast_image,'blastn']
        query_path='/query/query.fasta';db_path='/database/'+db.name
    else:prefix=[args.blastn];query_path=str(fasta);db_path=str(db)
    command=[*prefix,'-query',query_path,'-db',db_path,'-max_target_seqs',str(args.candidates),'-max_hsps','1',
             '-num_threads',str(args.threads),'-outfmt','6 saccver bitscore pident qcovs']
    result=subprocess.run(command,capture_output=True,text=True,check=True)
    hits=[]
    for line in result.stdout.splitlines():
        accession,score,identity,coverage=line.split('\t')
        if not ACCESSION.fullmatch(accession):raise ValueError('BLAST returned an unversioned accession: '+accession)
        if float(identity)>=args.min_nt_identity and float(coverage)>=args.min_query_coverage:
            hits.append({'accession':accession,'bitscore':float(score),'identity':float(identity),'query_coverage':float(coverage)})
    return sorted(hits,key=lambda h:(-h['bitscore'],-h['query_coverage'],-h['identity'],h['accession']))


def assign_sample(data,local,manifest,args,work):
    result=copy.deepcopy(data);refs={};searches=[];rejected=[]
    for seq in result.get('segment_sequences',[]):
        if not seq.get('sequence'):continue
        hits=shortlist(seq['sequence'],args.db,work,args)
        searches.append({'seqid':seq['seqid'],'segment':seq['segment'],'hits':hits})
        for hit in hits:
            accession=hit['accession']
            if accession not in local:raise ValueError('BLAST database and FASTA disagree: '+accession)
            raw=cached_record(accession,args.cache,args.offline)
            try:candidates=references_from_xml(raw,accession,seq['segment'],local[accession])
            except ValueError as error:rejected.append({'accession':accession,'reason':str(error)});continue
            if not candidates:rejected.append({'accession':accession,'reason':'No complete, validated supported CDS translation'})
            for ref in candidates:refs[ref['id']]=ref
    if not refs:raise ValueError(result['sample']+': no valid annotated reference candidates. No result files were written. '+str(rejected[:3]))
    panel={'schema_version':1,'panel_name':'local-flu-db-shortlist','references':list(refs.values()),'selection_method':'nucleotide shortlist followed by global protein alignment'}
    aa.panel_check(panel)
    evidence=aa.evidence_check(json.loads(args.evidence.read_text()),panel)
    provenance=result.get('provenance',{});min_identity=provenance.get('min_identity');min_coverage=provenance.get('min_coverage')
    if not isinstance(min_identity,(int,float)) or not isinstance(min_coverage,(int,float)) or not 0<=min_identity<=1 or not 0<=min_coverage<=1:raise ValueError('Missing/invalid recorded protein comparison thresholds')
    for p in result.get('proteins',[]):
        if p.get('status') not in {'READY','PARTIAL_INTERPRETATION','AMBIGUOUS_ALIGNMENT','AMBIGUOUS_REFERENCE','DISTANT_REFERENCE','NO_REFERENCE_FOR_PROTEIN'}:continue
        if not p.get('query_sequence'):raise ValueError(result['sample']+': saved translated protein is missing')
        aa.assess_protein(p,panel,evidence,min_identity,min_coverage)
    provenance['previous_reference_panel']=provenance.get('panel')
    provenance['previous_panel_sha256']=provenance.get('panel_sha256')
    provenance['panel_sha256']=hashlib.sha256((json.dumps(panel,indent=2,sort_keys=True)+'\n').encode()).hexdigest()
    provenance['panel_path']='reference_panel.json'
    provenance['panel']=panel;provenance['evidence_sha256']=aa.sha(args.evidence)
    provenance['reference_assignment']={'database_manifest':manifest,'manifest_sha256':aa.sha(args.manifest),'fasta_sha256':manifest.get('fasta_sha256') or aa.sha(args.fasta),
        'blastn_version':args.blast_version,'index_sha256':getattr(args,'index_hashes',{}),'shortlist_size':args.candidates,'min_nt_identity':args.min_nt_identity,'min_query_coverage':args.min_query_coverage,
        'queries':searches,'rejected_candidates':rejected,'previous_script_sha256':provenance.get('script_sha256'),'assignment_script_sha256':aa.sha(__file__)}
    provenance['script_sha256']=aa.sha(Path(aa.__file__));result['provenance']=provenance;result['module_version']=aa.VERSION
    result['status']='REVIEW' if result.get('unannotated_sequences') or any(p['status']!='READY' for p in result['proteins']) else 'READY'
    result.setdefault('limitations',[]).append('Reference selected from the local nucleotide-hit shortlist. Literature evidence requires the exact reference and residue; reference groups are not pooled.')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',nargs='+',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--db',type=Path,default=Path('resources/flu_db/fluA_db'))
    parser.add_argument('--fasta',type=Path,default=Path('resources/flu_db/fluA_reference.fasta'))
    parser.add_argument('--manifest',type=Path,default=Path('resources/flu_db/database_manifest.tsv'))
    parser.add_argument('--cache',type=Path,default=Path('resources/amino_acids/ncbi_annotation_cache'))
    parser.add_argument('--evidence',type=Path,default=Path('resources/amino_acids/evidence.json'))
    parser.add_argument('--blastn',default='blastn');parser.add_argument('--candidates',type=int,default=3);parser.add_argument('--threads',type=int,default=2)
    parser.add_argument('--min-nt-identity',type=float,default=70);parser.add_argument('--min-query-coverage',type=float,default=80);parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    if args.candidates<1 or args.threads<1 or not 0<=args.min_nt_identity<=100 or not 0<=args.min_query_coverage<=100:raise ValueError('Invalid BLAST search settings')
    executable=shutil.which(args.blastn)
    if not executable and args.blastn=='blastn':
        cached=sorted(Path('.snakemake/conda').glob('*/bin/blastn'))
        executable=str(cached[0].resolve()) if cached else None
    args.docker=None;args.blast_image='ncbi/blast-static:2.17.0'
    if executable:
        args.blastn=executable;command=[executable,'-version']
    elif args.blastn=='blastn' and shutil.which('docker'):
        args.docker=shutil.which('docker');command=[args.docker,'run','--rm',args.blast_image,'blastn','-version']
    else:raise ValueError('BLAST was not found locally or in the WINGS Conda cache, and Docker is unavailable. Pass --blastn /path/to/blastn.')
    args.blast_version=subprocess.run(command,capture_output=True,text=True,check=True).stdout.strip()
    args.db=args.db.expanduser().resolve();local,manifest=read_database(args.fasta,args.manifest)
    args.index_hashes={p.name:aa.sha(p) for p in sorted(args.db.parent.glob(args.db.name+'.n*')) if p.is_file()}
    if not args.index_hashes:raise ValueError('No nucleotide BLAST database index files found: '+str(args.db))
    pending=[];seen=set();source_paths={p.resolve() for p in args.inputs}
    with tempfile.TemporaryDirectory(prefix='wings-local-aa-') as directory:
        for i,path in enumerate(args.inputs,1):
            data=json.loads(path.read_text());name=data['sample']
            if not name or name in {'.','..'} or Path(name).name!=name or name in seen:raise ValueError('Unsafe or duplicate sample ID')
            seen.add(name);output=args.output_dir/name/'changes.json'
            if output.resolve() in source_paths:raise ValueError('Choose a new output directory; source JSONs must be preserved')
            print(f'[{i}/{len(args.inputs)}] Selecting references: {name}',flush=True)
            result=assign_sample(data,local,manifest,args,Path(directory))
            result['provenance']['reference_assignment']['source_json_sha256']=aa.sha(path)
            pending.append((output,result))
    for output,result in pending:
        aa.write_json(output.parent/'reference_panel.json',result['provenance']['panel'])
        aa.write_json(output,result)
    print('Wrote '+str(len(pending))+' samples to '+str(args.output_dir)+'. Source results preserved; no upstream workflow jobs were run.')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError,ET.ParseError) as error:raise SystemExit('ERROR: '+str(error))
