#!/usr/bin/env python3
"""Frozen NCBI segment records or local exports, scoped by study metadata.

Network queries contain public taxonomy/subtype/gene terms only. Collection
windows and geography are applied to source qualifiers locally, never release
or accession dates. Each snapshot freezes accession.version and raw responses.
"""
from __future__ import annotations
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

REFERENCE_DEFAULTS = dict(source='ncbi', subtypes=[], snapshot='initial',
    cache_dir='resources/phylodynamics/ncbi-cache', offline=False,
    max_records=250000, batch_size=100, source_fasta='', source_metadata='',
    email_env='NCBI_EMAIL', api_key_env='NCBI_API_KEY')
SEGMENTS = dict(zip('12345678', ('PB2','PB1','PA','HA','NP','NA','MP','NS')))
FIELDS = ['accession','segment','collection_date','country','state','host','specimen_id',
          'isolate','subtype','source','annotation_basis']
BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'


def reference_configuration(raw):
    if not isinstance(raw,dict) or set(raw)-set(REFERENCE_DEFAULTS):
        raise ValueError('Invalid phylodynamics.references settings')
    cfg=dict(REFERENCE_DEFAULTS,**raw)
    if cfg['source'] not in ('ncbi','local'):
        raise ValueError('Reference source must be ncbi or local')
    if not isinstance(cfg['subtypes'],list) or any(not re.fullmatch(r'H(?:[1-9]|1[0-8])(?:N(?:[1-9]|1[01]))?',str(s)) for s in cfg['subtypes']):
        raise ValueError('subtypes must contain H types or full H/N types, e.g. H5 or H5N1')
    if len(set(cfg['subtypes']))!=len(cfg['subtypes']): raise ValueError('Duplicate subtypes')
    for k,lo,hi in [('batch_size',1,500),('max_records',1,2000000)]:
        if type(cfg[k]) is not int or not lo<=cfg[k]<=hi:raise ValueError('Invalid '+k)
    if not isinstance(cfg['offline'],bool):raise ValueError('offline must be boolean')
    for k in ('snapshot','cache_dir','source_fasta','source_metadata','email_env','api_key_env'):
        if not isinstance(cfg[k],str):raise ValueError(k+' must be a string')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',cfg['snapshot']):raise ValueError('Invalid snapshot name')
    if cfg['source']=='local' and not all(cfg[k] for k in ('source_fasta','source_metadata')):
        raise ValueError('Local references require source_fasta and source_metadata')
    return cfg


