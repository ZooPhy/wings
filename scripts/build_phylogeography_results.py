#!/usr/bin/env python3
"""Shared Fast/BEAST results, with explicit method scope and no silent fallback."""
import argparse
from collections import defaultdict
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys
import numpy as np
from geographic_rate_prior import prior_config, histories as map_histories
from phylodynamic_mapping import TraitTree, numeric_date
from phylodynamic_estimands import focal_branches, entry_count
from phylodynamic_posterior import scope_history

ID=re.compile(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/replicate_[1-9][0-9]*\Z')
DEFAULTS=dict(enabled=True,method='fast',run_id='fast_v1',analyses=[],histories=600,seed=19073,
              geographic_prior={'family':'source'},max_mean_mcse=.15,max_probability_mcse=.025,
              include_beast=True,dating_run='long20m',posterior_run='posterior_5k',saved_inputs_only=False)
FAST_SCOPE='Conditional Bayesian geographic reconstruction on one fixed TreeTime-dated ML tree; topology and dating uncertainty are excluded.'
BEAST_SCOPE='BEAST dating followed by conditional geographic reconstruction across dated-tree draws; fixed topology; geography does not update the dating posterior.'


def config(raw=None):
    raw={} if raw is None else raw
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS):raise ValueError('Unknown phylogeography_results setting')
    c=dict(DEFAULTS,**raw)
    for key in ('enabled','include_beast','saved_inputs_only'):
        if type(c[key]) is not bool:raise ValueError('Invalid '+key)
    if c['method'] not in ('fast','beast'):raise ValueError('method must be fast or beast')
    for key in ('run_id','dating_run','posterior_run'):
        if not isinstance(c[key],str) or not re.fullmatch(r'[A-Za-z0-9_-]+',c[key]):raise ValueError('Invalid '+key)
    if not isinstance(c['analyses'],list) or len(set(c['analyses']))!=len(c['analyses']) or any(not isinstance(k,str) or not ID.fullmatch(k) for k in c['analyses']):raise ValueError('Invalid analyses')
    if type(c['histories']) is not int or not 400<=c['histories']<=10000 or type(c['seed']) is not int or c['seed']<1:raise ValueError('Use 400–10000 independent histories and a positive seed')
    for k,ceiling in [('max_mean_mcse',.15),('max_probability_mcse',.025)]:
        if type(c[k]) not in (int,float) or not math.isfinite(c[k]) or not 0<c[k]<=ceiling:raise ValueError('Precision thresholds can be tightened, not relaxed')
    if c['geographic_prior']!={'family':'source'}:prior_config(c['geographic_prior'])
    return c


def read(path):return json.loads(Path(path).read_text())


def analysis_ids(root,c,configured):
    """Use the saved selection cohort, never just its successful analyses."""
    if c['analyses']:return list(c['analyses'])
    if not c['saved_inputs_only']:return list(configured)
    path=Path(root)/'selection/selection_summary.json'
    if not path.is_file():
        raise ValueError('Saved-input mode requires '+str(path)+'; set explicit phylogeography_results.analyses if using an older selection export. No upstream analyses will be scheduled.')
    summary=read(path)
    rows=summary.get('replicates')
    if not isinstance(rows,list) or not rows:
        raise ValueError('Saved selection has no replicate list: '+str(path))
    keys=[r.get('id') if isinstance(r,dict) else None for r in rows]
    if any(not isinstance(k,str) or not ID.fullmatch(k) for k in keys) or len(set(keys))!=len(keys):
        raise ValueError('Invalid or duplicate saved analysis IDs: '+str(path))
    return keys


def saved_signature(paths):
    """Track external saved inputs as params, without linking producer rules."""
    return json.dumps({str(p):sha(p) if Path(p).is_file() else None for p in paths},sort_keys=True)


def fast_rule_inputs(root,key,c):
    if c['saved_inputs_only']:return []
    files=fast_sources(root,key)
    return [str(files[0]),str(files[1]),str(Path(root)/'selection')]+[str(p) for p in files[2:] if p.is_file()]


