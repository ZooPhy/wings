#!/usr/bin/env python3
"""Metadata-driven context planning, acquisition, and immutable run selections."""
import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import uuid
from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT/'scripts') not in sys.path:
    sys.path.insert(0,str(ROOT/'scripts'))
SCHEMA = 'wings.context-selection.v1'
PROVIDERS = ('ecology','phenology','public_genotypes','ebird','outbreak')


def load(name):
    return runpy.run_path(str(ROOT/'scripts'/name))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name)
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n')
        os.replace(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def cache_root():
    path=Path(os.environ.get('WINGS_CONTEXT_CACHE','~/.cache/wings/context')).expanduser().resolve()
    if path.is_relative_to(ROOT):raise ValueError('WINGS_CONTEXT_CACHE must be outside the checkout')
    return path


def options(data=None):
    data=data or {}
    allowed={'selected_sources','days','network','phenology','phenology_year','ebird_package','ebird_source','all_species_confirmed','outbreak_file','global_genotypes','required'}
    if set(data)-allowed:raise ValueError('Unknown context options: '+', '.join(sorted(set(data)-allowed)))
    result={'days':30,'network':True,'phenology':True,'phenology_year':2023,'ebird_package':'','ebird_source':'',
            'all_species_confirmed':False,'outbreak_file':'','global_genotypes':False,'required':[] ,**data}
    for key in ('network','phenology','all_species_confirmed','global_genotypes'):
        if not isinstance(result[key],bool):raise ValueError(key+' must be true or false')
    for key,lo,hi in [('days',1,365),('phenology_year',2000,2100)]:
        if type(result[key]) is not int or not lo<=result[key]<=hi:raise ValueError('Invalid '+key)
    if not isinstance(result['required'],list) or any(x not in PROVIDERS for x in result['required']):raise ValueError('Unknown required context source')
    if 'selected_sources' in result:
        selected_sources=result['selected_sources']
        if not isinstance(selected_sources,list) or any(not isinstance(x,str) or x not in PROVIDERS for x in selected_sources) or len(set(selected_sources))!=len(selected_sources):
            raise ValueError('Invalid selected context sources')
        result['selected_sources']=[name for name in PROVIDERS if name in selected_sources]
        result['phenology']='phenology' in selected_sources
        if any(name not in selected_sources for name in result['required']):
            raise ValueError('A required context source must also be selected')
    for key in ('ebird_package','ebird_source','outbreak_file'):

        if not isinstance(result[key],str) or len(result[key])>4096:raise ValueError('Invalid '+key)
    return result


def source_enabled(opts,name):
    return name in opts.get('selected_sources',PROVIDERS) and (name!='phenology' or opts['phenology'])


def metadata_scope(path,days):
    eco=load('build_ecological_context.py')
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f,delimiter='\t')
        if not reader.fieldnames or 'sample_id' not in reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames):
            raise ValueError('Metadata requires unique column names including sample_id')
        rows=list(reader)
    if not rows:raise ValueError('Metadata is empty')
    ids=[(r.get('sample_id') or '').strip() for r in rows]
    if any(not x for x in ids) or len(ids)!=len(set(ids)):raise ValueError('Metadata sample IDs must be nonempty and unique')
    if any(None in r for r in rows):raise ValueError('Metadata has extra tab-separated fields')
    aliases={}
    mapping=ROOT/'resources/ebird_host_codes_2025.tsv'
    if mapping.exists():
        with mapping.open() as f:
            aliases={r['host'].casefold():r['ebird_species'] for r in csv.DictReader(f,delimiter='\t')}
    scopes=[];issues=[];weather=set();nights=set();species=set()
    for r in rows:
        sid=r['sample_id'];m=eco['sample_metadata'](r);when=eco['iso_date'](m['collection_date'])
        raw_host=(r.get('host') or '').strip()
        host=aliases.get(raw_host.casefold()) or (r.get('host_common_name') or r.get('host_species') or raw_host).strip()
        host_labels=sorted({str(v).strip() for v in (host,r.get('host_species'),r.get('host_common_name')) if v and str(v).strip().casefold() not in ('na','unknown','none','n/a')})
        missing=host.upper() in ('','NA','UNKNOWN','NONE','N/A')
        if missing:issues.append({'sample_id':sid,'issue':'Host missing; taxon-dependent context unavailable'})
        else:species.add(host)
        if not when:
            issues.append({'sample_id':sid,'issue':'Complete ISO collection date missing; date-dependent context unavailable'});continue
        if when>date.today():
            issues.append({'sample_id':sid,'issue':'Collection date is in the future'});continue
        start,end=(when-timedelta(days=days)).isoformat(),(when+timedelta(days=days)).isoformat()
        country=m['country'];state=m['state']
        if country=='UNKNOWN':issues.append({'sample_id':sid,'issue':'Country missing; eBird scope cannot be established'})
        if state=='Unknown':issues.append({'sample_id':sid,'issue':'State missing; regional matching is limited'})
        if m['latitude'] is not None and m['longitude'] is not None and -90<=m['latitude']<=90 and -180<=m['longitude']<=180:
            request,_,reason=eco['weather_request'](m,days)
            if request:
                query=parse_qs(urlparse(request).query)
                weather.add((m['latitude'],m['longitude'],query['start_date'][0],query['end_date'][0]))
            else:issues.append({'sample_id':sid,'issue':reason})
        else:issues.append({'sample_id':sid,'issue':'Valid coordinate pair missing; point weather unavailable'})
        if country=='US' and state in eco['STATES'] and state not in ('AK','HI'):
            nights.add((state,(when-timedelta(days=1)).isoformat()))
        else:issues.append({'sample_id':sid,'issue':'BirdCast requires a supported contiguous-US state'})
        scopes.append({'sample_id':sid,'country':country,'state':state,'host':host,'date_from':start,'date_to':end,
                       'collection_date':when.isoformat(),'host_labels':host_labels,'state_name':eco['STATES'].get(state,state)})
    return {'sample_count':len(rows),'sample_ids':sorted(ids),'scopes':scopes,'issues':issues,'species':sorted(species),
            'weather_queries':[list(x) for x in sorted(weather)],'birdcast_queries':[list(x) for x in sorted(nights)]}


