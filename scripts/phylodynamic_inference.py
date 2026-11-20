#!/usr/bin/env python3
"""MAFFT, IQ-TREE, TreeTime and conditional Bayesian geographic histories."""
import argparse
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from phylodynamic_selection import read_tsv, write_json, digest
from phylodynamic_mapping import numeric_date, calendar_date, sample_histories
from phylodynamic_estimands import focal_branches, entry_count


def mafft_runtime():
    """Use binaries beside the selected launcher when installed by conda.

    Conda's MAFFT launcher can retain an unquoted, pre-relocation prefix.
    Override it only for this subprocess; other installation layouts retain
    their normal MAFFT_BINARIES setting and MAFFT's own version validation.
    """
    executable = shutil.which('mafft')
    if executable is None:
        raise FileNotFoundError('MAFFT executable not found on PATH')
    executable = str(Path(executable).absolute())
    binaries = Path(executable).parent.parent / 'libexec' / 'mafft'
    env = os.environ.copy()
    if binaries.is_dir():
        env['MAFFT_BINARIES'] = str(binaries)
    return executable, env


def infer(selection_dir, output, threads):
    selection = json.loads((selection_dir / 'selection.json').read_text())
    cfg = selection['config']
    output.mkdir(parents=True, exist_ok=True)
    for name in ('dated_nodes.json','temporal_diagnostics.json','clock_points.tsv'):
        (output/name).unlink(missing_ok=True)
    result = {k:selection[k] for k in ('id','segment','strategy','replicate','seed','study','references','locations')}
    result.update(lineage=selection.get('lineage',{}),status='blocked', reasons=list(selection['reasons']), selection_sha256=digest(selection_dir/'selection.json'))
    # A blocked replicate always replaces any stale reconstruction with null.
    write_json(output/'movie.json', None)
    write_json(output/'result.json', dict(result,status='incomplete',reasons=['inference_not_completed']))
    if selection['status'] != 'ready':
        write_json(output/'result.json',result)
        return result
    lineage=selection.get('lineage',{})
    if lineage.get('status')!='ready' or not lineage.get('target_clade'):
        result['reasons'].append('missing_or_unresolved_lineage_screen')
        write_json(output/'result.json',result)
        return result
    result['lineage']=lineage
    from treetime import TreeTime
    from Bio import Phylo
    tips = read_tsv(selection_dir/'tips.tsv')
    metadata = {r['id']:r for r in tips}
    if len(metadata) != len(tips):
        raise ValueError('Duplicate tip IDs')
    if digest(selection_dir/'input.fasta') != selection['selected_sha256']:
        raise ValueError('Selected FASTA changed after selection')
    mafft, mafft_env = mafft_runtime()
    commands = [
        [mafft,'--auto','--thread',str(threads),str((selection_dir/'input.fasta').resolve())],
        ['iqtree2','-s',str((output/'alignment.fasta').resolve()),'-m','GTR+G',
         '-nt',str(threads),'-seed',str(selection['seed'] % 2147483647),
         '-pre',str((output/'ml').resolve()),'-redo']]
    with (output/'tools.log').open('w') as log:
        subprocess.run([mafft,'--version'],stdout=log,stderr=log,check=True,env=mafft_env)
        subprocess.run(['iqtree2','--version'],stdout=log,stderr=log,check=True)
        with (output/'alignment.fasta').open('w') as aln:
            subprocess.run(commands[0],stdout=aln,stderr=log,check=True,env=mafft_env)
        subprocess.run(commands[1],stdout=log,stderr=log,check=True)
    tree = Phylo.read(output/'ml.treefile','newick')
    if {n.name for n in tree.get_terminals()} != set(metadata):
        raise ValueError('ML tree tips do not match selected tips')
    result['software']={p:importlib.metadata.version(p) for p in ('phylo-treetime','biopython','numpy','scipy')}
    from phylodynamic_temporal import diagnose
    diagnostic=diagnose(output/'ml.treefile',metadata,output,cfg['temporal'],cfg['min_clock_r2'],selection['seed'])
    result.update(clock_rate=diagnostic['observed']['rate'],clock_r2=diagnostic['observed']['r2'],
        temporal_diagnostics={k:v for k,v in diagnostic.items() if k not in ('permutations','cluster_members')},
        date_permutation_p={k:v['p_value'] for k,v in diagnostic['permutations'].items()},commands=commands)
    if diagnostic['status']!='passed':
        result['reasons'].extend(diagnostic['reasons'])
        write_json(output/'result.json',result)
        return result
    tt = TreeTime(tree=tree,aln=str(output/'alignment.fasta'),
                  dates={key:numeric_date(r['date']) for key,r in metadata.items()},gtr='JC69',verbose=0)
    tt.run(root='least-squares',infer_gtr=True,max_iter=2,resolve_polytomies=False,
           n_iqd=None,time_marginal='never',use_covariation=False,raise_uncaught_exceptions=True)
    clock_rate = float(tt.date2dist.clock_rate)
    r_squared = float(tt.date2dist.r_val)**2
    result.update(clock_rate=clock_rate if math.isfinite(clock_rate) else None,
                  clock_r2=r_squared if math.isfinite(r_squared) else None,
                  temporal_screen='Positive rate and R2 plus raw-ML tip and same-date-clade permutation diagnostics; conditional on one tree, not Bayesian rate-interval DRT.',
                  software={p:importlib.metadata.version(p) for p in ('phylo-treetime','biopython','numpy','scipy')},
                  commands=commands)
    if not math.isfinite(clock_rate) or clock_rate <= 0 or not math.isfinite(r_squared) or r_squared < cfg['min_clock_r2']:
        result['reasons'].append('temporal_screen_failed')
        write_json(output/'result.json',result)
        return result
    clades = list(tt.tree.find_clades(order='preorder'))
    ids = {id(c): (c.name if c.is_terminal() else f'ancestor_{i}') for i,c in enumerate(clades)}
    parents = {id(child):id(parent) for parent in clades for child in parent.clades}
    nodes = []
    for c in clades:
        if getattr(c,'bad_branch',False):
            result['reasons'].append('unusable_dated_branch')
        node = dict(id=ids[id(c)],parent=ids.get(parents.get(id(c))),date=calendar_date(float(c.numdate)))
        if c.is_terminal():
            r = metadata[c.name]
            node.update(observed_state=r['location'],label=r['sample_id'] or r['accession'])
            if r['sample_id']:
                node['sample_id'] = r['sample_id']
        nodes.append(node)
    if result['reasons']:
        write_json(output/'result.json',result)
        return result
    write_json(output/'dated_nodes.json',nodes)
    states = sorted(selection['locations'])
    histories, diagnostics = sample_histories(nodes,states,cfg['histories'],selection['seed'],
                                              cfg['rate_prior_shape'],cfg['rate_prior_rate'])
    result.update(status='complete', quadrature=diagnostics,
                  uncertainty='conditional-on-fixed-tree',
                  introduction_definition='All sampled jumps into a location from another observed location; includes reversals and re-entries.')
    import numpy as np
    result['introductions'] = {}
    result['all_tree_jumps'] = {}
    branches,mrca=focal_branches(nodes,[r['id'] for r in nodes if r.get('sample_id')])
    result['introduction_definition']='Entries on the ancestry from the study-sample MRCA to the same retained study tips; excludes the ancestral stem and unrepresented transmission.'
    result['focal_mrca']=mrca
    result['focal_sample_ids']=sorted(r['sample_id'] for r in nodes if r.get('sample_id'))
    if mrca is None:
        result['reasons'].append('focal_entry_counts_require_two_study_tips')
    for state in states:
        all_counts=[entry_count(h,state) for h in histories]
        result['all_tree_jumps'][state]=dict(mean=float(np.mean(all_counts)),definition='All retained-tree jumps; changes with the reference background.')
        if mrca is None:continue
        counts = [entry_count(h,state,branches) for h in histories]
        result['introductions'][state] = dict(mean=float(np.mean(counts)),
             lower=float(np.quantile(counts,.025)),upper=float(np.quantile(counts,.975)),
             zero_probability=sum(n==0 for n in counts)/len(counts))
    movie = dict(schema='wings.phylogeography-movie.v1',title='WINGS '+selection['id'],synthetic=False,
        provenance=dict(method='ER geographic CTMC; Gamma rate prior integrated by refined quadrature; exact conditional bridges',
            inference='bayesian',uncertainty='conditional-on-fixed-tree',analysis=selection['id'],
            prior=dict(shape=cfg['rate_prior_shape'],rate=cfg['rate_prior_rate'],units='off-diagonal transitions per year'),
            root_prior='uniform over observed locations',selection_sha256=result['selection_sha256'],
            temporal_screen=result['temporal_screen']),
        locations=selection['location_metadata'],segments=[dict(id=selection['segment'],nodes=nodes,histories=histories)])
    from build_phylogeography_movie import validate
    validate(movie, for_analysis=True)
    write_json(output/'movie.json',movie)
    write_json(output/'result.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--threads',type=int,default=4)
    a=p.parse_args()
    infer(a.selection,a.output,a.threads)

if __name__ == '__main__':
    main()
