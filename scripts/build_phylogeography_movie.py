#!/usr/bin/env python3
"""Package fixed-tree geographic histories for the WINGS movie; no inference is performed.

python scripts/build_phylogeography_movie.py --nodes nodes.tsv --histories histories.tsv \
  --jumps jumps.tsv --locations locations.tsv --method 'BEAST fixed-tree DTA' \
  --inference bayesian --output reconstruction.json
"""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile


def rows(path, required):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f'{path}: required columns: {", ".join(sorted(required))}')
        result = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in result):
            raise ValueError(f'{path}: malformed TSV row')
        return result


def build(args):
    segments = {}
    for row in rows(args.nodes, {'segment', 'id', 'parent', 'date'}):
        segment = segments.setdefault(row['segment'], {'id': row['segment'], 'nodes': [], 'histories': []})
        node = {k: row[k] for k in ('id', 'parent', 'date')}
        node['parent'] = node['parent'] or None
        for key in ('label', 'sample_id', 'observed_state'):
            if row.get(key): node[key] = row[key]
        segment['nodes'].append(node)
    histories = {}
    for row in rows(args.histories, {'segment', 'history', 'root_state'}):
        key = row['segment'], row['history']
        if key in histories: raise ValueError(f'Duplicate history: {key}')
        if row['segment'] not in segments: raise ValueError(f'Unknown segment: {row["segment"]}')
        history = {'id': row['history'], 'root_state': row['root_state'], 'jumps': []}
        histories[key] = history
        segments[row['segment']]['histories'].append(history)
    for row in rows(args.jumps, {'segment', 'history', 'branch', 'date', 'from', 'to'}):
        key = row['segment'], row['history']
        if key not in histories: raise ValueError(f'Jump references an undeclared history: {key}')
        histories[key]['jumps'].append({k: row[k] for k in ('branch', 'date', 'from', 'to')})
    locations = []
    for row in rows(args.locations, {'id', 'label', 'lat', 'lon'}):
        locations.append({'id': row['id'], 'label': row['label'], 'lat': float(row['lat']), 'lon': float(row['lon'])})
    return {'schema': 'wings.phylogeography-movie.v1', 'title': args.title, 'synthetic': False,
            'provenance': {'method': args.method, 'inference': args.inference,
                           'uncertainty': 'conditional-on-fixed-tree'},
            'locations': locations, 'segments': list(segments.values())}


def validate(data, *, for_analysis=False):
    module = Path(__file__).resolve().parent / 'report/phylogeography-movie.js'
    # Analysis keeps every draw and event. Browser import retains its resource
    # limits; it must not dictate whether a scientific reconstruction is valid.
    validator = 'validateForAnalysis' if for_analysis else 'validate'
    subprocess.run(['node', '-e', 'const m=require(process.argv[1]);let s="";process.stdin.on("data",x=>s+=x);process.stdin.on("end",()=>{const raw=JSON.parse(s);s="";m[process.argv[2]](raw);console.log("Validated reconstruction.");});', str(module), validator],
                   input=json.dumps(data, allow_nan=False), text=True, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('nodes', 'histories', 'jumps', 'locations'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--method', required=True)
    parser.add_argument('--inference', choices=['bayesian', 'empirical-bayes'], required=True)
    parser.add_argument('--title', default='Phylogeographic reconstruction')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists(): parser.error('Output exists; choose a new output path.')
    data = build(args)
    validate(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    try:
        # Exclusive create avoids replacing a file created during validation.
        with args.output.open('x', encoding='utf-8') as output:
            output.write(temporary.read_text(encoding='utf-8'))
    finally:
        temporary.unlink(missing_ok=True)
    print('Saved '+str(args.output))


if __name__ == '__main__':
    main()