def find_ebird(metadata,opts):
    if opts['ebird_source'] and not opts['ebird_package']:
        return {'status':'NEEDS_IMPORT','reason':'Import the selected eBird download'}
    api=load('ebird_context_package.py')
    candidates=[Path(opts['ebird_package']).expanduser()] if opts['ebird_package'] else sorted((cache_root()/'ebird').glob('*/context_manifest.json'))
    reasons=[]
    for candidate in candidates:
        directory=candidate.parent if candidate.name=='context_manifest.json' else candidate
        try:
            m=api['verify'](directory,metadata,opts['days'])
            return {'status':'READY','path':str(directory.resolve()),'package_id':m['package_id'],'release':m['release'],'reason':'Package covers this metadata'}
        except (OSError,ValueError,KeyError,TypeError) as e:reasons.append(str(e))
    return {'status':'NEEDS_IMPORT','reason':'; '.join(reasons[:2]) or 'Download matching EBD and sampling-event data, then import the extracted folder'}


def plan(metadata,settings=None):
    opts=options(settings);scope=metadata_scope(metadata,opts['days'])
    source=find_ebird(metadata,opts) if source_enabled(opts,'ebird') else {'status':'DISABLED','reason':'Not selected'}
    windows=sorted({(r['country'],r['state_name'],r['date_from'],r['date_to']) for r in scope['scopes'] if r['country']!='UNKNOWN'})
    proposal={'schema':'wings.context-plan.v1','metadata_sha256':sha(metadata),'options':opts,**scope,
            'ebird_request':{'url':'https://ebird.org/data/download','species':'All species','include_sampling_event_data':True,
                             'include_unvetted':False,'windows':[dict(zip(('country','state','date_from','date_to'),v)) for v in windows],
                             'instructions':'Request all species for these regions and complete date windows. Include sampling-event data. Extract the downloaded archive and retain its terms and citation. If a window extends beyond the release, use a covering release or an explicitly revised analysis window.'},
            'providers':{'ebird':source,
              'ecology':{'status':'PLANNED','reason':f"{len(scope['weather_queries'])} unique point/date weather requests; {len(scope['birdcast_queries'])} unique state/night migration requests"},
              'phenology':{'status':'DISABLED' if not opts['phenology'] else ('PLANNED' if os.environ.get('EBIRDST_ACCESS_KEY') else 'NEEDS_ACCESS'),
                           'reason':'Reference annual cycle version '+str(opts['phenology_year'])+'; use EBIRDST_ACCESS_KEY in the runner environment, or existing cached rasters. Host names are resolved against the source taxonomy during preparation.'},
              'public_genotypes':{'status':'PLANNED','reason':'Snapshot public genotype metadata, then select host/region/month matches' if not opts['global_genotypes'] else 'Explicit global public comparison selected'},
              'outbreak':{'status':'PLANNED','reason':'Retrieve the official APHIS CSV when downloads are allowed; use a validated saved snapshot if unavailable. A supplied CSV overrides automatic retrieval.'},
              'run_genotypes':{'status':'AFTER_ANALYSIS','reason':'Computed from the run GenoFLU calls; no external download. Pairing is optional.'}}}

    for name in PROVIDERS:
        if not source_enabled(opts,name):proposal['providers'][name]={'status':'DISABLED','reason':'Not selected'}
    return proposal


