"""One-dimensional ER geographic-rate integration; Gamma and lognormal priors."""
import math
import numpy as np
from scipy.special import logsumexp
from phylodynamic_mapping import TraitTree, posterior_grid, bridge, calendar_date, numeric_date


def prior_config(raw, source=None):
    if raw is None or raw=={'family':'source'}:
        if not source:raise ValueError('Source prior is unavailable')
        return prior_config(dict(family='gamma',parameter='pair_rate',shape=float(source['shape']),rate=float(source['rate'])))
    if not isinstance(raw,dict):raise ValueError('Geographic prior must be a mapping')
    family=raw.get('family');parameter=raw.get('parameter','exit_rate')
    if parameter not in ('pair_rate','exit_rate'):raise ValueError('Prior parameter must be pair_rate or exit_rate')
    expected={'family','parameter'}|({'shape','rate'} if family=='gamma' else {'median','log_sd'} if family=='lognormal' else set())
    if family not in ('gamma','lognormal') or set(raw)-expected:raise ValueError('Unknown geographic prior family or setting')
    out=dict(raw,parameter=parameter)
    for key in expected-{'family','parameter'}:
        v=out.get(key)
        if type(v) not in (int,float) or not math.isfinite(v) or v<=0:raise ValueError('Invalid prior '+key)
    return out


def integrate(tree,prior):
    p=prior_config(prior);factor=tree.k-1 if p['parameter']=='exit_rate' else 1
    if p['family']=='gamma':
        q,w,d=posterior_grid(tree,p['shape'],p['rate']*factor)
        return q,w,dict(d,prior=p,rate_parameter='off-diagonal pair rate per year',exit_factor=tree.k-1)
    mu=math.log(p['median']/factor);sd=p['log_sd'];lo=mu-8*sd;hi=mu+8*sd
    def density(x):return tree.prune(np.exp(x))-.5*((x-mu)/sd)**2
    for _ in range(12):
        if lo < -700 or hi > 700:raise ValueError('Lognormal prior exceeds numerical rate range')
        x=np.linspace(lo,hi,257);lp=density(x);peak=float(np.max(lp))
        if not math.isfinite(peak):raise ValueError('Nonfinite geographic likelihood')
        left=lp[0]>peak-30;right=lp[-1]>peak-30
        if not left and not right:break
        if left:lo-=max(4,4*sd)
        if right:hi+=max(4,4*sd)
    else:raise ValueError('Lognormal posterior tails could not be bounded')
    previous=None
    for n in (257,513,1025,2049,4097):
        x=np.linspace(lo,hi,n);lp=density(x);lp[[0,-1]]+=math.log(.5);w=np.exp(lp-logsumexp(lp));q=np.exp(x);mean=float(w@q)
        if previous:
            px,pw,pm=previous
            err=float(np.max(np.abs(np.interp(px,x,np.cumsum(w)-w/2)-(np.cumsum(pw)-pw/2))))
            if err<.001 and abs(mean-pm)/max(mean,1e-12)<.001:
                return q,w,dict(grid_points=n,cdf_error=err,rate_mean=mean,prior=p,
                  log_rate_bounds=[lo,hi],rate_parameter='off-diagonal pair rate per year',exit_factor=tree.k-1,
                  approximation='refined log-rate quadrature')
        previous=x,w,mean
    raise ValueError('Lognormal geographic-rate quadrature failed refinement checks')


def histories(nodes,states,count,seed,prior):
    tree=TraitTree(nodes,states);q,w,diagnostics=integrate(tree,prior);rng=np.random.default_rng(seed)
    draws=rng.choice(q,size=count,p=w);out=[]
    for index,rate in enumerate(draws):
        _,profiles=tree.prune([rate],True);assigned={};rp=profiles[tree.root][0]
        assigned[tree.root]=int(rng.choice(tree.k,p=rp/rp.sum()));jumps=[]
        for parent in tree.order:
            for child in tree.children[parent]:
                decay=math.exp(-tree.k*rate*tree.lengths[child]);prob=np.full(tree.k,(1-decay)/tree.k);prob[assigned[parent]]+=decay
                prob*=profiles[child][0]
                if prob.sum()<=0:raise ValueError('Impossible conditional state')
                assigned[child]=int(rng.choice(tree.k,p=prob/prob.sum()))
                for fraction,src,dst in bridge(assigned[parent],assigned[child],tree.lengths[child],rate,tree.k,rng):
                    date=calendar_date(tree.times[parent]+fraction*tree.lengths[child])
                    if not tree.times[parent]<numeric_date(date)<=tree.times[child]:raise ValueError('Event is finer than date resolution')
                    jumps.append(dict(branch=nodes[child]['id'],date=date,**{'from':states[src],'to':states[dst]}))
        out.append(dict(id=str(index+1),root_state=states[assigned[tree.root]],jumps=jumps))
    return out,dict(diagnostics,histories=count,seed=seed)
