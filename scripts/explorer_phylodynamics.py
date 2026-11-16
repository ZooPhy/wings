"""Attach checked viewer data to the matching surveillance cohort."""
import json
from pathlib import Path


def attach_results(payload, path):
    model = json.loads(Path(path).read_text(encoding='utf-8'))
    if model.get('schema') != 'wings.phylogeography-results.v1' or model.get('demo'):
        raise ValueError('Expected real Phylodynamics results, not an illustrative demo')
    rows = model.get('analyses')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Phylodynamics results contain no analyses')
    ids = [row['id'] for row in rows]
    if len(ids) != len(set(ids)) or model.get('default_analysis') not in ids or model.get('default_method') not in ('fast', 'beast'):
        raise ValueError('Invalid Phylodynamics analysis selection')
    samples = {s['sample_id'] for s in payload['samples']}
    for row in rows:
        for method, data in row['methods'].items():
            if method not in ('fast', 'beast') or data.get('method') != method or data.get('status') != 'passed':
                raise ValueError('Phylodynamics method has not passed its checks')
            focal = data.get('focal_sample_ids', [])
            if not focal or len(focal) != len(set(focal)) or not set(focal).issubset(samples):
                raise ValueError('Phylodynamics results do not match the surveillance sample cohort')
    payload['phylodynamics_results'] = model
    return payload