def scoped_genotypes(data,scope):
    """Conservative OR over host/region/month windows; never widen empty matches."""
    def norm(v):return re.sub(r'[^a-z0-9]+',' ',str(v).casefold()).strip()
    def matches(group,r):
        month=group.get('month')
        if not month or not r['date_from'][:7]<=month<=r['date_to'][:7]:return False
        if norm(r['host']) in ('','unknown','na','none','n a'):return False
        if norm(group.get('host')) not in {norm(v) for v in r.get('host_labels',[r['host']])}:return False
        loc=norm(group.get('location',''))
        countries={'US':['us','usa','united states','united states of america'],'CA':['ca','canada']}.get(r['country'],[norm(r['country'])])
        if not any(re.search(r'(?:^| )'+re.escape(c)+r'(?: |$)',loc) for c in countries):return False
        if r['state']=='Unknown':return True
        return any(re.search(r'(?:^| )'+re.escape(norm(s))+r'(?: |$)',loc) for s in (r['state'],r['state_name']))
    groups=[g for g in data['groups'] if any(matches(g,r) for r in scope['scopes'])]
    result=dict(data);result['source_audit']=data['audit'];result['groups']=groups
    counts=Counter()
    for g in groups:counts[g['status']]+=g['n']
    result['audit']={'included_runs':sum(counts.values()),'assigned_runs':counts['assigned'],
                     'status_counts':dict(counts),'assigned_runs_missing_collection_date':0}
    result['context_scope']={'metadata_sha256':scope['metadata_sha256'],'matching':'exact normalized host and region labels; collection-month overlap; no automatic widening',
                              'windows':scope['scopes'],'excluded_runs':data['audit']['included_runs']-sum(counts.values())}
    load('refresh_genotype_frequencies.py')['validate_snapshot'](result)
    return result


def command(args,log,timeout=900,env=None):
    with Path(log).open('w') as f:
        p=subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,env=env)
    if p.returncode:raise ValueError('Provider command failed; see '+Path(log).name)