def atomic(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
    tmp.write_bytes(data); os.replace(tmp,path)


def save(path,obj):
    atomic(path,(json.dumps(obj,indent=2,sort_keys=True)+'\n').encode())


def sha(data):return hashlib.sha256(data).hexdigest()


def normalized_date(text):
    text=str(text or '').strip()
    for fmt in ('%Y-%m-%d','%d-%b-%Y'):
        try:return datetime.strptime(text,fmt).date().isoformat()
        except ValueError:pass
    return text  # Preserve partial/ranged dates; never invent a collection day.


def segment_value(value):
    value=str(value).strip().upper()
    return SEGMENTS.get(value, {'M':'MP','M1':'MP','NS1':'NS'}.get(value,value if value in SEGMENTS.values() else ''))


def annotated_segment(header, supplied=''):
    found={segment_value(x) for x in re.findall(r'\bsegment\s+([1-8]|PB2|PB1|PA|HA|NP|NA|MP|NS)\b',header,re.I)}
    if supplied:found.add(segment_value(supplied))
    found.discard('')
    if len(found)!=1: return ''
    return next(iter(found))


def serotypes(text):return sorted(set(re.findall(r'\bH(?:1[0-8]|[1-9])(?:N(?:1[01]|[1-9]))?\b',text.upper())))


def matches_subtype(text,wanted):
    found=serotypes(text)
    return any(t==w or ('N' not in w and t.startswith(w+'N')) for w in wanted for t in found)


def scope_from_study(metadata, cfg, results=None):
    from phylodynamic_selection import read_tsv, exact_date, country, digest
    rows=read_tsv(metadata)
    dates=[exact_date(r.get('collection_date','')) for r in rows]
    known=[d for d in dates if d]
    if not known:raise ValueError('At least one exact study collection date is required to define the reference window')
    wanted=cfg['references']['subtypes'][:]
    basis='explicit configuration'
    if not wanted:
        basis='recorded study subtype / coverage contig annotations'
        calls=[]
        for r in rows:
            for k in ('subtype','serotype','potential_subtype','ha_call'):
                calls.extend(serotypes(r.get(k,'')))
            if results:
                p=Path(results)/(r.get('sample_id') or r.get('sample',''))/'coverage/coverage.tsv'
                if p.exists():
                    for q in read_tsv(p):calls.extend(serotypes(q.get('contig','').replace('_',' ')))
        # An HA family scope preserves other neuraminidase backgrounds (e.g. H5Nx).
        wanted=sorted({re.match(r'H\d+',x)[0] for x in calls})
    if not wanted:raise ValueError('No recorded H subtype found; set phylodynamics.references.subtypes explicitly (e.g. [H5])')
    return dict(start=(min(known)-timedelta(days=cfg['lookback_days'])).isoformat(),
        end=(max(known)+timedelta(days=cfg['lookahead_days'])).isoformat(),
        study_countries=sorted({country(r.get('country','')) for r in rows if r.get('country')}),
        countries=cfg['countries'], segments=cfg['segments'], subtypes=wanted, subtype_basis=basis,
        study_metadata_sha256=digest(metadata), partial_or_missing_study_dates=len(rows)-len(known),
        geography_policy='US states / Canadian provinces; other countries as country-level states',
        scope_note='Empty countries means global context. Study location counts do not set sampling probabilities.')


def query_for(scope):
    types=[]
    for t in scope['subtypes']:
        types += [t] if 'N' in t else [t]+[t+'N'+str(n) for n in range(1,10)]
    genes=[]
    for s in scope['segments']:
        num=next(k for k,v in SEGMENTS.items() if v==s)
        genes += [s+'[Gene Name]', '"segment '+num+'"[Title]']
        if s=='HA':genes.append('hemagglutinin[Title]')
        if s=='NA':genes.append('neuraminidase[Title]')
    return 'txid11320[Organism:exp] AND ('+' OR '.join('"'+t+'"[All Fields]' for t in sorted(set(types)))+') AND ('+' OR '.join(genes)+')'


class NCBI:
    def __init__(self,cfg):
        self.cfg=cfg; self.key=os.environ.get(cfg['api_key_env'],'');self.email=os.environ.get(cfg['email_env'],'')
        self.last=0.0
    def request(self,utility,params):
        if self.cfg['offline']:raise ValueError('Offline snapshot incomplete; enable networking or finish this snapshot first')
        if not self.email:raise ValueError('Set '+self.cfg['email_env']+' to your NCBI contact email')
        params=dict(params,tool='wings_phylodynamics',email=self.email)
        if self.key:params['api_key']=self.key
        for attempt in range(5):
            time.sleep(max(0,(0.12 if self.key else 0.36)-(time.monotonic()-self.last)))
            self.last=time.monotonic()
            try:
                req=urllib.request.Request(BASE+utility+'.fcgi',data=urllib.parse.urlencode(params).encode(),headers={'User-Agent':'WINGS reference selector/2'})
                with urllib.request.urlopen(req,timeout=90) as r:return r.read()
            except urllib.error.HTTPError as e:
                if e.code not in (429,500,502,503,504):raise RuntimeError('NCBI HTTP '+str(e.code)+'; request details withheld to protect credentials') from None
                delay=min(30,2**attempt)
                if e.headers and str(e.headers.get('Retry-After','')).isdigit():delay=min(30,int(e.headers['Retry-After']))
            except (urllib.error.URLError,TimeoutError):delay=min(30,2**attempt)
            time.sleep(delay)
        raise RuntimeError('NCBI request failed after five attempts; cached completed batches remain reusable')


def checked_xml(data):
    root=ET.fromstring(data)
    errors=[e.text for e in root.iter() if e.tag.upper()=='ERROR' and e.text]
    if errors:raise ValueError('NCBI returned an error; retry with a fresh snapshot if history expired')
    return root


def accession_snapshot(client, folder, query, cfg):
    path=folder/'accessions.json'
    if path.exists():
        record=json.loads(path.read_text())
        if record['query']!=query:raise ValueError('Snapshot query changed; choose a new snapshot name')
        if sha('\n'.join(record['accessions']).encode())!=record['accessions_sha256']:raise ValueError('Corrupt accession manifest')
        if len(record['accessions'])!=record['count'] or len(set(record['accessions']))!=record['count']:
            raise ValueError('Incomplete accession manifest')
        if len(record['accessions'])>cfg['max_records']:raise ValueError('Snapshot exceeds max_records; never silently truncate')
        return record
    raw=client.request('esearch',dict(db='nuccore',term=query,usehistory='y',retmax=0,retmode='xml'))
    root=checked_xml(raw)
    if root.find('ErrorList') is not None:
        raise ValueError('NCBI query returned search errors; inspect the query rather than silently dropping terms')
    warnings=[(e.tag,e.text or '') for e in root.findall('./WarningList/*')]
    # Empty OR alternatives (e.g. an absent H5Nx subtype) are expected. Other
    # warnings, including ignored/truncated phrases, require query review.
    if any(tag not in ('QuotedPhraseNotFound','PhraseNotFound','OutputMessage') for tag,text in warnings):
        raise ValueError('NCBI query returned unexpected search warnings; review query translation')
    if any(tag=='OutputMessage' and 'No items found' not in text for tag,text in warnings):
        raise ValueError('NCBI search was altered or truncated; review query translation')
    count=int(root.findtext('Count','0'))
    if count>cfg['max_records']:raise ValueError(f'NCBI query matched {count} records, above max_records={cfg["max_records"]}; no biased first-N subset was taken')
    ids=[]
    for start in range(0,count,5000):
        chunk=client.request('efetch',dict(db='nuccore',query_key=root.findtext('QueryKey'),WebEnv=root.findtext('WebEnv'),retstart=start,retmax=min(5000,count-start),rettype='acc',retmode='text'))
        batch=chunk.decode().split()
        if len(batch)!=min(5000,count-start) or any(not re.fullmatch(r'[A-Za-z_]+\d+\.\d+',x) for x in batch):
            raise ValueError('Incomplete or malformed accession page; snapshot not frozen')
        ids.extend(batch)
    if len(set(ids))!=count:raise ValueError('Duplicate accession in NCBI history; snapshot not frozen')
    record=dict(query=query,query_translation=root.findtext('QueryTranslation',''),accessions=sorted(ids),
        count=count,search_warnings=warnings,retrieved_at=datetime.now(timezone.utc).isoformat())
    record['accessions_sha256']=sha('\n'.join(record['accessions']).encode())
    save(path,record)
    return record


def parse_genbank(data):
    root=checked_xml(data)
    for gb in root.findall('.//GBSeq'):
        qualifiers={}
        for feature in gb.findall('./GBSeq_feature-table/GBFeature'):
            if feature.findtext('GBFeature_key')!='source':continue
            for q in feature.findall('./GBFeature_quals/GBQualifier'):
                qualifiers.setdefault(q.findtext('GBQualifier_name',''),[]).append(q.findtext('GBQualifier_value',''))
        def one(k):
            values=set(qualifiers.get(k,[]));return next(iter(values)) if len(values)==1 else ''
        header=gb.findtext('GBSeq_definition','')
        geo=one('geo_loc_name') or one('country')
        nation,_,region=geo.partition(':')
        # Only a declared first administrative unit is accepted; never infer from a city.
        region=region.split(',')[0].strip()
        specimens=[x for x in qualifiers.get('db_xref',[]) if x.startswith('BioSample:')]
        specimens += ['BioSample:'+x.findtext('GBXref_id','') for x in gb.findall('./GBSeq_xrefs/GBXref') if x.findtext('GBXref_dbname')=='BioSample']
        specimens=sorted(set(specimens))
        row=dict(accession=gb.findtext('GBSeq_accession-version',''),
            segment=annotated_segment(header,one('segment')),
            collection_date=normalized_date(one('collection_date')),country=nation.strip(),state=region,
            host=one('host'),specimen_id=specimens[0] if len(set(specimens))==1 else '',
            isolate=one('isolate') or one('strain'),subtype=one('serotype') or ' '.join(serotypes(header)),
            source='NCBI nuccore GenBank',annotation_basis='source qualifiers and explicit segment in definition')
        yield row,gb.findtext('GBSeq_sequence','').upper()


def remote_records(scope,cfg,client=None):
    client=client or NCBI(cfg)
    query=query_for(scope)
    # Query+snapshot, not live results, determines this reusable accession universe.
    folder=Path(cfg['cache_dir'])/cfg['snapshot']/sha(query.encode())[:20]
    manifest=accession_snapshot(client,folder,query,cfg)
    ids=manifest['accessions']
    for start in range(0,len(ids),cfg['batch_size']):
        batch=ids[start:start+cfg['batch_size']]
        key=sha('\n'.join(batch).encode());path=folder/(key+'.xml');check=folder/(key+'.json')
        if path.exists() and check.exists():
            data=path.read_bytes()
            if sha(data)!=json.loads(check.read_text())['sha256']:raise ValueError('Cached NCBI response hash mismatch: '+str(path))
        else:
            data=client.request('efetch',dict(db='nuccore',id=','.join(batch),rettype='gb',retmode='xml'))
        records=list(parse_genbank(data))
        if len(records)!=len(batch) or {r['accession'] for r,s in records}!=set(batch):
            raise ValueError('NCBI batch omitted or changed a frozen accession.version; no partial pool accepted')
        atomic(path,data);save(check,dict(sha256=sha(data),accessions=batch))
        for row,seq in records:yield row,seq


def local_records(fasta,metadata):
    from phylodynamic_selection import iter_fasta
    sequences={};bases={}
    for header,seq in iter_fasta(Path(fasta)):
        acc=header.split()[0]
        if acc in sequences:raise ValueError('Duplicate FASTA accession: '+acc)
        sequences[acc]=(header,seq)
        bases.setdefault(acc.split('.')[0],[]).append(acc)
    text=Path(metadata).read_text(encoding='utf-8-sig')
    dialect='excel-tab' if '\t' in text.splitlines()[0] else 'excel'
    rows=list(csv.DictReader(text.splitlines(),dialect=dialect));seen=set()
    for original in rows:
        r={k.lower():v for k,v in original.items() if k}
        acc=r.get('accession','').strip()
        if acc not in sequences:
            options=bases.get(acc,[])
            if len(options)!=1:raise ValueError('Missing or ambiguous FASTA accession for metadata: '+acc)
            acc=options[0]
        if acc in seen:raise ValueError('Duplicate metadata accession: '+acc)
        seen.add(acc);header,seq=sequences[acc]
        geo=r.get('geo_location','')
        nation,_,region=geo.partition(':')
        row=dict(accession=acc,segment=annotated_segment(header,r.get('segment','')),
            collection_date=normalized_date(r.get('collection_date','')),country=r.get('country') or nation,
            state=r.get('state') or r.get('usa') or region.split(',')[0].strip(),host=r.get('host',''),
            specimen_id=r.get('specimen_id') or ('BioSample:'+r['biosample'] if r.get('biosample') else ''),
            isolate=r.get('isolate',''),subtype=r.get('serotype') or r.get('subtype') or ' '.join(serotypes(header)),
            source='local export',annotation_basis='metadata and explicit FASTA segment annotation')
        yield row,seq
    if set(sequences)-seen:raise ValueError('FASTA contains records missing from metadata; no silently incomplete local pool accepted')


def prepare(metadata,results,output,cfg,client=None):
    from phylodynamic_selection import configuration, country, exact_date, write_tsv, digest
    cfg=configuration(cfg); ref=cfg['references'];scope=scope_from_study(metadata,cfg,results)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    # A failed refresh must not leave an apparently complete provenance manifest.
    (output/'provenance.json').unlink(missing_ok=True)
    source=local_records(ref['source_fasta'],ref['source_metadata']) if ref['source']=='local' else remote_records(scope,ref,client)
    retained=[];excluded=[];sequences=[];seen=set()
    for row,seq in source:
        acc=row['accession']
        if acc in seen:raise ValueError('Duplicate accession across reference batches: '+acc)
        seen.add(acc);row['country']=country(row['country']);reasons=[]
        when=exact_date(row['collection_date'])
        if row['segment'] not in scope['segments']:reasons.append('different_or_unresolved_segment')
        if not matches_subtype(row['subtype'],scope['subtypes']):reasons.append('different_or_unresolved_subtype')
        if not when:reasons.append('missing_partial_or_invalid_collection_date')
        elif not scope['start']<=when.isoformat()<=scope['end']:reasons.append('outside_collection_window')
        if scope['countries'] and row['country'] not in scope['countries']:reasons.append('outside_country_scope')
        if reasons:excluded.append(dict(row,reason=';'.join(reasons)));continue
        retained.append(row);sequences.append('>'+acc+'\n'+seq+'\n')
    write_tsv(output/'references.tsv',FIELDS,retained)
    write_tsv(output/'excluded.tsv',FIELDS+['reason'],excluded)
    atomic(output/'references.fasta',''.join(sequences).encode())
    record=dict(schema='wings.reference-snapshot.v2',scope=scope,source=ref['source'],
        snapshot=ref['snapshot'],query=query_for(scope) if ref['source']=='ncbi' else None,
        source_records=len(seen),retained_records=len(retained),excluded_records=len(excluded),
        files_sha256={p:digest(output/p) for p in ('references.tsv','references.fasta','excluded.tsv')},
        genetic_scope='Recorded H subtype and segment; no automatic clade assignment or nearest-neighbour enrichment.',
        limitations=['Metadata completeness filters can introduce bias.','Global source annotation is not verified genetic clade membership.'])
    if ref['source']=='local':record['source_sha256']={k:digest(ref[k]) for k in ('source_fasta','source_metadata')}
    save(output/'provenance.json',record)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('metadata','results','output','config'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();import yaml
    raw=yaml.safe_load(a.config.read_text());prepare(a.metadata,a.results,a.output,raw.get('phylodynamics',raw))

if __name__=='__main__':main()
