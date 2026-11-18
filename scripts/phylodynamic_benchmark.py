#!/usr/bin/env python3
"""Known-tree simulation benchmark; NOT validation of fitted trees or real data.

Prespecified test conditions include equal rates, asymmetric/time-varying rates,
biased surveillance, migrant enrichment, host imbalance and an unobserved deme.
Evaluate a fixed focal subtree separately from sampling losses in the full tree.
"""
from __future__ import annotations
import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import time
import numpy as np
from phylodynamic_mapping import calendar_date, numeric_date, sample_histories
from phylodynamic_selection import configuration, select, write_json, write_tsv
from phylodynamic_estimands import focal_branches, entry_count

SCENARIOS=('equal_rates','geographic_bias','host_bias','recent_migrants','asymmetric_rates','time_varying_rates','missing_deme')
STATES=['USA:KY','USA:OH','USA:TN']


def simulate(seed, scenario, n=96):
    rng=np.random.default_rng(seed);nodes=[dict(id='n0',parent=None,time=2020.0,state=0)]
    active=[0];now=2020.0
    while len(active)<n:
        now+=rng.exponential(1/(len(active)*2.5))
        parent=active.pop(int(rng.integers(len(active))))
        # This parent becomes a bifurcation; its time was its birth.
        for _ in range(2):
            nodes.append(dict(id='n'+str(len(nodes)),parent=nodes[parent]['id'],time=now))
            active.append(len(nodes)-1)
    # Serial terminal dates, independently of locations (no date imputation).
    for i in active:nodes[i]['time']+=float(rng.uniform(.05,.5))
    by_id={r['id']:r for r in nodes};jumps=[];sequences={'n0':rng.choice(list('ACGT'),240)}
    for row in nodes[1:]:
        parent=by_id[row['parent']];current=parent['state'];t=parent['time']
        while t<row['time']:
            q=np.full((3,3),.25);np.fill_diagonal(q,0)
            if scenario=='asymmetric_rates':q=np.array([[0,.7,.08],[.04,0,.25],[.5,.05,0]])
            boundary=2020.8
            if scenario=='time_varying_rates':q*=.15 if t<boundary else 5
            rate=q[current].sum();wait=float(rng.exponential(1/rate))
            if scenario=='time_varying_rates' and t<boundary<min(t+wait,row['time']):t=boundary;continue
            t+=wait
            if t>=row['time']:break
            destination=int(rng.choice(3,p=q[current]/rate))
            jumps.append(dict(branch=row['id'],date=calendar_date(t),**{'from':STATES[current],'to':STATES[destination]}));current=destination
        row['state']=current
        seq=sequences[parent['id']].copy()
        mask=rng.random(len(seq)) < 1-np.exp(-.08*(row['time']-parent['time']))
        seq[mask]=rng.choice(list('ACGT'),int(mask.sum()));sequences[row['id']]=seq
    tips=[]
    recent={j['branch'] for j in jumps if by_id[j['branch']]['time']-numeric_date(j['date'])<.25}
    for i in active:
        r=nodes[i];when=calendar_date(r['time'])[:10]
        host='wild' if rng.random()<(.85 if r['state']==0 else .25) else 'domestic'
        tips.append(dict(id=r['id'],date=when,month=when[:7],host=host,location=STATES[r['state']],sequence=''.join(sequences[r['id']]),recent=r['id'] in recent))
    rendered=[dict(id=r['id'],parent=r['parent'],date=calendar_date(r['time']),
                   **({'observed_state':STATES[r['state']]} if i in active else {})) for i,r in enumerate(nodes)]
    history=dict(root_state=STATES[0],jumps=jumps)
    return rendered,tips,history


def prune(nodes, retained):
    by_id={r['id']:r for r in nodes};keep=set()
    for tip in retained:
        current=tip
        while current is not None and current not in keep:keep.add(current);current=by_id[current]['parent']
    # Keep unary nodes and root, so true event branches are exactly traceable.
    return [dict(r) for r in nodes if r['id'] in keep]


