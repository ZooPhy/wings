#!/usr/bin/env python3
"""Opt-in BEAST 2 dating conditional on a fixed rooted topology (not fixed node dates)."""
from __future__ import annotations
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

DEFAULTS=dict(enabled=False, analyses=['HA/balanced/replicate_1'], run_id='initial', chains=2,
    chain_length=5000000, log_every=1000, burnin=.1, seed=73129, threads=2,
    clock_rate_median=.003, clock_rate_log_sd=1.5, population_median=1., population_log_sd=2.,
    max_rhat=1.01, min_bulk_ess=400, min_tail_ess=400, min_chain_ess=100,
    beast_command=['beast'], prior_only=False)
ID=re.compile(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/replicate_[1-9][0-9]*\Z')

def configuration(raw=None):
    raw={} if raw is None else raw
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS): raise ValueError('Unknown bayesian_dating configuration')
    c=dict(DEFAULTS,**raw)
    for k in ('enabled','prior_only'):
        if type(c[k]) is not bool: raise ValueError(k+' must be boolean')
    if not isinstance(c['analyses'],list) or not c['analyses'] or len(set(c['analyses']))!=len(c['analyses']) or any(not isinstance(s,str) or not ID.fullmatch(s) for s in c['analyses']): raise ValueError('Invalid analysis IDs')
    if not isinstance(c['run_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]+',c['run_id']):raise ValueError('Invalid run_id')
    for k in ('chains','chain_length','log_every','seed','threads','min_bulk_ess','min_tail_ess','min_chain_ess'):
        if type(c[k]) is not int or c[k]<1: raise ValueError(k+' must be a positive integer')
    if not 2<=c['chains']<=8: raise ValueError('Use 2–8 independent chains')
    if c['chain_length']%c['log_every'] or c['chain_length']//c['log_every']<100:raise ValueError('chain_length must be divisible by log_every and provide at least 100 logging intervals')
    for k in ('burnin','clock_rate_median','clock_rate_log_sd','population_median','population_log_sd','max_rhat'):
        if type(c[k]) not in (int,float) or not math.isfinite(c[k]):raise ValueError(k+' must be finite')
    if not 0<=c['burnin']<.5 or not 1<c['max_rhat']<=1.05:raise ValueError('Invalid burn-in or R-hat threshold')
    if min(c[k] for k in ('clock_rate_median','clock_rate_log_sd','population_median','population_log_sd'))<=0:raise ValueError('Prior parameters must be positive')
    if not isinstance(c['beast_command'],list) or not c['beast_command'] or any(not isinstance(v,str) or not v for v in c['beast_command']):raise ValueError('beast_command must be an argument list')
    return c


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');temp.replace(path)
def numeric_date(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00')) if 'T' in value else datetime.combine(date.fromisoformat(value),datetime.min.time(),timezone.utc)
    if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
    a=datetime(d.year,1,1,tzinfo=timezone.utc);b=datetime(d.year+1,1,1,tzinfo=timezone.utc)
    return d.year+(d-a).total_seconds()/(b-a).total_seconds()
def calendar(value):
    year=math.floor(value)
    if not 1<=year<9999:raise ValueError('Posterior date outside supported calendar')
    a=datetime(year,1,1);b=datetime(year+1,1,1)
    return (a+(b-a)*(value-year)).isoformat(timespec='seconds')+'Z'


def alignment(path):
    out={};key=None
    for line in Path(path).read_text().splitlines():
        if line.startswith('>'):
            key=line[1:].split()[0]
            if not re.fullmatch(r'[A-Za-z0-9_-]+',key) or key in out:raise ValueError('Unsafe or duplicate alignment ID')
            out[key]=''
        elif line.strip():
            if key is None:raise ValueError('FASTA sequence before header')
            out[key]+=line.strip().upper()
    if len(out)<3 or len(set(map(len,out.values())))!=1 or not next(iter(out.values())):raise ValueError('Alignment must have ≥3 equal-length sequences')
    if any(set(s)-set('ACGTRYSWKMBDHVN-?') for s in out.values()):raise ValueError('Unexpected nucleotide symbol')
    return out


def rooted_nodes(nodes,require_binary=True):
    by={n['id']:dict(n,children=[]) for n in nodes}
    if len(by)!=len(nodes):raise ValueError('Duplicate dated node IDs')
    roots=[n for n in by.values() if n['parent'] is None]
    if len(roots)!=1:raise ValueError('Expected one rooted tree')
    for n in by.values():
        if n['parent'] is not None:
            if n['parent'] not in by:raise ValueError('Missing parent')
            by[n['parent']]['children'].append(n['id'])
    seen=set();order=[]
    def walk(k):
        if k in seen:raise ValueError('Cycle in dated tree')
        seen.add(k);order.append(k)
        children=by[k]['children']
        if children and (len(children)<2 or (require_binary and len(children)!=2)):raise ValueError('A strictly bifurcating topology is required; no automatic resolutions are made')
        for child in children:walk(child)
    walk(roots[0]['id'])
    if len(seen)!=len(by):raise ValueError('Disconnected dated tree')
    return by,order


def dating_topology(nodes,ml_path):
    """Recover only an existing ML refinement, retaining the dated root bipartition."""
    by,order=rooted_nodes(nodes,require_binary=False)
    multifurcations=[k for k in order if len(by[k]['children'])>2]
    if not multifurcations:
        return by,order,dict(method='dated_binary_tree',restored_nodes=0)
    if len(by[order[0]]['children'])!=2:
        raise ValueError('The dated root must define two sides; cannot infer a root for an unresolved root polytomy')
    if not Path(ml_path).is_file():raise ValueError('A multifurcating dated tree requires its original ml.treefile')
    dated_sets={}
    for k in reversed(order):
        dated_sets[k]=frozenset().union(*(dated_sets[c] for c in by[k]['children'])) if by[k]['children'] else frozenset([k])
    original=parse_newick(Path(ml_path).read_text(),require_binary=False)
    graph={};labels={}
    def collect(node,parent=None):
        i=len(graph);graph[i]=[];labels[i]=node['name'] if not node['children'] else None
        if parent is not None:graph[i].append(parent);graph[parent].append(i)
        for child in node['children']:collect(child,i)
    collect(original)
    tips=[name for name in labels.values() if name is not None]
    if len(tips)!=len(set(tips)) or set(tips)!=set(dated_sets[order[0]]):
        raise ValueError('Original ML and dated tree tips differ')
    # A Newick display root may subdivide an unrooted edge; suppress only that root.
    if len(graph[0])==2 and labels[0] is None:
        a,z=graph.pop(0);labels.pop(0)
        graph[a].remove(0);graph[z].remove(0);graph[a].append(z);graph[z].append(a)
    if any(len(adj)!=(1 if labels[i] is not None else 3) for i,adj in graph.items()):
        raise ValueError('Original ML tree is not fully bifurcating; no arbitrary resolution is permitted')
    def side(i,parent):
        return frozenset([labels[i]]) if labels[i] is not None else frozenset().union(*(side(j,i) for j in graph[i] if j!=parent))
    target=dated_sets[by[order[0]]['children'][0]]
    complement=dated_sets[order[0]]-target
    edges=[(i,j) for i in graph for j in graph[i] if i<j and side(i,j) in (target,complement)]
    if len(edges)!=1:raise ValueError('Dated root split does not identify one unique original ML edge')
    def orient(i,parent):
        children=[orient(j,i) for j in graph[i] if j!=parent]
        leaves=frozenset([labels[i]]) if labels[i] is not None else frozenset().union(*(c['leaves'] for c in children))
        return dict(leaves=leaves,children=sorted(children,key=lambda c:tuple(sorted(c['leaves']))))
    a,z=edges[0];tree=dict(leaves=dated_sets[order[0]],children=[orient(a,z),orient(z,a)])
    recovered_sets=set()
    def gather(n):
        recovered_sets.add(n['leaves'])
        for child in n['children']:gather(child)
    gather(tree)
    if not set(dated_sets.values())<=recovered_sets:
        raise ValueError('Original ML topology conflicts with a retained dated clade; cannot restore it')
    known={leaves:k for k,leaves in dated_sets.items()};rebuilt=[];restored=[]
    def emit(n,parent=None,parent_date=None):
        if n['leaves'] in known:
            node={k:v for k,v in by[known[n['leaves']]].items() if k!='children'}
        else:
            key='ml_restored_'+hashlib.sha256('\n'.join(sorted(n['leaves'])).encode()).hexdigest()[:20]
            if key in by:raise ValueError('Restored-node identifier collision')
            node=dict(id=key,date=parent_date)
            restored.append(dict(id=key,descendant_tips=sorted(n['leaves'])))
        node['parent']=parent;rebuilt.append(node)
        for child in n['children']:emit(child,node['id'],node['date'])
    emit(tree)
    restored_by,restored_order=rooted_nodes(rebuilt)
    audit=dict(method='original_ml_refinement_at_dated_root',ml_sha256=digest(ml_path),
        dated_multifurcations=len(multifurcations),restored_nodes=len(restored),
        root_sides=[sorted(target),sorted(complement)],nodes=restored,
        initialization='Restored nodes start at the dated parent time; starting-tree heights open positive branches. These are starting values, not calibrations.',
        scope='Conditional on original ML refinements, including weak or zero-length branches; topology uncertainty is not integrated.')
    return restored_by,restored_order,audit


def load_inputs(inference,selection):
    inference=Path(inference);selection=Path(selection)
    record=json.loads((inference/'result.json').read_text())
    if record.get('status')!='complete':raise ValueError('Bayesian dating requires a completed, screened reconstruction')
    seqs=alignment(inference/'alignment.fasta')
    with (selection/'tips.tsv').open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
    meta={r['id']:r for r in rows}
    if len(meta)!=len(rows) or set(meta)!=set(seqs):raise ValueError('Alignment and metadata IDs differ')
    dates={k:numeric_date(r['date']) for k,r in meta.items()}
    if len(set(dates.values()))<2:raise ValueError('At least two collection dates required')
    nodes=json.loads((inference/'dated_nodes.json').read_text());by,order,topology_audit=dating_topology(nodes,inference/'ml.treefile')
    tips={k for k,n in by.items() if not n['children']}
    if tips!=set(seqs):raise ValueError('Dated topology and alignment tips differ')
    samples=record.get('focal_sample_ids',[])
    if len(samples)<2 or len(set(samples))!=len(samples):raise ValueError('Invalid WINGS sample set')
    focal=[k for k in seqs if meta[k].get('sample_id') in samples]
    if len(focal)!=len(samples) or {meta[k]['sample_id'] for k in focal}!=set(samples):raise ValueError('Not all WINGS samples matched exactly once')
    if {by[k].get('sample_id') for k in focal}!=set(samples):raise ValueError('Study labels differ between metadata and tree')
    for k in tips:
        if abs(numeric_date(by[k]['date'])-dates[k])>2/365.25:raise ValueError('Dated tip disagrees with metadata: '+k)
    hashes={str(p.name):digest(p) for p in [inference/'alignment.fasta',inference/'dated_nodes.json',inference/'result.json',selection/'tips.tsv']}
    if topology_audit['restored_nodes']:hashes['ml.treefile']=digest(inference/'ml.treefile')
    return dict(record=record,seqs=seqs,dates=dates,nodes=by,order=order,focal=sorted(focal),input_sha256=hashes,topology_audit=topology_audit)


def starting_tree(inp,factor=1.):
    latest=max(inp['dates'].values());heights={}
    for k in reversed(inp['order']):
        n=inp['nodes'][k]
        if not n['children']:heights[k]=latest-inp['dates'][k]
        else:
            initial=latest-numeric_date(n['date'])
            if any(numeric_date(inp['nodes'][c]['date'])<numeric_date(n['date'])-1e-9 for c in n['children']):raise ValueError('Child predates parent')
            heights[k]=max(initial*factor,max(heights[c] for c in n['children'])+1e-7)
    def emit(k):
        n=inp['nodes'][k];label='('+','.join(emit(c) for c in n['children'])+')' if n['children'] else k
        return label+(':'+format(heights[n['parent']]-heights[k],'.16g') if n['parent'] is not None else '')
    return emit(inp['order'][0])+';'


def xml_model(inp,c,chain):
    if not 1<=chain<=c['chains']:raise ValueError('Invalid chain index')
    root=ET.Element('beast',version='2.7',namespace='beast.base.core:beast.base.inference:beast.base.inference.parameter:beast.base.inference.distribution:beast.base.evolution.alignment:beast.base.evolution.tree:beast.base.evolution.operator:beast.base.inference.operator:beast.base.evolution.sitemodel:beast.base.evolution.substitutionmodel:beast.base.evolution.likelihood:beast.base.evolution.branchratemodel:beast.base.evolution.tree.coalescent')
    def add(p,tag,**attrs):return ET.SubElement(p,tag,{k:str(v) for k,v in attrs.items()})
    data=add(root,'data',id='alignment',spec='Alignment',dataType='nucleotide')
    for k,seq in inp['seqs'].items():add(data,'sequence',id='seq_'+k,spec='Sequence',taxon=k,totalcount=4,value=seq)
    add(root,'taxonset',id='taxa',spec='TaxonSet',alignment='@alignment')
    run=add(root,'run',id='mcmc',spec='MCMC',chainLength=c['chain_length'],storeEvery=c['log_every']*10,sampleFromPrior=str(c['prior_only']).lower())
    state=add(run,'state',id='state',storeEvery=c['log_every']*10)
    factor=.7+(.7*(chain-1)/(c['chains']-1))
    tree=add(state,'tree',name='stateNode',id='tree',spec='TreeParser',taxonset='@taxa',newick=starting_tree(inp,factor),IsLabelledNewick='true',adjustTipHeights='false',binarizeMultifurcations='false')
    add(tree,'trait',id='dates',spec='TraitSet',traitname='date-forward',taxa='@taxa',value=','.join(k+'='+format(inp['dates'][k],'.15g') for k in inp['seqs']))
    for id,value,dim in [('clockRate',c['clock_rate_median']/factor,1),('popSize',c['population_median']*factor,1),('kappa',2*factor,1),('gammaShape',factor,1),('frequencies','0.25 0.25 0.25 0.25',4)]:
        add(state,'parameter',name='stateNode',id=id,spec='RealParameter',value=value,dimension=dim,lower=0.)
    posterior=add(run,'distribution',id='posterior',spec='CompoundDistribution')
    prior=add(posterior,'distribution',id='prior',spec='CompoundDistribution')
    coal=add(prior,'distribution',id='coalescent',spec='Coalescent')
    add(coal,'treeIntervals',id='intervals',spec='TreeIntervals',tree='@tree')
    add(coal,'populationModel',id='population',spec='ConstantPopulation',popSize='@popSize')
    for name,median,sd in [('clockRate',c['clock_rate_median'],c['clock_rate_log_sd']),('popSize',c['population_median'],c['population_log_sd']),('kappa',2.,1.25)]:
        pr=add(prior,'distribution',id=name+'Prior',spec='Prior',x='@'+name)
        add(pr,'distr',spec='LogNormalDistributionModel',M=math.log(median),S=sd,meanInRealSpace='false')
    pr=add(prior,'distribution',id='shapePrior',spec='Prior',x='@gammaShape');add(pr,'distr',spec='Exponential',mean=1.)
    pr=add(prior,'distribution',id='frequencyPrior',spec='Prior',x='@frequencies');add(pr,'distr',spec='Dirichlet',alpha='1 1 1 1')
    like=add(posterior,'distribution',id='likelihood',spec='CompoundDistribution')
    tl=add(like,'distribution',id='sequenceLikelihood',spec='TreeLikelihood',data='@alignment',tree='@tree',useAmbiguities='true')
    site=add(tl,'siteModel',id='siteModel',spec='SiteModel',gammaCategoryCount=4,shape='@gammaShape')
    hky=add(site,'substModel',id='hky',spec='HKY',kappa='@kappa')
    add(hky,'frequencies',spec='Frequencies',frequencies='@frequencies')
    add(tl,'branchRateModel',id='clock',spec='StrictClockModel',**{'clock.rate':'@clockRate'})
    # No exchange, subtree-slide, Wilson-Balding or any other topology operator.
    for name in ('clockRate','popSize','kappa','gammaShape'):
        add(run,'operator',id=name+'Scaler',spec='beast.base.evolution.operator.ScaleOperator',parameter='@'+name,scaleFactor=.75,weight=3.)
    add(run,'operator',id='frequencyMover',spec='beast.base.inference.operator.DeltaExchangeOperator',parameter='@frequencies',delta=.01,weight=3.)
    add(run,'operator',id='internalHeights',spec='beast.base.evolution.operator.Uniform',tree='@tree',weight=30.)
    add(run,'operator',id='rootScaler',spec='beast.base.evolution.operator.ScaleOperator',tree='@tree',rootOnly='true',scaleFactor=.75,weight=3.)
    add(run,'operator',id='treeScaler',spec='beast.base.evolution.operator.ScaleOperator',tree='@tree',scaleFactor=.95,weight=3.)
    logger=add(run,'logger',id='trace',fileName='chain.log',logEvery=c['log_every'])
    for name in ('posterior','likelihood','prior','clockRate','popSize','kappa','gammaShape','frequencies'):
        if name=='likelihood' and c['prior_only']:continue
        add(logger,'log',idref=name)
    add(logger,'log',id='rootHeight',spec='TreeHeightLogger',tree='@tree')
    logger=add(run,'logger',id='trees',fileName='chain.trees',mode='tree',logEvery=c['log_every']);add(logger,'log',idref='tree')
    logger=add(run,'logger',id='screen',logEvery=c['log_every']*10)
    for name in ('posterior','clockRate','rootHeight'):add(logger,'log',idref=name)
    ET.indent(root)
    return ET.tostring(root,encoding='unicode')+'\n'


def resolve_beast_command(command, prefix=None):
    """Use the pinned Conda package's JAR with native Conda Java, not its bundled launcher.

    Some noarch distributions include a platform-specific Java runtime. The
    package file inventory identifies the JAR without guessing its install path.
    Explicit custom command lists are preserved.
    """
    if command != ['beast']:
        return list(command)
    prefix=Path(prefix or sys.prefix).resolve()
    records=sorted((prefix/'conda-meta').glob('beast2-*.json'))
    if not records:
        return [shutil.which('beast') or 'beast']
    if len(records)!=1:raise ValueError('Ambiguous Conda BEAST installation; rebuild the dating environment.')
    record=json.loads(records[0].read_text())
    if record.get('name')!='beast2' or record.get('version')!='2.7.7':
        raise ValueError('The dating environment must contain BEAST 2.7.7.')
    jars=[]
    for relative in record.get('files',[]):
        if Path(relative).name!='launcher.jar':continue
        path=(prefix/relative).resolve()
        if not path.is_relative_to(prefix):raise ValueError('BEAST JAR resolves outside the active Conda environment.')
        if path.is_file():jars.append(path)
    jars=list(dict.fromkeys(jars))
    if len(jars)!=1:raise ValueError('Expected one launcher.jar in the installed BEAST 2.7.7 package; found '+str(len(jars)))
    java_records=sorted((prefix/'conda-meta').glob('openjdk-*.json'))
    candidates=[]
    if java_records:
        for metadata in java_records:
            package=json.loads(metadata.read_text())
            if package.get('name')!='openjdk':continue
            paths=list(package.get('files',[]))
            paths.extend(item['_path'] for item in package.get('paths_data',{}).get('paths',[]) if '_path' in item)
            candidates.extend(prefix/name for name in paths if Path(name).parts[-2:]==('bin','java'))
    else:
        candidates=[prefix/'bin/java']
    usable=[]
    for candidate in candidates:
        path=candidate.resolve()
        if not path.is_relative_to(prefix):
            raise ValueError('OpenJDK Java resolves outside the active Conda environment: '+str(candidate))
        if path.is_file() and os.access(path,os.X_OK) and path not in usable:usable.append(path)
    if len(usable)!=1:
        raise ValueError('Native Java discovery expected one executable in the installed OpenJDK package; found '+str(len(usable))+
                         '. Environment: '+str(prefix)+'; candidates: '+repr([str(p) for p in candidates]))
    java=usable[0]
    return headless_beast_command(java,jars[0])


def headless_beast_command(java,launcher):
    """Use BEAST's pinned core directly, without JavaFX or user-package discovery."""
    launcher=Path(launcher).resolve()
    base=launcher.parent/'packages/BEAST.base.jar'
    version=launcher.parent/'packages/BEAST.base.version.xml'
    bridge=Path(__file__).resolve().with_name('WingsBeast.java')
    for path in (launcher,base,version,bridge):
        if not path.is_file():raise ValueError('Missing headless BEAST runtime file: '+str(path))
    return [str(Path(java).resolve()),'-Djava.awt.headless=true',
            '-Dwings.beast.base.version='+str(version),'-cp',
            os.pathsep.join(map(str,(launcher,base))),str(bridge)]


def log_tail(path):
    with Path(path).open('rb') as f:
        f.seek(0,2);f.seek(max(0,f.tell()-6000))
        return f.read().decode('utf-8',errors='replace').strip()


def logged_beast(command,out,name):
    """Keep engine stderr in both the saved log and the raised error."""
    logpath=Path(out)/name
    try:
        with logpath.open('w') as log:
            result=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT)
    except OSError as error:
        raise ValueError('Could not execute BEAST: '+str(error)+'; command: '+repr(command)) from error
    if result.returncode:
        raise ValueError('BEAST failed (exit '+str(result.returncode)+'); command: '+repr(command)+'; log: '+str(logpath)+'\n'+log_tail(logpath))


def run_chain(inference,selection,out,c,chain,validate_only=False,threads=None):
    c=configuration(c);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    inp=load_inputs(inference,selection);xml=xml_model(inp,c,chain)
    manifest=dict(schema='wings.bayesian-dating-chain.v1',analysis=inp['record']['id'],config=c,chain=chain,
        seed=c['seed']+chain*1009,inputs=inp['input_sha256'],xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),
        focal_sample_ids=inp['record']['focal_sample_ids'],focal_tip_ids=inp['focal'],tip_dates=inp['dates'],
        topology_audit=inp['topology_audit'],rooted_topology=starting_tree(inp),latest_tip=max(inp['dates'].values()),
        model='HKY+Gamma4; strict clock; constant coalescent; fixed rooted topology',
        interval_scope='Conditional on rooted topology, selected reference set, clock/substitution model and priors')
    previous=out/'manifest.json'
    if previous.exists() and json.loads(previous.read_text())!=manifest:raise ValueError('Run inputs or settings changed. Choose a new bayesian_dating.run_id; existing chains are preserved.')
    completion=out/'complete.json'
    if completion.exists():
        saved=json.loads(completion.read_text())
        if saved.get('status')=='complete' and saved.get('manifest_sha256')==digest(previous) and set(saved.get('output_sha256',{}))=={'chain.log','chain.trees'} and all((out/k).is_file() and digest(out/k)==v for k,v in saved['output_sha256'].items()):return saved
        raise ValueError('Completed chain provenance differs. Choose a new run_id.')
    if (out/'chain.log').exists() or (out/'chain.trees').exists():raise ValueError('Interrupted chain outputs preserved. Choose a new run_id; no automatic overwrite or unsafe resume.')
    write(previous,manifest);(out/'input.xml').write_text(xml)
    resolved=resolve_beast_command(c['beast_command'])
    logged_beast(resolved+['-version'],out,'version.log')
    version_text=(out/'version.log').read_text()
    if not re.search(r'\bv?2\.7\.7\b',version_text):raise ValueError('This generator is pinned to BEAST 2.7.7; detected: '+version_text[:300])
    logged_beast(resolved+['-java','-validate','input.xml'],out,'validation.log')
    if validate_only:return dict(status='validated',analysis=inp['record']['id'])
    command=resolved+['-java','-threads',str(min(c['threads'],threads or c['threads'])),'-seed',str(manifest['seed']),'-overwrite','input.xml']
    logged_beast(command,out,'tools.log')
    states,_=read_trace(out/'chain.log',c)
    if states[-1]!=c['chain_length']:raise ValueError('Chain did not reach requested length')
    if not (out/'chain.trees').is_file():raise ValueError('Missing sampled trees')
    done=dict(status='complete',command=command,beast_version=version_text.strip(),manifest_sha256=digest(previous),
              output_sha256={k:digest(out/k) for k in ('chain.log','chain.trees')})
    write(completion,done);return done