def import_ebird(metadata,opts):
    directory=Path(opts['ebird_source']).expanduser().resolve()
    if not opts['all_species_confirmed']:raise ValueError('Confirm all-species and geographic/date download coverage before importing')
    files=[p for p in directory.rglob('*') if p.is_file() and not p.is_symlink()]
    obs=[p for p in files if re.search(r'^ebd_.*rel[A-Z][a-z]{2}-\d{4}.*\.txt(?:\.gz)?$',p.name) and 'sampling' not in p.name.lower()]
    sed=[p for p in files if 'sampling' in p.name.lower() and re.search(r'\.txt(?:\.gz)?$',p.name)]
    docs=[p.parent for p in files if p.name=='terms_of_use.txt' and (p.parent/'recommended_citation.txt').is_file()]
    if len(obs)!=1 or len(sed)!=1 or len(set(docs))!=1:raise ValueError('Use one extracted release folder containing one EBD file, one sampling file, and matching terms/citation documents')
    labels=[re.findall(r'rel([A-Z][a-z]{2}-\d{4})',p.name) for p in (obs[0],sed[0])]
    if not labels[0] or not labels[1] or labels[0]!=labels[1]:raise ValueError('EBD and sampling filenames must identify the same release')
    destination=cache_root()/'ebird'/(labels[0][0]+'-'+sha(metadata)[:12]+'-'+uuid.uuid4().hex[:6])
    api=load('ebird_context_package.py')
    args=argparse.Namespace(command='build',output=destination,documents=docs[0],observations=obs[0],sampling=sed[0],
         metadata=Path(metadata),days=opts['days'],release=labels[0][0],taxonomy_version='unknown',acquired_at='unknown')
    api['prepare'](args)
    return str(destination)


def normalized_metadata(source,destination):
    """Use the production validator and the same sorted sample order as Snakefile."""
    with Path(source).open(encoding='utf-8-sig',newline='') as f:
        samples=sorted((r.get('sample_id') or '').strip() for r in csv.DictReader(f,delimiter='\t'))
    if any(',' in x for x in samples):raise ValueError('Sample IDs cannot contain commas')
    runtime=SimpleNamespace(input=SimpleNamespace(metadata=str(source)),
        output=SimpleNamespace(validated=str(destination),report=str(destination.with_suffix('.qc.tsv'))),
        params=SimpleNamespace(samples=','.join(samples),require_all_samples='true'))
    runpy.run_path(str(ROOT/'scripts/validate_metadata.py'),init_globals={'snakemake':runtime},run_name='__main__')
    return destination