def beast_rule_inputs(root,keys,c):
    if c['saved_inputs_only'] or not(c['include_beast'] or c['method']=='beast'):return []
    return [str(p) for key in keys for p in beast_sources(root,key,c) if p.is_file()]


def fast_rule_signature(root,key,c):
    return saved_signature(fast_sources(root,key)) if c['saved_inputs_only'] else ''


def beast_rule_signature(root,keys,c):
    if not c['saved_inputs_only'] or not(c['include_beast'] or c['method']=='beast'):return ''
    return saved_signature([p for key in keys for p in beast_sources(root,key,c)])
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()
def write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(obj,allow_nan=False,separators=(',',':'))+'\n');temp.replace(path)
def require(ok,message):
    if not ok:raise ValueError(message)
def fingerprints(paths):return {str(Path(p).resolve()):sha(p) for p in paths}
def unchanged(hashes):
    for path,digest in hashes.items():require(Path(path).is_file() and sha(path)==digest,'Source changed: '+path)
def assets():return Path(__file__).parent/'report'


def history_states(nodes,h,states):
    """Validate one complete history and return endpoint states."""
    tree=TraitTree(nodes,states);by={n['id']:n for n in nodes};events=defaultdict(list)
    require(h.get('root_state') in states,'Unknown root location')
    for j in h['jumps']:
        require(j['branch'] in by,'Unknown event branch');n=by[j['branch']]
        require(n['parent'] is not None and j['from'] in states and j['to'] in states and j['from']!=j['to'],'Invalid geographic event')
        require(numeric_date(by[n['parent']]['date'])<numeric_date(j['date'])<=numeric_date(n['date']),'Event outside its dated branch')
        events[j['branch']].append(j)
    ends={}
    for i in tree.order:
        n=nodes[i];state=ends[n['parent']] if n['parent'] is not None else h['root_state']
        for j in sorted(events[n['id']],key=lambda j:numeric_date(j['date'])):
            require(j['from']==state,'Broken state history');state=j['to']
        if n.get('observed_state') is not None:require(state==n['observed_state'],'History contradicts an observed sample location')
        ends[n['id']]=state
    return ends


def probability_error(p,n):
    # Independent conditional draws. Boundary events receive a one-sided bound.
    return 1-math.pow(.05,1/n) if p in (0,1) else math.sqrt(p*(1-p)/n)


def fast_precision(nodes,histories,states,c):
    n=len(histories);require(n>=400,'Too few geographic histories');node_counts={k:defaultdict(int) for k in [x['id'] for x in nodes]}
    counts={s:[] for s in states}
    for h in histories:
        ends=history_states(nodes,h,states)
        for k,s in ends.items():node_counts[k][s]+=1
        for s in states:counts[s].append(entry_count(h,s))
    failures=[];entries={};max_node_error=0.
    for key,dist in node_counts.items():
        for s in states:
            e=probability_error(dist[s]/n,n);max_node_error=max(max_node_error,e)
            if e>c['max_probability_mcse']:failures.append('Node-location precision insufficient: '+key);break
    for s,a in counts.items():
        mean=float(np.mean(a));constant=len(set(a))==1;err=float(np.std(a,ddof=1)/math.sqrt(n));zero=a.count(0)/n
        low,high=np.quantile(a,[.025,.975],method='inverted_cdf');tails=[sum(x<=v for x in a)/n for v in (low,high)]
        if err>c['max_mean_mcse'] or max(probability_error(x,n) for x in [zero,*tails])>c['max_probability_mcse']:failures.append('Entry-count precision insufficient: '+s)
        entries[s]=dict(mean=mean,interval95=[int(low),int(high)],mean_mcse=None if constant else err,
            zero_probability=zero,constant_sample=constant,boundary_probability_bound=probability_error(zero,n) if zero in (0,1) else None)
    return dict(status='blocked' if failures else 'passed',reasons=failures,entries=entries,max_node_probability_error=max_node_error,
       history_count=n,method='Independent conditional histories; sample-mean MCSE and probability MCSE/boundary bounds. No MCMC ESS is claimed.')


