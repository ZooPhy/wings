"""Root-optimized date-permutation diagnostics on an unconstrained ML tree.

These are regression permutation diagnostics, NOT a Bayesian rate-interval DRT.
Both tip and same-date monophyletic-cluster permutations are required. The root
is reoptimized for every permutation; no dated-tree branch lengths are used.
"""
import math
import re
from datetime import date
from pathlib import Path

DEFAULTS=dict(permutations=199,alpha=0.05)


def configuration(raw):
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS):raise ValueError('Invalid temporal options')
    cfg=dict(DEFAULTS,**raw)
    if type(cfg['permutations']) is not int or not 99<=cfg['permutations']<=999:
        raise ValueError('temporal.permutations must be 99–999')
    if type(cfg['alpha']) not in (int,float) or not math.isfinite(cfg['alpha']) or not 0<cfg['alpha']<=.05:
        raise ValueError('temporal.alpha must be in (0,0.05]')
    return cfg


def parse_tree(text):
    """Read IQ-TREE Newick with the pipeline's safe unquoted tip IDs."""
    if any(c in text for c in "'\"[]"):
        raise ValueError('Expected plain IQ-TREE Newick with safe pipeline IDs')
    tokens=re.findall(r'[^\s(),:;]+|[(),:;]',text); pos=0; names=[];adj=[]
    def read():
        nonlocal pos
        children=[];name=''
        if tokens[pos]=='(':
            pos+=1;children.append(read())
            while tokens[pos]==',':pos+=1;children.append(read())
            if tokens[pos]!=')':raise ValueError('Malformed Newick')
            pos+=1
        if tokens[pos] not in [',',')',':',';']:name=tokens[pos];pos+=1
        length=0.
        if tokens[pos]==':':pos+=1;length=float(tokens[pos]);pos+=1
        if not math.isfinite(length) or length<0:raise ValueError('Invalid ML branch length')
        k=len(names);names.append(name);adj.append([])
        for c,l in children:adj[k].append((c,l));adj[c].append((k,l))
        return k,length
    try:
        root,_=read()
        if tokens[pos:]!=[';']:raise ValueError('Malformed Newick terminator')
    except (IndexError,RecursionError) as e:raise ValueError('Malformed or excessive Newick nesting') from e
    return names,adj,root


class Regression:
    def __init__(self,text,metadata):
        import numpy as np
        self.names,self.adj,root=parse_tree(text)
        self.leaves=[i for i,edges in enumerate(self.adj) if len(edges)==1 and i!=root]
        self.ids=[self.names[k] for k in self.leaves]
        if len(self.ids)!=len(set(self.ids)) or set(self.ids)!=set(metadata):
            raise ValueError('Tree tips and dated metadata do not match')
        self.index={k:i for i,k in enumerate(self.leaves)}
        D=np.zeros((len(self.names),len(self.leaves)))
        for u in range(len(self.names)):
            stack=[(u,-1,0.)]
            while stack:
                k,p,d=stack.pop()
                if k in self.index:D[u,self.index[k]]=d
                stack.extend((c,k,d+l) for c,l in self.adj[k] if c!=p)
        self.D=D
        self.edges=[(u,v,l) for u,a in enumerate(self.adj) for v,l in a if u<v]
        self.Y=np.array([D[u] for u,v,l in self.edges])
        self.S=np.array([np.where(D[v]<D[u],-1.,1.) for u,v,l in self.edges])
        self.Yc=self.Y-self.Y.mean(1)[:,None];self.Sc=self.S-self.S.mean(1)[:,None]
        self.yy=np.einsum('ij,ij->i',self.Yc,self.Yc)
        self.ss=np.einsum('ij,ij->i',self.Sc,self.Sc)
        self.ys=np.einsum('ij,ij->i',self.Yc,self.Sc)
        self.lengths=np.array([l for u,v,l in self.edges])
        self.dates=np.array([date.fromisoformat(metadata[k]['date']).toordinal()/365.25 for k in self.ids])

    def fit(self,dates):
        import numpy as np
        x=np.asarray(dates)-np.mean(dates);xx=x@x
        if xx<=0:raise ValueError('At least two distinct dates required')
        xy=np.einsum('ij,j->i',self.Yc,x);xs=np.einsum('ij,j->i',self.Sc,x)
        a=self.yy-xy**2/xx;b=self.ss-xs**2/xx;c=self.ys-xy*xs/xx
        f=np.clip(np.divide(-c,b,out=np.zeros_like(c),where=b>1e-20),0,self.lengths)
        sse=np.maximum(0,a+2*f*c+f*f*b);i=int(np.argmin(sse))
        cov=xy[i]+f[i]*xs[i];variance=self.yy[i]+2*f[i]*self.ys[i]+f[i]**2*self.ss[i]
        r2=float(np.clip(cov**2/(xx*variance),0,1)) if variance>0 else 0.
        return dict(rate=float(cov/xx),r2=r2,sse=float(sse[i]),edge=i,position=float(f[i]))

    def distances(self,fit):
        return self.Y[fit['edge']]+fit['position']*self.S[fit['edge']]

    def clusters(self,fit):
        """Maximal same-date subtrees, rooted at the observed LS root."""
        def walk(u,parent):
            if u in self.index:
                i=self.index[u];return [i],[[i]]
            tips=[];groups=[]
            for v,_ in self.adj[u]:
                if v==parent:continue
                ti,gr=walk(v,u);tips+=ti;groups+=gr
            if tips and len(set(self.dates[tips]))==1:return tips,[tips]
            return tips,groups
        u,v,_=self.edges[fit['edge']]
        groups=walk(u,v)[1]+walk(v,u)[1]
        if sorted(i for g in groups for i in g)!=list(range(len(self.ids))):
            raise ValueError('Invalid permutation clusters')
        return groups