def prepare(metadata,directory,settings=None,progress=None,executor=command):
    """Write a new immutable selection; preserve previous snapshots on failure."""
    metadata=Path(metadata).resolve();directory=Path(directory).resolve();opts=options(settings)
    proposal=plan(metadata,opts);identity=proposal['metadata_sha256'];statuses={};cache=cache_root()
    store=directory/'snapshots';store.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='.preparing-',dir=store) as tmp:
        stage=Path(tmp);artifacts={'validated_metadata':'validated_metadata.tsv'}
        original_metadata=metadata
        metadata=normalized_metadata(metadata,stage/'validated_metadata.tsv')
        def event(provider,status,reason,**metrics):
            statuses[provider]={'status':status,'reason':reason,**metrics}
            if progress:progress({'status':'PREPARING','providers':statuses,'active_provider':provider})
        def attempt(provider,fn):
            if not source_enabled(opts,provider):
                event(provider,'DISABLED','Not selected');return
            event(provider,'PREPARING','Preparing metadata-matched context')
            try:fn()
            except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as e:
                event(provider,'UNAVAILABLE',str(e)[:500])
        def ecology():
            args=[sys.executable,str(ROOT/'scripts/build_ecological_context.py'),'--metadata',str(metadata),'--output',str(stage/'ecology.json'),
                  '--cache-dir',str(cache/'ecology'),'--days',str(opts['days'])]
            args+=['--fetch-weather','--fetch-birdcast'] if opts['network'] else ['--birdcast-cache']
            executor(args,stage/'ecology.log')
            data=json.loads((stage/'ecology.json').read_text())
            counts=Counter(v.get('status') for v in data.get('bindings',{}).values())
            migration=Counter(v.get('status') for v in data.get('birdcast',{}).get('bindings',{}).values())
            ready=counts['READY']+migration['AVAILABLE'];expected=2*proposal['sample_count']
            artifacts['ecology']='ecology.json'
            event('ecology','READY' if ready==expected else ('PARTIAL' if ready else 'UNAVAILABLE'),
                  f"Weather {counts['READY']}/{proposal['sample_count']}; migration {migration['AVAILABLE']}/{proposal['sample_count']} sample bindings available. See per-sample reasons in the snapshot.", weather_ready=counts['READY'],migration_ready=migration['AVAILABLE'],sample_count=proposal['sample_count'])
        attempt('ecology',ecology)
        def genotypes():
            args=[sys.executable,str(ROOT/'scripts/refresh_genotype_frequencies.py'),'--seed',str(ROOT/'assets/data/genotype-frequencies.json'),
                  '--output',str(stage/'source_genotypes.json'),'--cache-dir',str(cache/'genotypes')]
            if not opts['network']:args.append('--offline')
            executor(args,stage/'genotypes.log')
            source=json.loads((stage/'source_genotypes.json').read_text());load('refresh_genotype_frequencies.py')['validate_snapshot'](source)
            data=source if opts['global_genotypes'] else scoped_genotypes(source,proposal)
            write(stage/'genotypes.json',data);artifacts['genotypes']='genotypes.json';artifacts['genotype_source']='source_genotypes.json'
            n=data['audit']['included_runs'];refresh=source.get('report_refresh',{})
            event('public_genotypes','READY' if n else 'UNAVAILABLE',f"{n} public SRA runs in the selected comparison; source refresh: {refresh.get('status','unknown')}; retrieved/built: {source.get('fetched_at') or source.get('built_at') or 'not recorded'}. Frequencies describe included records, not population prevalence.", included_runs=n)
        attempt('public_genotypes',genotypes)
        # A schema-valid empty snapshot is explicit unavailability, never invented observations.
        if 'genotypes' not in artifacts:
            empty={'schema_version':'wings.genotype-frequencies.v1','unit':'SRA run','has_metadata':True,'groups':[],
                   'audit':{'included_runs':0,'assigned_runs':0,'status_counts':{}},
                   'context_scope':{'unavailable':True,'reason':statuses['public_genotypes']['reason']}}
            write(stage/'genotypes.json',empty);artifacts['genotypes']='genotypes.json'
        def phenology():
            if not opts['phenology']:event('phenology','DISABLED','Phenology not selected');return
            if not opts['network']:event('phenology','UNAVAILABLE','Offline preparation does not invoke the phenology downloader; reuse an existing prepared selection');return
            raster_cache=Path(os.environ.get('WINGS_EBIRDST_CACHE','~/.cache/wings/ebirdst')).expanduser()
            if not os.environ.get('EBIRDST_ACCESS_KEY') and not next(raster_cache.glob('**/*.tif'),None):
                event('phenology','NEEDS_ACCESS','Set EBIRDST_ACCESS_KEY before starting the runner, then prepare again');return
            engine=shutil.which('snakemake')
            if not engine:raise ValueError('Snakemake is needed to prepare the phenology environment')
            request={'metadata':str(metadata),'output':str(stage/'phenology.json'),'cache':str(raster_cache.resolve()),
                     'year':opts['phenology_year'],'repo':str(ROOT)}
            write(stage/'phenology_request.json',request)
            executor([engine,'--snakefile',str(ROOT/'scripts/context_phenology.smk'),'--directory',str(stage),'--cores','1','--use-conda',
                      '--conda-prefix',str(ROOT/'.snakemake'/'conda-platforms'/(platform.system().lower()+'-'+platform.machine().lower())),
                      '--profile','none','--workflow-profile','none','--configfile',str(stage/'phenology_request.json')],stage/'phenology.log',timeout=3600)
            data=json.loads((stage/'phenology.json').read_text());n=data.get('summary',{}).get('ready_profile_count',0)
            artifacts['phenology']='phenology.json'
            event('phenology','READY' if n>=proposal['sample_count'] else ('PARTIAL' if n else 'UNAVAILABLE'),f'{n} reference phenology profiles; reference version {opts["phenology_year"]}',ready_profiles=n,sample_count=proposal['sample_count'])
        attempt('phenology',phenology)
        def ebird():
            selection=find_ebird(metadata,opts)
            if selection['status']!='READY' and opts['ebird_source']:
                opts['ebird_package']=import_ebird(metadata,opts);selection=find_ebird(metadata,opts)
            statuses['ebird']=selection
            if progress:progress({'status':'PREPARING','providers':statuses,'active_provider':'ebird'})
        attempt('ebird',ebird)
        def outbreak():
            import aphis_data
            override=Path(opts['outbreak_file']).expanduser() if opts['outbreak_file'] else None
            if override is not None and not override.is_file():
                event('outbreak','NEEDS_IMPORT','The selected APHIS CSV is missing. Choose it again or clear the override.');return
            record=aphis_data.prepare(stage,cache_root()/'aphis',network=opts['network'],override=override,
                                      bundled=ROOT/'resources/aphis/hpai-wild-birds.csv')
            if record['status']=='READY':
                artifacts['aphis']='aphis.csv';artifacts['aphis_provenance']='aphis.provenance.json'
            event('outbreak',record.pop('status'),record.pop('reason'),**record)
        attempt('outbreak',outbreak)
        if sha(original_metadata)!=identity:raise ValueError('Metadata changed during preparation; review and prepare again')
        blocked=[p for p in opts['required'] if statuses[p]['status']!='READY']
        selection={'schema':SCHEMA,'snapshot_id':token,'prepared_at':datetime.now(timezone.utc).isoformat(),'metadata_sha256':identity,
                   'options':opts,'plan':proposal,'providers':statuses,'artifacts':artifacts,
                   'files':{name:{'sha256':sha(stage/name),'size_bytes':(stage/name).stat().st_size} for name in artifacts.values()},
                   'status':'BLOCKED' if blocked else 'READY','blocked_sources':blocked}
        write(stage/'selection.json',selection)
        final=store/token;stage.rename(final)
    write(directory/'selection.json',{'schema':'wings.context-pointer.v1','snapshot_id':token,'selection_sha256':sha(final/'selection.json')})
    return selection


