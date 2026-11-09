#!/usr/bin/env python3
"""Select one reproducible reference per protein for all saved cohort samples."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

spec=importlib.util.spec_from_file_location('cohort_aa',Path(__file__).with_name('wings_amino_acids.py'))
aa=importlib.util.module_from_spec(spec);spec.loader.exec_module(aa)
ELIGIBLE={'READY','PARTIAL_INTERPRETATION','AMBIGUOUS_ALIGNMENT','AMBIGUOUS_REFERENCE','DISTANT_REFERENCE','NO_REFERENCE_FOR_PROTEIN'}


def thresholds(sample):
    p=sample.get('provenance',{});values=p.get('min_identity'),p.get('min_coverage')
    if any(not isinstance(v,(float,int)) or not 0<=v<=1 for v in values):raise ValueError(sample['sample']+': invalid recorded comparison thresholds')
    return values


def choose_panel(samples):
    refs={};keys=set()
    for sample in samples:
        panel=aa.panel_check(sample.get('provenance',{}).get('panel',{}))
        for ref in panel['references']:
            if ref['id'] in refs and any(ref.get(k)!=refs[ref['id']].get(k) for k in ['sequence','gene','segment','protein_id','accession']):
                raise ValueError('Conflicting reference metadata for '+ref['id'])
            refs.setdefault(ref['id'],ref)
        for p in sample.get('proteins',[]):
            if p.get('status') in ELIGIBLE:
                if not p.get('query_sequence'):raise ValueError(sample['sample']+': missing saved translated sequence')
                keys.add((p['gene'],p['segment']))
    chosen=[];selection=[]
    for gene,segment in sorted(keys):
        candidates=sorted((r for r in refs.values() if r['gene']==gene and r['segment']==segment),key=lambda r:r['id'])
        if not candidates:continue
        # Identical candidate sequences need scoring only once; accession choice is deterministic.
        distinct={}
        for r in candidates:distinct.setdefault(r['sequence'],r)
        print('Selecting shared '+gene+' reference from '+str(len(distinct))+' distinct candidate proteins',flush=True)
        ranked=[]
        for ref in distinct.values():
            passing=0;score=identity=coverage=0.;comparisons={};sample_count=0
            for sample in samples:
                queries={p['query_sequence'] for p in sample.get('proteins',[]) if p.get('status') in ELIGIBLE and p['gene']==gene and p['segment']==segment}
                if not queries:continue
                sample_count+=1;mi,mc=thresholds(sample);values=[]
                for query in sorted(queries):
                    if query not in comparisons:
                        c=aa.compare(ref['sequence'],query)
                        comparisons[query]=(c['score']/(2*max(len(ref['sequence']),len(query))),c['identity'],c['coverage'],bool(c['alignment_resolution']['callable_reference_positions']))
                    values.append(comparisons[query])
                passing+=all(v[1]>=mi and v[2]>=mc and v[3] for v in values)
                score+=sum(v[0] for v in values)/len(values);identity+=sum(v[1] for v in values)/len(values);coverage+=sum(v[2] for v in values)/len(values)
            rank=(passing,round(score,12),round(identity,12),round(coverage,12))
            ranked.append((rank,ref,sample_count))
        ranked.sort(key=lambda item:(tuple(-v for v in item[0]),item[1]['id']))
        best,ref,n=ranked[0];ties=[r['id'] for rank,r,_ in ranked if rank==best]
        chosen.append(copy.deepcopy(ref));selection.append({'gene':gene,'segment':segment,'reference_id':ref['id'],'eligible_samples':n,
            'samples_meeting_existing_thresholds':best[0],'summed_normalized_score':best[1],
            'tied_best_distinct_reference_ids':ties,'tie_break':'lexicographic versioned reference ID',
            'equivalent_reference_ids':[r['id'] for r in candidates if r['sequence']==ref['sequence']]})
    if not chosen:raise ValueError('No reference candidates for the recorded cohort proteins')
    panel={'schema_version':1,'panel_name':'shared-cohort-protein-references','references':chosen,
           'selection_method':'maximize samples meeting recorded thresholds, then summed length-normalized alignment score, identity, coverage; stable ID tie-break',
           'cohort_samples':[s['sample'] for s in samples],'selection':selection}
    aa.panel_check(panel);return panel


def run(inputs,output_dir,evidence_path):
    inputs=[p.expanduser().resolve() for p in inputs];output_dir=output_dir.expanduser().resolve()
    samples=[];names=set()
    for path in inputs:
        data=json.loads(path.read_text());name=data['sample']
        if not name or name in {'.','..'} or Path(name).name!=name or name in names:raise ValueError('Unsafe or duplicate sample ID: '+name)
        names.add(name);thresholds(data)
        if (output_dir/name/'changes.json').resolve() in inputs:raise ValueError('Choose a new output directory; source JSONs must be preserved')
        samples.append(data)
    if not samples:raise ValueError('No saved samples supplied')
    evidence_hash=aa.sha(evidence_path)
    if any(s.get('provenance',{}).get('evidence_sha256')!=evidence_hash for s in samples):raise ValueError('Evidence file does not match the recorded version; supply the original with --evidence')
    panel=choose_panel(samples);evidence=aa.evidence_check(json.loads(evidence_path.read_text()),panel)
    panel_hash=hashlib.sha256((json.dumps(panel,indent=2,sort_keys=True)+'\n').encode()).hexdigest();pending=[]
    cohort_sources={sample['sample']:aa.sha(path) for path,sample in zip(inputs,samples)}
    for source,data in zip(inputs,samples):
        result=copy.deepcopy(data);mi,mc=thresholds(data)
        for p in result.get('proteins',[]):
            if p.get('status') in ELIGIBLE:aa.assess_protein(p,panel,evidence,mi,mc)
        provenance=result['provenance'];provenance['previous_reference_panel']=provenance.get('panel')
        provenance['previous_panel_sha256']=provenance.get('panel_sha256');provenance['panel']=panel;provenance['panel_sha256']=panel_hash
        provenance['cohort_reference_assignment']={'source_json_sha256':aa.sha(source),'all_source_json_sha256':cohort_sources,
            'assignment_script_sha256':aa.sha(__file__),'selected_reference_panel_sha256':panel_hash}
        provenance['script_sha256']=aa.sha(Path(aa.__file__));provenance['panel_path']='reference_panel.json'
        result['status']='REVIEW' if result.get('unannotated_sequences') or any(p['status']!='READY' for p in result.get('proteins',[])) else 'READY'
        pending.append((output_dir/result['sample']/'changes.json',result))
    # No result writes occur until the whole cohort has been validated and recalculated.
    for path,result in pending:aa.write_json(path.parent/'reference_panel.json',panel);aa.write_json(path,result)
    aa.write_json(output_dir/'cohort_reference_panel.json',panel)
    print('Wrote '+str(len(pending))+' samples using shared protein references to '+str(output_dir))
    print('Source results preserved. No BLAST search, NCBI download, or upstream workflow jobs were run.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--inputs',nargs='+',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path);parser.add_argument('--evidence',type=Path,default=Path('resources/amino_acids/evidence.json'))
    args=parser.parse_args();run(args.inputs,args.output_dir,args.evidence)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as error:raise SystemExit('ERROR: '+str(error))
