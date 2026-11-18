#!/usr/bin/env python3
"""Build an offline replicate comparison from existing results; never refit an analysis."""
import argparse
import csv
from datetime import date as calendar_date
import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from phylodynamic_estimands import focal_branches, entry_count


def script_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def scoped_movie(movie, record):
    """Declare the same study ancestry used by the inference, retaining every history."""
    samples = record.get('focal_sample_ids')
    if not isinstance(samples, list) or len(samples) < 2 or len(set(samples)) != len(samples):
        raise ValueError('Missing or ambiguous focal samples: ' + record['id'])
    segments = []
    info = None
    for segment in movie['segments']:
        if segment['id'] != record['segment']:
            raise ValueError('Replicate movie has an unexpected segment')
        nodes = segment['nodes']
        tips = [n['id'] for n in nodes if n.get('sample_id') in samples]
        if len(tips) != len(samples) or {n.get('sample_id') for n in nodes if n['id'] in tips} != set(samples):
            raise ValueError('Movie is missing declared study samples: ' + record['id'])
        if any(n['parent'] in tips for n in nodes):
            raise ValueError('Study samples must be tips')
        branches, mrca = focal_branches(nodes, tips)
        if mrca != record.get('focal_mrca'):
            raise ValueError('Focal MRCA differs from inference: ' + record['id'])
        roots = [n for n in nodes if n['parent'] is None]
        if len(roots) != 1 or not segment['histories']:
            raise ValueError('Invalid root or empty histories')
        histograms = {}
        for location, estimate in record.get('introductions', {}).items():
            hist = {}
            counts = [entry_count(h, location, branches) for h in segment['histories']]
            if not math.isclose(sum(counts)/len(counts), estimate['mean'], abs_tol=1e-9):
                raise ValueError('Movie counts differ from summary: ' + record['id'] + ' / ' + location)
            for n in counts: hist[str(n)] = hist.get(str(n), 0) + 1
            histograms[location] = hist
        by_id = {n['id']: n for n in nodes}
        info = dict(root_date=roots[0]['date'], study_mrca_date=by_id[mrca]['date'],
                    study_mrca=mrca, histories=len(segment['histories']), histograms=histograms)
        segments.append(dict(segment, focal_sample_ids=samples))
    if not segments: raise ValueError('No segment in movie')
    return dict(movie, segments=segments), info