def read_trace(path,c):
    lines=[s for s in Path(path).read_text().splitlines() if s.strip() and not s.lstrip().startswith('#')]
    if not lines or lines[0].split()[0].lower() not in ('sample','state'):raise ValueError('Missing BEAST trace header')
    headers=lines[0].split();rows=[];states=[]
    if len(set(headers))!=len(headers):raise ValueError('Duplicate trace headers')
    for line in lines[1:]:
        parts=line.split()
        if len(parts)!=len(headers):raise ValueError('Truncated or malformed trace row')
        state=int(parts[0]);vals=list(map(float,parts[1:]))
        if not all(math.isfinite(x) for x in vals):raise ValueError('Nonfinite trace values')
        states.append(state);rows.append(vals)
    if states!=list(range(0,c['chain_length']+1,c['log_every'])):raise ValueError('Incomplete, duplicate, or irregular trace states')
    return states,{h:[r[i] for r in rows] for i,h in enumerate(headers[1:])}


def parse_newick(text,translate=None,require_binary=True):
    text=re.sub(r'\[[^\]]*\]','',text)
    tokens=re.findall(r"[(),:;]|'[^']*'|[^\s(),:;]+",text);i=0
    def read():
        nonlocal i
        kids=[];name=None
        if tokens[i]=='(':
            i+=1;kids.append(read())
            while tokens[i]==',':i+=1;kids.append(read())
            if tokens[i]!=')':raise ValueError('Malformed tree')
            i+=1
        if tokens[i] not in (',',')',':',';'):
            name=tokens[i].strip("'");i+=1
        length=0.
        if tokens[i]==':':i+=1;length=float(tokens[i]);i+=1
        if not math.isfinite(length) or length<0:raise ValueError('Invalid sampled branch length')
        if not kids:
            if translate:name=translate.get(name,name)
            if not name:raise ValueError('Unlabelled tip')
        elif require_binary and len(kids)!=2:raise ValueError('Sampled topology is not bifurcating')
        return dict(name=name,length=length,children=kids)
    try:root=read()
    except (IndexError,ValueError) as e:raise ValueError('Cannot parse sampled Newick') from e
    if i!=len(tokens)-1 or tokens[i]!=';':raise ValueError('Trailing or missing Newick tokens')
    return root