def selected(directory,metadata):
    directory=Path(directory).resolve();pointer=json.loads((directory/'selection.json').read_text())
    token=pointer.get('snapshot_id','')
    if not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('Invalid context snapshot identity')
    folder=directory/'snapshots'/token;path=folder/'selection.json'
    if folder.is_symlink() or path.is_symlink() or sha(path)!=pointer.get('selection_sha256'):raise ValueError('Context selection integrity check failed')
    data=json.loads(path.read_text())
    if data.get('schema')!=SCHEMA or data.get('metadata_sha256')!=sha(metadata):raise ValueError('Prepared context does not match current metadata')
    if data['status']!='READY':raise ValueError('Required context is not ready: '+', '.join(data['blocked_sources']))
    for name,record in data['files'].items():
        if Path(name).name!=name or (folder/name).is_symlink() or sha(folder/name)!=record['sha256']:
            raise ValueError('Prepared context file changed: '+name)
    return folder,data


def configure(config,directory,metadata):
    folder,data=selected(directory,metadata);artifacts=data['artifacts']
    config['context_setup']={'selection':str(folder/'selection.json'),'selection_sha256':sha(folder/'selection.json')}
    config['ecological_context']={'enabled':'ecology' in artifacts,'snapshot':str(folder/'ecology.json'),'auto_birdcast':False,'auto_weather':False,'offline':True}
    config['genomic_ecological_concordance']={**(config.get('genomic_ecological_concordance') or {}),
        'auto_weather':False,'auto_phenology':False}
    config['phenology']={'enabled':False,'snapshot':str(folder/'phenology.json') if 'phenology' in artifacts else ''}
    config['genotype_frequencies']={'snapshot':str(folder/'genotypes.json'),'prepared_snapshot':True,'auto_refresh':False,'offline':True}
    ebird=data['providers']['ebird'];package=ebird.get('path') or str(cache_root()/'ebird'/'not-prepared')
    config['ebird']={'mode':'reuse' if ebird['status']=='READY' else 'off','context_dir':package,'required':'ebird' in data['options']['required'],'days':data['options']['days']}
    if ebird['status']=='READY':
        # Detect package replacement even when its new contents pass ordinary validation.
        current=load('ebird_context_package.py')['verify'](package,metadata,data['options']['days'])
        if current['package_id']!=ebird['package_id']:raise ValueError('Selected eBird package changed; prepare again')
    config['outbreak_context']={'enabled':'aphis' in artifacts,'csv':str(folder/'aphis.csv')}
    if 'aphis_provenance' in artifacts:config['outbreak_context']['provenance']=str(folder/'aphis.provenance.json')
    return config