def fast_sources(root,key):
    root=Path(root);inf=root/'inference'/key;sel=root/'selection'/key
    return [inf/'result.json',inf/'movie.json',inf/'dated_nodes.json',inf/'temporal_diagnostics.json',inf/'alignment.fasta',inf/'ml.treefile',sel/'selection.json',sel/'tips.tsv']


def build_fast(root,key,out,c):
    c=config(c);require(bool(ID.fullmatch(key)),'Invalid analysis ID');out=Path(out)
    result=dict(schema='wings.fast-geography.v1',id=key,status='blocked',reasons=[],settings=c)
    write(out,result)
    try:
        first=read(Path(root)/'inference'/key/'result.json')
        require(first.get('status')=='complete','Source reconstruction is blocked: '+ '; '.join(first.get('reasons',[])))
        files=fast_sources(root,key);source_hashes=fingerprints(files+[Path(__file__),Path(__file__).with_name('geographic_rate_prior.py')]);record,movie,nodes,temporal,_,_,selection,_=[read(f) if f.suffix=='.json' else None for f in files]
        require(record.get('id')==key and record.get('status')=='complete' and not record.get('reasons'),'A complete, screened fast reconstruction is required')
        require(temporal.get('status')=='passed' and record.get('temporal_diagnostics',{}).get('status')=='passed','Temporal-signal checks have not passed')
        require(temporal.get('tree_sha256')==sha(files[5]),'Clock screen belongs to a different ML tree')
        require(record.get('selection_sha256')==sha(files[6]) and selection.get('id')==key,'Selection provenance changed')
        require(movie.get('schema')=='wings.phylogeography-movie.v1' and movie.get('provenance',{}).get('analysis')==key and movie.get('provenance',{}).get('selection_sha256')==sha(files[6]),'Fast movie provenance mismatch')
        require(movie.get('provenance',{}).get('uncertainty')=='conditional-on-fixed-tree','Unsupported fast uncertainty scope')
        require(movie.get('provenance',{}).get('inference')=='bayesian','Fast histories must be conditional Bayesian samples')
        segments=movie['segments'];require(len(segments)==1 and segments[0]['nodes']==nodes,'Movie differs from the saved dated tree')
        with files[7].open() as f:meta=list(csv.DictReader(f,delimiter='\t'))
        tip_nodes=[n for n in nodes if 'observed_state' in n];by_meta={r['id']:r for r in meta}
        require(len(by_meta)==len(meta) and set(by_meta)=={n['id'] for n in tip_nodes},'Tip metadata differs from the tree')
        for n in tip_nodes:
            r=by_meta[n['id']];require(n['observed_state']==r['location'] and abs(numeric_date(n['date'])-numeric_date(r['date']))<=2/365.25,'Tip location/date mismatch')
        locations=movie['locations'];states=[l['id'] for l in locations]
        require(len(states)==len(set(states)) and locations==selection['location_metadata'],'Location metadata changed')
        focal=record['focal_sample_ids'];tips=[n['id'] for n in nodes if n.get('sample_id') in focal]
        require(len(set(focal))==len(focal)>=2 and len(tips)==len(focal),'Invalid WINGS cohort')
        source_prior=movie['provenance']['prior'];prior=prior_config(c['geographic_prior'],source_prior)
        source_p=prior_config({'family':'source'},source_prior)
        old_histories=segments[0]['histories']
        if prior==source_p and len(old_histories)==c['histories']:
            hs=old_histories;quadrature=record['quadrature'];reuse=True
            require(quadrature.get('cdf_error',math.inf)<=.001,'Source rate quadrature failed')
        else:
            hs,quadrature=map_histories(nodes,states,c['histories'],c['seed'],prior);reuse=False
        draws=[];scoped_nodes=None;mrca=None
        require(len({h['id'] for h in hs})==len(hs),'Duplicate geographic histories')
        for i,h in enumerate(hs):
            history_states(nodes,h,states)
            scoped_nodes,scoped,mrca=scope_history(nodes,h,tips)
            draws.append(dict(id=str(i+1),history=scoped))
        require(mrca==record.get('focal_mrca'),'WINGS ancestor differs from source reconstruction')
        diag=fast_precision(scoped_nodes,[d['history'] for d in draws],states,c)
        if reuse:
            for state,entry in diag['entries'].items():
                require(math.isclose(entry['mean'],record['introductions'][state]['mean'],abs_tol=1e-8),'Source jump counts differ from saved histories')
        require(diag['status']=='passed','; '.join(diag['reasons']))
        unchanged(source_hashes)
        dataset=dict(method='fast',status='passed',scope=FAST_SCOPE,analysis=key,locations=locations,nodes=scoped_nodes,
                     draws=draws,focal_mrca=mrca,focal_sample_ids=focal,
                     tmrca=dict(median=next(n['date'] for n in scoped_nodes if n['id']==mrca),hpd95=None),
                     prior=prior,entries=diag['entries'],diagnostics=diag,
                     temporal=dict(raw_ml_r2=temporal.get('observed',{}).get('r2'),status='passed'),
                     source_hashes=source_hashes,reused_histories=reuse,quadrature=quadrature)
        result.update(status='passed',dataset=dataset,source_hashes=source_hashes)
    except (OSError,ValueError,KeyError,TypeError) as e:
        result.update(status='blocked',reasons=[str(e)])
    write(out,result);return result


