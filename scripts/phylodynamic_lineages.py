"""H5 HA clade eligibility, frozen Nextclade dataset, and within-clade anchors.

Clade assignment is independent of geographic labels, dates and clock fit.
This module never substitutes an arbitrary sequence-distance cutoff for a clade.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

DATASET = 'community/moncla-lab/iav-h5/ha/all-clades'
DEFAULTS = dict(dataset=DATASET, tag='', snapshot='initial',
                cache_dir='resources/phylodynamics/nextclade-cache', nearest_per_study=2)


def configuration(raw):
    if not isinstance(raw, dict) or set(raw)-set(DEFAULTS):
        raise ValueError('Invalid lineage options')
    cfg = dict(DEFAULTS, **raw)
    if cfg['dataset'] != DATASET:
        raise ValueError('This release supports only the reviewed H5 HA all-clades dataset')
    for k in ('tag','snapshot','cache_dir'):
        if not isinstance(cfg[k],str) or (k != 'tag' and not cfg[k].strip()):
            raise ValueError('lineage.'+k+' must be a string')
    if type(cfg['nearest_per_study']) is not int or not 1 <= cfg['nearest_per_study'] <= 5:
        raise ValueError('lineage.nearest_per_study must be 1–5')
    return cfg


def hashes(directory):
    return {str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob('*')) if p.is_file()}


def frozen_dataset(cfg, offline=False):
    """Resolve a concrete tag once; cache content immutably, verify on reuse."""
    identity = {k:cfg[k] for k in ('dataset','tag','snapshot')}
    key = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:24]
    cache = Path(cfg['cache_dir']).resolve()/key
    manifest = cache/'manifest.json'
    if manifest.exists():
        data=json.loads(manifest.read_text())
        if data['request'] != identity or hashes(cache/'dataset') != data['sha256']:
            raise ValueError('Nextclade cache changed; use a new lineage.snapshot to refresh')
        return cache/'dataset', data
    if cache.exists():
        raise ValueError('Incomplete Nextclade cache: '+str(cache))
    if offline:
        raise ValueError('Nextclade dataset is not cached; offline mode cannot download it')
    cache.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nextclade-',dir=cache.parent) as td:
        stage=Path(td); dataset=stage/'dataset'
        tag=cfg['tag']
        if not tag:
            records=json.loads(subprocess.check_output(
                ['nextclade','dataset','list','--name',cfg['dataset'],'--json'],text=True))
            records=[r for r in records if r.get('path') == cfg['dataset']]
            if len(records)!=1 or not records[0].get('version',{}).get('tag'):
                raise ValueError('Cannot resolve a unique Nextclade dataset version')
            tag=records[0]['version']['tag']
        command=['nextclade','dataset','get','--name',cfg['dataset'],'--tag',tag,'--output-dir',str(dataset)]
        subprocess.run(command,check=True)
        for name in ('reference.fasta','tree.json','pathogen.json'):
            if not (dataset/name).is_file():raise ValueError('Incomplete Nextclade dataset: '+name)
        data=dict(request=identity,resolved_tag=tag,sha256=hashes(dataset),download_command=command)
        (stage/'manifest.json').write_text(json.dumps(data,indent=2)+'\n')
        # Atomic publication; never merge partial downloads into a frozen dataset.
        stage.rename(cache)
    return cache/'dataset',data


def read_fasta(path):
    rows={}; name=None
    for line in Path(path).read_text().splitlines():
        if line.startswith('>'):
            name=line[1:].split()[0]
            if name in rows:raise ValueError('Duplicate alignment ID: '+name)
            rows[name]=''
        elif line.strip():
            if name is None:raise ValueError('Invalid FASTA')
            rows[name]+=line.strip().upper()
    return rows


def classify(study, candidates, assignments):
    """All eligible study samples must receive the same usable clade call."""
    wanted={r['id'] for r in study+candidates}
    if len(wanted)!=len(study)+len(candidates):raise ValueError('Duplicate sequence IDs')
    if set(assignments)!=wanted:raise ValueError('Nextclade output IDs do not match input IDs')
    reasons=[]; decisions=[]; clades=set()
    for row in study+candidates:
        a=assignments[row['id']]
        status=a.get('qc.overallStatus','')
        clade=a.get('clade','').strip()
        usable=bool(clade and clade.lower() not in ('unassigned','unknown','na','n/a')
                    and not a.get('errors','').strip() and status in ('good','mediocre'))
        decisions.append(dict(id=row['id'],source=row['source'],accession=row.get('accession',''),
            sample_id=row.get('sample_id',''),clade=clade,qc=status,usable=usable,
            warnings=a.get('warnings',''),errors=a.get('errors','')))
        if row['source']=='study':
            if usable:clades.add(clade)
            else:reasons.append('study_clade_unresolved_or_bad_qc')
    if not study:reasons.append('no_eligible_study_samples')
    elif len(clades)>1:reasons.append('multiple_study_clades_require_separate_analyses')
    target=next(iter(clades)) if len(clades)==1 and not reasons else None
    kept=[]; excluded=[]
    byid={r['id']:r for r in candidates}
    for d in decisions:
        d['decision']='study_retained' if d['source']=='study' else (
            'clade_scope_unresolved' if not target else 'nextclade_unusable' if not d['usable'] else
            'different_clade' if d['clade']!=target else 'eligible_same_clade')
        if d['source']=='reference':
            r=byid[d['id']]
            if d['decision']=='eligible_same_clade':kept.append(r)
            else:excluded.append(dict(r,reason=d['decision']))
    return kept,excluded,dict(status='blocked' if reasons else 'ready',reasons=sorted(set(reasons)),
        study_clades=sorted(clades),target_clade=target,decisions=decisions)


def nearest_anchors(study,candidates,aligned,per_study):
    """Reserve exact-distance nearest references in the eligible clade.

    No date, location, clock metric or outcome is used. No distance threshold.
    Shared A/C/G/T positions must cover >=80% of the study's callable positions.
    Nextclade strips insertions relative to its reference; this alignment is used
    for ranking only, never substituted for the original input sequences.
    """
    import numpy as np
    if not study or not candidates:return [],[]
    candidates=sorted(candidates,key=lambda r:r['id']); study=sorted(study,key=lambda r:r['id'])
    allids=[r['id'] for r in study+candidates]
    if not set(allids)<=set(aligned):raise ValueError('Missing usable Nextclade aligned sequence')
    if len({len(aligned[k]) for k in allids})!=1:raise ValueError('Nextclade alignment lengths differ')
    a=np.array([list(aligned[r['id']]) for r in candidates]);valid=np.isin(a,list('ACGT'))
    chosen=set();audit=[]
    for s in study:
        b=np.array(list(aligned[s['id']])); callable_b=np.isin(b,list('ACGT'))
        mask=valid & callable_b; overlap=mask.sum(axis=1)
        distances=np.divide(((a!=b)&mask).sum(axis=1),overlap,
                            out=np.full(len(a),np.inf),where=overlap>0)
        distances[overlap<.8*callable_b.sum()]=np.inf
        ranks=sorted(range(len(candidates)),key=lambda i:(distances[i],candidates[i]['id']))
        ranks=[i for i in ranks if np.isfinite(distances[i])][:per_study]
        if len(ranks)<min(per_study,len(candidates)):
            raise ValueError('Insufficient aligned overlap for nearest references: '+s['id'])
        for rank,i in enumerate(ranks,1):
            r=candidates[i];chosen.add(r['id'])
            audit.append(dict(study_id=s['id'],reference_id=r['id'],accession=r.get('accession',''),
                              rank=rank,distance=float(distances[i]),compared_sites=int(overlap[i])))
    return sorted(chosen),audit


def screen(study,candidates,segment,output,cfg,threads,offline=False):
    from phylodynamic_selection import write_json,write_tsv
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if segment!='HA':
        audit=dict(status='blocked',reasons=['lineage_screen_not_supported_for_segment'],target_clade=None,
                   study_clades=[],decisions=[],anchor_ids=[])
        write_json(output/'lineage.json',audit)
        return [],[dict(r,reason='lineage_screen_not_supported_for_segment') for r in candidates],audit
    if not study or not candidates:
        audit=dict(status='blocked',reasons=['lineage_screen_requires_study_and_references'],
                   target_clade=None,study_clades=[],decisions=[],anchor_ids=[])
        write_json(output/'lineage.json',audit);return candidates,[],audit
    dataset,provenance=frozen_dataset(cfg,offline)
    version=subprocess.check_output(['nextclade','--version'],text=True).strip()
    fasta=output/'classification_input.fasta'
    fasta.write_text(''.join('>'+r['id']+'\n'+r['sequence']+'\n' for r in study+candidates))
    table=output/'nextclade.tsv'; alignment=output/'nextclade.aligned.fasta'
    # Failed runs must never consume outputs left by a previous invocation.
    for p in (table,alignment):p.unlink(missing_ok=True)
    # Request rescue explicitly instead of depending on tool/dataset defaults.
    # Clade and QC eligibility still come from the resulting Nextclade calls.
    command=['nextclade','run','--input-dataset',str(dataset),'--jobs',str(threads),
             '--retry-reverse-complement','true',
             '--output-tsv',str(table),'--output-fasta',str(alignment),str(fasta)]
    with (output/'nextclade.log').open('w') as log:
        subprocess.run(command,stdout=log,stderr=log,check=True)
    with table.open() as f:
        rows=list(csv.DictReader(f,delimiter='\t'))
    assignments={r['seqName']:r for r in rows}
    if len(rows)!=len(assignments):raise ValueError('Duplicate Nextclade output IDs')
    kept,excluded,audit=classify(study,candidates,assignments)
    byid={r['id']:r for r in study+candidates}
    for decision in audit['decisions']:
        row=byid[decision['id']]
        orientation=assignments[row['id']].get('isReverseComplement','').lower()
        if decision['usable'] and orientation not in ('true','false'):
            raise ValueError('Missing or invalid Nextclade orientation: '+row['id'])
        decision['reverse_complemented']=orientation=='true'
        decision['original_sequence_sha256']=hashlib.sha256(row['sequence'].encode()).hexdigest()
        if orientation=='true' and decision['usable']:
            row['sequence']=row['sequence'].translate(str.maketrans('ACGTRYSWKMBDHVN','TGCAYRSWMKVHDBN'))[::-1]
            row['sequence_sha256']=hashlib.sha256(row['sequence'].encode()).hexdigest()
        decision['oriented_sequence_sha256']=hashlib.sha256(row['sequence'].encode()).hexdigest()
    anchors,neighbors=[],[]
    if audit['status']=='ready' and kept:
        anchors,neighbors=nearest_anchors(study,kept,read_fasta(alignment),cfg['nearest_per_study'])
    audit.update(dataset=provenance,software=version,command=command,anchor_ids=anchors,
        input_sha256=hashlib.sha256(fasta.read_bytes()).hexdigest(),output_sha256={
            p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (table,alignment)},
        interpretation='Dataset-defined HA clade eligibility; no fixed genetic-distance cutoff. Not a guarantee of clocklike evolution.')
    write_tsv(output/'clade_decisions.tsv',list(audit['decisions'][0]),audit['decisions'])
    write_tsv(output/'nearest_references.tsv',['study_id','reference_id','accession','rank','distance','compared_sites'],neighbors)
    write_json(output/'lineage.json',audit)
    return kept,excluded,audit