def validate_config(config,metadata,samples=None):
    """Fail early if a prepared terminal run references changed or different evidence."""
    settings=config.get('context_setup') or {}
    path=Path(settings['selection']).expanduser().resolve()
    if sha(path)!=settings.get('selection_sha256'):raise ValueError('Prepared context selection changed; prepare again')
    data=json.loads(path.read_text());folder=path.parent
    if data.get('schema')!=SCHEMA or data.get('metadata_sha256')!=sha(metadata):raise ValueError('Prepared context metadata does not match this run')
    if data.get('status')!='READY':raise ValueError('Prepared context is blocked')
    if samples is not None and sorted(samples)!=data['plan']['sample_ids']:
        raise ValueError('Prepared context sample IDs do not match discovered FASTQ inputs')
    for name,record in data['files'].items():
        if Path(name).name!=name or (folder/name).is_symlink() or sha(folder/name)!=record['sha256']:
            raise ValueError('Prepared context artifact changed: '+name)
    for artifact,section,key in [('genotypes','genotype_frequencies','snapshot'),('ecology','ecological_context','snapshot'),
                                 ('phenology','phenology','snapshot'),('aphis','outbreak_context','csv')]:
        if artifact in data['artifacts']:
            configured=Path((config.get(section) or {}).get(key) or '.').expanduser().resolve()
            if configured!=(folder/data['artifacts'][artifact]).resolve():raise ValueError('Prepared context path differs from selection: '+section)
    ebird=data['providers']['ebird']
    if ebird['status']=='READY':
        package=(config.get('ebird') or {}).get('context_dir','')
        current=load('ebird_context_package.py')['verify'](package,metadata,data['options']['days'])
        if current['package_id']!=ebird['package_id']:raise ValueError('Prepared eBird package changed')
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','prepare']);p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--output-dir',type=Path);p.add_argument('--options',type=Path);p.add_argument('--config-out',type=Path)
    args=p.parse_args();opts=json.loads(args.options.read_text()) if args.options else {}
    if args.action=='plan':print(json.dumps(plan(args.metadata,opts),indent=2))
    else:
        if not args.output_dir:p.error('prepare requires --output-dir')
        result=prepare(args.metadata,args.output_dir,opts,progress=lambda p:print(json.dumps(p),flush=True))
        print('Context preparation:',result['status'])
        if args.config_out:
            import yaml
            if args.config_out.exists():raise ValueError('Config output exists; choose a new filename')
            config=configure({},args.output_dir,args.metadata)
            config['metadata_file']=str(args.metadata.resolve())
            args.config_out.write_text(yaml.safe_dump(config,sort_keys=False))
            print('Context configuration:',args.config_out)


if __name__=='__main__':main()