def beast_folder(root,key,c):return Path(root)/'bayesian'/key/c['dating_run']/'posterior'/c['posterior_run']


def beast_sources(root,key,c):
    folder=beast_folder(root,key,c)
    return [folder/'publication'/n for n in ('publication.json','diagnostics.json','movie.json')]+[folder/'gate'/n for n in ('verified.json','diagnostics.json','trees.json')]+[folder/'mapping/mapping.json']


def build_beast(root,key,c):
    files=beast_sources(root,key,c);publication,diagnostics,data,proof,gate=[read(f) for f in files[:5]]
    require(all(r.get('status')=='passed' for r in (publication,diagnostics,data,proof,gate)),'BEAST posterior/publication gates have not passed')
    require(publication['movie_sha256']==sha(files[2]) and publication['diagnostics_sha256']==sha(files[1]),'BEAST publication changed')
    require(proof['diagnostics_sha256']==sha(files[4]) and proof['trees_sha256']==sha(files[5]),'BEAST gate outputs changed')
    require(diagnostics.get('gate_sha256')==sha(files[3]) and data.get('gate_sha256')==sha(files[3]),'BEAST result belongs to a different gate')
    require(diagnostics.get('mapping_sha256')==sha(files[6]),'BEAST mapped histories changed')
    require(data.get('analysis')==key and data.get('settings')==proof.get('settings'),'BEAST analysis/settings mismatch')
    require(proof['settings']['max_rhat']<=1.01 and min(proof['settings']['min_bulk_ess'],proof['settings']['min_tail_ess'])>=400 and proof['settings']['min_chain_ess']>=100,'BEAST convergence thresholds are insufficient')
    for group in ('diagnostics','selected_tree_diagnostics'):
        require(bool(gate.get(group)),'BEAST internal-date diagnostics are missing')
        for name,d in gate[group].items():
            require(d.get('status')=='passed' and d.get('rhat',math.inf)<=proof['settings']['max_rhat'] and d.get('bulk_ess',0)>=proof['settings']['min_bulk_ess'] and d.get('tail_ess',0)>=proof['settings']['min_tail_ess'] and min(d.get('per_chain_bulk_ess',[0]))>=proof['settings']['min_chain_ess'],'BEAST diagnostic failed: '+name)
    unchanged(proof['source_fingerprint'])
    locations=data['locations'];states=[l['id'] for l in locations];per=defaultdict(set)
    topology=None
    for draw in data['draws']:
        require(draw['state'] not in per[draw['chain']],'Repeated BEAST tree');per[draw['chain']].add(draw['state'])
        ns=draw['nodes'];edges={(n['id'],n['parent']) for n in ns}
        if topology is None:topology=edges
        require(edges==topology,'Rooted topology differs across BEAST draws')
        history_states(ns,draw['history'],states)
        require(sorted(n['sample_id'] for n in ns if n.get('sample_id'))==sorted(data['focal_sample_ids']),'WINGS tips differ between BEAST draws')
    require(len(per)>=2 and len(set(map(len,per.values())))==1,'Unequal or missing BEAST chains')
    entries={}
    for k,v in data['entries'].items():
        entries[k]=dict(v,zero_probability=v['zero_probability']['estimate'])
    return dict(method='beast',status='passed',scope=BEAST_SCOPE,analysis=key,locations=locations,draws=data['draws'],
      focal_sample_ids=data['focal_sample_ids'],focal_mrca=data['draws'][0]['focal_mrca'],tmrca=data['tmrca'],
      prior=dict(family='gamma',parameter='pair_rate',shape=data['prior']['rate_prior_shape'],rate=data['prior']['rate_prior_rate']),
      entries=entries,diagnostics=diagnostics,source_hashes=fingerprints(files),gate_source_hashes=proof['source_fingerprint'])


