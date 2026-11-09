"""Compare the optimal-DAG implementation with an independent exhaustive oracle."""
import argparse
import copy
import importlib.util
import itertools
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('aa_resolved',ROOT/'scripts/wings_amino_acids.py')
aa=importlib.util.module_from_spec(spec);spec.loader.exec_module(aa)


def exhaustive(ref,query):
    paths=[]
    def visit(i,j,state,score,a,b):
        if i==len(ref) and j==len(query):paths.append((score,a,b));return
        if i<len(ref) and j<len(query):visit(i+1,j+1,0,score+(2 if ref[i]==query[j] else -3),a+ref[i],b+query[j])
        if i<len(ref) and state!=2:visit(i+1,j,1,score-(1 if state==1 else 8),a+ref[i],b+'-')
        if j<len(query) and state!=1:visit(i,j+1,2,score-(1 if state==2 else 8),a+'-',b+query[j])
    visit(0,0,0,0,'','');best=max(x[0] for x in paths)
    return [x for x in paths if x[0]==best]


def path_calls(a,b):
    r=q=0;out=set();stopped=False
    for x,y in zip(a,b):
        r+=x!='-';q+=y!='-'
        if not stopped and x!=y and x!='X' and y!='X':
            kind='insertion' if x=='-' else 'deletion' if y=='-' else 'stop_gain' if y=='*' else 'substitution'
            out.add((kind,r,q,x,y))
        if y=='*':stopped=True
    return out


