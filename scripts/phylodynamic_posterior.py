#!/usr/bin/env python3
"""Fail-closed, two-stage propagation of BEAST dated trees into geographic histories.

Dating is conditional on a fixed rooted topology. Geography does not feed back
into dating. No BEAST run, chain resumption, or automatic threshold relaxation.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import warnings
import numpy as np
import phylodynamic_bayesian as dating
from phylodynamic_mapping import sample_histories, numeric_date, calendar_date, TraitTree
from phylodynamic_estimands import focal_branches, entry_count

DEFAULTS = dict(enabled=False, analyses=['HA/balanced/replicate_1'], dating_run='long20m',
                run_id='posterior_v1', trees_per_chain=1000, seed=19073,
                max_rhat=1.01, min_bulk_ess=400, min_tail_ess=400, min_chain_ess=100,
                max_mean_mcse=.15, max_probability_mcse=.025,
                max_date_mcse_days=7., max_hpd_endpoint_mcse_days=14.)
SCOPE = ('Two-stage posterior: BEAST dates followed by geographic histories conditional on each dated tree. '
         'Fixed rooted topology and reference set; locations do not update dating. '
         'Geographic jumps are inferred state changes, not observed introductions.')


def configuration(raw=None):
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or set(raw)-set(DEFAULTS):
        raise ValueError('Unknown posterior_phylogeography setting')
    c = dict(DEFAULTS, **raw)
    if type(c['enabled']) is not bool:
        raise ValueError('enabled must be boolean')
    if not isinstance(c['analyses'], list) or not c['analyses'] or len(c['analyses']) != len(set(c['analyses'])) or any(not isinstance(x,str) or not dating.ID.fullmatch(x) for x in c['analyses']):
        raise ValueError('Invalid analysis IDs')
    for key in ('dating_run', 'run_id'):
        if not isinstance(c[key],str) or not re.fullmatch(r'[A-Za-z0-9_-]+',c[key]):
            raise ValueError('Invalid '+key)
    for key in ('trees_per_chain','seed','min_bulk_ess','min_tail_ess','min_chain_ess'):
        if type(c[key]) is not int or c[key] < 1:
            raise ValueError(key+' must be a positive integer')
    if not 400 <= c['trees_per_chain'] <= 10000:
        raise ValueError('trees_per_chain must be 400–10000; never silently repeat trees')
    for key in ('max_rhat','max_mean_mcse','max_probability_mcse','max_date_mcse_days','max_hpd_endpoint_mcse_days'):
        if type(c[key]) not in (int,float) or not math.isfinite(c[key]) or c[key]<=0:
            raise ValueError('Invalid '+key)
    if not 1<c['max_rhat']<=1.01 or c['min_bulk_ess']<400 or c['min_tail_ess']<400 or c['min_chain_ess']<100:
        raise ValueError('Convergence thresholds may be tightened, never relaxed below R-hat 1.01 / ESS 400 / per-chain 100')
    if c['max_mean_mcse']>.15 or c['max_probability_mcse']>.025 or c['max_date_mcse_days']>7 or c['max_hpd_endpoint_mcse_days']>14:
        raise ValueError('Precision thresholds may be tightened, not relaxed')
    return c


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def jread(path):return json.loads(Path(path).read_text())
def write(path,data):dating.write(path,data)
def ensure(ok,message):
    if not ok:raise ValueError(message)


def versions():
    return {name:importlib.metadata.version(name) for name in ('numpy','scipy','arviz')}


def implementation_files():
    base=Path(__file__).resolve().parent
    return [base/name for name in ('phylodynamic_posterior.py','phylodynamic_bayesian.py',
             'phylodynamic_mapping.py','phylodynamic_estimands.py','report/posterior-phylogeography.js',
             'report/posterior-phylogeography.css','report/map-boundaries.js')]


def source_paths(run,inference,selection):
    run,inference,selection=map(Path,(run,inference,selection))
    s=jread(run/'summary.json');c=dating.configuration(s['config'])
    paths=[run/'summary.json',selection/'selection.json',selection/'tips.tsv',
           inference/'result.json',inference/'alignment.fasta',inference/'dated_nodes.json',inference/'ml.treefile']
    for i in range(1,c['chains']+1):
        paths.extend(run/f'chain_{i}'/f for f in ('manifest.json','complete.json','chain.log','chain.trees','input.xml'))
    return paths+implementation_files()


def fingerprint(paths):return {str(Path(p).resolve()):sha(p) for p in paths}


def check_fingerprint(values):
    for path,digest in values.items():
        ensure(Path(path).is_file() and sha(path)==digest,'Input changed or missing; rerun gate: '+path)


def tree_records(path):
    """Stream semicolon-delimited NEXUS statements; never hold a full tree log."""
    translation={};buf='';seen=False
    with Path(path).open() as f:
        for line in f:
            buf+=line
            while ';' in buf:
                statement,buf=buf.split(';',1)
                trans=re.search(r'\btranslate\s+(.*)',statement,re.I|re.S)
                if trans:
                    ensure(not translation and not seen,'Duplicate or late NEXUS translation')
                    for item in trans.group(1).split(','):
                        parts=item.strip().split(None,1)
                        ensure(len(parts)==2,'Malformed NEXUS translation')
                        k,v=parts;ensure(k not in translation,'Duplicate translated taxon')
                        translation[k]=v.strip().strip("'")
                    ensure(len(set(translation.values()))==len(translation),'Duplicate translated labels')
                match=re.search(r'\btree\s+STATE_(\d+)\s*=\s*(.*)',statement,re.I|re.S)
                if match:
                    seen=True
                    yield int(match.group(1)),dating.parse_newick(match.group(2)+';',translation)
                elif re.search(r'\btree\s+',statement,re.I):
                    raise ValueError('Unrecognized tree state')
        ensure(not buf.strip(),'Truncated NEXUS statement')
    ensure(seen,'No sampled trees')


def date_tree(root,manifest,metadata=None):
    """Stable clade IDs, exact sampled branch lengths, checked fixed tip dates."""
    tmrca,rootdate,clades=dating.tree_stats(root,manifest['tip_dates'],manifest['focal_tip_ids'])
    nodes=[];internal={}
    def visit(n,parent,depth):
        if n['children']:
            leaves=sorted(leaves_of(n))
            key='clade_'+hashlib.sha256(json.dumps(leaves,separators=(',',':')).encode()).hexdigest()[:24]
            internal[key]=rootdate+depth
        else:key=n['name']
        row=dict(id=key,parent=parent,date=calendar_date(rootdate+depth))
        if not n['children'] and metadata is not None:
            m=metadata[key];row.update(observed_state=m['location'],label=m.get('sample_id') or m.get('accession') or key)
            if m.get('sample_id'):row['sample_id']=m['sample_id']
        nodes.append(row)
        for child in n['children']:visit(child,key,depth+child['length'])
    visit(root,None,0.)
    ensure(len({n['id'] for n in nodes})==len(nodes),'Node identifier collision')
    return nodes,internal,tmrca,rootdate,clades


def leaves_of(n):
    if not n['children']:return [n['name']]
    return [t for child in n['children'] for t in leaves_of(child)]


def effective_config(c,original):
    out=dict(c)
    out['max_rhat']=min(c['max_rhat'],original['max_rhat'])
    for k in ('min_bulk_ess','min_tail_ess','min_chain_ess'):out[k]=max(c[k],original[k])
    return out


def monitored_diagnostics(arrays,c):
    # Use the same independently maintained ArviZ algorithms as the dating gate.
    diags,reasons=dating.diagnostics(arrays,c)
    return diags,reasons


def mcse_mean(a):
    import arviz as az
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        v=float(az.mcse(np.asarray(a,float),method='mean'))
    ensure(math.isfinite(v),'Nonfinite Monte Carlo standard error')
    return v


def interval_precision(a,seed):
    """Circular moving-block bootstrap, separately within each chain.

    Block length covers at least twice the largest estimated mean/tail
    autocorrelation time. Reports empirical shortest-interval endpoint MCSE.
    """
    import arviz as az
    a=np.asarray(a,float);chains,n=a.shape
    ess=min(float(az.ess(a,method='mean')),float(az.ess(a,method='tail')))
    ensure(math.isfinite(ess) and ess>0,'Cannot estimate interval precision')
    block=max(2,math.ceil(2*a.size/min(ess,a.size)))
    ensure(block<=n//10,'Too few effective blocks for HPD precision check')
    rng=np.random.default_rng(seed);bounds=[]
    for _ in range(250):
        draws=[]
        for row in a:
            starts=rng.integers(0,n,size=math.ceil(n/block))
            inds=((starts[:,None]+np.arange(block))%n).ravel()[:n]
            draws.extend(row[inds])
        bounds.append(dating.hpd(draws))
    return dict(endpoint_mcse_days=(np.std(bounds,axis=0,ddof=1)*365.25).tolist(),
                block_length=block,bootstrap_replicates=250)


def date_precision(arrays,c):
    results={};reasons=[]
    for key in ('wings_tmrca','whole_tree_root_date'):
        a=np.asarray(arrays[key]);err=mcse_mean(a)*365.25
        info=interval_precision(a,c['seed']);info['mean_mcse_days']=err
        if err>c['max_date_mcse_days'] or max(info['endpoint_mcse_days'])>c['max_hpd_endpoint_mcse_days']:
            reasons.append(key+': date/HPD Monte Carlo precision insufficient')
        results[key]=info
    return results,reasons


def gate(run,inference,selection,out,c):
    c=configuration(c);run,inference,selection,out=map(Path,(run,inference,selection,out))
    out.mkdir(parents=True,exist_ok=True)
    # Remove success tokens first; a stale pass must never authorize a new run.
    for name in ('verified.json','trees.json'):(out/name).unlink(missing_ok=True)
    report=dict(schema='wings.posterior-gate.v1',status='blocked',reasons=[],settings=c,scope=SCOPE)
    write(out/'diagnostics.json',report)
    try:
        software=versions()
        inputs=fingerprint(source_paths(run,inference,selection))
        summary=jread(run/'summary.json');old=dating.configuration(summary['config']);thresholds=effective_config(c,old)
        ensure(summary.get('status')=='complete' and summary.get('prior_only') is False and not old['prior_only'],
               'A completed posterior dating run is required; prior-only or failed runs are not accepted')
        ensure(run.name==c['dating_run'],'dating_run does not match source directory')
        inp=dating.load_inputs(inference,selection)
        ensure(summary.get('analysis')==inp['record']['id'] and summary['analysis'] in c['analyses'],'Analysis mismatch')
        ensure(summary.get('input_sha256')==inp['input_sha256'],'Dating inputs differ from current inference/selection')
        sel=jread(selection/'selection.json')
        ensure(sel.get('id')==summary['analysis'] and sha(selection/'selection.json')==inp['record'].get('selection_sha256'),
               'Reference-selection provenance differs')
        with (selection/'tips.tsv').open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
        metadata={r['id']:r for r in rows};locations=sel['location_metadata']
        locids=[r['id'] for r in locations]
        ensure(len(set(locids))==len(locids) and set(locids)=={r['location'] for r in rows},'Location metadata differs from tip states')
        for r in locations:
            ensure(all(type(r.get(k)) in (int,float) and math.isfinite(r[k]) for k in ('lat','lon')) and -90<=r['lat']<=90 and -180<=r['lon']<=180,'Invalid map coordinates')
        prior={k:sel['config'][k] for k in ('rate_prior_shape','rate_prior_rate')}
        ensure(all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in prior.values()),'Invalid geographic rate prior')
        collected={};chosen=[];seeds=[];manifest_hashes=[];selected_arrays={};first=None
        for chain in range(1,old['chains']+1):
            folder=run/f'chain_{chain}';m=jread(folder/'manifest.json');done=jread(folder/'complete.json')
            ensure(m['config']==old and m['chain']==chain,'Chain settings or index differ')
            ensure(m.get('schema')=='wings.bayesian-dating-chain.v1','Unsupported chain manifest')
            ensure(done.get('status')=='complete' and done['manifest_sha256']==sha(folder/'manifest.json'),'Incomplete chain or changed manifest')
            ensure(done.get('output_sha256')=={f:sha(folder/f) for f in ('chain.log','chain.trees')},'Chain output hashes differ')
            ensure(m['xml_sha256']==sha(folder/'input.xml'),'BEAST XML changed')
            ensure(m['inputs']==inp['input_sha256'] and m['analysis']==summary['analysis'],'Chain input provenance differs')
            ensure(m['tip_dates']==inp['dates'] and sorted(m['focal_tip_ids'])==inp['focal'] and sorted(m['focal_sample_ids'])==sorted(inp['record']['focal_sample_ids']), 'Taxa or focal sample set changed')
            if first:
                ensure(all(m[k]==first[k] for k in ('model','rooted_topology','topology_audit','interval_scope')),'Models or rooted topology differ between chains')
            else:first=m
            ensure(m['latest_tip']==max(m['tip_dates'].values()),'Invalid latest tip date')
            seeds.append(m['seed']);manifest_hashes.append(sha(folder/'manifest.json'))
            states,trace=dating.read_trace(folder/'chain.log',old)
            required={'posterior','prior','likelihood','clockRate','popSize','kappa','gammaShape'}
            ensure(required<=set(trace),'Required posterior trace parameters missing')
            ensure(all(min(trace[k])>0 for k in ('clockRate','popSize','kappa','gammaShape')),'Nonpositive clock, population or substitution parameter')
            rootcol=[k for k in ('rootHeight','rootHeight.height') if k in trace]
            ensure(len(rootcol)==1,'Missing or ambiguous root-height trace')
            keep=[s for s in states if s>old['chain_length']*old['burnin']]
            ensure(len(keep)>=c['trees_per_chain'],'Not enough retained distinct trees; reduce trees_per_chain (minimum 400) or extend chains')
            rng=np.random.default_rng(np.random.SeedSequence([c['seed'],chain]))
            selected=set(int(x) for x in rng.choice(keep,c['trees_per_chain'],replace=False))
            expected=dating.tree_stats(dating.parse_newick(m['rooted_topology']),m['tip_dates'],m['focal_tip_ids'])[2]
            current=dating.tree_stats(dating.parse_newick(dating.starting_tree(inp)),m['tip_dates'],m['focal_tip_ids'])[2]
            ensure(current==expected,'Rooted splits differ from the current fixed topology')
            local={k:[] for k in trace};local.update(wings_tmrca=[],whole_tree_root_date=[])
            local_selected={};observed=[];internal_keys=None
            for index,(state,tree) in enumerate(tree_records(folder/'chain.trees')):
                ensure(index<len(states) and state==states[index],'Incomplete, duplicated or unordered tree states')
                nodes,internal,tmrca,rootdate,clades=date_tree(tree,m,metadata)
                ensure(clades==expected,'Sampled topology differs from the declared fixed topology')
                ensure(abs(m['latest_tip']-rootdate-trace[rootcol[0]][index])<=1e-5,'Tree/trace root height mismatch')
                if internal_keys is None:internal_keys=set(internal)
                ensure(set(internal)==internal_keys,'Internal clade identifiers changed')
                observed.append(state)
                if state<=old['chain_length']*old['burnin']:continue
                vals={k:trace[k][index] for k in trace};vals.update(wings_tmrca=tmrca,whole_tree_root_date=rootdate)
                vals.update({'node_date:'+k:v for k,v in internal.items()})
                for k,v in vals.items():local.setdefault(k,[]).append(v)
                if state in selected:
                    TraitTree(nodes,locids)
                    chosen.append(dict(chain=chain,state=state,nodes=nodes))
                    for k,v in vals.items():local_selected.setdefault(k,[]).append(v)
            ensure(observed==states,'Tree log incomplete')
            if collected:ensure(set(collected)==set(local),'Trace or internal-node columns differ between chains')
            for k,v in local.items():collected.setdefault(k,[]).append(v)
            for k,v in local_selected.items():selected_arrays.setdefault(k,[]).append(v)
            print(f'Checked chain {chain}: {len(keep)} retained trees, {len(internal_keys)} internal dates',flush=True)
        ensure(len(set(seeds))==len(seeds),'Independent chains require distinct seeds')
        ensure(manifest_hashes==summary.get('chain_manifests'),'Summary belongs to different chains')
        diags,reasons=monitored_diagnostics(collected,thresholds)
        selected_diag,selected_reasons=monitored_diagnostics(selected_arrays,thresholds)
        reasons+=['Selected trees: '+r for r in selected_reasons]
        precision={}
        if not reasons:
            precision,precision_reasons=date_precision(collected,thresholds);reasons+=precision_reasons
        report.update(analysis=summary['analysis'],thresholds=thresholds,software=software,
                      diagnostics=diags,selected_tree_diagnostics=selected_diag,date_precision=precision,reasons=reasons,
                      retained_per_chain=[len(x) for x in collected['wings_tmrca']],
                      source_fingerprint=inputs,interval_scope=SCOPE)
        if reasons:
            write(out/'diagnostics.json',report)
            raise ValueError('Posterior gate failed: '+'; '.join(reasons[:8])+f' ({len(reasons)} failures; see diagnostics.json)')
        def interval(key):
            values=np.asarray(collected[key]).ravel();bounds=dating.hpd(values)
            return dict(median=calendar_date(float(np.median(values))),hpd95=[calendar_date(x) for x in bounds])
        bundle=dict(schema='wings.posterior-trees.v1',analysis=summary['analysis'],settings=c,
            locations=locations,focal_tip_ids=first['focal_tip_ids'],focal_sample_ids=first['focal_sample_ids'],
            prior=prior,tmrca=interval('wings_tmrca'),root_date=interval('whole_tree_root_date'),draws=chosen)
        check_fingerprint(inputs)
        write(out/'trees.json',bundle)
        report.update(status='passed',trees_sha256=sha(out/'trees.json'),tmrca=bundle['tmrca'],root_date=bundle['root_date'])
        write(out/'diagnostics.json',report)
        write(out/'verified.json',dict(status='passed',diagnostics_sha256=sha(out/'diagnostics.json'),
             trees_sha256=sha(out/'trees.json'),source_fingerprint=inputs,settings=c,software=software))
        return report
    except Exception as e:
        (out/'verified.json').unlink(missing_ok=True);(out/'trees.json').unlink(missing_ok=True)
        report['status']='blocked'
        if not report['reasons']:report['reasons']=[str(e)]
        write(out/'diagnostics.json',report)
        raise


def checked_gate(folder,c):
    folder=Path(folder);v=jread(folder/'verified.json')
    ensure(v.get('status')=='passed' and v.get('settings')==c,'No passing gate for these settings')
    ensure(v['diagnostics_sha256']==sha(folder/'diagnostics.json') and v['trees_sha256']==sha(folder/'trees.json'),'Gate outputs changed')
    ensure(jread(folder/'diagnostics.json')['status']=='passed','Diagnostics are not passing')
    ensure(v['software']==versions(),'Diagnostic software changed; rerun gate')
    check_fingerprint(v['source_fingerprint'])
    return v,jread(folder/'trees.json')


def scope_history(nodes,history,focal):
    """Validate the complete history; retain only the study MRCA-to-tip ancestry."""
    by={n['id']:n for n in nodes};branches,mrca=focal_branches(nodes,focal)
    ensure(mrca is not None,'At least two WINGS tips required')
    root=next(n for n in nodes if n['parent'] is None);assigned={root['id']:history['root_state']};jumps={k:[] for k in by}
    for j in history['jumps']:
        ensure(j['branch'] in by and by[j['branch']]['parent'] is not None,'Jump on unknown/root branch')
        n=by[j['branch']];t=numeric_date(j['date'])
        ensure(numeric_date(by[n['parent']]['date'])<t<=numeric_date(n['date']),'Jump outside its own sampled branch')
        jumps[j['branch']].append(j)
    remaining=list(nodes)
    while remaining:
        progress=False
        for n in remaining[:]:
            if n['parent'] is not None and n['parent'] not in assigned:continue
            state=assigned[n['parent']] if n['parent'] is not None else assigned[n['id']]
            previous=-math.inf
            for j in sorted(jumps[n['id']],key=lambda x:x['date']):
                t=numeric_date(j['date'])
                ensure(t>=previous and j['from']==state and j['to']!=state,'Broken history continuity')
                previous=t;state=j['to']
            if 'observed_state' in n:ensure(state==n['observed_state'],'History does not reach the observed tip state')
            assigned[n['id']]=state;remaining.remove(n);progress=True
        ensure(progress,'Disconnected history')
    scoped=[dict(n,parent=None if n['id']==mrca else n['parent']) for n in nodes if n['id']==mrca or n['id'] in branches]
    return scoped,dict(root_state=assigned[mrca],jumps=[j for j in history['jumps'] if j['branch'] in branches]),mrca


def reconstruct(gate_dir,out,c):
    c=configuration(c);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'mapping.json').unlink(missing_ok=True)
    write(out/'mapping_status.json',dict(status='running'))
    try:
        proof,bundle=checked_gate(gate_dir,c);locids=[r['id'] for r in bundle['locations']];draws=[]
        for index,d in enumerate(bundle['draws']):
            seed=int(np.random.SeedSequence([c['seed'],d['chain'],d['state'],739]).generate_state(1)[0])
            hs,quad=sample_histories(d['nodes'],locids,1,seed,bundle['prior']['rate_prior_shape'],bundle['prior']['rate_prior_rate'])
            ensure(quad.get('cdf_error',math.inf)<=.001,'Geographic rate quadrature did not converge')
            nodes,h,mrca=scope_history(d['nodes'],hs[0],bundle['focal_tip_ids'])
            draws.append(dict(chain=d['chain'],state=d['state'],nodes=nodes,history=h,
                              focal_mrca=mrca,rate=quad['rate_draw_mean'],quadrature=quad))
            if (index+1)%25==0:print(f'Mapped {index+1}/{len(bundle["draws"])} dated trees',flush=True)
        checked_gate(gate_dir,c)
        data={k:v for k,v in bundle.items() if k not in ('schema','draws')}
        data.update(schema='wings.posterior-mapping.v1',status='mapped',scope=SCOPE,draws=draws,
                    gate_sha256=sha(Path(gate_dir)/'verified.json'),weighting='One history per distinct tree; equal draws per chain; all zero-event histories retained')
        write(out/'mapping.json',data);write(out/'mapping_status.json',dict(status='mapped',draws=len(draws)))
        return data
    except Exception as e:
        (out/'mapping.json').unlink(missing_ok=True)
        write(out/'mapping_status.json',dict(status='blocked',reasons=[str(e)]));raise


def probability_precision(indicators,base_ess):
    """Boundary estimates are upper/lower bounds, never exact posterior zero/one."""
    import arviz as az
    a=np.asarray(indicators,float);p=float(a.mean())
    if np.all(a==a.flat[0]):
        n=min(a.size,base_ess);bound=1-math.pow(.05,1/n)
        return dict(estimate=p,mcse=None,bound95=bound if p==0 else 1-bound,
                    boundary=True,effective_n=n,precision_halfwidth=bound)
    ess=float(az.ess(a,method='mean'))
    ensure(math.isfinite(ess) and ess>0,'Invalid indicator ESS')
    n=min(a.size,ess,base_ess);err=max(mcse_mean(a),math.sqrt(p*(1-p)/n))
    return dict(estimate=p,mcse=err,boundary=False,effective_n=n,precision_halfwidth=err)


def mapping_diagnostics(data,gate_report,c):
    chains=sorted({d['chain'] for d in data['draws']});per=[sorted([d for d in data['draws'] if d['chain']==i],key=lambda d:d['state']) for i in chains]
    ensure(len(chains)>=2 and len({len(row) for row in per})==1 and all(len(row)==c['trees_per_chain'] for row in per),'Unequal or missing mapped chains')
    ensure(all(len({d['state'] for d in row})==len(row) for row in per),'Repeated posterior tree draws')
    base_ess=min(x['bulk_ess'] for x in gate_report['selected_tree_diagnostics'].values())
    arrays={'geographic_rate':np.array([[d['rate'] for d in row] for row in per])}
    for loc in data['locations']:
        arrays['entries:'+loc['id']]=np.array([[entry_count(d['history'],loc['id']) for d in row] for row in per])
    variable={k:a for k,a in arrays.items() if not np.all(a==a.flat[0])}
    ensure('geographic_rate' in variable,'Constant geographic rate draws')
    diagnostics,reasons=monitored_diagnostics(variable,gate_report['thresholds'])
    counts={}
    for loc in data['locations']:
        k='entries:'+loc['id'];a=arrays[k];flat=a.ravel();constant=np.all(a==a.flat[0])
        err=0. if constant else mcse_mean(a)
        pzero=probability_precision(a==0,base_ess)
        # Check both endpoint CDF probabilities; count intervals are discrete, not HPDs.
        lower,upper=np.quantile(flat,[.025,.975],method='inverted_cdf')
        tails=[probability_precision(a<=lower,base_ess),probability_precision(a<=upper,base_ess)]
        if err>c['max_mean_mcse']:reasons.append(k+': count mean MCSE too large')
        if max([pzero['precision_halfwidth'],*[t['precision_halfwidth'] for t in tails]])>c['max_probability_mcse']:
            reasons.append(k+': probability/interval-tail Monte Carlo precision insufficient')
        if constant:
            diagnostics[k]=dict(status='constant_mapping_sample',rhat=None,bulk_ess=None,tail_ess=None,
              note='No sampled variation; this does not establish a point mass. Boundary-probability bound uses the minimum selected-date ESS.')
        counts[loc['id']]=dict(mean=float(flat.mean()),interval95=[int(lower),int(upper)],mean_mcse=None if constant else err,
            zero_probability=pzero,interval_tail_precision=tails,constant_sample=bool(constant))
    return dict(status='blocked' if reasons else 'passed',reasons=reasons,diagnostics=diagnostics,entries=counts,
                precision_scope='Monte Carlo precision checks, not model validation. Entry intervals are equal-tailed discrete posterior intervals; constant samples are not proof of a point mass.')


def invalidate_publication(out,message):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'movie.json').unlink(missing_ok=True)
    (out/'publication.json').unlink(missing_ok=True)
    (out/'movie.html').write_text('<!doctype html><meta charset="utf-8"><title>WINGS — withheld</title><h1>Posterior movie withheld</h1><p>'+html.escape(message)+'</p><p>See diagnostics.json and the gate diagnostics. No previous movie is served at this path.</p>')


def publish(gate_dir,mapping_dir,out,c):
    c=configuration(c);out=Path(out)
    invalidate_publication(out,'Validation in progress')
    try:
        proof,bundle=checked_gate(gate_dir,c);data=jread(Path(mapping_dir)/'mapping.json');mapping_hash=sha(Path(mapping_dir)/'mapping.json')
        ensure(data.get('status')=='mapped' and data.get('settings')==c and data.get('gate_sha256')==sha(Path(gate_dir)/'verified.json'),'Mapping provenance differs')
        ensure(data.get('analysis')==bundle['analysis'] and data.get('locations')==bundle['locations'],'Mapped analysis or locations differ')
        expected={(d['chain'],d['state']):d for d in bundle['draws']}
        ensure(len(data['draws'])==len(expected),'Missing mapped trees')
        seen=set()
        for d in data['draws']:
            key=(d['chain'],d['state']);ensure(key in expected and key not in seen,'Unknown or repeated mapped tree');seen.add(key)
            original=expected[key];branches,mrca=focal_branches(original['nodes'],bundle['focal_tip_ids'])
            expected_nodes=[dict(n,parent=None if n['id']==mrca else n['parent']) for n in original['nodes'] if n['id']==mrca or n['id'] in branches]
            ensure(d['nodes']==expected_nodes and d['focal_mrca']==mrca,'Mapped dates or ancestry changed')
            ensure(d['history']['root_state'] in {r['id'] for r in data['locations']},'Unknown root state')
            scope_history(d['nodes'],d['history'],bundle['focal_tip_ids'])
            ensure(math.isfinite(d['rate']) and d['rate']>0 and d['quadrature'].get('cdf_error',math.inf)<=.001,'Invalid geographic rate/quadrature')
        report=mapping_diagnostics(data,jread(Path(gate_dir)/'diagnostics.json'),c)
        report.update(schema='wings.posterior-publication.v1',scope=SCOPE,analysis=data['analysis'],settings=c,
                      gate_sha256=sha(Path(gate_dir)/'verified.json'),mapping_sha256=mapping_hash)
        write(out/'diagnostics.json',report)
        ensure(report['status']=='passed','Geographic precision gate failed: '+'; '.join(report['reasons'][:8]))
        # Display data retains each draw's own dates; never replace dates with medians.
        movie={k:v for k,v in data.items() if k not in ('schema','status')}
        movie.update(schema='wings.posterior-movie.v1',status='passed',entries=report['entries'])
        checked_gate(gate_dir,c)
        ensure(sha(Path(mapping_dir)/'mapping.json')==mapping_hash,'Mapping changed during publication')
        write(out/'movie.json',movie)
        assets=Path(__file__).parent/'report'
        js=(assets/'map-boundaries.js').read_text()+'\n'+(assets/'posterior-phylogeography.js').read_text();css=(assets/'posterior-phylogeography.css').read_text()
        embedded=json.dumps(movie,separators=(',',':'),allow_nan=False).replace('<','\\u003c')
        document='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WINGS posterior phylogeography</title><style>'+css+'</style><main id="app"></main><script id="posterior-data" type="application/json">'+embedded+'</script><script>'+js+'</script></html>'
        temp=out/'movie.html.tmp';temp.write_text(document);temp.replace(out/'movie.html')
        write(out/'publication.json',dict(status='passed',diagnostics_sha256=sha(out/'diagnostics.json'),movie_sha256=sha(out/'movie.json'),html_sha256=sha(out/'movie.html')))
        return report
    except Exception as e:
        invalidate_publication(out,str(e))
        if not (out/'diagnostics.json').exists() or jread(out/'diagnostics.json').get('status')=='passed':
            write(out/'diagnostics.json',dict(status='blocked',reasons=[str(e)]))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['gate','map','publish'])
    parser.add_argument('--settings-json',default='{}');parser.add_argument('--run',type=Path);parser.add_argument('--inference',type=Path);parser.add_argument('--selection',type=Path)
    parser.add_argument('--gate',type=Path);parser.add_argument('--mapping',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--publication',type=Path,help='Invalidate an older publication before gate or mapping starts')
    a=parser.parse_args()
    try:
        c=configuration(json.loads(a.settings_json))
        if a.publication:invalidate_publication(a.publication,'Upstream posterior validation/reconstruction is running')
        if a.mode=='gate':result=gate(a.run,a.inference,a.selection,a.output,c)
        elif a.mode=='map':result=reconstruct(a.gate,a.output,c)
        else:result=publish(a.gate,a.mapping,a.output,c)
        print(json.dumps(dict(status=result.get('status'),reasons=result.get('reasons',[]))))
    except Exception as e:
        print('BLOCKED: '+str(e),file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