def report(root,keys,out,c):
    c=config(c);root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'index.html').write_text('<!doctype html><h1>Phylogeography results are being validated</h1>')
    (out/'results.json').unlink(missing_ok=True)
    records=[]
    for key in keys:
        require(bool(ID.fullmatch(key)),'Invalid analysis ID')
        row=dict(id=key,methods={},unavailable={})
        fastpath=root/'results'/c['run_id']/'fast'/key/'result.json'
        try:
            f=read(fastpath);require(f.get('status')=='passed','; '.join(f.get('reasons',[])) or 'Fast analysis unavailable')
            require(f.get('settings')==c,'Fast results were generated with different settings')
            unchanged(f['source_hashes']);row['methods']['fast']=f['dataset']
        except (ValueError,OSError,KeyError) as e:row['unavailable']['fast']=str(e)
        if c['include_beast'] or c['method']=='beast':
            try:row['methods']['beast']=build_beast(root,key,c)
            except (ValueError,OSError,KeyError,TypeError) as e:row['unavailable']['beast']=str(e)
        else:row['unavailable']['beast']='BEAST results were not requested'
        if 'fast' in row['methods'] and 'beast' in row['methods']:
            require(sorted(row['methods']['fast']['focal_sample_ids'])==sorted(row['methods']['beast']['focal_sample_ids']),'Fast and BEAST WINGS cohorts differ')
        records.append(row)
    model=dict(schema='wings.phylogeography-results.v1',default_method=c['method'],analyses=records,
               default_analysis=keys[0],settings=c,
               description='Posterior ancestral-location probabilities and Markov jumps; reference replicates are never pooled.')
    write(out/'results.json',model)
    css=(assets()/'phylogeography-results.css').read_text();js=(assets()/'map-boundaries.js').read_text()+'\n'+(assets()/'phylogeography-results.js').read_text()
    payload=json.dumps(model,separators=(',',':'),allow_nan=False).replace('<','\\u003c')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WINGS · Phylogeography</title><style>'+css+'</style><main id="app"></main><script id="results-data" type="application/json">'+payload+'</script><script>'+js+'</script></html>'
    temp=out/'index.html.tmp';temp.write_text(page);temp.replace(out/'index.html')
    return model


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['fast','report']);p.add_argument('--root',type=Path,required=True);p.add_argument('--settings-json',default='{}');p.add_argument('--analysis');p.add_argument('--analyses',nargs='+');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();c=config(json.loads(a.settings_json))
    if a.mode=='fast':r=build_fast(a.root,a.analysis,a.output,c);print(r['status'],r.get('reasons',[]))
    else:report(a.root,a.analyses,a.output,c);print('Open '+str(a.output/'index.html'))

if __name__=='__main__':main()
