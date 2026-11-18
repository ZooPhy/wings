#!/usr/bin/env python3
"""Auditable reference subsets for conditional geographic trait inference."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
import hashlib
import heapq
import json
import math
from pathlib import Path
import random
import re
import statistics

from select_contextual_references import (SEGMENTS, iter_fasta, read_tsv, write_tsv,
    load_wings_targets, normalize_country)
from build_contextual_phylogeny_inputs import coverage_row, read_fasta_by_token

DEFAULTS = dict(enabled=False, segments=['HA'], strategies=['balanced', 'available'],
    replicates=3, seed=1729, max_references=180, max_per_location=40,
    lookback_days=730, lookahead_days=90, countries=[],
    min_callable=0.95, min_length_fraction=0.8, max_length_fraction=1.2,
    min_tips=8, min_locations=2, min_date_span_days=90, min_clock_r2=0.1,
    histories=600, rate_prior_shape=1.0, rate_prior_rate=1.0, threads=4,
    requested_locations=[], stratify_host=False, time_bin='month', references={}, lineage={}, temporal={})


def configuration(raw):
    if not isinstance(raw, dict):
        raise ValueError('phylodynamics must be a mapping')
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ValueError('Unknown phylodynamics options: ' + ', '.join(sorted(unknown)))
    cfg = dict(DEFAULTS, **raw)
    from phylodynamic_references import reference_configuration
    cfg['references'] = reference_configuration(cfg['references'])
    from phylodynamic_lineages import configuration as lineage_configuration
    from phylodynamic_temporal import configuration as temporal_configuration
    cfg['lineage'] = lineage_configuration(cfg['lineage'])
    cfg['temporal'] = temporal_configuration(cfg['temporal'])
    if cfg['time_bin'] not in ('month', 'quarter', 'year'):
        raise ValueError('time_bin must be month, quarter, or year')
    for key in ('min_callable','min_clock_r2','min_length_fraction','max_length_fraction','rate_prior_shape','rate_prior_rate'):
        if isinstance(cfg[key],bool) or not isinstance(cfg[key],(int,float)) or not math.isfinite(cfg[key]):
            raise ValueError(key + ' must be a finite number')
    for key in ('segments', 'strategies', 'countries', 'requested_locations'):
        if not isinstance(cfg[key], list) or len(set(cfg[key])) != len(cfg[key]):
            raise ValueError(key + ' must be a list without duplicates')
    if not cfg['segments'] or set(cfg['segments']) - set(SEGMENTS):
        raise ValueError('Invalid influenza segments')
    if not cfg['strategies'] or set(cfg['strategies']) - {'balanced', 'available', 'diversity'}:
        raise ValueError('Strategies must be balanced, available, or diversity')
    for key in ('replicates', 'max_references', 'max_per_location', 'min_tips',
                'min_locations', 'histories', 'threads'):
        if isinstance(cfg[key], bool) or not isinstance(cfg[key], int) or cfg[key] < 1:
            raise ValueError(key + ' must be a positive integer')
    if cfg['min_locations'] < 2 or cfg['min_tips'] < 3:
        raise ValueError('Inference needs at least two locations and three tips')
    if cfg['max_references'] > 450 or cfg['histories'] > 2000 or cfg['replicates'] > 20:
        raise ValueError('Limits: 450 references, 2000 histories, 20 replicates')
    for key in ('lookback_days', 'lookahead_days', 'min_date_span_days'):
        if not isinstance(cfg[key], int) or cfg[key] < 0:
            raise ValueError(key + ' must be a nonnegative integer')
    for key in ('min_callable', 'min_clock_r2'):
        if not 0 < float(cfg[key]) <= 1:
            raise ValueError(key + ' must be in (0,1]')
    if not (0 < cfg['min_length_fraction'] <= 1 <= cfg['max_length_fraction']):
        raise ValueError('Invalid sequence length fractions')
    if min(cfg['rate_prior_shape'], cfg['rate_prior_rate']) <= 0:
        raise ValueError('Gamma prior shape and rate must be positive')
    if not isinstance(cfg['seed'], int):
        raise ValueError('seed must be an integer')
    if not all(isinstance(cfg[k], bool) for k in ('enabled', 'stratify_host')):
        raise ValueError('enabled and stratify_host must be booleans')
    cfg['countries'] = [country(x) for x in cfg['countries']]
    if set(cfg['countries']) - set(country_catalog()):
        raise ValueError('Country scope contains an unsupported country; use a bundled country name or code')
    return cfg


@lru_cache(maxsize=1)
def boundary_data():
    text = (Path(__file__).parent / 'report/map-boundaries.js').read_text()
    return json.JSONDecoder().raw_decode(text.split('globalThis.WINGS_MAP_BOUNDARIES = ', 1)[1])[0]


@lru_cache(maxsize=1)
def country_catalog():
    return dict({r['country']: r for r in boundary_data()['countries']},
                USA={'name':'United States'}, CAN={'name':'Canada'})


def country(value):
    value = normalize_country(value).upper()
    special = {'CANADA':'CAN', 'MEXICO':'MEX', 'UNITED KINGDOM':'GBR',
               'RUSSIA':'RUS', 'SOUTH KOREA':'KOR', 'SOUTH GEORGIA AND THE SOUTH SANDWICH ISLANDS':'SGS'}
    if value in special:
        return special[value]
    for code, row in country_catalog().items():
        if value in (code, row['name'].upper()):
            return code
    return value


def exact_date(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value)):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def geography():
    data = boundary_data()
    aliases, locations = {}, {}
    for row in data['regions']:
        if not row.get('code'):
            continue
        key = row['country'] + ':' + row['code']
        locations[key] = dict(id=key, label=row['name'], lon=row['label'][0], lat=row['label'][1])
        for value in (row['name'], row['code']):
            aliases[(row['country'], value.casefold())] = key
    # States/provinces where bundled; other countries are explicitly country-level.
    regional = {r['country'] for r in data['regions']}
    for row in data['countries']:
        if row['country'] in regional:
            continue
        key = row['country'] + ':' + row['country']
        locations[key] = dict(id=key, label=row['name']+' (country)', lon=row['label'][0], lat=row['label'][1])
        aliases[(row['country'], '*')] = key
    return aliases, locations


def prepare_row(row, seq, origin, identifier, aliases, cfg, typical_length):
    out = dict(id=identifier, source=origin, accession=row.get('accession', ''),
               sample_id=row.get('sample_id', ''), date=row.get('collection_date', ''),
               host=row.get('host', '') or 'Unknown', country=country(row.get('country', '')),
               state=row.get('state', ''), specimen_id=row.get('specimen_id',''), sequence=seq.upper().replace('U', 'T'),
               segment_type=row.get('segment_type', ''), genotype=row.get('genotype', ''))
    out['location'] = aliases.get((out['country'], out['state'].strip().casefold()), aliases.get((out['country'], '*'), ''))
    out['month'] = out['date'][:7]
    out['sequence_sha256'] = hashlib.sha256(out['sequence'].encode()).hexdigest()
    reasons = []
    if exact_date(out['date']) is None:
        reasons.append('missing_or_partial_date')
    if cfg['countries'] and out['country'] not in cfg['countries']:
        reasons.append('outside_country_scope')
    if not out['location']:
        reasons.append('unresolved_state_or_province')
    if not seq:
        reasons.append('missing_sequence')
    elif set(out['sequence']) - set('ACGTRYSWKMBDHVN'):
        reasons.append('unsupported_or_gapped_sequence')
    else:
        if sum(c in 'ACGT' for c in out['sequence']) / len(seq) < cfg['min_callable']:
            reasons.append('low_callable_fraction')
        if not cfg['min_length_fraction'] * typical_length <= len(seq) <= cfg['max_length_fraction'] * typical_length:
            reasons.append('sequence_length')
    out['reasons'] = reasons
    return out


def kmers(seq, k=9):
    # Bounded bottom-hash sketch: reproducible, strand-aware and memory bounded.
    trans=str.maketrans('ACGT','TGCA')
    words={min(seq[i:i+k],seq[i:i+k].translate(trans)[::-1])
           for i in range(len(seq)-k+1) if set(seq[i:i+k]) <= set('ACGT')}
    return set(heapq.nsmallest(64,(int.from_bytes(hashlib.blake2b(w.encode(),digest_size=8).digest(),'big') for w in words)))


def time_stratum(row, width):
    month = row.get('month') or row['date'][:7]
    return month if width == 'month' else month[:4] if width == 'year' else month[:4]+'-Q'+str((int(month[5:7])-1)//3+1)


def composition(rows):
    return {key: dict(sorted(Counter(r.get(key, '') for r in rows).items()))
            for key in ('location', 'month', 'host')}


def select(candidates, study, cfg, strategy, seed, anchors=()):
    """Reserve within-clade nearest relatives, then sample remaining context."""
    rng = random.Random(seed)
    pool = sorted(candidates, key=lambda r: r['id'])
    rng.shuffle(pool)
    anchor_set=set(anchors)
    if not anchor_set <= {r['id'] for r in pool}:raise ValueError('Unknown nearest-reference anchor')
    fixed=[r for r in pool if r['id'] in anchor_set]
    if len(fixed)>cfg['max_references']:raise ValueError('Nearest references exceed reference budget')
    pool=[r for r in pool if r['id'] not in anchor_set]
    if strategy == 'available':
        # Explicit comparator: represents the eligible repository pool only.
        return sorted(fixed+pool[:cfg['max_references']-len(fixed)],key=lambda r:r['id'])
    location_counts = Counter(r['location'] for r in study+fixed)
    def stratum(r):
        return (r['location'], time_stratum(r, cfg['time_bin']), r['host'].casefold() if cfg['stratify_host'] else '')
    strata_counts = Counter(stratum(r) for r in study+fixed)
    ref_counts, selected = Counter(r['location'] for r in fixed), list(fixed)
    if max(ref_counts.values(),default=0)>cfg['max_per_location']:
        raise ValueError('Nearest references exceed per-location cap')
    sketches = {r['id']: (r['_diversity_sketch'] if '_diversity_sketch' in r else kmers(r['sequence'])) for r in pool + study + fixed} if strategy == 'diversity' else {}
    # Incremental minimum Jaccard distance; bounded k-mer screening, not a tree distance.
    distance = {r['id']: 1.0 for r in pool}
    def update_distance(chosen):
        sketch = sketches[chosen['id']]
        for r in pool:
            other = sketches[r['id']]
            union = len(sketch | other)
            d = 1 - len(sketch & other) / union if union else 0
            distance[r['id']] = min(distance[r['id']], d)
    if strategy == 'diversity':
        for r in study+fixed:
            update_distance(r)
    while pool and len(selected) < cfg['max_references']:
        eligible = [r for r in pool if ref_counts[r['location']] < cfg['max_per_location']]
        if not eligible:
            break
        loc_min = min(location_counts[r['location']] for r in eligible)
        eligible = [r for r in eligible if location_counts[r['location']] == loc_min]
        str_min = min(strata_counts[stratum(r)] for r in eligible)
        eligible = [r for r in eligible if strata_counts[stratum(r)] == str_min]
        chosen = max(eligible, key=lambda r: distance[r['id']]) if strategy == 'diversity' else eligible[0]
        pool.remove(chosen)
        selected.append(chosen)
        location_counts[chosen['location']] += 1
        strata_counts[stratum(chosen)] += 1
        ref_counts[chosen['location']] += 1
        if strategy == 'diversity':
            update_distance(chosen)
    return sorted(selected, key=lambda r: r['id'])


FIELDS = ['id', 'source', 'accession', 'sample_id', 'date', 'host', 'country', 'state',
          'location', 'month', 'specimen_id', 'segment_type', 'genotype', 'sequence_sha256', 'reason']


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n')


def build(results, metadata, public_table, fasta, output, cfg, samples=None):
    cfg = configuration(cfg)
    aliases, locations = geography()
    provenance_path=public_table.parent/'provenance.json'
    reference_provenance=json.loads(provenance_path.read_text()) if provenance_path.is_file() else None
    if reference_provenance:
        for name,path in [('references.tsv',public_table),('references.fasta',fasta)]:
            if reference_provenance['files_sha256'].get(name)!=digest(path):
                raise ValueError('Reference snapshot changed after preparation: '+name)
    invalid = set(cfg['requested_locations']) - set(locations)
    if invalid:
        raise ValueError('Unknown requested location IDs: ' + ', '.join(sorted(invalid)))
    public = read_tsv(public_table)
    normalized = not public or 'segment' in public[0]
    targets = [] if normalized else load_wings_targets(results, metadata)[0]
    metadata_rows = read_tsv(metadata)
    meta = {r.get('sample_id') or r.get('sample'): r for r in metadata_rows}
    if len(meta) != len(metadata_rows) or None in meta or '' in meta:
        raise ValueError('Missing or duplicate study metadata IDs')
    if samples is None:
        samples = sorted(meta)
    wanted = set(samples)
    if not wanted <= set(meta):
        raise ValueError('Study sample missing from metadata')
    targets = {r['sample_id']: r for r in targets if r['sample_id'] in wanted}
    accessions = ({r.get('accession') for r in public} if normalized else {r.get(s + '_accession') for r in public for s in cfg['segments']}) - {None, ''}
    sequences = {}
    for header, seq in iter_fasta(fasta):
        acc = header.split()[0]
        if acc in accessions:
            if acc in sequences:
                raise ValueError('Duplicate public FASTA accession: ' + acc)
            sequences[acc] = seq
    source_hashes = dict(public_table=digest(public_table), public_fasta=digest(fasta), metadata=digest(metadata),
                         geography=digest(Path(__file__).parent / 'report/map-boundaries.js'))
    for sid in sorted(wanted):
        for relative in ('coverage/coverage.tsv', 'merged/consensus_all_segments.fasta', 'genoflu/GenoFLU.tsv'):
            p = results / sid / relative
            if p.is_file():
                source_hashes[sid + '/' + relative] = digest(p)
    summary = dict(schema='wings.phylodynamic-selection.v1', config=cfg, input_sha256=source_hashes,
                   warning='Balances available references; does not correct unobserved surveillance or population sampling.',
                   reference_provenance=reference_provenance, segments={}, replicates=[])
    for segment in cfg['segments']:
        study_raw, excluded = [], []
        for sid in sorted(wanted):
            target = targets.get(sid)
            qc = coverage_row(results / sid / 'coverage/coverage.tsv', segment)
            reason = ('missing_segment_type' if not normalized and (not target or not target['segment_calls'].get(segment))
                      else 'study_qc' if not qc or qc.get('overall_status') != 'PASS' else '')
            if reason:
                excluded.append(dict(id=sid, source='study', reason=reason))
                continue
            seqs = read_fasta_by_token(results / sid / 'merged/consensus_all_segments.fasta')
            seq = seqs.get(qc.get('contig'), '')
            study_raw.append((dict(meta[sid], sample_id=sid, segment_type='source-annotation' if normalized else target['segment_calls'][segment]), seq))
        typical = statistics.median([len(seq) for _, seq in study_raw if seq]) if any(s for _, s in study_raw) else 1
        study = []
        for row, seq in study_raw:
            r = prepare_row(row, seq, 'study', 'study_' + hashlib.sha256(row['sample_id'].encode()).hexdigest()[:20], aliases, cfg, typical)
            if r['reasons']:
                excluded.append(dict(r, reason=';'.join(r['reasons'])))
            else:
                study.append(r)
        types = {r['segment_type'] for r in study}
        start = min((exact_date(r['date']) for r in study), default=date(2000, 1, 1)) - timedelta(days=cfg['lookback_days'])
        end = max((exact_date(r['date']) for r in study), default=date(2000, 1, 1)) + timedelta(days=cfg['lookahead_days'])
        candidates, seen_accessions = [], set()
        # Sequence identity alone is NOT evidence of a duplicate animal/specimen.
        redundancy = {(r['specimen_id'], r['sequence_sha256'], r['date'], r['location'], r['host'].casefold()) for r in study if r['specimen_id']}
        records = [dict(r, **{segment+'_accession':r['accession'], segment+'_type':'source-annotation', 'run_status':'OK'})
                   for r in public if r.get('segment') == segment] if normalized else public
        accession_metadata = defaultdict(set)
        for row in records:
            accession_metadata[row.get(segment+'_accession','')].add(tuple(row.get(k,'') for k in ('collection_date','country','state','host',segment+'_type')))
        for row in sorted(records, key=lambda r: (r.get(segment+'_accession', ''), json.dumps(r, sort_keys=True))):
            acc = row.get(segment + '_accession', '')
            r = prepare_row(dict(row, accession=acc, segment_type=row.get(segment+'_type', '')),
                            sequences.get(acc, ''), 'reference', 'ref_' + hashlib.sha256(acc.encode()).hexdigest()[:20], aliases, cfg, typical)
            if len(accession_metadata[acc]) > 1:
                r['reasons'].append('conflicting_accession_metadata')
            if row.get('run_status') != 'OK':
                r['reasons'].append('genotyping_failed')
            if r['segment_type'] not in types:
                r['reasons'].append('different_or_missing_segment_type')
            when = exact_date(r['date'])
            if when and not start <= when <= end:
                r['reasons'].append('outside_time_window')
            if not acc:
                r['reasons'].append('missing_accession')
            elif acc in seen_accessions:
                r['reasons'].append('duplicate_accession')
            if r['reasons']:
                excluded.append(dict(r, reason=';'.join(r['reasons'])))
                continue
            seen_accessions.add(acc)
            key = (r['specimen_id'], r['sequence_sha256'], r['date'], r['location'], r['host'].casefold())
            if r['specimen_id'] and key in redundancy:
                excluded.append(dict(r, reason='duplicate_specimen_sequence'))
                continue
            if r['specimen_id']:
                redundancy.add(key)
            candidates.append(r)
        segment_dir = output / segment
        from phylodynamic_lineages import screen
        candidates, clade_excluded, lineage = screen(study,candidates,segment,segment_dir/'lineage',
            cfg['lineage'],cfg['threads'],cfg['references']['offline'])
        excluded.extend(clade_excluded)
        anchor_ids=lineage['anchor_ids']
        lineage_record={k:lineage.get(k) for k in ('status','reasons','target_clade','study_clades','anchor_ids')}
        lineage_record['audit_sha256']=digest(segment_dir/'lineage/lineage.json')
        write_tsv(segment_dir / 'excluded.tsv', FIELDS, excluded)
        write_tsv(segment_dir / 'eligible.tsv', FIELDS, study + candidates)
        coverage = Counter((r['location'], r['month'], r['source']) for r in study+candidates)
        write_tsv(segment_dir / 'coverage.tsv', ['location', 'month', 'source', 'count'],
                  [dict(location=k[0], month=k[1], source=k[2], count=v) for k,v in sorted(coverage.items())])
        missing = sorted(set(cfg['requested_locations']) - {r['location'] for r in study+candidates})
        summary['segments'][segment] = dict(study=len(study), eligible_references=len(candidates),
            lineage=lineage_record, composition=composition(study+candidates), study_composition=composition(study),
            segment_types=sorted(types), window=[start.isoformat(),end.isoformat()],
            missing_requested_locations=missing,
            exclusions=dict(Counter(reason for r in excluded for reason in r['reason'].split(';'))))
        if 'diversity' in cfg['strategies']:
            for r in study+candidates:r['_diversity_sketch']=kmers(r['sequence'])
        for strategy in cfg['strategies']:
            for rep in range(1, cfg['replicates']+1):
                seed = int.from_bytes(hashlib.sha256(f"{cfg['seed']}:{segment}:{strategy}:{rep}".encode()).digest()[:4], 'big')
                selection_reasons=list(lineage['reasons'])
                if len(anchor_ids)>cfg['max_references']:
                    selection_reasons.append('nearest_references_exceed_budget')
                anchor_counts=Counter(r['location'] for r in candidates if r['id'] in anchor_ids)
                if strategy!='available' and max(anchor_counts.values(),default=0)>cfg['max_per_location']:
                    selection_reasons.append('nearest_references_exceed_location_cap')
                chosen = select(candidates,study,cfg,strategy,seed,anchor_ids) if not selection_reasons else []
                rows = study + chosen
                group = f'{segment}/{strategy}/replicate_{rep}'
                dest = output / group
                dest.mkdir(parents=True, exist_ok=True)
                (dest / 'input.fasta').write_text(''.join(f">{r['id']}\n{r['sequence']}\n" for r in rows))
                write_tsv(dest / 'tips.tsv', FIELDS, rows)
                write_tsv(dest / 'reference_decisions.tsv', ['accession', 'selected', 'reason'],
                    [dict(accession=r['accession'], selected=r in chosen, reason=('nearest_relative' if r['id'] in anchor_ids else 'sampled_context') if r in chosen else 'sampling_quota') for r in candidates])
                reasons = list(selection_reasons)
                if not study:
                    reasons.append('no_eligible_study_samples')
                if not candidates:
                    reasons.append('no_eligible_references')
                if len(rows) < cfg['min_tips']:
                    reasons.append('insufficient_tips')
                if len({r['location'] for r in rows}) < cfg['min_locations']:
                    reasons.append('insufficient_locations')
                dates = [exact_date(r['date']) for r in rows]
                if len(set(dates)) < 3 or (dates and (max(dates)-min(dates)).days < cfg['min_date_span_days']):
                    reasons.append('insufficient_collection_date_span')
                if missing:
                    reasons.append('missing_requested_locations')
                study_counts=Counter(r['location'] for r in study)
                available_counts=Counter(r['location'] for r in candidates)
                target=max(study_counts.values(),default=0)
                unfillable=sorted(loc for loc in set(study_counts)|set(available_counts)
                    if study_counts[loc]+min(available_counts[loc],cfg['max_per_location']) < target)
                record = dict(id=group, segment=segment, strategy=strategy, replicate=rep, seed=seed,
                              study=len(study), references=len(chosen), status='blocked' if reasons else 'ready', reasons=reasons,
                              locations=dict(Counter(r['location'] for r in rows)),
                              composition=composition(rows), study_composition=composition(study),
                              reference_composition=composition(chosen),
                              coverage_gaps=sorted({r['location'] for r in study+candidates}-{r['location'] for r in rows}),
                              locations_unable_to_match_largest_study_group=unfillable,
                              quota_status='Engineering limits; no empirically validated bias-reduction claim',
                              lineage=lineage_record, eligible_references=len(candidates), selected_sha256=digest(dest/'input.fasta'))
                if len(record['locations']) > 100:
                    record['status']='blocked'; record['reasons'].append('more_than_100_locations')
                if len(rows) * cfg['histories'] * 2 > 1000000:
                    record['status'] = 'blocked'; record['reasons'].append('movie_size_limit')
                write_json(dest / 'selection.json', dict(record, config=cfg, location_metadata=[locations[k] for k in sorted({r['location'] for r in rows})]))
                summary['replicates'].append(record)
    write_json(output / 'selection_summary.json', summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('results', 'metadata', 'public-table', 'fasta', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--config',type=Path)
    group.add_argument('--settings-json')
    p.add_argument('--samples-json')
    p.add_argument('--threads',type=int)
    a = p.parse_args()
    if a.settings_json:cfg=json.loads(a.settings_json)
    else:
        import yaml
        cfg=yaml.safe_load(a.config.read_text())
        cfg=cfg.get('phylodynamics',cfg)
    if a.threads:cfg['threads']=a.threads
    build(a.results,a.metadata,a.public_table,a.fasta,a.output,cfg,
          samples=json.loads(a.samples_json) if a.samples_json else None)

if __name__ == '__main__':
    main()