def tree_stats(root,dates,focal):
    distances={};clades=set();all_tips=[];focal=set(focal);mrca_depth=None;best=10**9
    def visit(n,depth):
        nonlocal mrca_depth,best
        if not n['children']:
            all_tips.append(n['name']);distances[n['name']]=depth;return frozenset([n['name']])
        leaves=frozenset().union(*(visit(c,depth+c['length']) for c in n['children']));clades.add(leaves)
        if focal<=leaves and len(leaves)<best:best=len(leaves);mrca_depth=depth
        return leaves
    visit(root,0.)
    if len(all_tips)!=len(set(all_tips)) or set(all_tips)!=set(dates) or mrca_depth is None:raise ValueError('Sampled tips differ from the declared taxon set')
    latest=max(dates.values());roots=[distances[k]+latest-dates[k] for k in dates]
    if max(roots)-min(roots)>1e-5:raise ValueError('Sampled tree tip heights disagree with collection dates')
    height=sum(roots)/len(roots)
    return latest-height+mrca_depth,latest-height,clades


def sampled_dates(path,manifest,c):
    content=Path(path).read_text();translation={}
    match=re.search(r'\btranslate\s+(.*?);',content,re.I|re.S)
    if match:
        for item in match.group(1).split(','):
            pieces=item.split(None,1)
            if len(pieces)!=2:raise ValueError('Malformed NEXUS translation')
            key,value=pieces;translation[key]=value.strip().strip("'")
    expected=tree_stats(parse_newick(manifest['rooted_topology']),manifest['tip_dates'],manifest['focal_tip_ids'])[2]
    values={}
    for state,tree in re.findall(r'\btree\s+STATE_([0-9]+)\s*=\s*(.*?;)',content,re.I|re.S):
        state=int(state)
        if state in values:raise ValueError('Duplicate sampled tree state')
        d,root,clades=tree_stats(parse_newick(tree,translation),manifest['tip_dates'],manifest['focal_tip_ids'])
        if clades!=expected:raise ValueError('Topology changed: refusing a fixed-topology HPD')
        values[state]=(d,root)
    if sorted(values)!=list(range(0,c['chain_length']+1,c['log_every'])):raise ValueError('Incomplete tree log or trace/tree state mismatch')
    return values