def write_comparison(summary, output, inference=None, dating_run='initial'):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',dating_run):raise ValueError('Invalid dating run ID')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    inference = Path(inference) if inference is not None else output/'inference'
    assets = output/'comparison_assets'; assets.mkdir(exist_ok=True)
    source = Path(__file__).resolve().parent/'report'
    for name in ('phylodynamic-comparison.js', 'phylodynamic-comparison.css',
                 'phylogeography-movie.js', 'phylogeography-movie.css', 'map-boundaries.js'):
        shutil.copyfile(source/name, assets/name)
    records = []; labels = {}
    for record in summary['analyses']:
        key = record['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/replicate_[0-9]+', key):
            raise ValueError('Unsafe replicate ID: ' + key)
        r = dict(record)
        folder = inference/key
        movie_path = folder/'movie.json'
        r['movie_script'] = None
        if record['status'] == 'complete' and movie_path.is_file():
            movie, info = scoped_movie(json.loads(movie_path.read_text()), record)
            r.update(info)
            filename = 'movie-' + hashlib.sha256(key.encode()).hexdigest()[:20] + '.js'
            (assets/filename).write_text('window.WINGS_COMPARISON_RECEIVE(' + script_json(key) + ',' + script_json(movie) + ');\n')
            r['movie_script'] = 'comparison_assets/' + filename
            labels.update({s['id']: s['label'] for s in movie['locations']})
        r['clock_points'] = []
        points = folder/'clock_points.tsv'
        if points.is_file():
            with points.open() as f:
                for p in csv.DictReader(f, delimiter='\t'):
                    distance=float(p['root_distance']); date=1970+(calendar_date.fromisoformat(p['date'])-calendar_date(1970,1,1)).days/365.25
                    if not math.isfinite(distance) or not math.isfinite(date):
                        raise ValueError('Nonfinite clock point: '+key)
                    r['clock_points'].append(dict(id=p['id'],date=date,root_distance=distance,source=p.get('source','')))
        dating_path=inference.parent/'bayesian'/key/dating_run/'summary.json'
        if dating_path.is_file():
            dating=json.loads(dating_path.read_text())
            current=inference/key/'result.json'
            sources={name:inference/key/name for name in ('result.json','alignment.fasta','dated_nodes.json')}
            sources['tips.tsv']=inference.parent/'selection'/key/'tips.tsv'
            if 'ml.treefile' in dating.get('input_sha256',{}):sources['ml.treefile']=inference/key/'ml.treefile'
            hashes_match=all(path.is_file() and dating.get('input_sha256',{}).get(name)==hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sources.items())
            if (dating.get('analysis')==key and hashes_match and current.is_file()
                and dating.get('input_sha256',{}).get('result.json')==hashlib.sha256(current.read_bytes()).hexdigest()
                and dating.get('focal_sample_ids')==record.get('focal_sample_ids')):
                r['bayesian_dating']=dating
                r['bayesian_report']='bayesian/'+key+'/'+dating_run+'/tmrca.html'
            else:
                r['bayesian_dating']={'status':'stale_or_mismatched','tmrca':None}
        records.append(r)
    model = dict(schema='wings.phylodynamic-comparison.v1', analyses=records,
                 primary_analyses=summary['primary_analyses'], locations=labels)
    body = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WINGS · Reference sampling comparison</title><link rel="stylesheet" href="comparison_assets/phylogeography-movie.css"><link rel="stylesheet" href="comparison_assets/phylodynamic-comparison.css"></head>
<body><main id="comparison"><header><p class="eyebrow">WINGS / PHYLOGEOGRAPHY</p><h1>Reference sampling comparison</h1><p>One study cohort. Separate reconstructions for each reference sample.</p></header>
<div class="toolbar"><label>Segment<select id="segment"></select></label><label>Entries into<select id="location"></select></label><a href="sensitivity.html">Full results table</a></div>
<p class="scope">Entries along the WINGS samples’ ancestry, starting at their common ancestor. The ancestral stem is excluded. Intervals condition on each dated tree; replicates are not pooled.</p>
<section aria-label="Replicate comparison"><div class="scroll"><table id="replicates"><thead><tr><th>Reference replicate</th><th>Entries · mean (95%)</th><th>P(0 entries)</th><th>Raw ML R²</th><th>Status</th></tr></thead><tbody></tbody></table></div><div id="intervals"></div></section>
<section id="selected"><h2 id="selection-title"></h2><p id="load-status" role="status"></p><div id="dates" class="cards"></div>
<div id="bayesian"></div><div id="movie"></div><details id="clock-details" open><summary>Clock diagnostics</summary><div id="clock-stats" class="cards"></div><p class="scope">A clock-screen pass does not validate the root date. These fits use different rooting and dating steps; neither includes tree uncertainty.</p><div id="clock-plots" class="plots"></div></details><p id="downloads"></p></section>
</main><script id="comparison-data" type="application/json">'''+script_json(model)+'''</script>
<script src="comparison_assets/map-boundaries.js"></script><script src="comparison_assets/phylogeography-movie.js"></script><script src="comparison_assets/phylodynamic-comparison.js"></script></body></html>'''
    (output/'comparison.html').write_text(body)
    return model


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary',type=Path,required=True)
    p.add_argument('--output',type=Path)
    p.add_argument('--dating-run',default='initial')
    a=p.parse_args()
    out=a.output or a.summary.parent
    write_comparison(json.loads(a.summary.read_text()), out, a.summary.parent/'inference',a.dating_run)
    print('Open '+str(out/'comparison.html'))

if __name__=='__main__': main()
