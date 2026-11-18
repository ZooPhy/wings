"""Common focal-sample ancestry estimand, separate from all-tree jump counts."""

def focal_branches(nodes, tip_ids):
    by_id={r['id']:r for r in nodes}
    if len(tip_ids)<2:return set(),None
    paths=[]
    for tip in tip_ids:
        path=[];seen=set();current=tip
        while current is not None:
            if current in seen or current not in by_id:raise ValueError('Invalid focal ancestry')
            seen.add(current);path.append(current);current=by_id[current]['parent']
        paths.append(path)
    shared=set(paths[0]).intersection(*map(set,paths[1:]))
    if not shared:raise ValueError('Disconnected focal samples')
    mrca=next(n for n in paths[0] if n in shared)
    branches=set()
    for path in paths:branches.update(path[:path.index(mrca)])
    return branches,mrca


def entry_count(history, target, branches=None):
    return sum(j['to']==target and (branches is None or j['branch'] in branches) for j in history['jumps'])