def hpd(values,mass=.95):
    a=sorted(values);n=len(a);k=math.ceil(mass*n)
    if not n or any(not math.isfinite(x) for x in a) or not 0<mass<1:raise ValueError('Invalid HPD inputs')
    i=min(range(n-k+1),key=lambda i:a[i+k-1]-a[i])
    return [a[i],a[i+k-1]]


def diagnostics(arrays,c):
    import numpy as np
    try:
        import arviz as az
    except (ImportError,AttributeError) as error:
        raise ValueError('ArviZ could not import. Recreate the dating Conda environment with the pinned Matplotlib version. Original error: '+str(error)) from error
    result={};reasons=[]
    for key,a in arrays.items():
        a=np.asarray(a,dtype=float)
        if a.ndim!=2 or a.shape[0]<2 or a.shape[1]<50 or not np.isfinite(a).all():raise ValueError('Invalid retained chains')
        if np.any(np.var(a,axis=1)==0):
            result[key]=dict(status='constant_chain');reasons.append(key+': constant chain');continue
        with __import__('warnings').catch_warnings():
            __import__('warnings').simplefilter('ignore')
            rh=float(az.rhat(a,method='rank'));bulk=float(az.ess(a,method='bulk'));tail=float(az.ess(a,method='tail'))
            each=[float(az.ess(row[None,:],method='bulk')) for row in a]
        vals=[rh,bulk,tail,*each]
        good=all(math.isfinite(x) for x in vals) and rh<=c['max_rhat'] and bulk>=c['min_bulk_ess'] and tail>=c['min_tail_ess'] and min(each)>=c['min_chain_ess']
        result[key]=dict(rhat=rh if math.isfinite(rh) else None,bulk_ess=bulk if math.isfinite(bulk) else None,
          tail_ess=tail if math.isfinite(tail) else None,per_chain_bulk_ess=[x if math.isfinite(x) else None for x in each],status='passed' if good else 'failed')
        if not good:reasons.append(key+': convergence/ESS threshold failed')
    return result,reasons


