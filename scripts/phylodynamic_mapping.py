#!/usr/bin/env python3
"""Conditional Bayesian ER trait mapping using one-dimensional quadrature.

No tree MCMC: integrate a Gamma-prior migration rate on a fixed dated tree,
then sample ancestral states and continuous-time Markov bridges. This is a
symmetric discrete-trait model, not a structured coalescent or transmission model.
"""
import math
from datetime import datetime, timedelta, timezone
import numpy as np
from scipy.special import logsumexp
from scipy.stats import poisson


def numeric_date(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    start = datetime(dt.year, 1, 1, tzinfo=timezone.utc)
    end = datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc)
    return dt.year + (dt-start).total_seconds()/(end-start).total_seconds()


def calendar_date(value):
    year = math.floor(value)
    if not 1 <= year < 9999:
        raise ValueError('Dated tree is outside the supported calendar')
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return (start + (end-start)*(value-year)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


class ZeroDurationTraitConflict(ValueError):
    """Observed locations disagree within a connected zero-duration subtree."""
    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__('zero_duration_trait_conflict: conflicting tip locations '
                         'connected by zero-duration branches in the saved dated tree')


class TraitTree:
    def __init__(self, nodes, states):
        self.nodes = nodes
        self.states = list(states)
        self.k = len(states)
        if self.k < 2 or len(set(states)) != self.k:
            raise ValueError('At least two unique observed states are required')
        self.by_id = {n['id']: i for i,n in enumerate(nodes)}
        if len(self.by_id) != len(nodes):
            raise ValueError('Duplicate node IDs')
        self.children = [[] for _ in nodes]
        self.times = np.array([numeric_date(n['date']) for n in nodes])
        self.lengths = np.zeros(len(nodes))
        roots = []
        for i,n in enumerate(nodes):
            if n['parent'] is None:
                roots.append(i)
            else:
                if n['parent'] not in self.by_id:
                    raise ValueError('Unknown tree parent')
                p = self.by_id[n['parent']]
                self.children[p].append(i)
                self.lengths[i] = self.times[i]-self.times[p]
                if self.lengths[i] < 0:
                    raise ValueError('Negative time branch')
        if len(roots) != 1:
            raise ValueError('Exactly one root required')
        self.root = roots[0]
        self.order, queue, seen = [], [self.root], set()
        while queue:
            i = queue.pop()
            if i in seen:
                raise ValueError('Cycle in dated tree')
            seen.add(i); self.order.append(i)
            queue.extend(self.children[i])
        if len(seen) != len(nodes):
            raise ValueError('Disconnected dated tree')
        self.observed = {}
        for i,n in enumerate(nodes):
            if not self.children[i]:
                if n.get('observed_state') not in states:
                    raise ValueError('Unknown tip state')
                self.observed[i] = states.index(n['observed_state'])
            elif n.get('observed_state') is not None:
                raise ValueError('Internal observations are not supported')
        # P(0) is the identity: every node in a zero-time component must share
        # one state. Detect contradictory tips before rate quadrature. Do not
        # add time, relabel tips or treat this as a numerical convergence error.
        component = {}
        observations = {}
        for i in self.order:
            parent = nodes[i]['parent']
            component[i] = (component[self.by_id[parent]]
                            if parent is not None and self.lengths[i] == 0 else i)
            if i in self.observed:
                observations.setdefault(component[i], []).append(dict(
                    id=nodes[i]['id'], label=nodes[i].get('label', nodes[i]['id']),
                    date=nodes[i]['date'], observed_state=self.states[self.observed[i]]))
        conflicts = [dict(component_root=nodes[root]['id'], date=nodes[root]['date'],
                          observations=tips)
                     for root, tips in observations.items()
                     if len({tip['observed_state'] for tip in tips}) > 1]
        if conflicts:
            raise ZeroDurationTraitConflict(conflicts)

    def prune(self, rates, return_profiles=False):
        rates = np.atleast_1d(rates)
        profiles = {}
        scale = np.zeros(len(rates))
        for i in reversed(self.order):
            profiles[i] = np.ones((len(rates),self.k))
            if i in self.observed:
                profiles[i][:] = 0
                profiles[i][:,self.observed[i]] = 1
                continue
            for child in self.children[i]:
                decay = np.exp(-self.k*rates*self.lengths[child])[:,None]
                # ER P has an identity and a uniform component.
                profiles[i] *= decay*profiles[child] + (1-decay)*profiles[child].mean(axis=1)[:,None]
                if not return_profiles:
                    del profiles[child]
                norm = profiles[i].max(axis=1)
                scale += np.log(np.maximum(norm, np.finfo(float).tiny))
                profiles[i] /= np.maximum(norm[:,None],np.finfo(float).tiny)
        root = profiles[self.root].mean(axis=1)
        likelihood = np.where(root > 0, np.log(np.maximum(root,np.finfo(float).tiny))+scale, -np.inf)
        return (likelihood, profiles) if return_profiles else likelihood


def posterior_grid(tree, shape=1, rate=1, tolerance=0.001):
    if not (math.isfinite(shape) and math.isfinite(rate) and min(shape,rate)>0):
        raise ValueError('Invalid Gamma prior')
    def log_density(x):
        q = np.exp(x)
        return tree.prune(q) + shape*x-rate*q  # Gamma(q) times dq/d(log q).
    lo, hi = math.log(shape/rate)-12, math.log(shape/rate)+8
    for _ in range(12):
        x = np.linspace(lo,hi,257)
        lp = log_density(x)
        peak = np.max(lp)
        if not np.isfinite(peak):
            raise ValueError('Trait observations have zero probability on this tree')
        left, right = lp[0] > peak-30, lp[-1] > peak-30
        if not left and not right:
            break
        if left: lo -= 8
        if right: hi += 4
    else:
        raise ValueError('Posterior tails could not be bounded')
    previous = None
    for n in (257,513,1025,2049,4097):
        x = np.linspace(lo,hi,n)
        lp = log_density(x)
        lp[[0,-1]] += math.log(0.5)
        p = np.exp(lp-logsumexp(lp))
        mean = float(p @ np.exp(x))
        if previous:
            px, pp, pm = previous
            # CDFs at cell centers compensate for the discrete grid half-step.
            error = float(np.max(np.abs(np.interp(px,x,np.cumsum(p)-p/2)-(np.cumsum(pp)-pp/2))))
            if error < tolerance and abs(mean-pm)/max(mean,1e-12) < tolerance:
                return np.exp(x), p, dict(grid_points=n, cdf_error=error, rate_mean=mean,
                    log_rate_bounds=[lo,hi], tail_log_density_drop=30,
                    prior_shape=shape, prior_rate=rate, approximation='refined log-rate quadrature')
        previous = x,p,mean
    raise ValueError('Rate posterior quadrature failed refinement checks')


def bridge(start, end, years, q, k, rng):
    """ER bridge by uniformization with rate k*q and uniform embedded states."""
    if years == 0:
        if start != end:
            raise ValueError('State change on a zero-duration branch')
        return []
    mu = k*q*years
    if not np.isfinite(mu) or mu <= 0 or mu > 100000:
        raise ValueError('Invalid or excessively large bridge rate')
    nonzero = -math.expm1(-mu)
    if start == end and rng.random() >= nonzero/(1+(k-1)*math.exp(-mu)):
        return []
    # Positive-truncated Poisson. Survival inversion avoids cancellation at small mu.
    n = int(poisson.isf((1-rng.random())*nonzero, mu))
    if n < 1:
        n = 1
    times = np.sort(rng.uniform(np.nextafter(0.0,1.0),1.0,n))
    next_states = list(rng.integers(k,size=n-1)) + [end]
    transitions, current = [], start
    for fraction, state in zip(times,next_states):
        if state != current:
            transitions.append((float(fraction), current, int(state)))
        current = int(state)
    return transitions


def sample_histories(nodes, states, count, seed, shape=1, rate=1):
    tree = TraitTree(nodes, states)
    qvalues, weights, diagnostics = posterior_grid(tree, shape, rate)
    rng = np.random.default_rng(seed)
    sampled_rates = rng.choice(qvalues, size=count, p=weights)
    histories = []
    for h,q in enumerate(sampled_rates):
        _, profiles = tree.prune([q], True)
        assigned = {}
        rp = profiles[tree.root][0]
        assigned[tree.root] = int(rng.choice(tree.k,p=rp/rp.sum()))
        jumps = []
        for parent in tree.order:
            for child in tree.children[parent]:
                decay = math.exp(-tree.k*q*tree.lengths[child])
                transition = np.full(tree.k,(1-decay)/tree.k)
                transition[assigned[parent]] += decay
                p = transition*profiles[child][0]
                if p.sum() <= 0:
                    raise ValueError('Impossible conditional ancestral state')
                assigned[child] = int(rng.choice(tree.k,p=p/p.sum()))
                for fraction,src,dst in bridge(assigned[parent],assigned[child],tree.lengths[child],q,tree.k,rng):
                    dt = calendar_date(tree.times[parent]+fraction*tree.lengths[child])
                    if not tree.times[parent] < numeric_date(dt) <= tree.times[child]:
                        raise ValueError('Event is finer than the movie time resolution')
                    jumps.append(dict(branch=nodes[child]['id'],date=dt,**{'from':states[src],'to':states[dst]}))
        histories.append(dict(id=str(h+1),root_state=states[assigned[tree.root]],jumps=jumps))
    diagnostics.update(histories=count, seed=seed, rate_draw_mean=float(np.mean(sampled_rates)))
    return histories, diagnostics