class ResolutionTests(unittest.TestCase):
    def test_exhaustive_short_sequences(self):
        sequences=[''.join(p) for length in range(1,5) for p in itertools.product('AC',repeat=length)]
        for ref in sequences:
            for query in sequences:
                paths=exhaustive(ref,query);comparison=aa.compare(ref,query)
                self.assertEqual(comparison['score'],paths[0][0],(ref,query))
                self.assertEqual(comparison['ambiguous_alignment'],len(paths)>1,(ref,query))
                invariant=set.intersection(*(path_calls(a,b) for _,a,b in paths))
                retained={(c['kind'],c['position'],c['query_position'],c['reference_aa'],c['query_aa']) for c in comparison['changes']}
                self.assertTrue(retained<=invariant,(ref,query,retained,invariant))
                mapping={i:set() for i in range(1,len(ref)+1)}
                for _,a,b in paths:
                    r=q=0
                    for x,y in zip(a,b):
                        r+=x!='-';q+=y!='-'
                        if x!='-':mapping[r].add((q,y=='-'))
                uncertain=[i for i,options in mapping.items() if len(options)>1]
                self.assertEqual(comparison['alignment_resolution']['uncertain_reference_positions'],uncertain)
                self.assertEqual(comparison['alignment_resolution']['callable_reference_positions'],[i for i in mapping if i not in uncertain])

    def test_keep_substitution_outside_ambiguous_repeat(self):
        c=aa.compare('MAAAACDEFGHIKLMNPQ','MAAACDEYGHIKLMNPQ')
        self.assertTrue(c['ambiguous_alignment']);self.assertEqual([x['change'] for x in c['changes']],['F9Y'])
        self.assertEqual(c['alignment_resolution']['uncertain_reference_positions'],[2,3,4,5])
        self.assertIn(9,c['alignment_resolution']['callable_reference_positions'])

    def test_ambiguous_insertion_withheld(self):
        c=aa.compare('MAAACDEFGHIK','MAAAACDEYGHIK')
        self.assertTrue(c['ambiguous_alignment']);self.assertTrue(c['alignment_resolution']['uncertain_insertion_anchors'])
        self.assertEqual([x['change'] for x in c['changes']],['F8Y'])

    def test_stop_and_unknown_across_alternatives(self):
        for ref,query in [('MAAAACDEFGHIK','MAAACD*FYHIK'),('MAAAACDEFGHIK','MAAACXEFYHIK')]:
            c=aa.compare(ref,query);paths=exhaustive(ref,query)
            invariant=set.intersection(*(path_calls(a,b) for _,a,b in paths))
            for event in c['changes']:self.assertIn((event['kind'],event['position'],event['query_position'],event['reference_aa'],event['query_aa']),invariant)
            if '*' in query:self.assertFalse(any(x['query_position']>query.index('*')+1 for x in c['changes']))

    def test_recompare_saved_proteins_preserves_inputs_and_references(self):
        with tempfile.TemporaryDirectory() as t:
            work=Path(t);evidence=work/'evidence.json';evidence.write_text(json.dumps({'schema_version':1,'entries':[]}))
            record=dict(gene='HA',segment='HA',query_sequence='MAAACDEYGHIKLMNPQ',status='AMBIGUOUS_ALIGNMENT',changes=[],issues=[])
            panel={'schema_version':1,'references':[dict(id='SYN.1:HA',accession='SYN.1',protein_id='SYN_HA.1',gene='HA',segment='HA',sequence='MAAAACDEFGHIKLMNPQ',source_url='https://example.org/synthetic')]}
            data={'sample':'sample','module_version':'1.1.0','status':'REVIEW','proteins':[record],
                  'provenance':{'panel':panel,'min_identity':.7,'min_coverage':.7,'evidence_sha256':aa.sha(evidence),'script_sha256':'old'}}
            source=work/'source.json';source.write_text(json.dumps(data));before=source.read_bytes()
            args=argparse.Namespace(inputs=[str(source)],output_dir=str(work/'new'),evidence=str(evidence));aa.recompare(args)
            result=json.loads((work/'new/sample/changes.json').read_text());protein=result['proteins'][0]
            self.assertEqual(protein['status'],'PARTIAL_INTERPRETATION');self.assertEqual([x['change'] for x in protein['changes']],['F9Y'])
            self.assertEqual(source.read_bytes(),before);self.assertEqual(result['provenance']['panel'],panel)
            evidence.write_text('{}')
            with self.assertRaises(ValueError):aa.recompare(args)
            self.assertEqual(source.read_bytes(),before)

    def test_analyze_recovers_calls_with_default_thresholds(self):
        with tempfile.TemporaryDirectory() as t:
            work=Path(t);vadr=work/'vadr';vadr.mkdir()
            query='MAAACDEYGHIKLMNPQ';codons={v:k for k,v in aa.CODE.items()}
            nt=''.join(codons[x] for x in query)+'TAA'
            sequence=work/'consensus.fasta';sequence.write_text('>x\n'+nt+'\n')
            (vadr/'x.vadr.pass.tbl').write_text('>Feature x\n1\t'+str(len(nt))+'\tCDS\n\t\t\tproduct\themagglycoprotein\n'.replace('hemagglycoprotein','hemagglutinin'))
            panel=work/'panel.json';panel.write_text(json.dumps({'schema_version':1,'references':[dict(id='SYN.1:HA',gene='HA',segment='HA',sequence='MAAAACDEFGHIKLMNPQ',accession='SYN.1',protein_id='T.1',source_url='https://example.org/synthetic')]}))
            evidence=work/'evidence.json';evidence.write_text(json.dumps({'schema_version':1,'entries':[dict(reference_id='SYN.1:HA',position=9,reference_aa='F',alternate_aa='Y',statement='Synthetic test annotation',study_context='Synthetic data',citation_url='https://example.org/synthetic')]}))
            output=work/'changes.json';aa.analyze(argparse.Namespace(sample='sample',enabled=1,vadr_dir=str(vadr),panel=str(panel),evidence=str(evidence),consensus=[('HA',str(sequence))],min_identity=.9,min_coverage=.9,output=str(output)))
            result=json.loads(output.read_text());protein=result['proteins'][0]
            self.assertEqual(protein['status'],'PARTIAL_INTERPRETATION');self.assertEqual(protein['changes'][0]['change'],'F9Y')
            self.assertEqual(len(protein['changes'][0]['evidence']),1);self.assertEqual(protein['codon_map']['codons'][7]['amino_acid'],'Y')
            aa.render(argparse.Namespace(inputs=[str(output)],html=str(work/'report.html'),tsv=str(work/'report.tsv'),json=str(work/'report.json')))
            self.assertIn('uncertain_reference_positions',(work/'report.tsv').read_text());self.assertIn('all_optimal_paths',(work/'report.tsv').read_text())

    def test_all_withheld_no_unique_position(self):
        c=aa.compare('AAAA','AAA');self.assertFalse(c['alignment_resolution']['callable_reference_positions']);self.assertEqual(c['changes'],[])
        panel={'references':[dict(id='test',gene='HA',segment='HA',sequence='AAAA',accession='SYN.1',protein_id='T.1')]}
        p=dict(gene='HA',segment='HA',query_sequence='AAA',status='READY',changes=[],issues=[])
        aa.assess_protein(p,panel,[],0,0);self.assertEqual(p['status'],'AMBIGUOUS_ALIGNMENT')


if __name__=='__main__':unittest.main()