def summarize(chains,out,c):
    c=configuration(c);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    result=dict(schema='wings.bayesian-tmrca.v1',status='incomplete',tmrca=None,root_date=None,reasons=[],config=c,
      scope='95% HPD conditional on fixed rooted topology, reference set, model and priors; no topology uncertainty',
      model='HKY+Gamma4; strict clock; constant coalescent',prior_only=c['prior_only'])
    write(out/'summary.json',result)
    try:
        if len(chains)!=c['chains']:raise ValueError('Not all independent chains supplied')
        collected={};manifests=[];seeds=[];states_out=[];focal_rows=[]
        for index,folder in enumerate(map(Path,chains),1):
            manifest=json.loads((folder/'manifest.json').read_text());complete=json.loads((folder/'complete.json').read_text())
            if manifest['config']!=c or manifest['chain']!=index:raise ValueError('Chain settings or order differ')
            if complete.get('status')!='complete' or complete['manifest_sha256']!=digest(folder/'manifest.json'):raise ValueError('Chain incomplete or manifest changed')
            for file,sha in complete['output_sha256'].items():
                if file not in ('chain.log','chain.trees') or digest(folder/file)!=sha:raise ValueError('Chain outputs changed')
            if set(complete['output_sha256'])!={'chain.log','chain.trees'}:raise ValueError('Missing output hashes')
            if manifests and any(manifest[k]!=manifests[0][k] for k in ('analysis','inputs','focal_tip_ids','rooted_topology','tip_dates')):raise ValueError('Cannot pool different analyses or models')
            seeds.append(manifest['seed']);manifests.append(manifest)
            states,trace=read_trace(folder/'chain.log',c);times=sampled_dates(folder/'chain.trees',manifest,c)
            required=('posterior','prior','clockRate','popSize','kappa','gammaShape')+(() if c['prior_only'] else ('likelihood',))
            if not all(k in trace for k in required):raise ValueError('Required trace parameters missing')
            rootcols=[k for k in trace if k in ('rootHeight','rootHeight.height')]
            if len(rootcols)!=1:raise ValueError('Missing root-height trace')
            for i,state in enumerate(states):
                if abs((manifest['latest_tip']-times[state][1])-trace[rootcols[0]][i])>1e-5:raise ValueError('Root height differs between trace and sampled tree')
            keep=[i for i,s in enumerate(states) if s>c['chain_length']*c['burnin']]
            trace['wings_tmrca']=[times[s][0] for s in states];trace['whole_tree_root_date']=[times[s][1] for s in states]
            if collected and set(trace)!=set(collected):raise ValueError('Trace columns differ between chains')
            for k,vals in trace.items():collected.setdefault(k,[]).append([vals[i] for i in keep])
            for i in keep:focal_rows.append([index,states[i],times[states[i]][0],times[states[i]][1]])
            states_out.append(len(keep))
        if len(set(seeds))!=len(seeds):raise ValueError('Independent chains require distinct seeds')
        monitored={k:v for k,v in collected.items() if not (c['prior_only'] and k=='likelihood')}
        diags,reasons=diagnostics(monitored,c)
        result.update(analysis=manifests[0]['analysis'],diagnostics=diags,reasons=reasons,
          diagnostics_method='ArviZ rank-normalized split R-hat; bulk and tail ESS; per-chain bulk ESS',summarizer_sha256=digest(__file__),
          topology_audit=manifests[0].get('topology_audit'),input_sha256=manifests[0]['inputs'],focal_sample_ids=manifests[0]['focal_sample_ids'],retained_per_chain=states_out,
          seeds=seeds,chain_manifests=[digest(Path(p)/'manifest.json') for p in chains])
        with (out/'tmrca_draws.tsv').open('w') as f:
            writer=csv.writer(f,delimiter='\t');writer.writerow(['chain','state','wings_tmrca_decimal_year','whole_tree_root_decimal_year']);writer.writerows(focal_rows)
        result['status']='not_converged' if reasons else 'prior_only' if c['prior_only'] else 'complete'
        if not reasons:
            import statistics
            for field,key in [('tmrca','wings_tmrca'),('root_date','whole_tree_root_date')]:
                vals=[x for chain in collected[key] for x in chain];bounds=hpd(vals)
                result[field]=dict(median_decimal_year=statistics.median(vals),hpd95_decimal_year=bounds,
                  median=calendar(statistics.median(vals)),hpd95=[calendar(x) for x in bounds],
                  method='Shortest contiguous interval containing at least 95% of retained draws (empirical HPD approximation)')
    except (OSError,ValueError,KeyError,ImportError) as e:
        result.update(status='blocked',tmrca=None,root_date=None,reasons=[str(e)])
    write(out/'summary.json',result);write_report(result,out/'tmrca.html')
    return result