def sample_pool(tips,scenario,rng):
    focal=[r for r in tips if r['location']==STATES[0]]
    focal=sorted(focal,key=lambda r:r['id'])
    if len(focal)<4:return [],[]
    focal=[focal[i] for i in sorted(rng.choice(len(focal),min(8,len(focal)),replace=False))]
    ids={r['id'] for r in focal};pool=[]
    for r in tips:
        if r['id'] in ids:continue
        p=.8
        if scenario=='geographic_bias':p={'USA:KY':1,'USA:OH':.25,'USA:TN':.08}[r['location']]
        elif scenario=='host_bias':p=1 if r['host']=='domestic' else .15
        elif scenario=='recent_migrants':p=1 if r['recent'] else .2
        elif scenario=='missing_deme':p=0 if r['location']==STATES[2] else .8
        if rng.random()<p:pool.append(r)
    return focal,pool


def evaluate(nodes,truth,focal,pool,scenario,seed,partition,strategy,budget,bin_width,host_strata,histories):
    cfg=configuration(dict(max_references=budget,max_per_location=budget,time_bin=bin_width,stratify_host=host_strata))
    chosen=select(pool,focal,cfg,strategy,seed)
    selected=prune(nodes,{r['id'] for r in focal+chosen})
    states=sorted({r['location'] for r in focal+chosen})
    base=dict(partition=partition,scenario=scenario,seed=seed,strategy=strategy,budget=budget,time_bin=bin_width,host_strata=host_strata,
              focal_tips=len(focal),references=len(chosen),available_references=len(pool))
    if len(states)<2:return dict(base,status='blocked',reason='fewer_than_two_observed_states')
    start=time.perf_counter()
    draws,diag=sample_histories(selected,states,histories,seed)
    elapsed=time.perf_counter()-start
    branches,mrca=focal_branches(nodes,[r['id'] for r in focal]);target=STATES[0]
    known=entry_count(truth,target,branches);counts=np.array([entry_count(h,target,branches) for h in draws])
    low,high=np.quantile(counts,[.025,.975]);mean=float(counts.mean())
    represented={r['id'] for r in selected if r['parent'] is not None}
    true_total=entry_count(truth,target);true_represented=entry_count(truth,target,represented)
    root_probs={s:sum(h['root_state']==s for h in draws)/histories for s in states}
    root_correct=max(root_probs,key=root_probs.get)==truth['root_state']
    all_counts=np.array([entry_count(h,target) for h in draws])
    return dict(base,status='complete',true_focal_entries=known,focal_mean=mean,
        error=mean-known,absolute_error=abs(mean-known),lower=float(low),upper=float(high),
        interval_covers_truth=bool(low<=known<=high),interval_width=float(high-low),
        entry_presence_probability=float((counts>0).mean()),entry_presence_truth=known>0,
        entry_presence_brier=float(((counts>0).mean()-(known>0))**2),
        root_correct=root_correct,root_true_probability=root_probs.get(truth['root_state'],0),
        true_full_tree_entries=true_total,true_retained_tree_entries=true_represented,
        retained_event_fraction=true_represented/true_total if true_total else None,
        inferred_retained_tree_mean=float(all_counts.mean()),runtime_seconds=elapsed,
        missing_true_states=sorted(set(STATES)-set(states)),quadrature_points=diag['grid_points'])