def diagnose(tree_path,metadata,output,cfg,min_r2,seed):
    import numpy as np
    from phylodynamic_selection import write_json,write_tsv,digest
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    model=Regression(Path(tree_path).read_text(),metadata)
    observed=model.fit(model.dates);groups=model.clusters(observed);reasons=[]
    if observed['rate']<=0:reasons.append('nonpositive_raw_ml_clock_rate')
    if observed['r2']<min_r2:reasons.append('weak_raw_ml_clock_fit')
    rng=np.random.default_rng(seed);nulls={}; n=cfg['permutations']
    for mode in ('tips','same_date_clades'):
        vals=[]
        if mode=='same_date_clades' and (len(groups)<4 or len(set(model.dates))<3):
            reasons.append('insufficient_temporal_permutation_clusters');continue
        for _ in range(n):
            if mode=='tips':dates=rng.permutation(model.dates)
            else:
                labels=rng.permutation([model.dates[g[0]] for g in groups]);dates=model.dates.copy()
                for g,label in zip(groups,labels):dates[g]=label
            fitted=model.fit(dates)
            vals.append(dict(rate=fitted['rate'],r2=fitted['r2'],
                             statistic=fitted['r2'] if fitted['rate']>0 else 0.))
        statistic=observed['r2'] if observed['rate']>0 else 0.
        p=(1+sum(v['statistic']>=statistic-1e-12 for v in vals))/(n+1)
        nulls[mode]=dict(p_value=p,permutations=n,draws=vals)
        if p>cfg['alpha']:reasons.append('date_permutation_not_supported_'+mode)
    distances=model.distances(observed);group_ids={i:g for g,a in enumerate(groups) for i in a}
    points=[dict(id=k,date=metadata[k]['date'],source=metadata[k].get('source',''),
                 root_distance=float(distances[i]),cluster=group_ids[i]) for i,k in enumerate(model.ids)]
    write_tsv(output/'clock_points.tsv',['id','date','source','root_distance','cluster'],points)
    report=dict(schema='wings.temporal-diagnostics.v1',status='blocked' if reasons else 'passed',
        reasons=reasons,observed=observed,permutations=nulls,clusters=len(groups),
        cluster_members=[[model.ids[i] for i in g] for g in groups],seed=seed,config=cfg,
        tree_sha256=digest(tree_path),
        method='Root-optimized least-squares regression; positive-slope R2 statistic; tip and same-date monophyletic-cluster permutations.',
        limitations=['Fixed unconstrained ML topology and branch lengths; no tree uncertainty.',
                     'Regression permutation diagnostic, not Bayesian rate-interval date randomization or calibrated dating.',
                     'Observed-root clusters are fixed across permutations; roots are reoptimized.',
                     'Population structure can confound temporal inference even when these screens pass.'])
    write_json(output/'temporal_diagnostics.json',report)
    return report
