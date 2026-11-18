#!/usr/bin/env python3
"""Compare inference replicates without pooling their posterior histories."""
import argparse
import html
import json
from pathlib import Path
from phylodynamic_selection import write_json
from build_phylodynamic_comparison import scoped_movie, write_comparison


def summarize(selection_dir, inference_dir, output):
    selection = json.loads((selection_dir/'selection_summary.json').read_text())
    records, movies = [], {}
    for item in selection['replicates']:
        folder = inference_dir/item['id']
        record = json.loads((folder/'result.json').read_text())
        records.append(record)
        if record['status'] == 'complete':
            movies[item['id']], _ = scoped_movie(json.loads((folder/'movie.json').read_text()), record)
    cfg=selection['config']
    primary_strategy='balanced' if 'balanced' in cfg['strategies'] else cfg['strategies'][0]
    primary_ids=[f'{s}/{primary_strategy}/replicate_1' for s in cfg['segments']]
    # Do not replace an unsuccessful predeclared primary with a favorable replicate.
    primary = None
    available = [movies[key] for key in primary_ids if key in movies]
    if available:
        primary = dict(available[0])
        primary['title']='WINGS primary reference subsets'
        primary['provenance']=dict(primary['provenance'],analyses=primary_ids,
            note='Predeclared replicate 1; segments with blocked analyses are omitted.')
        primary['segments']=[seg for m in available for seg in m['segments']]
        primary['locations']=list({loc['id']:loc for m in available for loc in m['locations']}.values())
    sensitivity = []
    for segment in cfg['segments']:
        complete=[r for r in records if r['segment']==segment and r['status']=='complete']
        for location in sorted({loc for r in complete for loc in r['introductions']}):
            estimates=[r['introductions'][location]['mean'] for r in complete if location in r['introductions']]
            sensitivity.append(dict(segment=segment,location=location,completed_replicates=len(estimates),
                mean_range=[min(estimates),max(estimates)],
                note='Range of replicate posterior means; not a credible interval. Missing locations are not zeros.'))
    result=dict(schema='wings.phylodynamic-sensitivity.v1',selection=selection,
        analyses=records,sensitivity=sensitivity,primary_analyses=primary_ids,phylogeography=primary,
        limitations=['Available reference pools may have unmeasured surveillance bias.',
            'Conditional ER trait inference: fixed dated ML tree, symmetric transitions, uniform root prior.',
            'Replicate ranges measure sampling sensitivity; they are not pooled Bayesian posteriors.',
            'Inferred geographic jumps are not observed introductions or transmission events.',
            'References are screened to the study HA clade; closest references are reserved before context sampling.',
            'Reference quotas are engineering settings, not validated corrections for sampling bias.',
            'Clock permutation diagnostics are conditional on an ML tree, not a Bayesian rate-interval test.',
            'Country-level external states and US/Canadian administrative units have different geographic scales.'])
    write_json(output/'summary.json',result)
    write_json(output/'primary_movie.json',primary)
    rows=[]
    for r in records:
        for location,values in (r.get('introductions') or {'—':{}}).items():
            interval=(f"{values['mean']:.2f} ({values['lower']:.1f}–{values['upper']:.1f})" if values else 'Unavailable')
            diagnostic=r.get('temporal_diagnostics',{})
            raw=diagnostic.get('observed',{}).get('r2')
            ps=r.get('date_permutation_p',{})
            check=('R² '+format(raw,'.3f')+'; p '+format(ps.get('tips',1),'.3f')+'/'+format(ps.get('same_date_clades',1),'.3f')) if raw is not None else 'Not run'
            cells=[r.get('lineage',{}).get('target_clade') or 'Unresolved',check,r['segment'],r['strategy'],str(r['replicate']),str(r['study']),str(r['references']),location,interval,
                   r['status']+(': '+', '.join(r['reasons']) if r['reasons'] else '')]
            link=f"inference/{r['id']}/movie.json"
            rows.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+
                        ('<td>'+('<a href="'+html.escape(link,quote=True)+'" download>Movie data</a> ' if values else '')+
                         ('<a href="'+html.escape(f"inference/{r['id']}/temporal_diagnostics.json",quote=True)+'" download>Clock diagnostics</a>' if diagnostic else '—')+'</td>')+'</tr>')
    body='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>WINGS sampling sensitivity</title>
<style>body{font:16px system-ui;margin:2rem;color:#243840}h1{color:#8c1d40}table{border-collapse:collapse;width:100%}th{background:#8c1d40;color:white;text-align:left}th,td{padding:.7rem;border-bottom:1px solid #dce3e5}tr:nth-child(even){background:#f5f8f8}a{color:#8c1d40}.table{overflow:auto}</style>
<h1>Reference sampling sensitivity</h1><p><a href="comparison.html">Compare replicate movies, trees and clock diagnostics →</a></p><p>Entries on study-sample ancestry: posterior mean (95% interval), conditional on each dated tree. The ancestry begins at the study-sample MRCA. Clock check reports raw-ML R² and tip/cluster permutation p-values.</p><ul>'''
    body+=''.join('<li>'+html.escape(x)+'</li>' for x in result['limitations'])+'</ul><div class="table"><table><thead><tr>'
    body+=''.join('<th>'+x+'</th>' for x in ['HA clade','Clock check','Segment','Strategy','Replicate','Study','References','Location','Introductions','Status','Download'])
    body+='</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div><p>Load a replicate’s movie data in Genomics → Phylogeography movie. The primary display uses the predeclared first balanced replicate.</p></html>'
    (output/'sensitivity.html').write_text(body)
    write_comparison(result, output, inference_dir)
    return result

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('selection','inference','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();summarize(a.selection,a.inference,a.output)