def run(output,replicates=3,histories=100,budgets=(16,32),partitions=('development','validation'),scenarios=SCENARIOS):
    if not 1<=replicates<=1000 or histories<20:raise ValueError('Invalid benchmark size')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    protocol=dict(schema='wings.sampling-benchmark.v1',replicates=replicates,histories=histories,budgets=list(budgets),
        partitions=list(partitions),scenarios=list(scenarios),seed_bases={'development':41000,'validation':91000},
        tree='Known dated branching trees, preserved unary nodes; no sequence-to-tree estimation',
        inference='Existing fixed-tree ER CTMC, Gamma(1,1) off-diagonal-rate prior',
        estimand='Entries into focal state on branches from fixed focal-sample MRCA to those samples',
        protocol_status='Prespecified engineering benchmark; quota recommendations withheld',
        limitations=['Small smoke runs cannot establish calibration or optimal quotas.',
         'Validation seeds are disjoint; these results must not be used to tune a claimed held-out validation.',
         'No structured-coalescent, tree/dating uncertainty, unsampled-deme model, or real surveillance validation.',
         'Diversification is trait-independent; this is not an epidemic simulator.'])
    write_json(output/'protocol.json',protocol)
    records=[]
    for part,scenario,rep in itertools.product(partitions,scenarios,range(replicates)):
        seed=protocol['seed_bases'][part]+SCENARIOS.index(scenario)*1000+rep
        nodes,tips,truth=simulate(seed,scenario)
        focal,pool=sample_pool(tips,scenario,np.random.default_rng(seed+700000))
        write_json(output/'truth'/f'{part}-{scenario}-{rep}.json',dict(nodes=nodes,history=truth,
                   focal_ids=[r['id'] for r in focal],pool_ids=[r['id'] for r in pool]))
        if not focal:
            records.append(dict(partition=part,scenario=scenario,seed=seed,status='blocked',reason='fewer_than_four_focal_tips'));continue
        # Baseline, spatial/month and spatial/quarter; host and genetic sensitivity are separate.
        designs=[('available','month',False),('balanced','month',False),('balanced','quarter',False),
                 ('balanced','month',True),('diversity','month',False)]
        for budget,(strategy,width,host) in itertools.product(budgets,designs):
            try:r=evaluate(nodes,truth,focal,pool,scenario,seed,part,strategy,budget,width,host,histories)
            except (ValueError,FloatingPointError) as error:r=dict(partition=part,scenario=scenario,seed=seed,strategy=strategy,budget=budget,time_bin=width,host_strata=host,status='failed',reason=str(error))
            records.append(r)
        write_json(output/'results.json',records)
        print(f'{part}: {scenario} replicate {rep+1}/{replicates}',flush=True)
    write_json(output/'results.json',records)
    groups={}
    for r in records:
        if 'strategy' not in r:continue
        key=tuple(r[k] for k in ('partition','scenario','strategy','budget','time_bin','host_strata'))
        groups.setdefault(key,[]).append(r)
    summaries=[]
    for key,rows in sorted(groups.items()):
        valid=[r for r in rows if r['status']=='complete']
        row=dict(zip(('partition','scenario','strategy','budget','time_bin','host_strata'),key))
        row.update(completed=len(valid),blocked_or_failed=len(rows)-len(valid))
        for metric in ('error','absolute_error','interval_covers_truth','interval_width','entry_presence_brier','root_correct','retained_event_fraction','runtime_seconds'):
            values=[r[metric] for r in valid if r[metric] is not None]
            row[metric]=sum(values)/len(values) if values else None
        summaries.append(row)
    write_json(output/'summary.json',dict(protocol=protocol,groups=summaries,quota_recommendation=None,
        status='benchmark_complete' if all(r['status']!='failed' for r in records) else 'computational_failures'))
    if summaries:write_tsv(output/'summary.tsv',list(summaries[0]),summaries)
    return records


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--replicates',type=int,default=3);p.add_argument('--histories',type=int,default=100)
    p.add_argument('--budgets',type=int,nargs='+',default=[16,32]);p.add_argument('--partition',choices=['development','validation','both'],default='both')
    p.add_argument('--scenarios',nargs='+',choices=SCENARIOS,default=list(SCENARIOS));a=p.parse_args()
    if any(b<1 or b>450 for b in a.budgets):p.error('budgets must be 1..450')
    records=run(a.output,a.replicates,a.histories,tuple(a.budgets),('development','validation') if a.partition=='both' else (a.partition,),tuple(a.scenarios))
    if any(r['status']=='failed' for r in records):raise SystemExit('Benchmark contains computational failures; inspect results.json')

if __name__=='__main__':main()