def write_report(r,path):
    esc=html.escape
    rows=[]
    for label,key in [('WINGS common ancestor','tmrca'),('Whole reference-tree root','root_date')]:
        value=r.get(key);rows.append('<tr><td>'+label+'</td><td>'+(esc(value['median'][:10]) if value else 'Withheld')+'</td><td>'+(' to '.join(esc(d[:10]) for d in value['hpd95']) if value else 'Unavailable')+'</td></tr>')
    body='<!doctype html><meta charset="utf-8"><title>WINGS Bayesian dating</title><style>body{font:16px system-ui;margin:32px;color:#263c46}h1{color:#8c1d40}td,th{padding:14px;border-bottom:1px solid #ddd;text-align:left}th{background:#8c1d40;color:white}table{border-collapse:collapse}li{margin:8px 0}</style><h1>WINGS Bayesian dating</h1>'
    body+='<p><b>'+esc(r['status'])+'</b> · '+esc(r.get('analysis',''))+'</p><p>'+esc(r['scope'])+'</p>'
    audit=r.get('topology_audit') or {}
    if audit.get('restored_nodes'):body+='<p>Original ML topology: '+str(audit['restored_nodes'])+' internal nodes restored at the dated root. HPD conditions on these refinements; topology uncertainty is not included.</p>'
    if r.get('prior_only'):body+='<p><b>PRIOR-ONLY RUN — NOT A POSTERIOR ESTIMATE.</b></p>'
    body+='<table><tr><th>Ancestor</th><th>Median date</th><th>95% HPD'+(' (prior)' if r.get('prior_only') else '')+'</th></tr>'+''.join(rows)+'</table><ul>'+''.join('<li>'+esc(x)+'</li>' for x in r['reasons'])+'</ul>'
    body+='<p>Node dates are re-estimated. The topology and reference set are fixed. These dates are not geographic introduction dates and do not update the existing movie or entry counts.</p><p><a href="summary.json">Diagnostics and settings</a> · <a href="tmrca_draws.tsv">Retained date draws</a></p>'
    Path(path).write_text(body)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    for mode in ('chain','summary'):
        a=sub.add_parser(mode);a.add_argument('--settings-json',required=True);a.add_argument('--output',type=Path,required=True)
        if mode=='chain':
            a.add_argument('--inference',type=Path,required=True);a.add_argument('--selection',type=Path,required=True);a.add_argument('--chain',type=int,required=True);a.add_argument('--validate-only',action='store_true');a.add_argument('--threads',type=int)
        else:a.add_argument('--chains',nargs='+',type=Path,required=True)
    a=p.parse_args();c=configuration(json.loads(a.settings_json))
    if a.mode=='chain':result=run_chain(a.inference,a.selection,a.output,c,a.chain,a.validate_only,a.threads)
    else:result=summarize(a.chains,a.output,c)
    print(json.dumps(dict(status=result['status'],reasons=result.get('reasons',[]))))
    if result['status']=='blocked':raise SystemExit(1)

if __name__=='__main__':main()
